
"""
================================================================================
CEFET-MG | Departamento de Computação - Computação Gráfica
Trabalho Final: TOP GRAPHICS - Simulador de Voo 3D (F-14 Tomcat)
================================================================================
Dependências:
    pip install glfw PyOpenGL PyOpenGL_accelerate numpy
================================================================================
"""

# TODO: remover o Wingman / Iceman para simplificar o projeto
# TODO: ter trem de pouso retrátil
# TODO: possibilitar o caça ficar parado (throttle 0) caso esteja no chão 
# TODO: ter colisão do porta aviões com o trem de pouso
# TODO: ter colisão do caça com a água no cenário 1 e com as rochas/solo do cenário 2 ("gameover" para reset caso seja mais fácil)
# TODO: modularizar o projeto (arquitetura planejada na proposta)
# TODO: implementar as texturas em assets

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
# 1. MATEMÁTICA VETORIAL E CINEMÁTICA 6-DOF (SEM GIMBAL LOCK)
# ==============================================================================

def normalize(v):
    """Normaliza um vetor 3D."""
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


class Aircraft:
    """
    Representa um caça F-14 Tomcat no espaço 3D com referencial ortonormal local (F, U, R)
    e parâmetros de animação hierárquica (RD08).
    """
    def __init__(self, pos=(0.0, 25.0, 0.0), is_wingman=False):
        self.pos = np.array(pos, dtype=np.float32)
        # Base vetorial ortogonal local: Frente (-Z inicial), Cima (+Y), Direita (+X)
        self.forward = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.right = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        self.speed = 45.0
        self.min_speed = 15.0
        self.max_speed = 140.0
        self.throttle = 0.35  # 0.0 a 1.0

        # Parâmetros de transformações geométricas filhas (RD08)
        self.wing_sweep_angle = 20.0   # 20 graus (aberta) até 68 graus (fechada/supersônica)
        self.auto_wing_sweep = True
        self.elevator_pitch = 0.0      # Ângulo atual dos profundores
        self.elevator_roll = 0.0       # Diferencial dos profundores (tailerons)
        self.rudder_yaw = 0.0          # Ângulo dos lemes duplos
        self.is_wingman = is_wingman

    def reset(self, scene_mode):
        """Reposiciona a aeronave no início do cenário selecionado."""
        if scene_mode == 1:
            # Posicionado próximo ao Porta-Aviões para aproximação/sobrevoo
            self.pos = np.array([0.0, 18.0, 140.0], dtype=np.float32)
            self.speed = 40.0
            self.throttle = 0.30
        else:
            # Entrada do Cânion Procedural (Trench Run)
            self.pos = np.array([0.0, 35.0, 350.0], dtype=np.float32)
            self.speed = 65.0
            self.throttle = 0.50

        self.forward = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.right = np.array([1.0, 0.0, 0.0], dtype=np.float32)

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

    def update(self, dt, pitch_input, roll_input, yaw_input, throttle_input):
        """Atualiza a cinemática de voo e as partes móveis do F-14."""
        # Atualiza potência (throttle) e velocidade linear
        self.throttle = np.clip(self.throttle + throttle_input * 0.45 * dt, 0.0, 1.0)
        target_speed = self.min_speed + self.throttle * (self.max_speed - self.min_speed)
        self.speed += (target_speed - self.speed) * min(1.0, 3.0 * dt)

        # Taxas angulares em radianos/s
        pitch_rate = 1.45
        roll_rate = 2.60
        yaw_rate = 0.85

        if abs(pitch_input) > 1e-4:
            self.pitch(pitch_input * pitch_rate * dt)
        if abs(roll_input) > 1e-4:
            self.roll(roll_input * roll_rate * dt)
        if abs(yaw_input) > 1e-4:
            self.yaw(yaw_input * yaw_rate * dt)

        # Deslocamento por translação no vetor Frente (RD08)
        self.pos += self.forward * self.speed * dt

        # Proteção simples de colisão com o piso/oceano
        if self.pos[1] < 2.5:
            self.pos[1] = 2.5
            if self.forward[1] < 0:
                self.forward[1] = 0.0
                self.forward = normalize(self.forward)
                self.right = normalize(np.cross(self.forward, np.array([0.0, 1.0, 0.0])))
                self.up = normalize(np.cross(self.right, self.forward))

        # Enflecamento automático das asas do F-14 (20° em baixa vel -> 68° em alta vel)
        if self.auto_wing_sweep:
            target_sweep = 20.0 + 48.0 * self.throttle
            self.wing_sweep_angle += (target_sweep - self.wing_sweep_angle) * min(1.0, 5.0 * dt)

        # Deflexão visual das superfícies de controle (profundores e lemes)
        self.elevator_pitch = pitch_input * 22.0
        self.elevator_roll = roll_input * 15.0
        self.rudder_yaw = yaw_input * 20.0

    def get_model_matrix(self):
        """
        Constrói a matriz 4x4 homogênea (column-major para OpenGL) a partir da base (R, U, -F, P).
        No modelo local do F-14, o nariz aponta para -Z, topo para +Y e asa direita para +X.
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
# 2. GERAÇÃO PROCEDURAL DE TEXTURAS UV (RD05)
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
            # Linhas de grade sutis para reforçar a percepção de velocidade
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
            # Bordas da pista brancas/amarelas
            if abs(x - 24) < 4 or abs(x - (size - 24)) < 4:
                img[y, x] = [230, 210, 60]
            # Faixa central tracejada branca
            if abs(x - size // 2) < 4 and (y // 16) % 2 == 0:
                img[y, x] = [235, 235, 235]
            # Trilho da catapulta de lançamento
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
            # Linhas de painéis metálicos da aeronave
            if x % 32 == 0 or y % 32 == 0:
                img[y, x] = [130, 135, 142]
            # Faixa de esquadrão naval na ponta
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
# 3. PRIMITIVAS E MODELAGEM LOW-POLY DO F-14 TOMCAT (RD02, RD03, RD08)
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
    # Topo (+Y)
    draw_quad_with_normal([-hx, hy, -hz], [-hx, hy, hz], [hx, hy, hz], [hx, hy, -hz], uv_scale)
    # Base (-Y)
    draw_quad_with_normal([-hx, -hy, hz], [-hx, -hy, -hz], [hx, -hy, -hz], [hx, -hy, hz], uv_scale)
    # Frente (-Z)
    draw_quad_with_normal([hx, -hy, -hz], [-hx, -hy, -hz], [-hx, hy, -hz], [hx, hy, -hz], uv_scale)
    # Trás (+Z)
    draw_quad_with_normal([-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz], uv_scale)
    # Direita (+X)
    draw_quad_with_normal([hx, -hy, hz], [hx, -hy, -hz], [hx, hy, -hz], [hx, hy, hz], uv_scale)
    # Esquerda (-X)
    draw_quad_with_normal([-hx, -hy, -hz], [-hx, -hy, hz], [-hx, hy, hz], [-hx, hy, -hz], uv_scale)
    glEnd()


def build_f14_static_fuselage_list(wing_tex_id, is_wingman=False):
    """
    Compila em uma Display List a fuselagem estática do F-14 Tomcat usando
    seções transversais (Cross-Sections), naceles duplas e canopy.
    O nariz aponta para -Z (z = -6.8) e os bocais ficam em +Z (z = +5.3).
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    # Materiais especulares metálicos para o caça (RD06)
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.75, 0.75, 0.80, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 64.0)

    # 1. RADOME E FUSELAGEM CENTRAL ("PANCAKE") POR SEÇÕES TRANSVERSAIS
    # Cada seção é definida por (z, half_width_bottom, half_width_top, y_bottom, y_top)
    sections = [
        (-6.8, 0.02, 0.02, -0.10, -0.05),  # Ponta do nariz (Pitot/Radome)
        (-5.2, 0.38, 0.30, -0.28,  0.22),  # Base do radome preto
        (-3.2, 0.58, 0.45, -0.35,  0.38),  # Seção do Cockpit frontal
        (-1.2, 0.85, 0.72, -0.36,  0.42),  # Cockpit traseiro (RIO) + Glove
        ( 1.5, 1.55, 1.35, -0.32,  0.32),  # Seção central larga ("Pancake")
        ( 4.5, 1.25, 1.05, -0.25,  0.25),  # Traseira entre os motores
        ( 5.3, 0.90, 0.80, -0.15,  0.18),  # Fechamento traseiro (Beavertail)
    ]

    for i in range(len(sections) - 1):
        z1, wb1, wt1, yb1, yt1 = sections[i]
        z2, wb2, wt2, yb2, yt2 = sections[i + 1]

        # Cor diferenciada para o bico do radar (preto/antracite) vs fuselagem cinza naval
        if i == 0:
            glColor3f(0.18, 0.19, 0.22)
        elif i == 2 and is_wingman:
            glColor3f(0.25, 0.40, 0.68)  # Pintura azul "Iceman" no nariz do Wingman
        elif i == 2:
            glColor3f(0.65, 0.22, 0.20)  # Pintura vermelha "Maverick" anti-glare
        else:
            glColor3f(0.72, 0.75, 0.79)

        # Vértices das duas seções (sentido anti-horário)
        tl1, tr1 = [-wt1, yt1, z1], [wt1, yt1, z1]
        bl1, br1 = [-wb1, yb1, z1], [wb1, yb1, z1]
        tl2, tr2 = [-wt2, yt2, z2], [wt2, yt2, z2]
        bl2, br2 = [-wb2, yb2, z2], [wb2, yb2, z2]

        glBegin(GL_QUADS)
        # Topo
        draw_quad_with_normal(tl1, tl2, tr2, tr1)
        # Base
        draw_quad_with_normal(br1, br2, bl2, bl1)
        # Lateral Direita
        draw_quad_with_normal(tr1, tr2, br2, br1)
        # Lateral Esquerda
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
        # Topo do canopy
        draw_quad_with_normal([-w1 * 0.6, y1, z1], [-w2 * 0.6, y2, z2], [w2 * 0.6, y2, z2], [w1 * 0.6, y1, z1])
        # Lateral direita do vidro
        draw_quad_with_normal([w1 * 0.6, y1, z1], [w2 * 0.6, y2, z2], [w2, y_base, z2], [w1, y_base, z1])
        # Lateral esquerda do vidro
        draw_quad_with_normal([-w1, y_base, z1], [-w2, y_base, z2], [-w2 * 0.6, y2, z2], [-w1 * 0.6, y1, z1])
        glEnd()

    # 3. NACELES DUPLAS DOS MOTORES TF30 / F110 (Entradas de ar retangulares inclinadas)
    glColor3f(0.64, 0.67, 0.71)
    for side in (-1.0, 1.0):
        x_in = side * 0.42
        x_out = side * 1.15
        glBegin(GL_QUADS)
        # Parede externa da nacele
        draw_quad_with_normal([x_out, -0.58, -1.8], [x_out, -0.52, 4.8], [x_out, 0.15, 4.8], [x_out, 0.18, -1.4])
        # Parede interna da nacele
        draw_quad_with_normal([x_in, 0.18, -1.4], [x_in, 0.15, 4.8], [x_in, -0.52, 4.8], [x_in, -0.58, -1.8])
        # Fundo da nacele
        draw_quad_with_normal([x_in, -0.58, -1.8], [x_in, -0.52, 4.8], [x_out, -0.52, 4.8], [x_out, -0.58, -1.8])
        glEnd()

        # Boca escura da tomada de ar frontal (Intake ramp)
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

    # 5. ESTABILIZADORES VERTICAIS DUPLOS INCLINADOS (TWIN TAILS CARACTERÍSTICOS DO F-14)
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 0.92, 0.22, 3.6)
        glRotatef(-side * 7.0, 0.0, 0.0, 1.0)  # Inclinação canted outward típica do Tomcat

        # Cor do esquadrão nas caudas (VF-84 Jolly Rogers / Top Gun)
        if is_wingman:
            glColor3f(0.20, 0.35, 0.65)
        else:
            glColor3f(0.22, 0.24, 0.28)

        glBegin(GL_QUADS)
        # Face externa da deriva
        draw_quad_with_normal([0.04, 0.0, -0.8], [0.04, 0.0, 1.2], [0.02, 1.65, 1.4], [0.02, 1.65, 0.3])
        # Face interna da deriva
        draw_quad_with_normal([-0.04, 0.0, 1.2], [-0.04, 0.0, -0.8], [-0.02, 1.65, 0.3], [-0.02, 1.65, 1.4])
        glEnd()

        # Ponta amarela/laranja do esquadrão no topo do estabilizador vertical
        if is_wingman:
            glColor3f(0.90, 0.90, 0.95)
        else:
            glColor3f(0.95, 0.78, 0.15)
        glBegin(GL_QUADS)
        draw_quad_with_normal([0.03, 1.45, 0.2], [0.03, 1.45, 1.35], [0.02, 1.68, 1.4], [0.02, 1.68, 0.3])
        draw_quad_with_normal([-0.03, 1.45, 1.35], [-0.03, 1.45, 0.2], [-0.02, 1.68, 0.3], [-0.02, 1.68, 1.4])
        glEnd()
        glPopMatrix()

    glEndList()
    return dlist


def draw_f14_wing_panel(side, wing_tex_id):
    """
    Desenha uma asa móvel do F-14 a partir do seu pivô local (0, 0, 0).
    side = +1.0 (asa direita) ou -1.0 (asa esquerda).
    """
    glBindTexture(GL_TEXTURE_2D, wing_tex_id)
    glColor3f(0.75, 0.77, 0.81)
    span = 4.2 * side
    glBegin(GL_QUADS)
    if side > 0:
        # Superfície superior
        draw_quad_with_normal([0.0, 0.06, -0.65], [0.0, 0.04, 0.85], [span, 0.02, 1.35], [span, 0.03, 0.35], 1.0)
        # Superfície inferior
        draw_quad_with_normal([0.0, -0.04, 0.85], [0.0, -0.06, -0.65], [span, -0.03, 0.35], [span, -0.02, 1.35], 1.0)
    else:
        # Superfície superior
        draw_quad_with_normal([0.0, 0.04, 0.85], [0.0, 0.06, -0.65], [span, 0.03, 0.35], [span, 0.02, 1.35], 1.0)
        # Superfície inferior
        draw_quad_with_normal([0.0, -0.06, -0.65], [0.0, -0.04, 0.85], [span, -0.02, 1.35], [span, -0.03, 0.35], 1.0)
    glEnd()

    # Luzes de navegação nas pontas das asas (Vermelha na esquerda, Verde na direita)
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
      3. Asas de geometria variável (Rotação nos pivôs locais).
      4. Profundores traseiros / Tailerons (Rotação com Pitch e Roll).
      5. Cones de Pós-Combustão (Escala dinâmica conforme o Throttle).
    """
    glPushMatrix()
    # Aplica a matriz 4x4 da base ortonormal local (Translação + Orientação 3D)
    glMultMatrixf(aircraft.get_model_matrix())

    # 1. Fuselagem principal, cockpit, naceles e caudas
    glCallList(fuselage_dlist)

    # 2. Asas de Geometria Variável (RD08: Translação para o pivô -> Rotação -> Desenho)
    # Asa Direita (+X)
    glPushMatrix()
    glTranslatef(1.65, 0.06, 0.15)
    glRotatef(-aircraft.wing_sweep_angle, 0.0, 1.0, 0.0)
    draw_f14_wing_panel(1.0, wing_tex_id)
    glPopMatrix()

    # Asa Esquerda (-X)
    glPushMatrix()
    glTranslatef(-1.65, 0.06, 0.15)
    glRotatef(aircraft.wing_sweep_angle, 0.0, 1.0, 0.0)
    draw_f14_wing_panel(-1.0, wing_tex_id)
    glPopMatrix()

    # 3. Profundores Horizontais Móveis (Tailerons) - RD08
    glColor3f(0.58, 0.60, 0.65)
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 1.15, -0.08, 4.4)
        # Combina arfagem (pitch) e rolagem diferencial (tailerons)
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

    # 4. Bocais das Turbinas e Pós-Combustão (Afterburners com glScalef - RD08)
    pulse = 1.0 + 0.12 * math.sin(sim_time * 38.0)
    flame_scale_z = (0.3 + 2.4 * aircraft.throttle) * pulse
    flame_scale_xy = 0.75 + 0.35 * aircraft.throttle

    for side in (-1.0, 1.0):
        # Anel metálico externo do bocal (Nozzle)
        glColor3f(0.22, 0.23, 0.26)
        glPushMatrix()
        glTranslatef(side * 0.78, -0.18, 4.85)
        draw_box(0.55, 0.55, 0.65)

        # Cone de fogo do Afterburner (Desativa iluminação para brilho próprio emissivo)
        glPushAttrib(GL_LIGHTING_BIT | GL_TEXTURE_BIT)
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)

        glPushMatrix()
        glTranslatef(0.0, 0.0, 0.32)
        glScalef(flame_scale_xy, flame_scale_xy, flame_scale_z)

        # Chama externa laranja/dourada
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

        # Núcleo interno azulado/branco de alta temperatura
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
# 4. CONSTRUÇÃO DOS DOIS CENÁRIOS: PORTA-AVIÕES E CÂNION PROCEDURAL
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
    deck_w = 24.0
    deck_l = 115.0
    deck_y = 10.15
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

    # Mastro do Radar e Ponte de Comando no topo da Ilha
    glColor3f(0.20, 0.22, 0.25)
    glTranslatef(0.0, 11.0, 0.0)
    draw_box(2.2, 8.0, 4.0)
    glPopMatrix()

    # 5. Boias luminosas de aproximação na popa do porta-aviões (Guia visual de pouso)
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


def canyon_height_func(x, z):
    """
    Função matemática f(x, z) que esculpe um corredor sinuoso ("Trench Run")
    com fundo plano navegável e paredões rochosos escarpados nas laterais.
    """
    # Centro sinuoso do cânion ao longo de Z
    center_x = 55.0 * math.sin(z * 0.0045) + 25.0 * math.cos(z * 0.011)
    dist = abs(x - center_x)

    # Largura do corredor central = 42 metros de cada lado
    canyon_wall = max(0.0, dist - 42.0)
    wall_height = min(165.0, (canyon_wall ** 1.35) * 0.65)

    # Rugosidade das montanhas usando ondas trigonométricas compostas
    roughness = (
        14.0 * math.sin(x * 0.045) * math.cos(z * 0.045)
        + 7.0 * math.sin(x * 0.11 + z * 0.09)
    )
    if dist < 42.0:
        # Leito do rio/cânion quase plano
        return 2.0 + 1.2 * math.sin(x * 0.08) * math.cos(z * 0.08)
    return max(2.0, wall_height + roughness)


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

    # Pré-calcula a malha de alturas Y(x, z)
    heights = np.zeros((len(xs), len(zs)), dtype=np.float32)
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            heights[i, j] = canyon_height_func(x, z)

    # Renderiza a malha de triângulos com coordenadas de textura UV e cores por altitude (RD03, RD05, RD06)
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
                # Leito do cânion mais escuro/úmido
                glColor3f(0.45, 0.42, 0.38)
            elif avg_y < 85.0:
                # Paredões de arenito avermelhado
                glColor3f(0.88, 0.68, 0.52)
            else:
                # Topo das montanhas mais claro
                glColor3f(0.95, 0.85, 0.75)

            # Triângulo 1
            n1 = compute_normal(p00, p01, p11)
            glNormal3fv(n1)
            glTexCoord2f(0.0, 0.0); glVertex3fv(p00)
            glTexCoord2f(0.0, 1.0); glVertex3fv(p01)
            glTexCoord2f(1.0, 1.0); glVertex3fv(p11)

            # Triângulo 2
            n2 = compute_normal(p00, p11, p10)
            glNormal3fv(n2)
            glTexCoord2f(0.0, 0.0); glVertex3fv(p00)
            glTexCoord2f(1.0, 1.0); glVertex3fv(p11)
            glTexCoord2f(1.0, 0.0); glVertex3fv(p10)
    glEnd()

    # Alvo da Missão ("Bunker Nuclear") no final do Cânion (z = -1150)
    target_z = -1150.0
    target_x = 55.0 * math.sin(target_z * 0.0045) + 25.0 * math.cos(target_z * 0.011)
    glDisable(GL_TEXTURE_2D)
    glPushMatrix()
    glTranslatef(target_x, 8.0, target_z)
    glColor3f(0.35, 0.38, 0.40)
    draw_box(22.0, 12.0, 22.0)

    # Marcação vermelha brilhante no centro do alvo
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
# 5. HUD DO COCKPIT E SISTEMA DE CÂMERAS (RD07)
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

    # Retículo central de mira (Crosshair do F-14)
    glBegin(GL_LINES)
    glVertex2f(cx - 25, cy); glVertex2f(cx - 8, cy)
    glVertex2f(cx + 8, cy);  glVertex2f(cx + 25, cy)
    glVertex2f(cx, cy - 25); glVertex2f(cx, cy - 8)
    glVertex2f(cx, cy + 8);  glVertex2f(cx, cy + 25)
    glEnd()

    # Horizonte Artificial (Pitch Ladder) que inclina conforme o Roll e Pitch do caça
    roll_angle = math.degrees(math.atan2(aircraft.right[1], aircraft.up[1]))
    pitch_angle = math.degrees(math.asin(np.clip(aircraft.forward[1], -1.0, 1.0)))

    glPushMatrix()
    glTranslatef(cx, cy, 0.0)
    glRotatef(-roll_angle, 0.0, 0.0, 1.0)
    glTranslatef(0.0, -pitch_angle * 4.5, 0.0)

    glBegin(GL_LINES)
    # Linha do horizonte principal
    glVertex2f(-120, 0); glVertex2f(-35, 0)
    glVertex2f(35, 0);   glVertex2f(120, 0)
    # Escadas de arfagem (+/- 10, 20, 30 graus)
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

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


# ==============================================================================
# 6. APLICAÇÃO PRINCIPAL E LOOP DE RENDERIZAÇÃO (GLFW + OPENGL)
# ==============================================================================

class TopGraphicsApp:
    def __init__(self, initial_scene=1):
        self.scene_mode = initial_scene  # 1 = Oceano + Porta-Aviões, 2 = Cânion Procedural
        self.camera_mode = 1             # 1 = Chase Cam, 2 = Cockpit/HUD, 3 = Orbital Mouse

        # Estados de recursos gráficos (RD05, RD06)
        self.lighting_enabled = True
        self.textures_enabled = True
        self.wireframe_mode = False
        self.wingman_formation = True

        # Parâmetros da Câmera 3 (Orbital Livre controlada por Mouse)
        self.orbit_yaw = 35.0
        self.orbit_pitch = 20.0
        self.orbit_distance = 22.0
        self.mouse_dragging = False
        self.last_mouse_x = 0.0
        self.last_mouse_y = 0.0

        # Posição suavizada da Chase Cam (Câmera 1)
        self.chase_cam_pos = np.array([0.0, 22.0, 160.0], dtype=np.float32)
        self.chase_cam_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)

        # Instâncias dos dois caças F-14 Tomcat (Maverick + Wingman Iceman)
        self.player = Aircraft()
        self.wingman = Aircraft(is_wingman=True)
        self.player.reset(self.scene_mode)
        self.chase_cam_pos = self.player.pos - self.player.forward * 18.0 + self.player.up * 5.0

    def setup_lighting(self):
        """Configura o modelo de iluminação de Phong/Gouraud (RD06)."""
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)  # Luz 0: Sol Direcional (Golden Hour / Pôr do Sol Top Gun)
        glEnable(GL_LIGHT1)  # Luz 1: Brilho dinâmico dos pós-combustores do F-14

        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_NORMALIZE)

        # Propriedades do Sol (Luz Direcional vinda do horizonte oeste)
        glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.28, 0.26, 0.30, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE,  [1.00, 0.88, 0.72, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.00, 0.95, 0.85, 1.0])

        # Propriedades da Luz 1 (Fogo laranja dos motores do caça)
        glLightfv(GL_LIGHT1, GL_AMBIENT,  [0.0, 0.0, 0.0, 1.0])
        glLightfv(GL_LIGHT1, GL_DIFFUSE,  [1.0, 0.55, 0.15, 1.0])
        glLightfv(GL_LIGHT1, GL_SPECULAR, [1.0, 0.70, 0.30, 1.0])
        glLightf(GL_LIGHT1, GL_CONSTANT_ATTENUATION, 1.0)
        glLightf(GL_LIGHT1, GL_LINEAR_ATTENUATION, 0.04)
        glLightf(GL_LIGHT1, GL_QUADRATIC_ATTENUATION, 0.008)

    def key_callback(self, window, key, scancode, action, mods):
        """Trata atalhos discretos de teclado para câmeras, cenas e inspeção técnica."""
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
        elif key == glfw.KEY_M:
            self.scene_mode = 2 if self.scene_mode == 1 else 1
            self.player.reset(self.scene_mode)
            self.chase_cam_pos = self.player.pos - self.player.forward * 18.0 + self.player.up * 5.0
            nome = "Cena 1: Oceano + Porta-Aviões" if self.scene_mode == 1 else "Cena 2: Cânion Procedural"
            print(f"[Cenário] Alternado para {nome}")
        elif key == glfw.KEY_R:
            self.player.reset(self.scene_mode)
            self.chase_cam_pos = self.player.pos - self.player.forward * 18.0 + self.player.up * 5.0
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
        elif key == glfw.KEY_F:
            self.wingman_formation = not self.wingman_formation
            modo = "Formação Tática (Ala)" if self.wingman_formation else "Patrulha Circular Independente"
            print(f"[Instanciação] Caça 2 (Iceman): {modo}")

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

    def update_wingman(self, sim_time):
        """Atualiza a posição e orientação do segundo F-14 instanciado na cena."""
        if self.wingman_formation:
            # Voa em formação escalonada à direita e ligeiramente atrás do jogador
            offset = self.player.right * 14.0 - self.player.forward * 10.0 + self.player.up * 1.5
            self.wingman.pos = self.player.pos + offset
            self.wingman.forward = self.player.forward.copy()
            self.wingman.up = self.player.up.copy()
            self.wingman.right = self.player.right.copy()
            self.wingman.throttle = self.player.throttle
            self.wingman.wing_sweep_angle = self.player.wing_sweep_angle
        else:
            # Voa em uma grande órbita circular inclinada ao redor do centro da cena
            radius = 220.0
            omega = 0.32
            angle = sim_time * omega
            self.wingman.pos = np.array([
                radius * math.cos(angle),
                65.0 + 15.0 * math.sin(angle * 2.0),
                radius * math.sin(angle)
            ], dtype=np.float32)

            tangent = np.array([-math.sin(angle), 0.0, math.cos(angle)], dtype=np.float32)
            self.wingman.forward = normalize(tangent)
            bank_up = normalize(np.array([-0.45 * math.cos(angle), 1.0, -0.45 * math.sin(angle)], dtype=np.float32))
            self.wingman.right = normalize(np.cross(self.wingman.forward, bank_up))
            self.wingman.up = normalize(np.cross(self.wingman.right, self.wingman.forward))
            self.wingman.throttle = 0.75
            self.wingman.wing_sweep_angle = 55.0

    def apply_camera(self, dt):
        """Aplica gluLookAt conforme o modo de câmera ativo (RD07)."""
        p = self.player.pos
        f = self.player.forward
        u = self.player.up

        if self.camera_mode == 1:
            # Modo 1: Chase Cam com interpolação suave (efeito de inércia/aceleração)
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
            # Modo 2: Cockpit / Primeira Pessoa (dentro do canopy olhando para frente)
            eye = p + f * 2.4 + u * 0.82
            target = eye + f * 50.0
            gluLookAt(
                eye[0], eye[1], eye[2],
                target[0], target[1], target[2],
                u[0], u[1], u[2]
            )

        elif self.camera_mode == 3:
            # Modo 3: Orbital Esférica Livre controlada por Mouse
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
            "Top Graphics - F-14 Tomcat 3D Flight Simulator (CEFET-MG)",
            None, None
        )
        if not window:
            glfw.terminate()
            return

        glfw.make_context_current(window)
        glfw.swap_interval(1)  # V-Sync ativado (60 FPS estáveis)

        # Registra callbacks de teclado e mouse
        glfw.set_key_callback(window, self.key_callback)
        glfw.set_mouse_button_callback(window, self.mouse_button_callback)
        glfw.set_cursor_pos_callback(window, self.cursor_pos_callback)
        glfw.set_scroll_callback(window, self.scroll_callback)

        # Configurações globais do OpenGL
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        self.setup_lighting()

        # Compilação das Texturas Procedurais (RD05) e Display Lists
        ocean_tex = create_ocean_texture()
        deck_tex = create_deck_texture()
        canyon_tex = create_canyon_texture()
        wing_tex = create_wing_insignia_texture()

        player_fuselage_list = build_f14_static_fuselage_list(wing_tex, is_wingman=False)
        wingman_fuselage_list = build_f14_static_fuselage_list(wing_tex, is_wingman=True)
        scene1_list = build_scene1_carrier_list(ocean_tex, deck_tex)
        scene2_list = build_scene2_canyon_list(canyon_tex)

        last_time = time.time()
        start_time = last_time

        print("\n" + "=" * 72)
        print(" CONTROLES DE VOO E DEMONSTRAÇÃO (TOP GRAPHICS - F-14 TOMCAT)")
        print("=" * 72)
        print(" [Setas Cima/Baixo]    : Arfagem (Pitch - Mergulhar / Subir)")
        print(" [Setas Esq/Dir]       : Rolagem (Roll - Inclinar Asas / Tonneau)")
        print(" [A / D]               : Guinada (Yaw - Leme Horizontal)")
        print(" [W / S]               : Potência das Turbinas (Throttle / Afterburner)")
        print(" [1 / 2 / 3]           : Câmeras (1: Chase, 2: Cockpit/HUD, 3: Orbital Mouse)")
        print(" [M]                   : Alternar Cenário (Porta-Aviões <-> Cânion)")
        print(" [G]                   : Alternar Enflecamento das Asas (Auto <-> Manual)")
        print(" [F]                   : Alternar Caça Ala (Formação <-> Órbita Circular)")
        print(" [L / T / Z]           : Ligar/Desligar Luzes (L), Texturas (T), Wireframe (Z)")
        print(" [R]                   : Reiniciar Posição do Caça")
        print(" [ESC]                 : Sair")
        print("=" * 72 + "\n")

        while not glfw.window_should_close(window):
            now = time.time()
            dt = min(0.05, now - last_time)
            last_time = now
            sim_time = now - start_time

            glfw.poll_events()

            # Leitura contínua dos comandos de voo
            pitch_in = 0.0
            roll_in = 0.0
            yaw_in = 0.0
            throttle_in = 0.0

            if glfw.get_key(window, glfw.KEY_UP) == glfw.PRESS:
                pitch_in -= 1.0  # Empurrar o manche (mergulhar)
            if glfw.get_key(window, glfw.KEY_DOWN) == glfw.PRESS:
                pitch_in += 1.0  # Puxar o manche (subir)
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

            # Atualiza cinemática 6-DOF do jogador e do caça Ala
            self.player.update(dt, pitch_in, roll_in, yaw_in, throttle_in)
            self.update_wingman(sim_time)

            # Atualiza título da janela com telemetria de voo em tempo real
            glfw.set_window_title(
                window,
                f"Top Graphics | F-14 Tomcat | Vel: {self.player.speed * 10:.0f} kt | "
                f"Alt: {self.player.pos[1] * 10:.0f} ft | Asas: {self.player.wing_sweep_angle:.0f}° | "
                f"Cam: {self.camera_mode} | Cena: {self.scene_mode}"
            )

            # Configuração do Viewport e Projeção Perspectiva
            width, height = glfw.get_framebuffer_size(window)
            height = max(1, height)
            glViewport(0, 0, width, height)

            # Cor do céu: pôr do sol alaranjado na Cena 2 ou azul naval na Cena 1
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

            # Posiciona a câmera virtual ativa (RD07)
            self.apply_camera(dt)

            # Configura estados de iluminação (RD06) e textura (RD05)
            if self.lighting_enabled:
                glEnable(GL_LIGHTING)
                # Posiciona a luz direcional (Sol) e a luz pontual nos motores do F-14
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

            # Renderiza o Cenário Selecionado (Cena 1: Porta-Aviões ou Cena 2: Cânion)
            if self.scene_mode == 1:
                glCallList(scene1_list)
            else:
                glCallList(scene2_list)

            if self.textures_enabled:
                glEnable(GL_TEXTURE_2D)
            else:
                glDisable(GL_TEXTURE_2D)

            # Renderiza o F-14 do Jogador (exceto se estiver na câmera de cockpit 1ª pessoa)
            if self.camera_mode != 2:
                draw_f14_complete(self.player, player_fuselage_list, wing_tex, sim_time)

            # Renderiza o segundo F-14 instanciado (Wingman / Iceman)
            draw_f14_complete(self.wingman, wingman_fuselage_list, wing_tex, sim_time)

            # Se estiver na Câmera 2 (Cockpit), desenha o HUD verde tático na tela
            if self.camera_mode == 2:
                draw_cockpit_hud(width, height, self.player)

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
    print("   [1] Cena 1: Oceano Texturizado + Porta-Aviões (USS Enterprise)")
    print("   [2] Cena 2: Cânion Procedural ('Trench Run' - Top Gun: Maverick)")
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
