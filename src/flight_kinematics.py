"""
================================================================================
TopGraphics | flight_kinematics.py
Cinemática e Aerodinâmica 6-DOF sem Gimbal Lock (base ortonormal local F, U, R + Rodrigues):
  - Velocidades e acelerações calibradas pelo F-14D Super Tomcat real
    (Empuxo Seco ~780 kt / Pós-Combustão Mach 2.34 = 1342 kt = 2485 km/h).
  - Vetor de velocidade 3D real com sustentação aerodinâmica, ângulo de ataque (AoA),
    gravidade longitudinal/vertical e física real de Estol (queda de nariz e queda de asa
    quando em baixa velocidade ou acima do AoA crítico).
  - Cálculo de Força G (G-Load) em curvas fechadas e puxadas de manche.
  - Superfícies móveis articuladas e acopladas à física:
      * Wing Spoilers de rolagem com trava automática em enflecamento >= 57°.
      * Trailing-Edge Flaps (Tecla 'F') com ganho de sustentação/redução de estol e
        trava/recolhimento automático quando o enflecamento >= 26°.
      * Leading-Edge Slats automáticos (CADC: baixa velocidade, flaps e alto AoA).
      * Split Dorsal & Ventral Air Brakes no Beaver Tail (Tecla 'B').
  - Modo solo no convés do CVN-65, modo de inspeção estacionária (Cena 3), colisões
    e mundo periódico ("Roundabout").
================================================================================
"""

import math

import numpy as np

from math_utils import normalize
from scene_utils import wrap_position_roundabout
from scene_canyon import (
    canyon_height_func,
    canyon_center_x,
    CANYON_BUNKER_Z,
    check_canyon_rock_collisions,
)
from scene_carrier import (
    CARRIER_DECK_Y,
    CARRIER_DECK_HALF_W,
    CARRIER_DECK_HALF_L,
    is_within_cvn65_deck_polygon,
    check_cvn65_extra_collisions,
    get_ocean_wave_height,
    trigger_ocean_splash,
)

GEAR_HEIGHT_OFFSET = 1.45          # Altura do eixo central do F-14 até a base das rodas

# ==============================================================================
# CONSTANTES AERODINÂMICAS E PROPULSÃO CALIBRADAS (F-14D SUPER TOMCAT)
# Escala do simulador: 1.0 unidade/s = 10 knots no HUD (134.2 -> 1342 kt / Mach 2.34)
# ==============================================================================
MAX_SPEED_DRY = 78.0               # Empuxo Militar Seco (~780 kt)
MAX_SPEED_AB = 134.2               # Pós-Combustão Máxima (1342 kt / 2485 km/h / Mach 2.34)

MIN_FLIGHT_SPEED_CLEAN = 19.5      # Velocidade de estol limpo com asas em 20° (195 kt)
MIN_FLIGHT_SPEED_FLAPS = 13.5      # Velocidade de estol com flaps/slats 100% (135 kt)
SWEEP_STALL_PENALTY = 5.0          # Acréscimo na vel. de estol com asas totalmente enflechadas (+50 kt)
MIN_FLIGHT_SPEED = MIN_FLIGHT_SPEED_CLEAN

ACCEL_RATE_DRY = 1.15              # Taxa de resposta de aceleração em empuxo seco
ACCEL_RATE_AB = 2.45               # Taxa de resposta de aceleração com pós-combustor (GE F110-GE-400)
DECK_CATAPULT_ACCEL_BOOST = 0.34   # Aceleração progressiva no convés (~3s / ~80-110m de corrida)

# Gravidade e aerodinâmica de sustentação / estol
GRAVITY_WORLD = 9.0                # Aceleração gravitacional efetiva na escala do simulador (u/s²)
CRITICAL_AOA_CLEAN_DEG = 21.0      # Ângulo de ataque crítico sem flaps/slats
CRITICAL_AOA_FLAP_BONUS = 4.0      # Ganho de AoA crítico com flaps estendidos
CRITICAL_AOA_SLAT_BONUS = 3.5      # Ganho de AoA crítico com slats de bordo de ataque estendidos

# Penalidades de arrasto do Trem de Pouso (Tecla 'Q')
GEAR_DRAG_SPEED_MULT = 0.58        # Reduz a velocidade máxima em até 42% com o trem baixado
GEAR_DRAG_ACCEL_MULT = 0.55        # Reduz a aceleração em até 45% com o trem baixado
GEAR_AIRBRAKE_DECEL = 2.8          # Frenagem aerodinâmica extra do trem baixado

# Split Dorsal & Ventral Air Brakes no Beaver Tail (Tecla 'B')
AIRBRAKE_ACTUATION_RATE = 4.8      # Velocidade de abertura/fechamento hidráulico (~0.5s)
AIRBRAKE_DRAG_DECEL = 3.0          # Forte frenagem aerodinâmica com speedbrakes abertos
AIRBRAKE_SPEED_MULT = 0.72         # Limita a velocidade máxima efetiva em até 28% enquanto aberto

# Trailing-Edge Flaps (Tecla 'F') com trava de enflecamento das asas
FLAP_LOCKOUT_SWEEP_DEG = 26.0      # Recolhe e trava os flaps se o enflecamento atingir >= 26°
FLAP_MAX_AUTO_SPEED = 42.0         # Velocidade máxima (420 kt) mantendo asas em 20° para flaps em modo AUTO
FLAP_ACTUATION_RATE = 0.58         # Duração de ~1.7s..1.9s sincronizada com FLAPS.wav
FLAP_MAX_DEFLECTION_DEG = 35.0     # Deflexão máxima dos flaps para baixo (35°)
FLAP_DRAG_DECEL = 1.45             # Arrasto induzido pelos flaps estendidos
FLAP_SPEED_MULT = 0.76             # Reduz a velocidade máxima efetiva enquanto estendidos

# Leading-Edge Slats Automáticos (CADC do F-14)
SLAT_ACTUATION_RATE = 3.2          # Resposta hidráulica automática dos slats

# Wing Spoilers de rolagem com trava automática em >= 57°
SPOILER_LOCKOUT_SWEEP_DEG = 57.0   # Trava os spoilers rente à asa a partir de 57° de enflecamento
SPOILER_MAX_DEFLECTION_DEG = 55.0  # Deflexão máxima para cima dos painéis de spoiler (F-14 real: ~55°)
SPOILER_ACTUATION_RATE = 14.0      # Velocidade de resposta hidráulica dos painéis
ROLL_RATE_TAILERON_ONLY = 1.95     # Taxa de rolagem apenas com tailerons diferenciais (>= 57°)
ROLL_RATE_SPOILER_BOOST = 0.85     # Ganho adicional de rolagem com wing spoilers ativos (< 57°)
SPOILER_PROVERSE_YAW = 0.14        # Assistência de guinada coordenada (reduz guinada adversa na curva)
SPOILER_ROLL_DRAG_DECEL = 0.45     # Arrasto aerodinâmico sutil ao erguer os spoilers em rolagem


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
    vetor de velocidade 3D real (sustentação, gravidade, AoA, estol e força G),
    superfícies móveis articuladas e detecção de colisões.
    """
    def __init__(self):
        self.pos = np.array([0.0, CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET, 95.0], dtype=np.float32)
        self.forward = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.right = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        self.velocity = np.zeros(3, dtype=np.float32)

        self.speed = 0.0
        self.min_flight_speed = MIN_FLIGHT_SPEED_CLEAN
        self.max_speed = MAX_SPEED_DRY
        self.throttle = 0.0            # 0.0 (parado no chão) a 1.0 (potência máxima)
        self.afterburner = False       # Estado do pós-combustor (Tecla 'E')

        # Estado de solo e trem de pouso retrátil
        self.on_ground = True
        self.gear_down = True          # Comando lógico do trem de pouso (Tecla 'Q')
        self.gear_deploy = 1.0         # Estado contínuo da animação: 1.0 (baixado) a 0.0 (recolhido)

        # Estado de colisão / Game Over ('solid' ou 'water')
        self.crashed = False
        self.crash_reason = ""
        self.crash_type = "solid"
        self.crash_timer = 0.0

        # Telemetria aerodinâmica (Força G, Ângulo de Ataque, Estol e Sustentação)
        self.g_load = 1.0              # Fator de carga normal (G)
        self.aoa_deg = 0.0             # Ângulo de ataque atual (graus)
        self.critical_aoa_deg = CRITICAL_AOA_CLEAN_DEG
        self.lift_efficiency = 1.0     # Eficiência de sustentação [0.0 .. 1.0]
        self.is_stalling = False       # True quando abaixo da vel. de estol ou acima do AoA crítico
        self._stall_roll_sign = 1.0    # Direção da queda de asa no estol severo

        # Deslocamento de teleporte toroidal ocorrido no último frame (para sincronizar a Chase Cam)
        self.last_wrap_delta = np.zeros(3, dtype=np.float32)

        # Parâmetros de transformações geométricas filhas
        self.wing_sweep_angle = 20.0   # 20 graus (aberta) até 68 graus (fechada/supersônica)
        self.auto_wing_sweep = True

        # Tailerons diferenciais (arfagem + rolagem) e lemes verticais duplos (guinada)
        self.taileron_pitch = 0.0
        self.taileron_roll = 0.0
        self.elevator_pitch = 0.0      # Alias retrocompatível para taileron_pitch
        self.elevator_roll = 0.0       # Alias retrocompatível para taileron_roll
        self.rudder_yaw = 0.0

        # Wing Spoilers de rolagem (4 painéis por asa; travados rente à asa em >= 57°)
        self.spoilers_locked = False
        self.spoiler_authority = 1.0
        self.spoiler_left_deg = 0.0
        self.spoiler_right_deg = 0.0

        # Trailing-Edge Flaps (Tecla 'F'; travados/recolhidos automaticamente em >= 26°)
        self.flaps_down = False
        self.flaps_deploy = 0.0        # 0.0 (recolhidos) a 1.0 (35° estendidos)
        self.flaps_locked = False
        self.flaps_moving = False

        # Leading-Edge Slats automáticos (CADC)
        self.slat_deploy = 0.0         # 0.0 (recolhidos) a 1.0 (estendidos/droop)

        # Split Dorsal & Ventral Air Brakes no Beaver Tail (Tecla 'B')
        self.airbrake_deployed = False
        self.airbrake_deploy = 0.0     # 0.0 (fechados) a 1.0 (totalmente abertos)

    def reset(self, scene_mode):
        """Reposiciona a aeronave no estado inicial do cenário selecionado (1, 2 ou 3)."""
        self.crashed = False
        self.crash_reason = ""
        self.crash_type = "solid"
        self.crash_timer = 0.0
        self.afterburner = False
        self.last_wrap_delta = np.zeros(3, dtype=np.float32)

        self.forward = np.array([0.0, 0.0, -1.0], dtype=np.float32)
        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.right = np.array([1.0, 0.0, 0.0], dtype=np.float32)

        self.taileron_pitch = 0.0
        self.taileron_roll = 0.0
        self.elevator_pitch = 0.0
        self.elevator_roll = 0.0
        self.rudder_yaw = 0.0
        self.spoiler_left_deg = 0.0
        self.spoiler_right_deg = 0.0

        self.airbrake_deployed = False
        self.airbrake_deploy = 0.0
        self.flaps_moving = False
        self.g_load = 1.0
        self.aoa_deg = 0.0
        self.lift_efficiency = 1.0
        self.is_stalling = False
        self._stall_roll_sign = 1.0

        if scene_mode == 1:
            # Cena 1: Pousado e parado no convés do CVN-65 (pronto para decolagem)
            self.pos = np.array([0.0, CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET, 95.0], dtype=np.float32)
            self.speed = 0.0
            self.velocity = np.zeros(3, dtype=np.float32)
            self.throttle = 0.0
            self.on_ground = True
            self.gear_down = True
            self.gear_deploy = 1.0
            self.wing_sweep_angle = 20.0
            self.flaps_down = False
            self.flaps_deploy = 0.0
            self.slat_deploy = 0.35
        elif scene_mode == 2:
            # Cena 2: Em voo na entrada do Cânion (~480 kt, trem e flaps recolhidos)
            self.pos = np.array([0.0, 38.0, 360.0], dtype=np.float32)
            self.speed = 48.0
            self.velocity = self.forward * self.speed
            self.throttle = 0.62
            self.on_ground = False
            self.gear_down = False
            self.gear_deploy = 0.0
            self.wing_sweep_angle = 36.0
            self.flaps_down = False
            self.flaps_deploy = 0.0
            self.slat_deploy = 0.0
        else:
            # Cena 3: Modo de Inspeção Técnica e Customização de Skins (suspenso e estacionário)
            self.pos = np.array([0.0, 15.0, 0.0], dtype=np.float32)
            self.speed = 32.0
            self.velocity = self.forward * self.speed
            self.throttle = 0.25
            self.on_ground = False
            self.gear_down = True
            self.gear_deploy = 1.0
            self.wing_sweep_angle = 20.0
            self.flaps_down = False
            self.flaps_deploy = 0.0
            self.slat_deploy = 0.40

        self.spoilers_locked = (self.wing_sweep_angle >= SPOILER_LOCKOUT_SWEEP_DEG)
        self.flaps_locked = (self.wing_sweep_angle >= FLAP_LOCKOUT_SWEEP_DEG)
        self.spoiler_authority = self._compute_spoiler_authority()
        self.min_flight_speed = self.get_effective_stall_speed()
        self.critical_aoa_deg = self.get_effective_critical_aoa()
        self.max_speed = self.get_effective_max_speed()

    # ==========================================================================
    # CONTROLES DISCRETOS DE SISTEMAS (TREM, AFTERBURNER, FLAPS, AIR BRAKES)
    # ==========================================================================

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
        if self.afterburner and self.throttle < 0.25:
            self.throttle = 0.25
        estado = "LIGADO (Mach 2.34 / 1342 kt Máx)" if self.afterburner else "DESLIGADO (Empuxo Militar Seco ~780 kt)"
        print(f"[Afterburner] Pós-Combustor: {estado}")

    def toggle_flaps(self):
        """
        Alterna os Trailing-Edge Flaps (Tecla 'F').
        Respeita a trava de enflecamento das asas (>= 26°):
          - Se já estiverem estendidos, permite recolher sempre.
          - Para estender, exige enflecamento < 26° (ou modo automático com vel. <= 420 kt).
        Retorna True se o estado lógico dos flaps foi alterado.
        """
        if self.crashed:
            return False

        if self.flaps_down:
            self.flaps_down = False
            print("[Flaps] RECOLHENDO (0°)")
            return True

        # Verifica trava de enflecamento das asas
        if self.wing_sweep_angle >= FLAP_LOCKOUT_SWEEP_DEG:
            if self.auto_wing_sweep and self.speed <= FLAP_MAX_AUTO_SPEED:
                # Em modo automático e velocidade segura, abre as asas para 20° para aceitar os flaps
                self.flaps_down = True
                print("[Flaps] ESTENDENDO (35° - Ganho de Sustentação / Menor Velocidade de Estol)")
                return True
            print(
                f"[Flaps] TRAVADOS! Reduza a velocidade ou abra as asas abaixo de "
                f"{FLAP_LOCKOUT_SWEEP_DEG:.0f}° (Atual: {self.wing_sweep_angle:.0f}°)."
            )
            return False

        self.flaps_down = True
        print("[Flaps] ESTENDENDO (35° - Ganho de Sustentação / Menor Velocidade de Estol)")
        return True

    def toggle_airbrake(self):
        """Alterna os Split Dorsal & Ventral Air Brakes no Beaver Tail (Tecla 'B')."""
        if self.crashed:
            return False
        self.airbrake_deployed = not self.airbrake_deployed
        estado = "ABERTOS (Frenagem Aerodinâmica Ativa)" if self.airbrake_deployed else "FECHADOS"
        print(f"[Air Brakes] Speedbrakes: {estado}")
        return True

    # ==========================================================================
    # CÁLCULOS AERODINÂMICOS (VELOCIDADE MÁXIMA, ESTOL, AOA CRÍTICO, SPOILERS)
    # ==========================================================================

    def _compute_spoiler_authority(self):
        """
        Retorna a autoridade aerodinâmica dos wing spoilers [0.0 .. 1.0] em função do
        ângulo de enflecamento das asas (travamento total >= 57°).
        """
        if self.wing_sweep_angle >= SPOILER_LOCKOUT_SWEEP_DEG:
            return 0.0
        sweep_frac = np.clip(
            (self.wing_sweep_angle - 20.0) / max(1.0, (SPOILER_LOCKOUT_SWEEP_DEG - 20.0)),
            0.0, 1.0
        )
        return float(1.0 - 0.35 * sweep_frac)

    def get_effective_stall_speed(self):
        """
        Calcula a velocidade de estol efetiva (em unidades internas; x10 = kt):
          - Limpo (20°): 195 kt (19.5)
          - Com Flaps 100% + Slats: reduz até ~135 kt (13.5), facilitando pousos e decolagens!
          - Com asas enflechadas (68°): sobe até ~245 kt (24.5).
        """
        sweep_norm = np.clip((self.wing_sweep_angle - 20.0) / 48.0, 0.0, 1.0)
        flap_gain = (MIN_FLIGHT_SPEED_CLEAN - MIN_FLIGHT_SPEED_FLAPS) * self.flaps_deploy
        slat_gain = 1.4 * self.slat_deploy * (1.0 - 0.5 * self.flaps_deploy)
        stall_spd = MIN_FLIGHT_SPEED_CLEAN + SWEEP_STALL_PENALTY * sweep_norm - flap_gain - slat_gain
        return float(max(12.5, stall_spd))

    def get_effective_critical_aoa(self):
        """Calcula o ângulo de ataque crítico (graus) ampliado pelos flaps e slats."""
        return float(
            CRITICAL_AOA_CLEAN_DEG
            + CRITICAL_AOA_FLAP_BONUS * self.flaps_deploy
            + CRITICAL_AOA_SLAT_BONUS * self.slat_deploy
        )

    def get_effective_max_speed(self):
        """
        Calcula a velocidade máxima efetiva considerando Pós-Combustor, Trem de Pouso,
        Flaps e Split Air Brakes.
        """
        base_max = MAX_SPEED_AB if self.afterburner else MAX_SPEED_DRY
        gear_factor = 1.0 - (1.0 - GEAR_DRAG_SPEED_MULT) * self.gear_deploy
        flap_factor = 1.0 - (1.0 - FLAP_SPEED_MULT) * self.flaps_deploy
        brake_factor = 1.0 - (1.0 - AIRBRAKE_SPEED_MULT) * self.airbrake_deploy
        return float(base_max * gear_factor * flap_factor * brake_factor)

    def get_effective_accel_rate(self):
        """Calcula a taxa de aceleração efetiva considerando Pós-Combustor e arrasto de trem/freios."""
        base_accel = ACCEL_RATE_AB if self.afterburner else ACCEL_RATE_DRY
        gear_factor = 1.0 - (1.0 - GEAR_DRAG_ACCEL_MULT) * self.gear_deploy
        brake_factor = 1.0 - 0.45 * self.airbrake_deploy
        return float(base_accel * gear_factor * brake_factor)

    def get_effective_roll_rate(self):
        """
        Calcula a taxa de rolagem efetiva (rad/s) combinando os tailerons diferenciais
        com o auxílio dos wing spoilers quando destravados (< 57°).
        """
        if self.spoilers_locked:
            return ROLL_RATE_TAILERON_ONLY
        deployed_frac = max(self.spoiler_left_deg, self.spoiler_right_deg) / SPOILER_MAX_DEFLECTION_DEG
        spoiler_boost = ROLL_RATE_SPOILER_BOOST * self.spoiler_authority * (0.35 + 0.65 * deployed_frac)
        return ROLL_RATE_TAILERON_ONLY + spoiler_boost

    def _update_control_surfaces(self, dt, pitch_input, roll_input, yaw_input, scene_mode):
        """
        Atualiza as deflexões hidráulicas de todas as superfícies móveis:
          - Wing Spoilers (travamento em >= 57°)
          - Flaps (travamento e recolhimento automático em >= 26°)
          - Slats automáticos (CADC: flaps, baixa velocidade e alto AoA; recolhem ao enflechar)
          - Split Dorsal & Ventral Air Brakes
          - Tailerons diferenciais e Lemes duplos
        """
        # 1. Travamento automático dos Wing Spoilers em >= 57°
        prev_sp_locked = self.spoilers_locked
        self.spoilers_locked = (self.wing_sweep_angle >= SPOILER_LOCKOUT_SWEEP_DEG)
        self.spoiler_authority = self._compute_spoiler_authority()
        if self.spoilers_locked != prev_sp_locked:
            estado = "TRAVADOS (Enflecamento >= 57°)" if self.spoilers_locked else "ATIVOS (< 57° - Auxílio de Rolagem)"
            print(f"[Wing Spoilers] {estado}")

        # 2. Travamento e recolhimento automático dos Flaps em >= 26°
        self.flaps_locked = (self.wing_sweep_angle >= FLAP_LOCKOUT_SWEEP_DEG)
        if self.flaps_locked and self.flaps_down:
            self.flaps_down = False
            print(f"[Flaps] Recolhimento automático acionado (Asas >= {FLAP_LOCKOUT_SWEEP_DEG:.0f}°)!")

        target_flaps = 1.0 if (self.flaps_down and not self.flaps_locked) else 0.0
        target_airbrake = 1.0 if self.airbrake_deployed else 0.0

        # 3. Slats automáticos (CADC): abrem com flaps, baixa velocidade ou alto AoA; recolhem com enflecamento
        if self.wing_sweep_angle >= 50.0:
            target_slats = 0.0
        else:
            sweep_allow = float(np.clip((50.0 - self.wing_sweep_angle) / 15.0, 0.0, 1.0))
            if scene_mode == 3:
                # Na Cena 3, acompanha os flaps ou abre parcialmente com asas abertas para inspeção
                raw_slat = max(self.flaps_deploy, float(np.clip((35.0 - self.wing_sweep_angle) / 15.0, 0.0, 0.65)))
            else:
                speed_slat = float(np.clip((38.0 - self.speed) / 18.0, 0.0, 1.0))
                aoa_slat = float(np.clip((abs(self.aoa_deg) - 7.0) / 10.0, 0.0, 1.0))
                raw_slat = max(self.flaps_deploy, speed_slat, aoa_slat)
            target_slats = raw_slat * sweep_allow

        # 4. Alvos de Tailerons, Lemes e Wing Spoilers
        target_pitch = float(pitch_input) * 22.0
        target_roll = float(roll_input) * 15.0
        target_yaw = float(yaw_input) * 20.0

        if self.spoilers_locked:
            target_sp_left = 0.0
            target_sp_right = 0.0
        else:
            target_sp_left = max(0.0, -float(roll_input)) * SPOILER_MAX_DEFLECTION_DEG
            target_sp_right = max(0.0, float(roll_input)) * SPOILER_MAX_DEFLECTION_DEG

        if dt > 1e-6:
            # Atuação linear constante nos Flaps (sincronizada com o som FLAPS.wav)
            flap_delta = target_flaps - self.flaps_deploy
            max_flap_step = FLAP_ACTUATION_RATE * dt
            if abs(flap_delta) > 0.008:
                self.flaps_deploy += float(np.clip(flap_delta, -max_flap_step, max_flap_step))
                self.flaps_moving = True
            else:
                self.flaps_deploy = target_flaps
                self.flaps_moving = False

            # Atuação hidráulica dos Air Brakes e Slats
            self.airbrake_deploy += (target_airbrake - self.airbrake_deploy) * min(1.0, AIRBRAKE_ACTUATION_RATE * dt)
            if abs(self.airbrake_deploy - target_airbrake) < 0.005:
                self.airbrake_deploy = target_airbrake

            self.slat_deploy += (target_slats - self.slat_deploy) * min(1.0, SLAT_ACTUATION_RATE * dt)

            # Atuação das superfícies primárias
            surf_blend = min(1.0, 16.0 * dt)
            sp_blend = min(1.0, SPOILER_ACTUATION_RATE * dt)

            self.taileron_pitch += (target_pitch - self.taileron_pitch) * surf_blend
            self.taileron_roll += (target_roll - self.taileron_roll) * surf_blend
            self.rudder_yaw += (target_yaw - self.rudder_yaw) * surf_blend

            self.spoiler_left_deg += (target_sp_left - self.spoiler_left_deg) * sp_blend
            self.spoiler_right_deg += (target_sp_right - self.spoiler_right_deg) * sp_blend

            if self.spoiler_left_deg < 0.05 and target_sp_left == 0.0:
                self.spoiler_left_deg = 0.0
            if self.spoiler_right_deg < 0.05 and target_sp_right == 0.0:
                self.spoiler_right_deg = 0.0
        else:
            self.flaps_moving = False

        # Mantém aliases retrocompatíveis sincronizados
        self.elevator_pitch = self.taileron_pitch
        self.elevator_roll = self.taileron_roll
        self.min_flight_speed = self.get_effective_stall_speed()
        self.critical_aoa_deg = self.get_effective_critical_aoa()

    # ==========================================================================
    # ROTAÇÕES 6-DOF E DETECÇÃO DE COLISÕES
    # ==========================================================================

    def trigger_crash(self, reason, crash_type="solid"):
        """Ativa o estado de Game Over ('solid' ou 'water') e agenda o reset automático."""
        if not self.crashed:
            self.crashed = True
            self.crash_reason = reason
            self.crash_type = crash_type
            self.crash_timer = 2.0
            self.speed = 0.0
            self.velocity[:] = 0.0
            self.throttle = 0.0
            self.afterburner = False
            self.flaps_moving = False
            self.is_stalling = False
            self.g_load = 1.0
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
        Verifica todas as colisões físicas do caça com o Porta-Aviões (CVN-65),
        Ondas Físicas do Oceano, Rochas 3D e Paredes do Cânion.
        """
        if self.crashed:
            return

        if scene_mode == 1:
            hit_struct, reason = check_cvn65_extra_collisions(self.pos, self.right, self.forward)
            if hit_struct:
                self.trigger_crash(reason, crash_type="solid")
                return

            deck_contact_y = CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET
            if self.is_within_carrier_deck_xz():
                if not self.on_ground and self.pos[1] <= deck_contact_y and prev_pos[1] >= CARRIER_DECK_Y - 1.0:
                    descent_rate = -float(self.velocity[1])
                    if self.gear_deploy > 0.75 and self.forward[1] > -0.42 and self.up[1] > 0.72 and descent_rate < 16.0:
                        self.pos[1] = deck_contact_y
                        self.on_ground = True
                        self.afterburner = False
                        self.is_stalling = False
                        self.aoa_deg = 0.0
                        self.g_load = 1.0
                        self.forward[1] = 0.0
                        self.forward = normalize(self.forward)
                        self.up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
                        self.right = normalize(np.cross(self.forward, self.up))
                        self.velocity = self.forward * self.speed
                        print("[Pouso] Toque suave no convés! Pós-combustor desligado. Segure 'S' ou use [B] para frear.")
                    elif self.gear_deploy <= 0.75:
                        self.pos[1] = CARRIER_DECK_Y + 0.4
                        self.trigger_crash("IMPACTO NO CONVÉS SEM O TREM DE POUSO BAIXADO!", crash_type="solid")
                        return
                    else:
                        self.pos[1] = CARRIER_DECK_Y + 0.5
                        self.trigger_crash("POUSO MUITO VIOLENTO OU DESNIVELADO NO CONVÉS!", crash_type="solid")
                        return

                elif not self.on_ground and self.pos[1] < CARRIER_DECK_Y:
                    self.trigger_crash("COLISÃO COM O CASCO DO PORTA-AVIÕES!", crash_type="solid")
                    return

            wave_y = get_ocean_wave_height(float(self.pos[0]), float(self.pos[2]))
            if self.pos[1] <= wave_y + 1.25:
                self.pos[1] = wave_y + 0.65
                trigger_ocean_splash(float(self.pos[0]), float(self.pos[2]), intensity=2.4)
                self.trigger_crash("COLISÃO COM AS ONDAS DO OCEANO!", crash_type="water")
                return

        elif scene_mode == 2:
            target_z = CANYON_BUNKER_Z
            target_x = canyon_center_x(target_z)
            if (abs(self.pos[0] - target_x) <= 12.5) and (abs(self.pos[2] - target_z) <= 12.5) and (self.pos[1] <= 15.5):
                self.trigger_crash("IMPACTO DIRETO COM O BUNKER ALVO!", crash_type="solid")
                return

            hit_rock, rock_reason = check_canyon_rock_collisions(self.pos, self.right, self.forward)
            if hit_rock:
                self.trigger_crash(rock_reason, crash_type="solid")
                return

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
                    self.trigger_crash("COLISÃO COM AS PAREDES DO CÂNION!", crash_type="solid")
                    return

    # ==========================================================================
    # LOOP DE ATUALIZAÇÃO AERODINÂMICA E CINEMÁTICA (SOLO, INSPEÇÃO E VOO 6-DOF)
    # ==========================================================================

    def update(self, dt, pitch_input, roll_input, yaw_input, throttle_input, brake_active, scene_mode):
        """Atualiza a cinemática, aerodinâmica de sustentação/estol, G-load, superfícies móveis e colisões."""
        self.last_wrap_delta = np.zeros(3, dtype=np.float32)

        if self.crashed:
            self.crash_timer -= dt
            if self.crash_timer <= 0.0:
                self.reset(scene_mode)
            return

        if dt <= 1e-6:
            self.flaps_moving = False
            return

        prev_pos = self.pos.copy()

        # 1. Atualiza animação do trem de pouso e potência (throttle)
        target_gear = 1.0 if self.gear_down else 0.0
        self.gear_deploy += (target_gear - self.gear_deploy) * min(1.0, 4.5 * dt)
        self.throttle = float(np.clip(self.throttle + throttle_input * 0.50 * dt, 0.0, 1.0))

        if self.throttle < 1e-3 and self.afterburner:
            self.afterburner = False
            print("[Afterburner] Pós-combustor desarmado automaticamente (Throttle = 0%).")

        # 2. Enflecamento automático das asas (20° -> 68° calibrado para 1342 kt; respeita flaps em baixa vel.)
        if self.auto_wing_sweep:
            if self.flaps_down and self.speed <= FLAP_MAX_AUTO_SPEED:
                target_sweep = 20.0
            else:
                speed_ratio = np.clip((self.speed - 28.0) / (MAX_SPEED_AB - 28.0), 0.0, 1.0)
                target_sweep = 20.0 + 48.0 * speed_ratio
            self.wing_sweep_angle += (target_sweep - self.wing_sweep_angle) * min(1.0, 5.0 * dt)

        # 3. Atualiza superfícies móveis (spoilers, flaps, slats, air brakes, tailerons, lemes)
        self._update_control_surfaces(dt, pitch_input, roll_input, yaw_input, scene_mode)

        # 4. Calcula envelopes efetivos de desempenho
        self.max_speed = self.get_effective_max_speed()
        accel_rate = self.get_effective_accel_rate()
        effective_roll_rate = self.get_effective_roll_rate()
        stall_speed = self.min_flight_speed
        crit_aoa = self.critical_aoa_deg

        # ======================================================================
        # MODO SOLO / PISTA DO PORTA-AVIÕES
        # ======================================================================
        if self.on_ground:
            self.gear_down = True
            self.gear_deploy = 1.0
            self.is_stalling = False
            self.aoa_deg = 0.0
            self.lift_efficiency = 1.0
            self.g_load += (1.0 - self.g_load) * min(1.0, 10.0 * dt)

            self.max_speed = self.get_effective_max_speed()
            deck_accel = self.get_effective_accel_rate() * DECK_CATAPULT_ACCEL_BOOST
            target_speed = self.throttle * self.max_speed

            extra_brake = AIRBRAKE_DRAG_DECEL * 4.5 * self.airbrake_deploy
            if self.throttle < 1e-3:
                decel_rate = (34.0 if brake_active else 12.0) + extra_brake
                self.speed = max(0.0, self.speed - decel_rate * dt)
            else:
                if self.speed > target_speed:
                    self.speed += (target_speed - self.speed) * min(1.0, (2.2 + self.airbrake_deploy * 3.0) * dt)
                else:
                    self.speed += (target_speed - self.speed) * min(1.0, deck_accel * dt)

            if self.speed > 0.5 and abs(yaw_input) > 1e-4:
                steer_rate = 0.75 * min(1.0, self.speed / 20.0)
                self.yaw(yaw_input * steer_rate * dt)

            self.velocity = self.forward * self.speed
            self.pos += self.velocity * dt
            self.pos[1] = CARRIER_DECK_Y + GEAR_HEIGHT_OFFSET

            # Decolagem: com flaps estendidos decola muito mais cedo (~135 kt vs ~195 kt limpo!)
            takeoff_speed = stall_speed * 0.96
            if self.speed >= takeoff_speed and pitch_input > 0.1:
                self.on_ground = False
                self.pitch(0.14)
                self.velocity = self.forward * self.speed
                self.pos[1] += 0.30
                print(
                    f"[Voo] Decolagem realizada a {self.speed * 10.0:.0f} kt! "
                    "Recolha trem [Q] e flaps [F] para reduzir o arrasto."
                )
            elif not self.is_within_carrier_deck_xz():
                self.on_ground = False
                self.velocity = self.forward * self.speed
                if self.speed < takeoff_speed:
                    print("[Alerta] Saiu do convés abaixo da velocidade de sustentação!")

        # ======================================================================
        # MODO INSPEÇÃO (CENA 3: Suspenso sem translação, sem estol e sem colisão)
        # ======================================================================
        elif scene_mode == 3:
            self.is_stalling = False
            self.aoa_deg = 0.0
            self.lift_efficiency = 1.0
            self.g_load = 1.0

            target_speed = self.throttle * self.max_speed
            self.speed += (target_speed - self.speed) * min(1.0, accel_rate * dt)

            pitch_rate = 1.45
            yaw_rate = 1.10

            if abs(pitch_input) > 1e-4:
                self.pitch(pitch_input * pitch_rate * dt)
            if abs(roll_input) > 1e-4:
                self.roll(roll_input * effective_roll_rate * dt)
            if abs(yaw_input) > 1e-4:
                self.yaw(yaw_input * yaw_rate * dt)

            self.velocity = self.forward * self.speed
            self.pos[:] = [0.0, 15.0, 0.0]

        # ======================================================================
        # MODO EM VOO (AERODINÂMICA 6-DOF COM SUSTENTAÇÃO, AOA, ESTOL E FORÇA G)
        # ======================================================================
        else:
            # Garante inicialização coerente de self.velocity
            vel_mag = float(np.linalg.norm(self.velocity))
            if vel_mag < 1e-3 and self.speed > 1e-2:
                self.velocity = self.forward * self.speed
                vel_mag = float(self.speed)

            # 1. Calcula Ângulo de Ataque (AoA) entre o nariz (forward) e o fluxo de ar (velocity)
            if vel_mag > 2.5:
                v_fwd = float(np.dot(self.velocity, self.forward))
                v_up = float(np.dot(self.velocity, self.up))
                aoa_rad = math.atan2(-v_up, max(0.5, v_fwd))
                raw_aoa_deg = math.degrees(aoa_rad)
            else:
                v_fwd = vel_mag
                raw_aoa_deg = 0.0

            self.aoa_deg = float(np.clip(raw_aoa_deg, -45.0, 60.0))

            # 2. Eficiência de Sustentação (Speed Factor x AoA Stall Curve)
            # Velocidade ao longo do eixo das asas (v_fwd) gera sustentação
            eff_airspeed = max(0.0, v_fwd)
            speed_lift = float(np.clip(
                (eff_airspeed - 0.58 * stall_speed) / max(1.0, 0.52 * stall_speed),
                0.0, 1.0
            ))

            abs_aoa = abs(self.aoa_deg)
            if abs_aoa <= crit_aoa:
                aoa_lift = 1.0
            else:
                # Queda acentuada de sustentação acima do ângulo de ataque crítico (descolamento da camada limite)
                aoa_excess = abs_aoa - crit_aoa
                aoa_lift = float(max(0.10, math.exp(-((aoa_excess / 7.5) ** 1.6))))

            self.lift_efficiency = float(np.clip(speed_lift * aoa_lift, 0.0, 1.0))
            stall_severity = 1.0 - self.lift_efficiency
            self.is_stalling = (eff_airspeed < stall_speed * 0.98) or (abs_aoa > crit_aoa + 1.5)

            # 3. Autoridade de controle (cai no estol profundo para impedir "subir parado")
            pitch_authority = 0.22 + 0.78 * self.lift_efficiency
            roll_authority = 0.30 + 0.70 * self.lift_efficiency

            # Em alta velocidade supersônica, suaviza levemente a taxa de pitch para curvas realistas (~7.5-9 G)
            high_spd_pitch_damp = 1.0 / (1.0 + max(0.0, (vel_mag - 55.0) / 85.0))
            pitch_rate = 1.48 * pitch_authority * high_spd_pitch_damp
            yaw_rate = 0.85 * (0.35 + 0.65 * self.lift_efficiency)

            actual_pitch_omega = 0.0
            if abs(pitch_input) > 1e-4:
                # No estol com nariz muito alto, bloqueia puxar ainda mais para cima
                if self.is_stalling and pitch_input > 0.0 and (self.forward[1] > 0.35 or self.aoa_deg > crit_aoa):
                    effective_p_in = pitch_input * 0.12
                else:
                    effective_p_in = pitch_input
                actual_pitch_omega = effective_p_in * pitch_rate
                self.pitch(actual_pitch_omega * dt)

            if abs(roll_input) > 1e-4:
                self.roll(roll_input * effective_roll_rate * roll_authority * dt)
                # Coordenação de guinada pelos wing spoilers ativos (< 57°)
                if not self.spoilers_locked and abs(yaw_input) < 1e-4:
                    active_sp_frac = max(self.spoiler_left_deg, self.spoiler_right_deg) / SPOILER_MAX_DEFLECTION_DEG
                    self.yaw(-roll_input * SPOILER_PROVERSE_YAW * self.spoiler_authority * active_sp_frac * dt)

            if abs(yaw_input) > 1e-4:
                self.yaw(yaw_input * yaw_rate * dt)

            # 4. Dinâmica física de Estol (Nose-Drop + Queda de Asa / Wing Drop)
            if stall_severity > 0.20:
                # Escolhe direção consistente da queda de asa conforme inclinação atual
                if abs(self.right[1]) > 0.06:
                    self._stall_roll_sign = -1.0 if self.right[1] > 0.0 else 1.0

                # Torque de queda de nariz (Nose-Drop): faz o nariz cair em direção ao chão/horizonte
                # em vez de ficar suspenso apontando para cima!
                nose_high_factor = max(0.0, float(self.forward[1]) + 0.35)
                upright_sign = 1.0 if self.up[1] >= 0.0 else -1.0
                nose_drop_rate = (0.55 + 1.35 * nose_high_factor) * (stall_severity ** 1.25)
                self.pitch(-upright_sign * nose_drop_rate * dt)
                actual_pitch_omega -= upright_sign * nose_drop_rate

                # Queda de asa (Wing Drop / Incipient Spin) em estol acentuado com nariz alto
                if stall_severity > 0.42 and self.forward[1] > 0.15:
                    wing_drop_roll = self._stall_roll_sign * 0.85 * ((stall_severity - 0.42) / 0.58)
                    self.roll(wing_drop_roll * dt)
                    self.yaw(-self._stall_roll_sign * 0.28 * ((stall_severity - 0.42) / 0.58) * dt)

            # 5. Forças longitudinais: Empuxo vs Arrasto + Componente da Gravidade na Subida/Mergulho
            spoiler_total_frac = (self.spoiler_left_deg + self.spoiler_right_deg) / SPOILER_MAX_DEFLECTION_DEG
            aoa_induced_drag = 0.095 * (min(abs_aoa, 35.0) ** 1.60) + 1.25 * max(0.0, abs(self.g_load) - 2.0)
            extra_drag = (
                GEAR_AIRBRAKE_DECEL * self.gear_deploy
                + FLAP_DRAG_DECEL * self.flaps_deploy
                + AIRBRAKE_DRAG_DECEL * self.airbrake_deploy
                + SPOILER_ROLL_DRAG_DECEL * spoiler_total_frac
                + aoa_induced_drag
            )

            # Aceleração propulsiva (empuxo ao longo do eixo longitudinal da turbina)
            # No F-14D com AB ligado, T/W > 1.0 permite manter subida íngreme; em Dry thrust a gravidade vence!
            base_thrust_accel = accel_rate * self.max_speed * (0.04 + 0.96 * self.throttle) * 0.34
            # Limite assintótico de velocidade máxima pela resistência aerodinâmica quadrática
            speed_ratio_max = vel_mag / max(1.0, self.max_speed)
            drag_decel_total = (0.34 * accel_rate * self.max_speed * (speed_ratio_max ** 1.65)) + extra_drag * (0.25 + 0.75 * speed_ratio_max)

            # Empuxo + Arrasto atuando no vetor velocidade
            thrust_vec = self.forward * base_thrust_accel
            drag_vec = (-normalize(self.velocity) * drag_decel_total) if vel_mag > 0.5 else np.zeros(3, dtype=np.float32)

            # Gravidade real (-Y) e Sustentação Aerodinâmica (que anula a gravidade quando lift_efficiency ~ 1)
            gravity_vec = np.array([0.0, -GRAVITY_WORLD, 0.0], dtype=np.float32)

            # A componente da gravidade perpendicular ao eixo forward é compensada pela sustentação das asas
            # (proporcional a lift_efficiency e ao cosseno do ângulo de inclinação/subida).
            # A componente paralela ao eixo forward (-g * forward[1]) SEMPRE drena velocidade na subida e ganha no mergulho!
            grav_parallel = self.forward * float(np.dot(gravity_vec, self.forward))
            grav_perp = gravity_vec - grav_parallel

            # Quando lift_efficiency = 1.0, a asa compensa 100% da gravidade perpendicular (voo sustentado).
            # Quando em estol (lift_efficiency -> 0.0), a asa perde sustentação e a aeronave cai livremente!
            uncompensated_grav = grav_parallel * 0.72 + grav_perp * (1.0 - self.lift_efficiency)

            # Integra aceleração na velocidade 3D
            self.velocity = self.velocity + (thrust_vec + drag_vec + uncompensated_grav) * dt

            # Alinhamento aerodinâmico do fluxo (weathercock / curva do vetor velocidade em direção ao nariz)
            # Forte em voo normal (baixo AoA), muito fraco durante o estol (o avião continua caindo com AoA alto!)
            vel_mag = float(np.linalg.norm(self.velocity))
            if vel_mag > 0.5:
                vel_dir = self.velocity / vel_mag
                # Taxa de alinhamento do vetor velocidade com forward (cria AoA transitório realista nas curvas!)
                align_rate = 0.45 + 3.8 * (self.lift_efficiency ** 1.4)
                # Em estol severo, não puxa a velocidade para cima se o nariz apontar para o céu!
                if self.is_stalling and self.forward[1] > 0.15:
                    align_rate *= 0.18
                blended_dir = normalize(vel_dir + (self.forward - vel_dir) * min(1.0, align_rate * dt))
                self.velocity = blended_dir * vel_mag

            # Limita velocidade máxima física (permite pequeno ganho em mergulho com AB)
            max_dive_cap = MAX_SPEED_AB * 1.03
            vel_mag = float(np.linalg.norm(self.velocity))
            if vel_mag > max_dive_cap:
                self.velocity *= (max_dive_cap / vel_mag)
                vel_mag = max_dive_cap

            self.speed = vel_mag

            # 6. Cálculo da Força G (G-Load) sentida pelo piloto no eixo 'up'
            # Converte speed para m/s reais (1 unidade = 10 kt = 5.1444 m/s) para cálculo físico exato de v*omega/g
            speed_ms = self.speed * 5.1444
            # Gravidade projetada no eixo up da aeronave (+1G nivelado, -1G invertido)
            g_static = float(self.up[1]) * self.lift_efficiency
            # Aceleração centrípeta na manobra de arfagem / curva fechada
            # (escalada pela resposta real do vetor velocidade para não dar picos irreais em estol)
            g_maneuver = (speed_ms * actual_pitch_omega / 9.81) * 0.16 * self.lift_efficiency
            # Adicional de curva inclinada coordenada (1 / cos(bank) quando sustentando altitude)
            raw_g = float(np.clip(g_static + g_maneuver, -3.5, 9.5))
            self.g_load += (raw_g - self.g_load) * min(1.0, 9.0 * dt)

            # 7. Integra posição 3D com a velocidade real (cai de fato em estol!)
            self.pos += self.velocity * dt

            # 8. Teleporte Toroidal ("Roundabout") ao cruzar os limites do mapa
            self.last_wrap_delta = wrap_position_roundabout(self.pos, scene_mode)
            if abs(self.last_wrap_delta[0]) > 1e-3 or abs(self.last_wrap_delta[2]) > 1e-3:
                prev_pos += self.last_wrap_delta

        # Checa colisões com o porta-aviões, ondas físicas do oceano ou rochas do cânion
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
