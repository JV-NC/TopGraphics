"""
================================================================================
TopGraphics | renderer_utils.py
Utilitários de renderização compartilhados: carregamento de texturas de 'assets/'
(com fallback procedural), iluminação (Phong), primitivas com normal automática
e overlays 2D (HUD / Game Over).
================================================================================
"""

import os
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


# ==============================================================================
# UPLOAD E CARREGAMENTO DE TEXTURAS (ASSETS + FALLBACK PROCEDURAL)
# ==============================================================================

def upload_texture_rgb(img, mirrored_repeat=True, use_mipmaps=True):
    """
    Envia uma imagem RGB (numpy uint8, shape (altura, largura, 3)) ao OpenGL como
    textura 2D. Utiliza GL_MIRRORED_REPEAT (para evitar costuras visíveis entre
    ladrilhos adjacentes) e Mipmaps (para evitar serrilhado/cintilação no horizonte
    e melhorar o desempenho de cache da GPU).
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
        gluBuild2DMipmaps(GL_TEXTURE_2D, GL_RGB, width, height, GL_RGB, GL_UNSIGNED_BYTE, img)
    else:
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, width, height, 0, GL_RGB, GL_UNSIGNED_BYTE, img)

    return tex_id


def _resolve_asset_path(filename):
    """
    Localiza um arquivo de textura dentro do diretório 'assets/' independentemente
    de o script ter sido executado da raiz do projeto ou de dentro de 'src/'.
    Também procura automaticamente por extensões alternativas (.jpg, .jpeg, .png, .bmp, .webp).
    """
    module_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(module_dir)

    search_dirs = [
        os.path.join(project_root, "assets"),
        os.path.join(module_dir, "assets"),
        os.path.join(os.getcwd(), "assets"),
        project_root,
        module_dir,
        os.getcwd(),
    ]

    stem, ext = os.path.splitext(filename)
    candidate_names = [filename]
    for alt_ext in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
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
    Pré-processamento leve e limpo para texturas de 'assets/':
      1. Remove tarjas pretas horizontais/verticais de letterbox nas bordas.
      2. Se a imagem estiver em escala de cinza escura (onde o brilho máximo é ~80/255), expande a faixa dinâmica
         para que os detalhes de ondas ou estratos rochosos fiquem nítidos sob a luz.
    """
    # 1. Remove tarjas pretas de letterbox nas bordas (se existirem)
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

    # 2. Normalização para texturas monocromáticas escuras
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
            # Expande o contraste dos estratos de 'sandstone.png' com tom de arenito quente
            curved = norm ** 0.90
            r = np.clip(68.0 + 165.0 * curved, 0.0, 255.0)
            g = np.clip(54.0 + 138.0 * curved, 0.0, 255.0)
            b = np.clip(42.0 + 108.0 * curved, 0.0, 255.0)
            return np.stack([r, g, b], axis=-1).astype(np.uint8)

    return arr


def load_texture_from_assets(filename, fallback_fn=None, mode="auto", target_size=512):
    """
    Carrega uma textura do diretório 'assets/', aplica o pré-processamento leve, redimensiona para potência de 2
    (target_size x target_size) e envia ao OpenGL com Mipmaps.
    Se o arquivo não for encontrado ou o Pillow não estiver instalado, executa fallback_fn().
    """
    asset_path = _resolve_asset_path(filename)

    if asset_path is not None and PIL_AVAILABLE:
        try:
            with Image.open(asset_path) as im:
                im_rgb = im.convert("RGB")
                arr = np.array(im_rgb, dtype=np.uint8)

            arr = _prepare_asset_image(arr, mode=mode)

            if arr.shape[0] != target_size or arr.shape[1] != target_size:
                resample_filter = getattr(Image, "Resampling", Image).LANCZOS
                im_resized = Image.fromarray(arr).resize((target_size, target_size), resample_filter)
                arr = np.array(im_resized, dtype=np.uint8)

            print(f"[Texturas] Carregada de assets: '{os.path.basename(asset_path)}' ({target_size}x{target_size}, modo={mode})")
            return upload_texture_rgb(arr, mirrored_repeat=True, use_mipmaps=True)

        except Exception as exc:
            print(f"[Aviso] Falha ao carregar textura '{filename}' ({exc}). Usando fallback procedural.")
    else:
        if not PIL_AVAILABLE:
            print(f"[Aviso] Biblioteca Pillow (PIL) não instalada ('pip install Pillow'). Usando textura procedural para '{filename}'.")
        else:
            print(f"[Aviso] Arquivo 'assets/{filename}' não encontrado. Usando textura procedural de fallback.")

    if fallback_fn is not None:
        return fallback_fn()

    default_img = np.full((64, 64, 3), 180, dtype=np.uint8)
    return upload_texture_rgb(default_img)


# ==============================================================================
# ILUMINAÇÃO
# ==============================================================================

def setup_lighting():
    """Configura o modelo de iluminação de Phong/Gouraud."""
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)  # Luz 0: Sol Direcional
    glEnable(GL_LIGHT1)  # Luz 1: Brilho dinâmico dos pós-combustores do F-14

    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    glShadeModel(GL_SMOOTH)
    glEnable(GL_NORMALIZE)

    glLightfv(GL_LIGHT0, GL_AMBIENT,  [0.28, 0.26, 0.30, 1.0])
    glLightfv(GL_LIGHT0, GL_DIFFUSE,  [1.00, 0.88, 0.72, 1.0])
    glLightfv(GL_LIGHT0, GL_SPECULAR, [1.00, 0.95, 0.85, 1.0])

    glLightfv(GL_LIGHT1, GL_AMBIENT,  [0.0, 0.0, 0.0, 1.0])
    glLightfv(GL_LIGHT1, GL_DIFFUSE,  [1.0, 0.55, 0.15, 1.0])
    glLightfv(GL_LIGHT1, GL_SPECULAR, [1.0, 0.70, 0.30, 1.0])
    glLightf(GL_LIGHT1, GL_CONSTANT_ATTENUATION, 1.0)
    glLightf(GL_LIGHT1, GL_LINEAR_ATTENUATION, 0.04)
    glLightf(GL_LIGHT1, GL_QUADRATIC_ATTENUATION, 0.008)


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


# ==============================================================================
# HUD DO COCKPIT E OVERLAY DE COLISÃO / GAME OVER
# ==============================================================================

def draw_cockpit_hud(width, height, aircraft):
    """
    Desenha um Head-Up Display (HUD) verde tático em projeção ortográfica 2D
    quando o usuário está na Câmera 2 (Cockpit / Primeira Pessoa).
    """
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, width, 0, height)

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glPushAttrib(GL_ENABLE_BIT | GL_LINE_BIT)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)

    cx, cy = width * 0.5, height * 0.5
    glColor3f(0.15, 1.0, 0.25)
    glLineWidth(2.0)

    # Retículo central de mira
    glBegin(GL_LINES)
    glVertex2f(cx - 25, cy); glVertex2f(cx - 8, cy)
    glVertex2f(cx + 8, cy);  glVertex2f(cx + 25, cy)
    glVertex2f(cx, cy - 25); glVertex2f(cx, cy - 8)
    glVertex2f(cx, cy + 8);  glVertex2f(cx, cy + 25)
    glEnd()

    # Horizonte Artificial
    roll_angle = math.degrees(math.atan2(aircraft.right[1], aircraft.up[1]))
    pitch_angle = math.degrees(math.asin(np.clip(aircraft.forward[1], -1.0, 1.0)))

    glPushMatrix()
    glTranslatef(cx, cy, 0.0)
    glRotatef(-roll_angle, 0.0, 0.0, 1.0)
    glTranslatef(0.0, -pitch_angle * 4.5, 0.0)

    glBegin(GL_LINES)
    glVertex2f(-120, 0); glVertex2f(-35, 0)
    glVertex2f(35, 0);   glVertex2f(120, 0)
    for deg in (-30, -20, -10, 10, 20, 30):
        y_off = deg * 4.5
        glVertex2f(-55, y_off); glVertex2f(-25, y_off)
        glVertex2f(25, y_off);  glVertex2f(55, y_off)
    glEnd()
    glPopMatrix()

    # Barra de Potência (Throttle) à esquerda
    glBegin(GL_LINE_LOOP)
    glVertex2f(cx - 240, cy - 100)
    glVertex2f(cx - 220, cy - 100)
    glVertex2f(cx - 220, cy + 100)
    glVertex2f(cx - 240, cy + 100)
    glEnd()

    fill_h = 200.0 * aircraft.throttle
    glBegin(GL_QUADS)
    glVertex2f(cx - 238, cy - 98)
    glVertex2f(cx - 222, cy - 98)
    glVertex2f(cx - 222, cy - 98 + fill_h)
    glVertex2f(cx - 238, cy - 98 + fill_h)
    glEnd()

    # Indicador luminoso de Trem de Pouso no HUD (Verde abaixo da mira quando baixado)
    if aircraft.gear_deploy > 0.5:
        glColor3f(0.2, 1.0, 0.2)
        glBegin(GL_TRIANGLES)
        glVertex2f(cx - 12, cy - 125)
        glVertex2f(cx + 12, cy - 125)
        glVertex2f(cx, cy - 145)
        glEnd()

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


def draw_crash_overlay(width, height):
    """
    Desenha um alerta visual vermelho semitransparente na tela quando ocorre Game Over/Colisão.
    """
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, width, 0, height)

    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_LINE_BIT)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_LIGHTING)
    glDisable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

    # Filtro vermelho translúcido sobre toda a tela
    glColor4f(0.85, 0.10, 0.08, 0.42)
    glBegin(GL_QUADS)
    glVertex2f(0, 0)
    glVertex2f(width, 0)
    glVertex2f(width, height)
    glVertex2f(0, height)
    glEnd()

    # Grande 'X' vermelho de impacto no centro da tela
    cx, cy = width * 0.5, height * 0.5
    glColor4f(1.0, 0.2, 0.15, 0.95)
    glLineWidth(5.0)
    glBegin(GL_LINES)
    glVertex2f(cx - 80, cy - 80); glVertex2f(cx + 80, cy + 80)
    glVertex2f(cx - 80, cy + 80); glVertex2f(cx + 80, cy - 80)
    glEnd()

    glPopAttrib()
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
