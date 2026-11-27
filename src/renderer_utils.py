"""
================================================================================
TopGraphics | renderer_utils.py
Utilitários de renderização 3D compartilhados: carregamento de texturas de 'assets/texture/'
(com pré-processamento seamless para rocha/arenito, filtragem anisotrópica e fallback
procedural), iluminação (Phong) e primitivas com normal automática.
================================================================================
"""

import os
import sys
import math

import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from math_utils import compute_normal

# Constantes OpenGL para Filtragem Anisotrópica (nitidez em ângulos rasantes de solo/paredões)
GL_TEXTURE_MAX_ANISOTROPY_EXT = 0x84FE
GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT = 0x84FF


# ==============================================================================
# UTILITÁRIOS DE SÍNTESE SEAMLESS PARA TEXTURAS DE TERRENO / ROCHA
# ==============================================================================

def _box_blur_2d(img2d, radius):
    """Filtro média móvel 2D separável O(H*W) via somas cumulativas em NumPy."""
    r = max(1, int(radius))
    pad_x = np.pad(img2d, ((0, 0), (r, r)), mode="reflect")
    cs_x = np.cumsum(np.pad(pad_x, ((0, 0), (1, 0)), mode="constant"), axis=1)
    blur_x = (cs_x[:, 2 * r + 1:] - cs_x[:, :-2 * r - 1]) / float(2 * r + 1)

    pad_y = np.pad(blur_x, ((r, r), (0, 0)), mode="reflect")
    cs_y = np.cumsum(np.pad(pad_y, ((1, 0), (0, 0)), mode="constant"), axis=0)
    blur_y = (cs_y[2 * r + 1:, :] - cs_y[:-2 * r - 1, :]) / float(2 * r + 1)
    return blur_y


def _make_seamless_tile_rgb(arr, level_strength=0.85, blur_div=5, per_channel_level=False):
    """
    Converte uma textura natural não-tileable (rocha/arenito ou oceano) em um tile
    verdadeiramente seamless para GL_REPEAT (eliminando listras de borda e losangos
    criados pelo GL_MIRRORED_REPEAT):
      1. Equaliza variações de iluminação/cor de baixa frequência (remove vinhetas,
         manchas centrais e bordas escuras).
      2. Aplica wrap-blend separável (X e Y) preservando a variância/contraste local
         para que bordas opostas casem sem costura nem perda de nitidez.
    """
    img_f = arr.astype(np.float32)
    h, w = img_f.shape[:2]
    if h < 32 or w < 32:
        return img_f

    r1 = max(12, min(h, w) // int(blur_div))
    r2 = max(10, min(h, w) // (int(blur_div) + 2))

    # 1. Equalização de iluminação global (high-pass suave)
    if per_channel_level:
        leveled = np.empty_like(img_f)
        for ch in range(3):
            low_ch = _box_blur_2d(_box_blur_2d(img_f[:, :, ch], r1), r2)
            mean_ch = float(np.mean(img_f[:, :, ch]))
            leveled[:, :, ch] = img_f[:, :, ch] + (mean_ch - low_ch) * float(level_strength)
    else:
        lum = 0.299 * img_f[:, :, 0] + 0.587 * img_f[:, :, 1] + 0.114 * img_f[:, :, 2]
        low = _box_blur_2d(_box_blur_2d(lum, r1), r2)
        mean_lum = float(np.mean(lum))
        leveled = img_f + (mean_lum - low)[:, :, None] * float(level_strength)

    # 2. Blend separável preservando contraste (1 / sqrt(m^2 + (1-m)^2))
    ch_mean = np.mean(leveled, axis=(0, 1), keepdims=True)

    # Emenda horizontal (X)
    xs = np.linspace(0.0, 2.0 * math.pi, w, endpoint=False, dtype=np.float32)
    wx = 0.5 * (1.0 - np.cos(xs))
    mx = np.clip((wx - 0.12) / 0.76, 0.0, 1.0)
    mx = mx * mx * (3.0 - 2.0 * mx)
    roll_x = np.roll(leveled, w // 2, axis=1)
    denom_x = np.sqrt(mx * mx + (1.0 - mx) ** 2)[None, :, None]
    seam_x = ch_mean + (
        (leveled - ch_mean) * mx[None, :, None]
        + (roll_x - ch_mean) * (1.0 - mx[None, :, None])
    ) / denom_x

    # Emenda vertical (Y)
    ys = np.linspace(0.0, 2.0 * math.pi, h, endpoint=False, dtype=np.float32)
    wy = 0.5 * (1.0 - np.cos(ys))
    my = np.clip((wy - 0.12) / 0.76, 0.0, 1.0)
    my = my * my * (3.0 - 2.0 * my)
    roll_y = np.roll(seam_x, h // 2, axis=0)
    denom_y = np.sqrt(my * my + (1.0 - my) ** 2)[:, None, None]
    seamless = ch_mean + (
        (seam_x - ch_mean) * my[:, None, None]
        + (roll_y - ch_mean) * (1.0 - my[:, None, None])
    ) / denom_y

    return np.clip(seamless, 0.0, 255.0)


# ==============================================================================
# UPLOAD E CARREGAMENTO DE TEXTURAS (ASSETS + FALLBACK PROCEDURAL)
# ==============================================================================

def upload_texture_rgb(img, mirrored_repeat=True, use_mipmaps=True):
    """
    Envia uma imagem RGB (numpy uint8, shape (altura, largura, 3)) ao OpenGL como
    textura 2D, com Mipmaps e Filtragem Anisotrópica (até 16x) para nitidez em
    ângulos rasantes.
    """
    img = np.ascontiguousarray(img, dtype=np.uint8)
    height, width = img.shape[:2]
    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)

    wrap_mode = GL_MIRRORED_REPEAT if (mirrored_repeat and ("GL_MIRRORED_REPEAT" in globals())) else GL_REPEAT
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, wrap_mode)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, wrap_mode)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

    if use_mipmaps:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        try:
            max_aniso = glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT)
            if max_aniso and max_aniso > 1.0:
                glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAX_ANISOTROPY_EXT, min(16.0, float(max_aniso)))
        except Exception:
            pass
        gluBuild2DMipmaps(GL_TEXTURE_2D, GL_RGB, width, height, GL_RGB, GL_UNSIGNED_BYTE, img)
    else:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, width, height, 0, GL_RGB, GL_UNSIGNED_BYTE, img)

    return tex_id


def _resolve_asset_path(filename):
    """
    Localiza um arquivo de textura dentro do diretório 'assets/texture/' independentemente
    de o script ter sido executado da raiz, de dentro de 'src/' ou empacotado via PyInstaller
    (suporte automático a sys._MEIPASS e ao diretório do executável compilado).
    Também procura automaticamente por extensões alternativas (.png, .jpg, .jpeg, .bmp, .webp).
    """
    base_roots = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        base_roots.append(exe_dir)
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base_roots.append(meipass)

    module_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(module_dir)
    base_roots.extend([project_root, module_dir, os.getcwd()])

    search_dirs = []
    for root in base_roots:
        for sub in (os.path.join("assets", "texture"), "assets"):
            d = os.path.join(root, sub)
            if d not in search_dirs:
                search_dirs.append(d)
    for root in base_roots:
        if root not in search_dirs:
            search_dirs.append(root)

    stem, ext = os.path.splitext(filename)
    candidate_names = [filename]
    for alt_ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        if alt_ext.lower() != ext.lower():
            candidate_names.append(stem + alt_ext)

    for d in search_dirs:
        for cname in candidate_names:
            candidate_path = os.path.join(d, cname)
            if os.path.isfile(candidate_path):
                return candidate_path

    return None


def _prepare_asset_image(arr, mode="auto"):
    """
    Pré-processamento leve e limpo para texturas de 'assets/texture/':
      1. Remove tarjas pretas horizontais/verticais de letterbox nas bordas.
      2. No modo 'rock', equaliza a iluminação e gera bordas 100% seamless para GL_REPEAT
         (eliminando os losangos/cruzes gerados pelo espelhamento em rochas diagonais).
      3. Se a imagem estiver em escala de cinza escura, expande a faixa dinâmica e
         aplica a paleta de oceano ou arenito natural.
    """
    row_means = arr.mean(axis=(1, 2))
    col_means = arr.mean(axis=(0, 2))
    valid_rows = np.where(row_means > 25.0)[0]
    valid_cols = np.where(col_means > 25.0)[0]

    if len(valid_rows) > 64 and len(valid_cols) > 64:
        r0, r1 = int(valid_rows[0]), int(valid_rows[-1])
        c0, c1 = int(valid_cols[0]), int(valid_cols[-1])
        if r0 > 0 or r1 < arr.shape[0] - 1 or c0 > 0 or c1 < arr.shape[1] - 1:
            r0 = min(r0 + 2, r1 - 32)
            r1 = max(r1 - 2, r0 + 32)
            c0 = min(c0 + 2, c1 - 32)
            c1 = max(c1 - 2, c0 + 32)
            arr = arr[r0:r1 + 1, c0:c1 + 1].copy()

    # Para rocha/arenito e oceano, equaliza iluminação e sintetiza tile seamless antes da colorização:
    # No oceano, usa nivelamento por canal mais forte (0.98) para remover 100% de manchas/vinhetas
    # macro (as ondas grandes já vêm da malha física de Gerstner), mantendo apenas as micro-ondulações!
    if mode == "rock":
        arr_f = _make_seamless_tile_rgb(arr, level_strength=0.85, blur_div=5, per_channel_level=False)
    elif mode == "ocean":
        arr_f = _make_seamless_tile_rgb(arr, level_strength=0.98, blur_div=8, per_channel_level=True)
    else:
        arr_f = arr.astype(np.float32)

    rg_diff = float(np.mean(np.abs(arr_f[:, :, 0] - arr_f[:, :, 1])))
    gb_diff = float(np.mean(np.abs(arr_f[:, :, 1] - arr_f[:, :, 2])))

    if rg_diff < 12.0 and gb_diff < 12.0:
        lum = 0.299 * arr_f[:, :, 0] + 0.587 * arr_f[:, :, 1] + 0.114 * arr_f[:, :, 2]
        p_low, p_high = np.percentile(lum, [2.0, 99.0])
        norm = np.clip((lum - p_low) / max(1.0, (p_high - p_low)), 0.0, 1.0)

        if mode == "ocean":
            crest = norm ** 1.35
            r = np.clip(18.0 + 115.0 * crest, 0.0, 255.0)
            g = np.clip(68.0 + 135.0 * norm, 0.0, 255.0)
            b = np.clip(128.0 + 112.0 * (norm ** 0.85), 0.0, 255.0)
            return np.stack([r, g, b], axis=-1).astype(np.uint8)
        elif mode == "rock":
            curved = norm ** 0.90
            r = np.clip(74.0 + 162.0 * curved, 0.0, 255.0)
            g = np.clip(56.0 + 134.0 * curved, 0.0, 255.0)
            b = np.clip(42.0 + 102.0 * curved, 0.0, 255.0)
            return np.stack([r, g, b], axis=-1).astype(np.uint8)

    return np.clip(arr_f, 0.0, 255.0).astype(np.uint8)


def load_texture_from_assets(filename, fallback_fn=None, mode="auto", target_size=512, mirrored_repeat=None):
    """
    Carrega uma textura do diretório 'assets/texture/', aplica o pré-processamento,
    redimensiona para potência de 2 (int quadrado ou tupla (largura, altura)) e envia
    ao OpenGL com Mipmaps e Filtragem Anisotrópica.
    No modo 'rock', usa GL_REPEAT por padrão (pois o tile é convertido em seamless).
    """
    if isinstance(target_size, (tuple, list)) and len(target_size) == 2:
        dst_w, dst_h = int(target_size[0]), int(target_size[1])
    else:
        dst_w = dst_h = int(target_size)

    if mirrored_repeat is None:
        mirrored_repeat = (mode not in ("rock", "ocean"))

    asset_path = _resolve_asset_path(filename)

    if asset_path is not None and PIL_AVAILABLE:
        try:
            with Image.open(asset_path) as im:
                # Se o PNG possuir canal alfa (ex: overlay transparente de água),
                # recorta bordas transparentes e compõe sobre a cor mediana opaca
                # em vez de preto, evitando molduras escuras repetidas no tiling!
                if im.mode in ("RGBA", "LA") or ("transparency" in im.info):
                    arr_rgba = np.array(im.convert("RGBA"), dtype=np.uint8)
                    alpha = arr_rgba[:, :, 3]
                    valid_r = np.where(alpha.mean(axis=1) > 40.0)[0]
                    valid_c = np.where(alpha.mean(axis=0) > 40.0)[0]
                    if len(valid_r) > 64 and len(valid_c) > 64:
                        arr_rgba = arr_rgba[valid_r[0]:valid_r[-1] + 1, valid_c[0]:valid_c[-1] + 1]
                        alpha = arr_rgba[:, :, 3]
                    rgb_f = arr_rgba[:, :, :3].astype(np.float32)
                    opaque = alpha > 180
                    if np.any(opaque):
                        bg_col = np.median(rgb_f[opaque], axis=0)
                    else:
                        bg_col = np.array([35.0, 95.0, 155.0], dtype=np.float32)
                    a_norm = (alpha.astype(np.float32) / 255.0)[:, :, None]
                    arr = np.clip(rgb_f * a_norm + bg_col[None, None, :] * (1.0 - a_norm), 0.0, 255.0).astype(np.uint8)
                else:
                    arr = np.array(im.convert("RGB"), dtype=np.uint8)

            arr = _prepare_asset_image(arr, mode=mode)

            if arr.shape[1] != dst_w or arr.shape[0] != dst_h:
                resample_filter = getattr(Image, "Resampling", Image).LANCZOS
                im_resized = Image.fromarray(arr).resize((dst_w, dst_h), resample_filter)
                arr = np.array(im_resized, dtype=np.uint8)

            wrap_str = "MIRRORED" if mirrored_repeat else "REPEAT(seamless)"
            print(f"[Texturas] Carregada de assets/texture: '{os.path.basename(asset_path)}' ({dst_w}x{dst_h}, modo={mode}, wrap={wrap_str})")
            return upload_texture_rgb(arr, mirrored_repeat=mirrored_repeat, use_mipmaps=True)

        except Exception as exc:
            print(f"[Aviso] Falha ao carregar textura '{filename}' ({exc}). Usando fallback procedural.")
    else:
        if not PIL_AVAILABLE:
            print(f"[Aviso] Biblioteca Pillow (PIL) não instalada ('pip install Pillow'). Usando textura procedural para '{filename}'.")
        else:
            print(f"[Aviso] Arquivo 'assets/texture/{filename}' não encontrado. Usando textura procedural de fallback.")

    if fallback_fn is not None:
        return fallback_fn()

    default_img = np.full((64, 64, 3), 180, dtype=np.uint8)
    return upload_texture_rgb(default_img, mirrored_repeat=mirrored_repeat)


def load_window_icon_images(filename="icon.png", sizes=(16, 32, 48, 64, 128)):
    """
    Carrega o ícone da janela (ex: 'assets/icon.png' ou 'assets/texture/icon.png')
    e gera uma lista de imagens PIL RGBA redimensionadas com LANCZOS para uso em
    glfw.set_window_icon(), evitando rejeição em X11 (_NET_WM_ICON) por tamanho
    excessivo e garantindo nitidez na barra de título, Alt+Tab e barra de tarefas.
    """
    if not PIL_AVAILABLE:
        return []

    icon_path = _resolve_asset_path(filename)
    if icon_path is None:
        icon_path = _resolve_asset_path("icon.ico")
    if icon_path is None:
        return []

    try:
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        with Image.open(icon_path) as im:
            base_rgba = im.convert("RGBA")
            return [base_rgba.resize((s, s), resample_filter) for s in sizes]
    except Exception as exc:
        print(f"[Janela] Aviso ao carregar ícone '{filename}': {exc}")
        return []


# ==============================================================================
# ILUMINAÇÃO
# ==============================================================================

def setup_lighting():
    """
    Configura o modelo de iluminação de Phong/Gouraud com Iluminação Hemisférica Suave:
      - GL_LIGHT0: Luz Direcional Principal do Sol (Key Light com elevação mínima de sombreamento).
      - GL_LIGHT1: Luz Pontual dinâmica dos pós-combustores do F-14 (Afterburner).
      - GL_LIGHT2: Luz Direcional de Preenchimento Atmosférico (Sky/Hemisphere Fill Light oposta ao Sol),
        eliminando sombras excessivamente escuras ao inclinar ou girar a aeronave.
    """
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_LIGHT1)
    glEnable(GL_LIGHT2)

    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    glShadeModel(GL_SMOOTH)
    glEnable(GL_NORMALIZE)

    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.16, 0.16, 0.18, 1.0])

    glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.26, 0.24, 0.26, 1.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE,  [0.62, 0.56, 0.48, 1.0])
    glLightfv(GL_LIGHT0, GL_SPECULAR, [0.38, 0.35, 0.30, 1.0])

    glLightfv(GL_LIGHT1, GL_AMBIENT,  [0.0, 0.0, 0.0, 1.0])
    glLightfv(GL_LIGHT1, GL_DIFFUSE,  [1.0, 0.55, 0.15, 1.0])
    glLightfv(GL_LIGHT1, GL_SPECULAR, [1.0, 0.70, 0.30, 1.0])
    glLightf(GL_LIGHT1, GL_CONSTANT_ATTENUATION, 1.0)
    glLightf(GL_LIGHT1, GL_LINEAR_ATTENUATION, 0.04)
    glLightf(GL_LIGHT1, GL_QUADRATIC_ATTENUATION, 0.008)

    glLightfv(GL_LIGHT2, GL_AMBIENT,  [0.0, 0.0, 0.0, 1.0])
    glLightfv(GL_LIGHT2, GL_DIFFUSE,  [0.26, 0.28, 0.34, 1.0])
    glLightfv(GL_LIGHT2, GL_SPECULAR, [0.0, 0.0, 0.0, 1.0])


# ==============================================================================
# PRIMITIVAS COM NORMAL E UV AUTOMÁTICOS
# ==============================================================================

def draw_quad_with_normal(p1, p2, p3, p4, uv_scale=1.0):
    """Desenha um quadrilátero calculando automaticamente seu vetor normal e coordenadas UV."""
    n = compute_normal(p1, p2, p3)
    glNormal3fv(n)
    glTexCoord2f(0.0, 0.0)
    glVertex3fv(p1)
    glTexCoord2f(uv_scale, 0.0)
    glVertex3fv(p2)
    glTexCoord2f(uv_scale, uv_scale)
    glVertex3fv(p3)
    glTexCoord2f(0.0, uv_scale)
    glVertex3fv(p4)


def draw_tri_with_normal(p1, p2, p3):
    """Desenha um triângulo calculando seu vetor normal unitário."""
    n = compute_normal(p1, p2, p3)
    glNormal3fv(n)
    glTexCoord2f(0.0, 0.0)
    glVertex3fv(p1)
    glTexCoord2f(1.0, 0.0)
    glVertex3fv(p2)
    glTexCoord2f(0.5, 1.0)
    glVertex3fv(p3)


def draw_box(dx, dy, dz, uv_scale=1.0):
    """Desenha um paralelepípedo centrado na origem com dimensões (dx, dy, dz)."""
    hx, hy, hz = dx * 0.5, dy * 0.5, dz * 0.5
    glBegin(GL_QUADS)
    draw_quad_with_normal([-hx, hy, -hz], [-hx, hy, hz], [hx, hy, hz], [hx, hy, -hz], uv_scale)
    draw_quad_with_normal([-hx, -hy, hz], [-hx, -hy, -hz], [hx, -hy, -hz], [hx, -hy, hz], uv_scale)
    draw_quad_with_normal([hx, -hy, -hz], [-hx, -hy, -hz], [-hx, hy, -hz], [hx, hy, -hz], uv_scale)
    draw_quad_with_normal([-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz], uv_scale)
    draw_quad_with_normal([hx, -hy, hz], [hx, -hy, -hz], [hx, hy, -hz], [hx, hy, hz], uv_scale)
    draw_quad_with_normal([-hx, -hy, -hz], [-hx, -hy, hz], [-hx, hy, hz], [-hx, hy, -hz], uv_scale)
    glEnd()
