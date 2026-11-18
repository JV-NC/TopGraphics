"""
================================================================================
TopGraphics | scene_carrier.py
Cena 1: Oceano Físico Baseado em Sistema de Partículas e Hidrodinâmica +
Porta-Aviões Nuclear USS Enterprise (CVN-65).

Arquitetura Física do Corpo d'Água (100% Python + NumPy + PyOpenGL):
  1. Malha de Partículas Superficiais Acopladas (Eulerian-Lagrangian Wave Grid):
     - 9.216 partículas de superfície (96x96) com movimento orbital trocoide de
       Gerstner (4 trens de onda direcionais) acoplado à Equação Diferencial da
       Onda 2D Amortecida (propagação elástica entre partículas vizinhas).
     - Normais analíticas + diferenças finitas e coloração dinâmica por altura/espuma
       (azul abissal nos cavados, verde-água translúcido nas cristas e espuma branca
       nas quebras por Jacobiano).
  2. Reações Físicas do Corpo d'Água:
     - Deslocamento Hidrodinâmico do Casco do CVN-65: Onda de proa (Bow Wave),
       esteira divergente em "V" (Kelvin Wake) e turbulência de popa dos 4 hélices.
     - Downwash / Jet Blast Supersônico do F-14 Tomcat: Voo rasante (Y < 38m)
       empurra fisicamente as partículas de água para baixo, gerando ondas de
       choque circulares/em "V" na superfície e levantando spray (Rooster Tail).
     - Impacto Hidrodinâmico (Splash): Colisão ou toque na água injeta impulso
       radial no campo de partículas e dispara uma coluna balística de água.
  3. Sistema de Partículas Livres 3D de Spray, Espuma e Quebra de Onda:
     - Até 1.800 partículas livres simuladas com gravidade (-9.81 m/s²), arrasto
       aerodinâmico, vento marítimo e flutuabilidade ao reentrar na superfície.
================================================================================
"""

import math
import numpy as np
from OpenGL.GL import *

from renderer_utils import upload_texture_rgb, load_texture_from_assets, draw_quad_with_normal
from cvn_65_model import (
    CARRIER_DECK_Y,
    CARRIER_DECK_HALF_W,
    CARRIER_DECK_HALF_L,
    create_cvn65_deck_texture,
    draw_cvn65_carrier,
    is_within_cvn65_deck_polygon,
    check_cvn65_extra_collisions,
)

# Período do mundo toroidal na Cena 1 (idêntico a scene_utils.py)
SCENE1_PERIOD = 4800.0
SCENE1_HALF_PERIOD = 2400.0


# ==============================================================================
# 1. TEXTURAS DA CENA 1 (OCEANO, ESPUMA/SPRAY RGBA E CONVÉS DO CVN-65)
# ==============================================================================

def _create_procedural_ocean_texture():
    """Fallback procedural 128x128 caso 'assets/ocean_water.png' não seja encontrado."""
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


def create_ocean_texture():
    """
    Carrega a textura 'assets/ocean_water.png' (convertendo automaticamente a faixa
    de ondas monocromática para azul-oceânico naval com mipmaps e repetição espelhada).
    """
    return load_texture_from_assets(
        "ocean_water.png",
        fallback_fn=_create_procedural_ocean_texture,
        mode="ocean",
        target_size=512,
    )


def create_deck_texture():
    """Delega a criação da textura de alta resolução do convés do CVN-65."""
    return create_cvn65_deck_texture()


def _create_spray_particle_texture():
    """
    Gera uma textura procedural RGBA 64x64 de gotícula/espuma hidrodinâmica com
    decaimento radial gaussiano suave para renderizar os billboards de spray.
    """
    size = 64
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    c = (size - 1) * 0.5
    r_sq = ((x - c) / c) ** 2 + ((y - c) / c) ** 2

    alpha = np.exp(-r_sq * 3.8) * np.clip(1.0 - r_sq, 0.0, 1.0)
    noise = 0.88 + 0.12 * np.sin(x * 0.7) * np.cos(y * 0.7)
    alpha = np.clip(alpha * noise, 0.0, 1.0)

    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[:, :, 0] = 238
    rgba[:, :, 1] = 248
    rgba[:, :, 2] = 255
    rgba[:, :, 3] = (alpha * 255.0).astype(np.uint8)

    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba)
    return tex_id


# ==============================================================================
# 2. SISTEMA FÍSICO DE CORPO D'ÁGUA E PARTÍCULAS HIDRODINÂMICAS
# ==============================================================================

def _wrap_coord_periodic(val):
    """Mapeia uma coordenada X ou Z para a célula fundamental [-2400, +2400]."""
    return ((val + SCENE1_HALF_PERIOD) % SCENE1_PERIOD) - SCENE1_HALF_PERIOD


def evaluate_gerstner_wave_height(x, z, sim_time):
    """
    Calcula a cota Y exata da superfície do mar em qualquer ponto (x, z) no instante
    sim_time somando os 4 trens de ondas físicas de Gerstner + esteira do CVN-65.
    Usado tanto para colisão física da aeronave quanto para flutuabilidade das partículas.
    """
    p1 = x * 0.042 + z * 0.028 - sim_time * 1.75
    p2 = -x * 0.026 + z * 0.048 - sim_time * 1.35
    p3 = x * 0.078 - z * 0.054 - sim_time * 2.35
    p4 = (x + z) * 0.130 + sim_time * 3.10

    y = (
        0.92 * math.cos(p1)
        + 0.68 * math.cos(p2)
        + 0.30 * math.cos(p3)
        + 0.14 * math.sin(p4)
    )

    # Amortecimento sob o casco do CVN-65 e onda de proa nas coordenadas periódicas
    xm = _wrap_coord_periodic(x)
    zm = _wrap_coord_periodic(z)
    if abs(xm) < 22.0 and -122.0 <= zm <= 118.0:
        hull_mask = math.exp(-((xm / 14.0) ** 2)) * math.exp(-((zm / 95.0) ** 4))
        y *= (1.0 - 0.85 * hull_mask)

    return float(y)


class OceanPhysicsSystem:
    """
    Simulador Físico do Corpo d'Água da Cena 1:
      - Parte 1: Grade de 96x96 partículas superficiais acopladas (Equação da Onda 2D
        Amortecida + Movimento Orbital Trocoide de Gerstner + Esteira Kelvin do CVN-65
        + Depressão Aerodinâmica de Downwash do F-14).
      - Parte 2: 1.800 partículas hidrodinâmicas livres 3D (Spray, Espuma de Crista,
        Bow Splash do Porta-Aviões, Esteira de Popa e Rooster Tail do F-14).
    """

    GRID_N = 96                 # 96x96 = 9.216 partículas de superfície acopladas
    GRID_STEP = 18.0            # Espaçamento de 18m -> cobre 1710m x 1710m em alta resolução
    MAX_PARTICLES = 1800        # Partículas hidrodinâmicas livres (spray, espuma e splash)

    def __init__(self):
        self.sim_time = 0.0
        self.spray_tex_id = None

        n = self.GRID_N
        half_span = 0.5 * (n - 1) * self.GRID_STEP
        axis = np.linspace(-half_span, half_span, n, dtype=np.float32)
        self.local_z, self.local_x = np.meshgrid(axis, axis, indexing="ij")

        # Distância radial normalizada nas bordas da grade para transição suave com o horizonte
        r_dist = np.maximum(np.abs(self.local_x), np.abs(self.local_z)) / half_span
        self.edge_fade = np.clip(1.0 - np.clip((r_dist - 0.78) / 0.22, 0.0, 1.0) ** 2, 0.0, 1.0).astype(np.float32)

        # Estado dinâmico da Equação da Onda 2D nas partículas da superfície (ancorado no mundo)
        self.snap_ix = 0
        self.snap_iz = 0
        self.eta = np.zeros((n, n), dtype=np.float32)       # Perturbação hidrodinâmica vertical (m)
        self.vel_y = np.zeros((n, n), dtype=np.float32)     # Velocidade vertical das partículas (m/s)
        self.wake_foam = np.zeros((n, n), dtype=np.float32) # Concentração de espuma persistente [0..1]

        # Buffers vetorizados para renderização rápida via OpenGL Client Arrays (glDrawElements)
        self.vertices = np.zeros((n, n, 3), dtype=np.float32)
        self.normals = np.zeros((n, n, 3), dtype=np.float32)
        self.uvs = np.zeros((n, n, 2), dtype=np.float32)
        self.colors = np.zeros((n, n, 4), dtype=np.float32)

        # Pré-calcula os índices de triângulos da malha 96x96 (18.050 triângulos)
        idx_grid = np.arange(n * n, dtype=np.uint32).reshape(n, n)
        i00 = idx_grid[:-1, :-1].ravel()
        i10 = idx_grid[1:, :-1].ravel()
        i11 = idx_grid[1:, 1:].ravel()
        i01 = idx_grid[:-1, 1:].ravel()
        self.indices = np.column_stack([i00, i10, i11, i00, i11, i01]).ravel()

        # Sistema de Partículas Livres 3D (Spray, Whitecaps, Esteira e Splash)
        # type: 0 = Spray Balístico, 1 = Espuma de Superfície (Flutuante), 2 = Rooster Tail / Splash
        self.p_pos = np.zeros((self.MAX_PARTICLES, 3), dtype=np.float32)
        self.p_vel = np.zeros((self.MAX_PARTICLES, 3), dtype=np.float32)
        self.p_life = np.zeros(self.MAX_PARTICLES, dtype=np.float32)
        self.p_max_life = np.ones(self.MAX_PARTICLES, dtype=np.float32)
        self.p_size = np.ones(self.MAX_PARTICLES, dtype=np.float32)
        self.p_type = np.zeros(self.MAX_PARTICLES, dtype=np.int32)
        self.spawn_cursor = 0

        # Buffers de renderização das partículas livres (4 vértices por billboard quad)
        self.quad_verts = np.zeros((self.MAX_PARTICLES * 4, 3), dtype=np.float32)
        self.quad_uvs = np.zeros((self.MAX_PARTICLES * 4, 2), dtype=np.float32)
        self.quad_uvs[0::4] = [0.0, 0.0]
        self.quad_uvs[1::4] = [1.0, 0.0]
        self.quad_uvs[2::4] = [1.0, 1.0]
        self.quad_uvs[3::4] = [0.0, 1.0]
        self.quad_colors = np.zeros((self.MAX_PARTICLES * 4, 4), dtype=np.float32)

        self._rng = np.random.default_rng(1986)
        self._seed_initial_carrier_wake_particles()

    def _shift_field_with_snap(self, new_ix, new_iz):
        """
        Mantém as ondas interativas (eta, vel_y, wake_foam) fixas nas coordenadas
        de mundo quando a janela da malha acompanha o deslocamento do caça.
        """
        dx = new_ix - self.snap_ix
        dz = new_iz - self.snap_iz
        if dx == 0 and dz == 0:
            return

        for arr in (self.eta, self.vel_y, self.wake_foam):
            if abs(dz) >= self.GRID_N or abs(dx) >= self.GRID_N:
                arr.fill(0.0)
                continue
            if dz != 0:
                arr[:] = np.roll(arr, -dz, axis=0)
                if dz > 0:
                    arr[-dz:, :] = 0.0
                else:
                    arr[:-dz, :] = 0.0
            if dx != 0:
                arr[:] = np.roll(arr, -dx, axis=1)
                if dx > 0:
                    arr[:, -dx:] = 0.0
                else:
                    arr[:, :-dx] = 0.0

        self.snap_ix = new_ix
        self.snap_iz = new_iz

    def spawn_particles(self, positions, velocities, lifetimes, sizes, p_types):
        """Insere um lote de novas partículas hidrodinâmicas no buffer circular."""
        count = len(positions)
        if count <= 0:
            return
        idx = (np.arange(count) + self.spawn_cursor) % self.MAX_PARTICLES
        self.spawn_cursor = (self.spawn_cursor + count) % self.MAX_PARTICLES

        self.p_pos[idx] = positions
        self.p_vel[idx] = velocities
        self.p_life[idx] = lifetimes
        self.p_max_life[idx] = np.maximum(0.05, lifetimes)
        self.p_size[idx] = sizes
        self.p_type[idx] = p_types

    def _seed_initial_carrier_wake_particles(self):
        """Popula inicialmente a esteira de espuma e spray do CVN-65 ao iniciar a cena."""
        n_init = 320
        z_wake = self._rng.uniform(112.0, 310.0, n_init).astype(np.float32)
        spread = 11.5 + (z_wake - 112.0) * 0.14
        x_wake = self._rng.normal(0.0, spread * 0.45, n_init).astype(np.float32)
        y_wake = np.full(n_init, 0.25, dtype=np.float32)

        pos = np.column_stack([x_wake, y_wake, z_wake])
        vel = np.column_stack([
            self._rng.uniform(-1.2, 1.2, n_init),
            self._rng.uniform(0.1, 0.8, n_init),
            self._rng.uniform(3.5, 9.0, n_init),
        ]).astype(np.float32)
        life = self._rng.uniform(1.2, 4.5, n_init).astype(np.float32)
        sizes = self._rng.uniform(2.8, 6.5, n_init).astype(np.float32)
        types = np.ones(n_init, dtype=np.int32)
        self.spawn_particles(pos, vel, life, sizes, types)

    def trigger_splash(self, x, z, intensity=2.0):
        """
        Injeta um forte pulso hidrodinâmico na malha de ondas em (x, z) e lança uma
        coluna explosiva de partículas de água e espuma (ex: impacto ou toque).
        """
        center_x = self.snap_ix * self.GRID_STEP
        center_z = self.snap_iz * self.GRID_STEP
        wx = self.local_x + center_x
        wz = self.local_z + center_z

        dist_sq = (wx - x) ** 2 + (wz - z) ** 2
        radius_sq = (28.0 * intensity) ** 2
        mask = dist_sq < radius_sq
        if np.any(mask):
            r = np.sqrt(dist_sq[mask])
            # Cavidade central seguida de anel elevado de impacto
            impulse = -14.0 * intensity * np.cos(r / (9.0 * intensity)) * np.exp(-r / (18.0 * intensity))
            self.vel_y[mask] += impulse
            self.wake_foam[mask] = np.clip(self.wake_foam[mask] + 0.95, 0.0, 1.0)

        # Emite géiser/coluna radial de partículas balísticas de água
        n_splash = min(260, int(120 * intensity))
        angles = self._rng.uniform(0.0, 2.0 * math.pi, n_splash)
        speeds_h = self._rng.uniform(2.0, 18.0 * intensity, n_splash)
        speeds_v = self._rng.uniform(8.0, 26.0 * intensity, n_splash)

        pos = np.column_stack([
            x + np.cos(angles) * self._rng.uniform(0.5, 4.5, n_splash),
            np.full(n_splash, evaluate_gerstner_wave_height(x, z, self.sim_time) + 0.6),
            z + np.sin(angles) * self._rng.uniform(0.5, 4.5, n_splash),
        ]).astype(np.float32)

        vel = np.column_stack([
            np.cos(angles) * speeds_h,
            speeds_v,
            np.sin(angles) * speeds_h,
        ]).astype(np.float32)

        life = self._rng.uniform(1.0, 2.8, n_splash).astype(np.float32)
        sizes = self._rng.uniform(1.8, 5.2, n_splash).astype(np.float32)
        types = np.full(n_splash, 2, dtype=np.int32)
        self.spawn_particles(pos, vel, life, sizes, types)

    def update(self, dt, aircraft, sim_time):
        """
        Atualiza a física do corpo d'água (Equação da Onda 2D + Ondas de Gerstner +
        Interações com o Casco do CVN-65 e com o F-14 Tomcat + Partículas Livres).
        """
        self.sim_time = sim_time
        px, py, pz = float(aircraft.pos[0]), float(aircraft.pos[1]), float(aircraft.pos[2])

        # 1. Alinha o centro da malha de alta resolução à posição (X, Z) do caça
        new_ix = int(round(px / self.GRID_STEP))
        new_iz = int(round(pz / self.GRID_STEP))
        self._shift_field_with_snap(new_ix, new_iz)

        center_x = self.snap_ix * self.GRID_STEP
        center_z = self.snap_iz * self.GRID_STEP
        wx = self.local_x + center_x
        wz = self.local_z + center_z

        # Coordenadas modulares periódicas para interação com qualquer instância do CVN-65
        wx_mod = ((wx + SCENE1_HALF_PERIOD) % SCENE1_PERIOD) - SCENE1_HALF_PERIOD
        wz_mod = ((wz + SCENE1_HALF_PERIOD) % SCENE1_PERIOD) - SCENE1_HALF_PERIOD

        if dt > 1e-4:
            sub_dt = min(dt, 0.025)

            # ------------------------------------------------------------------
            # A) INTEGRAÇÃO DA EQUAÇÃO DA ONDA 2D AMORTECIDA NAS PARTÍCULAS
            # ------------------------------------------------------------------
            laplacian = (
                np.roll(self.eta, 1, axis=0)
                + np.roll(self.eta, -1, axis=0)
                + np.roll(self.eta, 1, axis=1)
                + np.roll(self.eta, -1, axis=1)
                - 4.0 * self.eta
            )
            wave_stiffness = 22.0
            buoyancy_restoring = 4.2
            self.vel_y += (wave_stiffness * laplacian - buoyancy_restoring * self.eta) * sub_dt
            self.vel_y *= 0.968
            self.eta += self.vel_y * sub_dt

            # Zera bordas extremas da janela para evitar reflexão artificial
            self.eta[0, :] = self.eta[-1, :] = self.eta[:, 0] = self.eta[:, -1] = 0.0
            self.wake_foam *= max(0.0, 1.0 - 0.38 * sub_dt)

            # ------------------------------------------------------------------
            # B) INTERAÇÃO HIDRODINÂMICA COM O CASCO DO PORTA-AVIÕES (CVN-65)
            # ------------------------------------------------------------------
            # Onda de Proa (Bow Wave em Z_mod ~ -114m)
            bow_dist_sq = wx_mod ** 2 + (wz_mod + 114.0) ** 2
            bow_mask = bow_dist_sq < (26.0 ** 2)
            if np.any(bow_mask):
                self.eta[bow_mask] = 1.15 * np.exp(-bow_dist_sq[bow_mask] / 260.0)
                self.wake_foam[bow_mask] = np.clip(self.wake_foam[bow_mask] + 1.8 * sub_dt, 0.0, 1.0)

            # Esteira Kelvin em "V" e Turbilhão de Popa (Z_mod de +110m a +360m)
            stern_mask = (wz_mod >= 108.0) & (wz_mod <= 360.0) & (np.abs(wx_mod) <= 58.0)
            if np.any(stern_mask):
                dz_s = wz_mod[stern_mask] - 108.0
                dx_s = wx_mod[stern_mask]
                half_wake_w = 13.5 + 0.14 * dz_s
                in_cone = np.abs(dx_s) <= half_wake_w
                if np.any(in_cone):
                    ratio = dx_s[in_cone] / half_wake_w[in_cone]
                    decay = np.exp(-dz_s[in_cone] / 195.0)
                    # Cristas laterais da onda de Kelvin + cavidade turbulenta central
                    kelvin_profile = (
                        0.75 * np.cos((abs(ratio) - 0.72) * 5.0) * np.exp(-((abs(ratio) - 0.72) ** 2) / 0.08)
                        - 0.45 * np.exp(-(ratio ** 2) / 0.18) * np.sin(dz_s[in_cone] * 0.25 - sim_time * 8.0)
                    ) * decay
                    idx_s = np.where(stern_mask)
                    sel_z = idx_s[0][in_cone]
                    sel_x = idx_s[1][in_cone]
                    self.eta[sel_z, sel_x] = 0.65 * self.eta[sel_z, sel_x] + 0.35 * kelvin_profile
                    foam_add = np.exp(-(ratio ** 2) / 0.32) * decay * 1.4 * sub_dt
                    self.wake_foam[sel_z, sel_x] = np.clip(self.wake_foam[sel_z, sel_x] + foam_add, 0.0, 1.0)

            # ------------------------------------------------------------------
            # C) INTERAÇÃO AERODINÂMICA / JET BLAST DO F-14 EM VOO RASANTE
            # ------------------------------------------------------------------
            if (not aircraft.on_ground) and (not aircraft.crashed) and (1.2 < py < 38.0):
                alt_factor = np.clip((38.0 - py) / 34.0, 0.0, 1.0)
                ab_mult = 1.85 if getattr(aircraft, "afterburner", False) else 1.0
                speed_factor = np.clip(float(aircraft.speed) / 70.0, 0.2, 2.0)
                blast_strength = alt_factor * ab_mult * speed_factor

                # Ponto de impacto do jato/downwash logo atrás do F-14
                jet_x = px - float(aircraft.forward[0]) * (8.0 + 0.25 * py)
                jet_z = pz - float(aircraft.forward[2]) * (8.0 + 0.25 * py)

                d_jet_sq = (wx - jet_x) ** 2 + (wz - jet_z) ** 2
                jet_radius = 24.0 + 10.0 * ab_mult
                jet_mask = d_jet_sq < (jet_radius ** 2)
                if np.any(jet_mask):
                    r_j = np.sqrt(d_jet_sq[jet_mask])
                    # Depressão central por pressão + anel externo elevado
                    ring_push = -9.5 * blast_strength * np.cos(r_j / (0.42 * jet_radius)) * np.exp(-r_j / (0.55 * jet_radius))
                    self.vel_y[jet_mask] += ring_push * sub_dt * 12.0
                    self.wake_foam[jet_mask] = np.clip(
                        self.wake_foam[jet_mask] + 2.2 * blast_strength * np.exp(-r_j / 14.0) * sub_dt,
                        0.0, 1.0
                    )

                # Emite partículas de Rooster Tail (pluma de spray levantada pelo jato do F-14)
                n_rooster = int(np.clip(blast_strength * 14.0, 2, 24))
                ang_r = self._rng.uniform(-0.65, 0.65, n_rooster)
                back_x = -float(aircraft.forward[0])
                back_z = -float(aircraft.forward[2])
                right_x = float(aircraft.right[0])
                right_z = float(aircraft.right[2])

                lat_offset = self._rng.uniform(-4.5, 4.5, n_rooster)
                long_offset = self._rng.uniform(-3.0, 6.0, n_rooster)
                sp_x = jet_x + right_x * lat_offset + back_x * long_offset
                sp_z = jet_z + right_z * lat_offset + back_z * long_offset
                sp_y = np.full(n_rooster, evaluate_gerstner_wave_height(jet_x, jet_z, sim_time) + 0.35, dtype=np.float32)

                v_mag = (10.0 + 14.0 * blast_strength) * self._rng.uniform(0.7, 1.3, n_rooster)
                vx = (back_x * np.cos(ang_r) + right_x * np.sin(ang_r)) * v_mag
                vz = (back_z * np.cos(ang_r) + right_z * np.sin(ang_r)) * v_mag
                vy = (5.5 + 9.5 * blast_strength) * self._rng.uniform(0.6, 1.35, n_rooster)

                self.spawn_particles(
                    np.column_stack([sp_x, sp_y, sp_z]).astype(np.float32),
                    np.column_stack([vx, vy, vz]).astype(np.float32),
                    self._rng.uniform(0.55, 1.35, n_rooster).astype(np.float32),
                    self._rng.uniform(1.6, 3.8, n_rooster).astype(np.float32),
                    np.full(n_rooster, 2, dtype=np.int32),
                )

            # ------------------------------------------------------------------
            # D) EMISSÃO CONTÍNUA DE PARTÍCULAS (BOW WAVE, POPA E WHITECAPS)
            # ------------------------------------------------------------------
            # 1. Spray de impacto na proa do CVN-65 (próximo à célula atual do jogador)
            carrier_cell_x = round(px / SCENE1_PERIOD) * SCENE1_PERIOD
            carrier_cell_z = round(pz / SCENE1_PERIOD) * SCENE1_PERIOD

            n_bow = 6
            side_sign = self._rng.choice([-1.0, 1.0], size=n_bow)
            z_b = carrier_cell_z + self._rng.uniform(-115.0, -96.0, n_bow)
            x_b = carrier_cell_x + side_sign * (2.5 + (z_b - (carrier_cell_z - 115.0)) * 0.42)
            y_b = np.full(n_bow, 0.55, dtype=np.float32)
            vel_b = np.column_stack([
                side_sign * self._rng.uniform(2.5, 6.5, n_bow),
                self._rng.uniform(3.2, 7.8, n_bow),
                self._rng.uniform(-1.5, 4.0, n_bow),
            ]).astype(np.float32)
            self.spawn_particles(
                np.column_stack([x_b, y_b, z_b]).astype(np.float32),
                vel_b,
                self._rng.uniform(0.8, 1.7, n_bow).astype(np.float32),
                self._rng.uniform(1.8, 3.6, n_bow).astype(np.float32),
                np.zeros(n_bow, dtype=np.int32),
            )

            # 2. Turbilhão de espuma na popa do CVN-65
            n_stern = 8
            z_st = carrier_cell_z + self._rng.uniform(112.0, 145.0, n_stern)
            x_st = carrier_cell_x + self._rng.uniform(-11.0, 11.0, n_stern)
            y_st = np.full(n_stern, 0.25, dtype=np.float32)
            vel_st = np.column_stack([
                self._rng.uniform(-2.2, 2.2, n_stern),
                self._rng.uniform(0.4, 2.2, n_stern),
                self._rng.uniform(8.0, 16.0, n_stern),
            ]).astype(np.float32)
            self.spawn_particles(
                np.column_stack([x_st, y_st, z_st]).astype(np.float32),
                vel_st,
                self._rng.uniform(2.0, 4.2, n_stern).astype(np.float32),
                self._rng.uniform(3.0, 6.2, n_stern).astype(np.float32),
                np.ones(n_stern, dtype=np.int32),
            )

        # ======================================================================
        # 2. CÁLCULO VETORIZADO DAS ONDAS ORBITAIS DE GERSTNER + NORMAIS + CORES
        # ======================================================================
        p1 = wx * 0.042 + wz * 0.028 - sim_time * 1.75
        p2 = -wx * 0.026 + wz * 0.048 - sim_time * 1.35
        p3 = wx * 0.078 - wz * 0.054 - sim_time * 2.35
        p4 = (wx + wz) * 0.130 + sim_time * 3.10

        s1, c1 = np.sin(p1), np.cos(p1)
        s2, c2 = np.sin(p2), np.cos(p2)
        s3, c3 = np.sin(p3), np.cos(p3)
        s4, c4 = np.sin(p4), np.cos(p4)

        # Deslocamento horizontal orbital trocoide das partículas de água (cristas agudas, cavados largos)
        disp_x = (-0.58 * s1 + 0.34 * s2 - 0.18 * s3) * self.edge_fade
        disp_z = (-0.42 * s1 - 0.52 * s2 + 0.15 * s3) * self.edge_fade

        # Altura vertical combinando os 4 trens de Gerstner + campo hidrodinâmico interativo (eta)
        gerstner_y = 0.92 * c1 + 0.68 * c2 + 0.30 * c3 + 0.14 * s4

        # Reduz suavemente a oscilação exatamente dentro do casco do CVN-65
        hull_damp = 1.0 - 0.82 * np.exp(-((wx_mod / 14.5) ** 2)) * np.exp(-((wz_mod / 98.0) ** 4))
        total_y = (gerstner_y * hull_damp + self.eta) * self.edge_fade

        self.vertices[:, :, 0] = wx + disp_x
        self.vertices[:, :, 1] = total_y
        self.vertices[:, :, 2] = wz + disp_z

        # Gradientes espaciais (analíticos de Gerstner + diferenças finitas da onda interativa eta)
        deta_dz, deta_dx = np.gradient(self.eta, self.GRID_STEP)
        dydx = (
            -0.92 * 0.042 * s1
            + 0.68 * 0.026 * s2
            - 0.30 * 0.078 * s3
            + 0.14 * 0.130 * c4
            + deta_dx
        ) * self.edge_fade
        dydz = (
            -0.92 * 0.028 * s1
            - 0.68 * 0.048 * s2
            + 0.30 * 0.054 * s3
            + 0.14 * 0.130 * c4
            + deta_dz
        ) * self.edge_fade

        inv_len = 1.0 / np.sqrt(dydx * dydx + 1.0 + dydz * dydz)
        self.normals[:, :, 0] = -dydx * inv_len
        self.normals[:, :, 1] = inv_len
        self.normals[:, :, 2] = -dydz * inv_len

        # Coordenadas UV dinâmicas com leve deriva de corrente marítima
        uv_scale = 1.0 / 32.0
        self.uvs[:, :, 0] = (wx + disp_x * 0.5) * uv_scale + sim_time * 0.012
        self.uvs[:, :, 1] = (wz + disp_z * 0.5) * uv_scale + sim_time * 0.008

        # Coloração física da água: azul profundo nos cavados, turquesa nas cristas e espuma branca
        height_norm = np.clip((total_y + 1.65) / 3.30, 0.0, 1.0)
        steepness = np.clip((total_y - 0.92) * 0.85, 0.0, 1.0)
        foam_factor = np.clip(steepness ** 1.6 + self.wake_foam * 0.92, 0.0, 1.0)

        r_col = (0.10 + 0.24 * height_norm) * (1.0 - foam_factor) + 0.94 * foam_factor
        g_col = (0.36 + 0.38 * height_norm) * (1.0 - foam_factor) + 0.97 * foam_factor
        b_col = (0.64 + 0.30 * height_norm) * (1.0 - foam_factor) + 1.00 * foam_factor

        self.colors[:, :, 0] = r_col
        self.colors[:, :, 1] = g_col
        self.colors[:, :, 2] = b_col
        self.colors[:, :, 3] = 1.0

        # Emite partículas de Whitecaps nas cristas mais altas próximas à aeronave
        if dt > 1e-4:
            high_crests = (total_y > 1.32) & (np.abs( self.local_x ) < 420.0) & (np.abs( self.local_z ) < 420.0)
            crest_indices = np.argwhere(high_crests)
            if len(crest_indices) > 0:
                pick_n = min(5, len(crest_indices))
                chosen = crest_indices[self._rng.choice(len(crest_indices), size=pick_n, replace=False)]
                cz_idx, cx_idx = chosen[:, 0], chosen[:, 1]
                c_pos = self.vertices[cz_idx, cx_idx].copy()
                c_pos[:, 1] += 0.18
                c_vel = np.column_stack([
                    self._rng.uniform(-1.8, 1.8, pick_n),
                    self._rng.uniform(1.2, 3.8, pick_n),
                    self._rng.uniform(-1.8, 2.5, pick_n),
                ]).astype(np.float32)
                self.spawn_particles(
                    c_pos,
                    c_vel,
                    self._rng.uniform(0.6, 1.4, pick_n).astype(np.float32),
                    self._rng.uniform(1.4, 2.8, pick_n).astype(np.float32),
                    np.zeros(pick_n, dtype=np.int32),
                )

            # ------------------------------------------------------------------
            # 3. ATUALIZAÇÃO CINEMÁTICA VETORIZADA DAS PARTÍCULAS LIVRES 3D
            # ------------------------------------------------------------------
            alive = self.p_life > 0.0
            if np.any(alive):
                self.p_life[alive] -= dt
                still_alive = self.p_life > 0.0
                if np.any(still_alive):
                    airborne = still_alive & (self.p_type != 1)
                    floating = still_alive & (self.p_type == 1)

                    # Partículas aéreas (Spray / Rooster Tail / Splash): sofrem gravidade e arrasto
                    if np.any(airborne):
                        self.p_vel[airborne, 1] -= 9.81 * dt
                        self.p_vel[airborne, 0] *= max(0.0, 1.0 - 0.45 * dt)
                        self.p_vel[airborne, 2] *= max(0.0, 1.0 - 0.45 * dt)
                        self.p_pos[airborne] += self.p_vel[airborne] * dt

                        # Quando a gota cai de volta no mar, vira espuma flutuante na onda!
                        hit_water = self.p_pos[airborne, 1] <= 0.15
                        if np.any(hit_water):
                            air_idx = np.where(airborne)[0][hit_water]
                            self.p_pos[air_idx, 1] = 0.15
                            self.p_vel[air_idx, 1] = 0.0
                            self.p_vel[air_idx, 0] *= 0.35
                            self.p_vel[air_idx, 2] *= 0.35
                            self.p_type[air_idx] = 1

                    # Partículas de espuma flutuante: acompanham a elevação da onda na superfície
                    if np.any(floating):
                        self.p_vel[floating] *= max(0.0, 1.0 - 1.15 * dt)
                        self.p_pos[floating] += self.p_vel[floating] * dt
                        fx = self.p_pos[floating, 0]
                        fz = self.p_pos[floating, 2]
                        fp1 = fx * 0.042 + fz * 0.028 - sim_time * 1.75
                        fp2 = -fx * 0.026 + fz * 0.048 - sim_time * 1.35
                        self.p_pos[floating, 1] = 0.92 * np.cos(fp1) + 0.68 * np.cos(fp2) + 0.14

    def _draw_horizon_ocean_skirt(self, player_pos, ocean_tex_id):
        """
        Desenha a saia oceânica externa (da borda da malha física em +-855m até +-3500m)
        onde `edge_fade == 0`, garantindo continuidade perfeita até o Sky Dome sem costuras.
        """
        cx = self.snap_ix * self.GRID_STEP
        cz = self.snap_iz * self.GRID_STEP
        inner = 0.5 * (self.GRID_N - 1) * self.GRID_STEP
        outer = 3450.0
        uv_s = 1.0 / 32.0
        du = self.sim_time * 0.012
        dv = self.sim_time * 0.008

        glBindTexture(GL_TEXTURE_2D, ocean_tex_id)
        glColor4f(0.22, 0.55, 0.79, 1.0)
        glNormal3f(0.0, 1.0, 0.0)

        # 4 grandes trapézios conectando o perímetro interno da malha de partículas ao horizonte
        rings = [
            # Norte (-Z)
            ([cx - inner, 0.0, cz - inner], [cx + inner, 0.0, cz - inner],
             [cx + outer, 0.0, cz - outer], [cx - outer, 0.0, cz - outer]),
            # Sul (+Z)
            ([cx + inner, 0.0, cz + inner], [cx - inner, 0.0, cz + inner],
             [cx - outer, 0.0, cz + outer], [cx + outer, 0.0, cz + outer]),
            # Oeste (-X)
            ([cx - inner, 0.0, cz + inner], [cx - inner, 0.0, cz - inner],
             [cx - outer, 0.0, cz - outer], [cx - outer, 0.0, cz + outer]),
            # Leste (+X)
            ([cx + inner, 0.0, cz - inner], [cx + inner, 0.0, cz + inner],
             [cx + outer, 0.0, cz + outer], [cx + outer, 0.0, cz - outer]),
        ]

        glBegin(GL_QUADS)
        for p1, p2, p3, p4 in rings:
            for pt in (p1, p2, p3, p4):
                glTexCoord2f(pt[0] * uv_s + du, pt[2] * uv_s + dv)
                glVertex3f(pt[0], pt[1], pt[2])
        glEnd()

    def _draw_hydrodynamic_particles(self):
        """
        Renderiza as partículas hidrodinâmicas livres (Spray, Espuma, Bow Wave e Rooster Tail)
        usando billboards orientados à câmera e blending suave.
        """
        alive_idx = np.where(self.p_life > 0.0)[0]
        n_alive = len(alive_idx)
        if n_alive == 0:
            return

        if self.spray_tex_id is None:
            self.spray_tex_id = _create_spray_particle_texture()

        # Extrai os vetores Right e Up da câmera a partir da matriz MODELVIEW atual para Billboarding
        mv = glGetFloatv(GL_MODELVIEW_MATRIX)
        cam_right = np.array([mv[0][0], mv[1][0], mv[2][0]], dtype=np.float32)
        cam_up = np.array([mv[0][1], mv[1][1], mv[2][1]], dtype=np.float32)

        pos = self.p_pos[alive_idx]
        sizes = self.p_size[alive_idx]
        life_ratio = np.clip(self.p_life[alive_idx] / self.p_max_life[alive_idx], 0.0, 1.0)
        p_types = self.p_type[alive_idx]

        # Expande as partículas ao longo de sua vida e suaviza o alpha (fade-in / fade-out)
        cur_scale = sizes * (1.35 - 0.35 * life_ratio)
        alpha = np.sin(life_ratio * math.pi) * np.where(p_types == 1, 0.55, 0.78)

        # Constrói os 4 cantos dos billboards de forma 100% vetorizada
        # Para partículas flutuantes (type == 1), inclina o quad quase horizontalmente sobre a onda
        is_float = (p_types == 1)[:, None]
        rx = np.where(is_float, np.array([1.0, 0.0, 0.0], dtype=np.float32), cam_right) * cur_scale[:, None]
        uy = np.where(is_float, np.array([0.0, 0.15, 1.0], dtype=np.float32), cam_up) * cur_scale[:, None]

        total_v = n_alive * 4
        qv = self.quad_verts[:total_v]
        qv[0::4] = pos - rx - uy
        qv[1::4] = pos + rx - uy
        qv[2::4] = pos + rx + uy
        qv[3::4] = pos - rx + uy

        qc = self.quad_colors[:total_v]
        qc[:, 0] = 0.92
        qc[:, 1] = 0.97
        qc[:, 2] = 1.00
        qc[0::4, 3] = alpha
        qc[1::4, 3] = alpha
        qc[2::4, 3] = alpha
        qc[3::4, 3] = alpha

        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_POLYGON_BIT)
        glDisable(GL_LIGHTING)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.spray_tex_id)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_FALSE)

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

    def draw(self, aircraft, ocean_tex_id, lighting_enabled=True, textures_enabled=True, wireframe_mode=False):
        """
        Renderiza a superfície física do corpo d'água (malha de partículas 96x96 + saia
        de horizonte) e o sistema de partículas hidrodinâmicas livres (spray e espuma).
        """
        glPushAttrib(GL_ENABLE_BIT | GL_LIGHTING_BIT | GL_TEXTURE_BIT | GL_CURRENT_BIT | GL_POLYGON_BIT)

        if lighting_enabled:
            glEnable(GL_LIGHTING)
        else:
            glDisable(GL_LIGHTING)

        if textures_enabled:
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, ocean_tex_id)
        else:
            glDisable(GL_TEXTURE_2D)

        if wireframe_mode:
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        else:
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

        glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.85, 0.78, 0.62, 1.0])
        glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 56.0)

        # 1. Saia de horizonte externa conectada sem costuras à borda da malha física
        self._draw_horizon_ocean_skirt(aircraft.pos, ocean_tex_id)

        # 2. Malha física de partículas acopladas (96x96 = 18.050 triângulos via Client Arrays)
        glEnableClientState(GL_VERTEX_ARRAY)
        glEnableClientState(GL_NORMAL_ARRAY)
        glEnableClientState(GL_TEXTURE_COORD_ARRAY)
        glEnableClientState(GL_COLOR_ARRAY)

        glVertexPointer(3, GL_FLOAT, 0, self.vertices)
        glNormalPointer(GL_FLOAT, 0, self.normals)
        glTexCoordPointer(2, GL_FLOAT, 0, self.uvs)
        glColorPointer(4, GL_FLOAT, 0, self.colors)

        glDrawElements(GL_TRIANGLES, len(self.indices), GL_UNSIGNED_INT, self.indices)

        glDisableClientState(GL_COLOR_ARRAY)
        glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        glDisableClientState(GL_NORMAL_ARRAY)
        glDisableClientState(GL_VERTEX_ARRAY)

        # 3. Sistema de Partículas Livres 3D (Spray, Espuma, Esteira e Rooster Tail)
        if not wireframe_mode:
            self._draw_hydrodynamic_particles()

        glPopAttrib()


# ==============================================================================
# 3. INSTÂNCIA SINGLETON E FUNÇÕES PÚBLICAS DE INTEGRAÇÃO (MAIN / KINEMATICS)
# ==============================================================================

_OCEAN_SYSTEM = None


def get_ocean_system():
    """Retorna ou inicializa o simulador físico do oceano da Cena 1."""
    global _OCEAN_SYSTEM
    if _OCEAN_SYSTEM is None:
        _OCEAN_SYSTEM = OceanPhysicsSystem()
    return _OCEAN_SYSTEM


def get_ocean_wave_height(x, z, sim_time=None):
    """
    Retorna a altura física (Y) da onda na coordenada (x, z) para detecção de
    colisão realista com as ondas em flight_kinematics.py.
    """
    sys_inst = get_ocean_system()
    t = sys_inst.sim_time if sim_time is None else sim_time
    return evaluate_gerstner_wave_height(float(x), float(z), float(t))


def trigger_ocean_splash(x, z, intensity=2.0):
    """Dispara uma coluna de partículas de água e ondas de choque no ponto de impacto (x, z)."""
    get_ocean_system().trigger_splash(float(x), float(z), float(intensity))


def update_ocean_physics(dt, aircraft, sim_time):
    """Atualiza o sistema físico de partículas do oceano a cada frame."""
    get_ocean_system().update(float(dt), aircraft, float(sim_time))


def draw_physical_ocean(aircraft, ocean_tex_id, sim_time, lighting_enabled=True, textures_enabled=True, wireframe_mode=False):
    """Renderiza o corpo d'água físico completo e suas partículas hidrodinâmicas."""
    sys_inst = get_ocean_system()
    if abs(sys_inst.sim_time - sim_time) > 1e-4 and sys_inst.sim_time == 0.0:
        sys_inst.update(0.0, aircraft, sim_time)
    sys_inst.draw(
        aircraft,
        ocean_tex_id,
        lighting_enabled=lighting_enabled,
        textures_enabled=textures_enabled,
        wireframe_mode=wireframe_mode,
    )


# ==============================================================================
# 4. CONSTRUÇÃO DA DISPLAY LIST DO PORTA-AVIÕES CVN-65 (COM OBRA VIVA SUBMERSA)
# ==============================================================================

def _draw_cvn65_submerged_keel():
    """
    Desenha a carena submersa vermelha anti-incrustante (Obra Viva: Y = -4.2m até Y = 0.05m)
    sob o casco do USS Enterprise (CVN-65), garantindo que nunca apareça um vão
    sob o navio quando os cavados das ondas físicas passarem abaixo de Y = 0.0.
    """
    keel_stations = [
        (-115.0,  0.4,  0.6),
        (-102.0,  3.5,  5.5),
        ( -78.0,  9.0, 12.0),
        ( -40.0, 13.5, 16.2),
        (  15.0, 14.0, 16.5),
        (  75.0, 12.5, 15.2),
        ( 112.0,  8.5, 11.5),
    ]
    glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT)
    glDisable(GL_TEXTURE_2D)
    glColor3f(0.46, 0.13, 0.11)  # Vermelho óxido naval (Anti-Fouling Hull Red)

    glBegin(GL_QUADS)
    for i in range(len(keel_stations) - 1):
        z1, wb1, wt1 = keel_stations[i]
        z2, wb2, wt2 = keel_stations[i + 1]
        # Costado submerso estibordo (+X)
        draw_quad_with_normal([wt1, 0.05, z1], [wt2, 0.05, z2], [wb2, -4.2, z2], [wb1, -4.2, z1])
        # Costado submerso bombordo (-X)
        draw_quad_with_normal([-wb1, -4.2, z1], [-wb2, -4.2, z2], [-wt2, 0.05, z2], [-wt1, 0.05, z1])
    glEnd()
    glPopAttrib()


def build_scene1_carrier_list(ocean_tex_id, deck_tex_id):
    """
    Compila a Display List estática da Cena 1 contendo o Porta-Aviões Nuclear
    USS Enterprise (CVN-65) completo + Obra Viva submersa para interação com as ondas.
    (O oceano físico dinâmico e suas partículas são renderizados via draw_physical_ocean).
    """
    dlist = glGenLists(1)
    glNewList(dlist, GL_COMPILE)

    # 1. Carena submersa (Obra Viva) para contato contínuo com os cavados das ondas físicas
    _draw_cvn65_submerged_keel()

    # 2. Porta-Aviões USS Enterprise (CVN-65) completo (cvn_65_model.py)
    draw_cvn65_carrier(deck_tex_id)

    glEndList()
    return dlist