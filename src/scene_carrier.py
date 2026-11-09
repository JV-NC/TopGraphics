"""
================================================================================
TopGraphics | scene_carrier.py
Cena 1: oceano texturizado + porta-aviões (USS Enterprise simplificado).
Também exporta as constantes do convés usadas na colisão/pouso (flight_kinematics).
================================================================================
"""

# TODO: implement procedurally generated clouds (semi-transparent vapor, not solid objects)
# TODO: render more of the map as needed or implement a visual map boundary

import math

import numpy as np
from OpenGL.GL import *

from renderer_utils import draw_box, upload_texture_rgb


# ==============================================================================
# CONSTANTES GEOMÉTRICAS DO PORTA-AVIÕES E COLISÃO
# ==============================================================================

CARRIER_DECK_Y = 10.15          # Altura da superfície da pista do porta-aviões
CARRIER_DECK_HALF_W = 24.0      # Meia-largura do convés (-24 a +24 no eixo X)
CARRIER_DECK_HALF_L = 115.0     # Meio-comprimento do convés (-115 a +115 no eixo Z)


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
    """Gera uma textura 256x256 de pista de pouso de porta-aviões com faixas pintadas."""
    size = 256
    img = np.full((size, size, 3), 55, dtype=np.uint8)
    rng = np.random.default_rng(42)
    noise = rng.integers(-8, 9, size=(size, size, 3), dtype=np.int16)
    img = np.clip(img.astype(np.int16) + noise, 35, 80).astype(np.uint8)

    for y in range(size):
        for x in range(size):
            if abs(x - 24) < 4 or abs(x - (size - 24)) < 4:
                img[y, x] = [230, 210, 60]
            if abs(x - size // 2) < 4 and (y // 16) % 2 == 0:
                img[y, x] = [235, 235, 235]
            if abs(x - size // 2 + 28) < 2:
                img[y, x] = [120, 125, 130]

    return upload_texture_rgb(img)


# ==============================================================================
# CONSTRUÇÃO DA CENA 1 (DISPLAY LIST)
# ==============================================================================

def build_scene1_carrier_list(ocean_tex_id, deck_tex_id):
    """
    Compila a Cena 1: Oceano amplo texturizado + Porta-Aviões USS Enterprise (CVN-65).
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

    # 2. Casco do Porta-Aviões (USS Enterprise) centrado na origem (0, 0, 0)
    glDisable(GL_TEXTURE_2D)
    glColor3f(0.32, 0.34, 0.38)
    glPushMatrix()
    glTranslatef(0.0, 5.0, 0.0)
    draw_box(36.0, 10.0, 220.0)
    glPopMatrix()

    # 3. Convés de Voo (Flight Deck) com textura UV de pista
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, deck_tex_id)
    glColor3f(0.95, 0.95, 0.95)
    deck_w = CARRIER_DECK_HALF_W
    deck_l = CARRIER_DECK_HALF_L
    deck_y = CARRIER_DECK_Y
    glBegin(GL_QUADS)
    glNormal3f(0.0, 1.0, 0.0)
    glTexCoord2f(0.0, 0.0)
    glVertex3f(-deck_w, deck_y, -deck_l)
    glTexCoord2f(0.0, 6.0)
    glVertex3f(-deck_w, deck_y, deck_l)
    glTexCoord2f(1.0, 6.0)
    glVertex3f(deck_w, deck_y, deck_l)
    glTexCoord2f(1.0, 0.0)
    glVertex3f(deck_w, deck_y, -deck_l)
    glEnd()

    # 4. Superestrutura / Ilha de Comando ("Island") a estibordo (+X)
    glDisable(GL_TEXTURE_2D)
    glColor3f(0.45, 0.47, 0.52)
    glPushMatrix()
    glTranslatef(16.5, 17.5, -15.0)
    draw_box(7.0, 15.0, 28.0)

    glColor3f(0.20, 0.22, 0.25)
    glTranslatef(0.0, 11.0, 0.0)
    draw_box(2.2, 8.0, 4.0)
    glPopMatrix()

    # 5. Boias luminosas de aproximação na popa do porta-aviões
    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
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
