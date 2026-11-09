"""
================================================================================
TopGraphics | renderer_utils.py
Utilitários de renderização compartilhados: upload de texturas, iluminação (Phong),
primitivas com normal automática (quad, triângulo, caixa) e overlays 2D (HUD / Game Over).
================================================================================
"""

# TODO: implement textures in assets

import math

import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *

from math_utils import compute_normal


# ==============================================================================
# TEXTURAS
# ==============================================================================

def upload_texture_rgb(img):
    """
    Envia uma imagem RGB (numpy uint8, shape (altura, largura, 3)) ao OpenGL como
    textura 2D repetível (GL_REPEAT) com filtragem linear e devolve o id da textura.
    """
    height, width = img.shape[:2]
    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, width, height, 0, GL_RGB, GL_UNSIGNED_BYTE, img)
    return tex_id


# ==============================================================================
# ILUMINAÇÃO
# ==============================================================================

def setup_lighting():
    """Configura o modelo de iluminação de Phong/Gouraud."""
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)  # Luz 0: Sol Direcional
    glEnable(GL_LIGHT1)  # Luz 1: Brilho dinâmico dos pós-combustores do F-14

    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    glShadeModel(GL_SMOOTH)
    glEnable(GL_NORMALIZE)

    glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.28, 0.26, 0.30, 1.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE,  [1.00, 0.88, 0.72, 1.0])
    glLightfv(GL_LIGHT0, GL_SPECULAR, [1.00, 0.95, 0.85, 1.0])

    glLightfv(GL_LIGHT1, GL_AMBIENT,  [0.0, 0.0, 0.0, 1.0])
    glLightfv(GL_LIGHT1, GL_DIFFUSE,  [1.0, 0.55, 0.15, 1.0])
    glLightfv(GL_LIGHT1, GL_SPECULAR, [1.0, 0.70, 0.30, 1.0])
    glLightf(GL_LIGHT1, GL_CONSTANT_ATTENUATION, 1.0)
    glLightf(GL_LIGHT1, GL_LINEAR_ATTENUATION, 0.04)
    glLightf(GL_LIGHT1, GL_QUADRATIC_ATTENUATION, 0.008)


# ==============================================================================
# PRIMITIVAS COM NORMAL E UV AUTOMÁTICOS
# ==============================================================================

def draw_quad_with_normal(p1, p2, p3, p4, uv_scale=1.0):
    """Desenha um quadrilátero calculando automaticamente seu vetor normal e coordenadas UV."""
    n = compute_normal(p1, p2, p3)
    glNormal3fv(n)
    glTexCoord2f(0.0, 0.0)
    glVertex3fv(p1)
    glTexCoord2f(uv_scale, 0.0)
    glVertex3fv(p2)
    glTexCoord2f(uv_scale, uv_scale)
    glVertex3fv(p3)
    glTexCoord2f(0.0, uv_scale)
    glVertex3fv(p4)


def draw_tri_with_normal(p1, p2, p3):
    """Desenha um triângulo calculando seu vetor normal unitário."""
    n = compute_normal(p1, p2, p3)
    glNormal3fv(n)
    glTexCoord2f(0.0, 0.0)
    glVertex3fv(p1)
    glTexCoord2f(1.0, 0.0)
    glVertex3fv(p2)
    glTexCoord2f(0.5, 1.0)
    glVertex3fv(p3)


def draw_box(dx, dy, dz, uv_scale=1.0):
    """Desenha um paralelepípedo centrado na origem com dimensões (dx, dy, dz)."""
    hx, hy, hz = dx * 0.5, dy * 0.5, dz * 0.5
    glBegin(GL_QUADS)
    draw_quad_with_normal([-hx, hy, -hz], [-hx, hy, hz], [hx, hy, hz], [hx, hy, -hz], uv_scale)
    draw_quad_with_normal([-hx, -hy, hz], [-hx, -hy, -hz], [hx, -hy, -hz], [hx, -hy, hz], uv_scale)
    draw_quad_with_normal([hx, -hy, -hz], [-hx, -hy, -hz], [-hx, hy, -hz], [hx, hy, -hz], uv_scale)
    draw_quad_with_normal([-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz], uv_scale)
    draw_quad_with_normal([hx, -hy, hz], [hx, -hy, -hz], [hx, hy, -hz], [hx, hy, hz], uv_scale)
    draw_quad_with_normal([-hx, -hy, -hz], [-hx, -hy, hz], [-hx, hy, hz], [-hx, hy, -hz], uv_scale)
    glEnd()


# ==============================================================================
# HUD DO COCKPIT E OVERLAY DE COLISÃO / GAME OVER
# ==============================================================================

def draw_cockpit_hud(width, height, aircraft):
    """
    Desenha um Head-Up Display (HUD) verde tático em projeção ortográfica 2D
    quando o usuário está na Câmera 2 (Cockpit / Primeira Pessoa).
    """
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, width, 0, height)

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glPushAttrib(GL_ENABLE_BIT | GL_LINE_BIT)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)

    cx, cy = width * 0.5, height * 0.5
    glColor3f(0.15, 1.0, 0.25)
    glLineWidth(2.0)

    # Retículo central de mira
    glBegin(GL_LINES)
    glVertex2f(cx - 25, cy); glVertex2f(cx - 8, cy)
    glVertex2f(cx + 8, cy);  glVertex2f(cx + 25, cy)
    glVertex2f(cx, cy - 25); glVertex2f(cx, cy - 8)
    glVertex2f(cx, cy + 8);  glVertex2f(cx, cy + 25)
    glEnd()

    # Horizonte Artificial
    roll_angle = math.degrees(math.atan2(aircraft.right[1], aircraft.up[1]))
    pitch_angle = math.degrees(math.asin(np.clip(aircraft.forward[1], -1.0, 1.0)))

    glPushMatrix()
    glTranslatef(cx, cy, 0.0)
    glRotatef(-roll_angle, 0.0, 0.0, 1.0)
    glTranslatef(0.0, -pitch_angle * 4.5, 0.0)

    glBegin(GL_LINES)
    glVertex2f(-120, 0); glVertex2f(-35, 0)
    glVertex2f(35, 0);   glVertex2f(120, 0)
    for deg in (-30, -20, -10, 10, 20, 30):
        y_off = deg * 4.5
        glVertex2f(-55, y_off); glVertex2f(-25, y_off)
        glVertex2f(25, y_off);  glVertex2f(55, y_off)
    glEnd()
    glPopMatrix()

    # Barra de Potência (Throttle) à esquerda
    glBegin(GL_LINE_LOOP)
    glVertex2f(cx - 240, cy - 100)
    glVertex2f(cx - 220, cy - 100)
    glVertex2f(cx - 220, cy + 100)
    glVertex2f(cx - 240, cy + 100)
    glEnd()

    fill_h = 200.0 * aircraft.throttle
    glBegin(GL_QUADS)
    glVertex2f(cx - 238, cy - 98)
    glVertex2f(cx - 222, cy - 98)
    glVertex2f(cx - 222, cy - 98 + fill_h)
    glVertex2f(cx - 238, cy - 98 + fill_h)
    glEnd()

    # Indicador luminoso de Trem de Pouso no HUD (Verde abaixo da mira quando baixado)
    if aircraft.gear_deploy > 0.5:
        glColor3f(0.2, 1.0, 0.2)
        glBegin(GL_TRIANGLES)
        glVertex2f(cx - 12, cy - 125)
        glVertex2f(cx + 12, cy - 125)
        glVertex2f(cx, cy - 145)
        glEnd()

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


def draw_crash_overlay(width, height):
    """
    Desenha um alerta visual vermelho semitransparente na tela quando ocorre Game Over/Colisão.
    """
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, width, 0, height)

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_LINE_BIT)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    # Filtro vermelho translúcido sobre toda a tela
    glColor4f(0.85, 0.10, 0.08, 0.42)
    glBegin(GL_QUADS)
    glVertex2f(0, 0)
    glVertex2f(width, 0)
    glVertex2f(width, height)
    glVertex2f(0, height)
    glEnd()

    # Grande 'X' vermelho de impacto no centro da tela
    cx, cy = width * 0.5, height * 0.5
    glColor4f(1.0, 0.2, 0.15, 0.95)
    glLineWidth(5.0)
    glBegin(GL_LINES)
    glVertex2f(cx - 80, cy - 80); glVertex2f(cx + 80, cy + 80)
    glVertex2f(cx - 80, cy + 80); glVertex2f(cx + 80, cy - 80)
    glEnd()

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
