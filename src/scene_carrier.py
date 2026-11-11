"""
================================================================================
TopGraphics | scene_carrier.py
Cena 1: Oceano texturizado + Porta-Aviões Nuclear USS Enterprise (CVN-65)
================================================================================
"""

# TODO: remove lighted floats from map
# TODO: implement procedurally generated clouds (semi-transparent vapor, not solid objects)
# TODO: render more of the map as needed or implement a visual map boundary

import math

import numpy as np
from OpenGL.GL import *

from renderer_utils import draw_box, upload_texture_rgb
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
            r = np.clip(12 + wave * 0.4, 5, 45)
            g = np.clip(65 + wave * 0.9, 40, 110)
            b = np.clip(135 + wave * 1.4, 95, 190)
            if x % 32 == 0 or y % 32 == 0:
                r, g, b = min(255, r + 20), min(255, g + 30), min(255, b + 35)
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
    Compila a Cena 1: Oceano amplo texturizado + USS Enterprise (CVN-65) detalhado
    + Luzes de aproximação na popa.
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    # 1. Superfície do Oceano com repetição de textura UV
    glBindTexture(GL_TEXTURE_2D, ocean_tex_id)
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.4, 0.45, 0.5, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 32.0)
    glColor3f(0.85, 0.92, 1.0)

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

    # 3. Boias luminosas de aproximação alinhadas com a rampa de pouso na popa
    glPushAttrib(GL_LIGHTING_BIT | GL_TEXTURE_BIT)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    deck_l = CARRIER_DECK_HALF_L
    for i in range(1, 7):
        glColor3f(0.2, 1.0, 0.3)
        glPushMatrix()
        glTranslatef(-10.0, 10.5, deck_l + i * 35.0)
        draw_box(1.5, 1.5, 1.5)
        glPopMatrix()

        glPushMatrix()
        glTranslatef(10.0, 10.5, deck_l + i * 35.0)
        draw_box(1.5, 1.5, 1.5)
        glPopMatrix()
    glPopAttrib()

    glEndList()
    return dlist