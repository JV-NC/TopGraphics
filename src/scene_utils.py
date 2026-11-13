"""
================================================================================
TopGraphics | scene_utils.py
Utilitários compartilhados de ambiente, atmosfera e mundo periódico ("Roundabout"):
  1. Sistema de Mundo Infinito / Roundabout (Toroide):
     - Teleporta suavemente o caça para a borda oposta ao cruzar os limites (X, Z)
       e renderiza as cópias periódicas adjacentes da Display List da cena logo à
       frente do jogador, criando a ilusão perfeita de volta ao mundo sem bordas.
  2. Sistema de Nascer do Sol (Rising Sun) Otimizado com Display List:
     - Abóbada celeste esférica completa (-90° a +90°), disco solar e halos compilados
       em Display List (atualizada a cada 0.5s), eliminando gargalos de CPU em Python.
  3. Nuvens Procedurais Volumétricas (Vapor Semitransparente) distribuídas por todo
     o domínio periódico de cada mapa.
================================================================================
"""

import math
import numpy as np
from OpenGL.GL import *

from math_utils import normalize


# ==============================================================================
# 0. CONSTANTES E FUNÇÕES DO MUNDO PERIÓDICO ("ROUNDABOUT")
# ==============================================================================

# Cena 1 (Oceano + Porta-Aviões CVN-65): domínio [-2400, +2400] em X e Z (período = 4800m)
SCENE1_X_MIN = -2400.0
SCENE1_X_MAX =  2400.0
SCENE1_SPAN_X = SCENE1_X_MAX - SCENE1_X_MIN   # 4800.0

SCENE1_Z_MIN = -2400.0
SCENE1_Z_MAX =  2400.0
SCENE1_SPAN_Z = SCENE1_Z_MAX - SCENE1_Z_MIN   # 4800.0

# Cena 2 (Cânion Procedural): domínio [-360, +360] em X (720m) e [-1500, +500] em Z (2000m)
SCENE2_X_MIN = -360.0
SCENE2_X_MAX =  360.0
SCENE2_SPAN_X = SCENE2_X_MAX - SCENE2_X_MIN   # 720.0

SCENE2_Z_MIN = -1500.0
SCENE2_Z_MAX =   500.0
SCENE2_SPAN_Z = SCENE2_Z_MAX - SCENE2_Z_MIN   # 2000.0

# Distância de visibilidade da câmera (zFar = 3500.0 no gluPerspective)
WORLD_VIEW_DISTANCE = 3450.0


def get_scene_bounds(scene_mode):
    """Retorna (x_min, x_max, span_x, z_min, z_max, span_z) para o cenário ativo."""
    if scene_mode == 1:
        return (
            SCENE1_X_MIN, SCENE1_X_MAX, SCENE1_SPAN_X,
            SCENE1_Z_MIN, SCENE1_Z_MAX, SCENE1_SPAN_Z,
        )
    return (
        SCENE2_X_MIN, SCENE2_X_MAX, SCENE2_SPAN_X,
        SCENE2_Z_MIN, SCENE2_Z_MAX, SCENE2_SPAN_Z,
    )


def wrap_position_roundabout(pos, scene_mode):
    """
    Aplica o teleporte toroidal (Roundabout) na posição 3D da aeronave
    quando ela ultrapassa os limites (X ou Z) do mapa.
    Retorna o vetor 'wrap_delta' (deslocamento aplicado), que também deve ser
    somado à Chase Cam para que a câmera acompanhe o teleporte sem nenhum salto visual.
    """
    x_min, x_max, span_x, z_min, z_max, span_z = get_scene_bounds(scene_mode)
    old_x = float(pos[0])
    old_z = float(pos[2])

    new_x = old_x
    new_z = old_z

    if old_x < x_min:
        new_x = ((old_x - x_min) % span_x) + x_min
    elif old_x >= x_max:
        new_x = ((old_x - x_min) % span_x) + x_min

    if old_z < z_min:
        new_z = ((old_z - z_min) % span_z) + z_min
    elif old_z >= z_max:
        new_z = ((old_z - z_min) % span_z) + z_min

    dx = new_x - old_x
    dz = new_z - old_z

    if abs(dx) > 1e-3 or abs(dz) > 1e-3:
        pos[0] = new_x
        pos[2] = new_z
        return np.array([dx, 0.0, dz], dtype=np.float32)

    return np.zeros(3, dtype=np.float32)


def _interval_distance(val, vmin, vmax):
    """Distância mínima de uma coordenada escalar 'val' até o intervalo [vmin, vmax]."""
    if val < vmin:
        return vmin - val
    if val > vmax:
        return val - vmax
    return 0.0


def get_visible_periodic_offsets(player_pos, scene_mode):
    """
    Determina quais cópias periódicas (tiles vizinhos) do mapa estão dentro do
    alcance visual da câmera (WORLD_VIEW_DISTANCE) a partir de 'player_pos'.
    Assim, antes mesmo do caça cruzar a fronteira do mapa, o lado oposto já está
    renderizado logo à sua frente!
    """
    x_min, x_max, span_x, z_min, z_max, span_z = get_scene_bounds(scene_mode)
    px, py, pz = float(player_pos[0]), float(player_pos[1]), float(player_pos[2])

    if scene_mode == 1:
        # Na Cena 1 (span = 4800m), avalia a vizinhança 3x3 e desenha apenas os tiles
        # cuja borda está dentro do raio de visão de 3450m.
        offsets = []
        for ix in (-1, 0, 1):
            tx_min = x_min + ix * span_x
            tx_max = x_max + ix * span_x
            dx = _interval_distance(px, tx_min, tx_max)
            if dx > WORLD_VIEW_DISTANCE:
                continue
            for iz in (-1, 0, 1):
                tz_min = z_min + iz * span_z
                tz_max = z_max + iz * span_z
                dz = _interval_distance(pz, tz_min, tz_max)
                if math.hypot(dx, dz) <= WORLD_VIEW_DISTANCE:
                    offsets.append((ix * span_x, iz * span_z))
        return offsets

    # Na Cena 2 (Cânion: span_z = 2000m, span_x = 720m):
    # Sempre desenha o tile atual (iz = 0) e os vizinhos frontal/traseiro (iz = -1, +1)
    # para que o corredor de 6000m nunca tenha fim visível.
    # Nos lados (ix = -1, +1), só precisa instanciar se o caça subir acima dos paredões
    # (py > 90m) ou se afastar lateralmente do centro do cânion (|px| > 150m).
    if py > 90.0 or abs(px) > 150.0:
        x_indices = (-1, 0, 1)
    else:
        x_indices = (0,)

    offsets = []
    for ix in x_indices:
        for iz in (-1, 0, 1):
            offsets.append((ix * span_x, iz * span_z))
    return offsets


def draw_periodic_scene(scene_dlist, player_pos, scene_mode):
    """
    Renderiza a Display List do cenário no tile principal (0, 0) e nas cópias
    periódicas adjacentes visíveis, garantindo continuidade visual 100% sem costuras
    no efeito Roundabout (Pac-Man).
    """
    offsets = get_visible_periodic_offsets(player_pos, scene_mode)
    for ox, oz in offsets:
        if abs(ox) < 1e-3 and abs(oz) < 1e-3:
            glCallList(scene_dlist)
        else:
            glPushMatrix()
            glTranslatef(ox, 0.0, oz)
            glCallList(scene_dlist)
            glPopMatrix()


# ==============================================================================
# 1. CONFIGURAÇÃO DO NASCER DO SOL (RISING SUN) E ATMOSFERA (COM CACHE DE GPU)
# ==============================================================================

SKY_DOME_RADIUS = 2200.0        # Raio da abóbada celeste esférica (dentro do zFar = 3500)
SUN_DISTANCE = 2100.0           # Distância do disco solar no horizonte (-Z)
SUN_AZIMUTH_RAD = -0.16         # Leve deslocamento a bombordo/oeste do eixo -Z
SUN_RISE_DURATION = 240.0       # Tempo (s) para o sol subir da aurora até a manhã alta
SUN_MIN_ELEV_DEG = 4.5          # Elevação inicial (rasante ao horizonte no início do voo)
SUN_MAX_ELEV_DEG = 26.0         # Elevação máxima após o ciclo de subida

# Cache interno de Display List para o Sky Dome (evita recalcular 800+ vértices em Python a cada frame)
_sky_dome_cache = {
    "dlist": None,
    "last_key": None,
}


def get_sun_state(sim_time, scene_mode=1):
    """
    Calcula a progressão contínua do nascer do sol em função de 'sim_time'.
    """
    progress = min(1.0, max(0.0, sim_time / SUN_RISE_DURATION))
    t = progress * progress * (3.0 - 2.0 * progress)

    elev_deg = SUN_MIN_ELEV_DEG + t * (SUN_MAX_ELEV_DEG - SUN_MIN_ELEV_DEG)
    elev_rad = math.radians(elev_deg)

    sx = math.cos(elev_rad) * math.sin(SUN_AZIMUTH_RAD)
    sy = math.sin(elev_rad)
    sz = -math.cos(elev_rad) * math.cos(SUN_AZIMUTH_RAD)
    sun_dir = normalize(np.array([sx, sy, sz], dtype=np.float32))

    if scene_mode == 1:
        zenith_dawn = np.array([0.08, 0.14, 0.34], dtype=np.float32)
        zenith_day  = np.array([0.18, 0.38, 0.72], dtype=np.float32)
        upper_dawn  = np.array([0.16, 0.24, 0.48], dtype=np.float32)
        upper_day   = np.array([0.32, 0.54, 0.84], dtype=np.float32)
        mid_dawn    = np.array([0.48, 0.34, 0.46], dtype=np.float32)
        mid_day     = np.array([0.62, 0.66, 0.78], dtype=np.float32)
        horiz_dawn  = np.array([0.92, 0.44, 0.24], dtype=np.float32)
        horiz_day   = np.array([0.96, 0.76, 0.52], dtype=np.float32)
    else:
        zenith_dawn = np.array([0.12, 0.13, 0.30], dtype=np.float32)
        zenith_day  = np.array([0.24, 0.38, 0.66], dtype=np.float32)
        upper_dawn  = np.array([0.24, 0.20, 0.40], dtype=np.float32)
        upper_day   = np.array([0.42, 0.52, 0.74], dtype=np.float32)
        mid_dawn    = np.array([0.58, 0.34, 0.38], dtype=np.float32)
        mid_day     = np.array([0.72, 0.62, 0.64], dtype=np.float32)
        horiz_dawn  = np.array([0.96, 0.42, 0.20], dtype=np.float32)
        horiz_day   = np.array([0.95, 0.72, 0.46], dtype=np.float32)

    zenith_color = (1.0 - t) * zenith_dawn + t * zenith_day
    upper_sky_color = (1.0 - t) * upper_dawn + t * upper_day
    mid_sky_color = (1.0 - t) * mid_dawn + t * mid_day
    horizon_color = (1.0 - t) * horiz_dawn + t * horiz_day

    sun_core = np.array([1.0, 0.92 + 0.06 * t, 0.72 + 0.20 * t], dtype=np.float32)
    sun_halo = (1.0 - t) * np.array([1.0, 0.38, 0.14], dtype=np.float32) + t * np.array([1.0, 0.72, 0.32], dtype=np.float32)

    light_ambient = [
        float(0.24 + 0.10 * t),
        float(0.20 + 0.12 * t),
        float(0.24 + 0.10 * t),
        1.0
    ]
    light_diffuse = [
        1.0,
        float(0.66 + 0.24 * t),
        float(0.46 + 0.34 * t),
        1.0
    ]
    light_specular = [
        1.0,
        float(0.78 + 0.18 * t),
        float(0.58 + 0.30 * t),
        1.0
    ]

    return {
        "dir": sun_dir,
        "progress": t,
        "elev_deg": elev_deg,
        "scene_mode": scene_mode,
        "zenith_color": zenith_color,
        "upper_sky_color": upper_sky_color,
        "mid_sky_color": mid_sky_color,
        "horizon_color": horizon_color,
        "sun_core_color": sun_core,
        "sun_halo_color": sun_halo,
        "light_ambient": light_ambient,
        "light_diffuse": light_diffuse,
        "light_specular": light_specular,
    }


def apply_sunrise_lighting(sun_state, lighting_enabled=True):
    """
    Atualiza a cor de fundo (glClearColor) usando a cor do zênite e configura GL_LIGHT0.
    """
    zc = sun_state["zenith_color"]
    glClearColor(float(zc[0]), float(zc[1]), float(zc[2]), 1.0)

    if lighting_enabled:
        glEnable(GL_LIGHTING)
        sdir = sun_state["dir"]
        glLightfv(GL_LIGHT0, GL_POSITION, [float(sdir[0]), float(sdir[1]), float(sdir[2]), 0.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, sun_state["light_ambient"])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, sun_state["light_diffuse"])
        glLightfv(GL_LIGHT0, GL_SPECULAR, sun_state["light_specular"])
    else:
        glDisable(GL_LIGHTING)


def _compute_sky_dome_vertex_color(elev_deg, azim_sin, azim_cos, sun_state):
    """
    Calcula a cor exata (r, g, b) de um vértice da abóbada celeste esférica
    para a elevação 'elev_deg' (-30° a +90°) e direção azimutal (azim_sin, azim_cos).
    """
    hc = sun_state["horizon_color"]
    mc = sun_state["mid_sky_color"]
    uc = sun_state["upper_sky_color"]
    zc = sun_state["zenith_color"]
    sdir = sun_state["dir"]

    if elev_deg <= 0.0:
        t_sub = np.clip(-elev_deg / 30.0, 0.0, 1.0)
        base_col = (1.0 - t_sub) * hc + t_sub * (0.45 * hc + 0.55 * zc)
    elif elev_deg <= 14.0:
        u = elev_deg / 14.0
        base_col = (1.0 - u) * hc + u * mc
    elif elev_deg <= 38.0:
        u = (elev_deg - 14.0) / (38.0 - 14.0)
        base_col = (1.0 - u) * mc + u * uc
    else:
        u = (elev_deg - 38.0) / (90.0 - 38.0)
        u_smooth = u * u * (3.0 - 2.0 * u)
        base_col = (1.0 - u_smooth) * uc + u_smooth * zc

    elev_atten = max(0.0, 1.0 - max(0.0, elev_deg) / 55.0) ** 2.0
    if elev_atten > 1e-4:
        horiz_dot = max(0.0, azim_sin * float(sdir[0]) + (-azim_cos) * float(sdir[2]))
        glow_boost = (horiz_dot ** 3.0) * 0.34 * elev_atten
        r = min(1.0, float(base_col[0]) + glow_boost)
        g = min(1.0, float(base_col[1]) + glow_boost * 0.55)
        b = min(1.0, float(base_col[2]) + glow_boost * 0.25)
        return r, g, b

    return float(base_col[0]), float(base_col[1]), float(base_col[2])


def _compile_sky_dome_display_list(sun_state):
    """
    Compila a geometria da abóbada celeste e do disco solar em uma Display List.
    Só é chamada quando o Sol se move significativamente (~a cada 0.5s) ou ao trocar de cena.
    """
    if _sky_dome_cache["dlist"] is None:
        _sky_dome_cache["dlist"] = glGenLists(1)

    dlist = _sky_dome_cache["dlist"]
    glNewList(dlist, GL_COMPILE)

    sc = sun_state["sun_core_color"]
    sh = sun_state["sun_halo_color"]
    zc = sun_state["zenith_color"]
    sdir = sun_state["dir"]

    segments = 32
    lat_rings_deg = [-30.0, -10.0, 0.0, 6.0, 13.0, 22.0, 35.0, 52.0, 70.0, 83.0]

    # 1. Faixas Esféricas de Latitude (-30° até +83°)
    for r_idx in range(len(lat_rings_deg) - 1):
        lat1_deg = lat_rings_deg[r_idx]
        lat2_deg = lat_rings_deg[r_idx + 1]
        lat1_rad = math.radians(lat1_deg)
        lat2_rad = math.radians(lat2_deg)

        y1 = SKY_DOME_RADIUS * math.sin(lat1_rad)
        r1 = SKY_DOME_RADIUS * math.cos(lat1_rad)
        y2 = SKY_DOME_RADIUS * math.sin(lat2_rad)
        r2 = SKY_DOME_RADIUS * math.cos(lat2_rad)

        glBegin(GL_QUAD_STRIP)
        for i in range(segments + 1):
            ang = (2.0 * math.pi * i) / segments
            ca = math.cos(ang)
            sa = math.sin(ang)

            c1_r, c1_g, c1_b = _compute_sky_dome_vertex_color(lat1_deg, sa, ca, sun_state)
            glColor4f(c1_r, c1_g, c1_b, 1.0)
            glVertex3f(r1 * sa, y1, -r1 * ca)

            c2_r, c2_g, c2_b = _compute_sky_dome_vertex_color(lat2_deg, sa, ca, sun_state)
            glColor4f(c2_r, c2_g, c2_b, 1.0)
            glVertex3f(r2 * sa, y2, -r2 * ca)
        glEnd()

    # 2. Calota Superior do Zênite (+83° até +90°)
    top_ring_deg = lat_rings_deg[-1]
    top_ring_rad = math.radians(top_ring_deg)
    y_ring = SKY_DOME_RADIUS * math.sin(top_ring_rad)
    r_ring = SKY_DOME_RADIUS * math.cos(top_ring_rad)

    glBegin(GL_TRIANGLE_FAN)
    glColor4f(float(zc[0]), float(zc[1]), float(zc[2]), 1.0)
    glVertex3f(0.0, SKY_DOME_RADIUS, 0.0)
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        ca = math.cos(ang)
        sa = math.sin(ang)
        cr, cg, cb = _compute_sky_dome_vertex_color(top_ring_deg, sa, ca, sun_state)
        glColor4f(cr, cg, cb, 1.0)
        glVertex3f(r_ring * sa, y_ring, -r_ring * ca)
    glEnd()

    # 3. Calota Inferior (-30° até -90°)
    bot_ring_deg = lat_rings_deg[0]
    bot_ring_rad = math.radians(bot_ring_deg)
    y_bot_ring = SKY_DOME_RADIUS * math.sin(bot_ring_rad)
    r_bot_ring = SKY_DOME_RADIUS * math.cos(bot_ring_rad)
    nadir_col = 0.35 * sun_state["horizon_color"] + 0.65 * zc

    glBegin(GL_TRIANGLE_FAN)
    glColor4f(float(nadir_col[0]), float(nadir_col[1]), float(nadir_col[2]), 1.0)
    glVertex3f(0.0, -SKY_DOME_RADIUS, 0.0)
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        ca = math.cos(ang)
        sa = math.sin(ang)
        cr, cg, cb = _compute_sky_dome_vertex_color(bot_ring_deg, sa, ca, sun_state)
        glColor4f(cr, cg, cb, 1.0)
        glVertex3f(r_bot_ring * sa, y_bot_ring, -r_bot_ring * ca)
    glEnd()

    # 4. Disco Solar e Coroas de Difração
    sun_pos = sdir * SUN_DISTANCE
    up_world = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    sun_right = normalize(np.cross(sdir, up_world))
    sun_up = normalize(np.cross(sun_right, sdir))

    halo_layers = [
        (560.0, 0.0,  [sh[0], sh[1] * 0.75, sh[2] * 0.5, 0.22]),
        (300.0, 0.0,  [sh[0], sh[1],        sh[2],       0.38]),
        (145.0, 0.25, [sc[0], sc[1] * 0.92, sc[2] * 0.7, 0.65]),
        ( 76.0, 0.96, [sc[0], sc[1],        sc[2],       0.98]),
    ]

    fan_segs = 24
    for radius, center_alpha_boost, rgba in halo_layers:
        glBegin(GL_TRIANGLE_FAN)
        if center_alpha_boost > 0.5:
            glColor4f(1.0, 0.99, 0.92, float(rgba[3]))
        else:
            glColor4f(float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3]))
        glVertex3f(float(sun_pos[0]), float(sun_pos[1]), float(sun_pos[2]))

        edge_alpha = 0.85 if center_alpha_boost > 0.8 else 0.0
        glColor4f(float(rgba[0]), float(rgba[1]), float(rgba[2]), edge_alpha)
        for i in range(fan_segs + 1):
            ang = (2.0 * math.pi * i) / fan_segs
            offset = sun_right * (math.cos(ang) * radius) + sun_up * (math.sin(ang) * radius)
            pt = sun_pos + offset
            glVertex3f(float(pt[0]), float(pt[1]), float(pt[2]))
        glEnd()

    glEndList()


def draw_rising_sun_and_sky(anchor_pos, sun_state, scene_mode=1):
    """
    Renderiza a abóbada celeste esférica completa usando Display List em cache,
    centrada em (X, Y, Z) da aeronave.
    """
    # Atualiza o cache apenas quando a elevação solar muda em ~0.1 grau ou muda o cenário
    cache_key = (scene_mode, int(round(sun_state["elev_deg"] * 10.0)))
    if _sky_dome_cache["last_key"] != cache_key or _sky_dome_cache["dlist"] is None:
        _compile_sky_dome_display_list(sun_state)
        _sky_dome_cache["last_key"] = cache_key

    glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT | GL_POLYGON_BIT)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glDisable(GL_DEPTH_TEST)
    glDepthMask(GL_FALSE)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    glPushMatrix()
    glTranslatef(float(anchor_pos[0]), float(anchor_pos[1]), float(anchor_pos[2]))
    glCallList(_sky_dome_cache["dlist"])
    glPopMatrix()

    glPopAttrib()


def draw_ocean_sun_glitter(anchor_pos, sun_state, sim_time):
    """
    Desenha a trilha de reflexo dourado do nascer do sol ('Sun Glitter Path')
    sobre a superfície do oceano na Cena 1.
    """
    glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glDepthMask(GL_FALSE)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    sdir = sun_state["dir"]
    sh = sun_state["sun_halo_color"]
    sc = sun_state["sun_core_color"]

    horiz_dir = normalize(np.array([sdir[0], 0.0, sdir[2]], dtype=np.float32))
    perp_dir = np.array([-horiz_dir[2], 0.0, horiz_dir[0]], dtype=np.float32)

    base_x = float(anchor_pos[0])
    base_z = float(anchor_pos[2])

    num_strips = 22
    glBegin(GL_QUADS)
    for i in range(num_strips):
        dist = 160.0 + i * 95.0
        shimmer = 0.75 + 0.25 * math.sin(sim_time * 3.8 + i * 1.7)
        half_w = (12.0 + i * 5.5) * shimmer
        depth_l = 28.0 + i * 2.8

        center = np.array([base_x, 0.18, base_z], dtype=np.float32) + horiz_dir * dist
        p1 = center - perp_dir * half_w - horiz_dir * depth_l
        p2 = center + perp_dir * half_w - horiz_dir * depth_l
        p3 = center + perp_dir * (half_w * 0.8) + horiz_dir * depth_l
        p4 = center - perp_dir * (half_w * 0.8) + horiz_dir * depth_l

        alpha = (0.12 + 0.14 * (i / float(num_strips))) * shimmer
        glColor4f(float(sc[0]), float(0.75 * sc[1] + 0.25 * sh[1]), float(sh[2]), alpha)
        glVertex3f(float(p1[0]), 0.18, float(p1[2]))
        glVertex3f(float(p2[0]), 0.18, float(p2[2]))
        glVertex3f(float(p3[0]), 0.18, float(p3[2]))
        glVertex3f(float(p4[0]), 0.18, float(p4[2]))
    glEnd()

    glPopAttrib()


# ==============================================================================
# 2. NUVENS PROCEDURAIS (VAPOR SEMITRANSPARENTE COM SUPORTE PERIÓDICO)
# ==============================================================================

def create_cloud_vapor_texture():
    """
    Gera proceduralmente uma textura RGBA 128x128 de vapor de nuvem semitransparente.
    """
    size = 128
    img = np.zeros((size, size, 4), dtype=np.uint8)

    xs = np.linspace(-1.0, 1.0, size, dtype=np.float32)
    ys = np.linspace(-1.0, 1.0, size, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)

    r2 = xv * xv + yv * yv
    radial_mask = np.clip(1.0 - r2 / 0.90, 0.0, 1.0) ** 2.2

    turb = (
        0.50 * np.sin(xv * 3.8 + np.cos(yv * 3.2))
        + 0.30 * np.cos(yv * 6.5 - np.sin(xv * 5.8))
        + 0.20 * np.sin((xv + yv) * 11.0)
    )
    density = np.clip(0.68 + 0.32 * turb, 0.15, 1.0)
    alpha_f = radial_mask * density

    shade = np.clip(238 + 17 * (0.35 - yv), 210, 255).astype(np.uint8)

    img[:, :, 0] = shade
    img[:, :, 1] = shade
    img[:, :, 2] = np.clip(shade.astype(np.int16) + 5, 0, 255).astype(np.uint8)
    img[:, :, 3] = np.clip(alpha_f * 165.0, 0.0, 165.0).astype(np.uint8)

    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, img)
    return tex_id


def _draw_vapor_puff_cluster(cx, cy, cz, rx, ry, rz, rng):
    """
    Compila um banco de nuvem individual usando planos de vapor cruzados.
    """
    num_wisps = 8
    for _ in range(num_wisps):
        ox = float(rng.uniform(-0.48, 0.48) * rx)
        oy = float(rng.uniform(-0.35, 0.45) * ry)
        oz = float(rng.uniform(-0.48, 0.48) * rz)

        w_scale = float(rng.uniform(0.55, 1.05))
        pw = rx * w_scale
        pl = rz * w_scale
        ph = ry * float(rng.uniform(0.45, 0.85))

        yaw_deg = float(rng.uniform(0.0, 180.0))
        tilt_x = float(rng.uniform(-14.0, 14.0))
        tilt_z = float(rng.uniform(-14.0, 14.0))

        height_factor = (oy / max(1.0, ry)) + 0.5
        if height_factor < 0.42:
            glColor4f(1.0, 0.74, 0.58, 0.34)
        elif height_factor < 0.72:
            glColor4f(0.99, 0.88, 0.78, 0.38)
        else:
            glColor4f(1.0, 0.96, 0.92, 0.42)

        glPushMatrix()
        glTranslatef(cx + ox, cy + oy, cz + oz)
        glRotatef(yaw_deg, 0.0, 1.0, 0.0)
        glRotatef(tilt_x, 1.0, 0.0, 0.0)
        glRotatef(tilt_z, 0.0, 0.0, 1.0)

        glBegin(GL_QUADS)
        glTexCoord2f(0.0, 0.0); glVertex3f(-pw, 0.0, -pl)
        glTexCoord2f(1.0, 0.0); glVertex3f( pw, 0.0, -pl)
        glTexCoord2f(1.0, 1.0); glVertex3f( pw, 0.0,  pl)
        glTexCoord2f(0.0, 1.0); glVertex3f(-pw, 0.0,  pl)

        glTexCoord2f(0.0, 0.0); glVertex3f(-pw * 0.85, -ph, -pl * 0.45)
        glTexCoord2f(1.0, 0.0); glVertex3f( pw * 0.85, -ph, -pl * 0.45)
        glTexCoord2f(1.0, 1.0); glVertex3f( pw * 0.85,  ph,  pl * 0.45)
        glTexCoord2f(0.0, 1.0); glVertex3f(-pw * 0.85,  ph,  pl * 0.45)

        glTexCoord2f(0.0, 0.0); glVertex3f(-pw * 0.45, -ph, -pl * 0.85)
        glTexCoord2f(1.0, 0.0); glVertex3f(-pw * 0.45, -ph,  pl * 0.85)
        glTexCoord2f(1.0, 1.0); glVertex3f( pw * 0.45,  ph,  pl * 0.85)
        glTexCoord2f(0.0, 1.0); glVertex3f( pw * 0.45,  ph, -pl * 0.85)
        glEnd()

        glPopMatrix()


def build_procedural_clouds_list(scene_mode=1):
    """
    Compila uma Display List contendo formações de nuvens procedurais distribuídas
    por todo o domínio periódico do cenário.
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    rng = np.random.default_rng(101 if scene_mode == 1 else 202)

    if scene_mode == 1:
        num_clusters = 52
        for _ in range(num_clusters):
            cx = float(rng.uniform(SCENE1_X_MIN + 150.0, SCENE1_X_MAX - 150.0))
            cz = float(rng.uniform(SCENE1_Z_MIN + 150.0, SCENE1_Z_MAX - 150.0))
            if abs(cx) < 180.0 and abs(cz) < 280.0:
                cy = float(rng.uniform(135.0, 240.0))
            else:
                cy = float(rng.uniform(82.0, 255.0))

            rx = float(rng.uniform(75.0, 165.0))
            ry = float(rng.uniform(18.0, 38.0))
            rz = float(rng.uniform(75.0, 165.0))
            _draw_vapor_puff_cluster(cx, cy, cz, rx, ry, rz, rng)

    else:
        num_clusters = 40
        for _ in range(num_clusters):
            cz = float(rng.uniform(SCENE2_Z_MIN + 60.0, SCENE2_Z_MAX - 60.0))
            cx = float(rng.uniform(SCENE2_X_MIN + 40.0, SCENE2_X_MAX - 40.0))
            cy = float(rng.uniform(115.0, 235.0))

            rx = float(rng.uniform(65.0, 135.0))
            ry = float(rng.uniform(15.0, 32.0))
            rz = float(rng.uniform(65.0, 135.0))
            _draw_vapor_puff_cluster(cx, cy, cz, rx, ry, rz, rng)

    glEndList()
    return dlist


def draw_procedural_clouds(clouds_dlist, cloud_tex_id, sim_time, player_pos=None, scene_mode=1):
    """
    Renderiza a camada de nuvens procedurais como vapor semitransparente, repetindo
    também nos tiles periódicos visíveis para manter continuidade no Roundabout.
    """
    glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT | GL_POLYGON_BIT)
    glDisable(GL_LIGHTING)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, cloud_tex_id)

    glEnable(GL_DEPTH_TEST)
    glDepthMask(GL_FALSE)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    drift_x = math.sin(sim_time * 0.015) * 35.0
    drift_z = (sim_time * 3.2) % 400.0 - 200.0

    if player_pos is not None:
        offsets = get_visible_periodic_offsets(player_pos, scene_mode)
    else:
        offsets = [(0.0, 0.0)]

    for ox, oz in offsets:
        glPushMatrix()
        glTranslatef(ox + drift_x, 0.0, oz + drift_z)
        glCallList(clouds_dlist)
        glPopMatrix()

    glPopAttrib()