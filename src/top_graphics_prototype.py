
"""
================================================================================
CEFET-MG | Departamento de Computação - Computação Gráfica
Trabalho Final: TOP GRAPHICS - Simulador de Voo 3D (F-14 Tomcat)
================================================================================
Dependências:
    pip install glfw PyOpenGL PyOpenGL_accelerate numpy
================================================================================
"""

# TODO: modularizar o projeto (arquitetura planejada na proposta)
# TODO: modelar o F14-TC
# melhorias/incrementos posteriores, n urgentes
# TODO: modelar movimento dos tailerons e spoilers de asa na rolagem, profundores na arfagem e do leme de direção na guinada (já tem em partes)
# TODO: possibilitar ativar e desativar os afterburners para aumentar velocidade
# TODO: integração com controle
# TODO: implementar as texturas em assets
# TODO: fazer nuvens geradas proceduralmente (vapor meio transparente, n solido)
# TODO: implement procedurally generated rocks for scenario 2 (use same texture and has colision)
# TODO: implementar sound effects (som dos motores, som ambiente do oceano e trilha sonora q pode ser mutada)
# TODO: menu pro projeto (titulo, seletor de cena e mapa de controles na mesma tela)
# TODO: "skins" para escolher para o F14
# TODO: implement Scenario 3 (just the aircraft in camera 3 for model analisys and reaction of the controls)
# TODO: makefile com configuracao de .env
# TODO: renderizar mais mapa conforme a necessidade ou colocar um limitador de mapa visual

import sys
import math
import time
import numpy as np

try:
    import glfw
    from OpenGL.GL import *
    from OpenGL.GLU import *
except ImportError as e:
    print("Erro ao importar bibliotecas gráficas:", e)
    print("Instale as dependências com: pip install glfw PyOpenGL numpy")
    sys.exit(1)


# ==============================================================================
# CONSTANTES GEOMÉTRICAS DO PORTA-AVIÕES E COLISÃO
# ==============================================================================
CARRIER_DECK_Y = 10.15          # Altura da superfície da pista do porta-aviões
CARRIER_DECK_HALF_W = 24.0      # Meia-largura do convés (-24 a +24 no eixo X)
CARRIER_DECK_HALF_L = 115.0     # Meio-comprimento do convés (-115 a +115 no eixo Z)
GEAR_HEIGHT_OFFSET = 1.45       # Altura do eixo central do F-14 até a base das rodas


# ==============================================================================
# 1. MATEMÁTICA VETORIAL E FUNÇÃO DE TERRENO DO CÂNION
# ==============================================================================

def normalize(v):
    """Normaliza um vetdwaor 3D."""
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-8 else v


def rodrigues_rotation(v, k, angle_rad):
    """
    Rotaciona o vetor 'v' em torno do eixo unitário 'k' por 'angle_rad' (Fórmula de Rodrigues).
    Evita completamente o problema de Gimbal Lock dos ângulos de Euler.
    """
    k = normalize(k)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return v * cos_a + np.cross(k, v) * sin_a + k * np.dot(k, v) * (1.0 - cos_a)


def compute_normal(p1, p2, p3):
    """Calcula o vetor normal unitário de um triângulo (p1, p2, p3) para iluminação (RD06)."""
    u = np.array(p2, dtype=np.float32) - np.array(p1, dtype=np.float32)
    v = np.array(p3, dtype=np.float32) - np.array(p1, dtype=np.float32)
    n = np.cross(u, v)
    return normalize(n)


def canyon_height_func(x, z):
    """
    Função matemática f(x, z) que esculpe um corredor sinuoso ("Trench Run")
    com fundo plano navegável e paredões rochosos escarpados nas laterais.
    Usada tanto para gerar a malha 3D quanto para checar colisão exata com a rocha.
    """
    center_x = 55.0 * math.sin(z * 0.0045) + 25.0 * math.cos(z * 0.011)
    dist = abs(x - center_x)

    canyon_wall = max(0.0, dist - 42.0)
    wall_height = min(165.0, (canyon_wall ** 1.35) * 0.65)

    roughness = (
        14.0 * math.sin(x * 0.045) * math.cos(z * 0.045)
        + 7.0 * math.sin(x * 0.11 + z * 0.09)
    )
    if dist < 42.0:
        return 2.0 + 1.2 * math.sin(x * 0.08) * math.cos(z * 0.08)
    return max(2.0, wall_height + roughness)


# ==============================================================================
# 2. CLASSE DO CAÇA F-14 TOMCAT (CINEMÁTICA 6-DOF, SOLO, TREM DE POUSO E COLISÃO)
# ==============================================================================

class Aircraft:
    """
    Representa o caça F-14 Tomcat no espaço 3D com referencial ortonormal local (F, U, R),
    estados de solo/porta-aviões, trem de pouso retrátil e detecção de colisão.
    """
    def __init__(self):
        self.pos = np.array([0.0, CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET, 95.0], dtype=np.float32)
        self.forward = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.right = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        self.speed = 0.0
        self.min_flight_speed = 28.0   # Velocidade mínima de sustentação (stall/takeoff)
        self.max_speed = 140.0
        self.throttle = 0.0            # 0.0 (parado no chão) a 1.0 (pós-combustão máxima)

        # Estado de solo e trem de pouso retrátil (RD08)
        self.on_ground = True
        self.gear_down = True          # Comando lógico do trem de pouso (Tecla 'E')
        self.gear_deploy = 1.0         # Estado contínuo da animação: 1.0 (baixado) a 0.0 (recolhido)

        # Estado de colisão / Game Over
        self.crashed = False
        self.crash_reason = ""
        self.crash_timer = 0.0

        # Parâmetros de transformações geométricas filhas (RD08)
        self.wing_sweep_angle = 20.0   # 20 graus (aberta) até 68 graus (fechada/supersônica)
        self.auto_wing_sweep = True
        self.elevator_pitch = 0.0
        self.elevator_roll = 0.0
        self.rudder_yaw = 0.0

    def reset(self, scene_mode):
        """Reposiciona a aeronave no estado inicial do cenário selecionado."""
        self.crashed = False
        self.crash_reason = ""
        self.crash_timer = 0.0

        self.forward = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.right = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        if scene_mode == 1:
            # Cena 1: Começa pousado e totalmente parado na popa do convés do Porta-Aviões
            self.pos = np.array([0.0, CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET, 95.0], dtype=np.float32)
            self.speed = 0.0
            self.throttle = 0.0
            self.on_ground = True
            self.gear_down = True
            self.gear_deploy = 1.0
            self.wing_sweep_angle = 20.0
        else:
            # Cena 2: Começa em voo na entrada do Cânion com trem de pouso recolhido
            self.pos = np.array([0.0, 38.0, 360.0], dtype=np.float32)
            self.speed = 65.0
            self.throttle = 0.50
            self.on_ground = False
            self.gear_down = False
            self.gear_deploy = 0.0
            self.wing_sweep_angle = 44.0

    def toggle_gear(self):
        """Alterna o recolhimento/acionamento do trem de pouso."""
        if self.on_ground:
            print("[Trem de Pouso] Não é possível recolher o trem de pouso enquanto apoiado no convés!")
            return
        self.gear_down = not self.gear_down
        estado = "BAIXANDO (DEPLOY)" if self.gear_down else "RECOLHENDO (RETRACT)"
        print(f"[RD08] Trem de Pouso Retrátil: {estado}")

    def trigger_crash(self, reason):
        """Ativa o estado de Game Over e agenda o reset automático."""
        if not self.crashed:
            self.crashed = True
            self.crash_reason = reason
            self.crash_timer = 2.0  # Segundos até reiniciar automaticamente
            self.speed = 0.0
            self.throttle = 0.0
            print(f"\n[GAME OVER] {reason} Reiniciando em 2 segundos (ou pressione 'R')...\n")

    def pitch(self, angle_rad):
        """Arfagem: rotaciona Forward e Up em torno do eixo Right."""
        self.forward = normalize(rodrigues_rotation(self.forward, self.right, angle_rad))
        self.up = normalize(np.cross(self.right, self.forward))

    def roll(self, angle_rad):
        """Rolagem: rotaciona Right e Up em torno do eixo Forward."""
        self.right = normalize(rodrigues_rotation(self.right, self.forward, angle_rad))
        self.up = normalize(np.cross(self.right, self.forward))

    def yaw(self, angle_rad):
        """Guinada: rotaciona Forward e Right em torno do eixo Up."""
        self.forward = normalize(rodrigues_rotation(self.forward, self.up, angle_rad))
        self.right = normalize(np.cross(self.forward, self.up))

    def is_within_carrier_deck_xz(self, pos=None):
        """Verifica se a coordenada (X, Z) está sobre a área útil da pista do porta-aviões."""
        p = self.pos if pos is None else pos
        return (abs(p[0]) <= CARRIER_DECK_HALF_W) and (abs(p[2]) <= CARRIER_DECK_HALF_L)

    def check_collisions(self, prev_pos, scene_mode):
        """
        Verifica todas as colisões físicas do caça com o Porta-Aviões, Oceano e Cânion.
        """
        if self.crashed:
            return

        if scene_mode == 1:
            # 1. Colisão com a Ilha de Comando (Superestrutura a estibordo do Porta-Aviões)
            # Ilha centrada em (16.5, 17.5, -15.0) com dimensões (7.0, 15.0, 28.0) + mastro
            if (11.5 <= self.pos[0] <= 21.5) and (-30.5 <= self.pos[2] <= 0.5) and (self.pos[1] <= 30.0):
                self.trigger_crash("COLISÃO COM A TORRE DE COMANDO DO PORTA-AVIÕES!")
                return

            # 2. Interação e Colisão com o Convés / Casco do Porta-Aviões
            deck_contact_y = CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET
            if self.is_within_carrier_deck_xz():
                # Se estava acima do convés e desceu até a altura de toque
                if not self.on_ground and self.pos[1] <= deck_contact_y and prev_pos[1] >= CARRIER_DECK_Y - 1.0:
                    # Condições de pouso seguro:
                    # - Trem de pouso baixado (gear_deploy > 0.75)
                    # - Taxa de descida suave (forward[1] > -0.42)
                    # - Asas niveladas (up[1] > 0.72)
                    if self.gear_deploy > 0.75 and self.forward[1] > -0.42 and self.up[1] > 0.72:
                        self.pos[1] = deck_contact_y
                        self.on_ground = True
                        # Nivela o vetor de voo paralelamente ao convés
                        self.forward[1] = 0.0
                        self.forward = normalize(self.forward)
                        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
                        self.right = normalize(np.cross(self.forward, self.up))
                        print("[Pouso] Toque suave no convés! Reduza o throttle ('S') para frear.")
                    elif self.gear_deploy <= 0.75:
                        self.pos[1] = CARRIER_DECK_Y + 0.4
                        self.trigger_crash("IMPACTO NO CONVÉS SEM O TREM DE POUSO BAIXADO!")
                        return
                    else:
                        self.pos[1] = CARRIER_DECK_Y + 0.5
                        self.trigger_crash("POUSO MUITO VIOLENTO OU DESNIVELADO NO CONVÉS!")
                        return

                # Colisão frontal/lateral com o casco do navio abaixo do nível da pista
                elif not self.on_ground and self.pos[1] < CARRIER_DECK_Y:
                    self.trigger_crash("COLISÃO COM O CASCO DO PORTA-AVIÕES!")
                    return

            # 3. Colisão com a Água (Oceano em Y = 0.0)
            if self.pos[1] <= 1.25:
                self.pos[1] = 0.8
                self.trigger_crash("COLISÃO COM O OCEANO!")
                return

        elif scene_mode == 2:
            # 1. Colisão com o Bunker Alvo no final do cânion (z = -1150)
            target_z = -1150.0
            target_x = 55.0 * math.sin(target_z * 0.0045) + 25.0 * math.cos(target_z * 0.011)
            if (abs(self.pos[0] - target_x) <= 12.5) and (abs(self.pos[2] - target_z) <= 12.5) and (self.pos[1] <= 15.5):
                self.trigger_crash("IMPACTO DIRETO COM O BUNKER ALVO!")
                return

            # 2. Colisão com o solo e paredões rochosos do Cânion Procedural
            # Testa o centro da fuselagem e as extremidades das asas esquerda/direita
            wing_span_check = 4.8
            sample_points = [
                self.pos,
                self.pos + self.right * wing_span_check,
                self.pos - self.right * wing_span_check,
                self.pos + self.forward * 5.0
            ]
            for pt in sample_points:
                ground_y = canyon_height_func(float(pt[0]), float(pt[2]))
                if pt[1] <= ground_y + 1.35:
                    self.trigger_crash("COLISÃO COM AS ROCHAS DO CÂNION!")
                    return

    def update(self, dt, pitch_input, roll_input, yaw_input, throttle_input, brake_active, scene_mode):
        """Atualiza a cinemática de solo/voo, trem de pouso e colisões."""
        # Se bateu, apenas conta o cronômetro regressivo para reiniciar
        if self.crashed:
            self.crash_timer -= dt
            if self.crash_timer <= 0.0:
                self.reset(scene_mode)
            return

        prev_pos = self.pos.copy()

        # Atualiza animação suave do trem de pouso retrátil (RD08)
        target_gear = 1.0 if self.gear_down else 0.0
        self.gear_deploy += (target_gear - self.gear_deploy) * min(1.0, 4.5 * dt)

        # Atualiza potência (throttle) entre 0.0 e 1.0
        self.throttle = np.clip(self.throttle + throttle_input * 0.50 * dt, 0.0, 1.0)

        # ======================================================================
        # MODO SOLO / PISTA DO PORTA-AVIÕES (Permite ficar parado com throttle 0)
        # ======================================================================
        if self.on_ground:
            self.gear_down = True
            self.gear_deploy = 1.0

            # Velocidade alvo no solo: 0.0 se throttle == 0, até max_speed
            target_speed = self.throttle * self.max_speed
            if self.throttle < 1e-3:
                # Desaceleração natural por atrito ou freio ativo ('S')
                decel_rate = 38.0 if brake_active else 14.0
                self.speed = max(0.0, self.speed - decel_rate * dt)
            else:
                accel_rate = 2.2 * dt
                self.speed += (target_speed - self.speed) * min(1.0, accel_rate)

            # Direção (Steering da roda de nariz) com 'A' e 'D' quando em movimento no chão
            if self.speed > 0.5 and abs(yaw_input) > 1e-4:
                steer_rate = 0.75 * min(1.0, self.speed / 25.0)
                self.yaw(yaw_input * steer_rate * dt)

            # Deslocamento horizontal sobre o convés
            self.pos += self.forward * self.speed * dt
            self.pos[1] = CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET

            # Decolagem (Rotation): se atingiu velocidade mínima de voo e puxou o manche (pitch_input > 0)
            if self.speed >= self.min_flight_speed and pitch_input > 0.1:
                self.on_ground = False
                self.pitch(0.12)  # Eleva o nariz suavemente para sair do convés
                self.pos[1] += 0.25
                print("[Voo] Decolagem realizada! Pressione 'E' para recolher o trem de pouso.")

            # Verifica se saiu dos limites da pista do porta-aviões
            elif not self.is_within_carrier_deck_xz():
                self.on_ground = False
                if self.speed < self.min_flight_speed:
                    print("[Alerta] Saiu do convés sem velocidade de sustentação!")

        # ======================================================================
        # MODO EM VOO (6-DOF Livre sem Gimbal Lock)
        # ======================================================================
        else:
            # Em voo, mesmo com throttle 0 a aeronave mantém uma velocidade mínima de planeio
            # mas se estiver muito lenta sofre perda de altitude (stall/gravidade)
            target_speed = 18.0 + self.throttle * (self.max_speed - 18.0)
            self.speed += (target_speed - self.speed) * min(1.0, 2.5 * dt)

            pitch_rate = 1.45
            roll_rate = 2.60
            yaw_rate = 0.85

            if abs(pitch_input) > 1e-4:
                self.pitch(pitch_input * pitch_rate * dt)
            if abs(roll_input) > 1e-4:
                self.roll(roll_input * roll_rate * dt)
            if abs(yaw_input) > 1e-4:
                self.yaw(yaw_input * yaw_rate * dt)

            # Deslocamento no vetor Frente
            self.pos += self.forward * self.speed * dt

            # Efeito de perda de sustentação (Stall) se a velocidade em voo cair abaixo do mínimo
            if self.speed < self.min_flight_speed:
                sink_rate = (self.min_flight_speed - self.speed) * 0.85
                self.pos[1] -= sink_rate * dt

        # Enflecamento automático das asas do F-14 (20° aberta -> 68° fechada em alta velocidade)
        if self.auto_wing_sweep:
            speed_ratio = np.clip((self.speed - 30.0) / (self.max_speed - 30.0), 0.0, 1.0)
            target_sweep = 20.0 + 48.0 * speed_ratio
            self.wing_sweep_angle += (target_sweep - self.wing_sweep_angle) * min(1.0, 5.0 * dt)

        # Deflexão visual das superfícies de controle (profundores e lemes)
        self.elevator_pitch = pitch_input * 22.0
        self.elevator_roll = roll_input * 15.0
        self.rudder_yaw = yaw_input * 20.0

        # Checa colisões com o porta-aviões, água ou rochas do cânion
        self.check_collisions(prev_pos, scene_mode)

    def get_model_matrix(self):
        """
        Constrói a matriz 4x4 homogênea (column-major para OpenGL) a partir da base (R, U, -F, P).
        """
        neg_f = -self.forward
        m = np.array([
            [self.right[0], self.right[1], self.right[2], 0.0],
            [self.up[0],    self.up[1],    self.up[2],    0.0],
            [neg_f[0],      neg_f[1],      neg_f[2],      0.0],
            [self.pos[0],   self.pos[1],   self.pos[2],   1.0]
        ], dtype=np.float32)
        return m


# ==============================================================================
# 3. GERAÇÃO PROCEDURAL DE TEXTURAS UV (RD05)
# ==============================================================================

def create_ocean_texture():
    """Gera uma textura 128x128 para a superfície do oceano com padrão de ondas."""
    size = 128
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            wave = (
                math.sin(x * 0.25) * 12
                + math.cos(y * 0.25) * 12
                + math.sin((x + y) * 0.15) * 8
            )
            r = np.clip(12 + wave * 0.4, 5, 45)
            g = np.clip(65 + wave * 0.9, 40, 110)
            b = np.clip(135 + wave * 1.4, 95, 190)
            if x % 32 == 0 or y % 32 == 0:
                r, g, b = min(255, r + 20), min(255, g + 30), min(255, b + 35)
            img[y, x] = [int(r), int(g), int(b)]

    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, size, size, 0, GL_RGB, GL_UNSIGNED_BYTE, img)
    return tex_id


def create_deck_texture():
    """Gera uma textura 256x256 de pista de pouso de porta-aviões com faixas pintadas."""
    size = 256
    img = np.full((size, size, 3), 55, dtype=np.uint8)
    rng = np.random.default_rng(42)
    noise = rng.integers(-8, 9, size=(size, size, 3), dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 35, 80).astype(np.uint8)

    for y in range(size):
        for x in range(size):
            if abs(x - 24) < 4 or abs(x - (size - 24)) < 4:
                img[y, x] = [230, 210, 60]
            if abs(x - size // 2) < 4 and (y // 16) % 2 == 0:
                img[y, x] = [235, 235, 235]
            if abs(x - size // 2 + 28) < 2:
                img[y, x] = [120, 125, 130]

    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, size, size, 0, GL_RGB, GL_UNSIGNED_BYTE, img)
    return tex_id


def create_canyon_texture():
    """Gera uma textura estratificada de rocha sedimentar/arenito para o cânion."""
    size = 128
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(size):
        strata = math.sin(y * 0.22) * 18 + math.cos(y * 0.08) * 14
        for x in range(size):
            grain = math.sin(x * 0.35 + y * 0.15) * 8
            r = np.clip(155 + strata + grain, 90, 215)
            g = np.clip(105 + strata * 0.7 + grain, 60, 165)
            b = np.clip(72 + strata * 0.5 + grain, 40, 120)
            img[y, x] = [int(r), int(g), int(b)]

    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, size, size, 0, GL_RGB, GL_UNSIGNED_BYTE, img)
    return tex_id


def create_wing_insignia_texture():
    """Gera textura metálica para fuselagem/asas com faixas navais (RD05)."""
    size = 128
    img = np.full((size, size, 3), 175, dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            if x % 32 == 0 or y % 32 == 0:
                img[y, x] = [130, 135, 142]
            if 85 < x < 110:
                img[y, x] = [35, 45, 70]
            elif 110 <= x < 116:
                img[y, x] = [220, 180, 40]

    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, size, size, 0, GL_RGB, GL_UNSIGNED_BYTE, img)
    return tex_id


# ==============================================================================
# 4. PRIMITIVAS, MODELAGEM DO F-14 E TREM DE POUSO RETRÁTIL (RD02, RD03, RD08)
# ==============================================================================

def draw_quad_with_normal(p1, p2, p3, p4, uv_scale=1.0):
    """Desenha um quadrilátero calculando automaticamente seu vetor normal e coordenadas UV."""
    n = compute_normal(p1, p2, p3)
    glNormal3fv(n)
    glTexCoord2f(0.0, 0.0)
    glVertex3fv(p1)
    glTexCoord2f(uv_scale, 0.0)
    glVertex3fv(p2)
    glTexCoord2f(uv_scale, uv_scale)
    glVertex3fv(p3)
    glTexCoord2f(0.0, uv_scale)
    glVertex3fv(p4)


def draw_tri_with_normal(p1, p2, p3):
    """Desenha um triângulo calculando seu vetor normal unitário."""
    n = compute_normal(p1, p2, p3)
    glNormal3fv(n)
    glTexCoord2f(0.0, 0.0)
    glVertex3fv(p1)
    glTexCoord2f(1.0, 0.0)
    glVertex3fv(p2)
    glTexCoord2f(0.5, 1.0)
    glVertex3fv(p3)


def draw_box(dx, dy, dz, uv_scale=1.0):
    """Desenha um paralelepípedo centrado na origem com dimensões (dx, dy, dz)."""
    hx, hy, hz = dx * 0.5, dy * 0.5, dz * 0.5
    glBegin(GL_QUADS)
    draw_quad_with_normal([-hx, hy, -hz], [-hx, hy, hz], [hx, hy, hz], [hx, hy, -hz], uv_scale)
    draw_quad_with_normal([-hx, -hy, hz], [-hx, -hy, -hz], [hx, -hy, -hz], [hx, -hy, hz], uv_scale)
    draw_quad_with_normal([hx, -hy, -hz], [-hx, -hy, -hz], [-hx, hy, -hz], [hx, hy, -hz], uv_scale)
    draw_quad_with_normal([-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz], uv_scale)
    draw_quad_with_normal([hx, -hy, hz], [hx, -hy, -hz], [hx, hy, -hz], [hx, hy, hz], uv_scale)
    draw_quad_with_normal([-hx, -hy, -hz], [-hx, -hy, hz], [-hx, hy, hz], [-hx, hy, -hz], uv_scale)
    glEnd()


def draw_wheel(radius=0.26, width=0.14, segments=12):
    """Desenha uma roda cilíndrica low-poly ao longo do eixo X (pneu preto + calota cinza)."""
    half_w = width * 0.5
    # Banda de rodagem do pneu
    glColor3f(0.12, 0.12, 0.14)
    glBegin(GL_QUAD_STRIP)
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        ny = math.cos(ang)
        nz = math.sin(ang)
        glNormal3f(0.0, ny, nz)
        glVertex3f(-half_w, radius * ny, radius * nz)
        glVertex3f( half_w, radius * ny, radius * nz)
    glEnd()

    # Calotas laterais
    for side in (-1.0, 1.0):
        glColor3f(0.75, 0.77, 0.80)
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(side, 0.0, 0.0)
        glVertex3f(side * half_w, 0.0, 0.0)
        for i in range(segments + 1):
            ang = (2.0 * math.pi * i) / segments
            y = radius * 0.65 * math.cos(ang)
            z = radius * 0.65 * math.sin(ang)
            glVertex3f(side * (half_w + 0.005), y, z)
        glEnd()


def draw_retractable_landing_gear(gear_deploy, rudder_yaw):
    """
    Renderiza o Trem de Pouso Retrátil do F-14 Tomcat usando hierarquia de matrizes (RD08).
    gear_deploy varia continuamente de 1.0 (baixado) a 0.0 (recolhido).
    """
    if gear_deploy < 0.02:
        return

    glPushAttrib(GL_TEXTURE_BIT)
    glDisable(GL_TEXTURE_2D)

    retract_angle = (1.0 - gear_deploy) * 90.0

    # 1. TREM DE POUSO DE NARIZ (Nose Gear: z = -4.1, recolhe dobrando para trás)
    glPushMatrix()
    glTranslatef(0.0, -0.32, -4.1)
    glRotatef(retract_angle, 1.0, 0.0, 0.0)

    # Porta da baia do trem dianteiro
    glColor3f(0.68, 0.70, 0.74)
    glPushMatrix()
    glTranslatef(-0.22, -0.25, 0.0)
    draw_box(0.04, 0.45, 0.70)
    glPopMatrix()

    # Haste principal (oleo strut)
    glColor3f(0.85, 0.87, 0.90)
    glPushMatrix()
    glTranslatef(0.0, -0.45, 0.0)
    draw_box(0.10, 0.90, 0.10)

    # Roda dupla dianteira (gira com o comando de leme/steering 'A' e 'D')
    glTranslatef(0.0, -0.45, 0.0)
    glRotatef(rudder_yaw, 0.0, 1.0, 0.0)
    glPushMatrix()
    glTranslatef(-0.10, 0.0, 0.0)
    draw_wheel(radius=0.22, width=0.10)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0.10, 0.0, 0.0)
    draw_wheel(radius=0.22, width=0.10)
    glPopMatrix()

    glPopMatrix()
    glPopMatrix()

    # 2. TRENS DE POUSO PRINCIPAIS (Main Gears: x = +-1.15, z = 0.85, recolhem para dentro)
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 1.15, -0.35, 0.85)
        # Rotaciona lateralmente para o interior da fuselagem ao recolher
        glRotatef(side * retract_angle, 0.0, 0.0, 1.0)

        # Porta externa da baia do trem principal
        glColor3f(0.65, 0.68, 0.72)
        glPushMatrix()
        glTranslatef(side * 0.18, -0.30, 0.0)
        draw_box(0.04, 0.55, 0.85)
        glPopMatrix()

        # Haste principal (Main Strut)
        glColor3f(0.82, 0.84, 0.88)
        glPushMatrix()
        glTranslatef(0.0, -0.42, 0.0)
        draw_box(0.14, 0.84, 0.14)

        # Roda principal de alta carga
        glTranslatef(0.0, -0.42, 0.0)
        draw_wheel(radius=0.30, width=0.18)
        glPopMatrix()

        glPopMatrix()

    glPopAttrib()


def build_f14_static_fuselage_list(wing_tex_id):
    """
    Compila em uma Display List a fuselagem estática do F-14 Tomcat usando
    seções transversais (Cross-Sections), naceles duplas e canopy.
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.75, 0.75, 0.80, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 64.0)

    # 1. RADOME E FUSELAGEM CENTRAL ("PANCAKE") POR SEÇÕES TRANSVERSAIS
    sections = [
        (-6.8, 0.02, 0.02, -0.10, -0.05),
        (-5.2, 0.38, 0.30, -0.28,  0.22),
        (-3.2, 0.58, 0.45, -0.35,  0.38),
        (-1.2, 0.85, 0.72, -0.36,  0.42),
        ( 1.5, 1.55, 1.35, -0.32,  0.32),
        ( 4.5, 1.25, 1.05, -0.25,  0.25),
        ( 5.3, 0.90, 0.80, -0.15,  0.18),
    ]

    for i in range(len(sections) - 1):
        z1, wb1, wt1, yb1, yt1 = sections[i]
        z2, wb2, wt2, yb2, yt2 = sections[i + 1]

        if i == 0:
            glColor3f(0.18, 0.19, 0.22)
        elif i == 2:
            glColor3f(0.65, 0.22, 0.20)  # Pintura vermelha anti-glare "Maverick"
        else:
            glColor3f(0.72, 0.75, 0.79)

        tl1, tr1 = [-wt1, yt1, z1], [wt1, yt1, z1]
        bl1, br1 = [-wb1, yb1, z1], [wb1, yb1, z1]
        tl2, tr2 = [-wt2, yt2, z2], [wt2, yt2, z2]
        bl2, br2 = [-wb2, yb2, z2], [wb2, yb2, z2]

        glBegin(GL_QUADS)
        draw_quad_with_normal(tl1, tl2, tr2, tr1)
        draw_quad_with_normal(br1, br2, bl2, bl1)
        draw_quad_with_normal(tr1, tr2, br2, br1)
        draw_quad_with_normal(bl1, bl2, tl2, tl1)
        glEnd()

    # 2. CANOPY DO COCKPIT (Biposto: Piloto + RIO)
    glColor3f(0.18, 0.38, 0.58)
    canopy_sec = [
        (-4.3, 0.05, 0.22),
        (-3.2, 0.36, 0.72),
        (-1.6, 0.34, 0.68),
        (-0.3, 0.12, 0.32),
    ]
    for i in range(len(canopy_sec) - 1):
        z1, w1, y1 = canopy_sec[i]
        z2, w2, y2 = canopy_sec[i + 1]
        y_base = 0.28
        glBegin(GL_QUADS)
        draw_quad_with_normal([-w1 * 0.6, y1, z1], [-w2 * 0.6, y2, z2], [w2 * 0.6, y2, z2], [w1 * 0.6, y1, z1])
        draw_quad_with_normal([w1 * 0.6, y1, z1], [w2 * 0.6, y2, z2], [w2, y_base, z2], [w1, y_base, z1])
        draw_quad_with_normal([-w1, y_base, z1], [-w2, y_base, z2], [-w2 * 0.6, y2, z2], [-w1 * 0.6, y1, z1])
        glEnd()

    # 3. NACELES DUPLAS DOS MOTORES (Entradas de ar retangulares inclinadas)
    glColor3f(0.64, 0.67, 0.71)
    for side in (-1.0, 1.0):
        x_in = side * 0.42
        x_out = side * 1.15
        glBegin(GL_QUADS)
        draw_quad_with_normal([x_out, -0.58, -1.8], [x_out, -0.52, 4.8], [x_out, 0.15, 4.8], [x_out, 0.18, -1.4])
        draw_quad_with_normal([x_in, 0.18, -1.4], [x_in, 0.15, 4.8], [x_in, -0.52, 4.8], [x_in, -0.58, -1.8])
        draw_quad_with_normal([x_in, -0.58, -1.8], [x_in, -0.52, 4.8], [x_out, -0.52, 4.8], [x_out, -0.58, -1.8])
        glEnd()

        glColor3f(0.12, 0.13, 0.15)
        glBegin(GL_QUADS)
        draw_quad_with_normal([x_in, -0.58, -1.8], [x_out, -0.58, -1.8], [x_out, 0.18, -1.4], [x_in, 0.18, -1.4])
        glEnd()
        glColor3f(0.64, 0.67, 0.71)

    # 4. LUVAS DAS ASAS (WING GLOVES FIXAS COM TEXTURA UV - RD05)
    glBindTexture(GL_TEXTURE_2D, wing_tex_id)
    glColor3f(0.76, 0.78, 0.82)
    for side in (-1.0, 1.0):
        glBegin(GL_TRIANGLES)
        p1 = [side * 0.75, 0.12, -2.2]
        p2 = [side * 2.15, 0.08, 0.3]
        p3 = [side * 0.95, 0.12, 1.8]
        if side > 0:
            draw_tri_with_normal(p1, p3, p2)
            draw_tri_with_normal([p1[0], -0.05, p1[2]], [p2[0], -0.02, p2[2]], [p3[0], -0.05, p3[2]])
        else:
            draw_tri_with_normal(p1, p2, p3)
            draw_tri_with_normal([p1[0], -0.05, p1[2]], [p3[0], -0.05, p3[2]], [p2[0], -0.02, p2[2]])
        glEnd()

    # 5. ESTABILIZADORES VERTICAIS DUPLOS INCLINADOS (TWIN TAILS)
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 0.92, 0.22, 3.6)
        glRotatef(-side * 7.0, 0.0, 0.0, 1.0)

        glColor3f(0.22, 0.24, 0.28)
        glBegin(GL_QUADS)
        draw_quad_with_normal([0.04, 0.0, -0.8], [0.04, 0.0, 1.2], [0.02, 1.65, 1.4], [0.02, 1.65, 0.3])
        draw_quad_with_normal([-0.04, 0.0, 1.2], [-0.04, 0.0, -0.8], [-0.02, 1.65, 0.3], [-0.02, 1.65, 1.4])
        glEnd()

        glColor3f(0.95, 0.78, 0.15)
        glBegin(GL_QUADS)
        draw_quad_with_normal([0.03, 1.45, 0.2], [0.03, 1.45, 1.35], [0.02, 1.68, 1.4], [0.02, 1.68, 0.3])
        draw_quad_with_normal([-0.03, 1.45, 1.35], [-0.03, 1.45, 0.2], [-0.02, 1.68, 0.3], [-0.02, 1.68, 1.4])
        glEnd()
        glPopMatrix()

    glEndList()
    return dlist


def draw_f14_wing_panel(side, wing_tex_id):
    """Desenha uma asa móvel do F-14 a partir do seu pivô local (0, 0, 0)."""
    glBindTexture(GL_TEXTURE_2D, wing_tex_id)
    glColor3f(0.75, 0.77, 0.81)
    span = 4.2 * side
    glBegin(GL_QUADS)
    if side > 0:
        draw_quad_with_normal([0.0, 0.06, -0.65], [0.0, 0.04, 0.85], [span, 0.02, 1.35], [span, 0.03, 0.35], 1.0)
        draw_quad_with_normal([0.0, -0.04, 0.85], [0.0, -0.06, -0.65], [span, -0.03, 0.35], [span, -0.02, 1.35], 1.0)
    else:
        draw_quad_with_normal([0.0, 0.04, 0.85], [0.0, 0.06, -0.65], [span, 0.03, 0.35], [span, 0.02, 1.35], 1.0)
        draw_quad_with_normal([0.0, -0.06, -0.65], [0.0, -0.04, 0.85], [span, -0.02, 1.35], [span, -0.03, 0.35], 1.0)
    glEnd()

    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    if side > 0:
        glColor3f(0.1, 1.0, 0.2)
    else:
        glColor3f(1.0, 0.15, 0.1)
    glPushMatrix()
    glTranslatef(span, 0.0, 0.85)
    draw_box(0.15, 0.08, 0.35)
    glPopMatrix()
    glPopAttrib()


def draw_f14_complete(aircraft, fuselage_dlist, wing_tex_id, sim_time):
    """
    Renderiza o F-14 Tomcat completo aplicando transformações hierárquicas (RD08):
      1. Matriz global 6-DOF da aeronave.
      2. Fuselagem estática (Display List).
      3. Trem de pouso retrátil (Rotação de recolhimento + direção da roda de nariz).
      4. Asas de geometria variável (Rotação nos pivôs locais).
      5. Profundores traseiros / Tailerons (Rotação com Pitch e Roll).
      6. Cones de Pós-Combustão (Escala dinâmica conforme o Throttle).
    """
    glPushMatrix()
    glMultMatrixf(aircraft.get_model_matrix())

    # 1. Fuselagem principal, cockpit, naceles e caudas
    glCallList(fuselage_dlist)

    # 2. Trem de Pouso Retrátil (RD08)
    draw_retractable_landing_gear(aircraft.gear_deploy, aircraft.rudder_yaw)

    # 3. Asas de Geometria Variável (RD08)
    glPushMatrix()
    glTranslatef(1.65, 0.06, 0.15)
    glRotatef(-aircraft.wing_sweep_angle, 0.0, 1.0, 0.0)
    draw_f14_wing_panel(1.0, wing_tex_id)
    glPopMatrix()

    glPushMatrix()
    glTranslatef(-1.65, 0.06, 0.15)
    glRotatef(aircraft.wing_sweep_angle, 0.0, 1.0, 0.0)
    draw_f14_wing_panel(-1.0, wing_tex_id)
    glPopMatrix()

    # 4. Profundores Horizontais Móveis (Tailerons) - RD08
    glColor3f(0.58, 0.60, 0.65)
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 1.15, -0.08, 4.4)
        deflection = aircraft.elevator_pitch + side * aircraft.elevator_roll
        glRotatef(deflection, 1.0, 0.0, 0.0)
        glBegin(GL_QUADS)
        span = side * 1.65
        if side > 0:
            draw_quad_with_normal([0.0, 0.02, -0.5], [0.0, 0.02, 0.7], [span, 0.0, 1.1], [span, 0.0, 0.3])
            draw_quad_with_normal([0.0, -0.02, 0.7], [0.0, -0.02, -0.5], [span, 0.0, 0.3], [span, 0.0, 1.1])
        else:
            draw_quad_with_normal([0.0, 0.02, 0.7], [0.0, 0.02, -0.5], [span, 0.0, 0.3], [span, 0.0, 1.1])
            draw_quad_with_normal([0.0, -0.02, -0.5], [0.0, -0.02, 0.7], [span, 0.0, 1.1], [span, 0.0, 0.3])
        glEnd()
        glPopMatrix()

    # 5. Bocais das Turbinas e Pós-Combustão (Afterburners com glScalef - RD08)
    pulse = 1.0 + 0.12 * math.sin(sim_time * 38.0)
    flame_scale_z = (0.05 + 2.6 * aircraft.throttle) * pulse
    flame_scale_xy = 0.65 + 0.45 * aircraft.throttle

    for side in (-1.0, 1.0):
        glColor3f(0.22, 0.23, 0.26)
        glPushMatrix()
        glTranslatef(side * 0.78, -0.18, 4.85)
        draw_box(0.55, 0.55, 0.65)

        # Só desenha chama do pós-combustor se throttle > 0.02
        if aircraft.throttle > 0.02 and not aircraft.crashed:
            glPushAttrib(GL_LIGHTING_BIT | GL_TEXTURE_BIT)
            glDisable(GL_LIGHTING)
            glDisable(GL_TEXTURE_2D)

            glPushMatrix()
            glTranslatef(0.0, 0.0, 0.32)
            glScalef(flame_scale_xy, flame_scale_xy, flame_scale_z)

            glColor3f(1.0, 0.55 + 0.3 * aircraft.throttle, 0.12)
            glBegin(GL_TRIANGLES)
            r = 0.24
            tip = [0.0, 0.0, 1.4]
            pts = [[-r, -r, 0.0], [r, -r, 0.0], [r, r, 0.0], [-r, r, 0.0]]
            for i in range(4):
                p_a = pts[i]
                p_b = pts[(i + 1) % 4]
                glVertex3fv(p_a)
                glVertex3fv(p_b)
                glVertex3fv(tip)
            glEnd()

            glColor3f(0.75, 0.90, 1.0)
            glScalef(0.55, 0.55, 0.65)
            glBegin(GL_TRIANGLES)
            for i in range(4):
                p_a = pts[i]
                p_b = pts[(i + 1) % 4]
                glVertex3fv(p_a)
                glVertex3fv(p_b)
                glVertex3fv(tip)
            glEnd()

            glPopMatrix()
            glPopAttrib()
        glPopMatrix()

    glPopMatrix()


# ==============================================================================
# 5. CONSTRUÇÃO DOS DOIS CENÁRIOS: PORTA-AVIÕES E CÂNION PROCEDURAL
# ==============================================================================

def build_scene1_carrier_list(ocean_tex_id, deck_tex_id):
    """
    Compila a Cena 1: Oceano amplo texturizado + Porta-Aviões USS Enterprise (CVN-65).
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    # 1. Superfície do Oceano com repetição de textura UV (RD05)
    glBindTexture(GL_TEXTURE_2D, ocean_tex_id)
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.4, 0.45, 0.5, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 32.0)
    glColor3f(0.85, 0.92, 1.0)

    grid_size = 2400.0
    step = 120.0
    uv_tile = 2.0
    glBegin(GL_QUADS)
    glNormal3f(0.0, 1.0, 0.0)
    z = -grid_size
    while z < grid_size:
        x = -grid_size
        while x < grid_size:
            glTexCoord2f(0.0, 0.0)
            glVertex3f(x, 0.0, z)
            glTexCoord2f(0.0, uv_tile)
            glVertex3f(x, 0.0, z + step)
            glTexCoord2f(uv_tile, uv_tile)
            glVertex3f(x + step, 0.0, z + step)
            glTexCoord2f(uv_tile, 0.0)
            glVertex3f(x + step, 0.0, z)
            x += step
        z += step
    glEnd()

    # 2. Casco do Porta-Aviões (USS Enterprise) centrado na origem (0, 0, 0)
    glDisable(GL_TEXTURE_2D)
    glColor3f(0.32, 0.34, 0.38)
    glPushMatrix()
    glTranslatef(0.0, 5.0, 0.0)
    draw_box(36.0, 10.0, 220.0)
    glPopMatrix()

    # 3. Convés de Voo (Flight Deck) com textura UV de pista (RD05)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, deck_tex_id)
    glColor3f(0.95, 0.95, 0.95)
    deck_w = CARRIER_DECK_HALF_W
    deck_l = CARRIER_DECK_HALF_L
    deck_y = CARRIER_DECK_Y
    glBegin(GL_QUADS)
    glNormal3f(0.0, 1.0, 0.0)
    glTexCoord2f(0.0, 0.0)
    glVertex3f(-deck_w, deck_y, -deck_l)
    glTexCoord2f(0.0, 6.0)
    glVertex3f(-deck_w, deck_y, deck_l)
    glTexCoord2f(1.0, 6.0)
    glVertex3f(deck_w, deck_y, deck_l)
    glTexCoord2f(1.0, 0.0)
    glVertex3f(deck_w, deck_y, -deck_l)
    glEnd()

    # 4. Superestrutura / Ilha de Comando ("Island") a estibordo (+X)
    glDisable(GL_TEXTURE_2D)
    glColor3f(0.45, 0.47, 0.52)
    glPushMatrix()
    glTranslatef(16.5, 17.5, -15.0)
    draw_box(7.0, 15.0, 28.0)

    glColor3f(0.20, 0.22, 0.25)
    glTranslatef(0.0, 11.0, 0.0)
    draw_box(2.2, 8.0, 4.0)
    glPopMatrix()

    # 5. Boias luminosas de aproximação na popa do porta-aviões
    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    for i in range(1, 7):
        glColor3f(0.2, 1.0, 0.3)
        glPushMatrix()
        glTranslatef(-10.0, 10.5, deck_l + i * 35.0)
        draw_box(1.5, 1.5, 1.5)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(10.0, 10.5, deck_l + i * 35.0)
        draw_box(1.5, 1.5, 1.5)
        glPopMatrix()
    glPopAttrib()

    glEndList()
    return dlist


def build_scene2_canyon_list(canyon_tex_id):
    """
    Compila a Cena 2: Cânion Procedural ("Trench Run" de Top Gun: Maverick)
    com cálculo de normais em cada face e um Bunker Alvo no final.
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    glBindTexture(GL_TEXTURE_2D, canyon_tex_id)
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.15, 0.12, 0.10, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 10.0)

    x_min, x_max, dx = -360.0, 360.0, 18.0
    z_min, z_max, dz = -1400.0, 500.0, 20.0

    xs = np.arange(x_min, x_max + dx, dx)
    zs = np.arange(z_min, z_max + dz, dz)

    heights = np.zeros((len(xs), len(zs)), dtype=np.float32)
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            heights[i, j] = canyon_height_func(x, z)

    glBegin(GL_TRIANGLES)
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            x0, x1 = xs[i], xs[i + 1]
            z0, z1 = zs[j], zs[j + 1]
            y00, y10 = heights[i, j], heights[i + 1, j]
            y01, y11 = heights[i, j + 1], heights[i + 1, j + 1]

            p00 = [x0, y00, z0]
            p10 = [x1, y10, z0]
            p01 = [x0, y01, z1]
            p11 = [x1, y11, z1]

            avg_y = 0.25 * (y00 + y10 + y01 + y11)
            if avg_y < 6.0:
                glColor3f(0.45, 0.42, 0.38)
            elif avg_y < 85.0:
                glColor3f(0.88, 0.68, 0.52)
            else:
                glColor3f(0.95, 0.85, 0.75)

            n1 = compute_normal(p00, p01, p11)
            glNormal3fv(n1)
            glTexCoord2f(0.0, 0.0); glVertex3fv(p00)
            glTexCoord2f(0.0, 1.0); glVertex3fv(p01)
            glTexCoord2f(1.0, 1.0); glVertex3fv(p11)

            n2 = compute_normal(p00, p11, p10)
            glNormal3fv(n2)
            glTexCoord2f(0.0, 0.0); glVertex3fv(p00)
            glTexCoord2f(1.0, 1.0); glVertex3fv(p11)
            glTexCoord2f(1.0, 0.0); glVertex3fv(p10)
    glEnd()

    target_z = -1150.0
    target_x = 55.0 * math.sin(target_z * 0.0045) + 25.0 * math.cos(target_z * 0.011)
    glDisable(GL_TEXTURE_2D)
    glPushMatrix()
    glTranslatef(target_x, 8.0, target_z)
    glColor3f(0.35, 0.38, 0.40)
    draw_box(22.0, 12.0, 22.0)

    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    glColor3f(1.0, 0.15, 0.15)
    glTranslatef(0.0, 6.2, 0.0)
    draw_box(10.0, 0.5, 10.0)
    glPopAttrib()
    glPopMatrix()

    glEndList()
    return dlist


# ==============================================================================
# 6. HUD DO COCKPIT E OVERLAY DE COLISÃO / GAME OVER (RD07)
# ==============================================================================

def draw_cockpit_hud(width, height, aircraft):
    """
    Desenha um Head-Up Display (HUD) verde tático em projeção ortográfica 2D
    quando o usuário está na Câmera 2 (Cockpit / Primeira Pessoa).
    """
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, width, 0, height)

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glPushAttrib(GL_ENABLE_BIT | GL_LINE_BIT)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)

    cx, cy = width * 0.5, height * 0.5
    glColor3f(0.15, 1.0, 0.25)
    glLineWidth(2.0)

    # Retículo central de mira
    glBegin(GL_LINES)
    glVertex2f(cx - 25, cy); glVertex2f(cx - 8, cy)
    glVertex2f(cx + 8, cy);  glVertex2f(cx + 25, cy)
    glVertex2f(cx, cy - 25); glVertex2f(cx, cy - 8)
    glVertex2f(cx, cy + 8);  glVertex2f(cx, cy + 25)
    glEnd()

    # Horizonte Artificial
    roll_angle = math.degrees(math.atan2(aircraft.right[1], aircraft.up[1]))
    pitch_angle = math.degrees(math.asin(np.clip(aircraft.forward[1], -1.0, 1.0)))

    glPushMatrix()
    glTranslatef(cx, cy, 0.0)
    glRotatef(-roll_angle, 0.0, 0.0, 1.0)
    glTranslatef(0.0, -pitch_angle * 4.5, 0.0)

    glBegin(GL_LINES)
    glVertex2f(-120, 0); glVertex2f(-35, 0)
    glVertex2f(35, 0);   glVertex2f(120, 0)
    for deg in (-30, -20, -10, 10, 20, 30):
        y_off = deg * 4.5
        glVertex2f(-55, y_off); glVertex2f(-25, y_off)
        glVertex2f(25, y_off);  glVertex2f(55, y_off)
    glEnd()
    glPopMatrix()

    # Barra de Potência (Throttle) à esquerda
    glBegin(GL_LINE_LOOP)
    glVertex2f(cx - 240, cy - 100)
    glVertex2f(cx - 220, cy - 100)
    glVertex2f(cx - 220, cy + 100)
    glVertex2f(cx - 240, cy + 100)
    glEnd()

    fill_h = 200.0 * aircraft.throttle
    glBegin(GL_QUADS)
    glVertex2f(cx - 238, cy - 98)
    glVertex2f(cx - 222, cy - 98)
    glVertex2f(cx - 222, cy - 98 + fill_h)
    glVertex2f(cx - 238, cy - 98 + fill_h)
    glEnd()

    # Indicador luminoso de Trem de Pouso no HUD (Verde abaixo da mira quando baixado)
    if aircraft.gear_deploy > 0.5:
        glColor3f(0.2, 1.0, 0.2)
        glBegin(GL_TRIANGLES)
        glVertex2f(cx - 12, cy - 125)
        glVertex2f(cx + 12, cy - 125)
        glVertex2f(cx, cy - 145)
        glEnd()

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


def draw_crash_overlay(width, height):
    """
    Desenha um alerta visual vermelho semitransparente na tela quando ocorre Game Over/Colisão.
    """
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, width, 0, height)

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_LINE_BIT)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    # Filtro vermelho translúcido sobre toda a tela
    glColor4f(0.85, 0.10, 0.08, 0.42)
    glBegin(GL_QUADS)
    glVertex2f(0, 0)
    glVertex2f(width, 0)
    glVertex2f(width, height)
    glVertex2f(0, height)
    glEnd()

    # Grande 'X' vermelho de impacto no centro da tela
    cx, cy = width * 0.5, height * 0.5
    glColor4f(1.0, 0.2, 0.15, 0.95)
    glLineWidth(5.0)
    glBegin(GL_LINES)
    glVertex2f(cx - 80, cy - 80); glVertex2f(cx + 80, cy + 80)
    glVertex2f(cx - 80, cy + 80); glVertex2f(cx + 80, cy - 80)
    glEnd()

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


# ==============================================================================
# 7. APLICAÇÃO PRINCIPAL E LOOP DE RENDERIZAÇÃO (GLFW + OPENGL)
# ==============================================================================

class TopGraphicsApp:
    def __init__(self, initial_scene=1):
        self.scene_mode = initial_scene  # 1 = Oceano + Porta-Aviões, 2 = Cânion Procedural
        self.camera_mode = 1             # 1 = Chase Cam, 2 = Cockpit/HUD, 3 = Orbital Mouse

        # Estados de recursos gráficos (RD05, RD06)
        self.lighting_enabled = True
        self.textures_enabled = True
        self.wireframe_mode = False

        # Parâmetros da Câmera 3 (Orbital Livre controlada por Mouse)
        self.orbit_yaw = 35.0
        self.orbit_pitch = 20.0
        self.orbit_distance = 20.0
        self.mouse_dragging = False
        self.last_mouse_x = 0.0
        self.last_mouse_y = 0.0

        # Instância única do F-14 Tomcat (Wingman removido para simplificação)
        self.player = Aircraft()
        self.player.reset(self.scene_mode)
        self.chase_cam_pos = self.player.pos - self.player.forward * 17.5 + self.player.up * 4.6
        self.chase_cam_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    def setup_lighting(self):
        """Configura o modelo de iluminação de Phong/Gouraud (RD06)."""
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)  # Luz 0: Sol Direcional
        glEnable(GL_LIGHT1)  # Luz 1: Brilho dinâmico dos pós-combustores do F-14

        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_NORMALIZE)

        glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.28, 0.26, 0.30, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE,  [1.00, 0.88, 0.72, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.00, 0.95, 0.85, 1.0])

        glLightfv(GL_LIGHT1, GL_AMBIENT,  [0.0, 0.0, 0.0, 1.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE,  [1.0, 0.55, 0.15, 1.0])
        glLightfv(GL_LIGHT1, GL_SPECULAR, [1.0, 0.70, 0.30, 1.0])
        glLightf(GL_LIGHT1, GL_CONSTANT_ATTENUATION, 1.0)
        glLightf(GL_LIGHT1, GL_LINEAR_ATTENUATION, 0.04)
        glLightf(GL_LIGHT1, GL_QUADRATIC_ATTENUATION, 0.008)

    def key_callback(self, window, key, scancode, action, mods):
        """Trata atalhos discretos de teclado para câmeras, trem de pouso, cenas e inspeção."""
        if action != glfw.PRESS:
            return

        if key == glfw.KEY_ESCAPE:
            glfw.set_window_should_close(window, True)
        elif key == glfw.KEY_1:
            self.camera_mode = 1
            print("[Câmera] Modo 1: Chase Cam (Perseguição Dinâmica)")
        elif key == glfw.KEY_2:
            self.camera_mode = 2
            print("[Câmera] Modo 2: Cockpit / HUD Tático (Primeira Pessoa)")
        elif key == glfw.KEY_3:
            self.camera_mode = 3
            print("[Câmera] Modo 3: Orbital Livre 360° (Arraste o mouse / Scroll para zoom)")
        elif key == glfw.KEY_E:
            self.player.toggle_gear()
        elif key == glfw.KEY_M:
            self.scene_mode = 2 if self.scene_mode == 1 else 1
            self.player.reset(self.scene_mode)
            self.chase_cam_pos = self.player.pos - self.player.forward * 17.5 + self.player.up * 4.6
            nome = "Cena 1: Oceano + Porta-Aviões" if self.scene_mode == 1 else "Cena 2: Cânion Procedural"
            print(f"[Cenário] Alternado para {nome}")
        elif key == glfw.KEY_R:
            self.player.reset(self.scene_mode)
            self.chase_cam_pos = self.player.pos - self.player.forward * 17.5 + self.player.up * 4.6
            print("[Voo] Posição do F-14 reiniciada.")
        elif key == glfw.KEY_L:
            self.lighting_enabled = not self.lighting_enabled
            print(f"[RD06] Iluminação Artificial: {'ATIVADA' if self.lighting_enabled else 'DESATIVADA'}")
        elif key == glfw.KEY_T:
            self.textures_enabled = not self.textures_enabled
            print(f"[RD05] Mapeamento de Texturas UV: {'ATIVADO' if self.textures_enabled else 'DESATIVADO'}")
        elif key == glfw.KEY_Z:
            self.wireframe_mode = not self.wireframe_mode
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe_mode else GL_FILL)
            print(f"[Malha 3D] Modo Wireframe: {'ATIVADO' if self.wireframe_mode else 'DESATIVADO'}")
        elif key == glfw.KEY_G:
            self.player.auto_wing_sweep = not self.player.auto_wing_sweep
            if not self.player.auto_wing_sweep:
                self.player.wing_sweep_angle = 68.0 if self.player.wing_sweep_angle < 45.0 else 20.0
            estado = "AUTOMÁTICO" if self.player.auto_wing_sweep else f"MANUAL ({self.player.wing_sweep_angle:.0f}°)"
            print(f"[RD08] Enflecamento das Asas do F-14: {estado}")

    def mouse_button_callback(self, window, button, action, mods):
        if button == glfw.MOUSE_BUTTON_LEFT:
            self.mouse_dragging = (action == glfw.PRESS)
            self.last_mouse_x, self.last_mouse_y = glfw.get_cursor_pos(window)

    def cursor_pos_callback(self, window, xpos, ypos):
        if self.mouse_dragging and self.camera_mode == 3:
            dx = xpos - self.last_mouse_x
            dy = ypos - self.last_mouse_y
            self.orbit_yaw += dx * 0.45
            self.orbit_pitch = np.clip(self.orbit_pitch + dy * 0.45, -80.0, 85.0)
        self.last_mouse_x, self.last_mouse_y = xpos, ypos

    def scroll_callback(self, window, xoffset, yoffset):
        if self.camera_mode == 3:
            self.orbit_distance = np.clip(self.orbit_distance - yoffset * 2.0, 8.0, 80.0)

    def apply_camera(self, dt):
        """Aplica gluLookAt conforme o modo de câmera ativo (RD07)."""
        p = self.player.pos
        f = self.player.forward
        u = self.player.up

        if self.camera_mode == 1:
            desired_pos = p - f * 17.5 + u * 4.6
            lerp_factor = min(1.0, 8.5 * dt)
            self.chase_cam_pos += (desired_pos - self.chase_cam_pos) * lerp_factor
            self.chase_cam_up = normalize(self.chase_cam_up + (u - self.chase_cam_up) * lerp_factor)
            target = p + f * 12.0
            gluLookAt(
                self.chase_cam_pos[0], self.chase_cam_pos[1], self.chase_cam_pos[2],
                target[0], target[1], target[2],
                self.chase_cam_up[0], self.chase_cam_up[1], self.chase_cam_up[2]
            )

        elif self.camera_mode == 2:
            eye = p + f * 2.4 + u * 0.82
            target = eye + f * 50.0
            gluLookAt(
                eye[0], eye[1], eye[2],
                target[0], target[1], target[2],
                u[0], u[1], u[2]
            )

        elif self.camera_mode == 3:
            yaw_rad = math.radians(self.orbit_yaw)
            pitch_rad = math.radians(self.orbit_pitch)
            cx = p[0] + self.orbit_distance * math.cos(pitch_rad) * math.sin(yaw_rad)
            cy = p[1] + self.orbit_distance * math.sin(pitch_rad)
            cz = p[2] + self.orbit_distance * math.cos(pitch_rad) * math.cos(yaw_rad)
            gluLookAt(cx, cy, cz, p[0], p[1], p[2], 0.0, 1.0, 0.0)

    def run(self):
        if not glfw.init():
            print("Falha ao inicializar o GLFW.")
            return

        window = glfw.create_window(
            1280, 720,
            "Top Graphics v2 - F-14 Tomcat 3D Flight Simulator (CEFET-MG)",
            None, None
        )
        if not window:
            glfw.terminate()
            return

        glfw.make_context_current(window)
        glfw.swap_interval(1)

        glfw.set_key_callback(window, self.key_callback)
        glfw.set_mouse_button_callback(window, self.mouse_button_callback)
        glfw.set_cursor_pos_callback(window, self.cursor_pos_callback)
        glfw.set_scroll_callback(window, self.scroll_callback)

        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        self.setup_lighting()

        ocean_tex = create_ocean_texture()
        deck_tex = create_deck_texture()
        canyon_tex = create_canyon_texture()
        wing_tex = create_wing_insignia_texture()

        player_fuselage_list = build_f14_static_fuselage_list(wing_tex)
        scene1_list = build_scene1_carrier_list(ocean_tex, deck_tex)
        scene2_list = build_scene2_canyon_list(canyon_tex)

        last_time = time.time()
        start_time = last_time

        print("\n" + "=" * 76)
        print(" CONTROLES DE VOO E DEMONSTRAÇÃO (TOP GRAPHICS v2 - F-14 TOMCAT)")
        print("=" * 76)
        print(" [W / S]               : Potência (Throttle) / Segure 'S' no convés para Frear")
        print(" [Setas Baixo / Cima]  : Puxar Manche (Subir/Decolar) / Empurrar (Mergulhar)")
        print(" [Setas Esq / Dir]     : Rolagem (Roll - Inclinar Asas em voo)")
        print(" [A / D]               : Guinada (Leme em voo / Direção da roda no convés)")
        print(" [E]                   : Recolher / Baixar Trem de Pouso Retrátil (RD08)")
        print(" [G]                   : Alternar Enflecamento das Asas (Auto <-> Manual)")
        print(" [1 / 2 / 3]           : Câmeras (1: Chase, 2: Cockpit/HUD, 3: Orbital Mouse)")
        print(" [M]                   : Alternar Cenário (Porta-Aviões <-> Cânion)")
        print(" [L / T / Z]           : Ligar/Desligar Luzes (L), Texturas (T), Wireframe (Z)")
        print(" [R]                   : Reiniciar Posição do Caça imediatamente")
        print(" [ESC]                 : Sair")
        print("=" * 76 + "\n")

        while not glfw.window_should_close(window):
            now = time.time()
            dt = min(0.05, now - last_time)
            last_time = now
            sim_time = now - start_time

            glfw.poll_events()

            pitch_in = 0.0
            roll_in = 0.0
            yaw_in = 0.0
            throttle_in = 0.0
            brake_active = False

            if glfw.get_key(window, glfw.KEY_UP) == glfw.PRESS:
                pitch_in -= 1.0
            if glfw.get_key(window, glfw.KEY_DOWN) == glfw.PRESS:
                pitch_in += 1.0
            if glfw.get_key(window, glfw.KEY_LEFT) == glfw.PRESS:
                roll_in -= 1.0
            if glfw.get_key(window, glfw.KEY_RIGHT) == glfw.PRESS:
                roll_in += 1.0
            if glfw.get_key(window, glfw.KEY_A) == glfw.PRESS:
                yaw_in += 1.0
            if glfw.get_key(window, glfw.KEY_D) == glfw.PRESS:
                yaw_in -= 1.0
            if glfw.get_key(window, glfw.KEY_W) == glfw.PRESS:
                throttle_in += 1.0
            if glfw.get_key(window, glfw.KEY_S) == glfw.PRESS:
                throttle_in -= 1.0
                brake_active = True

            # Atualiza cinemática, trem de pouso e colisões do F-14
            self.player.update(dt, pitch_in, roll_in, yaw_in, throttle_in, brake_active, self.scene_mode)

            # Atualiza título da janela com estado do voo, trem de pouso e alertas
            if self.player.crashed:
                title_status = f"GAME OVER: {self.player.crash_reason}"
            else:
                gear_str = "DOWN" if self.player.gear_down else "UP"
                ground_str = "NO CONVÉS" if self.player.on_ground else "EM VOO"
                title_status = (
                    f"{ground_str} | Vel: {self.player.speed * 10:.0f} kt | "
                    f"Alt: {self.player.pos[1] * 10:.0f} ft | Trem(E): {gear_str} | "
                    f"Asas(G): {self.player.wing_sweep_angle:.0f}° | Cam: {self.camera_mode}"
                )
            glfw.set_window_title(window, f"Top Graphics v2 | {title_status}")

            width, height = glfw.get_framebuffer_size(window)
            height = max(1, height)
            glViewport(0, 0, width, height)

            if self.scene_mode == 1:
                glClearColor(0.42, 0.62, 0.85, 1.0)
            else:
                glClearColor(0.78, 0.55, 0.38, 1.0)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(60.0, width / float(height), 0.5, 3500.0)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            self.apply_camera(dt)

            if self.lighting_enabled:
                glEnable(GL_LIGHTING)
                glLightfv(GL_LIGHT0, GL_POSITION, [0.6, 0.45, 0.65, 0.0])
                afterburner_pos = self.player.pos - self.player.forward * 5.5
                glLightfv(
                    GL_LIGHT1, GL_POSITION,
                    [afterburner_pos[0], afterburner_pos[1], afterburner_pos[2], 1.0]
                )
            else:
                glDisable(GL_LIGHTING)

            if self.textures_enabled:
                glEnable(GL_TEXTURE_2D)
            else:
                glDisable(GL_TEXTURE_2D)

            if self.scene_mode == 1:
                glCallList(scene1_list)
            else:
                glCallList(scene2_list)

            if self.textures_enabled:
                glEnable(GL_TEXTURE_2D)
            else:
                glDisable(GL_TEXTURE_2D)

            if self.camera_mode != 2:
                draw_f14_complete(self.player, player_fuselage_list, wing_tex, sim_time)

            if self.camera_mode == 2:
                draw_cockpit_hud(width, height, self.player)

            if self.player.crashed:
                draw_crash_overlay(width, height)

            glfw.swap_buffers(window)

        glfw.terminate()

def select_initial_scene():
    """Menu rápido no terminal ao iniciar a aplicação (ou via argumento de linha de comando)."""
    if len(sys.argv) > 1 and sys.argv[1] in ("1", "2"):
        return int(sys.argv[1])

    print("=" * 68)
    print("   TOP GRAPHICS - SIMULADOR DE VOO F-14 TOMCAT (CEFET-MG)")
    print("=" * 68)
    print(" Escolha o cenário inicial (você também pode alternar com 'M' em voo):")
    print("   [1] Cena 1: Oceano + Porta-Aviões (Inicia parado no convés para decolar)")
    print("   [2] Cena 2: Cânion Procedural ('Trench Run' - Inicia em voo)")
    print("=" * 68)
    try:
        choice = input(" Digite 1 ou 2 [Padrão = 1]: ").strip()
        if choice == "2":
            return 2
    except EOFError:
        pass
    return 1

if __name__ == "__main__":
    scene_choice = select_initial_scene()
    app = TopGraphicsApp(initial_scene=scene_choice)
    app.run()