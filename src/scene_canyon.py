"""
================================================================================
TopGraphics | scene_canyon.py
Cena 2: cânion procedural ("Trench Run"). Contém a função matemática do terreno
(usada na malha 3D e na colisão exata com a rocha) e o bunker alvo.
================================================================================
"""

# TODO: implement procedurally generated rocks for scenario 2 (use same texture and has colision)
# TODO: render more of the map as needed or implement a visual map boundary

import math

import numpy as np
from OpenGL.GL import *

from math_utils import compute_normal
from renderer_utils import draw_box, upload_texture_rgb


# ==============================================================================
# FUNÇÃO DE TERRENO DO CÂNION
# ==============================================================================

CANYON_BUNKER_Z = -1150.0   # Posição Z do bunker alvo no final do cânion


def canyon_center_x(z):
    """Coordenada X do eixo central sinuoso do cânion na profundidade z."""
    return 55.0 * math.sin(z * 0.0045) + 25.0 * math.cos(z * 0.011)


def canyon_height_func(x, z):
    """
    Função matemática f(x, z) que esculpe um corredor sinuoso ("Trench Run")
    com fundo plano navegável e paredões rochosos escarpados nas laterais.
    Usada tanto para gerar a malha 3D quanto para checar colisão exata com a rocha.
    """
    center_x = canyon_center_x(z)
    dist = abs(x - center_x)

    canyon_wall = max(0.0, dist - 42.0)
    wall_height = min(165.0, (canyon_wall ** 1.35) * 0.65)

    roughness = (
        14.0 * math.sin(x * 0.045) * math.cos(z * 0.045)
        + 7.0 * math.sin(x * 0.11 + z * 0.09)
    )
    if dist < 42.0:
        return 2.0 + 1.2 * math.sin(x * 0.08) * math.cos(z * 0.08)
    return max(2.0, wall_height + roughness)


# ==============================================================================
# TEXTURA PROCEDURAL DA CENA 2
# ==============================================================================

def create_canyon_texture():
    """Gera uma textura estratificada de rocha sedimentar/arenito para o cânion."""
    size = 128
    img = np.zeros((size, size, 3), dtype=np.uint8)
    for y in range(size):
        strata = math.sin(y * 0.22) * 18 + math.cos(y * 0.08) * 14
        for x in range(size):
            grain = math.sin(x * 0.35 + y * 0.15) * 8
            r = np.clip(155 + strata + grain, 90, 215)
            g = np.clip(105 + strata * 0.7 + grain, 60, 165)
            b = np.clip(72 + strata * 0.5 + grain, 40, 120)
            img[y, x] = [int(r), int(g), int(b)]

    return upload_texture_rgb(img)


# ==============================================================================
# CONSTRUÇÃO DA CENA 2 (DISPLAY LIST)
# ==============================================================================

def build_scene2_canyon_list(canyon_tex_id):
    """
    Compila a Cena 2: Cânion Procedural ("Trench Run" de Top Gun: Maverick)
    com cálculo de normais em cada face e um Bunker Alvo no final.
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    glBindTexture(GL_TEXTURE_2D, canyon_tex_id)
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.15, 0.12, 0.10, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 10.0)

    x_min, x_max, dx = -360.0, 360.0, 18.0
    z_min, z_max, dz = -1400.0, 500.0, 20.0

    xs = np.arange(x_min, x_max + dx, dx)
    zs = np.arange(z_min, z_max + dz, dz)

    heights = np.zeros((len(xs), len(zs)), dtype=np.float32)
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            heights[i, j] = canyon_height_func(x, z)

    glBegin(GL_TRIANGLES)
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            x0, x1 = xs[i], xs[i + 1]
            z0, z1 = zs[j], zs[j + 1]
            y00, y10 = heights[i, j], heights[i + 1, j]
            y01, y11 = heights[i, j + 1], heights[i + 1, j + 1]

            p00 = [x0, y00, z0]
            p10 = [x1, y10, z0]
            p01 = [x0, y01, z1]
            p11 = [x1, y11, z1]

            avg_y = 0.25 * (y00 + y10 + y01 + y11)
            if avg_y < 6.0:
                glColor3f(0.45, 0.42, 0.38)
            elif avg_y < 85.0:
                glColor3f(0.88, 0.68, 0.52)
            else:
                glColor3f(0.95, 0.85, 0.75)

            n1 = compute_normal(p00, p01, p11)
            glNormal3fv(n1)
            glTexCoord2f(0.0, 0.0); glVertex3fv(p00)
            glTexCoord2f(0.0, 1.0); glVertex3fv(p01)
            glTexCoord2f(1.0, 1.0); glVertex3fv(p11)

            n2 = compute_normal(p00, p11, p10)
            glNormal3fv(n2)
            glTexCoord2f(0.0, 0.0); glVertex3fv(p00)
            glTexCoord2f(1.0, 1.0); glVertex3fv(p11)
            glTexCoord2f(1.0, 0.0); glVertex3fv(p10)
    glEnd()

    target_z = CANYON_BUNKER_Z
    target_x = canyon_center_x(target_z)
    glDisable(GL_TEXTURE_2D)
    glPushMatrix()
    glTranslatef(target_x, 8.0, target_z)
    glColor3f(0.35, 0.38, 0.40)
    draw_box(22.0, 12.0, 22.0)

    glPushAttrib(GL_LIGHTING_BIT)
    glDisable(GL_LIGHTING)
    glColor3f(1.0, 0.15, 0.15)
    glTranslatef(0.0, 6.2, 0.0)
    draw_box(10.0, 0.5, 10.0)
    glPopAttrib()
    glPopMatrix()

    glEndList()
    return dlist
