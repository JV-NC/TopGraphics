"""
================================================================================
TopGraphics | scene_inspection.py
Cenário 3: Hangar / Domo de Inspeção Técnica, Aerodinâmica e Customização de Skins.
  - F-14 suspenso em voo estacionário em (0, 15, 0) com Câmera 3 (Orbital 360°) travada.
  - Grade tática polar de referência espacial e iluminação de estúdio para destacar
    tanto pinturas foscas quanto reflexos metálicos.
  - Painel 2D exclusivo da Cena 3 (ocultável com 'H') para customização de skins [K/P].
================================================================================
"""

import math
from OpenGL.GL import *
from OpenGL.GLU import *

from hud import draw_vector_text, _draw_hud_panel_box


def apply_inspection_lighting(lighting_enabled=True):
    """
    Configura iluminação de hangar/estúdio para a Cena 3, garantindo excelente
    visibilidade do dorso, ventre e reflexos especulares das skins metálicas.
    """
    glClearColor(0.05, 0.08, 0.13, 1.0)

    if not lighting_enabled:
        glDisable(GL_LIGHTING)
        return

    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)

    # Luz principal clara (Key Light superior frontal-direita + Ambient reforçado para o ventre)
    glLightfv(GL_LIGHT0, GL_POSITION, [0.45, 0.82, 0.35, 0.0])
    glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.42, 0.45, 0.50, 1.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE,  [0.98, 0.97, 0.95, 1.0])
    glLightfv(GL_LIGHT0, GL_SPECULAR, [1.00, 1.00, 1.00, 1.0])


def build_scene3_inspection_list():
    """
    Compila a plataforma tática de referência espacial da Cena 3 (posicionada abaixo
    do caça em Y = 8.5, enquanto o F-14 flutua em Y = 15.0) + anel giroscópico sutil.
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    glPushAttrib(GL_ENABLE_BIT | GL_LINE_BIT | GL_CURRENT_BIT | GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LINE_SMOOTH)

    floor_y = 8.5
    center_y = 15.0

    # 1. Disco escuro translúcido da plataforma de inspeção
    glColor4f(0.04, 0.09, 0.15, 0.65)
    glBegin(GL_TRIANGLE_FAN)
    glVertex3f(0.0, floor_y - 0.02, 0.0)
    segments = 64
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        glVertex3f(26.0 * math.cos(ang), floor_y - 0.02, 26.0 * math.sin(ang))
    glEnd()

    # 2. Grade cartesiana tática sobre a plataforma
    glLineWidth(1.0)
    glColor4f(0.15, 0.55, 0.75, 0.25)
    glBegin(GL_LINES)
    for g in range(-20, 21, 2):
        glVertex3f(float(g), floor_y, -20.0)
        glVertex3f(float(g), floor_y,  20.0)
        glVertex3f(-20.0, floor_y, float(g))
        glVertex3f( 20.0, floor_y, float(g))
    glEnd()

    # 3. Anéis concêntricos de escala métrica (R = 6m, 12m, 18m, 24m)
    glLineWidth(1.6)
    for radius, alpha in ((6.0, 0.55), (12.0, 0.45), (18.0, 0.35), (24.0, 0.60)):
        glColor4f(0.20, 0.85, 0.95, alpha)
        glBegin(GL_LINE_LOOP)
        for i in range(72):
            ang = (2.0 * math.pi * i) / 72
            glVertex3f(radius * math.cos(ang), floor_y + 0.01, radius * math.sin(ang))
        glEnd()

    # 4. Eixos de referência primários (X = Envergadura, Z = Comprimento Longitudinal, Y = Prumo)
    glLineWidth(2.0)
    glBegin(GL_LINES)
    # Eixo longitudinal Z (Proa -Z em ciano brilhante)
    glColor4f(0.20, 0.95, 0.65, 0.70)
    glVertex3f(0.0, floor_y + 0.02, -24.0)
    glVertex3f(0.0, floor_y + 0.02,  24.0)
    # Eixo transversal X (Envergadura)
    glColor4f(0.20, 0.75, 0.95, 0.55)
    glVertex3f(-24.0, floor_y + 0.02, 0.0)
    glVertex3f( 24.0, floor_y + 0.02, 0.0)
    # Linha de prumo vertical até o centro de massa do F-14 (0, 15, 0)
    glColor4f(0.35, 1.00, 0.65, 0.35)
    glVertex3f(0.0, floor_y, 0.0)
    glVertex3f(0.0, center_y, 0.0)
    glEnd()

    # 5. Anel de horizonte zero ao redor do nível da aeronave (Y = 15.0, R = 14.0)
    glLineWidth(1.2)
    glColor4f(0.22, 0.90, 0.55, 0.28)
    glBegin(GL_LINES)
    for i in range(0, 72, 2):
        a1 = (2.0 * math.pi * i) / 72
        a2 = (2.0 * math.pi * (i + 1)) / 72
        glVertex3f(14.0 * math.cos(a1), center_y, 14.0 * math.sin(a1))
        glVertex3f(14.0 * math.cos(a2), center_y, 14.0 * math.sin(a2))
    glEnd()

    glPopAttrib()
    glEndList()
    return dlist


def draw_inspection_overlay(width, height, aircraft, skin_manager, scene_mode=3):
    """
    Desenha o painel superior esquerdo de Customização de Skins EXCLUSIVAMENTE
    quando o usuário está na Cena 3 (Modo de Inspeção).
    """
    if scene_mode != 3 or skin_manager is None:
        return

    pat_name, pal_name, swatches = skin_manager.get_hud_summary()

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

    # Painel de Customização de Skin no canto superior esquerdo (exclusivo da Cena 3)
    px0, py1 = 22.0, height - 18.0
    px1, py0 = 368.0, height - 134.0
    _draw_hud_panel_box(px0, py0, px1, py1, cut=6.0)

    glLineWidth(1.6)
    glColor4f(0.35, 1.0, 0.58, 1.0)
    draw_vector_text("CUSTOMIZACAO DE SKIN [K / P]", px0 + 12.0, py1 - 20.0, scale=9.0, align="left")

    glColor4f(0.80, 1.0, 0.88, 0.95)
    draw_vector_text(f"SKIN [K]: {pat_name}", px0 + 12.0, py1 - 42.0, scale=8.0, align="left")
    draw_vector_text(f"PALETA [P]: {pal_name}", px0 + 12.0, py1 - 62.0, scale=7.8, align="left")

    # Se for camuflagem, desenha as 4 amostras de cores da paleta ativa (R, G, B, K mapeados)
    if swatches is not None:
        channel_labels = ["R", "G", "B", "K"]
        glColor4f(0.55, 0.95, 0.70, 0.90)
        draw_vector_text("CANAIS SUBSTITUIDOS:", px0 + 12.0, py0 + 14.0, scale=7.5, align="left")
        for idx, rgb in enumerate(swatches):
            bx = px0 + 178.0 + idx * 42.0
            by = py0 + 10.0
            glColor4f(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, 0.95)
            glBegin(GL_QUADS)
            glVertex2f(bx, by)
            glVertex2f(bx + 22.0, by)
            glVertex2f(bx + 22.0, by + 16.0)
            glVertex2f(bx, by + 16.0)
            glEnd()
            glColor4f(0.30, 1.0, 0.55, 0.90)
            glBegin(GL_LINE_LOOP)
            glVertex2f(bx, by)
            glVertex2f(bx + 22.0, by)
            glVertex2f(bx + 22.0, by + 16.0)
            glVertex2f(bx, by + 16.0)
            glEnd()
            draw_vector_text(channel_labels[idx], bx + 26.0, by + 4.0, scale=7.2, align="left")
    else:
        glColor4f(0.55, 0.95, 0.70, 0.85)
        draw_vector_text("PRESSIONE [K] PARA MUDAR PADRAO", px0 + 12.0, py0 + 14.0, scale=7.6, align="left")

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)