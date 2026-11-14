"""
================================================================================
TopGraphics | skin_manager.py
Gerenciador de Skins do F-14 Tomcat:
  - 1 Padrão Original (VF-84 Naval sem skin externa na fuselagem)
  - 3 Padrões Metálicos (brushed_gold, polished_silver, matte_black_steel)
  - 3 Padrões de Camuflagem (digital, tiger_stripes, blobs)
  - 5 Paletas de Cores para Camuflagem (arctic, desert, navy, urban, woodland)
    mapeadas a partir dos canais de alto contraste:
    [Vermelho Vivo, Verde Claro, Azul Escuro, Preto].
================================================================================
"""

# TODO: fix metallic and camo pattern distortions

import os
import math
import numpy as np
from OpenGL.GL import *

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from renderer_utils import _resolve_asset_path, upload_texture_rgb


# ==============================================================================
# 1. DEFINIÇÃO DOS CANAIS DE ALTO CONTRASTE E PALETAS DE CAMUFLAGEM
# ==============================================================================

# Centroides RGB dos 4 canais da máscara de camuflagem:
# [0] Vermelho Vivo, [1] Verde Claro, [2] Azul Escuro, [3] Preto
MASK_REFERENCE_RGB = np.array([
    [245.0,  38.0,  28.0],  # Canal 0: Vermelho vivo (Red)
    [148.0, 228.0, 108.0],  # Canal 1: Verde claro (Light Green)
    [ 16.0,  75.0, 158.0],  # Canal 2: Azul escuro (Dark Blue)
    [  8.0,   8.0,   8.0],  # Canal 3: Preto (Black)
], dtype=np.float32)

# As 5 paletas mapeiam na mesma ordem: [Vermelho Vivo, Verde Claro, Azul Escuro, Preto]
CAMO_PALETTES = {
    "arctic": {
        "label": "ARCTIC (BRANCO / CINZA / PRETO)",
        "colors": np.array([
            [182, 192, 204],  # Vermelho vivo -> Cinza gelo médio-claro
            [242, 246, 250],  # Verde claro   -> Branco ártico
            [118, 128, 140],  # Azul escuro   -> Cinza polar escuro
            [ 28,  32,  38],  # Preto         -> Preto carvão ártico
        ], dtype=np.uint8),
    },
    "desert": {
        "label": "DESERT (AMARELO / MARROM / LARANJA)",
        "colors": np.array([
            [218, 142,  68],  # Vermelho vivo -> Laranja deserto vibrante
            [236, 214, 164],  # Verde claro   -> Amarelo claro / Areia
            [168, 104,  54],  # Azul escuro   -> Terracota / Ocre queimado
            [ 82,  52,  34],  # Preto         -> Marrom terra escuro
        ], dtype=np.uint8),
    },
    "navy": {
        "label": "NAVY (TONALIDADES DE AZUL)",
        "colors": np.array([
            [ 72, 118, 168],  # Vermelho vivo -> Azul cobalto naval
            [132, 168, 204],  # Verde claro   -> Azul claro superioridade aérea
            [ 36,  74, 118],  # Azul escuro   -> Azul marinho profundo
            [ 16,  32,  54],  # Preto         -> Azul abissal noturno
        ], dtype=np.uint8),
    },
    "urban": {
        "label": "URBAN (PRETO / CINZA / ASFALTO)",
        "colors": np.array([
            [122, 128, 136],  # Vermelho vivo -> Cinza concreto médio
            [176, 182, 190],  # Verde claro   -> Cinza urbano claro
            [ 72,  78,  86],  # Azul escuro   -> Cinza asfalto
            [ 24,  26,  30],  # Preto         -> Preto tático fosco
        ], dtype=np.uint8),
    },
    "woodland": {
        "label": "WOODLAND (VERDE MATA / MARROM / ASFALTO)",
        "colors": np.array([
            [112, 128,  68],  # Vermelho vivo -> Verde oliva / musgo
            [ 68, 104,  54],  # Verde claro   -> Verde mata fechado
            [ 96,  66,  42],  # Azul escuro   -> Marrom floresta
            [ 38,  42,  46],  # Preto         -> Cinza asfalto escuro
        ], dtype=np.uint8),
    },
}

PALETTE_ORDER = ["arctic", "desert", "navy", "urban", "woodland"]


# ==============================================================================
# 2. CATÁLOGO DE PADRÕES DE SKIN (PADRÃO + 3 METÁLICOS + 3 CAMUFLAGENS)
# ==============================================================================

SKIN_PATTERNS = [
    {
        "id": "default",
        "name": "PADRAO VF-84 JOLLY ROGERS",
        "category": "default",
        "asset": None,
        "specular": [0.75, 0.75, 0.80, 1.0],
        "shininess": 64.0,
        "base_tint": (0.95, 0.96, 0.98),
    },
    {
        "id": "brushed_gold",
        "name": "METALICO: OURO ESCOVADO",
        "category": "metallic",
        "asset": "brushed_gold.png",
        "specular": [1.00, 0.88, 0.45, 1.0],
        "shininess": 78.0,
        "base_tint": (1.00, 0.96, 0.88),
    },
    {
        "id": "polished_silver",
        "name": "METALICO: PRATA POLIDO",
        "category": "metallic",
        "asset": "polished_silver.png",
        "specular": [1.00, 1.00, 1.00, 1.0],
        "shininess": 112.0,
        "base_tint": (0.98, 0.99, 1.00),
    },
    {
        "id": "matte_black_steel",
        "name": "METALICO: ACO NEGRO FOSCO",
        "category": "metallic",
        "asset": "matte_black_steel.png",
        "specular": [0.34, 0.36, 0.40, 1.0],
        "shininess": 22.0,
        "base_tint": (0.92, 0.93, 0.95),
    },
    {
        "id": "digital",
        "name": "CAMO: DIGITAL (PIXELS)",
        "category": "camo",
        "asset": "digital.png",
        "specular": [0.18, 0.18, 0.18, 1.0],
        "shininess": 12.0,
        "base_tint": (0.96, 0.96, 0.96),
    },
    {
        "id": "tiger_stripes",
        "name": "CAMO: TIGER STRIPE",
        "category": "camo",
        "asset": "tiger_stripes.png",
        "specular": [0.18, 0.18, 0.18, 1.0],
        "shininess": 12.0,
        "base_tint": (0.96, 0.96, 0.96),
    },
    {
        "id": "blobs",
        "name": "CAMO: BLOBS (ORGANICO)",
        "category": "camo",
        "asset": "blobs.png",
        "specular": [0.18, 0.18, 0.18, 1.0],
        "shininess": 12.0,
        "base_tint": (0.96, 0.96, 0.96),
    },
]


# ==============================================================================
# 3. PROCESSAMENTO DE IMAGEM E FALLBACKS PROCEDURAIS
# ==============================================================================

def _load_raw_asset_rgb(filename, target_size=512, preserve_sharp_pixels=False):
    """
    Carrega a imagem de 'assets/' sem cortar bordas escuras (evitando perda em
    matte_black_steel ou máscaras pretas) e redimensiona para target_size x target_size.
    """
    asset_path = _resolve_asset_path(filename)
    if asset_path is not None and PIL_AVAILABLE:
        try:
            with Image.open(asset_path) as im:
                im_rgb = im.convert("RGB")
                if im_rgb.size != (target_size, target_size):
                    resample_Namespace = getattr(Image, "Resampling", Image)
                    interp = resample_Namespace.NEAREST if preserve_sharp_pixels else resample_Namespace.LANCZOS
                    im_rgb = im_rgb.resize((target_size, target_size), interp)
                arr = np.array(im_rgb, dtype=np.uint8)
            print(f"[Skins] Asset carregado: '{os.path.basename(asset_path)}' ({target_size}x{target_size})")
            return arr
        except Exception as exc:
            print(f"[Skins] Aviso: falha ao ler '{filename}' ({exc}). Usando fallback procedural.")
    else:
        print(f"[Skins] Aviso: 'assets/{filename}' não encontrado. Gerando padrão procedural.")
    return None


def _generate_fallback_metallic(pattern_id, size=512):
    """Fallback procedural caso algum asset metálico não seja encontrado."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    streak = np.sin(x * 0.35) * 6.0 + np.sin(x * 1.15 + y * 0.05) * 4.0 + np.cos(y * 0.08) * 3.0

    if pattern_id == "brushed_gold":
        base = np.array([218.0, 178.0, 72.0], dtype=np.float32)
    elif pattern_id == "polished_silver":
        base = np.array([212.0, 218.0, 226.0], dtype=np.float32)
    else:  # matte_black_steel
        base = np.array([48.0, 52.0, 58.0], dtype=np.float32)

    img = np.clip(base[None, None, :] + streak[:, :, None], 0.0, 255.0).astype(np.uint8)
    return img


def _generate_fallback_camo_mask(pattern_id, size=512):
    """
    Gera máscara procedural nas 4 cores de alto contraste (Vermelho, Verde, Azul, Preto)
    caso algum arquivo de camuflagem não seja encontrado em assets/.
    """
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    mask = np.zeros((size, size, 3), dtype=np.uint8)

    if pattern_id == "digital":
        bx = (x // 16).astype(np.int32)
        by = (y // 16).astype(np.int32)
        h = (bx * 374761393 + by * 668265263) % 100
        idx = np.select([h < 18, h < 52, h < 78], [0, 1, 2], default=3)
    elif pattern_id == "tiger_stripes":
        wave = np.sin(y * 0.055 + np.sin(x * 0.025) * 2.2) + 0.45 * np.cos(x * 0.04 - y * 0.03)
        idx = np.select([wave > 0.45, wave > -0.15], [3, 1], default=2)
    else:  # blobs
        v1 = np.sin(x * 0.024) * np.cos(y * 0.024) + 0.5 * np.sin((x + y) * 0.018)
        v2 = np.cos(x * 0.031 - y * 0.022)
        idx = np.select([v1 > 0.45, v2 > 0.35, v1 < -0.25], [1, 0, 2], default=3)

    ref_u8 = MASK_REFERENCE_RGB.astype(np.uint8)
    mask[:, :] = ref_u8[idx]
    return mask


def apply_camo_palette_replacement(mask_rgb, palette_key, sharp_edges=False):
    """
    Substitui os 4 canais de alto contraste (Vermelho vivo, Verde claro, Azul escuro, Preto)
    pelas cores correspondentes da paleta selecionada.
      - Para 'digital', usa classificação direta (argmin) para manter os pixels nítidos.
      - Para 'tiger_stripes' e 'blobs', usa interpolação inversa da distância entre os
        2 canais mais próximos, preservando bordas anti-aliased suaves sem misturar
        cores não adjacentes.
    """
    palette_colors = CAMO_PALETTES[palette_key]["colors"].astype(np.float32)
    img_f = mask_rgb.astype(np.float32)

    # Distância quadrática (H, W, 4) para cada um dos 4 canais de referência
    diffs = img_f[:, :, None, :] - MASK_REFERENCE_RGB[None, None, :, :]
    dist_sq = np.sum(diffs * diffs, axis=-1)

    if sharp_edges:
        nearest_idx = np.argmin(dist_sq, axis=-1)
        out = palette_colors[nearest_idx]
    else:
        idx_sorted = np.argsort(dist_sq, axis=-1)
        idx1 = idx_sorted[:, :, 0]
        idx2 = idx_sorted[:, :, 1]

        d1 = np.take_along_axis(dist_sq, idx1[..., None], axis=-1)[..., 0]
        d2 = np.take_along_axis(dist_sq, idx2[..., None], axis=-1)[..., 0]

        w1 = 1.0 / ((d1 + 1.0) ** 2.2)
        w2 = 1.0 / ((d2 + 1.0) ** 2.2)
        alpha = (w1 / (w1 + w2))[..., None]

        c1 = palette_colors[idx1]
        c2 = palette_colors[idx2]
        out = c1 * alpha + c2 * (1.0 - alpha)

    # Leve micro-textura de chapa aeronáutica para enriquecer a interação com a luz Phong
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    panel_grain = (((xx * 13 + yy * 29) % 7) - 3.0) * 0.85
    out = np.clip(out + panel_grain[:, :, None], 0.0, 255.0).astype(np.uint8)
    return out


# ==============================================================================
# 4. CLASSE GERENCIADORA DE SKINS EM TEMPO REAL
# ==============================================================================

class SkinManager:
    """
    Controla o padrão de skin ativo, a paleta de camuflagem ativa e mantém
    cache das texturas OpenGL compiladas para troca instantânea em tempo real.
    """
    def __init__(self, default_wing_tex_id):
        self.default_wing_tex_id = default_wing_tex_id
        self.pattern_index = 0
        self.palette_index = 0

        self._raw_mask_cache = {}
        self._gl_texture_cache = {}

    @property
    def current_pattern(self):
        return SKIN_PATTERNS[self.pattern_index]

    @property
    def current_palette_key(self):
        return PALETTE_ORDER[self.palette_index]

    @property
    def current_palette_info(self):
        return CAMO_PALETTES[self.current_palette_key]

    def is_custom_skin_active(self):
        """Retorna True se a skin atual for Metálica ou Camuflagem (não-padrão)."""
        return self.current_pattern["category"] != "default"

    def is_camo_active(self):
        """Retorna True se o padrão atual for um dos 3 padrões de camuflagem."""
        return self.current_pattern["category"] == "camo"

    def next_pattern(self):
        """Avança para o próximo padrão de skin (Tecla 'K')."""
        self.pattern_index = (self.pattern_index + 1) % len(SKIN_PATTERNS)
        pat = self.current_pattern
        if pat["category"] == "camo":
            pal_label = self.current_palette_info["label"]
            print(f"[Skin] Padrão: {pat['name']} | Paleta: {pal_label}")
        else:
            print(f"[Skin] Padrão: {pat['name']}")

    def next_palette(self):
        """Avança para a próxima paleta de cores de camuflagem (Tecla 'P')."""
        self.palette_index = (self.palette_index + 1) % len(PALETTE_ORDER)
        pal_label = self.current_palette_info["label"]
        if not self.is_camo_active():
            print(f"[Paleta Camo] Pré-selecionada: {pal_label} (Pressione 'K' até um padrão CAMO)")
        else:
            print(f"[Paleta Camo] Aplicada: {pal_label} em {self.current_pattern['name']}")

    def get_active_texture_id(self):
        """
        Retorna o texture ID OpenGL correspondente à combinação (padrão, paleta) atual.
        Compila e envia à GPU na primeira vez que a combinação é solicitada.
        """
        pat = self.current_pattern
        pat_id = pat["id"]
        cat = pat["category"]

        if cat == "default":
            return self.default_wing_tex_id

        if cat == "metallic":
            cache_key = (pat_id, None)
            if cache_key not in self._gl_texture_cache:
                arr = _load_raw_asset_rgb(pat["asset"], target_size=512, preserve_sharp_pixels=False)
                if arr is None:
                    arr = _generate_fallback_metallic(pat_id, size=512)
                self._gl_texture_cache[cache_key] = upload_texture_rgb(arr, mirrored_repeat=True, use_mipmaps=True)
            return self._gl_texture_cache[cache_key]

        # Categoria 'camo': combina máscara de alto contraste + paleta ativa
        pal_key = self.current_palette_key
        cache_key = (pat_id, pal_key)
        if cache_key not in self._gl_texture_cache:
            if pat_id not in self._raw_mask_cache:
                is_digital = (pat_id == "digital")
                raw_mask = _load_raw_asset_rgb(pat["asset"], target_size=512, preserve_sharp_pixels=is_digital)
                if raw_mask is None:
                    raw_mask = _generate_fallback_camo_mask(pat_id, size=512)
                self._raw_mask_cache[pat_id] = raw_mask

            colored_arr = apply_camo_palette_replacement(
                self._raw_mask_cache[pat_id],
                pal_key,
                sharp_edges=(pat_id == "digital")
            )
            self._gl_texture_cache[cache_key] = upload_texture_rgb(
                colored_arr, mirrored_repeat=True, use_mipmaps=True
            )

        return self._gl_texture_cache[cache_key]

    def get_hud_summary(self):
        """Retorna strings formatadas para exibição no HUD e na Cena 3."""
        pat = self.current_pattern
        if pat["category"] == "camo":
            return pat["name"], self.current_palette_info["label"], self.current_palette_info["colors"]
        elif pat["category"] == "metallic":
            return pat["name"], "ACABAMENTO METALICO ESPECIAL", None
        else:
            return pat["name"], "ESQUADRAO NAVAL ORIGINAL", None