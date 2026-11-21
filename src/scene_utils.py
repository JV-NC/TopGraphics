"""
================================================================================
TopGraphics | scene_utils.py
Utilitários compartilhados de ambiente, atmosfera, ciclo Dia/Noite e Roundabout:
  1. Sistema de Mundo Infinito / Roundabout (Toroide):
     - Teleporta suavemente o caça para a borda oposta ao cruzar os limites (X, Z)
       e renderiza as cópias periódicas adjacentes da Display List da cena.
  2. Sistema Completo de Ciclo Dia e Noite (24h Contínuo + Presets pela Tecla [C]):
     - Amanhecer (06:25), Meio-Dia (12:00), Pôr do Sol (17:35) e Noite (21:00).
     - Abóbada celeste esférica completa (-90° a +90°), disco solar com halos,
       Lua cheia com halo prateado e campo estelar procedural compilados em
       Display List com cache inteligente.
     - Iluminação direcional principal (GL_LIGHT0: Sol ou Lua) + preenchimento
       atmosférico hemisférico (GL_LIGHT2) + trilha de reflexo no oceano (Sol/Lua).
  3. Nuvens Procedurais Volumétricas (Vapor Semitransparente) com tonalidade
     dinâmica sincronizada ao horário do dia e suporte periódico.
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
    somado à Chase Cam e aos sistemas de partículas para continuidade sem saltos.
    """
    x_min, x_max, span_x, z_min, z_max, span_z = get_scene_bounds(scene_mode)
    old_x = float(pos[0])
    old_z = float(pos[2])

    new_x = old_x
    new_z = old_z

    if old_x < x_min or old_x >= x_max:
        new_x = ((old_x - x_min) % span_x) + x_min

    if old_z < z_min or old_z >= z_max:
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
    """
    x_min, x_max, span_x, z_min, z_max, span_z = get_scene_bounds(scene_mode)
    px, py, pz = float(player_pos[0]), float(player_pos[1]), float(player_pos[2])

    if scene_mode == 1:
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
    periódicas adjacentes visíveis, garantindo continuidade visual sem costuras.
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
# 1. SISTEMA DE CICLO DIA E NOITE (24H CONTÍNUO + PRESETS MANUAIS TECLA [C])
# ==============================================================================

SKY_DOME_RADIUS = 2200.0        # Raio da abóbada celeste esférica (dentro do zFar = 3500)
SUN_DISTANCE = 2100.0           # Distância do disco solar e lunar no céu
DAY_CYCLE_DURATION_SEC = 360.0  # 1 ciclo completo de 24h a cada 6 minutos em modo AUTO
DAY_CYCLE_HOURS_PER_SEC = 24.0 / DAY_CYCLE_DURATION_SEC

# Presets cíclicos acionados pela tecla [C]
TIME_OF_DAY_PRESETS = [
    {"id": "sunrise", "label": "AMANHECER",  "hour": 6.42},
    {"id": "noon",    "label": "MEIO-DIA",   "hour": 12.00},
    {"id": "sunset",  "label": "POR DO SOL", "hour": 17.58},
    {"id": "night",   "label": "NOITE",      "hour": 20.85},
]

# Constantes legadas mantidas por retrocompatibilidade
SUN_RISE_DURATION = DAY_CYCLE_DURATION_SEC
SUN_MIN_ELEV_DEG = 4.5
SUN_MAX_ELEV_DEG = 72.0

# Keyframes de paleta atmosférica e iluminação ao longo das 24 horas (hora, valores)
# Cada entrada define:
#   zenith, upper, mid, horizon,
#   sun_core, sun_halo,
#   light_amb, light_diff, light_spec, fill_diff, cloud_tint, star_alpha
_DAY_CYCLE_KEYFRAMES = [
    # 00:00 — Meia-noite (luar prateado e visibilidade noturna segura para voo)
    (0.0, {
        "zenith":  [0.015, 0.025, 0.075],
        "upper":   [0.025, 0.042, 0.115],
        "mid":     [0.045, 0.070, 0.165],
        "horizon": [0.075, 0.110, 0.215],
        "sun_core": [0.95, 0.45, 0.22],
        "sun_halo": [0.90, 0.28, 0.12],
        "amb":     [0.14, 0.18, 0.28],
        "diff":    [0.26, 0.32, 0.48],
        "spec":    [0.24, 0.28, 0.40],
        "fill":    [0.12, 0.16, 0.25],
        "cloud":   [0.34, 0.40, 0.56],
        "stars":   1.00,
    }),
    # 04:45 — Pré-aurora (céu noturno começando a clarear no horizonte Leste)
    (4.75, {
        "zenith":  [0.025, 0.040, 0.110],
        "upper":   [0.050, 0.075, 0.175],
        "mid":     [0.140, 0.120, 0.230],
        "horizon": [0.340, 0.180, 0.210],
        "sun_core": [1.00, 0.62, 0.30],
        "sun_halo": [0.96, 0.30, 0.12],
        "amb":     [0.17, 0.19, 0.27],
        "diff":    [0.34, 0.34, 0.44],
        "spec":    [0.26, 0.26, 0.34],
        "fill":    [0.16, 0.18, 0.26],
        "cloud":   [0.54, 0.46, 0.54],
        "stars":   0.72,
    }),
    # 06:25 — Amanhecer clássico Top Graphics (Sol baixo a Leste -Z, dourado/âmbar)
    (6.42, {
        "zenith":  [0.090, 0.155, 0.360],
        "upper":   [0.180, 0.265, 0.510],
        "mid":     [0.500, 0.355, 0.460],
        "horizon": [0.940, 0.460, 0.240],
        "sun_core": [1.00, 0.93, 0.74],
        "sun_halo": [1.00, 0.42, 0.15],
        "amb":     [0.28, 0.25, 0.28],
        "diff":    [0.60, 0.50, 0.40],
        "spec":    [0.34, 0.29, 0.22],
        "fill":    [0.24, 0.25, 0.31],
        "cloud":   [0.98, 0.80, 0.66],
        "stars":   0.04,
    }),
    # 08:30 — Manhã alta
    (8.50, {
        "zenith":  [0.150, 0.360, 0.740],
        "upper":   [0.290, 0.540, 0.860],
        "mid":     [0.560, 0.720, 0.900],
        "horizon": [0.850, 0.860, 0.840],
        "sun_core": [1.00, 0.97, 0.88],
        "sun_halo": [1.00, 0.82, 0.52],
        "amb":     [0.34, 0.35, 0.38],
        "diff":    [0.72, 0.70, 0.65],
        "spec":    [0.44, 0.43, 0.40],
        "fill":    [0.28, 0.32, 0.40],
        "cloud":   [0.98, 0.96, 0.94],
        "stars":   0.00,
    }),
    # 12:00 — Meio-Dia (Sol a pino, céu azul cristalino, luz intensa e limpa)
    (12.00, {
        "zenith":  [0.110, 0.340, 0.780],
        "upper":   [0.240, 0.530, 0.900],
        "mid":     [0.480, 0.730, 0.950],
        "horizon": [0.760, 0.880, 0.960],
        "sun_core": [1.00, 0.99, 0.95],
        "sun_halo": [1.00, 0.95, 0.78],
        "amb":     [0.38, 0.40, 0.44],
        "diff":    [0.78, 0.78, 0.76],
        "spec":    [0.50, 0.50, 0.48],
        "fill":    [0.30, 0.36, 0.45],
        "cloud":   [1.00, 1.00, 1.00],
        "stars":   0.00,
    }),
    # 15:30 — Tarde ensolarada
    (15.50, {
        "zenith":  [0.150, 0.350, 0.720],
        "upper":   [0.310, 0.520, 0.820],
        "mid":     [0.620, 0.700, 0.840],
        "horizon": [0.900, 0.800, 0.680],
        "sun_core": [1.00, 0.96, 0.84],
        "sun_halo": [1.00, 0.76, 0.42],
        "amb":     [0.34, 0.33, 0.34],
        "diff":    [0.72, 0.66, 0.56],
        "spec":    [0.42, 0.38, 0.32],
        "fill":    [0.26, 0.29, 0.36],
        "cloud":   [1.00, 0.92, 0.84],
        "stars":   0.00,
    }),
    # 17:35 — Pôr do Sol (Sol baixo a Oeste +Z, céu carmesim/violeta/laranja Top Gun)
    (17.58, {
        "zenith":  [0.105, 0.115, 0.295],
        "upper":   [0.240, 0.165, 0.360],
        "mid":     [0.620, 0.280, 0.320],
        "horizon": [0.980, 0.390, 0.170],
        "sun_core": [1.00, 0.86, 0.58],
        "sun_halo": [1.00, 0.32, 0.11],
        "amb":     [0.27, 0.21, 0.25],
        "diff":    [0.62, 0.42, 0.30],
        "spec":    [0.36, 0.26, 0.18],
        "fill":    [0.22, 0.20, 0.28],
        "cloud":   [0.98, 0.66, 0.50],
        "stars":   0.10,
    }),
    # 19:00 — Crepúsculo (Blue Hour, primeiras estrelas aparecendo)
    (19.00, {
        "zenith":  [0.030, 0.045, 0.130],
        "upper":   [0.065, 0.080, 0.200],
        "mid":     [0.170, 0.135, 0.255],
        "horizon": [0.380, 0.200, 0.220],
        "sun_core": [0.96, 0.48, 0.22],
        "sun_halo": [0.92, 0.26, 0.12],
        "amb":     [0.18, 0.19, 0.28],
        "diff":    [0.34, 0.34, 0.46],
        "spec":    [0.26, 0.27, 0.36],
        "fill":    [0.16, 0.18, 0.27],
        "cloud":   [0.52, 0.46, 0.58],
        "stars":   0.78,
    }),
    # 20:50 — Noite estrelada com Lua cheia elevada à frente
    (20.85, {
        "zenith":  [0.015, 0.025, 0.075],
        "upper":   [0.025, 0.042, 0.115],
        "mid":     [0.045, 0.070, 0.165],
        "horizon": [0.075, 0.110, 0.215],
        "sun_core": [0.95, 0.45, 0.22],
        "sun_halo": [0.90, 0.28, 0.12],
        "amb":     [0.14, 0.18, 0.28],
        "diff":    [0.26, 0.32, 0.48],
        "spec":    [0.24, 0.28, 0.40],
        "fill":    [0.12, 0.16, 0.25],
        "cloud":   [0.34, 0.40, 0.56],
        "stars":   1.00,
    }),
    # 24:00 — Fechamento periódico exato com 00:00
    (24.0, {
        "zenith":  [0.015, 0.025, 0.075],
        "upper":   [0.025, 0.042, 0.115],
        "mid":     [0.045, 0.070, 0.165],
        "horizon": [0.075, 0.110, 0.215],
        "sun_core": [0.95, 0.45, 0.22],
        "sun_halo": [0.90, 0.28, 0.12],
        "amb":     [0.14, 0.18, 0.28],
        "diff":    [0.26, 0.32, 0.48],
        "spec":    [0.24, 0.28, 0.40],
        "fill":    [0.12, 0.16, 0.25],
        "cloud":   [0.34, 0.40, 0.56],
        "stars":   1.00,
    }),
]

# Campo estelar determinístico na abóbada celeste (420 estrelas)
def _generate_starfield(count=420):
    rng = np.random.default_rng(198605)
    stars = []
    for _ in range(count):
        # Distribuição uniforme sobre a calota celeste (elevação entre 3° e 88°)
        u = float(rng.uniform(0.05, 1.0))
        elev = math.asin(u)
        azim = float(rng.uniform(0.0, 2.0 * math.pi))
        r = SKY_DOME_RADIUS * 0.96
        x = r * math.cos(elev) * math.sin(azim)
        y = r * math.sin(elev)
        z = -r * math.cos(elev) * math.cos(azim)
        bright = float(rng.uniform(0.45, 1.0))
        size = float(rng.choice([1.4, 1.8, 2.3, 3.0], p=[0.48, 0.32, 0.15, 0.05]))
        # Variação realista de temperatura espectral (azuladas, brancas, amareladas)
        tint_pick = float(rng.random())
        if tint_pick < 0.28:
            col = (0.78 * bright, 0.88 * bright, 1.00 * bright)
        elif tint_pick < 0.82:
            col = (0.96 * bright, 0.97 * bright, 1.00 * bright)
        else:
            col = (1.00 * bright, 0.92 * bright, 0.78 * bright)
        stars.append((x, y, z, col[0], col[1], col[2], size))
    return stars


_SKY_STARS = _generate_starfield(420)

# Cache interno de Display List para o Sky Dome
_sky_dome_cache = {
    "dlist": None,
    "last_key": None,
}


def get_phase_label_for_hour(hour):
    """Retorna o rótulo da fase do ciclo solar para uma hora em [0..24)."""
    h = float(hour) % 24.0
    if 5.2 <= h < 8.5:
        return "AMANHECER"
    elif 8.5 <= h < 16.0:
        return "MEIO-DIA"
    elif 16.0 <= h < 19.2:
        return "POR DO SOL"
    return "NOITE"


def format_clock_hhmm(hour):
    """Formata uma hora decimal (ex: 6.42) em string 'HH:MM'."""
    h = float(hour) % 24.0
    hh = int(h)
    mm = int((h - hh) * 60.0)
    return f"{hh:02d}:{mm:02d}"


def _sample_day_keyframes(hour):
    """Interpola suavemente todos os parâmetros atmosféricos para a hora [0..24)."""
    h = float(hour) % 24.0
    for idx in range(len(_DAY_CYCLE_KEYFRAMES) - 1):
        h0, k0 = _DAY_CYCLE_KEYFRAMES[idx]
        h1, k1 = _DAY_CYCLE_KEYFRAMES[idx + 1]
        if h0 <= h <= h1:
            u = (h - h0) / max(1e-5, (h1 - h0))
            u = u * u * (3.0 - 2.0 * u)  # Smoothstep
            res = {}
            for key in k0:
                v0 = k0[key]
                v1 = k1[key]
                if isinstance(v0, list):
                    res[key] = (1.0 - u) * np.array(v0, dtype=np.float32) + u * np.array(v1, dtype=np.float32)
                else:
                    res[key] = float((1.0 - u) * v0 + u * v1)
            return res
    # Fallback seguro
    return {k: (np.array(v, dtype=np.float32) if isinstance(v, list) else float(v)) for k, v in _DAY_CYCLE_KEYFRAMES[0][1].items()}


def get_sun_state(sim_time, scene_mode=1, time_of_day_hours=None):
    """
    Calcula a astronomia completa do ciclo Dia/Noite (Sol, Lua, Estrelas, Abóbada Celeste
    e Iluminação Direcional + Hemisférica):
      - Se 'time_of_day_hours' for fornecido (0..24), usa esse horário diretamente.
      - Caso contrário, deriva o horário continuamente a partir de 'sim_time' iniciando em 06:25.
    """
    if time_of_day_hours is None:
        hour = (6.42 + float(sim_time) * DAY_CYCLE_HOURS_PER_SEC) % 24.0
    else:
        hour = float(time_of_day_hours) % 24.0

    # Ângulo solar: 06:00 = 0 rad (Leste -Z), 12:00 = pi/2 (Alto), 18:00 = pi (Oeste +Z)
    theta = ((hour - 6.0) / 24.0) * (2.0 * math.pi)
    orbit_tilt = math.radians(18.0)  # Inclinação orbital para Sul (+X), gerando sombras 3D ao meio-dia

    sun_x = math.sin(theta) * math.sin(orbit_tilt)
    sun_y = math.sin(theta) * math.cos(orbit_tilt)
    sun_z = -math.cos(theta)
    sun_dir = normalize(np.array([sun_x, sun_y, sun_z], dtype=np.float32))
    sun_elev_deg = math.degrees(math.asin(float(np.clip(sun_dir[1], -1.0, 1.0))))

    # Posição da Lua (oposta ao Sol no ciclo de 24h -> ergue-se a Leste -Z ao anoitecer!)
    moon_theta = theta - math.pi
    moon_x = math.sin(moon_theta) * math.sin(orbit_tilt)
    moon_y = math.sin(moon_theta) * math.cos(orbit_tilt)
    moon_z = -math.cos(moon_theta)
    moon_dir = normalize(np.array([moon_x, moon_y, moon_z], dtype=np.float32))
    moon_elev_deg = math.degrees(math.asin(float(np.clip(moon_dir[1], -1.0, 1.0))))

    kf = _sample_day_keyframes(hour)

    zenith_color = kf["zenith"].copy()
    upper_sky_color = kf["upper"].copy()
    mid_sky_color = kf["mid"].copy()
    horizon_color = kf["horizon"].copy()

    # Leve aquecimento desértico no horizonte do Cânion durante o dia/crepúsculo
    if scene_mode == 2:
        day_weight = float(np.clip((sun_elev_deg + 8.0) / 30.0, 0.0, 1.0))
        horizon_color = np.clip(horizon_color + np.array([0.05, 0.01, -0.04], dtype=np.float32) * day_weight, 0.0, 1.0)
        mid_sky_color = np.clip(mid_sky_color + np.array([0.04, 0.00, -0.04], dtype=np.float32) * day_weight, 0.0, 1.0)

    # Fator de presença solar vs lunar
    sun_visibility = float(np.clip((sun_elev_deg + 4.0) / 8.0, 0.0, 1.0))
    moon_visibility = float(np.clip((moon_elev_deg + 3.0) / 10.0, 0.0, 1.0) * np.clip((-sun_elev_deg + 4.0) / 14.0, 0.0, 1.0))
    is_night = (sun_elev_deg < -4.0)

    # Direção de iluminação principal (GL_LIGHT0):
    # Usa o Sol durante o dia e a Lua à noite, mantendo elevação mínima de 24°
    # para iluminar o convés, o F-14 e os paredões do cânion sem estouro rasante.
    active_celestial = moon_dir if is_night else sun_dir
    act_elev = max(24.0, math.degrees(math.asin(float(np.clip(active_celestial[1], -1.0, 1.0)))))
    horiz_len = math.hypot(float(active_celestial[0]), float(active_celestial[2]))
    if horiz_len > 1e-4:
        hx = float(active_celestial[0]) / horiz_len
        hz = float(active_celestial[2]) / horiz_len
    else:
        hx, hz = 0.0, -1.0

    act_rad = math.radians(act_elev)
    light_dir = normalize(np.array([
        math.cos(act_rad) * hx,
        math.sin(act_rad),
        math.cos(act_rad) * hz,
    ], dtype=np.float32))

    fill_dir = normalize(np.array([-light_dir[0] * 0.72, 0.68, -light_dir[2] * 0.72], dtype=np.float32))

    # Brilho ambiente normalizado [0.22 à noite .. 1.0 ao meio-dia] para tintagem de partículas/poeira/spray
    daylight_factor = float(np.clip((sun_elev_deg + 10.0) / 38.0, 0.0, 1.0))

    light_ambient = [float(kf["amb"][0]), float(kf["amb"][1]), float(kf["amb"][2]), 1.0]
    light_diffuse = [float(kf["diff"][0]), float(kf["diff"][1]), float(kf["diff"][2]), 1.0]
    light_specular = [float(kf["spec"][0]), float(kf["spec"][1]), float(kf["spec"][2]), 1.0]
    fill_diffuse = [float(kf["fill"][0]), float(kf["fill"][1]), float(kf["fill"][2]), 1.0]

    return {
        "hour": hour,
        "clock_str": format_clock_hhmm(hour),
        "phase_label": get_phase_label_for_hour(hour),
        "is_night": is_night,
        "daylight_factor": daylight_factor,
        "dir": sun_dir,
        "moon_dir": moon_dir,
        "light_dir": light_dir,
        "fill_dir": fill_dir,
        "progress": (hour / 24.0),
        "elev_deg": sun_elev_deg,
        "moon_elev_deg": moon_elev_deg,
        "sun_visibility": sun_visibility,
        "moon_visibility": moon_visibility,
        "star_alpha": float(kf["stars"]),
        "scene_mode": scene_mode,
        "zenith_color": zenith_color,
        "upper_sky_color": upper_sky_color,
        "mid_sky_color": mid_sky_color,
        "horizon_color": horizon_color,
        "sun_core_color": kf["sun_core"],
        "sun_halo_color": kf["sun_halo"],
        "moon_core_color": np.array([0.92, 0.95, 1.00], dtype=np.float32),
        "moon_halo_color": np.array([0.46, 0.62, 0.90], dtype=np.float32),
        "cloud_tint": kf["cloud"],
        "light_ambient": light_ambient,
        "light_diffuse": light_diffuse,
        "light_specular": light_specular,
        "fill_diffuse": fill_diffuse,
    }


def apply_sunrise_lighting(sun_state, lighting_enabled=True):
    """
    Atualiza a cor de fundo (glClearColor) e configura GL_LIGHT0 (Sol ou Lua) +
    GL_LIGHT2 (Preenchimento Atmosférico) conforme o horário atual do ciclo Dia/Noite.
    """
    zc = sun_state["zenith_color"]
    glClearColor(float(zc[0]), float(zc[1]), float(zc[2]), 1.0)

    if lighting_enabled:
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT2)

        # Ajusta luz ambiente global suavemente entre dia (0.18) e noite (0.10)
        df = sun_state.get("daylight_factor", 0.6)
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [
            0.09 + 0.09 * df,
            0.10 + 0.08 * df,
            0.15 + 0.04 * df,
            1.0
        ])

        ldir = sun_state["light_dir"]
        fdir = sun_state["fill_dir"]

        glLightfv(GL_LIGHT0, GL_POSITION, [float(ldir[0]), float(ldir[1]), float(ldir[2]), 0.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, sun_state["light_ambient"])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, sun_state["light_diffuse"])
        glLightfv(GL_LIGHT0, GL_SPECULAR, sun_state["light_specular"])

        glLightfv(GL_LIGHT2, GL_POSITION, [float(fdir[0]), float(fdir[1]), float(fdir[2]), 0.0])
        glLightfv(GL_LIGHT2, GL_AMBIENT, [0.0, 0.0, 0.0, 1.0])
        glLightfv(GL_LIGHT2, GL_DIFFUSE, sun_state["fill_diffuse"])
        glLightfv(GL_LIGHT2, GL_SPECULAR, [0.0, 0.0, 0.0, 1.0])
    else:
        glDisable(GL_LIGHTING)


def _compute_sky_dome_vertex_color(elev_deg, azim_sin, azim_cos, sun_state):
    """
    Calcula a cor exata (r, g, b) de um vértice da abóbada celeste esférica
    com espalhamento atmosférico direcional em torno do Sol (ou brilho sutil da Lua).
    """
    hc = sun_state["horizon_color"]
    mc = sun_state["mid_sky_color"]
    uc = sun_state["upper_sky_color"]
    zc = sun_state["zenith_color"]

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

    r, g, b = float(base_col[0]), float(base_col[1]), float(base_col[2])

    # Brilho de espalhamento no horizonte na direção do Sol (forte no amanhecer/pôr do sol)
    sun_vis = sun_state.get("sun_visibility", 1.0)
    low_sun_factor = float(np.clip(1.0 - abs(sun_state["elev_deg"]) / 42.0, 0.0, 1.0))
    elev_atten = max(0.0, 1.0 - max(0.0, elev_deg) / 55.0) ** 2.0

    if sun_vis > 0.01 and elev_atten > 1e-4:
        sdir = sun_state["dir"]
        horiz_dot = max(0.0, azim_sin * float(sdir[0]) + (-azim_cos) * float(sdir[2]))
        glow_boost = (horiz_dot ** 3.0) * (0.14 + 0.28 * low_sun_factor) * elev_atten * sun_vis
        sh = sun_state["sun_halo_color"]
        r = min(1.0, r + glow_boost * float(sh[0]))
        g = min(1.0, g + glow_boost * float(sh[1]) * 0.72)
        b = min(1.0, b + glow_boost * float(sh[2]) * 0.55)

    # Brilho prateado suave no horizonte na direção da Lua à noite
    moon_vis = sun_state.get("moon_visibility", 0.0)
    if moon_vis > 0.05 and elev_atten > 1e-4:
        mdir = sun_state["moon_dir"]
        m_dot = max(0.0, azim_sin * float(mdir[0]) + (-azim_cos) * float(mdir[2]))
        m_boost = (m_dot ** 3.0) * 0.12 * elev_atten * moon_vis
        r = min(1.0, r + m_boost * 0.60)
        g = min(1.0, g + m_boost * 0.78)
        b = min(1.0, b + m_boost * 1.00)

    return r, g, b


def _draw_celestial_disc(celestial_dir, halo_layers, fan_segs=26):
    """Desenha um astro (Sol ou Lua) e suas coroas de difração a SUN_DISTANCE."""
    pos = celestial_dir * SUN_DISTANCE
    ref_up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    if abs(float(celestial_dir[1])) > 0.96:
        ref_up = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    c_right = normalize(np.cross(celestial_dir, ref_up))
    c_up = normalize(np.cross(c_right, celestial_dir))

    for radius, center_rgba, edge_rgba in halo_layers:
        glBegin(GL_TRIANGLE_FAN)
        glColor4f(*center_rgba)
        glVertex3f(float(pos[0]), float(pos[1]), float(pos[2]))
        glColor4f(*edge_rgba)
        for i in range(fan_segs + 1):
            ang = (2.0 * math.pi * i) / fan_segs
            offset = c_right * (math.cos(ang) * radius) + c_up * (math.sin(ang) * radius)
            pt = pos + offset
            glVertex3f(float(pt[0]), float(pt[1]), float(pt[2]))
        glEnd()


def _compile_sky_dome_display_list(sun_state):
    """
    Compila a abóbada celeste esférica, estrelas noturnas, Sol e Lua em Display List.
    """
    if _sky_dome_cache["dlist"] is None:
        _sky_dome_cache["dlist"] = glGenLists(1)

    dlist = _sky_dome_cache["dlist"]
    glNewList(dlist, GL_COMPILE)

    zc = sun_state["zenith_color"]
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

    # 4. Campo Estelar (visível no crepúsculo e durante toda a noite)
    star_alpha = sun_state.get("star_alpha", 0.0)
    if star_alpha > 0.02:
        glEnable(GL_POINT_SMOOTH)
        for size_bucket in (1.4, 1.8, 2.3, 3.0):
            glPointSize(size_bucket)
            glBegin(GL_POINTS)
            for sx, sy, sz, cr, cg, cb, s_sz in _SKY_STARS:
                if abs(s_sz - size_bucket) < 0.1:
                    glColor4f(cr, cg, cb, star_alpha)
                    glVertex3f(sx, sy, sz)
            glEnd()
        glPointSize(1.0)

    # 5. Disco Solar e Coroas de Difração (durante o dia, amanhecer e pôr do sol)
    sun_vis = sun_state.get("sun_visibility", 1.0)
    if sun_vis > 0.01:
        sc = sun_state["sun_core_color"]
        sh = sun_state["sun_halo_color"]
        sun_layers = [
            (540.0, (float(sh[0]), float(sh[1]) * 0.78, float(sh[2]) * 0.55, 0.22 * sun_vis),
                    (float(sh[0]), float(sh[1]) * 0.78, float(sh[2]) * 0.55, 0.0)),
            (285.0, (float(sh[0]), float(sh[1]),        float(sh[2]),       0.38 * sun_vis),
                    (float(sh[0]), float(sh[1]),        float(sh[2]),       0.0)),
            (138.0, (float(sc[0]), float(sc[1]) * 0.94, float(sc[2]) * 0.75, 0.65 * sun_vis),
                    (float(sc[0]), float(sc[1]) * 0.94, float(sc[2]) * 0.75, 0.0)),
            ( 72.0, (1.0, 0.99, 0.94, 0.98 * sun_vis),
                    (float(sc[0]), float(sc[1]),        float(sc[2]),       0.86 * sun_vis)),
        ]
        _draw_celestial_disc(sun_state["dir"], sun_layers)

    # 6. Lua Cheia e Halo Prateado (durante a noite e crepúsculo)
    moon_vis = sun_state.get("moon_visibility", 0.0)
    if moon_vis > 0.02:
        mc = sun_state["moon_core_color"]
        mh = sun_state["moon_halo_color"]
        moon_layers = [
            (380.0, (float(mh[0]), float(mh[1]), float(mh[2]), 0.16 * moon_vis),
                    (float(mh[0]), float(mh[1]), float(mh[2]), 0.0)),
            (180.0, (float(mh[0]) * 1.15, float(mh[1]) * 1.12, float(mh[2]), 0.28 * moon_vis),
                    (float(mh[0]), float(mh[1]), float(mh[2]), 0.0)),
            ( 66.0, (float(mc[0]), float(mc[1]), float(mc[2]), 0.96 * moon_vis),
                    (0.76, 0.82, 0.92, 0.84 * moon_vis)),
        ]
        _draw_celestial_disc(sun_state["moon_dir"], moon_layers)

    glEndList()


def draw_rising_sun_and_sky(anchor_pos, sun_state, scene_mode=1):
    """
    Renderiza a abóbada celeste esférica completa (céu, estrelas, Sol e Lua)
    usando Display List em cache, centrada na posição da aeronave.
    """
    # Atualiza o cache quando a hora muda em ~0.02h (~1.2 min simulado) ou ao trocar de cena
    cache_key = (scene_mode, int(round(sun_state["hour"] * 50.0)))
    if _sky_dome_cache["last_key"] != cache_key or _sky_dome_cache["dlist"] is None:
        _compile_sky_dome_display_list(sun_state)
        _sky_dome_cache["last_key"] = cache_key

    glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT | GL_POLYGON_BIT | GL_POINT_BIT)
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
    Desenha a trilha de reflexo cintilante do Sol (de dia/amanhecer/pôr do sol) ou
    da Lua (à noite — brilho prateado) sobre o oceano na Cena 1.
    """
    is_night = sun_state.get("is_night", False)
    if is_night:
        vis = sun_state.get("moon_visibility", 0.0)
        cdir = sun_state["moon_dir"]
        c_core = sun_state["moon_core_color"]
        c_halo = sun_state["moon_halo_color"]
        strength = 0.72 * vis
    else:
        vis = sun_state.get("sun_visibility", 1.0)
        cdir = sun_state["dir"]
        c_core = sun_state["sun_core_color"]
        c_halo = sun_state["sun_halo_color"]
        # Mais intenso com sol mais baixo, suave ao meio-dia
        low_boost = 0.60 + 0.40 * float(np.clip(1.0 - sun_state["elev_deg"] / 70.0, 0.0, 1.0))
        strength = vis * low_boost

    if strength < 0.03:
        return

    horiz_len = math.hypot(float(cdir[0]), float(cdir[2]))
    if horiz_len < 0.08:
        return

    glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glDepthMask(GL_FALSE)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    horiz_dir = normalize(np.array([cdir[0], 0.0, cdir[2]], dtype=np.float32))
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

        alpha = (0.12 + 0.14 * (i / float(num_strips))) * shimmer * strength
        glColor4f(
            float(0.75 * c_core[0] + 0.25 * c_halo[0]),
            float(0.75 * c_core[1] + 0.25 * c_halo[1]),
            float(0.65 * c_core[2] + 0.35 * c_halo[2]),
            alpha
        )
        glVertex3f(float(p1[0]), 0.18, float(p1[2]))
        glVertex3f(float(p2[0]), 0.18, float(p2[2]))
        glVertex3f(float(p3[0]), 0.18, float(p3[2]))
        glVertex3f(float(p4[0]), 0.18, float(p4[2]))
    glEnd()

    glPopAttrib()


# ==============================================================================
# 2. NUVENS PROCEDURAIS (VAPOR SEMITRANSPARENTE COM TINTAGEM DIA/NOITE)
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
    Compila um banco de nuvem individual usando tons neutros de altura (0.76..1.0)
    para que a iluminação ambiente em draw_procedural_clouds aplique a cor exata do
    Amanhecer, Meio-Dia, Pôr do Sol ou Noite sem recompilar a Display List.
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
            glColor4f(0.78, 0.76, 0.78, 0.34)
        elif height_factor < 0.72:
            glColor4f(0.90, 0.90, 0.91, 0.38)
        else:
            glColor4f(1.00, 1.00, 1.00, 0.42)

        glPushMatrix()
        glTranslatef(cx + ox, cy + oy, cz + oz)
        glRotatef(yaw_deg, 0.0, 1.0, 0.0)
        glRotatef(tilt_x, 1.0, 0.0, 0.0)
        glRotatef(tilt_z, 0.0, 0.0, 1.0)

        glNormal3f(0.0, 1.0, 0.0)
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


def draw_procedural_clouds(clouds_dlist, cloud_tex_id, sim_time, player_pos=None, scene_mode=1, sun_state=None):
    """
    Renderiza a camada de nuvens procedurais como vapor semitransparente, tintada em
    hardware de acordo com o horário atual do ciclo Dia/Noite (sun_state).
    """
    glPushAttrib(GL_ENABLE_BIT | GL_LIGHTING_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT | GL_POLYGON_BIT)
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, cloud_tex_id)

    # Usa GL_LIGHT_MODEL_AMBIENT (sem luzes direcionais) para multiplicar os tons neutros
    # da Display List pela cor atmosférica da hora atual sem recompilar geometria!
    if sun_state is not None and "cloud_tint" in sun_state:
        ct = sun_state["cloud_tint"]
        glEnable(GL_LIGHTING)
        glDisable(GL_LIGHT0)
        glDisable(GL_LIGHT1)
        glDisable(GL_LIGHT2)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.0, 0.0, 0.0, 1.0])
        glMaterialfv(GL_FRONT_AND_BACK, GL_EMISSION, [0.0, 0.0, 0.0, 1.0])
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [float(ct[0]), float(ct[1]), float(ct[2]), 1.0])
    else:
        glDisable(GL_LIGHTING)

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
