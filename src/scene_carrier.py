"""
================================================================================
TopGraphics | scene_carrier.py
Cena 1: Oceano texturizado + Porta-Aviões Nuclear USS Enterprise (CVN-65).
Integrado com scene_utils.py (Nascer do Sol e Nuvens de Vapor Procedurais).
================================================================================
"""

import math

import numpy as np
from OpenGL.GL import *

from renderer_utils import upload_texture_rgb
from cvn_65_model import (
    CARRIER_DECK_Y,
    CARRIER_DECK_HALF_W,
    CARRIER_DECK_HALF_L,
    create_cvn65_deck_texture,
    draw_cvn65_carrier,
    is_within_cvn65_deck_polygon,
    check_cvn65_extra_collisions,
)


# ==============================================================================
# TEXTURAS PROCEDURAIS DA CENA 1
# ==============================================================================

def create_ocean_texture():
    """Gera uma textura 128x128 para a superfície do oceano com padrão de ondas."""
    size = 128
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(size):
        for x in range(size):
            wave = (
                math.sin(x * 0.25) * 12
                + math.cos(y * 0.25) * 12
                + math.sin((x + y) * 0.15) * 8
            )
            r = np.clip(16 + wave * 0.5, 8, 52)
            g = np.clip(62 + wave * 0.9, 38, 108)
            b = np.clip(128 + wave * 1.4, 88, 185)
            if x % 32 == 0 or y % 32 == 0:
                r, g, b = min(255, r + 18), min(255, g + 26), min(255, b + 32)
            img[y, x] = [int(r), int(g), int(b)]

    return upload_texture_rgb(img)


def create_deck_texture():
    """Delega a criação da textura de alta resolução do convés do CVN-65."""
    return create_cvn65_deck_texture()


# ==============================================================================
# CONSTRUÇÃO DA CENA 1 (DISPLAY LIST)
# ==============================================================================

def build_scene1_carrier_list(ocean_tex_id, deck_tex_id):
    """
    Compila a Cena 1: Oceano amplo texturizado com reflexo especular para o
    nascer do sol + USS Enterprise (CVN-65) detalhado (boias luminosas removidas).
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    # 1. Superfície do Oceano com repetição de textura UV e brilho especular dourado
    glBindTexture(GL_TEXTURE_2D, ocean_tex_id)
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.65, 0.55, 0.42, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 42.0)
    glColor3f(0.82, 0.88, 0.96)

    grid_size = 2400.0
    step = 120.0
    uv_tile = 2.0
    glBegin(GL_QUADS)
    glNormal3f(0.0, 1.0, 0.0)
    z = -grid_size
    while z < grid_size:
        x = -grid_size
        while x < grid_size:
            glTexCoord2f(0.0, 0.0)
            glVertex3f(x, 0.0, z)
            glTexCoord2f(0.0, uv_tile)
            glVertex3f(x, 0.0, z + step)
            glTexCoord2f(uv_tile, uv_tile)
            glVertex3f(x + step, 0.0, z + step)
            glTexCoord2f(uv_tile, 0.0)
            glVertex3f(x + step, 0.0, z)
            x += step
        z += step
    glEnd()

    # 2. Porta-Aviões USS Enterprise (CVN-65) completo (cvn_65_model.py)
    draw_cvn65_carrier(deck_tex_id)

    glEndList()
    return dlist
