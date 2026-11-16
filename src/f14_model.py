"""
================================================================================
TopGraphics | f14_model.py
Modelo low-poly de alta fidelidade do F-14 Tomcat: fuselagem por seções transversais, canopy,
naceles, asas de geometria variável, trem de pouso retrátil, profundores, pós-combustores
e suporte completo ao Sistema de Customização de Skins (Padrão, Metálicas e Camuflagens)
com Mapeamento UV Triplanar Métrico (livre de distorções de aspecto ou cisalhamento).
================================================================================
"""

# TODO: refactor movable parts of the aircraft (spoiler wings, flaps, tailerons, rudders, elevators)

import math
import numpy as np
from OpenGL.GL import *

from math_utils import compute_normal
from renderer_utils import (
    draw_box, draw_quad_with_normal, draw_tri_with_normal, upload_texture_rgb
)

# Escala métrica uniforme para mapeamento UV triplanar das skins (unidades de textura por metro)
# Garante texels 100% quadrados e contínuos em todas as chapas da aeronave, sem esticar!
SKIN_UV_SCALE = 0.42
SKIN_UV_OFFSET = 0.37


# ==============================================================================
# MAPEAMENTO UV TRIPLANAR MÉTRICO
# ==============================================================================

def _project_planar_uv(vertex, normal, scale=SKIN_UV_SCALE):
    """
    Calcula coordenadas (u, v) diretamente a partir da posição métrica 3D (x, y, z)
    do vértice projetada no plano dominante da normal da superfície (Box/Triplanar Mapping).
    Elimina completamente o estiramento em caixas longas (espinha dorsal, asas)
    e o cisalhamento diagonal em trapézios (seções da fuselagem, luvas e tailerons).
    """
    vx, vy, vz = float(vertex[0]), float(vertex[1]), float(vertex[2])
    nx, ny, nz = abs(float(normal[0])), abs(float(normal[1])), abs(float(normal[2]))

    if ny >= nx and ny >= nz:
        # Superfícies predominantemente horizontais (dorso, ventre, asas, tailerons, luvas)
        u = vx * scale + SKIN_UV_OFFSET
        v = vz * scale + SKIN_UV_OFFSET
    elif nx >= ny and nx >= nz:
        # Superfícies predominantemente laterais (laterais das naceles, derivas, lemes, fuselagem)
        u = vz * scale + SKIN_UV_OFFSET
        v = vy * scale + SKIN_UV_OFFSET
    else:
        # Superfícies frontais/traseiras
        u = vx * scale + SKIN_UV_OFFSET
        v = vy * scale + SKIN_UV_OFFSET

    return u, v


def draw_quad_planar_uv(p1, p2, p3, p4, scale=SKIN_UV_SCALE):
    """Desenha um quadrilátero com normal automática e projeção UV métrica sem distorção."""
    n = compute_normal(p1, p2, p3)
    glNormal3fv(n)
    for pt in (p1, p2, p3, p4):
        u, v = _project_planar_uv(pt, n, scale)
        glTexCoord2f(u, v)
        glVertex3fv(pt)


def draw_tri_planar_uv(p1, p2, p3, scale=SKIN_UV_SCALE):
    """Desenha um triângulo com normal automática e projeção UV métrica sem distorção."""
    n = compute_normal(p1, p2, p3)
    glNormal3fv(n)
    for pt in (p1, p2, p3):
        u, v = _project_planar_uv(pt, n, scale)
        glTexCoord2f(u, v)
        glVertex3fv(pt)


def draw_box_planar_uv(dx, dy, dz, scale=SKIN_UV_SCALE):
    """
    Desenha um paralelepípedo centrado na origem onde cada face recebe coordenadas UV
    proporcionais às suas dimensões reais em metros (dx, dy, dz), evitando estiramento.
    """
    hx, hy, hz = dx * 0.5, dy * 0.5, dz * 0.5
    glBegin(GL_QUADS)
    draw_quad_planar_uv([-hx,  hy, -hz], [-hx,  hy,  hz], [ hx,  hy,  hz], [ hx,  hy, -hz], scale)
    draw_quad_planar_uv([-hx, -hy,  hz], [-hx, -hy, -hz], [ hx, -hy, -hz], [ hx, -hy,  hz], scale)
    draw_quad_planar_uv([ hx, -hy, -hz], [-hx, -hy, -hz], [-hx,  hy, -hz], [ hx,  hy, -hz], scale)
    draw_quad_planar_uv([-hx, -hy,  hz], [ hx, -hy,  hz], [ hx,  hy,  hz], [-hx,  hy,  hz], scale)
    draw_quad_planar_uv([ hx, -hy,  hz], [ hx, -hy, -hz], [ hx,  hy, -hz], [ hx,  hy,  hz], scale)
    draw_quad_planar_uv([-hx, -hy, -hz], [-hx, -hy,  hz], [-hx,  hy,  hz], [-hx,  hy, -hz], scale)
    glEnd()


def draw_surface_quad(p1, p2, p3, p4, uv_scale=1.0, planar_uv=False):
    """Seleciona entre UV métrico triplanar (para skins customizadas) ou UV local padrão."""
    if planar_uv:
        draw_quad_planar_uv(p1, p2, p3, p4, SKIN_UV_SCALE)
    else:
        draw_quad_with_normal(p1, p2, p3, p4, uv_scale)


def draw_surface_tri(p1, p2, p3, planar_uv=False):
    """Seleciona entre UV métrico triplanar (para skins customizadas) ou UV local padrão."""
    if planar_uv:
        draw_tri_planar_uv(p1, p2, p3, SKIN_UV_SCALE)
    else:
        draw_tri_with_normal(p1, p2, p3)


def draw_surface_box(dx, dy, dz, uv_scale=1.0, planar_uv=False):
    """Seleciona entre caixa com UV métrico proporcional ou caixa padrão."""
    if planar_uv:
        draw_box_planar_uv(dx, dy, dz, SKIN_UV_SCALE)
    else:
        draw_box(dx, dy, dz, uv_scale)


# ==============================================================================
# UTILITÁRIOS GEOMÉTRICOS DO MODELO
# ==============================================================================

def draw_cylinder_z(
    r1, r2, z1, z2, segments=12, y_scale=1.0, x_scale=1.0,
    cap_start=False, cap_end=False, planar_uv=False
):
    """Desenha um cilindro/tronco de cone ao longo do eixo Z com suporte a UV métrico."""
    dz = z2 - z1
    dr = r2 - r1
    length = math.hypot(dz, dr)
    nz_slope = -dr / length if length > 1e-6 else 0.0
    nr_slope = dz / length if length > 1e-6 else 1.0
    r_avg = max(0.15, 0.5 * (r1 + r2))
    circumference = 2.0 * math.pi * r_avg

    glBegin(GL_QUAD_STRIP)
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        ca = math.cos(ang)
        sa = math.sin(ang)
        nx = ca * nr_slope / max(0.1, x_scale)
        ny = sa * nr_slope / max(0.1, y_scale)
        nz = nz_slope
        n_len = math.sqrt(nx * nx + ny * ny + nz * nz)
        if n_len > 1e-6:
            glNormal3f(nx / n_len, ny / n_len, nz / n_len)

        x1 = r1 * ca * x_scale
        y1 = r1 * sa * y_scale
        x2 = r2 * ca * x_scale
        y2 = r2 * sa * y_scale

        if planar_uv:
            u_arc = (i / float(segments)) * circumference * SKIN_UV_SCALE + SKIN_UV_OFFSET
            v1 = z1 * SKIN_UV_SCALE + SKIN_UV_OFFSET
            v2 = z2 * SKIN_UV_SCALE + SKIN_UV_OFFSET
            glTexCoord2f(u_arc, v1)
            glVertex3f(x1, y1, z1)
            glTexCoord2f(u_arc, v2)
            glVertex3f(x2, y2, z2)
        else:
            glTexCoord2f(i / float(segments), 0.0)
            glVertex3f(x1, y1, z1)
            glTexCoord2f(i / float(segments), 1.0)
            glVertex3f(x2, y2, z2)
    glEnd()

    if cap_start and r1 > 1e-4:
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0.0, 0.0, -1.0)
        glVertex3f(0.0, 0.0, z1)
        for i in range(segments, -1, -1):
            ang = (2.0 * math.pi * i) / segments
            glVertex3f(r1 * math.cos(ang) * x_scale, r1 * math.sin(ang) * y_scale, z1)
        glEnd()

    if cap_end and r2 > 1e-4:
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0.0, 0.0, 1.0)
        glVertex3f(0.0, 0.0, z2)
        for i in range(segments + 1):
            ang = (2.0 * math.pi * i) / segments
            glVertex3f(r2 * math.cos(ang) * x_scale, r2 * math.sin(ang) * y_scale, z2)
        glEnd()


def draw_prism_section(sec1, sec2, tex_scale=0.0, planar_uv=False):
    """
    Conecta duas seções transversais octogonais/trapezoidais ao longo de Z.
    Cada seção: (z, w_bot, w_mid, w_top, y_bot, y_mid, y_top)
    """
    z1, wb1, wm1, wt1, yb1, ym1, yt1 = sec1
    z2, wb2, wm2, wt2, yb2, ym2, yt2 = sec2

    pts1 = [
        [-wt1, yt1, z1], [wt1, yt1, z1],
        [wm1, ym1, z1],  [wb1, yb1, z1],
        [-wb1, yb1, z1], [-wm1, ym1, z1]
    ]
    pts2 = [
        [-wt2, yt2, z2], [wt2, yt2, z2],
        [wm2, ym2, z2],  [wb2, yb2, z2],
        [-wb2, yb2, z2], [-wm2, ym2, z2]
    ]

    glBegin(GL_QUADS)
    for k in range(6):
        kn = (k + 1) % 6
        draw_surface_quad(pts1[k], pts2[k], pts2[kn], pts1[kn], tex_scale, planar_uv=planar_uv)
    glEnd()


# ==============================================================================
# TEXTURA PROCEDURAL PADRÃO DA AERONAVE (ESQUADRÃO NAVAL VF-84 / TOP GUN)
# ==============================================================================

def create_wing_insignia_texture():
    """Gera textura metálica naval com linhas de painéis, rebites e faixas de esquadrão."""
    size = 128
    img = np.full((size, size, 3), 182, dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            noise = ((x * 17 + y * 31) % 9) - 4
            base = np.clip(182 + noise, 165, 195)
            img[y, x] = [base - 3, base, base + 5]

            if x % 32 == 0 or y % 32 == 0:
                img[y, x] = [125, 130, 138]
            elif x % 16 == 0 and y % 4 == 0:
                img[y, x] = [148, 152, 158]

            if 86 < x < 108:
                img[y, x] = [34, 42, 64]
            elif 108 <= x < 115:
                img[y, x] = [230, 190, 45]

    return upload_texture_rgb(img)


# ==============================================================================
# TREM DE POUSO RETRÁTIL
# ==============================================================================

def draw_wheel(radius=0.26, width=0.14, segments=14):
    """Desenha uma roda cilíndrica ao longo do eixo X (pneu de borracha + aro naval branco)."""
    half_w = width * 0.5
    glColor3f(0.11, 0.11, 0.13)
    glBegin(GL_QUAD_STRIP)
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        ny = math.cos(ang)
        nz = math.sin(ang)
        glNormal3f(0.0, ny, nz)
        glVertex3f(-half_w, radius * ny, radius * nz)
        glVertex3f( half_w, radius * ny, radius * nz)
    glEnd()

    for side in (-1.0, 1.0):
        glColor3f(0.14, 0.14, 0.16)
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(side, 0.0, 0.0)
        glVertex3f(side * half_w, 0.0, 0.0)
        for i in range(segments + 1):
            ang = (2.0 * math.pi * i) / segments
            glVertex3f(side * half_w, radius * math.cos(ang), radius * math.sin(ang))
        glEnd()

        glColor3f(0.90, 0.92, 0.95)
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(side, 0.0, 0.0)
        glVertex3f(side * (half_w + 0.006), 0.0, 0.0)
        for i in range(segments + 1):
            ang = (2.0 * math.pi * i) / segments
            glVertex3f(
                side * (half_w + 0.006),
                radius * 0.56 * math.cos(ang),
                radius * 0.56 * math.sin(ang)
            )
        glEnd()


def draw_retractable_landing_gear(gear_deploy, rudder_yaw):
    """Renderiza o Trem de Pouso Retrátil mantendo contato exato em Y = -1.45."""
    if gear_deploy < 0.02:
        return

    glPushAttrib(GL_TEXTURE_BIT | GL_ENABLE_BIT)
    glDisable(GL_TEXTURE_2D)

    retract_angle = (1.0 - gear_deploy) * 90.0

    # 1. Trem de pouso de nariz
    glPushMatrix()
    glTranslatef(0.0, -0.32, -4.10)
    glRotatef(retract_angle, 1.0, 0.0, 0.0)

    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 0.22, -0.22, 0.0)
        glColor3f(0.75, 0.78, 0.82)
        draw_box(0.03, 0.42, 0.72)
        glColor3f(0.78, 0.16, 0.16)
        glTranslatef(-side * 0.018, 0.0, 0.0)
        draw_box(0.01, 0.36, 0.66)
        glPopMatrix()

    glColor3f(0.90, 0.92, 0.95)
    glPushMatrix()
    glTranslatef(0.0, -0.45, 0.0)
    draw_box(0.09, 0.90, 0.09)
    glPopMatrix()

    glColor3f(0.82, 0.85, 0.88)
    glPushMatrix()
    glTranslatef(0.0, -0.32, 0.22)
    glRotatef(-32.5, 1.0, 0.0, 0.0)
    draw_box(0.06, 0.65, 0.06)
    glPopMatrix()

    glColor3f(0.88, 0.72, 0.18)
    glPushMatrix()
    glTranslatef(0.0, -0.62, -0.18)
    glRotatef(22.0, 1.0, 0.0, 0.0)
    draw_box(0.05, 0.48, 0.05)
    glPopMatrix()

    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    glColor3f(1.0, 0.98, 0.82)
    glPushMatrix()
    glTranslatef(0.0, -0.52, -0.07)
    draw_box(0.08, 0.08, 0.04)
    glPopMatrix()
    glPopAttrib()

    glPushMatrix()
    glTranslatef(0.0, -0.90, 0.0)
    glRotatef(rudder_yaw, 0.0, 1.0, 0.0)
    glColor3f(0.80, 0.82, 0.86)
    draw_box(0.28, 0.06, 0.06)
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 0.11, 0.0, 0.0)
        draw_wheel(radius=0.22, width=0.09)
        glPopMatrix()
    glPopMatrix()

    glPopMatrix()

    # 2. Trens de pouso principais
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 1.15, -0.35, 0.85)
        glRotatef(side * retract_angle, 0.0, 0.0, 1.0)

        glPushMatrix()
        glTranslatef(side * 0.18, -0.28, 0.0)
        glColor3f(0.68, 0.71, 0.75)
        draw_box(0.04, 0.54, 0.88)
        glColor3f(0.78, 0.16, 0.16)
        glTranslatef(-side * 0.022, 0.0, 0.0)
        draw_box(0.01, 0.48, 0.80)
        glPopMatrix()

        glColor3f(0.88, 0.90, 0.94)
        glPushMatrix()
        glTranslatef(0.0, -0.40, 0.0)
        draw_box(0.12, 0.80, 0.12)
        glPopMatrix()

        glColor3f(0.78, 0.80, 0.85)
        glPushMatrix()
        glTranslatef(-side * 0.24, -0.34, -0.14)
        glRotatef(side * 32.0, 0.0, 0.0, 1.0)
        glRotatef(-25.0, 1.0, 0.0, 0.0)
        draw_box(0.06, 0.66, 0.06)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(0.0, -0.80, 0.0)
        draw_wheel(radius=0.30, width=0.18)
        glPopMatrix()

        glPopMatrix()

    glPopAttrib()


# ==============================================================================
# MÍSSEIS E PILONES DE ARMAMENTO
# ==============================================================================

def draw_missile(length, radius, body_color, fin_span, nose_color=(0.18, 0.20, 0.22)):
    """Desenha um míssil ar-ar cilíndrico com ogiva cônica e aletas cruciformes a 45°."""
    z_nose = -length * 0.5
    z_cone_end = z_nose + length * 0.24
    z_tail = length * 0.5

    glColor3fv(nose_color)
    draw_cylinder_z(0.005, radius, z_nose, z_cone_end, segments=8)

    glColor3fv(body_color)
    draw_cylinder_z(radius, radius, z_cone_end, z_tail, segments=8, cap_end=True)

    glColor3f(0.28, 0.30, 0.34)
    for angle_deg in (45.0, 135.0):
        glPushMatrix()
        glRotatef(angle_deg, 0.0, 0.0, 1.0)
        glPushMatrix()
        glTranslatef(0.0, 0.0, -length * 0.04)
        draw_box(fin_span * 1.6, 0.018, length * 0.16)
        glPopMatrix()
        glPushMatrix()
        glTranslatef(0.0, 0.0, z_tail - length * 0.10)
        draw_box(fin_span * 2.0, 0.018, length * 0.16)
        glPopMatrix()
        glPopMatrix()


def draw_weapons_loadout():
    """Renderiza 4x AIM-54 Phoenix, 2x AIM-7 Sparrow e 2x AIM-9 Sidewinder."""
    glPushAttrib(GL_TEXTURE_BIT | GL_ENABLE_BIT)
    glDisable(GL_TEXTURE_2D)

    for z_station in (-0.35, 1.95):
        for side in (-1.0, 1.0):
            x_pos = side * 0.23
            glColor3f(0.60, 0.63, 0.68)
            glPushMatrix()
            glTranslatef(x_pos, -0.36, z_station)
            draw_box(0.14, 0.10, 1.45)
            glPopMatrix()

            glPushMatrix()
            glTranslatef(x_pos, -0.47, z_station)
            draw_missile(
                length=1.65, radius=0.075,
                body_color=(0.88, 0.90, 0.93), fin_span=0.14, nose_color=(0.22, 0.24, 0.27)
            )
            glPopMatrix()

    for side in (-1.0, 1.0):
        x_pylon = side * 1.48
        glColor3f(0.66, 0.69, 0.74)
        glPushMatrix()
        glTranslatef(x_pylon, -0.10, 0.35)
        draw_box(0.08, 0.24, 1.35)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(x_pylon, -0.28, 0.35)
        draw_missile(
            length=1.55, radius=0.055,
            body_color=(0.85, 0.87, 0.90), fin_span=0.12, nose_color=(0.30, 0.32, 0.35)
        )
        glPopMatrix()

        glColor3f(0.55, 0.58, 0.62)
        glPushMatrix()
        glTranslatef(x_pylon + side * 0.08, -0.08, 0.25)
        draw_box(0.06, 0.06, 1.10)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(x_pylon + side * 0.13, -0.08, 0.20)
        draw_missile(
            length=1.30, radius=0.040,
            body_color=(0.82, 0.84, 0.88), fin_span=0.09, nose_color=(0.15, 0.16, 0.18)
        )
        glPopMatrix()

    glPopAttrib()


# ==============================================================================
# COCKPIT BIPOSTO DETALHADO E CANOPY EM BOLHA
# ==============================================================================

def draw_cockpit_and_canopy():
    """Constrói o interior do cockpit, assentos Martin-Baker GRU-7A e canopy em bolha."""
    glPushAttrib(GL_TEXTURE_BIT | GL_ENABLE_BIT)
    glDisable(GL_TEXTURE_2D)

    glColor3f(0.18, 0.20, 0.23)
    glPushMatrix()
    glTranslatef(0.0, 0.26, -2.35)
    draw_box(0.62, 0.14, 3.10)
    glPopMatrix()

    glColor3f(0.12, 0.13, 0.15)
    glPushMatrix()
    glTranslatef(0.0, 0.42, -3.35)
    glRotatef(-18.0, 1.0, 0.0, 0.0)
    draw_box(0.46, 0.22, 0.38)
    glPopMatrix()

    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    glColor3f(0.15, 0.90, 0.45)
    glPushMatrix()
    glTranslatef(0.0, 0.56, -3.42)
    glRotatef(-25.0, 1.0, 0.0, 0.0)
    draw_box(0.18, 0.14, 0.02)
    glPopMatrix()
    glPopAttrib()

    glColor3f(0.14, 0.15, 0.18)
    glPushMatrix()
    glTranslatef(0.0, 0.44, -2.05)
    glRotatef(-12.0, 1.0, 0.0, 0.0)
    draw_box(0.50, 0.24, 0.35)
    glPopMatrix()

    for z_seat in (-2.75, -1.45):
        glPushMatrix()
        glTranslatef(0.0, 0.38, z_seat)
        glRotatef(14.0, 1.0, 0.0, 0.0)

        glColor3f(0.22, 0.24, 0.26)
        draw_box(0.34, 0.46, 0.12)

        glColor3f(0.28, 0.35, 0.24)
        glPushMatrix()
        glTranslatef(0.0, -0.14, -0.08)
        draw_box(0.32, 0.12, 0.26)
        glPopMatrix()

        glColor3f(0.32, 0.34, 0.28)
        glPushMatrix()
        glTranslatef(0.0, 0.26, 0.0)
        draw_box(0.22, 0.14, 0.12)
        glColor3f(0.95, 0.80, 0.10)
        glTranslatef(0.0, 0.10, -0.02)
        draw_box(0.12, 0.06, 0.04)
        glPopMatrix()

        glColor3f(0.92, 0.94, 0.96)
        glPushMatrix()
        glTranslatef(0.0, 0.24, -0.10)
        draw_box(0.18, 0.18, 0.18)
        glColor3f(0.10, 0.12, 0.16)
        glTranslatef(0.0, 0.01, -0.06)
        draw_box(0.16, 0.10, 0.08)
        glPopMatrix()

        glPopMatrix()

    canopy_sections = [
        (-4.35, 0.10, 0.04, 0.24, 0.26),
        (-3.65, 0.34, 0.20, 0.32, 0.62),
        (-2.85, 0.40, 0.24, 0.34, 0.78),
        (-1.85, 0.38, 0.23, 0.34, 0.75),
        (-0.95, 0.30, 0.16, 0.34, 0.56),
        (-0.15, 0.16, 0.08, 0.32, 0.36),
    ]

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glColor4f(0.22, 0.48, 0.72, 0.58)

    for i in range(len(canopy_sections) - 1):
        z1, wb1, wt1, yb1, yt1 = canopy_sections[i]
        z2, wb2, wt2, yb2, yt2 = canopy_sections[i + 1]
        ym1 = yb1 + (yt1 - yb1) * 0.68
        ym2 = yb2 + (yt2 - yb2) * 0.68
        wm1 = wb1 * 0.88
        wm2 = wb2 * 0.88

        glBegin(GL_QUADS)
        draw_quad_with_normal([-wt1, yt1, z1], [-wt2, yt2, z2], [wt2, yt2, z2], [wt1, yt1, z1])
        draw_quad_with_normal([wt1, yt1, z1], [wt2, yt2, z2], [wm2, ym2, z2], [wm1, ym1, z1])
        draw_quad_with_normal([-wm1, ym1, z1], [-wm2, ym2, z2], [-wt2, yt2, z2], [-wt1, yt1, z1])
        draw_quad_with_normal([wm1, ym1, z1], [wm2, ym2, z2], [wb2, yb2, z2], [wb1, yb1, z1])
        draw_quad_with_normal([-wb1, yb1, z1], [-wb2, yb2, z2], [-wm2, ym2, z2], [-wm1, ym1, z1])
        glEnd()

    glDisable(GL_BLEND)

    glColor3f(0.32, 0.35, 0.39)
    for z1, wb1, wt1, yb1, yt1 in canopy_sections[1:4]:
        ym1 = yb1 + (yt1 - yb1) * 0.68
        wm1 = wb1 * 0.88
        glPushMatrix()
        glTranslatef(0.0, yt1 + 0.008, z1)
        draw_box(wt1 * 2.02, 0.025, 0.05)
        glPopMatrix()
        for side in (-1.0, 1.0):
            glPushMatrix()
            glTranslatef(side * wm1, (yb1 + yt1) * 0.5, z1)
            glRotatef(-side * 22.0, 0.0, 0.0, 1.0)
            draw_box(0.025, yt1 - yb1, 0.05)
            glPopMatrix()

    glPopAttrib()


# ==============================================================================
# FUSELAGEM ESTÁTICA DO F-14 (MODO PADRÃO VF-84 E MODO COM SKIN CUSTOMIZÁVEL)
# ==============================================================================

def _compile_f14_fuselage_geometry(wing_tex_id=None, full_skin_uv=False):
    """
    Núcleo compartilhado de compilação da fuselagem do F-14:
      - Se full_skin_uv == False: mantém o visual original do VF-84 Jolly Rogers.
      - Se full_skin_uv == True: utiliza Mapeamento UV Triplanar Métrico (planar_uv=True)
        em todas as chapas da fuselagem, dorso, naceles, luvas e derivas, eliminando
        qualquer estiramento ou distorção diagonal nas skins metálicas e camuflagens.
    """
    # 1. Componentes funcionais da ponta do nariz (sempre sem textura de pintura)
    glPushAttrib(GL_TEXTURE_BIT | GL_ENABLE_BIT)
    glDisable(GL_TEXTURE_2D)

    # Tubo de Pitot
    glColor3f(0.85, 0.87, 0.90)
    draw_cylinder_z(0.008, 0.016, -7.25, -6.80, segments=8)

    # Ponta dielétrica escura do Radome
    glColor3f(0.16, 0.17, 0.20)
    draw_cylinder_z(0.016, 0.18, -6.80, -5.85, segments=14, y_scale=0.92)

    # Lente do sensor TCS e canos do canhão Vulcan M61A1
    glColor3f(0.10, 0.12, 0.15)
    glPushMatrix()
    glTranslatef(0.0, -0.37, -5.19)
    draw_box(0.12, 0.10, 0.08)
    glPopMatrix()

    glColor3f(0.22, 0.24, 0.27)
    glPushMatrix()
    glTranslatef(-0.39, -0.05, -4.25)
    draw_cylinder_z(0.04, 0.06, -0.45, 0.45, segments=8)
    glColor3f(0.10, 0.10, 0.12)
    draw_cylinder_z(0.025, 0.025, -0.58, -0.40, segments=8)
    glPopMatrix()

    glPopAttrib()

    # 2. Superfícies pintadas da fuselagem, radome principal, dorso Pancake e naceles
    glPushAttrib(GL_TEXTURE_BIT | GL_ENABLE_BIT)
    if not full_skin_uv:
        glDisable(GL_TEXTURE_2D)

    # Corpo principal do Radome
    glColor3f(0.95, 0.96, 0.98) if full_skin_uv else glColor3f(0.74, 0.77, 0.81)
    draw_cylinder_z(0.18, 0.44, -5.85, -4.45, segments=14, y_scale=0.95, planar_uv=full_skin_uv)

    # Carenagem do Casulo TCS sob o queixo
    glColor3f(0.92, 0.93, 0.95) if full_skin_uv else glColor3f(0.66, 0.69, 0.73)
    glPushMatrix()
    glTranslatef(0.0, -0.36, -4.75)
    draw_surface_box(0.16, 0.14, 0.85, uv_scale=1.0, planar_uv=full_skin_uv)
    glPopMatrix()

    # Seções octogonais da fuselagem
    fuselage_sections = [
        (-4.45, 0.34, 0.44, 0.28, -0.32,  0.00, 0.24),
        (-3.20, 0.46, 0.58, 0.38, -0.36,  0.04, 0.34),
        (-1.60, 0.62, 0.78, 0.48, -0.36,  0.06, 0.38),
        (-0.20, 0.95, 1.18, 0.85, -0.34,  0.08, 0.38),
        ( 1.50, 1.32, 1.55, 1.25, -0.30,  0.08, 0.35),
        ( 3.60, 1.18, 1.32, 1.08, -0.24,  0.06, 0.30),
        ( 4.75, 0.95, 1.06, 0.88, -0.18,  0.05, 0.24),
    ]

    for i in range(len(fuselage_sections) - 1):
        if full_skin_uv:
            glColor3f(0.96, 0.97, 0.98)
        else:
            if i == 0:
                glColor3f(0.20, 0.22, 0.25)
            elif i == 1:
                glColor3f(0.68, 0.22, 0.20)
            else:
                glColor3f(0.73, 0.76, 0.80)
        draw_prism_section(fuselage_sections[i], fuselage_sections[i + 1], tex_scale=0.0, planar_uv=full_skin_uv)

    # Chines laterais inclinados
    glColor3f(0.94, 0.95, 0.97) if full_skin_uv else glColor3f(0.70, 0.73, 0.77)
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 0.56, 0.08, -2.15)
        glRotatef(-side * 25.0, 0.0, 0.0, 1.0)
        draw_surface_box(0.22, 0.10, 2.50, uv_scale=1.0, planar_uv=full_skin_uv)
        glPopMatrix()

    # Espinha Dorsal Superior e Painéis Inclinados do Pancake (agora com UV métrico sem esticar!)
    glColor3f(0.96, 0.97, 0.99) if full_skin_uv else glColor3f(0.75, 0.78, 0.82)
    glPushMatrix()
    glTranslatef(0.0, 0.36, 1.45)
    draw_surface_box(0.68, 0.10, 4.40, uv_scale=1.0, planar_uv=full_skin_uv)
    glPopMatrix()

    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 0.68, 0.32, 1.55)
        glRotatef(-side * 7.5, 0.0, 0.0, 1.0)
        draw_surface_box(0.78, 0.09, 4.20, uv_scale=1.0, planar_uv=full_skin_uv)
        glPopMatrix()

    # Beaver Tail Traseiro
    glColor3f(0.92, 0.93, 0.95) if full_skin_uv else glColor3f(0.68, 0.71, 0.75)
    glPushMatrix()
    glTranslatef(0.0, 0.06, 5.15)
    draw_surface_box(0.46, 0.14, 1.15, uv_scale=1.0, planar_uv=full_skin_uv)
    glColor3f(0.25, 0.27, 0.30)
    glTranslatef(0.0, 0.0, 0.52)
    draw_surface_box(0.36, 0.08, 0.18, uv_scale=0.5, planar_uv=full_skin_uv)
    glPopMatrix()

    # 3. Naceles Duplas, Rampas de Admissão e Quilhas Ventrais
    for side in (-1.0, 1.0):
        x_in = side * 0.42
        x_out = side * 1.16

        glColor3f(0.92, 0.93, 0.95) if full_skin_uv else glColor3f(0.65, 0.68, 0.72)
        glBegin(GL_QUADS)
        draw_surface_quad([x_out, -0.58, -1.85], [x_out, -0.50, 4.65], [x_out, 0.16, 4.65], [x_out, 0.20, -1.35], 1.5, planar_uv=full_skin_uv)
        draw_surface_quad([x_in, 0.20, -1.35], [x_in, 0.16, 4.65], [x_in, -0.50, 4.65], [x_in, -0.58, -1.85], 1.5, planar_uv=full_skin_uv)
        draw_surface_quad([x_in, -0.58, -1.85], [x_in, -0.50, 4.65], [x_out, -0.50, 4.65], [x_out, -0.58, -1.85], 1.5, planar_uv=full_skin_uv)
        draw_surface_quad([x_in, 0.20, -1.35], [x_out, 0.20, -1.35], [x_out, 0.16, 4.65], [x_in, 0.16, 4.65], 1.5, planar_uv=full_skin_uv)
        glEnd()

        glColor3f(0.95, 0.96, 0.98) if full_skin_uv else glColor3f(0.72, 0.75, 0.79)
        glBegin(GL_QUADS)
        draw_surface_quad([x_in, 0.22, -2.25], [x_out, 0.22, -2.05], [x_out, 0.20, -1.35], [x_in, 0.20, -1.35], 1.0, planar_uv=full_skin_uv)
        draw_surface_quad([x_out, 0.22, -2.05], [x_out, -0.58, -1.85], [x_out, 0.20, -1.35], [x_out, 0.22, -2.05], 1.0, planar_uv=full_skin_uv)
        glEnd()

        # Quilha Ventral
        glColor3f(0.90, 0.91, 0.93) if full_skin_uv else glColor3f(0.60, 0.63, 0.67)
        glPushMatrix()
        glTranslatef(side * 0.78, -0.54, 3.25)
        glRotatef(side * 12.0, 0.0, 0.0, 1.0)
        glBegin(GL_QUADS)
        draw_surface_quad([0.02, 0.05, -0.95], [0.02, 0.05, 0.95], [0.01, -0.32, 0.75], [0.01, -0.26, -0.45], 1.0, planar_uv=full_skin_uv)
        draw_surface_quad([-0.02, 0.05, 0.95], [-0.02, 0.05, -0.95], [-0.01, -0.26, -0.45], [-0.01, -0.32, 0.75], 1.0, planar_uv=full_skin_uv)
        glEnd()
        glPopMatrix()

        # Interior escuro da tomada de ar (sem textura)
        glPushAttrib(GL_TEXTURE_BIT | GL_ENABLE_BIT)
        glDisable(GL_TEXTURE_2D)
        glColor3f(0.10, 0.11, 0.13)
        glBegin(GL_QUADS)
        draw_quad_with_normal([x_in, -0.58, -1.85], [x_out, -0.58, -1.85], [x_out, 0.20, -1.45], [x_in, 0.20, -1.45])
        glEnd()
        glPopAttrib()

    glPopAttrib()

    # 4. Luvas Fixas das Asas (Wing Gloves)
    if not full_skin_uv and wing_tex_id is not None:
        glBindTexture(GL_TEXTURE_2D, wing_tex_id)
    glColor3f(0.96, 0.97, 0.99) if full_skin_uv else glColor3f(0.77, 0.79, 0.83)

    for side in (-1.0, 1.0):
        p_front = [side * 0.72,  0.14, -2.45]
        p_mid   = [side * 1.45,  0.12, -0.85]
        p_outer = [side * 2.18,  0.09,  0.28]
        p_rear  = [side * 1.15,  0.13,  2.15]

        b_front = [side * 0.72, -0.06, -2.45]
        b_mid   = [side * 1.45, -0.05, -0.85]
        b_outer = [side * 2.18, -0.02,  0.28]
        b_rear  = [side * 1.15, -0.06,  2.15]

        glBegin(GL_QUADS)
        if side > 0:
            draw_surface_quad(p_front, p_rear, p_outer, p_mid, 1.0, planar_uv=full_skin_uv)
            draw_surface_quad(b_front, b_mid, b_outer, b_rear, 1.0, planar_uv=full_skin_uv)
            draw_surface_quad(p_front, p_mid, b_mid, b_front, 1.0, planar_uv=full_skin_uv)
            draw_surface_quad(p_mid, p_outer, b_outer, b_mid, 1.0, planar_uv=full_skin_uv)
            draw_surface_quad(p_outer, p_rear, b_rear, b_outer, 1.0, planar_uv=full_skin_uv)
        else:
            draw_surface_quad(p_front, p_mid, p_outer, p_rear, 1.0, planar_uv=full_skin_uv)
            draw_surface_quad(b_front, b_rear, b_outer, b_mid, 1.0, planar_uv=full_skin_uv)
            draw_surface_quad(p_mid, p_front, b_front, b_mid, 1.0, planar_uv=full_skin_uv)
            draw_surface_quad(p_outer, p_mid, b_mid, b_outer, 1.0, planar_uv=full_skin_uv)
            draw_surface_quad(p_rear, p_outer, b_outer, b_rear, 1.0, planar_uv=full_skin_uv)
        glEnd()

    # 5. Estabilizadores Verticais Duplos Inclinados (Twin Tails)
    glPushAttrib(GL_TEXTURE_BIT | GL_ENABLE_BIT)
    if not full_skin_uv:
        glDisable(GL_TEXTURE_2D)

    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 0.94, 0.22, 3.55)
        glRotatef(-side * 7.5, 0.0, 0.0, 1.0)

        glColor3f(0.92, 0.93, 0.95) if full_skin_uv else glColor3f(0.68, 0.71, 0.75)
        glBegin(GL_TRIANGLES)
        draw_surface_tri([0.03, 0.0, -1.65], [0.03, 0.0, -0.75], [0.02, 0.28, -0.75], planar_uv=full_skin_uv)
        draw_surface_tri([-0.03, 0.0, -0.75], [-0.03, 0.0, -1.65], [-0.02, 0.28, -0.75], planar_uv=full_skin_uv)
        glEnd()

        glColor3f(0.94, 0.95, 0.97) if full_skin_uv else glColor3f(0.20, 0.22, 0.26)
        glBegin(GL_QUADS)
        draw_surface_quad([0.045, 0.0, -0.80], [0.045, 0.0, 0.88], [0.025, 1.52, 1.15], [0.025, 1.52, 0.25], 1.0, planar_uv=full_skin_uv)
        draw_surface_quad([-0.045, 0.0, 0.88], [-0.045, 0.0, -0.80], [-0.025, 1.52, 0.25], [-0.025, 1.52, 1.15], 1.0, planar_uv=full_skin_uv)
        draw_surface_quad([-0.045, 0.0, -0.80], [0.045, 0.0, -0.80], [0.025, 1.52, 0.25], [-0.025, 1.52, 0.25], 1.0, planar_uv=full_skin_uv)
        glEnd()

        # Topo da deriva
        glColor3f(0.96, 0.96, 0.98) if full_skin_uv else glColor3f(0.95, 0.78, 0.15)
        glBegin(GL_QUADS)
        draw_surface_quad([0.03, 1.52, 0.25], [0.03, 1.52, 1.42], [0.02, 1.72, 1.48], [0.02, 1.72, 0.35], 0.5, planar_uv=full_skin_uv)
        draw_surface_quad([-0.03, 1.52, 1.42], [-0.03, 1.52, 0.25], [-0.02, 1.72, 0.35], [-0.02, 1.72, 1.48], 0.5, planar_uv=full_skin_uv)
        glEnd()

        if side < 0:
            glPushAttrib(GL_LIGHTING_BIT | GL_TEXTURE_BIT | GL_ENABLE_BIT)
            glDisable(GL_LIGHTING)
            glDisable(GL_TEXTURE_2D)
            glColor3f(1.0, 0.15, 0.10)
            glPushMatrix()
            glTranslatef(0.0, 1.75, 0.65)
            draw_box(0.06, 0.06, 0.12)
            glPopMatrix()
            glPopAttrib()

        glPopMatrix()

    glPopAttrib()

    # 6. Cockpit Biposto, Canopy e Armamento Naval
    draw_cockpit_and_canopy()
    draw_weapons_loadout()


def build_f14_static_fuselage_list(wing_tex_id):
    """Compila a Display List original (Padrão VF-84 Jolly Rogers)."""
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.75, 0.75, 0.80, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 64.0)
    _compile_f14_fuselage_geometry(wing_tex_id=wing_tex_id, full_skin_uv=False)
    glEndList()
    return dlist


def build_f14_skinned_fuselage_list():
    """
    Compila a Display List com Mapeamento UV Triplanar Métrico para receber
    qualquer textura de Skin Metálica ou Camuflagem sem distorção.
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)
    _compile_f14_fuselage_geometry(wing_tex_id=None, full_skin_uv=True)
    glEndList()
    return dlist


# ==============================================================================
# ASAS DE GEOMETRIA VARIÁVEL (SLATS, FLAPS/SPOILERS)
# ==============================================================================

def draw_f14_wing_panel(side, wing_tex_id, sweep_angle, roll_input_deg, full_skin_uv=False):
    """Desenha uma asa móvel do F-14 a partir do seu pivô local (0, 0, 0) sem estiramento UV."""
    glBindTexture(GL_TEXTURE_2D, wing_tex_id)
    glColor3f(0.96, 0.97, 0.99) if full_skin_uv else glColor3f(0.75, 0.77, 0.81)

    span = 4.20 * side
    root_le = [0.0,   0.00, -0.68]
    root_mc = [0.0,   0.07, -0.10]
    root_te = [0.0,   0.00,  0.88]
    root_mb = [0.0,  -0.05, -0.10]

    tip_le  = [span,  0.00,  0.32]
    tip_mc  = [span,  0.03,  0.68]
    tip_te  = [span,  0.00,  1.38]
    tip_mb  = [span, -0.02,  0.68]

    glBegin(GL_QUADS)
    if side > 0:
        draw_surface_quad(root_le, root_mc, tip_mc, tip_le, 1.0, planar_uv=full_skin_uv)
        draw_surface_quad(root_mc, root_te, tip_te, tip_mc, 1.0, planar_uv=full_skin_uv)
        draw_surface_quad(root_mc, root_le, tip_le, tip_mb, 1.0, planar_uv=full_skin_uv)
        draw_surface_quad(root_te, root_mb, tip_mb, tip_te, 1.0, planar_uv=full_skin_uv)
    else:
        draw_surface_quad(root_mc, root_le, tip_le, tip_mc, 1.0, planar_uv=full_skin_uv)
        draw_surface_quad(root_te, root_mc, tip_mc, tip_te, 1.0, planar_uv=full_skin_uv)
        draw_surface_quad(root_le, root_mb, tip_mb, tip_le, 1.0, planar_uv=full_skin_uv)
        draw_surface_quad(root_mb, root_te, tip_te, tip_mb, 1.0, planar_uv=full_skin_uv)
    glEnd()

    glPushAttrib(GL_TEXTURE_BIT | GL_ENABLE_BIT)
    if not full_skin_uv:
        glDisable(GL_TEXTURE_2D)

    # Slat de bordo de ataque
    slat_deploy = max(0.0, min(1.0, (35.0 - sweep_angle) / 15.0))
    glColor3f(0.90, 0.91, 0.93) if full_skin_uv else glColor3f(0.64, 0.67, 0.71)
    glPushMatrix()
    glTranslatef(0.0, -0.015 * slat_deploy, -0.08 * slat_deploy)
    glBegin(GL_QUADS)
    s_in_1 = [side * 0.35, 0.01, -0.58]
    s_in_2 = [side * 0.35, 0.03, -0.42]
    s_out_1 = [span * 0.94, 0.01,  0.24]
    s_out_2 = [span * 0.94, 0.02,  0.38]
    if side > 0:
        draw_surface_quad(s_in_1, s_in_2, s_out_2, s_out_1, 1.0, planar_uv=full_skin_uv)
    else:
        draw_surface_quad(s_in_2, s_in_1, s_out_1, s_out_2, 1.0, planar_uv=full_skin_uv)
    glEnd()
    glPopMatrix()

    # Spoilers superiores de rolagem
    spoiler_up = max(0.0, side * roll_input_deg * 1.2)
    if spoiler_up > 0.5:
        glColor3f(0.85, 0.86, 0.88) if full_skin_uv else glColor3f(0.52, 0.55, 0.60)
        glPushMatrix()
        glTranslatef(side * 1.85, 0.05, 0.42)
        glRotatef(side * 14.0, 0.0, 1.0, 0.0)
        glRotatef(spoiler_up, 1.0, 0.0, 0.0)
        draw_surface_box(2.10, 0.02, 0.24, uv_scale=1.0, planar_uv=full_skin_uv)
        glPopMatrix()

    # Luzes de navegação nas pontas das asas
    glPushAttrib(GL_LIGHTING_BIT | GL_TEXTURE_BIT | GL_ENABLE_BIT)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    if side > 0:
        glColor3f(0.10, 1.0, 0.22)
    else:
        glColor3f(1.0, 0.14, 0.10)
    glPushMatrix()
    glTranslatef(span, 0.0, 0.85)
    draw_box(0.14, 0.06, 0.42)
    glPopMatrix()
    glPopAttrib()

    glPopAttrib()


# ==============================================================================
# RENDERIZAÇÃO HIERÁRQUICA COMPLETA DO F-14 TOMCAT
# ==============================================================================

def draw_f14_complete(
    aircraft,
    fuselage_dlist,
    wing_tex_id,
    sim_time,
    skin_manager=None,
    skinned_fuselage_dlist=None
):
    """
    Renderiza o F-14 Tomcat completo aplicando transformações hierárquicas e a Skin ativa.
    """
    use_custom_skin = (
        skin_manager is not None
        and skinned_fuselage_dlist is not None
        and skin_manager.is_custom_skin_active()
    )
    active_tex_id = skin_manager.get_active_texture_id() if skin_manager is not None else wing_tex_id

    glPushMatrix()
    glMultMatrixf(aircraft.get_model_matrix())

    # 1. Fuselagem principal, cockpit, naceles, derivas e mísseis
    if use_custom_skin:
        pat = skin_manager.current_pattern
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, pat["specular"])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, pat["shininess"])
        glBindTexture(GL_TEXTURE_2D, active_tex_id)
        glCallList(skinned_fuselage_dlist)
    else:
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.75, 0.75, 0.80, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 64.0)
        glCallList(fuselage_dlist)

    # 2. Trem de Pouso Retrátil
    draw_retractable_landing_gear(aircraft.gear_deploy, aircraft.rudder_yaw)

    # 3. Asas de Geometria Variável
    glPushMatrix()
    glTranslatef(1.65, 0.06, 0.15)
    glRotatef(-aircraft.wing_sweep_angle, 0.0, 1.0, 0.0)
    draw_f14_wing_panel(1.0, active_tex_id, aircraft.wing_sweep_angle, aircraft.elevator_roll, full_skin_uv=use_custom_skin)
    glPopMatrix()

    glPushMatrix()
    glTranslatef(-1.65, 0.06, 0.15)
    glRotatef(aircraft.wing_sweep_angle, 0.0, 1.0, 0.0)
    draw_f14_wing_panel(-1.0, active_tex_id, aircraft.wing_sweep_angle, aircraft.elevator_roll, full_skin_uv=use_custom_skin)
    glPopMatrix()

    glPushAttrib(GL_TEXTURE_BIT | GL_ENABLE_BIT)
    if use_custom_skin:
        glBindTexture(GL_TEXTURE_2D, active_tex_id)
    else:
        glDisable(GL_TEXTURE_2D)

    # 4. Lemes Articulados nas Derivas Duplas (com UV métrico sem cisalhamento)
    glColor3f(0.92, 0.93, 0.95) if use_custom_skin else glColor3f(0.26, 0.28, 0.33)
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 0.94, 0.22, 3.55)
        glRotatef(-side * 7.5, 0.0, 0.0, 1.0)
        glTranslatef(0.0, 0.0, 0.96)
        glRotatef(aircraft.rudder_yaw, 0.0, 1.0, 0.0)
        glBegin(GL_QUADS)
        draw_surface_quad([0.03, 0.05, 0.0], [0.02, 0.05, 0.36], [0.015, 1.48, 0.46], [0.02, 1.48, 0.16], 0.6, planar_uv=use_custom_skin)
        draw_surface_quad([-0.03, 0.05, 0.36], [-0.03, 0.05, 0.0], [-0.02, 1.48, 0.16], [-0.015, 1.48, 0.46], 0.6, planar_uv=use_custom_skin)
        glEnd()
        glPopMatrix()

    # 5. Profundores Horizontais Móveis (Differential Tailerons - sem cisalhamento trapezoidal)
    glColor3f(0.92, 0.93, 0.95) if use_custom_skin else glColor3f(0.58, 0.61, 0.66)
    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 1.15, -0.06, 4.35)
        deflection = aircraft.elevator_pitch + side * aircraft.elevator_roll
        glRotatef(deflection, 1.0, 0.0, 0.0)
        glRotatef(-side * 3.0, 0.0, 0.0, 1.0)

        span = side * 1.75
        glBegin(GL_QUADS)
        if side > 0:
            draw_surface_quad([0.0, 0.03, -0.60], [0.0, 0.02, 0.78], [span, 0.01, 1.25], [span, 0.01, 0.38], 1.0, planar_uv=use_custom_skin)
            draw_surface_quad([0.0, -0.02, 0.78], [0.0, -0.03, -0.60], [span, -0.01, 0.38], [span, -0.01, 1.25], 1.0, planar_uv=use_custom_skin)
            draw_surface_quad([0.0, -0.03, -0.60], [0.0, 0.03, -0.60], [span, 0.01, 0.38], [span, -0.01, 0.38], 1.0, planar_uv=use_custom_skin)
        else:
            draw_surface_quad([0.0, 0.02, 0.78], [0.0, 0.03, -0.60], [span, 0.01, 0.38], [span, 0.01, 1.25], 1.0, planar_uv=use_custom_skin)
            draw_surface_quad([0.0, -0.03, -0.60], [0.0, -0.02, 0.78], [span, -0.01, 1.25], [span, -0.01, 0.38], 1.0, planar_uv=use_custom_skin)
            draw_surface_quad([0.0, 0.03, -0.60], [0.0, -0.03, -0.60], [span, -0.01, 0.38], [span, 0.01, 0.38], 1.0, planar_uv=use_custom_skin)
        glEnd()
        glPopMatrix()

    # 6. Bocais Cilíndricos das Turbinas e Pós-Combustão (Afterburners - sem textura de skin)
    glDisable(GL_TEXTURE_2D)
    ab_active = getattr(aircraft, "afterburner", False) and aircraft.throttle > 0.02 and not aircraft.crashed
    pulse = 1.0 + 0.12 * math.sin(sim_time * 42.0)

    if ab_active:
        nozzle_open_r = 0.26 + 0.06 * aircraft.throttle
        flame_scale_z = (0.85 + 2.40 * aircraft.throttle) * pulse
        flame_scale_xy = 0.78 + 0.38 * aircraft.throttle
    else:
        nozzle_open_r = 0.20 + 0.03 * aircraft.throttle
        flame_scale_z = (0.12 + 0.28 * aircraft.throttle) * pulse
        flame_scale_xy = 0.52 + 0.18 * aircraft.throttle

    for side in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(side * 0.78, -0.16, 4.65)

        glColor3f(0.32, 0.34, 0.38)
        draw_cylinder_z(0.33, 0.31, -0.25, 0.35, segments=12)

        glColor3f(0.18, 0.19, 0.22)
        draw_cylinder_z(0.31, nozzle_open_r, 0.35, 0.82, segments=12)

        glColor3f(0.08, 0.08, 0.10)
        draw_cylinder_z(nozzle_open_r * 0.92, nozzle_open_r * 0.92, 0.35, 0.80, segments=12, cap_start=True)

        if aircraft.throttle > 0.02 and not aircraft.crashed:
            glPushAttrib(GL_LIGHTING_BIT | GL_ENABLE_BIT)
            glDisable(GL_LIGHTING)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

            glPushMatrix()
            glTranslatef(0.0, 0.0, 0.78)
            glScalef(flame_scale_xy, flame_scale_xy, flame_scale_z)

            if ab_active:
                glColor4f(1.0, 0.52 + 0.32 * aircraft.throttle, 0.10, 0.88)
                draw_cylinder_z(0.24, 0.01, 0.0, 1.45, segments=10)

                glColor4f(0.75, 0.92, 1.0, 0.95)
                draw_cylinder_z(0.15, 0.005, 0.0, 0.95, segments=10)

                glColor4f(1.0, 0.95, 0.80, 0.85)
                for ring_z, ring_r in ((0.28, 0.14), (0.56, 0.10), (0.84, 0.06)):
                    draw_cylinder_z(ring_r, ring_r * 0.65, ring_z, ring_z + 0.08, segments=8)
            else:
                glColor4f(0.95, 0.45, 0.12, 0.45 * aircraft.throttle)
                draw_cylinder_z(0.18, 0.05, 0.0, 0.55, segments=10)

            glPopMatrix()
            glPopAttrib()

        glPopMatrix()

    glPopAttrib()
    glPopMatrix()