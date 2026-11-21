"""
================================================================================
TopGraphics | scene_inspection.py
Cenário 3: Hangar / Domo de Inspeção Técnica, Aerodinâmica e Customização de Skins.
  - F-14 suspenso em voo estacionário em (0, 15, 0) com Câmera 3 (Orbital 360°) travada.
  - Plataforma tática rebaixada (Y = -12.0, 27m abaixo do caça) e renderizada sem
    escrita no Z-buffer (glDepthMask=GL_FALSE) no disco translúcido, garantindo
    inspeção 360° livre do ventre, mísseis, trem de pouso e air brakes ventrais
    sem jamais obstruir a aeronave (com ou sem zoom).
  - Iluminação de estúdio (Key Light superior + Fill Light inferior) para destacar
    tanto o dorso quanto o ventre e os reflexos metálicos.
  - Painel 2D exclusivo da Cena 3 (ocultável com 'H') para customização de skins [K/P].
================================================================================
"""

import math
from OpenGL.GL import *
from OpenGL.GLU import *

from hud import draw_vector_text, _draw_hud_panel_box

INSPECTION_CENTER_Y = 15.0
INSPECTION_FLOOR_Y = -12.0   # 27m abaixo do F-14: livre de obstrução mesmo em -80° sem zoom!


def apply_inspection_lighting(lighting_enabled=True):
    """
    Configura iluminação de hangar/estúdio para a Cena 3, com Key Light superior
    (GL_LIGHT0) e Fill Light inferior suave (GL_LIGHT2) para iluminar também o
    ventre, mísseis AIM-54, trem de pouso e air brakes ventrais.
    """
    glClearColor(0.05, 0.08, 0.13, 1.0)

    if not lighting_enabled:
        glDisable(GL_LIGHTING)
        return

    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_LIGHT2)

    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.22, 0.24, 0.28, 1.0])

    # Key Light superior frontal-direita
    glLightfv(GL_LIGHT0, GL_POSITION, [0.45, 0.82, 0.35, 0.0])
    glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.36, 0.39, 0.44, 1.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE,  [0.95, 0.94, 0.92, 1.0])
    glLightfv(GL_LIGHT0, GL_SPECULAR, [1.00, 1.00, 1.00, 1.0])

    # Fill Light inferior-oposta suave para inspeção detalhada do ventre do F-14
    glLightfv(GL_LIGHT2, GL_POSITION, [-0.35, -0.75, -0.45, 0.0])
    glLightfv(GL_LIGHT2, GL_AMBIENT,  [0.0, 0.0, 0.0, 1.0])
    glLightfv(GL_LIGHT2, GL_DIFFUSE,  [0.38, 0.42, 0.50, 1.0])
    glLightfv(GL_LIGHT2, GL_SPECULAR, [0.25, 0.28, 0.35, 1.0])


def build_scene3_inspection_list():
    """
    Compila a plataforma tática de referência espacial da Cena 3 em Y = -12.0
    (27m abaixo do F-14 em Y = 15.0), com glDepthMask(GL_FALSE) no piso translúcido
    para que o chão nunca oculte o caça ao girar a câmera por baixo.
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    glPushAttrib(GL_ENABLE_BIT | GL_LINE_BIT | GL_CURRENT_BIT | GL_LIGHTING_BIT | GL_DEPTH_BUFFER_BIT)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LINE_SMOOTH)
    # Mantém teste de profundidade ativo, mas desativa escrita no Z-buffer para que
    # a plataforma translúcida de referência jamais tampe o F-14 em ângulos inferiores!
    glDepthMask(GL_FALSE)

    floor_y = INSPECTION_FLOOR_Y
    center_y = INSPECTION_CENTER_Y

    # 1. Disco escuro translúcido da plataforma de inspeção
    glColor4f(0.04, 0.09, 0.15, 0.48)
    glBegin(GL_TRIANGLE_FAN)
    glVertex3f(0.0, floor_y - 0.02, 0.0)
    segments = 64
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        glVertex3f(30.0 * math.cos(ang), floor_y - 0.02, 30.0 * math.sin(ang))
    glEnd()

    # 2. Grade cartesiana tática sobre a plataforma
    glLineWidth(1.0)
    glColor4f(0.15, 0.55, 0.75, 0.24)
    glBegin(GL_LINES)
    for g in range(-24, 25, 3):
        glVertex3f(float(g), floor_y, -24.0)
        glVertex3f(float(g), floor_y,  24.0)
        glVertex3f(-24.0, floor_y, float(g))
        glVertex3f( 24.0, floor_y, float(g))
    glEnd()

    # 3. Anéis concêntricos de escala métrica (R = 6m, 12m, 18m, 24m, 30m)
    glLineWidth(1.5)
    for radius, alpha in ((6.0, 0.45), (12.0, 0.40), (18.0, 0.35), (24.0, 0.42), (30.0, 0.55)):
        glColor4f(0.20, 0.85, 0.95, alpha)
        glBegin(GL_LINE_LOOP)
        for i in range(72):
            ang = (2.0 * math.pi * i) / 72
            glVertex3f(radius * math.cos(ang), floor_y + 0.01, radius * math.sin(ang))
        glEnd()

    # 4. Eixos de referência primários (X = Envergadura, Z = Comprimento, Y = Prumo)
    glLineWidth(1.8)
    glBegin(GL_LINES)
    # Eixo longitudinal Z (Proa -Z em ciano brilhante)
    glColor4f(0.20, 0.95, 0.65, 0.65)
    glVertex3f(0.0, floor_y + 0.02, -30.0)
    glVertex3f(0.0, floor_y + 0.02,  30.0)
    # Eixo transversal X (Envergadura)
    glColor4f(0.20, 0.75, 0.95, 0.50)
    glVertex3f(-30.0, floor_y + 0.02, 0.0)
    glVertex3f( 30.0, floor_y + 0.02, 0.0)
    # Linha de prumo vertical suave até o centro de massa do F-14 (0, 15, 0)
    glColor4f(0.35, 1.00, 0.65, 0.22)
    glVertex3f(0.0, floor_y, 0.0)
    glVertex3f(0.0, center_y, 0.0)
    glEnd()

    # 5. Anel de horizonte zero ao redor do nível da aeronave (Y = 15.0, R = 15.0)
    glLineWidth(1.2)
    glColor4f(0.22, 0.90, 0.55, 0.28)
    glBegin(GL_LINES)
    for i in range(0, 72, 2):
        a1 = (2.0 * math.pi * i) / 72
        a2 = (2.0 * math.pi * (i + 1)) / 72
        glVertex3f(15.0 * math.cos(a1), center_y, 15.0 * math.sin(a1))
        glVertex3f(15.0 * math.cos(a2), center_y, 15.0 * math.sin(a2))
    glEnd()

    glDepthMask(GL_TRUE)
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
