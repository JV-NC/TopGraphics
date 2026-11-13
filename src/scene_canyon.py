"""
================================================================================
TopGraphics | scene_canyon.py
Cena 2: cânion procedural ("Trench Run"), usando sandstone.png em toda a cena.
  - Exporta a função matemática do terreno e a checagem de colisão com as rochas.
================================================================================
"""

import math

import numpy as np
from OpenGL.GL import *

from math_utils import compute_normal
from renderer_utils import draw_box, upload_texture_rgb, load_texture_from_assets


# ==============================================================================
# CONSTANTES DO TERRENO
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


def _generate_canyon_boulders():
    """
    Gera de forma determinística (seed fixo) a lista de rochas/matacões 3D
    distribuídos ao longo do leito e das encostas do cânion (entre Z = +230 e Z = -1050),
    mantendo a zona inicial de voo (Z > 260) e o corredor central navegáveis.
    """
    rng = np.random.default_rng(77)
    boulders = []

    for z_base in np.linspace(230.0, -1050.0, 34):
        z = float(z_base + rng.uniform(-12.0, 12.0))
        cx = canyon_center_x(z)

        side = -1.0 if (len(boulders) % 2 == 0) else 1.0
        lateral_offset = float(rng.uniform(14.0, 38.0)) * side
        if len(boulders) % 4 == 2:
            lateral_offset = float(rng.uniform(-12.0, 12.0))

        bx = cx + lateral_offset
        by = canyon_height_func(bx, z) - 0.8

        rx = float(rng.uniform(5.5, 11.5))
        ry = float(rng.uniform(6.0, 16.5))
        rz = float(rng.uniform(5.5, 11.5))
        yaw = float(rng.uniform(0.0, 360.0))

        boulders.append({
            "x": bx,
            "y_base": by,
            "z": z,
            "rx": rx,
            "ry": ry,
            "rz": rz,
            "yaw": yaw,
            "seed": int(rng.integers(1000, 99999)),
        })

    return boulders


CANYON_ROCK_OBSTACLES = _generate_canyon_boulders()


def check_canyon_rock_collisions(pos, right_vec=None, forward_vec=None):
    """
    Verifica se o caça (centro, pontas das asas ou nariz) colidiu com alguma
    das rochas procedurais 3D do Cenário 2.
    Retorna (True, motivo_str) em caso de impacto, ou (False, "") caso contrário.
    """
    sample_points = [pos]
    if right_vec is not None:
        sample_points.append(pos + right_vec * 4.5)
        sample_points.append(pos - right_vec * 4.5)
    if forward_vec is not None:
        sample_points.append(pos + forward_vec * 4.8)

    for pt in sample_points:
        px, py, pz = float(pt[0]), float(pt[1]), float(pt[2])
        for b in CANYON_ROCK_OBSTACLES:
            if abs(pz - b["z"]) > (b["rz"] + 2.5):
                continue
            if abs(px - b["x"]) > (b["rx"] + 2.5):
                continue
            if py > (b["y_base"] + b["ry"] + 1.2) or py < (b["y_base"] - 1.0):
                continue

            dx = (px - b["x"]) / max(1.0, b["rx"] * 0.92)
            dy = (py - (b["y_base"] + b["ry"] * 0.38)) / max(1.0, b["ry"] * 0.68)
            dz = (pz - b["z"]) / max(1.0, b["rz"] * 0.92)
            if (dx * dx + dy * dy + dz * dz) <= 1.0:
                return True, "COLISÃO COM UMA ROCHA DO CÂNION!"

    return False, ""


# ==============================================================================
# TEXTURA DA CENA 2 (SANDSTONE.PNG + FALLBACK PROCEDURAL)
# ==============================================================================

def _create_procedural_canyon_texture():
    """Fallback procedural 128x128 caso as texturas de 'assets/' não sejam encontradas."""
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


def create_canyon_texture():
    """Carrega sandstone.png ou usa a textura procedural como fallback."""
    return load_texture_from_assets(
        "sandstone.png",
        fallback_fn=_create_procedural_canyon_texture,
        mode="rock",
        target_size=512,
    )


# ==============================================================================
# MODELAGEM DE MATACÃO / ROCHA FACETADA 3D COM MAPEAMENTO UV
# ==============================================================================

def _draw_procedural_boulder(boulder):
    """
    Desenha um matacão/rocha 3D facetado usando a textura sandstone.png.
    """
    rng = np.random.default_rng(boulder["seed"])
    rx, ry, rz = boulder["rx"], boulder["ry"], boulder["rz"]

    n_stacks = 4
    n_slices = 7

    rings = []
    for st in range(n_stacks):
        v_frac = st / float(n_stacks)
        elev = v_frac * (math.pi * 0.46)
        r_ring = math.cos(elev)
        y_ring = math.sin(elev) * ry

        ring_pts = []
        for sl in range(n_slices):
            ang = (2.0 * math.pi * sl) / n_slices
            perturb = float(rng.uniform(0.78, 1.18))
            px = rx * r_ring * math.cos(ang) * perturb
            pz = rz * r_ring * math.sin(ang) * perturb
            py = y_ring * float(rng.uniform(0.88, 1.12)) if st > 0 else 0.0
            u_coord = (sl / float(n_slices)) * 2.0
            v_coord = v_frac * 1.5
            ring_pts.append(([px, py, pz], u_coord, v_coord))
        rings.append(ring_pts)

    top_pt = [0.0, ry * float(rng.uniform(0.92, 1.06)), 0.0]

    glPushMatrix()
    glTranslatef(boulder["x"], boulder["y_base"], boulder["z"])
    glRotatef(boulder["yaw"], 0.0, 1.0, 0.0)

    shade = float(rng.uniform(0.80, 0.96))
    glColor3f(shade, shade * 0.95, shade * 0.90)

    glBegin(GL_TRIANGLES)
    for st in range(n_stacks - 1):
        curr_r = rings[st]
        next_r = rings[st + 1]
        for sl in range(n_slices):
            sl_next = (sl + 1) % n_slices
            p00, u00, v00 = curr_r[sl]
            p10, u10, v10 = curr_r[sl_next]
            p01, u01, v01 = next_r[sl]
            p11, u11, v11 = next_r[sl_next]

            n1 = compute_normal(p00, p10, p11)
            glNormal3fv(n1)
            glTexCoord2f(u00, v00); glVertex3fv(p00)
            glTexCoord2f(u10, v10); glVertex3fv(p10)
            glTexCoord2f(u11, v11); glVertex3fv(p11)

            n2 = compute_normal(p00, p11, p01)
            glNormal3fv(n2)
            glTexCoord2f(u00, v00); glVertex3fv(p00)
            glTexCoord2f(u11, v11); glVertex3fv(p11)
            glTexCoord2f(u01, v01); glVertex3fv(p01)

    last_r = rings[-1]
    for sl in range(n_slices):
        sl_next = (sl + 1) % n_slices
        p0, u0, v0 = last_r[sl]
        p1, u1, v1 = last_r[sl_next]
        n_top = compute_normal(p0, p1, top_pt)
        glNormal3fv(n_top)
        glTexCoord2f(u0, v0); glVertex3fv(p0)
        glTexCoord2f(u1, v1); glVertex3fv(p1)
        glTexCoord2f(0.5 * (u0 + u1), 2.0); glVertex3fv(top_pt)
    glEnd()

    glPopMatrix()


# ==============================================================================
# CONSTRUÇÃO DA CENA 2 (DISPLAY LIST)
# ==============================================================================

def build_scene2_canyon_list(canyon_tex_id):
    """
    Compila a Cena 2: Cânion Procedural ("Trench Run" de Top Gun: Maverick).
    Usa a mesma textura sandstone.png no piso, nos paredões e nas rochas 3D.
    O bunker alvo fica no final do cânion (z = -1150).
    """

    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    glEnable(GL_TEXTURE_2D)
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.20, 0.18, 0.15, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 14.0)

    x_min, x_max, dx = -360.0, 360.0, 18.0
    z_min, z_max, dz = -1400.0, 500.0, 20.0

    xs = np.arange(x_min, x_max + dx, dx)
    zs = np.arange(z_min, z_max + dz, dz)

    heights = np.zeros((len(xs), len(zs)), dtype=np.float32)
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            heights[i, j] = canyon_height_func(x, z)

    uv_world_scale = 0.045

    # 1A. Malha do leito do cânion (usa sandstone.png)
    glBindTexture(GL_TEXTURE_2D, canyon_tex_id)
    glBegin(GL_TRIANGLES)
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            y00, y10 = float(heights[i, j]), float(heights[i + 1, j])
            y01, y11 = float(heights[i, j + 1]), float(heights[i + 1, j + 1])
            avg_y = 0.25 * (y00 + y10 + y01 + y11)
            if avg_y >= 6.5:
                continue

            x0, x1 = float(xs[i]), float(xs[i + 1])
            z0, z1 = float(zs[j]), float(zs[j + 1])
            p00, p10 = [x0, y00, z0], [x1, y10, z0]
            p01, p11 = [x0, y01, z1], [x1, y11, z1]

            u00, v00 = x0 * uv_world_scale, z0 * uv_world_scale
            u10, v10 = x1 * uv_world_scale, z0 * uv_world_scale
            u01, v01 = x0 * uv_world_scale, z1 * uv_world_scale
            u11, v11 = x1 * uv_world_scale, z1 * uv_world_scale

            glColor3f(0.94, 0.90, 0.84)

            n1 = compute_normal(p00, p01, p11)
            glNormal3fv(n1)
            glTexCoord2f(u00, v00); glVertex3fv(p00)
            glTexCoord2f(u01, v01); glVertex3fv(p01)
            glTexCoord2f(u11, v11); glVertex3fv(p11)

            n2 = compute_normal(p00, p11, p10)
            glNormal3fv(n2)
            glTexCoord2f(u00, v00); glVertex3fv(p00)
            glTexCoord2f(u11, v11); glVertex3fv(p11)
            glTexCoord2f(u10, v10); glVertex3fv(p10)
    glEnd()

    # 1B. Malha dos paredões rochosos e topo das montanhas (usa sandstone.png)
    glBegin(GL_TRIANGLES)
    for i in range(len(xs) - 1):
        for j in range(len(zs) - 1):
            y00, y10 = float(heights[i, j]), float(heights[i + 1, j])
            y01, y11 = float(heights[i, j + 1]), float(heights[i + 1, j + 1])
            avg_y = 0.25 * (y00 + y10 + y01 + y11)
            if avg_y < 6.5:
                continue

            x0, x1 = float(xs[i]), float(xs[i + 1])
            z0, z1 = float(zs[j]), float(zs[j + 1])
            p00, p10 = [x0, y00, z0], [x1, y10, z0]
            p01, p11 = [x0, y01, z1], [x1, y11, z1]

            u00, v00 = (x0 + y00 * 0.45) * uv_world_scale, z0 * uv_world_scale
            u10, v10 = (x1 + y10 * 0.45) * uv_world_scale, z0 * uv_world_scale
            u01, v01 = (x0 + y01 * 0.45) * uv_world_scale, z1 * uv_world_scale
            u11, v11 = (x1 + y11 * 0.45) * uv_world_scale, z1 * uv_world_scale

            if avg_y < 85.0:
                glColor3f(0.92, 0.88, 0.84)
            else:
                glColor3f(1.00, 0.96, 0.92)

            n1 = compute_normal(p00, p01, p11)
            glNormal3fv(n1)
            glTexCoord2f(u00, v00); glVertex3fv(p00)
            glTexCoord2f(u01, v01); glVertex3fv(p01)
            glTexCoord2f(u11, v11); glVertex3fv(p11)

            n2 = compute_normal(p00, p11, p10)
            glNormal3fv(n2)
            glTexCoord2f(u00, v00); glVertex3fv(p00)
            glTexCoord2f(u11, v11); glVertex3fv(p11)
            glTexCoord2f(u10, v10); glVertex3fv(p10)
    glEnd()

    # 2. Rochas / matacões 3D gerados proceduralmente (usam sandstone.png)
    for boulder in CANYON_ROCK_OBSTACLES:
        _draw_procedural_boulder(boulder)

    # 3. Bunker Alvo no final do cânion
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