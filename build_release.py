#!/usr/bin/env python3
"""
================================================================================
TopGraphics | build_release.py
Empacotador multiplataforma (Windows & Linux) via PyInstaller para GitHub Releases:
  - Compila 'src/main.py' com todos os módulos locais de 'src/'.
  - Empacota automaticamente a pasta 'assets/' (texturas, skins, ícone e áudios).
  - Detecta automaticamente 'assets/icon.ico' ou 'assets/icon.png':
      * Windows: embute ícone multi-resolução (16..256 px) no '.exe' via '--icon'
        (convertendo automaticamente PNG -> ICO com Pillow se necessário).
      * Linux  : inclui 'TopGraphics.png' (256x256) e 'install_desktop_shortcut.sh'
        no pacote '--onedir' para criar o atalho no menu de aplicativos com ícone.
  - Coleta bibliotecas nativas de PyOpenGL, GLFW, PortAudio (sounddevice) e
    libsndfile (soundfile), garantindo execução fora do ambiente Python.
  - Gera o pacote pronto para upload em GitHub Releases dentro de 'release/':
      * Windows: release/TopGraphics-Windows-x64.zip
      * Linux  : release/TopGraphics-Linux-x64.tar.gz

Uso (a partir da raiz do repositório):
    python build_release.py                 # Modo pasta (--onedir, startup instantâneo) + arquivo compactado
    python build_release.py --onefile       # Executável único standalone + arquivo compactado
    python build_release.py --console       # Mantém janela de terminal aberta (ideal para debug)
    python build_release.py --version v1.0  # Inclui tag de versão no nome do arquivo em release/
================================================================================
"""

import argparse
import importlib.util
import os
import platform
import subprocess
import sys
import tarfile
import zipfile

APP_NAME = "TopGraphics"
ICON_ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _has_package(pkg_name):
    """Verifica se um pacote Python está instalado no ambiente atual."""
    return importlib.util.find_spec(pkg_name) is not None


def _get_platform_tag():
    """Retorna rótulo limpo de SO e arquitetura (ex: 'Windows-x64', 'Linux-x64')."""
    sys_name = platform.system()
    if sys_name == "Windows":
        os_tag = "Windows"
    elif sys_name == "Linux":
        os_tag = "Linux"
    elif sys_name == "Darwin":
        os_tag = "macOS"
    else:
        os_tag = sys_name or "UnknownOS"

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        arch_tag = "x64"
    elif machine in ("aarch64", "arm64"):
        arch_tag = "arm64"
    else:
        arch_tag = machine or "unknown"

    return f"{os_tag}-{arch_tag}"


def _find_icon_source(project_root, explicit_icon=None):
    """
    Localiza o arquivo de ícone personalizado do projeto.
    Prioriza o caminho informado em '--icon' e, na ausência dele, busca automaticamente
    em 'assets/' e 'assets/texture/' (.ico preferencial no Windows; .png em qualquer SO).
    """
    if explicit_icon:
        resolved = explicit_icon if os.path.isabs(explicit_icon) else os.path.join(project_root, explicit_icon)
        if os.path.isfile(resolved):
            return resolved
        print(f"[Build] Aviso: ícone informado não encontrado: {resolved}")

    if platform.system() == "Windows":
        candidates = (
            os.path.join("assets", "icon.ico"),
            os.path.join("assets", "icon.png"),
            os.path.join("assets", "texture", "icon.ico"),
            os.path.join("assets", "texture", "icon.png"),
        )
    else:
        candidates = (
            os.path.join("assets", "icon.png"),
            os.path.join("assets", "texture", "icon.png"),
            os.path.join("assets", "icon.ico"),
            os.path.join("assets", "texture", "icon.ico"),
        )

    for rel_path in candidates:
        full_p = os.path.join(project_root, rel_path)
        if os.path.isfile(full_p):
            return full_p
    return None


def _prepare_windows_ico(project_root, icon_source):
    """
    Garante um arquivo '.ico' multi-resolução (16..256 px) para o PyInstaller no Windows.
    Se a origem já for '.ico', usa diretamente; se for '.png'/outra imagem, converte com Pillow.
    """
    if not icon_source or not os.path.isfile(icon_source):
        return None

    if icon_source.lower().endswith(".ico"):
        return icon_source

    try:
        from PIL import Image

        build_dir = os.path.join(project_root, "build")
        os.makedirs(build_dir, exist_ok=True)
        out_ico = os.path.join(build_dir, f"{APP_NAME}.ico")

        with Image.open(icon_source) as im:
            rgba = im.convert("RGBA")
            rgba.save(out_ico, format="ICO", sizes=ICON_ICO_SIZES)

        print(f"[Build] Ícone Windows gerado automaticamente: {out_ico} (a partir de {os.path.basename(icon_source)})")
        return out_ico
    except Exception as exc:
        print(f"[Build] Aviso: falha ao converter '{icon_source}' para .ico ({exc}); passando original ao PyInstaller.")
        return icon_source


def _add_linux_desktop_assets(dist_app_dir, icon_source):
    """
    No Linux (--onedir), binários ELF não embutem ícone próprio.
    Gera 'TopGraphics.png' (256x256) e 'install_desktop_shortcut.sh' dentro da pasta
    compilada para que o usuário possa criar o atalho no menu de aplicativos com 1 comando.
    """
    if not os.path.isdir(dist_app_dir):
        return

    icon_dest = os.path.join(dist_app_dir, f"{APP_NAME}.png")
    if icon_source and os.path.isfile(icon_source):
        try:
            from PIL import Image
            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            with Image.open(icon_source) as im:
                im.convert("RGBA").resize((256, 256), resample_filter).save(icon_dest, format="PNG")
            print(f"[Build] Ícone Linux (256x256) adicionado ao pacote: {icon_dest}")
        except Exception as exc:
            print(f"[Build] Aviso ao gerar ícone Linux PNG: {exc}")

    shortcut_script = os.path.join(dist_app_dir, "install_desktop_shortcut.sh")
    script_content = f"""#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
DESKTOP_DIR="${{XDG_DATA_HOME:-$HOME/.local/share}}/applications"
DESKTOP_FILE="$DESKTOP_DIR/{APP_NAME}.desktop"

mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Top Graphics - F-14 Tomcat
Comment=Simulador de Voo 3D F-14 Tomcat (CEFET-MG)
Exec="$APP_DIR/{APP_NAME}"
Path=$APP_DIR
Icon=$APP_DIR/{APP_NAME}.png
Terminal=false
Categories=Game;Simulation;
StartupWMClass={APP_NAME}
EOF

chmod +x "$DESKTOP_FILE"
echo "[TopGraphics] Atalho criado com sucesso em: $DESKTOP_FILE"
"""
    with open(shortcut_script, "w", encoding="utf-8", newline="\n") as f:
        f.write(script_content)
    os.chmod(shortcut_script, 0o755)
    print(f"[Build] Instalador de atalho Linux gerado: {shortcut_script}")


def _build_pyinstaller_command(project_root, onefile=False, show_console=False, icon_path=None):
    """Monta a linha de comando completa do PyInstaller para Windows ou Linux."""
    entry_script = os.path.join(project_root, "src", "main.py")
    src_dir = os.path.join(project_root, "src")
    assets_dir = os.path.join(project_root, "assets")

    if not os.path.isfile(entry_script):
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {entry_script}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", APP_NAME,
        "--paths", src_dir,
        "--onefile" if onefile else "--onedir",
    ]

    # No Windows, --windowed evita abrir o console preto atrás da janela GLFW
    if show_console:
        cmd.append("--console")
    else:
        cmd.append("--windowed")

    # Ícone no executável (.exe no Windows; no Linux, ELF ignora --icon e usa .desktop + GLFW)
    resolved_icon = _find_icon_source(project_root, icon_path)
    if platform.system() == "Windows" and resolved_icon:
        win_ico = _prepare_windows_ico(project_root, resolved_icon)
        if win_ico and os.path.isfile(win_ico):
            cmd.extend(["--icon", win_ico])
    elif resolved_icon and icon_path:
        cmd.extend(["--icon", resolved_icon])

    # Empacota todos os assets (texturas, skins, ícone e áudios WAV/MP3) preservando 'assets/'
    if os.path.isdir(assets_dir):
        add_data_arg = f"{assets_dir}{os.pathsep}assets"
        cmd.extend(["--add-data", add_data_arg])
    else:
        print(f"[Build] Aviso: pasta '{assets_dir}' não encontrada; o executável usará fallbacks procedurais.")

    # Coleta bibliotecas nativas e submódulos dinâmicos essenciais
    for pkg in ("glfw", "sounddevice", "soundfile", "_sounddevice_data", "_soundfile_data"):
        if _has_package(pkg):
            cmd.extend(["--collect-all", pkg])

    # PyOpenGL carrega plataformas e manipuladores de arrays dinamicamente em runtime
    cmd.extend(["--collect-submodules", "OpenGL"])
    if _has_package("OpenGL_accelerate"):
        cmd.extend(["--collect-all", "OpenGL_accelerate"])

    hidden_imports = [
        "OpenGL.GL",
        "OpenGL.GLU",
        "OpenGL.arrays.numpymodule",
        "OpenGL.arrays.ctypesarrays",
        "OpenGL.arrays.ctypesparameters",
        "OpenGL.arrays.lists",
        "OpenGL.arrays.numbers",
        "OpenGL.arrays.strings",
        "OpenGL.arrays.vbo",
        "PIL._imaging",
        "numpy",
    ]
    if platform.system() == "Windows":
        hidden_imports.append("OpenGL.platform.win32")
    elif platform.system() == "Linux":
        hidden_imports.extend(["OpenGL.platform.glx", "OpenGL.platform.egl"])

    for mod in hidden_imports:
        cmd.extend(["--hidden-import", mod])

    cmd.append(entry_script)
    return cmd


def _create_release_archive(dist_dir, release_dir, onefile, version_tag=None):
    """
    Empacota a saída de 'dist/' em um arquivo pronto para upload no GitHub Releases:
      - Windows: .zip
      - Linux  : .tar.gz (preservando permissões executáveis +x)
    """
    os.makedirs(release_dir, exist_ok=True)
    plat_tag = _get_platform_tag()
    mode_suffix = "-portable" if onefile else ""
    ver_suffix = f"-{version_tag}" if version_tag else ""
    base_name = f"{APP_NAME}{ver_suffix}-{plat_tag}{mode_suffix}"

    is_windows = (platform.system() == "Windows")
    exe_name = f"{APP_NAME}.exe" if is_windows else APP_NAME

    if onefile:
        target_path = os.path.join(dist_dir, exe_name)
    else:
        target_path = os.path.join(dist_dir, APP_NAME)

    if not os.path.exists(target_path):
        raise FileNotFoundError(f"Artefato compilado não encontrado em: {target_path}")

    if is_windows:
        archive_path = os.path.join(release_dir, f"{base_name}.zip")
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            if os.path.isfile(target_path):
                zf.write(target_path, arcname=os.path.basename(target_path))
            else:
                parent_dir = os.path.dirname(target_path)
                for root, _, files in os.walk(target_path):
                    for fname in files:
                        full_p = os.path.join(root, fname)
                        rel_p = os.path.relpath(full_p, parent_dir)
                        zf.write(full_p, arcname=rel_p)
        return archive_path

    # Linux / macOS: tar.gz preserva bit de execução (+x) do binário ELF e scripts
    archive_path = os.path.join(release_dir, f"{base_name}.tar.gz")
    with tarfile.open(archive_path, "w:gz") as tf:
        tf.add(target_path, arcname=os.path.basename(target_path))
    return archive_path


def main():
    parser = argparse.ArgumentParser(
        description="Compila o Top Graphics (F-14 Tomcat) em executável Windows/Linux via PyInstaller."
    )
    parser.add_argument(
        "--onefile", action="store_true",
        help="Gera um único executável standalone (startup ligeiramente mais lento na extração)."
    )
    parser.add_argument(
        "--console", action="store_true",
        help="Mantém o terminal/console visível junto com a janela OpenGL (útil para debug)."
    )
    parser.add_argument(
        "--version", default="",
        help="Tag de versão opcional para o arquivo em release/ (ex: v1.0.0)."
    )
    parser.add_argument(
        "--icon", default="",
        help="Caminho opcional para um ícone (.ico ou .png; padrão: detecção automática em assets/)."
    )
    parser.add_argument(
        "--no-archive", action="store_true",
        help="Apenas compila em dist/ sem gerar o arquivo compactado em release/."
    )
    args = parser.parse_args()

    if not _has_package("PyInstaller"):
        print("[Build] ERRO: PyInstaller não encontrado no ambiente Python atual.")
        print("[Build] Instale com: pip install pyinstaller  (ou execute: make install-build)")
        sys.exit(1)

    project_root = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(project_root, "dist")
    release_dir = os.path.join(project_root, "release")
    icon_source = _find_icon_source(project_root, args.icon or None)

    print("=" * 74)
    print(f" TOP GRAPHICS — BUILD DE RELEASE ({_get_platform_tag()})")
    print(f" Modo    : {'ONEFILE (executável único)' if args.onefile else 'ONEDIR (pasta otimizada + startup rápido)'}")
    print(f" Console : {'ATIVADO (debug)' if args.console else 'OCULTO (windowed)'}")
    print(f" Ícone   : {os.path.relpath(icon_source, project_root) if icon_source else 'Padrão (nenhum assets/icon.png|.ico)'}")
    print("=" * 74)

    cmd = _build_pyinstaller_command(
        project_root=project_root,
        onefile=args.onefile,
        show_console=args.console,
        icon_path=args.icon or None,
    )

    print("[Build] Executando PyInstaller...")
    result = subprocess.run(cmd, cwd=project_root)
    if result.returncode != 0:
        print(f"[Build] Falha na compilação (código {result.returncode}).")
        sys.exit(result.returncode)

    # No Linux (--onedir), adiciona ícone 256x256 e script instalador de atalho .desktop
    if platform.system() == "Linux" and not args.onefile:
        _add_linux_desktop_assets(os.path.join(dist_dir, APP_NAME), icon_source)

    if not args.no_archive:
        archive_path = _create_release_archive(
            dist_dir=dist_dir,
            release_dir=release_dir,
            onefile=args.onefile,
            version_tag=args.version.strip() or None,
        )
        size_mb = os.path.getsize(archive_path) / (1024.0 * 1024.0)
        print("-" * 74)
        print(f"[Build] Pacote pronto para GitHub Releases: {archive_path} ({size_mb:.1f} MB)")
        print("-" * 74)
    else:
        print(f"[Build] Compilação concluída em: {dist_dir}")


if __name__ == "__main__":
    main()