"""
================================================================================
TopGraphics | flight_kinematics.py
Cinemática de voo 6-DOF sem Gimbal Lock (base ortonormal local F, U, R + Rodrigues),
modo solo no convés, trem de pouso retrátil e detecção de colisão.
================================================================================
"""

# TODO: allow afterburners to be toggled on and off to increase speed
# TODO: landing gear down reduces max speed and acceleration

import math

import numpy as np

from math_utils import normalize
from scene_carrier import CARRIER_DECK_Y, CARRIER_DECK_HALF_W, CARRIER_DECK_HALF_L
from scene_canyon import canyon_height_func, canyon_center_x, CANYON_BUNKER_Z


GEAR_HEIGHT_OFFSET = 1.45       # Altura do eixo central do F-14 até a base das rodas


def rodrigues_rotation(v, k, angle_rad):
    """
    Rotaciona o vetor 'v' em torno do eixo unitário 'k' por 'angle_rad' (Fórmula de Rodrigues).
    Evita completamente o problema de Gimbal Lock dos ângulos de Euler.
    """
    k = normalize(k)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return v * cos_a + np.cross(k, v) * sin_a + k * np.dot(k, v) * (1.0 - cos_a)


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

        # Estado de solo e trem de pouso retrátil
        self.on_ground = True
        self.gear_down = True          # Comando lógico do trem de pouso (Tecla 'E')
        self.gear_deploy = 1.0         # Estado contínuo da animação: 1.0 (baixado) a 0.0 (recolhido)

        # Estado de colisão / Game Over
        self.crashed = False
        self.crash_reason = ""
        self.crash_timer = 0.0

        # Parâmetros de transformações geométricas filhas
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
        print(f"Trem de Pouso Retrátil: {estado}")

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
            target_z = CANYON_BUNKER_Z
            target_x = canyon_center_x(target_z)
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

        # Atualiza animação suave do trem de pouso retrátil
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
