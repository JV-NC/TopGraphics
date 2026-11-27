"""
================================================================================
TopGraphics | scene_canyon.py
Cena 2: cânion procedural ("Trench Run"), usando sandstone.png em toda a cena.
  - Função matemática 100% periódica (C-infinito nas bordas X = +-360 e Z = -1500..+500)
    para permitir o efeito Roundabout (mapa infinito).
  - Sistema Físico de Partículas de Poeira e Areia (CanyonDustSystem):
      * Levanta plumas volumétricas de poeira arenítica (vórtices de ponta de asa e
        sopro das turbinas) e grãos balísticos de terra/cascalho durante voos rasantes
        próximos ao solo ou às encostas/paredões do cânion.
      * Dispara nuvem de impacto em colisões, acompanha o teleporte Roundabout sem
        saltos e adapta a tonalidade automaticamente ao ciclo Dia/Noite.
  - Exporta a função matemática do terreno e a checagem de colisão com as rochas.
================================================================================
"""

import math

import numpy as np
from OpenGL.GL import *

from math_utils import compute_normal
from renderer_utils import draw_box, upload_texture_rgb, load_texture_from_assets
from scene_utils import (
    SCENE2_X_MIN, SCENE2_X_MAX, SCENE2_SPAN_X,
    SCENE2_Z_MIN, SCENE2_Z_MAX, SCENE2_SPAN_Z,
)

# ==============================================================================
# CONSTANTES DO TERRENO PERIÓDICO (ROUNDABOUT)
# ==============================================================================

CANYON_BUNKER_Z = -1150.0   # Posição Z do bunker alvo em cada ciclo do cânion

# Frequências angulares fundamentais (garantem f(x + Lx, z + Lz) == f(x, z) exato)
_OMEGA_X = (2.0 * math.pi) / SCENE2_SPAN_X   # 2*pi / 720.0
_OMEGA_Z = (2.0 * math.pi) / SCENE2_SPAN_Z   # 2*pi / 2000.0


def _wrap_canyon_xz(x, z):
    """Mapeia qualquer coordenada (x, z) para a célula fundamental do cânion."""
    xw = ((x - SCENE2_X_MIN) % SCENE2_SPAN_X) + SCENE2_X_MIN
    zw = ((z - SCENE2_Z_MIN) % SCENE2_SPAN_Z) + SCENE2_Z_MIN
    return xw, zw


def canyon_center_x(z):
    """
    Coordenada X do eixo central sinuoso do cânion na profundidade z.
    Usa harmônicos inteiros (1 e 3) de _OMEGA_Z para fechar um ciclo perfeito a cada 2000m.
    """
    return 55.0 * math.sin(1.0 * _OMEGA_Z * z) + 25.0 * math.cos(3.0 * _OMEGA_Z * z)


def canyon_height_func(x, z):
    """
    Função matemática f(x, z) periódica que esculpe um corredor sinuoso ("Trench Run")
    com fundo plano navegável e paredões rochosos escarpados nas laterais.
    """
    xw, zw = _wrap_canyon_xz(x, z)
    center_x = canyon_center_x(zw)
    dist = abs(xw - center_x)

    canyon_wall = max(0.0, dist - 42.0)
    wall_height = min(165.0, (canyon_wall ** 1.35) * 0.65)

    roughness = (
        14.0 * math.sin(5.0 * _OMEGA_X * xw) * math.cos(14.0 * _OMEGA_Z * zw)
        + 7.0 * math.sin(13.0 * _OMEGA_X * xw + 28.0 * _OMEGA_Z * zw)
    )
    if dist < 42.0:
        return 2.0 + 1.2 * math.sin(9.0 * _OMEGA_X * xw) * math.cos(25.0 * _OMEGA_Z * zw)
    return max(2.0, wall_height + roughness)


def _canyon_height_vec(x_arr, z_arr):
    """Versão vetorizada em NumPy de canyon_height_func para física de partículas 3D."""
    xw = ((x_arr - SCENE2_X_MIN) % SCENE2_SPAN_X) + SCENE2_X_MIN
    zw = ((z_arr - SCENE2_Z_MIN) % SCENE2_SPAN_Z) + SCENE2_Z_MIN
    center_x = 55.0 * np.sin(1.0 * _OMEGA_Z * zw) + 25.0 * np.cos(3.0 * _OMEGA_Z * zw)
    dist = np.abs(xw - center_x)

    canyon_wall = np.maximum(0.0, dist - 42.0)
    wall_height = np.minimum(165.0, (canyon_wall ** 1.35) * 0.65)
    roughness = (
        14.0 * np.sin(5.0 * _OMEGA_X * xw) * np.cos(14.0 * _OMEGA_Z * zw)
        + 7.0 * np.sin(13.0 * _OMEGA_X * xw + 28.0 * _OMEGA_Z * zw)
    )
    floor_h = 2.0 + 1.2 * np.sin(9.0 * _OMEGA_X * xw) * np.cos(25.0 * _OMEGA_Z * zw)
    wall_h = np.maximum(2.0, wall_height + roughness)
    return np.where(dist < 42.0, floor_h, wall_h).astype(np.float32)


def _generate_canyon_boulders():
    """
    Gera de forma determinística (seed fixo) a lista de rochas/matacões 3D
    distribuídos ao longo do leito e das encostas do cânion (entre Z = +230 e Z = -1050).
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
    das rochas procedurais 3D do Cenário 2 (considerando coordenadas periódicas).
    """
    sample_points = [pos]
    if right_vec is not None:
        sample_points.append(pos + right_vec * 4.5)
        sample_points.append(pos - right_vec * 4.5)
    if forward_vec is not None:
        sample_points.append(pos + forward_vec * 4.8)

    for pt in sample_points:
        px, pz = _wrap_canyon_xz(float(pt[0]), float(pt[2]))
        py = float(pt[1])
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
    """Fallback procedural 256x128 100% periódico (seamless) caso sandstone não seja encontrado."""
    h, w = 128, 256
    ys = np.linspace(0.0, 2.0 * math.pi, h, endpoint=False, dtype=np.float32)[:, None]
    xs = np.linspace(0.0, 2.0 * math.pi, w, endpoint=False, dtype=np.float32)[None, :]
    strata = 18.0 * np.sin(5.0 * ys + 0.4 * np.sin(2.0 * xs)) + 14.0 * np.cos(2.0 * ys)
    grain = 8.0 * np.sin(11.0 * xs + 4.0 * ys) + 4.0 * np.cos(19.0 * xs - 7.0 * ys)
    r = np.clip(158.0 + strata + grain, 90.0, 220.0)
    g = np.clip(108.0 + strata * 0.72 + grain * 0.8, 60.0, 170.0)
    b = np.clip(74.0 + strata * 0.52 + grain * 0.6, 40.0, 125.0)
    img = np.stack([r, g, b], axis=-1).astype(np.uint8)
    return upload_texture_rgb(img, mirrored_repeat=False, use_mipmaps=True)


def create_canyon_texture():
    """
    Carrega sandstone.png/.jpg em resolução 1024x512 (preservando a proporção 2:1
    dos estratos horizontais), equalizado e convertido em tile seamless para GL_REPEAT.
    """
    return load_texture_from_assets(
        "sandstone.png",
        fallback_fn=_create_procedural_canyon_texture,
        mode="rock",
        target_size=(1024, 512),
        mirrored_repeat=False,
    )


# ==============================================================================
# SISTEMA FÍSICO DE PARTÍCULAS DE POEIRA E AREIA EM VOO RASANTE (CANYON DUST)
# ==============================================================================

def _create_dust_particle_texture():
    """
    Gera textura RGBA 64x64 procedural de nuvem turbulenta de poeira/areia com
    bordas macias e granulação interna sutil (para Billboards 3D sem costuras).
    """
    size = 64
    xs = np.linspace(-1.0, 1.0, size, dtype=np.float32)
    ys = np.linspace(-1.0, 1.0, size, dtype=np.float32)
    xv, yv = np.meshgrid(xs, ys)
    r2 = xv * xv + yv * yv

    radial = np.clip(1.0 - r2, 0.0, 1.0) ** 1.85
    # Ruído orgânico multi-frequência simulando grãos e redemoinho de areia
    swirl = (
        0.55
        + 0.25 * np.sin(xv * 4.5 + np.cos(yv * 4.2))
        + 0.14 * np.cos(yv * 8.0 - xv * 6.5)
        + 0.06 * np.sin((xv - yv) * 14.0)
    )
    alpha = np.clip(radial * swirl * 1.15, 0.0, 1.0)

    # Gradiente interno suave (mais claro no topo iluminado, mais denso no núcleo)
    lum = np.clip(226.0 + 24.0 * (0.25 - yv * 0.65) - 18.0 * r2, 185.0, 255.0).astype(np.uint8)

    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[:, :, 0] = lum
    rgba[:, :, 1] = np.clip(lum.astype(np.int16) - 6, 0, 255).astype(np.uint8)
    rgba[:, :, 2] = np.clip(lum.astype(np.int16) - 14, 0, 255).astype(np.uint8)
    rgba[:, :, 3] = (alpha * 235.0).astype(np.uint8)

    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba)
    return tex_id


class CanyonDustSystem:
    """
    Simulador Físico de Partículas de Poeira, Areia e Terra na Cena 2 (Cânion):
      - Detecta voos rasantes sobre o leito do cânion (AGL < 38m) e passagens
        rente aos paredões laterais (distância lateral às encostas).
      - Gera duas camadas físicas distintas:
          * Tipo 0 (Plumas de Poeira Arenítica): nuvens volumétricas que se
            expandem, sobem e giram em vórtices duplos atrás das asas/turbinas.
          * Tipo 1 (Terra e Areia Grossa Balística): partículas densas e escuras
            arremessadas pelo sopro dos pós-combustores que caem sob gravidade.
      - Renderizado via OpenGL Client Arrays (glDrawArrays) 100% vetorizado em NumPy.
    """

    MAX_PARTICLES = 1600
    LOW_PASS_MAX_AGL = 38.0    # Altura máxima acima do terreno (AGL) para levantar poeira

    def __init__(self):
        self.dust_tex_id = None
        self.sim_time = 0.0
        self._prev_crashed = False

        # Buffers circulares de partículas (100% vetorizados em NumPy)
        self.p_pos = np.zeros((self.MAX_PARTICLES, 3), dtype=np.float32)
        self.p_vel = np.zeros((self.MAX_PARTICLES, 3), dtype=np.float32)
        self.p_life = np.zeros(self.MAX_PARTICLES, dtype=np.float32)
        self.p_max_life = np.ones(self.MAX_PARTICLES, dtype=np.float32)
        self.p_size = np.ones(self.MAX_PARTICLES, dtype=np.float32)
        # p_type: 0 = Nuvem/Pluma de Poeira (expansiva), 1 = Grão de Terra/Areia (balístico)
        self.p_type = np.zeros(self.MAX_PARTICLES, dtype=np.int32)
        # Variação tonal individual por partícula [0.82 .. 1.14]
        self.p_shade = np.ones(self.MAX_PARTICLES, dtype=np.float32)
        self.spawn_cursor = 0

        # Buffers de renderização para Billboard Quads (4 vértices por partícula)
        self.quad_verts = np.zeros((self.MAX_PARTICLES * 4, 3), dtype=np.float32)
        self.quad_uvs = np.zeros((self.MAX_PARTICLES * 4, 2), dtype=np.float32)
        self.quad_uvs[0::4] = [0.0, 0.0]
        self.quad_uvs[1::4] = [1.0, 0.0]
        self.quad_uvs[2::4] = [1.0, 1.0]
        self.quad_uvs[3::4] = [0.0, 1.0]
        self.quad_colors = np.zeros((self.MAX_PARTICLES * 4, 4), dtype=np.float32)

        self._rng = np.random.default_rng(2026)

    def reset(self):
        """Limpa todas as partículas ativas (ao trocar de cena ou reiniciar com [R])."""
        self.p_life.fill(0.0)
        self.spawn_cursor = 0
        self._prev_crashed = False

    def spawn_particles(self, positions, velocities, lifetimes, sizes, p_types):
        """Insere um lote de partículas de poeira/areia no buffer circular."""
        count = len(positions)
        if count <= 0:
            return
        idx = (np.arange(count) + self.spawn_cursor) % self.MAX_PARTICLES
        self.spawn_cursor = (self.spawn_cursor + count) % self.MAX_PARTICLES

        self.p_pos[idx] = positions
        self.p_vel[idx] = velocities
        self.p_life[idx] = lifetimes
        self.p_max_life[idx] = np.maximum(0.08, lifetimes)
        self.p_size[idx] = sizes
        self.p_type[idx] = p_types
        self.p_shade[idx] = self._rng.uniform(0.84, 1.14, count).astype(np.float32)

    def trigger_impact_burst(self, x, y, z, intensity=2.2):
        """Dispara uma nuvem densa de poeira e detritos arenosos no ponto de colisão."""
        n_plume = min(180, int(75 * intensity))
        n_grit = min(140, int(60 * intensity))
        ground_y = canyon_height_func(x, z)
        base_y = max(y, ground_y + 0.6)

        # 1. Nuvem de poeira em expansão radial
        ang1 = self._rng.uniform(0.0, 2.0 * math.pi, n_plume)
        spd_h1 = self._rng.uniform(4.0, 22.0 * intensity, n_plume)
        spd_v1 = self._rng.uniform(3.5, 16.0 * intensity, n_plume)
        pos1 = np.column_stack([
            x + np.cos(ang1) * self._rng.uniform(0.5, 4.0, n_plume),
            base_y + self._rng.uniform(0.0, 2.5, n_plume),
            z + np.sin(ang1) * self._rng.uniform(0.5, 4.0, n_plume),
        ]).astype(np.float32)
        vel1 = np.column_stack([np.cos(ang1) * spd_h1, spd_v1, np.sin(ang1) * spd_h1]).astype(np.float32)
        self.spawn_particles(
            pos1, vel1,
            self._rng.uniform(1.8, 3.6, n_plume).astype(np.float32),
            self._rng.uniform(2.8, 6.2, n_plume).astype(np.float32),
            np.zeros(n_plume, dtype=np.int32),
        )

        # 2. Grãos balísticos de terra/rocha
        ang2 = self._rng.uniform(0.0, 2.0 * math.pi, n_grit)
        spd_h2 = self._rng.uniform(8.0, 32.0 * intensity, n_grit)
        spd_v2 = self._rng.uniform(10.0, 28.0 * intensity, n_grit)
        pos2 = np.column_stack([
            x + np.cos(ang2) * self._rng.uniform(0.3, 3.0, n_grit),
            base_y + self._rng.uniform(0.2, 2.0, n_grit),
            z + np.sin(ang2) * self._rng.uniform(0.3, 3.0, n_grit),
        ]).astype(np.float32)
        vel2 = np.column_stack([np.cos(ang2) * spd_h2, spd_v2, np.sin(ang2) * spd_h2]).astype(np.float32)
        self.spawn_particles(
            pos2, vel2,
            self._rng.uniform(0.9, 2.2, n_grit).astype(np.float32),
            self._rng.uniform(0.55, 1.45, n_grit).astype(np.float32),
            np.ones(n_grit, dtype=np.int32),
        )

    def _emit_dust_from_surface(self, cx, cz, surface_y, aircraft, strength, lateral_push_sign=0.0):
        """
        Emite simultaneamente plumas de poeira (vórtices) e grãos balísticos de areia
        a partir de um ponto (cx, surface_y, cz) varrido pelo jato do F-14.
        """
        back_x = -float(aircraft.forward[0])
        back_z = -float(aircraft.forward[2])
        right_x = float(aircraft.right[0])
        right_z = float(aircraft.right[2])

        # Normaliza projeções horizontais para empurrar a poeira para trás e para os lados
        b_len = math.hypot(back_x, back_z)
        if b_len > 1e-4:
            back_x /= b_len
            back_z /= b_len
        else:
            back_x, back_z = 0.0, 1.0

        r_len = math.hypot(right_x, right_z)
        if r_len > 1e-4:
            right_x /= r_len
            right_z /= r_len
        else:
            right_x, right_z = 1.0, 0.0

        # 1. Plumas volumétricas de poeira (Tipo 0 — vórtices duplos de ponta de asa/turbinas)
        n_plume = int(np.clip(strength * 11.0, 2, 18))
        side_choice = self._rng.choice([-1.0, 1.0], size=n_plume)
        if abs(lateral_push_sign) > 0.5:
            # Em rasante de paredão lateral, empurra a poeira para dentro do corredor
            side_out = np.full(n_plume, lateral_push_sign, dtype=np.float32)
            lat_off = self._rng.uniform(-2.5, 2.5, n_plume)
        else:
            side_out = side_choice
            lat_off = side_choice * self._rng.uniform(1.6, 6.2, n_plume)

        long_off = self._rng.uniform(-4.0, 7.5, n_plume)
        px = cx + right_x * lat_off + back_x * long_off
        pz = cz + right_z * lat_off + back_z * long_off
        py = _canyon_height_vec(px, pz) + self._rng.uniform(0.35, 1.85, n_plume)

        back_spd = (7.5 + 14.5 * strength) * self._rng.uniform(0.65, 1.30, n_plume)
        out_spd = (5.5 + 11.5 * strength) * self._rng.uniform(0.55, 1.35, n_plume)
        up_spd = (3.0 + 7.5 * strength) * self._rng.uniform(0.60, 1.40, n_plume)

        vx = back_x * back_spd + right_x * (side_out * out_spd)
        vz = back_z * back_spd + right_z * (side_out * out_spd)
        vy = up_spd

        self.spawn_particles(
            np.column_stack([px, py, pz]).astype(np.float32),
            np.column_stack([vx, vy, vz]).astype(np.float32),
            self._rng.uniform(1.45, 3.10, n_plume).astype(np.float32),
            self._rng.uniform(2.0, 4.6, n_plume).astype(np.float32),
            np.zeros(n_plume, dtype=np.int32),
        )

        # 2. Grãos balísticos de terra/areia grossa (Tipo 1 — jato de exaustão)
        n_grit = int(np.clip(strength * 9.0, 1, 14))
        g_side = self._rng.choice([-1.0, 1.0], size=n_grit)
        if abs(lateral_push_sign) > 0.5:
            g_out = np.full(n_grit, lateral_push_sign, dtype=np.float32)
            g_lat = self._rng.uniform(-1.8, 1.8, n_grit)
        else:
            g_out = g_side
            g_lat = g_side * self._rng.uniform(0.8, 4.8, n_grit)

        g_long = self._rng.uniform(-2.0, 5.5, n_grit)
        gx = cx + right_x * g_lat + back_x * g_long
        gz = cz + right_z * g_lat + back_z * g_long
        gy = _canyon_height_vec(gx, gz) + self._rng.uniform(0.25, 1.10, n_grit)

        g_back_spd = (13.0 + 20.0 * strength) * self._rng.uniform(0.70, 1.35, n_grit)
        g_out_spd = (4.0 + 9.0 * strength) * self._rng.uniform(0.50, 1.35, n_grit)
        g_up_spd = (5.5 + 11.5 * strength) * self._rng.uniform(0.65, 1.40, n_grit)

        gvx = back_x * g_back_spd + right_x * (g_out * g_out_spd)
        gvz = back_z * g_back_spd + right_z * (g_out * g_out_spd)
        gvy = g_up_spd

        self.spawn_particles(
            np.column_stack([gx, gy, gz]).astype(np.float32),
            np.column_stack([gvx, gvy, gvz]).astype(np.float32),
            self._rng.uniform(0.60, 1.45, n_grit).astype(np.float32),
            self._rng.uniform(0.42, 1.15, n_grit).astype(np.float32),
            np.ones(n_grit, dtype=np.int32),
        )

    def update(self, dt, aircraft, sim_time):
        """
        Atualiza emissão em voos rasantes, explosão de impacto em colisões,
        continuidade Roundabout e cinemática vetorizada das partículas de poeira/areia.
        """
        self.sim_time = sim_time

        # Acompanha o teleporte Roundabout da aeronave para que o rastro não suma na borda
        wrap_delta = getattr(aircraft, "last_wrap_delta", None)
        if wrap_delta is not None and (abs(float(wrap_delta[0])) > 1e-3 or abs(float(wrap_delta[2])) > 1e-3):
            alive_w = self.p_life > 0.0
            if np.any(alive_w):
                self.p_pos[alive_w] += wrap_delta

        # Detecta impacto/crash neste frame e gera nuvem explosiva de poeira no cânion
        if aircraft.crashed:
            if not self._prev_crashed:
                self.trigger_impact_burst(
                    float(aircraft.pos[0]), float(aircraft.pos[1]), float(aircraft.pos[2]),
                    intensity=2.4
                )
            self._prev_crashed = True
        else:
            self._prev_crashed = False

        if dt <= 1e-5:
            return

        # ----------------------------------------------------------------------
        # 1. EMISSÃO POR VOO RASANTE (SOLO E ENCOSTAS/PAREDÕES DO CÂNION)
        # ----------------------------------------------------------------------
        if (not aircraft.crashed) and float(aircraft.speed) > 10.0:
            px, py, pz = float(aircraft.pos[0]), float(aircraft.pos[1]), float(aircraft.pos[2])
            ab_mult = 1.75 if getattr(aircraft, "afterburner", False) else 1.0
            speed_factor = float(np.clip(float(aircraft.speed) / 55.0, 0.25, 2.10))

            # Ponto onde o cone de exaustão/downwash atinge o solo logo atrás do caça
            jet_x = px - float(aircraft.forward[0]) * 8.5
            jet_z = pz - float(aircraft.forward[2]) * 8.5
            ground_y = canyon_height_func(jet_x, jet_z)
            agl = py - ground_y

            # A) Rasante sobre o solo / fundo do cânion / topo de platô (AGL < 38m)
            if 0.4 < agl < self.LOW_PASS_MAX_AGL:
                alt_factor = float(np.clip((self.LOW_PASS_MAX_AGL - agl) / (self.LOW_PASS_MAX_AGL - 2.0), 0.0, 1.0))
                # Resposta mais intensa quanto mais perto do chão (curva quadrática suave)
                prox_curve = alt_factor ** 1.35
                strength = prox_curve * speed_factor * ab_mult
                if strength > 0.08:
                    self._emit_dust_from_surface(jet_x, jet_z, ground_y, aircraft, strength, lateral_push_sign=0.0)

            # B) Rasante lateral rente aos paredões do cânion (levanta areia da encosta!)
            for side_sign in (-1.0, 1.0):
                probe_x = jet_x + float(aircraft.right[0]) * (18.0 * side_sign)
                probe_z = jet_z + float(aircraft.right[2]) * (18.0 * side_sign)
                wall_y = canyon_height_func(probe_x, probe_z)
                if wall_y > (py - 8.0) and wall_y > 10.0:
                    wall_strength = 0.65 * speed_factor * ab_mult
                    self._emit_dust_from_surface(
                        probe_x, probe_z, min(py, wall_y), aircraft, wall_strength,
                        lateral_push_sign=-side_sign
                    )

        # ----------------------------------------------------------------------
        # 2. INTEGRAÇÃO CINEMÁTICA VETORIZADA DAS PARTÍCULAS ATIVAS
        # ----------------------------------------------------------------------
        alive = self.p_life > 0.0
        if not np.any(alive):
            return

        self.p_life[alive] -= dt
        still = self.p_life > 0.0
        if not np.any(still):
            return

        plumes = still & (self.p_type == 0)
        grit = still & (self.p_type == 1)

        # Tipo 0 (Plumas de Poeira): forte arrasto aerodinâmico + leve turbulência/flutuabilidade
        if np.any(plumes):
            drag_p = max(0.0, 1.0 - 1.35 * dt)
            self.p_vel[plumes, 0] *= drag_p
            self.p_vel[plumes, 2] *= drag_p
            # Leve redução da subida + assentamento bem lento (nuvem pairando no cânion)
            self.p_vel[plumes, 1] = self.p_vel[plumes, 1] * max(0.0, 1.0 - 0.95 * dt) - 1.15 * dt
            # Brisa suave de turbulência lateral
            swirl_phase = self.sim_time * 2.2 + self.p_pos[plumes, 2] * 0.08
            self.p_vel[plumes, 0] += np.sin(swirl_phase) * 1.4 * dt
            self.p_pos[plumes] += self.p_vel[plumes] * dt

            # Mantém plumas sempre acima do terreno local
            terrain_p = _canyon_height_vec(self.p_pos[plumes, 0], self.p_pos[plumes, 2]) + 0.35
            below_p = self.p_pos[plumes, 1] < terrain_p
            if np.any(below_p):
                p_idx = np.where(plumes)[0][below_p]
                self.p_pos[p_idx, 1] = terrain_p[below_p]
                self.p_vel[p_idx, 1] = np.maximum(0.4, -self.p_vel[p_idx, 1] * 0.2)

        # Tipo 1 (Grãos de Areia/Terra): trajetória balística com gravidade real
        if np.any(grit):
            drag_g = max(0.0, 1.0 - 0.50 * dt)
            self.p_vel[grit, 0] *= drag_g
            self.p_vel[grit, 2] *= drag_g
            self.p_vel[grit, 1] -= 14.5 * dt
            self.p_pos[grit] += self.p_vel[grit] * dt

            # Colisão com o solo: quica suavemente ou dissipa em pó
            terrain_g = _canyon_height_vec(self.p_pos[grit, 0], self.p_pos[grit, 2]) + 0.15
            below_g = self.p_pos[grit, 1] <= terrain_g
            if np.any(below_g):
                g_idx = np.where(grit)[0][below_g]
                self.p_pos[g_idx, 1] = terrain_g[below_g]
                self.p_vel[g_idx, 1] = np.abs(self.p_vel[g_idx, 1]) * 0.25
                self.p_vel[g_idx, 0] *= 0.45
                self.p_vel[g_idx, 2] *= 0.45
                self.p_life[g_idx] = np.minimum(self.p_life[g_idx], 0.25)

    def draw(self, sun_state=None, wireframe_mode=False):
        """
        Renderiza todas as partículas de poeira e areia com billboards orientados à câmera,
        expansão progressiva e tintagem dinâmica sincronizada ao ciclo Dia/Noite.
        """
        if wireframe_mode:
            return

        alive_idx = np.where(self.p_life > 0.0)[0]
        n_alive = len(alive_idx)
        if n_alive == 0:
            return

        if self.dust_tex_id is None:
            self.dust_tex_id = _create_dust_particle_texture()

        mv = glGetFloatv(GL_MODELVIEW_MATRIX)
        cam_right = np.array([mv[0][0], mv[1][0], mv[2][0]], dtype=np.float32)
        cam_up = np.array([mv[0][1], mv[1][1], mv[2][1]], dtype=np.float32)

        pos = self.p_pos[alive_idx]
        sizes = self.p_size[alive_idx]
        life_ratio = np.clip(self.p_life[alive_idx] / self.p_max_life[alive_idx], 0.0, 1.0)
        p_types = self.p_type[alive_idx]
        shades = self.p_shade[alive_idx]

        # Plumas de poeira expandem até ~2.6x do tamanho inicial enquanto sobem e se dissipam;
        # grãos balísticos mantêm tamanho compacto
        age = 1.0 - life_ratio
        cur_scale = np.where(
            p_types == 0,
            sizes * (0.65 + 1.95 * (age ** 0.72)),
            sizes * (0.90 + 0.25 * age)
        )

        # Fade-in rápido no nascimento e fade-out suave na dissipação
        fade_in = np.clip(age / 0.14, 0.0, 1.0)
        fade_out = life_ratio ** 1.15
        alpha = fade_in * fade_out * np.where(p_types == 0, 0.62, 0.88)

        # Paleta de areia/arenito modulada pela iluminação do ciclo Dia/Noite
        if sun_state is not None:
            df = float(sun_state.get("daylight_factor", 0.75))
            ld = sun_state["light_diffuse"]
            la = sun_state["light_ambient"]
            lit_r = float(np.clip(la[0] * 0.75 + ld[0] * 0.95, 0.24, 1.12))
            lit_g = float(np.clip(la[1] * 0.75 + ld[1] * 0.95, 0.24, 1.10))
            lit_b = float(np.clip(la[2] * 0.80 + ld[2] * 0.95, 0.28, 1.08))
            # À noite, atenua opacidade sutilmente para integrar ao luar sem parecer neblina luminosa
            alpha *= (0.62 + 0.38 * df)
        else:
            lit_r, lit_g, lit_b = 0.96, 0.82, 0.66

        # Cor base: Plumas em ocre/areia arenítica clara; Grãos em terracota/terra escura
        base_r = np.where(p_types == 0, 0.84, 0.62) * shades * lit_r
        base_g = np.where(p_types == 0, 0.63, 0.43) * shades * lit_g
        base_b = np.where(p_types == 0, 0.44, 0.29) * shades * lit_b

        base_r = np.clip(base_r, 0.0, 1.0)
        base_g = np.clip(base_g, 0.0, 1.0)
        base_b = np.clip(base_b, 0.0, 1.0)

        rx = cam_right[None, :] * cur_scale[:, None]
        uy = cam_up[None, :] * cur_scale[:, None]

        total_v = n_alive * 4
        qv = self.quad_verts[:total_v]
        qv[0::4] = pos - rx - uy
        qv[1::4] = pos + rx - uy
        qv[2::4] = pos + rx + uy
        qv[3::4] = pos - rx + uy

        qc = self.quad_colors[:total_v]
        for corner in range(4):
            qc[corner::4, 0] = base_r
            qc[corner::4, 1] = base_g
            qc[corner::4, 2] = base_b
            qc[corner::4, 3] = alpha

        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_POLYGON_BIT)
        glDisable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.dust_tex_id)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_TEXTURE_COORD_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)

        glVertexPointer(3, GL_FLOAT, 0, qv)
        glTexCoordPointer(2, GL_FLOAT, 0, self.quad_uvs[:total_v])
        glColorPointer(4, GL_FLOAT, 0, qc)
        glDrawArrays(GL_QUADS, 0, total_v)

        glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

        glDepthMask(GL_TRUE)
        glPopAttrib()


_CANYON_DUST_SYSTEM = None


def get_canyon_dust_system():
    """Retorna ou inicializa o sistema de partículas de poeira/areia da Cena 2."""
    global _CANYON_DUST_SYSTEM
    if _CANYON_DUST_SYSTEM is None:
        _CANYON_DUST_SYSTEM = CanyonDustSystem()
    return _CANYON_DUST_SYSTEM


def reset_canyon_dust():
    """Limpa as partículas de poeira da Cena 2."""
    get_canyon_dust_system().reset()


def trigger_canyon_dust_burst(x, y, z, intensity=2.2):
    """Dispara uma explosão de poeira e terra arenosa em (x, y, z)."""
    get_canyon_dust_system().trigger_impact_burst(float(x), float(y), float(z), float(intensity))


def update_canyon_dust(dt, aircraft, sim_time):
    """Atualiza as partículas de poeira/areia em voo rasante no cânion."""
    get_canyon_dust_system().update(float(dt), aircraft, float(sim_time))


def draw_canyon_dust(sun_state=None, wireframe_mode=False):
    """Renderiza as partículas de poeira e areia da Cena 2."""
    get_canyon_dust_system().draw(sun_state=sun_state, wireframe_mode=wireframe_mode)


# ==============================================================================
# PROJEÇÃO UV TRIPLANAR MÉTRICA E ESTRATIFICAÇÃO GEOLÓGICA DO CÂNION
# ==============================================================================
# Textura sandstone é 1024x512 (proporção 2:1).
# Escalas métricas exatas para manter texels 100% quadrados (0.078 m/px) e fechar
# múltiplos inteiros exatos no domínio periódico Roundabout (GL_REPEAT):
#   - 720m * (1/80)  =  9.0 ciclos inteiros em X
#   - 2000m * (1/80) = 25.0 ciclos inteiros em Z (paredões)
#   - 2000m * (1/40) = 50.0 ciclos inteiros em Z (leito)
CANYON_UV_SCALE_U = 1.0 / 80.0    # 1 tile = 80m na direção dos estratos (1024 px)
CANYON_UV_SCALE_V = 1.0 / 40.0    # 1 tile = 40m perpendicular aos estratos (512 px)


def _project_canyon_triplanar_uv(pt, normal, scale_u=CANYON_UV_SCALE_U, scale_v=CANYON_UV_SCALE_V):
    """
    Projeta coordenadas UV métricas segundo o eixo dominante da normal do triângulo:
      - Superfícies horizontais (|ny| dominante — leito/platôs): plano XZ (u=x, v=z).
      - Paredões laterais Leste/Oeste (|nx| dominante): plano ZY (u=z, v=y) — alinha
        os estratos sedimentares horizontalmente ao longo do cânion em AMBOS os lados,
        eliminando completamente o estiramento vertical da parede esquerda!
      - Curvas escarpadas Norte/Sul (|nz| dominante): plano XY (u=x, v=y).
    """
    vx, vy, vz = float(pt[0]), float(pt[1]), float(pt[2])
    nx, ny, nz = abs(float(normal[0])), abs(float(normal[1])), abs(float(normal[2]))

    if ny >= nx and ny >= nz:
        return vx * scale_u, vz * scale_v
    if nx >= ny and nx >= nz:
        return vz * scale_u, vy * scale_v
    return vx * scale_u, vy * scale_v


def _canyon_strata_vertex_color(y):
    """
    Aplica modulação sutil de cor por altitude simulando estratos sedimentares reais
    de arenito (areia clara no leito, camadas terracota/ocre nas paredes, topo iluminado),
    quebrando uniformidade visual ao longo dos 2000m sem alterar a continuidade periódica.
    """
    if y < 6.0:
        return (0.95, 0.87, 0.76)

    # Faixas geológicas horizontais suaves em função da altura Y
    band = 0.5 + 0.5 * math.sin(y * 0.14 + 0.4 * math.sin(y * 0.045))
    elev_t = min(1.0, max(0.0, (y - 6.0) / 145.0))

    r = 0.86 + 0.12 * band + 0.04 * elev_t
    g = 0.72 + 0.14 * band + 0.08 * elev_t
    b = 0.62 + 0.13 * band + 0.11 * elev_t
    return (min(1.0, r), min(1.0, g), min(1.0, b))


# ==============================================================================
# MODELAGEM DE MATACÃO / ROCHA FACETADA 3D COM MAPEAMENTO UV TRIPLANAR
# ==============================================================================

def _draw_procedural_boulder(boulder):
    """Desenha um matacão/rocha 3D facetado com projeção UV triplanar sem estiramento."""
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
            ring_pts.append([px, py, pz])
        rings.append(ring_pts)

    top_pt = [0.0, ry * float(rng.uniform(0.92, 1.06)), 0.0]

    glPushMatrix()
    glTranslatef(boulder["x"], boulder["y_base"], boulder["z"])
    glRotatef(boulder["yaw"], 0.0, 1.0, 0.0)

    shade = float(rng.uniform(0.78, 0.94))
    glColor3f(shade, shade * 0.90, shade * 0.82)

    # Escala triplanar própria para o porte das rochas (6m..16m) mantendo proporção 2:1
    b_scale_u = 1.0 / 28.0
    b_scale_v = 1.0 / 14.0

    def _emit_boulder_tri(pa, pb, pc):
        n = compute_normal(pa, pb, pc)
        glNormal3fv(n)
        for pt in (pa, pb, pc):
            u, v = _project_canyon_triplanar_uv(pt, n, b_scale_u, b_scale_v)
            glTexCoord2f(u, v)
            glVertex3fv(pt)

    glBegin(GL_TRIANGLES)
    for st in range(n_stacks - 1):
        curr_r = rings[st]
        next_r = rings[st + 1]
        for sl in range(n_slices):
            sl_next = (sl + 1) % n_slices
            p00 = curr_r[sl]
            p10 = curr_r[sl_next]
            p01 = next_r[sl]
            p11 = next_r[sl_next]
            _emit_boulder_tri(p00, p10, p11)
            _emit_boulder_tri(p00, p11, p01)

    last_r = rings[-1]
    for sl in range(n_slices):
        sl_next = (sl + 1) % n_slices
        _emit_boulder_tri(last_r[sl], last_r[sl_next], top_pt)
    glEnd()

    glPopMatrix()


# ==============================================================================
# CONSTRUÇÃO DA CENA 2 (DISPLAY LIST PERIÓDICA COM UV TRIPLANAR MÉTRICO)
# ==============================================================================

def build_scene2_canyon_list(canyon_tex_id):
    """
    Compila a Cena 2: Cânion Procedural ("Trench Run" de Top Gun: Maverick).
    Malha periódica refinada em X = [-360..+360] (passo 12m, 60 células) e
    Z = [-1500..+500] (passo 16m, 125 células), utilizando Projeção UV Triplanar
    Métrica + textura seamless 1024x512 (GL_REPEAT) sem estiramento em nenhum paredão.
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, canyon_tex_id)
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.16, 0.14, 0.12, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 12.0)

    dx = 12.0
    dz = 16.0
    xs = np.linspace(SCENE2_X_MIN, SCENE2_X_MAX, int(round(SCENE2_SPAN_X / dx)) + 1)
    zs = np.linspace(SCENE2_Z_MIN, SCENE2_Z_MAX, int(round(SCENE2_SPAN_Z / dz)) + 1)

    heights = np.zeros((len(xs), len(zs)), dtype=np.float32)
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            heights[i, j] = canyon_height_func(float(x), float(z))
    # Garante igualdade numérica exata nas bordas de costura Roundabout
    heights[-1, :] = heights[0, :]
    heights[:, -1] = heights[:, 0]

    # 1. Malha unificada do cânion com Projeção UV Triplanar Métrica e estratos por altitude
    glBegin(GL_TRIANGLES)
    for i in range(len(xs) - 1):
        x0, x1 = float(xs[i]), float(xs[i + 1])
        for j in range(len(zs) - 1):
            z0, z1 = float(zs[j]), float(zs[j + 1])
            y00, y10 = float(heights[i, j]), float(heights[i + 1, j])
            y01, y11 = float(heights[i, j + 1]), float(heights[i + 1, j + 1])

            p00 = [x0, y00, z0]
            p10 = [x1, y10, z0]
            p01 = [x0, y01, z1]
            p11 = [x1, y11, z1]

            c00 = _canyon_strata_vertex_color(y00)
            c10 = _canyon_strata_vertex_color(y10)
            c01 = _canyon_strata_vertex_color(y01)
            c11 = _canyon_strata_vertex_color(y11)

            # Triângulo 1: (p00, p01, p11)
            n1 = compute_normal(p00, p01, p11)
            glNormal3fv(n1)
            for pt, col in ((p00, c00), (p01, c01), (p11, c11)):
                u, v = _project_canyon_triplanar_uv(pt, n1)
                glColor3fv(col)
                glTexCoord2f(u, v)
                glVertex3fv(pt)

            # Triângulo 2: (p00, p11, p10)
            n2 = compute_normal(p00, p11, p10)
            glNormal3fv(n2)
            for pt, col in ((p00, c00), (p11, c11), (p10, c10)):
                u, v = _project_canyon_triplanar_uv(pt, n2)
                glColor3fv(col)
                glTexCoord2f(u, v)
                glVertex3fv(pt)
    glEnd()

    # 2. Rochas / matacões 3D gerados proceduralmente (usam sandstone com UV triplanar)
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
