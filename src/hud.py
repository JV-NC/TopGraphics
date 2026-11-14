"""
================================================================================
TopGraphics | hud.py
Sistema Integrado de Aviónica e Head-Up Display (HUD) Tático do F-14 Tomcat.
Renderizado 100% via código em projeção ortográfica 2D (OpenGL), incluindo:
  - Fonte vetorial própria (Stroke Font) sem dependências externas.
  - Bússola deslizante no topo (Heading Tape 000°..359° + pontos cardeais + GPS Lat/Lon).
  - Horizonte Artificial com Escala de Ângulo de Arfagem (Pitch Ladder + Roll Scale).
  - Fitas verticais deslizantes de Velocidade (Knots - kt) e Altitude (Feet - ft).
  - Painéis de Estado de Voo (No Convés / Em Voo / Stall), Throttle e Afterburner (E).
  - Painel Mecânico: Trem de Pouso (Q) com luzes de roda e Asas (G) com diagrama 2D
    dinâmico que acompanha o ângulo de enflecamento em tempo real.
  - Tela de Alerta de Impacto (Game Over) com tipografia vetorial.
================================================================================
"""

import math
import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *


# ==============================================================================
# 1. FONTE VETORIAL TÁTICA (STROKE FONT) — 100% EM OPENGL
# ==============================================================================
# Cada glifo é definido em uma grade normalizada [0.0 .. 1.0] em X e [0.0 .. 1.0] em Y
# como uma lista de segmentos de reta: ((x1, y1), (x2, y2)).

_VECTOR_GLYPHS = {
    "0": [((0.1, 0.0), (0.9, 0.0)), ((0.9, 0.0), (0.9, 1.0)), ((0.9, 1.0), (0.1, 1.0)), ((0.1, 1.0), (0.1, 0.0)), ((0.1, 0.15), (0.9, 0.85))],
    "1": [((0.5, 0.0), (0.5, 1.0)), ((0.25, 0.8), (0.5, 1.0)), ((0.2, 0.0), (0.8, 0.0))],
    "2": [((0.1, 0.85), (0.25, 1.0)), ((0.25, 1.0), (0.75, 1.0)), ((0.75, 1.0), (0.9, 0.85)), ((0.9, 0.85), (0.9, 0.6)), ((0.9, 0.6), (0.1, 0.0)), ((0.1, 0.0), (0.9, 0.0))],
    "3": [((0.1, 1.0), (0.9, 1.0)), ((0.9, 1.0), (0.9, 0.0)), ((0.9, 0.0), (0.1, 0.0)), ((0.3, 0.52), (0.9, 0.52))],
    "4": [((0.15, 1.0), (0.15, 0.45)), ((0.15, 0.45), (0.9, 0.45)), ((0.75, 0.0), (0.75, 1.0))],
    "5": [((0.9, 1.0), (0.1, 1.0)), ((0.1, 1.0), (0.1, 0.55)), ((0.1, 0.55), (0.85, 0.55)), ((0.85, 0.55), (0.9, 0.1)), ((0.9, 0.1), (0.75, 0.0)), ((0.75, 0.0), (0.1, 0.0))],
    "6": [((0.85, 1.0), (0.15, 1.0)), ((0.15, 1.0), (0.1, 0.0)), ((0.1, 0.0), (0.9, 0.0)), ((0.9, 0.0), (0.9, 0.5)), ((0.9, 0.5), (0.1, 0.5))],
    "7": [((0.1, 1.0), (0.9, 1.0)), ((0.9, 1.0), (0.4, 0.0))],
    "8": [((0.1, 0.0), (0.9, 0.0)), ((0.9, 0.0), (0.9, 1.0)), ((0.9, 1.0), (0.1, 1.0)), ((0.1, 1.0), (0.1, 0.0)), ((0.1, 0.52), (0.9, 0.52))],
    "9": [((0.1, 0.0), (0.85, 0.0)), ((0.85, 0.0), (0.9, 1.0)), ((0.9, 1.0), (0.1, 1.0)), ((0.1, 1.0), (0.1, 0.5)), ((0.1, 0.5), (0.9, 0.5))],

    "A": [((0.1, 0.0), (0.1, 0.75)), ((0.1, 0.75), (0.5, 1.0)), ((0.5, 1.0), (0.9, 0.75)), ((0.9, 0.75), (0.9, 0.0)), ((0.1, 0.42), (0.9, 0.42))],
    "B": [((0.1, 0.0), (0.1, 1.0)), ((0.1, 1.0), (0.75, 1.0)), ((0.75, 1.0), (0.9, 0.78)), ((0.9, 0.78), (0.75, 0.52)), ((0.75, 0.52), (0.1, 0.52)), ((0.75, 0.52), (0.9, 0.25)), ((0.9, 0.25), (0.75, 0.0)), ((0.75, 0.0), (0.1, 0.0))],
    "C": [((0.9, 0.85), (0.75, 1.0)), ((0.75, 1.0), (0.2, 1.0)), ((0.2, 1.0), (0.1, 0.85)), ((0.1, 0.85), (0.1, 0.15)), ((0.1, 0.15), (0.2, 0.0)), ((0.2, 0.0), (0.75, 0.0)), ((0.75, 0.0), (0.9, 0.15))],
    "D": [((0.1, 0.0), (0.1, 1.0)), ((0.1, 1.0), (0.68, 1.0)), ((0.68, 1.0), (0.9, 0.75)), ((0.9, 0.75), (0.9, 0.25)), ((0.9, 0.25), (0.68, 0.0)), ((0.68, 0.0), (0.1, 0.0))],
    "E": [((0.9, 1.0), (0.1, 1.0)), ((0.1, 1.0), (0.1, 0.0)), ((0.1, 0.0), (0.9, 0.0)), ((0.1, 0.52), (0.72, 0.52))],
    "F": [((0.9, 1.0), (0.1, 1.0)), ((0.1, 1.0), (0.1, 0.0)), ((0.1, 0.52), (0.72, 0.52))],
    "G": [((0.9, 0.85), (0.75, 1.0)), ((0.75, 1.0), (0.1, 1.0)), ((0.1, 1.0), (0.1, 0.0)), ((0.1, 0.0), (0.9, 0.0)), ((0.9, 0.0), (0.9, 0.48)), ((0.9, 0.48), (0.5, 0.48))],
    "H": [((0.1, 0.0), (0.1, 1.0)), ((0.9, 0.0), (0.9, 1.0)), ((0.1, 0.52), (0.9, 0.52))],
    "I": [((0.2, 1.0), (0.8, 1.0)), ((0.5, 0.0), (0.5, 1.0)), ((0.2, 0.0), (0.8, 0.0))],
    "J": [((0.85, 1.0), (0.85, 0.15)), ((0.85, 0.15), (0.65, 0.0)), ((0.65, 0.0), (0.2, 0.0)), ((0.2, 0.0), (0.1, 0.2))],
    "K": [((0.1, 0.0), (0.1, 1.0)), ((0.9, 1.0), (0.1, 0.5)), ((0.1, 0.5), (0.9, 0.0))],
    "L": [((0.1, 1.0), (0.1, 0.0)), ((0.1, 0.0), (0.9, 0.0))],
    "M": [((0.1, 0.0), (0.1, 1.0)), ((0.1, 1.0), (0.5, 0.45)), ((0.5, 0.45), (0.9, 1.0)), ((0.9, 1.0), (0.9, 0.0))],
    "N": [((0.1, 0.0), (0.1, 1.0)), ((0.1, 1.0), (0.9, 0.0)), ((0.9, 0.0), (0.9, 1.0))],
    "O": [((0.1, 0.0), (0.9, 0.0)), ((0.9, 0.0), (0.9, 1.0)), ((0.9, 1.0), (0.1, 1.0)), ((0.1, 1.0), (0.1, 0.0))],
    "P": [((0.1, 0.0), (0.1, 1.0)), ((0.1, 1.0), (0.85, 1.0)), ((0.85, 1.0), (0.9, 0.75)), ((0.9, 0.75), (0.85, 0.52)), ((0.85, 0.52), (0.1, 0.52))],
    "Q": [((0.1, 0.0), (0.9, 0.0)), ((0.9, 0.0), (0.9, 1.0)), ((0.9, 1.0), (0.1, 1.0)), ((0.1, 1.0), (0.1, 0.0)), ((0.55, 0.3), (0.95, -0.08))],
    "R": [((0.1, 0.0), (0.1, 1.0)), ((0.1, 1.0), (0.85, 1.0)), ((0.85, 1.0), (0.9, 0.75)), ((0.9, 0.75), (0.85, 0.52)), ((0.85, 0.52), (0.1, 0.52)), ((0.5, 0.52), (0.9, 0.0))],
    "S": [((0.9, 0.9), (0.75, 1.0)), ((0.75, 1.0), (0.15, 1.0)), ((0.15, 1.0), (0.1, 0.55)), ((0.1, 0.55), (0.85, 0.5)), ((0.85, 0.5), (0.9, 0.1)), ((0.9, 0.1), (0.75, 0.0)), ((0.75, 0.0), (0.1, 0.0))],
    "T": [((0.05, 1.0), (0.95, 1.0)), ((0.5, 0.0), (0.5, 1.0))],
    "U": [((0.1, 1.0), (0.1, 0.12)), ((0.1, 0.12), (0.25, 0.0)), ((0.25, 0.0), (0.75, 0.0)), ((0.75, 0.0), (0.9, 0.12)), ((0.9, 0.12), (0.9, 1.0))],
    "V": [((0.1, 1.0), (0.5, 0.0)), ((0.5, 0.0), (0.9, 1.0))],
    "W": [((0.08, 1.0), (0.25, 0.0)), ((0.25, 0.0), (0.5, 0.55)), ((0.5, 0.55), (0.75, 0.0)), ((0.75, 0.0), (0.92, 1.0))],
    "X": [((0.1, 0.0), (0.9, 1.0)), ((0.1, 1.0), (0.9, 0.0))],
    "Y": [((0.1, 1.0), (0.5, 0.5)), ((0.9, 1.0), (0.5, 0.5)), ((0.5, 0.5), (0.5, 0.0))],
    "Z": [((0.1, 1.0), (0.9, 1.0)), ((0.9, 1.0), (0.1, 0.0)), ((0.1, 0.0), (0.9, 0.0))],

    "-": [((0.15, 0.5), (0.85, 0.5))],
    "+": [((0.15, 0.5), (0.85, 0.5)), ((0.5, 0.18), (0.5, 0.82))],
    ".": [((0.42, 0.0), (0.58, 0.0)), ((0.58, 0.0), (0.58, 0.14)), ((0.58, 0.14), (0.42, 0.14)), ((0.42, 0.14), (0.42, 0.0))],
    ":": [((0.42, 0.2), (0.58, 0.2)), ((0.42, 0.72), (0.58, 0.72))],
    "/": [((0.15, 0.0), (0.85, 1.0))],
    "%": [((0.15, 0.0), (0.85, 1.0)), ((0.15, 0.75), (0.35, 0.75)), ((0.15, 0.95), (0.35, 0.95)), ((0.65, 0.05), (0.85, 0.05)), ((0.65, 0.25), (0.85, 0.25))],
    "°": [((0.25, 0.72), (0.65, 0.72)), ((0.65, 0.72), (0.65, 1.0)), ((0.65, 1.0), (0.25, 1.0)), ((0.25, 1.0), (0.25, 0.72))],
    "'": [((0.5, 0.72), (0.4, 1.0))],
    "\"": [((0.35, 0.72), (0.28, 1.0)), ((0.65, 0.72), (0.58, 1.0))],
    "[": [((0.65, 0.0), (0.25, 0.0)), ((0.25, 0.0), (0.25, 1.0)), ((0.25, 1.0), (0.65, 1.0))],
    "]": [((0.35, 0.0), (0.75, 0.0)), ((0.75, 0.0), (0.75, 1.0)), ((0.75, 1.0), (0.35, 1.0))],
    "|": [((0.5, 0.0), (0.5, 1.0))],
}

# Mapa de normalização de caracteres acentuados para equivalentes ASCII táticos
_ACCENT_MAP = str.maketrans(
    "ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç",
    "AAAAEEIOOOUCAAAAEEIOOOUC"
)


def draw_vector_text(text, x, y, scale=11.0, align="left", spacing=0.34):
    """
    Desenha uma string usando a fonte vetorial tática (GL_LINES).
      - scale: altura em pixels dos caracteres.
      - align: 'left', 'center' ou 'right'.
    """
    if not text:
        return
    clean_text = text.translate(_ACCENT_MAP).upper()
    char_w = scale * 0.68
    step_x = char_w * (1.0 + spacing)
    total_w = len(clean_text) * step_x - (char_w * spacing)

    if align == "center":
        start_x = x - total_w * 0.5
    elif align == "right":
        start_x = x - total_w
    else:
        start_x = x

    glBegin(GL_LINES)
    cx = start_x
    for ch in clean_text:
        segs = _VECTOR_GLYPHS.get(ch)
        if segs:
            for (x1, y1), (x2, y2) in segs:
                glVertex2f(cx + x1 * char_w, y + y1 * scale)
                glVertex2f(cx + x2 * char_w, y + y2 * scale)
        cx += step_x
    glEnd()


def _draw_hud_panel_box(x0, y0, x1, y1, bg_rgba=(0.02, 0.08, 0.04, 0.42), border_rgba=(0.15, 0.95, 0.38, 0.72), cut=6.0):
    """
    Desenha uma moldura tática chanfrada semitransparente estilo painel militar.
    """
    glColor4f(*bg_rgba)
    glBegin(GL_POLYGON)
    glVertex2f(x0 + cut, y0)
    glVertex2f(x1, y0)
    glVertex2f(x1, y1 - cut)
    glVertex2f(x1 - cut, y1)
    glVertex2f(x0, y1)
    glVertex2f(x0, y0 + cut)
    glEnd()

    glColor4f(*border_rgba)
    glBegin(GL_LINE_LOOP)
    glVertex2f(x0 + cut, y0)
    glVertex2f(x1, y0)
    glVertex2f(x1, y1 - cut)
    glVertex2f(x1 - cut, y1)
    glVertex2f(x0, y1)
    glVertex2f(x0, y0 + cut)
    glEnd()


# ==============================================================================
# 2. COMPONENTES DO HUD: BÚSSOLA / GPS, HORIZONTE ARTIFICIAL, VELOCIDADE E ALTITUDE
# ==============================================================================

_CARDINAL_POINTS = {
    0: "N", 45: "NE", 90: "E", 135: "SE",
    180: "S", 225: "SW", 270: "W", 315: "NW"
}


def _compute_heading_deg(aircraft):
    """
    Calcula o rumo magnético/geográfico (000° a 359°) a partir do vetor forward:
      - Norte (000°) = -Z
      - Leste (090°) = +X
      - Sul   (180°) = +Z
      - Oeste (270°) = -X
    """
    fx = float(aircraft.forward[0])
    fz = float(aircraft.forward[2])
    if abs(fx) < 1e-6 and abs(fz) < 1e-6:
        return 0.0
    hdg = math.degrees(math.atan2(fx, -fz)) % 360.0
    return hdg


def _compute_gps_strings(aircraft, scene_mode):
    """
    Converte as coordenadas (X, Z) do caça em coordenadas geográficas Latitude/Longitude:
      - Cena 1 (Oceano Pacífico / Grupo de Batalha CVN-65): base 32°40'N, 117°30'W
      - Cena 2 (Cânion Tático Top Gun / Fallon Range): base 39°25'N, 118°45'W
    """
    if scene_mode == 1:
        base_lat = 32.6667
        base_lon = 117.5000
    else:
        base_lat = 39.4167
        base_lon = 118.7500

    # Em nosso referencial: -Z avança para o Norte (+Lat), +X avança para o Leste (-Lon no hemisfério W)
    lat = base_lat + (-float(aircraft.pos[2]) / 111111.0)
    lon = base_lon - (float(aircraft.pos[0]) / 92000.0)

    def to_dms(val, pos_hem, neg_hem):
        hem = pos_hem if val >= 0 else neg_hem
        v = abs(val)
        deg = int(v)
        rem = (v - deg) * 60.0
        mins = int(rem)
        secs = int((rem - mins) * 60.0)
        return f"{deg:02d}°{mins:02d}'{secs:02d}\"{hem}"

    return to_dms(lat, "N", "S"), to_dms(lon, "W", "E")


def _draw_compass_and_gps(width, height, aircraft, scene_mode):
    """
    Desenha a Bússola Tática deslizante (Heading Tape) no topo central da tela
    e o painel de coordenadas GPS (Latitude / Longitude).
    """
    cx = width * 0.5
    tape_y = height - 44.0
    tape_half_w = 165.0
    px_per_deg = 4.2

    hdg = _compute_heading_deg(aircraft)
    lat_str, lon_str = _compute_gps_strings(aircraft, scene_mode)

    # Moldura de fundo da fita da bússola
    _draw_hud_panel_box(
        cx - tape_half_w - 6, tape_y - 10,
        cx + tape_half_w + 6, tape_y + 24,
        bg_rgba=(0.01, 0.06, 0.03, 0.45),
        border_rgba=(0.15, 0.95, 0.40, 0.65),
        cut=5.0
    )

    # Recorte com glScissor para que as marcações deslizem suavemente dentro da caixa
    glEnable(GL_SCISSOR_TEST)
    glScissor(int(cx - tape_half_w), int(tape_y - 9), int(2 * tape_half_w), 33)

    glColor4f(0.20, 1.0, 0.42, 0.92)
    glLineWidth(1.5)

    base_deg = int(math.floor(hdg))
    for offset_deg in range(-42, 43):
        d = (base_deg + offset_deg) % 360
        # Diferença angular exata em ponto flutuante
        diff = ((d - hdg + 540.0) % 360.0) - 180.0
        x_pos = cx + diff * px_per_deg

        if d % 5 == 0:
            tick_h = 9.0 if (d % 10 == 0) else 5.0
            glBegin(GL_LINES)
            glVertex2f(x_pos, tape_y - 8.0)
            glVertex2f(x_pos, tape_y - 8.0 + tick_h)
            glEnd()

        if d in _CARDINAL_POINTS:
            glColor4f(0.55, 1.0, 0.65, 1.0)
            draw_vector_text(_CARDINAL_POINTS[d], x_pos, tape_y + 4.0, scale=10.5, align="center")
            glColor4f(0.20, 1.0, 0.42, 0.92)
        elif d % 30 == 0:
            draw_vector_text(f"{d:03d}", x_pos, tape_y + 4.0, scale=8.5, align="center")

    glDisable(GL_SCISSOR_TEST)

    # Marcador central fixo (Lubber Line / Caret) e caixa digital do rumo
    glColor4f(0.35, 1.0, 0.55, 1.0)
    glBegin(GL_TRIANGLES)
    glVertex2f(cx - 6.0, tape_y - 16.0)
    glVertex2f(cx + 6.0, tape_y - 16.0)
    glVertex2f(cx, tape_y - 9.0)
    glEnd()

    # Caixa digital do Rumo (HDG) abaixo da fita e GPS no canto superior direito
    _draw_hud_panel_box(
        cx - 44.0, tape_y - 36.0,
        cx + 44.0, tape_y - 16.0,
        bg_rgba=(0.01, 0.08, 0.03, 0.62),
        border_rgba=(0.25, 1.0, 0.48, 0.85),
        cut=3.0
    )
    glColor4f(0.40, 1.0, 0.58, 1.0)
    draw_vector_text(f"HDG {int(round(hdg)) % 360:03d}°", cx, tape_y - 31.0, scale=9.5, align="center")

    # Coordenadas GPS e Identificação do Mapa no topo direito
    gps_x1 = width - 22.0
    gps_x0 = gps_x1 - 246.0
    gps_y1 = height - 18.0
    gps_y0 = gps_y1 - 46.0
    _draw_hud_panel_box(gps_x0, gps_y0, gps_x1, gps_y1, cut=5.0)

    sector_name = "SECTOR 01: CVN-65 PACIFIC" if scene_mode == 1 else "SECTOR 02: TRENCH CANYON"
    glColor4f(0.25, 1.0, 0.48, 0.95)
    draw_vector_text(sector_name, gps_x0 + 10.0, gps_y1 - 17.0, scale=8.2, align="left")
    glColor4f(0.65, 1.0, 0.78, 0.90)
    draw_vector_text(f"GPS {lat_str} {lon_str}", gps_x0 + 10.0, gps_y0 + 8.0, scale=7.8, align="left")


def _draw_artificial_horizon(width, height, aircraft, camera_mode):
    """
    Desenha o Horizonte Artificial com Escala de Ângulo de Arfagem (Pitch Ladder)
    e Indicador de Inclinação (Bank/Roll Scale) no centro da tela.
    Em câmeras externas (Modo 1 e 3), mantém uma janela central livre (gap) ao redor
    do caça e transparência calibrada para nunca cobrir o modelo 3D do F-14!
    """
    cx, cy = width * 0.5, height * 0.5

    roll_deg = math.degrees(math.atan2(float(aircraft.right[1]), float(aircraft.up[1])))
    pitch_deg = math.degrees(math.asin(np.clip(float(aircraft.forward[1]), -1.0, 1.0)))

    # Ajusta opacidade e espaçamento interno conforme a câmera (Cockpit vs Externa)
    is_cockpit = (camera_mode == 2)
    alpha_main = 0.92 if is_cockpit else 0.62
    inner_gap = 28.0 if is_cockpit else 54.0
    outer_span = 98.0 if is_cockpit else 114.0
    px_per_deg = 4.6

    # 1. Símbolo de Referência da Aeronave (Boresight Waterline '-v-' fixo no centro)
    glColor4f(0.25, 1.0, 0.45, alpha_main)
    glLineWidth(2.0 if is_cockpit else 1.6)

    if is_cockpit:
        # Mira central tática completa no Cockpit
        glBegin(GL_LINES)
        glVertex2f(cx - 22.0, cy); glVertex2f(cx - 7.0, cy)
        glVertex2f(cx + 7.0, cy);  glVertex2f(cx + 22.0, cy)
        glVertex2f(cx, cy - 22.0); glVertex2f(cx, cy - 7.0)
        glVertex2f(cx, cy + 7.0);  glVertex2f(cx, cy + 22.0)
        glEnd()
    else:
        # Marcadores laterais discretos de linha d'água (deixando o F-14 totalmente livre no centro)
        glBegin(GL_LINES)
        glVertex2f(cx - 50.0, cy); glVertex2f(cx - 36.0, cy)
        glVertex2f(cx - 36.0, cy); glVertex2f(cx - 36.0, cy - 5.0)
        glVertex2f(cx + 36.0, cy); glVertex2f(cx + 50.0, cy)
        glVertex2f(cx + 36.0, cy); glVertex2f(cx + 36.0, cy - 5.0)
        glEnd()

    # 2. Janela de recorte (glScissor) para a Escada de Arfagem (Pitch Ladder)
    ladder_half_w = 165.0
    ladder_half_h = 148.0
    glEnable(GL_SCISSOR_TEST)
    glScissor(
        int(cx - ladder_half_w),
        int(cy - ladder_half_h),
        int(2 * ladder_half_w),
        int(2 * ladder_half_h)
    )

    glPushMatrix()
    glTranslatef(cx, cy, 0.0)
    glRotatef(-roll_deg, 0.0, 0.0, 1.0)
    glTranslatef(0.0, -pitch_deg * px_per_deg, 0.0)

    # Linha do Horizonte Real (0 graus)
    glColor4f(0.22, 1.0, 0.45, alpha_main)
    glLineWidth(2.0)
    glBegin(GL_LINES)
    glVertex2f(-outer_span - 24.0, 0.0); glVertex2f(-inner_gap, 0.0)
    glVertex2f( inner_gap, 0.0);         glVertex2f( outer_span + 24.0, 0.0)
    # Pequenos traços verticais nas pontas internas do horizonte
    glVertex2f(-inner_gap, 0.0); glVertex2f(-inner_gap, -6.0)
    glVertex2f( inner_gap, 0.0); glVertex2f( inner_gap, -6.0)
    glEnd()

    # Escada de Ângulos de Arfagem (Pitch Rungs de -80° a +80° em passos de 5°/10°)
    glLineWidth(1.5)
    pitch_steps = [-80, -70, -60, -50, -40, -30, -20, -15, -10, -5, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80]
    for deg in pitch_steps:
        # Só desenha os degraus próximos do pitch atual para máxima limpeza e performance
        if abs(deg - pitch_deg) > 36.0:
            continue

        y_r = deg * px_per_deg
        x_in = inner_gap + 4.0
        x_out = outer_span - (12.0 if abs(deg) % 10 != 0 else 0.0)
        tip_dy = -6.0 if deg > 0 else 6.0  # Pontas apontam em direção ao horizonte (0°)

        glBegin(GL_LINES)
        if deg > 0:
            # Arfagem positiva (subida): linha contínua
            glVertex2f(-x_out, y_r); glVertex2f(-x_in, y_r)
            glVertex2f( x_in,  y_r); glVertex2f( x_out, y_r)
        else:
            # Arfagem negativa (mergulho): linha tracejada em 3 segmentos
            for side in (-1.0, 1.0):
                seg_len = (x_out - x_in) / 5.0
                for s in (0, 2, 4):
                    xa = side * (x_in + s * seg_len)
                    xb = side * (x_in + (s + 1) * seg_len)
                    glVertex2f(xa, y_r); glVertex2f(xb, y_r)

        # Dobras verticais nas extremidades internas de cada degrau
        glVertex2f(-x_in, y_r); glVertex2f(-x_in, y_r + tip_dy)
        glVertex2f( x_in, y_r); glVertex2f( x_in, y_r + tip_dy)
        glEnd()

        # Numeração do ângulo de arfagem nas extremidades externas (a cada 10°)
        if abs(deg) % 10 == 0:
            label = f"{abs(deg)}"
            draw_vector_text(label, -x_out - 6.0, y_r - 4.0, scale=8.0, align="right")
            draw_vector_text(label,  x_out + 6.0, y_r - 4.0, scale=8.0, align="left")

    glPopMatrix()
    glDisable(GL_SCISSOR_TEST)

    # 3. Arco Superior de Escala de Rolagem (Bank Angle Indicator)
    bank_r = ladder_half_h + 10.0
    glColor4f(0.20, 0.95, 0.42, alpha_main * 0.85)
    glLineWidth(1.4)
    glBegin(GL_LINES)
    for b_deg in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
        ang_rad = math.radians(90.0 - b_deg)
        tk_len = 8.0 if (b_deg % 30 == 0 or abs(b_deg) == 45) else 4.5
        ca, sa = math.cos(ang_rad), math.sin(ang_rad)
        glVertex2f(cx + bank_r * ca, cy + bank_r * sa)
        glVertex2f(cx + (bank_r + tk_len) * ca, cy + (bank_r + tk_len) * sa)
    glEnd()

    # Ponteiro móvel do ângulo de rolagem (Roll Pointer)
    clamped_roll = np.clip(roll_deg, -65.0, 65.0)
    ptr_rad = math.radians(90.0 + clamped_roll)
    px_tip = cx + (bank_r - 2.0) * math.cos(ptr_rad)
    py_tip = cy + (bank_r - 2.0) * math.sin(ptr_rad)
    glBegin(GL_TRIANGLES)
    glVertex2f(px_tip, py_tip)
    glVertex2f(px_tip - 4.5, py_tip - 8.0)
    glVertex2f(px_tip + 4.5, py_tip - 8.0)
    glEnd()


def _draw_speed_and_altitude_tapes(width, height, aircraft):
    """
    Desenha as escalas verticais deslizantes de Velocidade (Esquerda, em Knots)
    e Altitude (Direita, em Pés) com leitores digitais destacados.
    """
    cx, cy = width * 0.5, height * 0.5
    tape_h = 220.0
    tape_half_h = tape_h * 0.5

    speed_kt = float(aircraft.speed) * 10.0
    max_kt = float(aircraft.max_speed) * 10.0
    alt_ft = float(aircraft.pos[1]) * 10.0
    vsi_fpm = float(aircraft.forward[1] * aircraft.speed) * 600.0 if not aircraft.on_ground else 0.0

    # ==========================================================================
    # 1. FITA DE VELOCIDADE (ESQUERDA — AIRSPEED IN KNOTS)
    # ==========================================================================
    spd_x = max(92.0, cx - 285.0)
    _draw_hud_panel_box(
        spd_x - 58.0, cy - tape_half_h,
        spd_x + 12.0, cy + tape_half_h,
        bg_rgba=(0.01, 0.06, 0.03, 0.42),
        border_rgba=(0.15, 0.95, 0.40, 0.65),
        cut=5.0
    )

    glColor4f(0.35, 1.0, 0.55, 0.95)
    draw_vector_text("SPD KT", spd_x - 23.0, cy + tape_half_h + 7.0, scale=8.5, align="center")

    # Escala deslizante de velocidade (ticks a cada 20 kt, números a cada 100 kt)
    glEnable(GL_SCISSOR_TEST)
    glScissor(int(spd_x - 57.0), int(cy - tape_half_h + 1), 68, int(tape_h - 2))

    px_per_kt = 0.85
    base_kt = int(math.floor(speed_kt / 20.0) * 20)
    glColor4f(0.20, 1.0, 0.42, 0.88)
    glLineWidth(1.4)

    for k_val in range(max(0, base_kt - 160), base_kt + 180, 20):
        y_pos = cy + (k_val - speed_kt) * px_per_kt
        tk_w = 10.0 if (k_val % 100 == 0) else 5.0
        glBegin(GL_LINES)
        glVertex2f(spd_x + 11.0 - tk_w, y_pos)
        glVertex2f(spd_x + 11.0, y_pos)
        glEnd()
        if k_val % 100 == 0:
            draw_vector_text(f"{k_val}", spd_x - 2.0, y_pos - 4.0, scale=8.0, align="right")

    # Marca vermelha/âmbar de velocidade máxima efetiva na fita
    y_max = cy + (max_kt - speed_kt) * px_per_kt
    if cy - tape_half_h <= y_max <= cy + tape_half_h:
        glColor4f(1.0, 0.65, 0.15, 0.95)
        glBegin(GL_LINES)
        glVertex2f(spd_x - 52.0, y_max)
        glVertex2f(spd_x + 11.0, y_max)
        glEnd()

    glDisable(GL_SCISSOR_TEST)

    # Caixa digital central de leitura da velocidade atual
    _draw_hud_panel_box(
        spd_x - 68.0, cy - 13.0,
        spd_x + 16.0, cy + 13.0,
        bg_rgba=(0.01, 0.10, 0.04, 0.85),
        border_rgba=(0.35, 1.0, 0.55, 1.0),
        cut=4.0
    )
    glColor4f(0.45, 1.0, 0.62, 1.0)
    draw_vector_text(f"{speed_kt:04.0f}", spd_x + 8.0, cy - 5.5, scale=11.0, align="right")

    # Sub-leituras abaixo da fita de velocidade: Limite Máximo Efetivo e Número Mach
    mach_num = speed_kt / 661.5
    glColor4f(0.65, 1.0, 0.75, 0.92)
    draw_vector_text(f"MAX {max_kt:.0f} KT", spd_x - 56.0, cy - tape_half_h - 16.0, scale=8.2, align="left")
    draw_vector_text(f"MACH {mach_num:.2f}", spd_x - 56.0, cy - tape_half_h - 30.0, scale=8.2, align="left")

    # ==========================================================================
    # 2. FITA DE ALTITUDE (DIREITA — ALTIMETER IN FEET)
    # ==========================================================================
    alt_x = min(width - 92.0, cx + 285.0)
    _draw_hud_panel_box(
        alt_x - 12.0, cy - tape_half_h,
        alt_x + 58.0, cy + tape_half_h,
        bg_rgba=(0.01, 0.06, 0.03, 0.42),
        border_rgba=(0.15, 0.95, 0.40, 0.65),
        cut=5.0
    )

    glColor4f(0.35, 1.0, 0.55, 0.95)
    draw_vector_text("ALT FT", alt_x + 23.0, cy + tape_half_h + 7.0, scale=8.5, align="center")

    glEnable(GL_SCISSOR_TEST)
    glScissor(int(alt_x - 11.0), int(cy - tape_half_h + 1), 68, int(tape_h - 2))

    px_per_ft = 0.42
    base_ft = int(math.floor(alt_ft / 50.0) * 50)
    glColor4f(0.20, 1.0, 0.42, 0.88)
    glLineWidth(1.4)

    for a_val in range(max(0, base_ft - 300), base_ft + 350, 50):
        y_pos = cy + (a_val - alt_ft) * px_per_ft
        tk_w = 10.0 if (a_val % 100 == 0) else 5.0
        glBegin(GL_LINES)
        glVertex2f(alt_x - 11.0, y_pos)
        glVertex2f(alt_x - 11.0 + tk_w, y_pos)
        glEnd()
        if a_val % 100 == 0:
            draw_vector_text(f"{a_val}", alt_x + 2.0, y_pos - 4.0, scale=8.0, align="left")

    glDisable(GL_SCISSOR_TEST)

    # Caixa digital central de leitura da altitude atual
    _draw_hud_panel_box(
        alt_x - 16.0, cy - 13.0,
        alt_x + 68.0, cy + 13.0,
        bg_rgba=(0.01, 0.10, 0.04, 0.85),
        border_rgba=(0.35, 1.0, 0.55, 1.0),
        cut=4.0
    )
    glColor4f(0.45, 1.0, 0.62, 1.0)
    draw_vector_text(f"{alt_ft:04.0f}", alt_x - 8.0, cy - 5.5, scale=11.0, align="left")

    # Sub-leituras abaixo da fita de altitude: Razão Vertical (VSI) e Atitude Numérica
    pitch_deg = math.degrees(math.asin(np.clip(float(aircraft.forward[1]), -1.0, 1.0)))
    roll_deg = math.degrees(math.atan2(float(aircraft.right[1]), float(aircraft.up[1])))
    glColor4f(0.65, 1.0, 0.75, 0.92)
    draw_vector_text(f"VSI {vsi_fpm:+05.0f}", alt_x - 10.0, cy - tape_half_h - 16.0, scale=8.2, align="left")
    draw_vector_text(f"P{pitch_deg:+03.0f}° R{roll_deg:+03.0f}°", alt_x - 10.0, cy - tape_half_h - 30.0, scale=8.2, align="left")


# ==============================================================================
# 3. PAINÉIS INFERIORES DE TELEMETRIA E SISTEMAS (STATUS, THROTTLE, AB, TREM, ASAS)
# ==============================================================================

def _draw_bottom_telemetry_panels(width, height, aircraft, sim_time):
    """
    Renderiza os dois painéis inferiores da aeronave:
      - Inferior Esquerdo: Estado da Aeronave (NO CONVÉS / EM VOO / STALL),
        Barra de Throttle (%) e Pós-Combustor (Afterburner [E]).
      - Inferior Direito: Trem de Pouso Retrátil [Q] (com luzes de 3 rodas) e
        Ângulo de Enflecamento das Asas [G] (com silhueta 2D animada do F-14).
    """
    # --------------------------------------------------------------------------
    # PAINEL INFERIOR ESQUERDO: STATUS DE VOO, THROTTLE E AFTERBURNER
    # --------------------------------------------------------------------------
    lx0, ly0 = 22.0, 20.0
    lx1, ly1 = 278.0, 128.0
    _draw_hud_panel_box(lx0, ly0, lx1, ly1, cut=6.0)

    # 1. Estado da Aeronave (NO CONVES vs EM VOO vs ALERTA DE STALL)
    is_stalling = (not aircraft.on_ground) and (aircraft.speed < aircraft.min_flight_speed * 1.05)
    if aircraft.on_ground:
        status_txt = "STATUS: NO CONVES"
        status_col = (0.30, 0.95, 1.0, 1.0)
    elif is_stalling:
        blink = 0.45 + 0.55 * abs(math.sin(sim_time * 8.0))
        status_txt = "ALERTA: STALL / BAIXA VEL"
        status_col = (1.0, 0.28, 0.15, blink)
    else:
        status_txt = "STATUS: EM VOO"
        status_col = (0.30, 1.0, 0.52, 1.0)

    glColor4f(*status_col)
    draw_vector_text(status_txt, lx0 + 12.0, ly1 - 22.0, scale=9.5, align="left")

    # 2. Barra Horizontal de Potência (Throttle W/S)
    thr_pct = int(round(float(aircraft.throttle) * 100.0))
    glColor4f(0.65, 1.0, 0.75, 0.95)
    draw_vector_text(f"THR [W/S]: {thr_pct:03d}%", lx0 + 12.0, ly1 - 48.0, scale=8.5, align="left")

    bar_x0, bar_y0 = lx0 + 12.0, ly1 - 66.0
    bar_w, bar_h = 230.0, 11.0
    glColor4f(0.15, 0.65, 0.30, 0.75)
    glBegin(GL_LINE_LOOP)
    glVertex2f(bar_x0, bar_y0)
    glVertex2f(bar_x0 + bar_w, bar_y0)
    glVertex2f(bar_x0 + bar_w, bar_y0 + bar_h)
    glVertex2f(bar_x0, bar_y0 + bar_h)
    glEnd()

    fill_w = bar_w * float(aircraft.throttle)
    if aircraft.afterburner and aircraft.throttle > 0.02:
        glColor4f(1.0, 0.62, 0.15, 0.90)
    else:
        glColor4f(0.22, 0.95, 0.45, 0.85)
    glBegin(GL_QUADS)
    glVertex2f(bar_x0 + 2.0, bar_y0 + 2.0)
    glVertex2f(bar_x0 + max(2.0, fill_w - 2.0), bar_y0 + 2.0)
    glVertex2f(bar_x0 + max(2.0, fill_w - 2.0), bar_y0 + bar_h - 2.0)
    glVertex2f(bar_x0 + 2.0, bar_y0 + bar_h - 2.0)
    glEnd()

    # 3. Indicador de Pós-Combustor (Afterburner [E])
    if aircraft.afterburner:
        ab_pulse = 0.80 + 0.20 * math.sin(sim_time * 14.0)
        glColor4f(1.0, 0.60, 0.14, ab_pulse)
        draw_vector_text("AB [E]: LIGADO [MAX BOOST]", lx0 + 12.0, ly0 + 12.0, scale=8.8, align="left")
    else:
        glColor4f(0.35, 0.80, 0.48, 0.80)
        draw_vector_text("AB [E]: DESLIGADO [MIL]", lx0 + 12.0, ly0 + 12.0, scale=8.8, align="left")

    # --------------------------------------------------------------------------
    # PAINEL INFERIOR DIREITO: TREM DE POUSO [Q] E GEOMETRIA DAS ASAS [G]
    # --------------------------------------------------------------------------
    rx1 = width - 22.0
    rx0 = rx1 - 268.0
    ry0, ry1 = 20.0, 128.0
    _draw_hud_panel_box(rx0, ry0, rx1, ry1, cut=6.0)

    # 1. Estado do Trem de Pouso Retrátil [Q] + Indicadores de 3 Rodas (Nose + Left/Right Main)
    if aircraft.gear_deploy > 0.95:
        gear_txt = "TREM [Q]: BAIXADO"
        gear_col = (0.28, 1.0, 0.48, 1.0)
    elif aircraft.gear_deploy < 0.05:
        gear_txt = "TREM [Q]: RECOLHIDO"
        gear_col = (0.55, 0.90, 0.68, 0.85)
    else:
        gear_txt = "TREM [Q]: TRANSITO"
        gear_col = (1.0, 0.75, 0.18, 1.0)

    glColor4f(*gear_col)
    draw_vector_text(gear_txt, rx0 + 12.0, ry1 - 24.0, scale=8.8, align="left")

    # Luzes esquemáticas das 3 pernas do trem de pouso (Nariz no topo, Principais na base)
    gx_center = rx0 + 48.0
    gy_center = ry1 - 54.0
    wheel_offsets = [(0.0, 10.0), (-14.0, -6.0), (14.0, -6.0)]
    for wx, wy in wheel_offsets:
        if aircraft.gear_deploy > 0.90:
            glColor4f(0.20, 1.0, 0.40, 0.95)
            glBegin(GL_TRIANGLES)
            glVertex2f(gx_center + wx, gy_center + wy + 5.0)
            glVertex2f(gx_center + wx - 5.0, gy_center + wy - 4.0)
            glVertex2f(gx_center + wx + 5.0, gy_center + wy - 4.0)
            glEnd()
        elif aircraft.gear_deploy > 0.08:
            glColor4f(1.0, 0.72, 0.15, 0.95)
            glBegin(GL_LINE_LOOP)
            glVertex2f(gx_center + wx, gy_center + wy + 5.0)
            glVertex2f(gx_center + wx - 5.0, gy_center + wy - 4.0)
            glVertex2f(gx_center + wx + 5.0, gy_center + wy - 4.0)
            glEnd()
        else:
            glColor4f(0.25, 0.65, 0.38, 0.55)
            glBegin(GL_LINE_LOOP)
            glVertex2f(gx_center + wx - 4.0, gy_center + wy - 2.0)
            glVertex2f(gx_center + wx + 4.0, gy_center + wy - 2.0)
            glVertex2f(gx_center + wx + 4.0, gy_center + wy + 2.0)
            glVertex2f(gx_center + wx - 4.0, gy_center + wy + 2.0)
            glEnd()

    # 2. Enflecamento das Asas [G] + Silhueta 2D Dinâmica do F-14 Tomcat
    sweep_mode_str = "AUTO" if aircraft.auto_wing_sweep else "MAN"
    glColor4f(0.35, 1.0, 0.55, 0.95)
    draw_vector_text(
        f"ASAS [G]: {aircraft.wing_sweep_angle:02.0f}° {sweep_mode_str}",
        rx0 + 12.0, ry0 + 12.0, scale=8.8, align="left"
    )

    # Desenho esquemático 2D do F-14 no lado direito do painel com asas que rotacionam ao vivo
    icon_x = rx1 - 46.0
    icon_y = ry0 + 54.0
    sweep_rad = math.radians(float(aircraft.wing_sweep_angle))

    glColor4f(0.30, 1.0, 0.52, 0.90)
    glLineWidth(1.6)
    glBegin(GL_LINES)
    # Fuselagem e radome na silhueta 2D
    glVertex2f(icon_x, icon_y + 28.0); glVertex2f(icon_x - 5.0, icon_y + 8.0)
    glVertex2f(icon_x, icon_y + 28.0); glVertex2f(icon_x + 5.0, icon_y + 8.0)
    glVertex2f(icon_x - 5.0, icon_y + 8.0); glVertex2f(icon_x - 6.0, icon_y - 22.0)
    glVertex2f(icon_x + 5.0, icon_y + 8.0); glVertex2f(icon_x + 6.0, icon_y - 22.0)
    # Tailerons traseiros
    glVertex2f(icon_x - 6.0, icon_y - 16.0); glVertex2f(icon_x - 15.0, icon_y - 24.0)
    glVertex2f(icon_x + 6.0, icon_y - 16.0); glVertex2f(icon_x + 15.0, icon_y - 24.0)
    glEnd()

    # Asas móveis na silhueta 2D (pivôs em icon_x +- 6, icon_y + 6)
    wing_len = 24.0
    wx_span = wing_len * math.cos(sweep_rad)
    wy_back = wing_len * math.sin(sweep_rad)
    glColor4f(0.55, 1.0, 0.70, 1.0)
    glLineWidth(2.2)
    glBegin(GL_LINES)
    # Asa esquerda
    glVertex2f(icon_x - 5.0, icon_y + 6.0)
    glVertex2f(icon_x - 5.0 - wx_span, icon_y + 6.0 - wy_back)
    # Asa direita
    glVertex2f(icon_x + 5.0, icon_y + 6.0)
    glVertex2f(icon_x + 5.0 + wx_span, icon_y + 6.0 - wy_back)
    glEnd()


# ==============================================================================
# 4. FUNÇÃO PRINCIPAL DO HUD E OVERLAY DE COLISÃO (GAME OVER)
# ==============================================================================

def draw_flight_hud(width, height, aircraft, camera_mode=1, scene_mode=1, sim_time=0.0):
    """
    Renderiza o Head-Up Display (HUD) integrado em todas as câmeras (1, 2 e 3),
    consolidando toda a telemetria da aeronave na tela com estética militar limpa.
    """
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, width, 0, height)

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_LINE_BIT | GL_SCISSOR_BIT | GL_POLYGON_BIT)
    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LINE_SMOOTH)

    # 1. Bússola deslizante (Heading Tape) + Coordenadas GPS no topo
    _draw_compass_and_gps(width, height, aircraft, scene_mode)

    # 2. Horizonte Artificial com Escala de Ângulo de Arfagem (Pitch Ladder)
    _draw_artificial_horizon(width, height, aircraft, camera_mode)

    # 3. Fitas verticais de Velocidade (kt) e Altitude (ft)
    _draw_speed_and_altitude_tapes(width, height, aircraft)

    # 4. Painéis inferiores de Estado, Potência, Afterburner, Trem de Pouso e Asas
    _draw_bottom_telemetry_panels(width, height, aircraft, sim_time)

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


def draw_crash_overlay(width, height, crash_reason="IMPACTO DETECTADO!"):
    """
    Desenha o alerta visual vermelho semitransparente e o banner vetorial de Game Over
    quando ocorre colisão, exibindo o motivo exato na tela.
    """
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, width, 0, height)

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_LINE_BIT | GL_POLYGON_BIT)
    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LINE_SMOOTH)

    # Filtro vermelho translúcido sobre toda a tela
    glColor4f(0.75, 0.08, 0.06, 0.38)
    glBegin(GL_QUADS)
    glVertex2f(0, 0)
    glVertex2f(width, 0)
    glVertex2f(width, height)
    glVertex2f(0, height)
    glEnd()

    cx, cy = width * 0.5, height * 0.5

    # Moldura central de Alerta Crítico
    _draw_hud_panel_box(
        cx - 290.0, cy - 58.0,
        cx + 290.0, cy + 62.0,
        bg_rgba=(0.14, 0.02, 0.02, 0.88),
        border_rgba=(1.0, 0.22, 0.18, 0.98),
        cut=8.0
    )

    glLineWidth(2.2)
    glColor4f(1.0, 0.25, 0.20, 1.0)
    draw_vector_text("[ GAME OVER - AERONAVE PERDIDA ]", cx, cy + 28.0, scale=13.0, align="center")

    glLineWidth(1.8)
    glColor4f(1.0, 0.88, 0.82, 1.0)
    draw_vector_text(str(crash_reason), cx, cy - 4.0, scale=10.0, align="center")

    glLineWidth(1.5)
    glColor4f(1.0, 0.72, 0.30, 0.95)
    draw_vector_text("REINICIANDO AUTOMATICAMENTE OU PRESSIONE [R]", cx, cy - 36.0, scale=8.5, align="center")

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
