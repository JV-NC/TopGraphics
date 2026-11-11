"""
================================================================================
TopGraphics | flight_kinematics.py
Cinemática de voo 6-DOF sem Gimbal Lock (base ortonormal local F, U, R + Rodrigues),
modo solo no convés, pós-combustor (afterburner), arrasto do trem de pouso e colisão.
================================================================================
"""

# TODO: implement maximum speeds and accelerations more consistent with the actual F-14 (1342 kt max)

import math

import numpy as np

from math_utils import normalize
from scene_carrier import CARRIER_DECK_Y, CARRIER_DECK_HALF_W, CARRIER_DECK_HALF_L
from scene_canyon import canyon_height_func, canyon_center_x, CANYON_BUNKER_Z
from scene_carrier import (
    CARRIER_DECK_Y, CARRIER_DECK_HALF_W, CARRIER_DECK_HALF_L,
    is_within_cvn65_deck_polygon, check_cvn65_extra_collisions
)

GEAR_HEIGHT_OFFSET = 1.45       # Altura do eixo central do F-14 até a base das rodas

# Constantes de desempenho aerodinâmico e propulsão
MIN_FLIGHT_SPEED = 28.0         # Velocidade mínima de sustentação (280 kt)
MIN_GLIDE_SPEED = 18.0          # Velocidade mínima de planeio em voo (180 kt)
MAX_SPEED_DRY = 110.0           # Velocidade máxima em empuxo seco / Military Power (1100 kt)
MAX_SPEED_AB = 180.0            # Velocidade máxima com pós-combustor / Afterburner (1800 kt)

ACCEL_RATE_DRY = 2.0            # Taxa base de aceleração em empuxo seco
ACCEL_RATE_AB = 3.8             # Taxa de aceleração com pós-combustor ligado

# Penalidades de arrasto aerodinâmico enquanto o trem de pouso não está 100% retraído
GEAR_DRAG_SPEED_MULT = 0.58     # Reduz a velocidade máxima em até 42% com o trem baixado
GEAR_DRAG_ACCEL_MULT = 0.50     # Reduz a aceleração em até 50% com o trem baixado
GEAR_AIRBRAKE_DECEL = 3.2       # Frenagem aerodinâmica extra ao baixar o trem em alta velocidade


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
    estados de solo/porta-aviões, pós-combustor, trem de pouso retrátil e detecção de colisão.
    """
    def __init__(self):
        self.pos = np.array([0.0, CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET, 95.0], dtype=np.float32)
        self.forward = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.right = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        self.speed = 0.0
        self.min_flight_speed = MIN_FLIGHT_SPEED
        self.max_speed = MAX_SPEED_DRY
        self.throttle = 0.0            # 0.0 (parado no chão) a 1.0 (potência máxima)
        self.afterburner = False       # Estado do pós-combustor (Tecla 'E')

        # Estado de solo e trem de pouso retrátil
        self.on_ground = True
        self.gear_down = True          # Comando lógico do trem de pouso (Tecla 'Q')
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
        self.afterburner = False

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
            self.throttle = 0.60
            self.on_ground = False
            self.gear_down = False
            self.gear_deploy = 0.0
            self.wing_sweep_angle = 40.0

        self.max_speed = self.get_effective_max_speed()

    def toggle_gear(self):
        """Alterna o recolhimento/acionamento do trem de pouso (Tecla 'Q')."""
        if self.on_ground:
            print("[Trem de Pouso] Não é possível recolher o trem de pouso enquanto apoiado no convés!")
            return
        self.gear_down = not self.gear_down
        estado = "BAIXANDO (DEPLOY - Arrasto Ativo)" if self.gear_down else "RECOLHENDO (RETRACT - Arrasto Reduzido)"
        print(f"[Trem de Pouso] {estado}")

    def toggle_afterburner(self):
        """Alterna o pós-combustor / Afterburner (Tecla 'E'), alterando vel. máxima e aceleração."""
        if self.crashed:
            return
        self.afterburner = not self.afterburner
        # Se ligou o afterburner com throttle muito baixo, aplica potência mínima para ignição
        if self.afterburner and self.throttle < 0.25:
            self.throttle = 0.25
        estado = "LIGADO (Empuxo Máximo Supersônico)" if self.afterburner else "DESLIGADO (Empuxo Seco / Militar)"
        print(f"[Afterburner] Pós-Combustor: {estado}")

    def get_effective_max_speed(self):
        """
        Calcula a velocidade máxima efetiva considerando:
          1. Estado do Pós-Combustor (MAX_SPEED_AB vs MAX_SPEED_DRY).
          2. Resistência do ar (arrasto) proporcional à extensão do trem de pouso (gear_deploy).
        """
        base_max = MAX_SPEED_AB if self.afterburner else MAX_SPEED_DRY
        drag_factor = 1.0 - (1.0 - GEAR_DRAG_SPEED_MULT) * self.gear_deploy
        return base_max * drag_factor

    def get_effective_accel_rate(self):
        """
        Calcula a taxa de aceleração efetiva considerando:
          1. Estado do Pós-Combustor (ACCEL_RATE_AB vs ACCEL_RATE_DRY).
          2. Resistência do ar enquanto o trem de pouso não estiver 100% retraído (gear_deploy > 0).
        """
        base_accel = ACCEL_RATE_AB if self.afterburner else ACCEL_RATE_DRY
        drag_factor = 1.0 - (1.0 - GEAR_DRAG_ACCEL_MULT) * self.gear_deploy
        return base_accel * drag_factor

    def trigger_crash(self, reason):
        """Ativa o estado de Game Over e agenda o reset automático."""
        if not self.crashed:
            self.crashed = True
            self.crash_reason = reason
            self.crash_timer = 2.0  # Segundos até reiniciar automaticamente
            self.speed = 0.0
            self.throttle = 0.0
            self.afterburner = False
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
        """Verifica se a coordenada (X, Z) está sobre a área útil do polígono do CVN-65."""
        p = self.pos if pos is None else pos
        return is_within_cvn65_deck_polygon(float(p[0]), float(p[2]))

    def check_collisions(self, prev_pos, scene_mode):
        """
        Verifica todas as colisões físicas do caça com o Porta-Aviões (CVN-65), Oceano e Cânion.
        """
        if self.crashed:
            return

        if scene_mode == 1:
            # 1. Colisão com a Ilha Nuclear SCANFAR, Domo Beehive, Mastro em Treliça, Guindaste ou JBD
            hit_struct, reason = check_cvn65_extra_collisions(self.pos, self.right, self.forward)
            if hit_struct:
                self.trigger_crash(reason)
                return

            # 2. Interação e Colisão com o Convés / Casco do Porta-Aviões
            deck_contact_y = CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET
            if self.is_within_carrier_deck_xz():
                # Se estava acima do convés e desceu até a altura de toque
                if not self.on_ground and self.pos[1] <= deck_contact_y and prev_pos[1] >= CARRIER_DECK_Y - 1.0:
                    if self.gear_deploy > 0.75 and self.forward[1] > -0.42 and self.up[1] > 0.72:
                        self.pos[1] = deck_contact_y
                        self.on_ground = True
                        self.afterburner = False
                        self.forward[1] = 0.0
                        self.forward = normalize(self.forward)
                        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
                        self.right = normalize(np.cross(self.forward, self.up))
                        print("[Pouso] Toque suave no convés! Pós-combustor desligado. Segure 'S' para frear.")
                    elif self.gear_deploy <= 0.75:
                        self.pos[1] = CARRIER_DECK_Y + 0.4
                        self.trigger_crash("IMPACTO NO CONVÉS SEM O TREM DE POUSO BAIXADO!")
                        return
                    else:
                        self.pos[1] = CARRIER_DECK_Y + 0.5
                        self.trigger_crash("POUSO MUITO VIOLENTO OU DESNIVELADO NO CONVÉS!")
                        return

                # Colisão frontal/lateral com o casco/sponsons do navio abaixo do nível da pista
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
        """Atualiza a cinemática de solo/voo, pós-combustor, arrasto do trem de pouso e colisões."""
        if self.crashed:
            self.crash_timer -= dt
            if self.crash_timer <= 0.0:
                self.reset(scene_mode)
            return

        prev_pos = self.pos.copy()

        # Atualiza animação suave do trem de pouso retrátil (0.0 = recolhido, 1.0 = baixado)
        target_gear = 1.0 if self.gear_down else 0.0
        self.gear_deploy += (target_gear - self.gear_deploy) * min(1.0, 4.5 * dt)

        # Atualiza potência (throttle) entre 0.0 e 1.0
        self.throttle = np.clip(self.throttle + throttle_input * 0.50 * dt, 0.0, 1.0)

        # Se o piloto zerar o throttle completamente, desarma o pós-combustor automaticamente
        if self.throttle < 1e-3 and self.afterburner:
            self.afterburner = False
            print("[Afterburner] Pós-combustor desarmado automaticamente (Throttle = 0%).")

        # Calcula velocidade máxima e aceleração efetivas (considerando Afterburner e Arrasto do Trem)
        self.max_speed = self.get_effective_max_speed()
        accel_rate = self.get_effective_accel_rate()

        # ======================================================================
        # MODO SOLO / PISTA DO PORTA-AVIÕES (Permite ficar parado com throttle 0)
        # ======================================================================
        if self.on_ground:
            self.gear_down = True
            self.gear_deploy = 1.0
            self.max_speed = self.get_effective_max_speed()
            accel_rate = self.get_effective_accel_rate()

            target_speed = self.throttle * self.max_speed
            if self.throttle < 1e-3:
                decel_rate = 38.0 if brake_active else 14.0
                self.speed = max(0.0, self.speed - decel_rate * dt)
            else:
                self.speed += (target_speed - self.speed) * min(1.0, accel_rate * dt)

            # Direção (Steering da roda de nariz) com 'A' e 'D' quando em movimento no chão
            if self.speed > 0.5 and abs(yaw_input) > 1e-4:
                steer_rate = 0.75 * min(1.0, self.speed / 25.0)
                self.yaw(yaw_input * steer_rate * dt)

            # Deslocamento horizontal sobre o convés
            self.pos += self.forward * self.speed * dt
            self.pos[1] = CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET

            # Decolagem (Rotation): atingiu velocidade mínima de voo e puxou o manche (pitch_input > 0)
            if self.speed >= self.min_flight_speed and pitch_input > 0.1:
                self.on_ground = False
                self.pitch(0.12)
                self.pos[1] += 0.25
                print("[Voo] Decolagem realizada! Pressione 'Q' para recolher o trem de pouso e reduzir o arrasto.")

            # Verifica se saiu dos limites da pista do porta-aviões
            elif not self.is_within_carrier_deck_xz():
                self.on_ground = False
                if self.speed < self.min_flight_speed:
                    print("[Alerta] Saiu do convés sem velocidade de sustentação!")

        # ======================================================================
        # MODO EM VOO (6-DOF Livre sem Gimbal Lock)
        # ======================================================================
        else:
            target_speed = MIN_GLIDE_SPEED + self.throttle * (self.max_speed - MIN_GLIDE_SPEED)

            # Se a velocidade atual está acima da velocidade alvo (ex: baixou o trem de pouso ou
            # desligou o afterburner em alta velocidade), aplica arrasto aerodinâmico de frenagem
            if self.speed > target_speed:
                drag_decel = 1.8 + GEAR_AIRBRAKE_DECEL * self.gear_deploy
                self.speed += (target_speed - self.speed) * min(1.0, drag_decel * dt)
            else:
                self.speed += (target_speed - self.speed) * min(1.0, accel_rate * dt)

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

        # Enflecamento automático das asas do F-14 (20° aberta -> 68° fechada em regime supersônico)
        if self.auto_wing_sweep:
            speed_ratio = np.clip((self.speed - 35.0) / (MAX_SPEED_AB - 35.0), 0.0, 1.0)
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
