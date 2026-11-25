# ==============================================================================
# Top Graphics - F-14 Tomcat 3D Flight Simulator (CEFET-MG)
# Makefile Multiplataforma (Linux & Windows) com suporte a .venv e GitHub Releases
# ==============================================================================

VENV_DIR := .venv
VERSION  ?=

ifeq ($(OS),Windows_NT)
	SYS_PYTHON := python
	VENV_PY    := $(VENV_DIR)/Scripts/python.exe
	VENV_PIP   := $(VENV_DIR)/Scripts/pip.exe
else
	SYS_PYTHON := python3
	VENV_PY    := $(VENV_DIR)/bin/python
	VENV_PIP   := $(VENV_DIR)/bin/pip
endif

# Usa automaticamente o Python da .venv se ela existir; senão usa o Python do sistema
PYTHON := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(SYS_PYTHON))
VERSION_FLAG := $(if $(VERSION),--version $(VERSION),)

.PHONY: help venv install install-build run run1 run2 run3 build build-onefile build-debug clean-build clean

help:
	@echo "========================================================================"
	@echo " Top Graphics - Comandos Disponiveis (Linux / Windows)"
	@echo "========================================================================"
	@echo "  make venv          : Cria o ambiente virtual em .venv"
	@echo "  make install       : Instala dependencias de requirements.txt na .venv"
	@echo "  make install-build : Instala PyInstaller para gerar executaveis"
	@echo "  make run           : Executa o simulador iniciando no Menu Principal"
	@echo "  make run1          : Inicia direto na Cena 1 (Porta-Avioes CVN-65)"
	@echo "  make run2          : Inicia direto na Cena 2 (Canion Trench Run)"
	@echo "  make run3          : Inicia direto na Cena 3 (Hangar de Inspecao/Skins)"
	@echo "  make build         : Compila executavel otimizado + pacote em release/"
	@echo "  make build-onefile : Compila executavel unico standalone + release/"
	@echo "  make build-debug   : Compila com console aberto para diagnostico"
	@echo "  make clean-build   : Remove artefatos temporarios (build/, dist/, *.spec)"
	@echo "  make clean         : Limpa builds, release/ e caches __pycache__"
	@echo "  Dica: passe VERSION=v1.0.0 (ex: make build VERSION=v1.0.0)"
	@echo "========================================================================"

venv:
	$(SYS_PYTHON) -m venv $(VENV_DIR)

install:
	@if [ ! -f "$(VENV_PY)" ] && [ ! -f "$(VENV_DIR)/Scripts/python.exe" ]; then $(SYS_PYTHON) -m venv $(VENV_DIR); fi
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r requirements.txt

install-build:
	$(PYTHON) -m pip install --upgrade pyinstaller

run:
	$(PYTHON) src/main.py

run1:
	$(PYTHON) src/main.py 1

run2:
	$(PYTHON) src/main.py 2

run3:
	$(PYTHON) src/main.py 3

build:
	$(PYTHON) build_release.py $(VERSION_FLAG)

build-onefile:
	$(PYTHON) build_release.py --onefile $(VERSION_FLAG)

build-debug:
	$(PYTHON) build_release.py --console --no-archive

clean-build:
	$(PYTHON) -c "import shutil, glob, os; [shutil.rmtree(d, ignore_errors=True) for d in ('build', 'dist')]; [os.remove(f) for f in glob.glob('*.spec')]"

clean: clean-build
	$(PYTHON) -c "import shutil, pathlib; shutil.rmtree('release', ignore_errors=True); [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"