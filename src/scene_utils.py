"""
================================================================================
TopGraphics | scene_utils.py
Utilitários compartilhados de ambiente e atmosfera para os cenários (Cena 1 e Cena 2):
  1. Sistema de Nascer do Sol (Rising Sun): domo de horizonte crepuscular, disco solar
     com múltiplos halos de difração atmosférica, reflexo especular no mar e atualização
     dinâmica da iluminação direcional (GL_LIGHT0).
  2. Nuvens Procedurais Volumétricas (Vapor Semitransparente): textura RGBA gerada via
     ruído fractal trigonométrico (fBm) com decaimento radial gaussiano e renderização
     em camadas sem escrita no Z-Buffer (glDepthMask(GL_FALSE)), garantindo aspecto de
     vapor real ao redor e através do caça F-14.
================================================================================
"""

# TODO: render more of the map as needed or implement a visual map boundary (maybe create more map and implement a fake roundabout around the world, teleporting user to the other border)
# TODO: fix: sky "crown" that creates a bege sky above the sun rising horizon

import math
import numpy as np
from OpenGL.GL import *

from math_utils import normalize


# ==============================================================================
# 1. CONFIGURAÇÃO DO NASCER DO SOL (RISING SUN) E ATMOSFERA
# ==============================================================================

SUN_DISTANCE = 2600.0           # Distância do disco solar no horizonte (-Z)
SUN_AZIMUTH_RAD = -0.16         # Leve deslocamento a bombordo/oeste do eixo -Z
SUN_RISE_DURATION = 240.0       # Tempo (s) para o sol subir da aurora até a manhã alta
SUN_MIN_ELEV_DEG = 4.5          # Elevação inicial (rasante ao horizonte no início do voo)
SUN_MAX_ELEV_DEG = 26.0         # Elevação máxima após o ciclo de subida


def get_sun_state(sim_time, scene_mode=1):
    """
    Calcula a progressão contínua do nascer do sol em função de 'sim_time'.
    Retorna um dicionário com:
      - 'dir': vetor unitário apontando para o Sol (x, y, z)
      - 'progress': fração [0.0, 1.0] da subida solar
      - 'zenith_color': cor RGB do topo do céu
      - 'horizon_color': cor RGB da faixa do horizonte
      - 'sun_core_color': cor RGB do núcleo solar
      - 'sun_halo_color': cor RGB da coroa luminosa
      - 'light_ambient', 'light_diffuse', 'light_specular': parâmetros para GL_LIGHT0
    """
    # Progressão suave entre 0.0 (alvorada rasante) e 1.0 (manhã dourada)
    progress = min(1.0, max(0.0, sim_time / SUN_RISE_DURATION))
    # Curva suave (smoothstep)
    t = progress * progress * (3.0 - 2.0 * progress)

    elev_deg = SUN_MIN_ELEV_DEG + t * (SUN_MAX_ELEV_DEG - SUN_MIN_ELEV_DEG)
    elev_rad = math.radians(elev_deg)

    # Vetor unitário apontando do centro da cena para o Sol no horizonte frontal (-Z)
    sx = math.cos(elev_rad) * math.sin(SUN_AZIMUTH_RAD)
    sy = math.sin(elev_rad)
    sz = -math.cos(elev_rad) * math.cos(SUN_AZIMUTH_RAD)
    sun_dir = normalize(np.array([sx, sy, sz], dtype=np.float32))

    if scene_mode == 1:
        # Cena 1 (Oceano + CVN-65): transição de azul-violeta crepuscular para azul celeste dourado
        zenith_dawn = np.array([0.14, 0.22, 0.44], dtype=np.float32)
        zenith_day  = np.array([0.30, 0.52, 0.82], dtype=np.float32)
        horiz_dawn  = np.array([0.92, 0.44, 0.24], dtype=np.float32)
        horiz_day   = np.array([0.96, 0.76, 0.52], dtype=np.float32)
    else:
        # Cena 2 (Cânion): tons mais quentes de deserto / âmbar na alvorada
        zenith_dawn = np.array([0.22, 0.18, 0.36], dtype=np.float32)
        zenith_day  = np.array([0.42, 0.50, 0.72], dtype=np.float32)
        horiz_dawn  = np.array([0.96, 0.42, 0.20], dtype=np.float32)
        horiz_day   = np.array([0.95, 0.72, 0.46], dtype=np.float32)

    zenith_color = (1.0 - t) * zenith_dawn + t * zenith_day
    horizon_color = (1.0 - t) * horiz_dawn + t * horiz_day

    sun_core = np.array([1.0, 0.92 + 0.06 * t, 0.72 + 0.20 * t], dtype=np.float32)
    sun_halo = (1.0 - t) * np.array([1.0, 0.38, 0.14], dtype=np.float32) + t * np.array([1.0, 0.72, 0.32], dtype=np.float32)

    # Cores da luz direcional GL_LIGHT0 que banham o F-14, o porta-aviões e as rochas
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
        "zenith_color": zenith_color,
        "horizon_color": horizon_color,
        "sun_core_color": sun_core,
        "sun_halo_color": sun_halo,
        "light_ambient": light_ambient,
        "light_diffuse": light_diffuse,
        "light_specular": light_specular,
    }


def apply_sunrise_lighting(sun_state, lighting_enabled=True):
    """
    Atualiza a cor de fundo (glClearColor) e os parâmetros da fonte direcional GL_LIGHT0
    de acordo com a elevação atual do nascer do sol.
    """
    zc = sun_state["zenith_color"]
    hc = sun_state["horizon_color"]
    # Cor de limpeza intermediária entre o horizonte e o zênite
    clear_rgb = 0.55 * zc + 0.45 * hc
    glClearColor(float(clear_rgb[0]), float(clear_rgb[1]), float(clear_rgb[2]), 1.0)

    if lighting_enabled:
        glEnable(GL_LIGHTING)
        sdir = sun_state["dir"]
        # w = 0.0 define fonte direcional (raios paralelos vindos da direção do Sol)
        glLightfv(GL_LIGHT0, GL_POSITION, [float(sdir[0]), float(sdir[1]), float(sdir[2]), 0.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, sun_state["light_ambient"])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, sun_state["light_diffuse"])
        glLightfv(GL_LIGHT0, GL_SPECULAR, sun_state["light_specular"])
    else:
        glDisable(GL_LIGHTING)


def draw_rising_sun_and_sky(anchor_pos, sun_state, scene_mode=1):
    """
    Renderiza o domo atmosférico de nascer do sol, a faixa incandescente do horizonte,
    o disco solar com múltiplos halos translúcidos (vapor/glow) e a trilha de reflexo
    solar sobre a água (na Cena 1).
    Deve ser chamado ANTES da geometria opaca da cena (com glDepthMask(GL_FALSE)).
    """
    glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT | GL_POLYGON_BIT)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glDisable(GL_DEPTH_TEST)
    glDepthMask(GL_FALSE)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    cx = float(anchor_pos[0])
    cz = float(anchor_pos[2])

    zc = sun_state["zenith_color"]
    hc = sun_state["horizon_color"]
    sc = sun_state["sun_core_color"]
    sh = sun_state["sun_halo_color"]
    sdir = sun_state["dir"]

    sky_radius = 2700.0
    segments = 36

    glPushMatrix()
    glTranslatef(cx, 0.0, cz)

    # 1. Cilindro/Domo de Gradiente Atmosférico 360° (Horizonte -> Meia-Altura -> Zênite)
    y_bot = -80.0
    y_mid = 420.0
    y_top = 1550.0

    # Faixa inferior (Horizonte incandescente -> Transição intermediária)
    mid_col = 0.38 * hc + 0.62 * zc
    glBegin(GL_QUAD_STRIP)
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        ca = math.cos(ang)
        sa = math.sin(ang)
        vx = sky_radius * sa
        vz = -sky_radius * ca

        # Intensifica o brilho alaranjado na direção próxima ao Sol
        cos_sun = max(0.0, (vx * sdir[0] + vz * sdir[2]) / sky_radius)
        glow_boost = (cos_sun ** 3.0) * 0.35

        hr = min(1.0, float(hc[0]) + glow_boost)
        hg = min(1.0, float(hc[1]) + glow_boost * 0.55)
        hb = min(1.0, float(hc[2]) + glow_boost * 0.25)

        glColor4f(hr, hg, hb, 1.0)
        glVertex3f(vx, y_bot, vz)

        glColor4f(float(mid_col[0]), float(mid_col[1]), float(mid_col[2]), 1.0)
        glVertex3f(vx, y_mid, vz)
    glEnd()

    # Faixa superior (Meia-Altura -> Zênite profundo)
    glBegin(GL_QUAD_STRIP)
    for i in range(segments + 1):
        ang = (2.0 * math.pi * i) / segments
        vx = sky_radius * math.sin(ang)
        vz = -sky_radius * math.cos(ang)

        glColor4f(float(mid_col[0]), float(mid_col[1]), float(mid_col[2]), 1.0)
        glVertex3f(vx, y_mid, vz)

        glColor4f(float(zc[0]), float(zc[1]), float(zc[2]), 1.0)
        glVertex3f(vx, y_top, vz)
    glEnd()

    # 2. Disco Solar e Coroas de Difração (Billboard alinhado ao vetor do Sol)
    sun_pos = sdir * SUN_DISTANCE
    up_world = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    sun_right = normalize(np.cross(sdir, up_world))
    sun_up = normalize(np.cross(sun_right, sdir))

    # Desenha 4 camadas concêntricas de halo (do brilho atmosférico amplo até o núcleo solar)
    halo_layers = [
        (680.0, 0.0,  [sh[0], sh[1] * 0.75, sh[2] * 0.5, 0.22]),
        (360.0, 0.0,  [sh[0], sh[1],        sh[2],       0.38]),
        (175.0, 0.25, [sc[0], sc[1] * 0.92, sc[2] * 0.7, 0.65]),
        ( 92.0, 0.96, [sc[0], sc[1],        sc[2],       0.98]),
    ]

    fan_segs = 28
    for radius, center_alpha_boost, rgba in halo_layers:
        glBegin(GL_TRIANGLE_FAN)
        if center_alpha_boost > 0.5:
            glColor4f(1.0, 0.99, 0.92, float(rgba[3]))
        else:
            glColor4f(float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3]))
        glVertex3f(float(sun_pos[0]), float(sun_pos[1]), float(sun_pos[2]))

        # Borda externa do halo decai suavemente para alpha = 0 (exceto o disco central)
        edge_alpha = 0.85 if center_alpha_boost > 0.8 else 0.0
        glColor4f(float(rgba[0]), float(rgba[1]), float(rgba[2]), edge_alpha)
        for i in range(fan_segs + 1):
            ang = (2.0 * math.pi * i) / fan_segs
            offset = sun_right * (math.cos(ang) * radius) + sun_up * (math.sin(ang) * radius)
            pt = sun_pos + offset
            glVertex3f(float(pt[0]), float(pt[1]), float(pt[2]))
        glEnd()

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

    # Direção horizontal no plano XZ em direção ao Sol
    horiz_dir = normalize(np.array([sdir[0], 0.0, sdir[2]], dtype=np.float32))
    perp_dir = np.array([-horiz_dir[2], 0.0, horiz_dir[0]], dtype=np.float32)

    base_x = float(anchor_pos[0])
    base_z = float(anchor_pos[2])

    # Faixas cintilantes ao longo do caminho entre o porta-aviões/caça e o horizonte solar
    num_strips = 26
    glBegin(GL_QUADS)
    for i in range(num_strips):
        dist = 160.0 + i * 85.0
        shimmer = 0.75 + 0.25 * math.sin(sim_time * 3.8 + i * 1.7)
        half_w = (12.0 + i * 5.2) * shimmer
        depth_l = 28.0 + i * 2.5

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
# 2. NUVENS PROCEDURAIS (VAPOR SEMITRANSPARENTE, NÃO SÓLIDO)
# ==============================================================================

def create_cloud_vapor_texture():
    """
    Gera proceduralmente uma textura RGBA 128x128 de vapor de nuvem semitransparente.
    Usa soma de harmônicos trigonométricos (fBm) modulada por um envelope radial
    gaussiano suave para que as bordas tenham alpha = 0 (zero quinas visíveis).
    """
    size = 128
    img = np.zeros((size, size, 4), dtype=np.uint8)

    xs = np.linspace(-1.0, 1.0, size, dtype=np.float32)
    ys = np.linspace(-1.0, 1.0, size, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)

    # Distância radial ao quadrado a partir do centro da textura
    r2 = xv * xv + yv * yv
    # Envelope suave que zera completamente em r >= 0.95
    radial_mask = np.clip(1.0 - r2 / 0.90, 0.0, 1.0) ** 2.2

    # Turbulência fractal suave (3 oitavas trigonométricas)
    turb = (
        0.50 * np.sin(xv * 3.8 + np.cos(yv * 3.2))
        + 0.30 * np.cos(yv * 6.5 - np.sin(xv * 5.8))
        + 0.20 * np.sin((xv + yv) * 11.0)
    )
    density = np.clip(0.68 + 0.32 * turb, 0.15, 1.0)
    alpha_f = radial_mask * density

    # Gradiente sutil de iluminação interna no puff de vapor
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
    Compila um banco de nuvem individual usando planos de vapor cruzados e levemente
    inclinados em múltiplas camadas horizontais e oblíquas.
    Como a textura RGBA tem bordas gaussianas transparentes e glDepthMask(GL_FALSE)
    está ativo na renderização, o resultado visual é uma névoa/vapor tridimensional
    suave que pode ser atravessada pelo F-14 sem parecer um objeto sólido.
    """
    num_wisps = 9
    for k in range(num_wisps):
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

        # Base da nuvem recebe iluminação alaranjada/rosada do nascer do sol;
        # topo da nuvem é mais claro/creme
        height_factor = (oy / max(1.0, ry)) + 0.5
        if height_factor < 0.42:
            # Brilho inferior do sol nascente (Golden/Rose underside)
            glColor4f(1.0, 0.74, 0.58, 0.34)
        elif height_factor < 0.72:
            glColor4f(0.99, 0.88, 0.78, 0.38)
        else:
            # Topo iluminado
            glColor4f(1.0, 0.96, 0.92, 0.42)

        glPushMatrix()
        glTranslatef(cx + ox, cy + oy, cz + oz)
        glRotatef(yaw_deg, 0.0, 1.0, 0.0)
        glRotatef(tilt_x, 1.0, 0.0, 0.0)
        glRotatef(tilt_z, 0.0, 0.0, 1.0)

        glBegin(GL_QUADS)
        # 1. Camada horizontal principal de vapor
        glTexCoord2f(0.0, 0.0); glVertex3f(-pw, 0.0, -pl)
        glTexCoord2f(1.0, 0.0); glVertex3f( pw, 0.0, -pl)
        glTexCoord2f(1.0, 1.0); glVertex3f( pw, 0.0,  pl)
        glTexCoord2f(0.0, 1.0); glVertex3f(-pw, 0.0,  pl)

        # 2. Camada oblíqua longitudinal (dá volume quando visto de frente/trás em voo nivelado)
        glTexCoord2f(0.0, 0.0); glVertex3f(-pw * 0.85, -ph, -pl * 0.45)
        glTexCoord2f(1.0, 0.0); glVertex3f( pw * 0.85, -ph, -pl * 0.45)
        glTexCoord2f(1.0, 1.0); glVertex3f( pw * 0.85,  ph,  pl * 0.45)
        glTexCoord2f(0.0, 1.0); glVertex3f(-pw * 0.85,  ph,  pl * 0.45)

        # 3. Camada oblíqua transversal (dá volume quando visto de lado)
        glTexCoord2f(0.0, 0.0); glVertex3f(-pw * 0.45, -ph, -pl * 0.85)
        glTexCoord2f(1.0, 0.0); glVertex3f(-pw * 0.45, -ph,  pl * 0.85)
        glTexCoord2f(1.0, 1.0); glVertex3f( pw * 0.45,  ph,  pl * 0.85)
        glTexCoord2f(0.0, 1.0); glVertex3f( pw * 0.45,  ph, -pl * 0.85)
        glEnd()

        glPopMatrix()


def build_procedural_clouds_list(scene_mode=1):
    """
    Compila uma Display List contendo dezenas de formações de nuvens procedurais
    distribuídas pelo espaço 3D do cenário (sem colisão e sem escrita no Z-buffer).
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    rng = np.random.default_rng(101 if scene_mode == 1 else 202)

    if scene_mode == 1:
        # Cena 1 (Oceano + Porta-Aviões): bancos de nuvens marítimas entre 85m e 260m de altitude
        num_clusters = 52
        for _ in range(num_clusters):
            cx = float(rng.uniform(-1850.0, 1850.0))
            cz = float(rng.uniform(-2100.0, 1450.0))
            # Evita colocar nuvens muito baixas exatamente sobre a pista do porta-aviões
            if abs(cx) < 180.0 and abs(cz) < 280.0:
                cy = float(rng.uniform(135.0, 240.0))
            else:
                cy = float(rng.uniform(82.0, 255.0))

            rx = float(rng.uniform(75.0, 165.0))
            ry = float(rng.uniform(18.0, 38.0))
            rz = float(rng.uniform(75.0, 165.0))
            _draw_vapor_puff_cluster(cx, cy, cz, rx, ry, rz, rng)

    else:
        # Cena 2 (Cânion Procedural): bancos de neblina alta sobre os paredões rochosos
        # e nuvens esparsas ao longo do corredor de voo
        num_clusters = 44
        for _ in range(num_clusters):
            cz = float(rng.uniform(-1450.0, 480.0))
            cx = float(rng.uniform(-420.0, 420.0))
            cy = float(rng.uniform(115.0, 235.0))

            rx = float(rng.uniform(65.0, 140.0))
            ry = float(rng.uniform(15.0, 32.0))
            rz = float(rng.uniform(65.0, 140.0))
            _draw_vapor_puff_cluster(cx, cy, cz, rx, ry, rz, rng)

    glEndList()
    return dlist


def draw_procedural_clouds(clouds_dlist, cloud_tex_id, sim_time):
    """
    Renderiza a camada de nuvens procedurais como vapor semitransparente:
      - Desativa escrita no Depth Buffer (glDepthMask(GL_FALSE)) mantendo o teste
        de profundidade ativo (GL_DEPTH_TEST), para que o F-14 e as montanhas
        ocultem corretamente o vapor atrás deles, mas o vapor nunca crie recortes
        sólidos nem bloqueie objetos.
      - Aplica deriva suave de vento ao longo do tempo (sim_time).
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

    # Movimento suave de deriva pelo vento
    drift_x = math.sin(sim_time * 0.015) * 35.0
    drift_z = (sim_time * 3.2) % 400.0 - 200.0

    glPushMatrix()
    glTranslatef(drift_x, 0.0, drift_z)
    glCallList(clouds_dlist)
    glPopMatrix()

    glPopAttrib()
