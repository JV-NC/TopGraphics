"""
================================================================================
TopGraphics | f14_model.py
Modelo low-poly hierárquico do F-14 Tomcat: fuselagem por seções transversais, canopy,
naceles, asas de geometria variável, trem de pouso retrátil, profundores e pós-combustores.
================================================================================
"""

# TODO: model the F14-TC based on its technical specifications
# TODO: model taileron and wing spoiler movement during roll, elevators during pitch, and the rudders during yaw (partially implemented)
# TODO: implement F-14 skins for customization

import math

import numpy as np
from OpenGL.GL import *

from renderer_utils import (
    draw_box, draw_quad_with_normal, draw_tri_with_normal, upload_texture_rgb
)


# ==============================================================================
# TEXTURA PROCEDURAL DA AERONAVE
# ==============================================================================

def create_wing_insignia_texture():
    """Gera textura metálica para fuselagem/asas com faixas navais."""
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

    return upload_texture_rgb(img)


# ==============================================================================
# TREM DE POUSO RETRÁTIL
# ==============================================================================

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
    Renderiza o Trem de Pouso Retrátil do F-14 Tomcat usando hierarquia de matrizes.
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


# ==============================================================================
# FUSELAGEM, ASAS E AERONAVE COMPLETA
# ==============================================================================

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

    # 4. LUVAS DAS ASAS (WING GLOVES FIXAS COM TEXTURA UV)
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
    Renderiza o F-14 Tomcat completo aplicando transformações hierárquicas:
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

    # 2. Trem de Pouso Retrátil
    draw_retractable_landing_gear(aircraft.gear_deploy, aircraft.rudder_yaw)

    # 3. Asas de Geometria Variável
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

    # 4. Profundores Horizontais Móveis (Tailerons)
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

    # 5. Bocais das Turbinas e Pós-Combustão (Afterburners com glScalef)
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
