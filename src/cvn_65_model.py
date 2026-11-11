"""
================================================================================
TopGraphics | cvn_65_model.py
Modelo low-poly de alta fidelidade do Porta-Aviões Nuclear USS Enterprise (CVN-65)
Inclui mapeamento UV planar sem distorções no convés e Ilha/Mastro em treliça 3D.
================================================================================
"""

import math
import numpy as np
from OpenGL.GL import *

from renderer_utils import (
    draw_box, draw_quad_with_normal, draw_tri_with_normal, upload_texture_rgb
)


# ==============================================================================
# CONSTANTES DIMENSIONAIS E DE COLISÃO (HARMONIZADAS COM FLIGHT_KINEMATICS)
# ==============================================================================

CARRIER_DECK_Y = 10.15          # Cota Y da superfície da pista de pouso
CARRIER_DECK_HALF_W = 24.0      # Meia-largura de referência do convés (-24 a +24 em X)
CARRIER_DECK_HALF_L = 115.0     # Meio-comprimento do convés (-115 a +115 em Z)

# Largura de referência do mapeamento UV planar
DECK_UV_HALF_W = 28.0

# Envelope global da Ilha + Mastro
CVN65_ISLAND_AABB = {
    "x_min": 12.0, "x_max": 22.4,
    "y_min": CARRIER_DECK_Y, "y_max": 42.0,
    "z_min": -31.5, "z_max": 2.5,
}

# Volumes hierárquicos (AABBs) fiéis à nova geometria da Ilha Nuclear e Mastro
CVN65_ISLAND_BOXES = [
    # 1. Base da Ilha, Passadiço, PriFly, Bloco Cúbico SCANFAR e Casa Traseira
    {
        "name": "TORRE DE COMANDO (SCANFAR) DO USS ENTERPRISE",
        "x_min": 12.0, "x_max": 22.2,
        "y_min": CARRIER_DECK_Y, "y_max": 23.5,
        "z_min": -31.5, "z_max": 2.5,
    },
    # 2. Domo Cônico Beehive (ECM) e Radar 3D AN/SPS-48 no topo do bloco
    {
        "name": "DOMO ECM BEEHIVE DA ILHA DO PORTA-AVIÕES",
        "x_min": 13.2, "x_max": 21.0,
        "y_min": 23.0, "y_max": 29.2,
        "z_min": -26.5, "z_max": -4.0,
    },
    # 3. Mastro Principal em Treliça, Vergas (Yardarms) e Antena TACAN Superior
    {
        "name": "MASTRO DE RADAR DO USS ENTERPRISE",
        "x_min": 12.6, "x_max": 21.8,
        "y_min": 22.5, "y_max": 42.0,
        "z_min": -12.5, "z_max": 0.5,
    },
]

# Caixas de colisão secundárias no convés (Guindaste e Defletores laterais a estibordo)
CVN65_DECK_OBSTACLES_AABB = [
    # Guindaste móvel estacionado a estibordo atrás da Ilha
    {
        "name": "GUINDASTE DO CONVÉS",
        "x_min": 14.5, "x_max": 21.0,
        "y_min": CARRIER_DECK_Y, "y_max": 16.5,
        "z_min": 8.0, "z_max": 24.0,
    },
    # Defletor de Jato (JBD) da Catapulta Lateral de Estibordo
    {
        "name": "DEFLETOR DE JATO (JBD)",
        "x_min": 9.8, "x_max": 15.5,
        "y_min": CARRIER_DECK_Y, "y_max": 12.8,
        "z_min": -48.0, "z_max": -42.0,
    },
]


def get_cvn65_deck_edges_at_z(z):
    """
    Retorna os limites laterais exatos (x_port, x_starboard) do polígono do convés
    na coordenada longitudinal 'z' (interpolação linear exata das seções do CVN-65).
    """
    deck_strips = [
        (-115.0, -11.5, 11.5),
        (-102.0, -14.5, 14.5),
        ( -65.0, -24.0, 24.0),
        ( -35.0, -26.5, 24.5),
        (  35.0, -26.5, 24.5),
        (  70.0, -26.0, 24.5),
        (  85.0, -23.0, 23.5),
        ( 115.0, -18.0, 18.0),
    ]
    if z <= deck_strips[0][0]:
        return deck_strips[0][1], deck_strips[0][2]
    if z >= deck_strips[-1][0]:
        return deck_strips[-1][1], deck_strips[-1][2]

    for i in range(len(deck_strips) - 1):
        z1, xp1, xs1 = deck_strips[i]
        z2, xp2, xs2 = deck_strips[i + 1]
        if z1 <= z <= z2:
            t = (z - z1) / (z2 - z1)
            return xp1 + t * (xp2 - xp1), xs1 + t * (xs2 - xs1)

    return -24.0, 24.0


def is_within_cvn65_deck_polygon(x, z):
    """
    Verifica se a coordenada (x, z) está sobre o polígono real do convés de voo
    do USS Enterprise CVN-65.
    """
    if abs(z) > CARRIER_DECK_HALF_L:
        return False
    x_port, x_stbd = get_cvn65_deck_edges_at_z(z)
    return (x_port <= x <= x_stbd)


def check_cvn65_extra_collisions(pos, right_vec=None, forward_vec=None):
    """
    Verifica colisão da aeronave (centro, pontas das asas e nariz) com os 3 níveis
    da Ilha Nuclear SCANFAR + Mastro em Treliça e obstáculos laterais do CVN-65.
    Retorna (True, motivo_str) se houve colisão, ou (False, "") caso contrário.
    """
    sample_points = [pos]
    if right_vec is not None:
        sample_points.append(pos + right_vec * 4.5)
        sample_points.append(pos - right_vec * 4.5)
    if forward_vec is not None:
        sample_points.append(pos + forward_vec * 4.8)

    for pt in sample_points:
        x, y, z = float(pt[0]), float(pt[1]), float(pt[2])

        # 1. Verifica os volumes hierárquicos da Ilha + Beehive + Mastro em Treliça
        for box in CVN65_ISLAND_BOXES:
            if (box["x_min"] <= x <= box["x_max"]) and (box["z_min"] <= z <= box["z_max"]) and (box["y_min"] <= y <= box["y_max"]):
                return True, f"COLISÃO COM O {box['name']}!"

        # 2. Verifica obstáculos secundários do convés (Guindaste e JBD)
        for obs in CVN65_DECK_OBSTACLES_AABB:
            if (obs["x_min"] <= x <= obs["x_max"]) and (obs["z_min"] <= z <= obs["z_max"]) and (obs["y_min"] <= y <= obs["y_max"]):
                return True, f"COLISÃO COM O {obs['name']} DO PORTA-AVIÕES!"

    return False, ""


# ==============================================================================
# UTILITÁRIOS GEOMÉTRICOS AUXILIARES
# ==============================================================================

def _draw_cylinder_y(r_bot, r_top, y_bot, y_top, segments=16, cap_top=True):
    """Desenha um cilindro ou tronco de cone vertical ao longo do eixo Y."""
    dy = y_top - y_bot
    dr = r_top - r_bot
    length = math.hypot(dy, dr)
    ny_slope = -dr / length if length > 1e-6 else 0.0
    nr_slope = dy / length if length > 1e-6 else 1.0

    glBegin(GL_QUAD_STRIP)
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        ca, sa = math.cos(ang), math.sin(ang)
        glNormal3f(ca * nr_slope, ny_slope, sa * nr_slope)
        glVertex3f(r_bot * ca, y_bot, r_bot * sa)
        glVertex3f(r_top * ca, y_top, r_top * sa)
    glEnd()

    if cap_top and r_top > 1e-4:
        glBegin(GL_TRIANGLE_FAN)
        glNormal3f(0.0, 1.0, 0.0)
        glVertex3f(0.0, y_top, 0.0)
        for i in range(segments, -1, -1):
            ang = (2.0 * math.pi * i) / segments
            glVertex3f(r_top * math.cos(ang), y_top, r_top * math.sin(ang))
        glEnd()


def _draw_strut_3d(p1, p2, thickness=0.12):
    """Desenha uma viga/barra 3D entre dois pontos arbitrários p1 e p2 (para o mastro em treliça)."""
    v = np.array(p2, dtype=np.float32) - np.array(p1, dtype=np.float32)
    length = float(np.linalg.norm(v))
    if length < 1e-5:
        return
    mid = 0.5 * (np.array(p1, dtype=np.float32) + np.array(p2, dtype=np.float32))
    vn = v / length

    # Eixo padrão Y da draw_box rotacionado para alinhar ao vetor vn
    up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    axis = np.cross(up, vn)
    axis_len = float(np.linalg.norm(axis))
    dot_val = float(np.clip(np.dot(up, vn), -1.0, 1.0))
    angle_deg = math.degrees(math.acos(dot_val))

    glPushMatrix()
    glTranslatef(float(mid[0]), float(mid[1]), float(mid[2]))
    if axis_len > 1e-5:
        glRotatef(angle_deg, float(axis[0] / axis_len), float(axis[1] / axis_len), float(axis[2] / axis_len))
    elif dot_val < 0.0:
        glRotatef(180.0, 1.0, 0.0, 0.0)
    draw_box(thickness, length, thickness)
    glPopMatrix()


def _draw_hull_loft_segment(z1, z2, w_bot1, w_top1, w_bot2, w_top2, y_bot, y_top):
    """Conecta duas seções trapezoidais simétricas do casco ao longo de Z."""
    bl1, br1 = [-w_bot1, y_bot, z1], [w_bot1, y_bot, z1]
    tl1, tr1 = [-w_top1, y_top, z1], [w_top1, y_top, z1]
    bl2, br2 = [-w_bot2, y_bot, z2], [w_bot2, y_bot, z2]
    tl2, tr2 = [-w_top2, y_top, z2], [w_top2, y_top, z2]

    glBegin(GL_QUADS)
    draw_quad_with_normal(tr1, tr2, br2, br1)
    draw_quad_with_normal(bl1, bl2, tl2, tl1)
    glEnd()


# ==============================================================================
# TEXTURA PROCEDURAL 1024x1024 EM ESPAÇO DO MUNDO
# ==============================================================================

def _stamp_digit_6(img, x0, y0, w, h, color):
    """Desenha o dígito '6' estilo naval US Navy no buffer de textura."""
    t = max(3, w // 5)
    img[y0:y0 + t, x0:x0 + w] = color
    img[y0 + h - t:y0 + h, x0:x0 + w] = color
    img[y0 + h // 2 - t // 2:y0 + h // 2 + t // 2, x0:x0 + w] = color
    img[y0:y0 + h, x0:x0 + t] = color
    img[y0 + h // 2:y0 + h, x0 + w - t:x0 + w] = color


def _stamp_digit_5(img, x0, y0, w, h, color):
    """Desenha o dígito '5' estilo naval US Navy no buffer de textura."""
    t = max(3, w // 5)
    img[y0:y0 + t, x0:x0 + w] = color
    img[y0 + h - t:y0 + h, x0:x0 + w] = color
    img[y0 + h // 2 - t // 2:y0 + h // 2 + t // 2, x0:x0 + w] = color
    img[y0:y0 + h // 2, x0:x0 + t] = color
    img[y0 + h // 2:y0 + h, x0 + w - t:x0 + w] = color


def create_cvn65_deck_texture():
    """
    Gera textura 1024x1024 mapeada diretamente nas coordenadas reais do convés
    (X em [-28, +28], Z em [-115, +115]), eliminando 100% da distorção trapezoidal:
      - Pista oblíqua perfeitamente reta da popa (X=+3.5, Z=+106) ao sponson (X=-17.5, Z=-56).
      - Faixa central tracejada de decolagem reta em X = 0.0.
      - Foul Line vermelha/branca reta em X = +9.2.
      - 4 trilhos de catapultas a vapor retos + linhas amarelas seguindo a borda real do convés.
    """
    size = 1024
    img = np.full((size, size, 3), 52, dtype=np.uint8)
    rng = np.random.default_rng(65)
    noise = rng.integers(-5, 6, size=(size, size, 3), dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 36, 70).astype(np.uint8)

    # Funções de conversão Mundo <-> Pixel (lineares e constantes em todo o convés)
    def x_to_px(x_w):
        return int(round(((x_w + DECK_UV_HALF_W) / (2.0 * DECK_UV_HALF_W)) * (size - 1)))

    def z_to_py(z_w):
        return int(round(((z_w + CARRIER_DECK_HALF_L) / (2.0 * CARRIER_DECK_HALF_L)) * (size - 1)))

    # 1. Juntas das chapas de aço HY-80
    for py in range(0, size, 32):
        img[py:py + 1, :] = np.clip(img[py:py + 1, :].astype(np.int16) - 9, 25, 255).astype(np.uint8)
    for px in range(0, size, 32):
        img[:, px:px + 1] = np.clip(img[:, px:px + 1].astype(np.int16) - 7, 25, 255).astype(np.uint8)

    # 2. Marcas escuras de borracha na zona de toque dos cabos (Z = +32 a +92)
    py_td_start, py_td_end = z_to_py(32.0), z_to_py(92.0)
    px_td_left, px_td_right = x_to_px(-8.5), x_to_px(6.5)
    for py in range(py_td_start, py_td_end):
        for px in range(px_td_left, px_td_right):
            if ((px * 11 + py * 17) % 6) == 0:
                img[py, px] = np.clip(img[py, px].astype(np.int16) - 13, 22, 255).astype(np.uint8)

    # Parâmetros geométricos exatos da Pista Oblíqua (Angled Flight Deck) em coordenadas de mundo
    z_ang_start = -58.0
    z_ang_end = 106.0
    x_ang_start = -17.2   # Extremidade dianteira no sponson de bombordo
    x_ang_end = 3.2       # Extremidade traseira na cabeceira da popa
    half_ang_w = 7.2      # Meia-largura da pista oblíqua (14.4m de largura total)

    for py in range(size):
        z_w = -CARRIER_DECK_HALF_L + (2.0 * CARRIER_DECK_HALF_L) * (py / float(size - 1))

        # A) Linhas amarelas de segurança contornando a borda real do polígono do convés
        xp_edge, xs_edge = get_cvn65_deck_edges_at_z(z_w)
        px_port_line = x_to_px(xp_edge + 0.85)
        px_stbd_line = x_to_px(xs_edge - 0.85)
        if 0 <= px_port_line < size - 5:
            img[py, px_port_line:px_port_line + 5] = [235, 200, 42]
        if 5 <= px_stbd_line < size:
            img[py, px_stbd_line - 5:px_stbd_line] = [235, 200, 42]

        # B) Linha Central Axial de Decolagem (X = 0.0, perfeitamente reta sob o F-14)
        if -104.0 <= z_w <= 104.0:
            px_center = x_to_px(0.0)
            if (int((z_w + 115.0) * 0.45) % 2) == 0:
                img[py, px_center - 4:px_center + 4] = [238, 240, 244]

        # C) Pista Oblíqua de Pouso (Angled Deck) 100% reta em espaço de mundo
        if z_ang_start <= z_w <= z_ang_end:
            t_ang = (z_w - z_ang_start) / (z_ang_end - z_ang_start)
            x_ang_c = x_ang_start + t_ang * (x_ang_end - x_ang_start)

            px_left = x_to_px(x_ang_c - half_ang_w)
            px_right = x_to_px(x_ang_c + half_ang_w)
            px_mid = x_to_px(x_ang_c)

            # Borda esquerda da pista oblíqua (branca externa + amarela interna)
            if 0 <= px_left < size - 9:
                img[py, px_left:px_left + 6] = [240, 240, 242]
                img[py, px_left + 6:px_left + 9] = [238, 198, 42]

            # Borda direita da pista oblíqua (branca externa + amarela interna)
            if 9 <= px_right < size:
                img[py, px_right - 6:px_right] = [240, 240, 242]
                img[py, px_right - 9:px_right - 6] = [238, 198, 42]

            # Eixo central tracejado amarelo da pista oblíqua
            if (int((z_w + 115.0) * 0.5) % 2) == 0:
                img[py, px_mid - 3:px_mid + 3] = [242, 202, 45]

        # D) Foul Line de Segurança de Estibordo (X = +9.2, vermelha e branca reta)
        if -65.0 <= z_w <= 86.0:
            px_foul = x_to_px(9.2)
            foul_col = [220, 38, 32] if (int((z_w + 115.0) * 0.6) % 2 == 0) else [242, 242, 242]
            img[py, px_foul - 3:px_foul + 3] = foul_col

        # E) Trilhos das 4 Catapultas a Vapor
        if -108.0 <= z_w <= -32.0:
            px_cat1 = x_to_px(-4.8)
            px_cat2 = x_to_px(4.8)
            img[py, px_cat1 - 2:px_cat1 + 2] = [145, 152, 160]
            img[py, px_cat2 - 2:px_cat2 + 2] = [145, 152, 160]
        if -54.0 <= z_w <= 18.0:
            t_c3 = (z_w - (-54.0)) / 72.0
            px_cat3 = x_to_px(-21.0 + t_c3 * 4.5)
            px_cat4 = x_to_px(-15.5 + t_c3 * 4.5)
            img[py, px_cat3 - 2:px_cat3 + 2] = [145, 152, 160]
            img[py, px_cat4 - 2:px_cat4 + 2] = [145, 152, 160]

    # 3. Barras de Cabeceira de Pouso na Popa (Threshold Markings em Z = +106 a +113)
    py_th0, py_th1 = z_to_py(106.5), z_to_py(113.0)
    for x_bar in np.linspace(-9.5, 9.5, 9):
        px_b = x_to_px(x_bar)
        img[py_th0:py_th1, px_b - 5:px_b + 5] = [238, 238, 240]

    # 4. Numeral "65" branco pintado na Proa (Z = -104 a -88) e na Popa (Z = +88 a +103)
    white_paint = [240, 242, 245]
    px_6 = x_to_px(-4.2)
    px_5 = x_to_px(0.8)
    digit_w = x_to_px(3.6) - x_to_px(0.0)

    # Numeral "65" na Proa
    py_bow_top = z_to_py(-103.0)
    py_bow_h = z_to_py(-88.0) - py_bow_top
    _stamp_digit_6(img, px_6, py_bow_top, digit_w, py_bow_h, white_paint)
    _stamp_digit_5(img, px_5, py_bow_top, digit_w, py_bow_h, white_paint)

    # Numeral "65" na Popa (antes da cabeceira)
    py_stern_top = z_to_py(88.0)
    py_stern_h = z_to_py(103.0) - py_stern_top
    _stamp_digit_6(img, px_6, py_stern_top, digit_w, py_stern_h, white_paint)
    _stamp_digit_5(img, px_5, py_stern_top, digit_w, py_stern_h, white_paint)

    return upload_texture_rgb(img)


# ==============================================================================
# SUBCOMPONENTES 3D DO USS ENTERPRISE CVN-65
# ==============================================================================

def _draw_cvn65_hull_and_sponsons():
    """
    Constrói o casco completo do CVN-65
      - Obra viva + linha d'água preta + bulbo de proa.
      - Costado cinza naval (Haze Gray) com proa lançada (flared bow).
      - Sponsons em balanço para a pista oblíqua (-X) e elevadores (+X).
      - Aberturas recuadas do hangar e 4 elevadores de aeronaves nas bordas.
    """
    hull_stations = [
        (-115.0,  0.5,   3.5),
        (-102.0,  5.5,  10.5),
        ( -78.0, 12.0,  16.5),
        ( -40.0, 16.2,  19.0),
        (  15.0, 16.5,  19.2),
        (  75.0, 15.2,  18.2),
        ( 112.0, 11.5,  15.5),
    ]

    # 1. Faixa da Linha d'Água Preta (Boot-Topping: Y = 0.0 a Y = 1.65)
    glColor3f(0.10, 0.11, 0.13)
    for i in range(len(hull_stations) - 1):
        z1, wb1, wt1 = hull_stations[i]
        z2, wb2, wt2 = hull_stations[i + 1]
        wm1 = wb1 + (wt1 - wb1) * 0.22
        wm2 = wb2 + (wt2 - wb2) * 0.22
        _draw_hull_loft_segment(z1, z2, wb1, wm1, wb2, wm2, 0.0, 1.65)

    # Bulbo de proa ao nível da linha d'água
    glColor3f(0.48, 0.14, 0.12)
    glPushMatrix()
    glTranslatef(0.0, 0.45, -113.5)
    draw_box(2.4, 0.9, 6.5)
    glPopMatrix()

    # 2. Costado Principal Cinza Naval (Haze Gray: Y = 1.65 a Y = 7.20)
    glColor3f(0.36, 0.39, 0.43)
    for i in range(len(hull_stations) - 1):
        z1, wb1, wt1 = hull_stations[i]
        z2, wb2, wt2 = hull_stations[i + 1]
        wm1 = wb1 + (wt1 - wb1) * 0.22
        wm2 = wb2 + (wt2 - wb2) * 0.22
        _draw_hull_loft_segment(z1, z2, wm1, wt1, wm2, wt2, 1.65, 7.20)

    # Fechamento da Popa Espelhada (Transom Stern em Z = +112.0 a +115.0)
    glColor3f(0.32, 0.35, 0.39)
    glBegin(GL_QUADS)
    draw_quad_with_normal([-11.5, 0.0, 112.0], [11.5, 0.0, 112.0], [15.5, 7.2, 112.0], [-15.5, 7.2, 112.0])
    draw_quad_with_normal([-15.5, 7.2, 112.0], [15.5, 7.2, 112.0], [18.0, CARRIER_DECK_Y, 115.0], [-18.0, CARRIER_DECK_Y, 115.0])
    glEnd()

    # Fechamento da Proa Lançada (Bow Stem / Hurricane Bow em Z = -115.0 a -102.0)
    glColor3f(0.38, 0.41, 0.45)
    glBegin(GL_QUADS)
    draw_quad_with_normal([-3.5, 7.2, -112.0], [3.5, 7.2, -112.0], [11.5, CARRIER_DECK_Y, -115.0], [-11.5, CARRIER_DECK_Y, -115.0])
    draw_quad_with_normal([3.5, 7.2, -112.0], [10.5, 7.2, -102.0], [14.5, CARRIER_DECK_Y, -102.0], [11.5, CARRIER_DECK_Y, -115.0])
    draw_quad_with_normal([-10.5, 7.2, -102.0], [-3.5, 7.2, -112.0], [-11.5, CARRIER_DECK_Y, -115.0], [-14.5, CARRIER_DECK_Y, -102.0])
    glEnd()

    # 3. Sponsons Superiores do Hangar e Sustentação do Convés (Y = 7.20 a Y = 10.05)
    glColor3f(0.33, 0.36, 0.40)
    port_sponson = [
        (-102.0, -10.5, -14.5),
        ( -65.0, -15.0, -24.0),
        ( -35.0, -18.5, -26.5),
        (  35.0, -19.0, -26.5),
        (  70.0, -17.5, -26.0),
        ( 112.0, -15.5, -18.0),
    ]
    glBegin(GL_QUADS)
    for i in range(len(port_sponson) - 1):
        z1, xb1, xt1 = port_sponson[i]
        z2, xb2, xt2 = port_sponson[i + 1]
        draw_quad_with_normal([xb1, 7.20, z1], [xb2, 7.20, z2], [xt2, 10.05, z2], [xt1, 10.05, z1])
    glEnd()

    stbd_sponson = [
        (-102.0, 10.5, 14.5),
        ( -65.0, 15.0, 24.0),
        (  80.0, 18.5, 24.5),
        ( 112.0, 15.5, 18.0),
    ]
    glBegin(GL_QUADS)
    for i in range(len(stbd_sponson) - 1):
        z1, xb1, xt1 = stbd_sponson[i]
        z2, xb2, xt2 = stbd_sponson[i + 1]
        draw_quad_with_normal([xt1, 10.05, z1], [xt2, 10.05, z2], [xb2, 7.20, z2], [xb1, 7.20, z1])
    glEnd()

    # 4. Aberturas Laterais do Hangar (Hangar Bays)
    glColor3f(0.14, 0.15, 0.18)
    for z_bay in (-52.0, 22.0, 58.0):
        glPushMatrix()
        glTranslatef(18.8, 6.2, z_bay)
        draw_box(0.8, 2.6, 16.0)
        glPopMatrix()
    for z_bay in (48.0, 78.0):
        glPushMatrix()
        glTranslatef(-18.8, 6.2, z_bay)
        draw_box(0.8, 2.6, 15.0)
        glPopMatrix()

    # 5. Os 4 Elevadores de Borda de Convés do CVN-65 (Deck-Edge Elevators)
    elevators = [
        ( 25.4, -54.0, 13.0),
        ( 25.4,  22.0, 13.0),
        ( 25.4,  58.0, 13.0),
        (-27.4,  52.0, 13.0),
    ]
    for x_el, z_el, l_el in elevators:
        glColor3f(0.28, 0.30, 0.34)
        glPushMatrix()
        glTranslatef(x_el, CARRIER_DECK_Y - 0.22, z_el)
        draw_box(3.2, 0.40, l_el)
        glColor3f(0.42, 0.45, 0.50)
        glTranslatef(-math.copysign(0.8, x_el), -1.1, 0.0)
        draw_box(1.6, 1.8, l_el * 0.82)
        glPopMatrix()


def _draw_cvn65_flight_deck_surface(deck_tex_id):
    """
    Desenha a superfície superior do Convés de Voo em Y = CARRIER_DECK_Y,
    usando COORDENADAS UV PLANARES EM ESPAÇO DE MUNDO (u linear em X, v linear em Z)
    para eliminar qualquer distorção diagonal nas linhas pintadas da pista.
    """
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, deck_tex_id)
    glColor3f(0.96, 0.96, 0.98)

    y = CARRIER_DECK_Y
    deck_strips = [
        (-115.0, -11.5, 11.5),
        (-102.0, -14.5, 14.5),
        ( -65.0, -24.0, 24.0),
        ( -35.0, -26.5, 24.5),
        (  35.0, -26.5, 24.5),
        (  70.0, -26.0, 24.5),
        (  85.0, -23.0, 23.5),
        ( 115.0, -18.0, 18.0),
    ]

    glBegin(GL_QUADS)
    glNormal3f(0.0, 1.0, 0.0)
    for i in range(len(deck_strips) - 1):
        z1, xp1, xs1 = deck_strips[i]
        z2, xp2, xs2 = deck_strips[i + 1]

        v1 = (z1 + CARRIER_DECK_HALF_L) / (2.0 * CARRIER_DECK_HALF_L)
        v2 = (z2 + CARRIER_DECK_HALF_L) / (2.0 * CARRIER_DECK_HALF_L)

        up1 = (xp1 + DECK_UV_HALF_W) / (2.0 * DECK_UV_HALF_W)
        up2 = (xp2 + DECK_UV_HALF_W) / (2.0 * DECK_UV_HALF_W)
        us1 = (xs1 + DECK_UV_HALF_W) / (2.0 * DECK_UV_HALF_W)
        us2 = (xs2 + DECK_UV_HALF_W) / (2.0 * DECK_UV_HALF_W)

        glTexCoord2f(up1, v1)
        glVertex3f(xp1, y, z1)
        glTexCoord2f(up2, v2)
        glVertex3f(xp2, y, z2)
        glTexCoord2f(us2, v2)
        glVertex3f(xs2, y, z2)
        glTexCoord2f(us1, v1)
        glVertex3f(xs1, y, z1)
    glEnd()

    glDisable(GL_TEXTURE_2D)


def _draw_3d_number_65_side_plaque(side):
    """
    Desenha a placa azul-marinho e os dígitos '65' em relevo 3D na lateral do
    bloco SCANFAR da Ilha (visível mesmo com texturas desligadas).
    """
    x_face = side * 4.22
    glPushMatrix()
    glTranslatef(x_face, 0.15, -3.6)

    # Fundo azul-marinho naval da placa
    glColor3f(0.14, 0.18, 0.26)
    draw_box(0.10, 2.50, 3.60)

    # Dígitos "6" e "5" em blocos 3D brancos
    glColor3f(0.95, 0.96, 0.98)
    x_digit = side * 0.05
    # Define qual dígito fica à frente/atrás conforme o lado (bombordo vs estibordo)
    z_6 = -0.85 * side
    z_5 =  0.85 * side

    # Dígito '6'
    for dy, dz, sy, sz in [
        ( 0.85, z_6, 0.26, 1.25),   # barra superior
        ( 0.00, z_6, 0.24, 1.25),   # barra central
        (-0.85, z_6, 0.26, 1.25),   # barra inferior
        ( 0.00, z_6 - 0.48 * side, 1.95, 0.28),  # coluna esquerda completa
        (-0.42, z_6 + 0.48 * side, 1.10, 0.28),  # coluna direita inferior
    ]:
        glPushMatrix()
        glTranslatef(x_digit, dy, dz)
        draw_box(0.06, sy, sz)
        glPopMatrix()

    # Dígito '5'
    for dy, dz, sy, sz in [
        ( 0.85, z_5, 0.26, 1.25),   # barra superior
        ( 0.00, z_5, 0.24, 1.25),   # barra central
        (-0.85, z_5, 0.26, 1.25),   # barra inferior
        ( 0.42, z_5 - 0.48 * side, 1.10, 0.28),  # coluna esquerda superior
        (-0.42, z_5 + 0.48 * side, 1.10, 0.28),  # coluna direita inferior
    ]:
        glPushMatrix()
        glTranslatef(x_digit, dy, dz)
        draw_box(0.06, sy, sz)
        glPopMatrix()

    glPopMatrix()


def _draw_cvn65_island_superstructure():
    """
    Reconstrói com máxima fidelidade a Ilha Nuclear e o Mastro em Treliça do
    USS Enterprise CVN-65:
      1. Casamata inferior alongada com nervuras verticais, proa chanfrada e casa de popa.
      2. Passarelas (catwalks) em múltiplos níveis, PriFly envidraçado a bombordo e
         2 galerias de comando (Navigation Bridge e Flag Bridge) com viseiras solares.
      3. Bloco Cúbico SCANFAR em balanço com os 8 painéis phased-array (AN/SPS-32 horizontais
         e AN/SPS-33 verticais) emoldurados + placas 3D '65' + radomes SATCOM OE-82.
      4. Cúpula Cônica 'Beehive' (AN/ULQ-6 ECM) escalonada com 5 anéis horizontais e mastro de topo.
      5. Torre traseira de radar (AN/SPS-48 planar 3D) e Mastro Principal em Treliça
         de 4 pernas convergentes, travessas em X, 3 plataformas, 2 vergas largas e antena TACAN.
    """
    y0 = CARRIER_DECK_Y
    island_x = 17.2
    island_z = -15.0

    glPushMatrix()
    glTranslatef(island_x, y0, island_z)

    # ==========================================================================
    # 1. CASAMATA INFERIOR / PEDESTAL DA ILHA (Y = 0.0 a 6.4)
    # ==========================================================================
    # Corpo central inferior (Z = -13.5 a +10.5 relativo a island_z -> Z_world = -28.5 a -4.5)
    glColor3f(0.42, 0.45, 0.50)
    glPushMatrix()
    glTranslatef(0.0, 3.2, -1.5)
    draw_box(5.4, 6.4, 24.0)
    glPopMatrix()

    # Proa chanfrada da base da ilha (Z_rel = -15.8 a -13.5)
    glColor3f(0.40, 0.43, 0.48)
    glBegin(GL_QUADS)
    # Frente estreita
    draw_quad_with_normal([-1.8, 0.0, -15.8], [1.8, 0.0, -15.8], [1.8, 6.4, -15.8], [-1.8, 6.4, -15.8])
    # Bochecha bombordo
    draw_quad_with_normal([-2.7, 0.0, -13.5], [-1.8, 0.0, -15.8], [-1.8, 6.4, -15.8], [-2.7, 6.4, -13.5])
    # Bochecha estibordo
    draw_quad_with_normal([1.8, 0.0, -15.8], [2.7, 0.0, -13.5], [2.7, 6.4, -13.5], [1.8, 6.4, -15.8])
    # Topo da proa da ilha
    draw_quad_with_normal([-2.7, 6.4, -13.5], [-1.8, 6.4, -15.8], [1.8, 6.4, -15.8], [2.7, 6.4, -13.5])
    glEnd()

    # Extensão traseira escalonada da Ilha (Aft Radar/Machinery House: Z_rel = +10.5 a +16.8)
    glColor3f(0.39, 0.42, 0.47)
    glPushMatrix()
    glTranslatef(0.0, 2.6, 13.6)
    draw_box(4.6, 5.2, 6.4)
    glPopMatrix()

    # Nervuras verticais externas e portas estanques na base da ilha
    glColor3f(0.33, 0.36, 0.40)
    for z_rib in (-11.0, -7.5, -4.0, -0.5, 3.0, 6.5, 10.0):
        for side in (-1.0, 1.0):
            glPushMatrix()
            glTranslatef(side * 2.75, 2.8, z_rib)
            draw_box(0.18, 5.6, 0.32)
            glPopMatrix()

    # ==========================================================================
    # 2. PASSARELAS (CATWALKS), PRIFLY E PONTES DE COMANDO (Y = 3.8 a 6.6)
    # ==========================================================================
    # Passarela contínua de Nível O-2 / O-3 ao redor da frente e bombordo
    glColor3f(0.35, 0.38, 0.43)
    glPushMatrix()
    glTranslatef(-3.05, 3.8, -1.0)
    draw_box(0.90, 0.55, 25.5)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0.0, 3.8, -14.8)
    draw_box(6.4, 0.55, 1.8)
    glPopMatrix()

    # Cabine PriFly (Primary Flight Control) em balanço a bombordo voltada para o convés
    glColor3f(0.44, 0.47, 0.52)
    glPushMatrix()
    glTranslatef(-3.45, 5.1, 2.2)
    draw_box(1.40, 1.90, 11.2)
    # Vidros escuros inclinados do PriFly
    glColor3f(0.08, 0.14, 0.20)
    glTranslatef(-0.66, 0.10, 0.0)
    draw_box(0.16, 0.88, 10.4)
    # Teto/viseira solar sobre o PriFly
    glColor3f(0.48, 0.51, 0.56)
    glTranslatef(0.25, 0.62, 0.0)
    draw_box(0.85, 0.22, 11.4)
    glPopMatrix()

    # Ponte de Navegação e Ponte do Almirante (2 galerias frontais sobrepostas)
    for y_br, z_br, w_br in ((4.5, -13.8, 5.2), (5.7, -13.4, 5.6)):
        # Janelas blindadas escuras
        glColor3f(0.08, 0.14, 0.20)
        glPushMatrix()
        glTranslatef(0.0, y_br, z_br)
        draw_box(w_br, 0.72, 1.2)
        glPopMatrix()
        # Quebra-sol (visor) superior
        glColor3f(0.48, 0.51, 0.56)
        glPushMatrix()
        glTranslatef(0.0, y_br + 0.44, z_br - 0.18)
        draw_box(w_br + 0.4, 0.18, 1.5)
        glPopMatrix()

    # ==========================================================================
    # 3. BLOCO CÚBICO NUCLEAR SCANFAR
    # ==========================================================================
    # O grande cubo característico em balanço sobre o pedestal (Z_rel = -12.5 a +4.5)
    glColor3f(0.49, 0.52, 0.57)
    glPushMatrix()
    glTranslatef(0.0, 9.3, -4.0)
    draw_box(8.30, 5.80, 17.20)

    # Moldura superior de acabamento (Roof Coaming / Bulwark) do bloco SCANFAR
    glColor3f(0.42, 0.45, 0.50)
    glPushMatrix()
    glTranslatef(0.0, 3.05, 0.0)
    draw_box(8.60, 0.35, 17.50)
    glPopMatrix()

    # Painéis de Radar Phased-Array AN/SPS-32 (Largo) e AN/SPS-33 (Alto) nas laterais (-X e +X)
    for side in (-1.0, 1.0):
        # 1. Painel Retangular Largo AN/SPS-32 (parte traseira/central da lateral)
        glPushMatrix()
        glTranslatef(side * 4.18, -0.05, 3.2)
        glColor3f(0.28, 0.30, 0.34)
        draw_box(0.22, 3.40, 7.60)
        glColor3f(0.80, 0.82, 0.86)
        glTranslatef(side * 0.08, 0.0, 0.0)
        draw_box(0.12, 3.00, 7.10)
        glPopMatrix()

        # 2. Painel Vertical Alto AN/SPS-33 (parte central da lateral)
        glPushMatrix()
        glTranslatef(side * 4.18, 0.10, -2.2)
        glColor3f(0.28, 0.30, 0.34)
        draw_box(0.22, 4.30, 2.60)
        glColor3f(0.82, 0.84, 0.88)
        glTranslatef(side * 0.08, 0.0, 0.0)
        draw_box(0.12, 3.90, 2.20)
        glPopMatrix()

        # 3. Placa Naval com Numeral "65" em Relevo 3D na porção dianteira da lateral
        _draw_3d_number_65_side_plaque(side)

    # Painéis SCANFAR Frontal (-Z) e Traseiro (+Z) do Bloco Cúbico
    for z_dir in (-1.0, 1.0):
        # Painel AN/SPS-32 frontal/traseiro
        glPushMatrix()
        glTranslatef(-1.1 * z_dir, -0.05, z_dir * 8.64)
        glColor3f(0.28, 0.30, 0.34)
        draw_box(4.80, 3.20, 0.22)
        glColor3f(0.80, 0.82, 0.86)
        glTranslatef(0.0, 0.0, z_dir * 0.08)
        draw_box(4.40, 2.80, 0.12)
        glPopMatrix()

        # Painel AN/SPS-33 vertical frontal/traseiro
        glPushMatrix()
        glTranslatef(2.35 * z_dir, 0.10, z_dir * 8.64)
        glColor3f(0.28, 0.30, 0.34)
        draw_box(2.10, 4.20, 0.22)
        glColor3f(0.82, 0.84, 0.88)
        glTranslatef(0.0, 0.0, z_dir * 0.08)
        draw_box(1.75, 3.80, 0.12)
        glPopMatrix()

    glPopMatrix()  # Fim do Bloco SCANFAR

    # Radomes brancos de comunicação por satélite (OE-82 SATCOM) nos cantos do teto
    for sx, sz in ((-3.2, -11.2), (3.2, -11.2), (-3.2, 3.2)):
        glPushMatrix()
        glTranslatef(sx, 12.35, sz)
        glColor3f(0.38, 0.40, 0.45)
        _draw_cylinder_y(0.32, 0.32, 0.0, 0.75, segments=10, cap_top=True)
        glColor3f(0.92, 0.94, 0.96)
        _draw_cylinder_y(0.58, 0.52, 0.75, 1.65, segments=12, cap_top=True)
        glPopMatrix()

    # ==========================================================================
    # 4. DOMO CÔNICO ESCALONADO "BEEHIVE" ECM
    # ==========================================================================
    glPushMatrix()
    glTranslatef(0.0, 12.2, -5.8)

    # Pedestal cilíndrico de base do domo
    glColor3f(0.45, 0.48, 0.53)
    _draw_cylinder_y(r_bot=3.45, r_top=3.35, y_bot=0.0, y_top=0.85, segments=18, cap_top=True)

    # Corpo cônico principal do Beehive (3 estágios suaves)
    glColor3f(0.56, 0.59, 0.64)
    _draw_cylinder_y(r_bot=3.25, r_top=2.25, y_bot=0.85, y_top=2.45, segments=18, cap_top=False)
    glColor3f(0.62, 0.65, 0.70)
    _draw_cylinder_y(r_bot=2.25, r_top=1.25, y_bot=2.45, y_top=3.95, segments=18, cap_top=False)
    glColor3f(0.68, 0.71, 0.76)
    _draw_cylinder_y(r_bot=1.25, r_top=0.58, y_bot=3.95, y_top=4.75, segments=18, cap_top=True)

    # Os 5 Anéis Horizontais de Antenas ECM (AN/ULQ-6 Slotted Rings)
    glColor3f(0.26, 0.28, 0.32)
    beehive_rings = [
        (1.15, 3.22, 0.22),
        (1.85, 2.76, 0.22),
        (2.55, 2.28, 0.20),
        (3.25, 1.80, 0.18),
        (3.90, 1.35, 0.16),
    ]
    for ry, rr, rh in beehive_rings:
        _draw_cylinder_y(r_bot=rr, r_top=rr * 0.97, y_bot=ry, y_top=ry + rh, segments=18, cap_top=True)

    # Nervuras verticais de guia de ondas nas 4 direções cardeais do Beehive
    glColor3f(0.35, 0.38, 0.42)
    for ang_deg in (0.0, 90.0, 180.0, 270.0):
        glPushMatrix()
        glRotatef(ang_deg, 0.0, 1.0, 0.0)
        _draw_strut_3d([0.0, 1.0, 3.10], [0.0, 4.5, 0.65], thickness=0.14)
        glPopMatrix()

    # Cúpula superior e antena stub no ápice do Beehive
    glColor3f(0.85, 0.87, 0.90)
    _draw_cylinder_y(r_bot=0.42, r_top=0.18, y_bot=4.75, y_top=5.45, segments=12, cap_top=True)
    _draw_cylinder_y(r_bot=0.06, r_top=0.04, y_bot=5.45, y_top=6.30, segments=8, cap_top=True)

    glPopMatrix()  # Fim do Beehive

    # ==========================================================================
    # 5. TORRE DE POPA, RADAR 3D AN/SPS-48 E MASTRO EM TRELIÇA
    # ==========================================================================
    # Torre de suporte do radar e base do mastro imediatamente a ré do bloco SCANFAR
    glColor3f(0.44, 0.47, 0.52)
    glPushMatrix()
    glTranslatef(0.0, 8.8, 7.6)
    draw_box(4.2, 7.2, 5.8)
    glPopMatrix()

    # Pedestal e Radar Planar Rotativo de Busca Aérea 3D AN/SPS-48E (entre o Beehive e o Mastro)
    glPushMatrix()
    glTranslatef(0.0, 12.2, 2.2)
    glColor3f(0.40, 0.43, 0.48)
    _draw_cylinder_y(r_bot=1.10, r_top=0.90, y_bot=0.0, y_top=1.40, segments=12, cap_top=True)
    # Moldura giratória e tela planar quadrada escura do AN/SPS-48
    glPushMatrix()
    glTranslatef(0.0, 2.45, 0.0)
    glRotatef(25.0, 0.0, 1.0, 0.0)
    glRotatef(-12.0, 1.0, 0.0, 0.0)
    glColor3f(0.18, 0.20, 0.24)
    draw_box(3.10, 2.30, 0.28)
    glColor3f(0.32, 0.35, 0.40)
    glTranslatef(0.0, 0.0, -0.18)
    draw_box(2.70, 1.90, 0.14)
    glPopMatrix()
    glPopMatrix()

    # --------------------------------------------------------------------------
    # MASTRO PRINCIPAL EM TRELIÇA PIRAMIDAL DE 4 PERNAS (Y = 12.2 a 28.5)
    # --------------------------------------------------------------------------
    glPushMatrix()
    glTranslatef(0.0, 12.2, 7.8)

    mast_h = 15.8          # Y_rel de 0.0 a 15.8 (Y_world de 22.35 a 38.15)
    w_bot = 1.45           # Meia-largura na base da treliça
    w_top = 0.32           # Meia-largura no topo da treliça
    num_bays = 7

    # 4 Colunas Principais Inclinadas (Corner Legs)
    glColor3f(0.24, 0.26, 0.30)
    for sx in (-1.0, 1.0):
        for sz in (-1.0, 1.0):
            p_base = [sx * w_bot, 0.0, sz * w_bot]
            p_apex = [sx * w_top, mast_h, sz * w_top]
            _draw_strut_3d(p_base, p_apex, thickness=0.18)

    # Travessas Horizontais e Diagonais em "X" nos 7 andares da treliça
    glColor3f(0.28, 0.30, 0.35)
    for b in range(num_bays):
        t0 = b / float(num_bays)
        t1 = (b + 1) / float(num_bays)
        y_a = t0 * mast_h
        y_b = t1 * mast_h
        w_a = w_bot + t0 * (w_top - w_bot)
        w_b = w_bot + t1 * (w_top - w_bot)

        # Anel horizontal no topo do andar
        _draw_strut_3d([-w_b, y_b, -w_b], [ w_b, y_b, -w_b], thickness=0.11)
        _draw_strut_3d([-w_b, y_b,  w_b], [ w_b, y_b,  w_b], thickness=0.11)
        _draw_strut_3d([-w_b, y_b, -w_b], [-w_b, y_b,  w_b], thickness=0.11)
        _draw_strut_3d([ w_b, y_b, -w_b], [ w_b, y_b,  w_b], thickness=0.11)

        # Diagonais nas faces frontal/traseira e laterais
        for s_face in (-1.0, 1.0):
            _draw_strut_3d([-w_a, y_a, s_face * w_a], [ w_b, y_b, s_face * w_b], thickness=0.08)
            _draw_strut_3d([ w_a, y_a, s_face * w_a], [-w_b, y_b, s_face * w_b], thickness=0.08)
            _draw_strut_3d([s_face * w_a, y_a, -w_a], [s_face * w_b, y_b,  w_b], thickness=0.08)

    # 3 Plataformas de Radar em Balanço no Mastro (Forward & Aft Mast Platforms)
    platforms = [
        ( 4.5, 2.4, 3.8, -1.0),   # Plataforma Inferior (Y_world = 26.85)
        ( 9.2, 2.0, 3.2, -0.8),   # Plataforma Média (Y_world = 31.55)
        (13.4, 1.5, 2.6, -0.5),   # Plataforma Superior (Y_world = 35.75)
    ]
    for py_plat, pw_plat, pl_plat, pz_plat in platforms:
        glColor3f(0.34, 0.37, 0.42)
        glPushMatrix()
        glTranslatef(0.0, py_plat, pz_plat)
        draw_box(pw_plat, 0.24, pl_plat)
        # Guarda-corpo da plataforma
        glColor3f(0.25, 0.27, 0.31)
        glTranslatef(0.0, 0.25, -pl_plat * 0.42)
        draw_box(pw_plat * 0.95, 0.28, 0.14)
        glPopMatrix()

    # Radar de Busca de Superfície AN/SPS-10 / SPS-67 na plataforma média
    glColor3f(0.75, 0.78, 0.82)
    glPushMatrix()
    glTranslatef(0.0, 10.1, -2.1)
    glRotatef(-35.0, 0.0, 1.0, 0.0)
    draw_box(2.20, 0.45, 0.22)
    glPopMatrix()

    # Radar de Navegação de Alta Rotação na plataforma superior
    glColor3f(0.88, 0.90, 0.94)
    glPushMatrix()
    glTranslatef(0.0, 14.1, -1.5)
    draw_box(1.65, 0.26, 0.18)
    glPopMatrix()

    # Vergas Horizontais Largas (Yardarms) com Antenas Dipolo nas extremidades
    yardarms = [
        ( 6.8, 8.80, -0.4),   # Verga Principal Larga (span = 8.8m)
        (11.6, 6.20, -0.2),   # Verga Superior (span = 6.2m)
    ]
    for yy, y_span, yz in yardarms:
        glColor3f(0.26, 0.28, 0.32)
        glPushMatrix()
        glTranslatef(0.0, yy, yz)
        draw_box(y_span, 0.20, 0.20)
        # Mãos-francesas diagonais de sustentação da verga
        _draw_strut_3d([-0.8, -1.1, 0.0], [-y_span * 0.38, 0.0, 0.0], thickness=0.09)
        _draw_strut_3d([ 0.8, -1.1, 0.0], [ y_span * 0.38, 0.0, 0.0], thickness=0.09)

        # Antenas verticais de comunicação/ESM nas pontas das vergas
        glColor3f(0.78, 0.80, 0.84)
        for tip_side in (-1.0, 1.0):
            glPushMatrix()
            glTranslatef(tip_side * (y_span * 0.48), 0.75, 0.0)
            draw_box(0.08, 1.50, 0.08)
            glPopMatrix()
            glPushMatrix()
            glTranslatef(tip_side * (y_span * 0.32), 0.55, 0.0)
            draw_box(0.07, 1.10, 0.07)
            glPopMatrix()
        glPopMatrix()

    # Mastro Tubular Superior TACAN / UHF (Y_rel = 15.8 a 19.3 -> Y_world até 41.65)
    glColor3f(0.32, 0.35, 0.40)
    _draw_cylinder_y(r_bot=0.28, r_top=0.10, y_bot=mast_h, y_top=mast_h + 3.4, segments=10, cap_top=True)
    # Tambor cilíndrico branco da antena TACAN no topo
    glColor3f(0.90, 0.92, 0.95)
    _draw_cylinder_y(r_bot=0.36, r_top=0.36, y_bot=mast_h + 2.6, y_top=mast_h + 3.2, segments=12, cap_top=True)

    # Luzes Anticolisão Vermelhas no Topo do Mastro e nas Pontas da Verga Principal
    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    glColor3f(1.0, 0.16, 0.10)
    glPushMatrix()
    glTranslatef(0.0, mast_h + 3.55, 0.0)
    draw_box(0.42, 0.42, 0.42)
    glPopMatrix()
    for tip_s in (-1.0, 1.0):
        glPushMatrix()
        glTranslatef(tip_s * 4.4, 7.65, -0.4)
        draw_box(0.24, 0.24, 0.24)
        glPopMatrix()
    glPopAttrib()

    glPopMatrix()  # Fim do Mastro em Treliça
    glPopMatrix()  # Fim da Ilha


def _draw_cvn65_deck_equipment():
    """
    Desenha os sistemas operacionais do convés do CVN-65:
      - 4 Cabos de Parada (Arresting Gear Wires) na seção traseira da pista.
      - Sistema Óptico de Pouso FLOLS ('Meatball') a bombordo.
      - Passarelas laterais (Catwalks) e defletores de jato.
      - 3 Domas brancas Phalanx CIWS 20mm + Lançadores Sea Sparrow.
      - Guindaste amarelo de convés estacionado a estibordo da Ilha.
    """
    y = CARRIER_DECK_Y

    # 1. Os 4 Cabos de Parada Mk 7 (Arresting Gear Wires) na zona de pouso
    glColor3f(0.20, 0.22, 0.25)
    for z_wire in (42.0, 54.0, 66.0, 78.0):
        glPushMatrix()
        glTranslatef(-2.0, y + 0.04, z_wire)
        draw_box(26.0, 0.05, 0.14)
        glPopMatrix()

    # 2. Sistema Óptico de Pouso FLOLS / "Meatball" a Bombordo
    glPushMatrix()
    glTranslatef(-25.2, y, 28.0)
    glColor3f(0.15, 0.17, 0.20)
    glPushMatrix()
    glTranslatef(0.0, 1.1, 0.0)
    draw_box(2.2, 2.2, 1.2)
    glPopMatrix()
    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    glColor3f(0.15, 1.0, 0.25)
    glPushMatrix()
    glTranslatef(0.0, 1.2, -0.65)
    draw_box(1.9, 0.22, 0.1)
    glPopMatrix()
    glColor3f(1.0, 0.78, 0.10)
    glPushMatrix()
    glTranslatef(0.0, 1.2, -0.68)
    draw_box(0.38, 0.38, 0.1)
    glPopMatrix()
    glPopAttrib()
    glPopMatrix()

    # 3. Defletor de Jato (JBD) elevado na catapulta lateral de estibordo
    glPushMatrix()
    glTranslatef(12.5, y, -45.0)
    glRotatef(-38.0, 1.0, 0.0, 0.0)
    glColor3f(0.30, 0.33, 0.37)
    draw_box(5.2, 2.4, 0.25)
    glPopMatrix()

    # 4. Guindaste Amarelo de Aeronaves a Estibordo da Ilha
    glPushMatrix()
    glTranslatef(17.5, y, 15.0)
    glColor3f(0.85, 0.68, 0.12)
    glPushMatrix()
    glTranslatef(0.0, 1.2, 0.0)
    draw_box(3.2, 2.4, 5.5)
    glTranslatef(0.0, 1.0, 1.5)
    glRotatef(28.0, 1.0, 0.0, 0.0)
    draw_box(0.8, 0.8, 9.5)
    glPopMatrix()
    glPopMatrix()

    # 5. Passarelas de Borda de Convés (Catwalks) e Defesas CIWS
    glColor3f(0.30, 0.33, 0.37)
    glPushMatrix()
    glTranslatef(-27.2, y - 0.45, 0.0)
    draw_box(1.2, 0.7, 130.0)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(25.2, y - 0.45, -10.0)
    draw_box(1.2, 0.7, 150.0)
    glPopMatrix()

    ciws_positions = [
        ( 26.2, y - 0.8, -22.0),
        (-27.8, y - 0.8, -32.0),
        (-20.2, y - 0.8, 108.0),
    ]
    for cx, cy, cz in ciws_positions:
        glPushMatrix()
        glTranslatef(cx, cy, cz)
        glColor3f(0.34, 0.37, 0.42)
        draw_box(2.4, 0.8, 3.2)
        glColor3f(0.92, 0.94, 0.96)
        _draw_cylinder_y(r_bot=0.55, r_top=0.55, y_bot=0.4, y_top=1.8, segments=10, cap_top=True)
        glPopMatrix()


# ==============================================================================
# FUNÇÃO PRINCIPAL DE DESENHO DO PORTA-AVIÕES USS ENTERPRISE (CVN-65)
# ==============================================================================

def draw_cvn65_carrier(deck_tex_id):
    """
    Renderiza o modelo completo do porta-aviões nuclear USS Enterprise (CVN-65):
      1. Casco multi-seção, linha d'água, bulbo de proa, sponsons e 4 elevadores.
      2. Convés de voo assimétrico em Y = 10.15 com UV planar sem distorções.
      3. Superestrutura/Ilha Nuclear SCANFAR + Domo Beehive + Mastro em treliça 3D.
      4. Cabos de parada, FLOLS ('Meatball'), Catwalks, Phalanx CIWS e Guindaste.
    """
    glPushAttrib(GL_TEXTURE_BIT | GL_LIGHTING_BIT | GL_ENABLE_BIT)
    glDisable(GL_TEXTURE_2D)

    # 1. Casco inferior, obra morta, hangares, sponsons e elevadores
    _draw_cvn65_hull_and_sponsons()

    # 2. Pista de pouso texturizada com UV planar sem distorção
    _draw_cvn65_flight_deck_surface(deck_tex_id)

    # 3. Ilha de comando nuclear SCANFAR e Mastro em treliça
    _draw_cvn65_island_superstructure()

    # 4. Equipamentos de convés, cabos de parada, FLOLS e defesas
    _draw_cvn65_deck_equipment()

    glPopAttrib()