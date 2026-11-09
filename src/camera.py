"""
================================================================================
TopGraphics | camera.py
Sistema de câmeras virtuais: 1) Chase Cam, 2) Cockpit Cam, 3) Orbital Livre (mouse).
Independente de GLFW: o main.py repassa os eventos de mouse para os métodos on_*.
================================================================================
"""

import math

import numpy as np
from OpenGL.GLU import gluLookAt

from math_utils import normalize

CHASE_BACK_DIST = 17.5   # Distância da Chase Cam atrás da aeronave
CHASE_UP_DIST = 4.6      # Altura da Chase Cam acima da aeronave


class CameraController:
    """Mantém o estado das 3 câmeras e aplica gluLookAt conforme o modo ativo."""

    MODE_MESSAGES = {
        1: "[Câmera] Modo 1: Chase Cam (Perseguição Dinâmica)",
        2: "[Câmera] Modo 2: Cockpit / HUD Tático (Primeira Pessoa)",
        3: "[Câmera] Modo 3: Orbital Livre 360° (Arraste o mouse / Scroll para zoom)",
    }

    def __init__(self, aircraft):
        self.mode = 1  # 1 = Chase Cam, 2 = Cockpit/HUD, 3 = Orbital Mouse

        # Parâmetros da Câmera 3 (Orbital Livre controlada por Mouse)
        self.orbit_yaw = 35.0
        self.orbit_pitch = 20.0
        self.orbit_distance = 20.0
        self.mouse_dragging = False
        self.last_mouse_x = 0.0
        self.last_mouse_y = 0.0

        # Estado suavizado da Chase Cam
        self.chase_cam_pos = np.zeros(3, dtype=np.float32)
        self.chase_cam_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        self.snap_chase_to(aircraft)

    def set_mode(self, mode):
        """Troca o modo de câmera (1, 2 ou 3) e informa no terminal."""
        self.mode = mode
        print(self.MODE_MESSAGES[mode])

    def snap_chase_to(self, aircraft):
        """Posiciona a Chase Cam instantaneamente atrás da aeronave (usado em reset/troca de cena)."""
        self.chase_cam_pos = (
            aircraft.pos - aircraft.forward * CHASE_BACK_DIST + aircraft.up * CHASE_UP_DIST
        )

    def on_mouse_button(self, pressed, x, y):
        """Botão esquerdo do mouse: inicia/encerra o arraste da câmera orbital."""
        self.mouse_dragging = pressed
        self.last_mouse_x, self.last_mouse_y = x, y

    def on_cursor_pos(self, xpos, ypos):
        """Movimento do cursor: gira a câmera orbital enquanto o botão está pressionado."""
        if self.mouse_dragging and self.mode == 3:
            dx = xpos - self.last_mouse_x
            dy = ypos - self.last_mouse_y
            self.orbit_yaw += dx * 0.45
            self.orbit_pitch = np.clip(self.orbit_pitch + dy * 0.45, -80.0, 85.0)
        self.last_mouse_x, self.last_mouse_y = xpos, ypos

    def on_scroll(self, yoffset):
        """Scroll do mouse: zoom da câmera orbital."""
        if self.mode == 3:
            self.orbit_distance = np.clip(self.orbit_distance - yoffset * 2.0, 8.0, 80.0)

    def apply(self, aircraft, dt):
        """Aplica gluLookAt conforme o modo de câmera ativo."""
        p = aircraft.pos
        f = aircraft.forward
        u = aircraft.up

        if self.mode == 1:
            desired_pos = p - f * CHASE_BACK_DIST + u * CHASE_UP_DIST
            lerp_factor = min(1.0, 8.5 * dt)
            self.chase_cam_pos += (desired_pos - self.chase_cam_pos) * lerp_factor
            self.chase_cam_up = normalize(self.chase_cam_up + (u - self.chase_cam_up) * lerp_factor)
            target = p + f * 12.0
            gluLookAt(
                self.chase_cam_pos[0], self.chase_cam_pos[1], self.chase_cam_pos[2],
                target[0], target[1], target[2],
                self.chase_cam_up[0], self.chase_cam_up[1], self.chase_cam_up[2]
            )

        elif self.mode == 2:
            eye = p + f * 2.4 + u * 0.82
            target = eye + f * 50.0
            gluLookAt(
                eye[0], eye[1], eye[2],
                target[0], target[1], target[2],
                u[0], u[1], u[2]
            )

        elif self.mode == 3:
            yaw_rad = math.radians(self.orbit_yaw)
            pitch_rad = math.radians(self.orbit_pitch)
            cx = p[0] + self.orbit_distance * math.cos(pitch_rad) * math.sin(yaw_rad)
            cy = p[1] + self.orbit_distance * math.sin(pitch_rad)
            cz = p[2] + self.orbit_distance * math.cos(pitch_rad) * math.cos(yaw_rad)
            gluLookAt(cx, cy, cz, p[0], p[1], p[2], 0.0, 1.0, 0.0)
