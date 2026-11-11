# Configurações do projeto
VENV = .venv
MAIN = src/main.py
REQ = requirements.txt

# Ajuste automático para Windows vs Linux/macOS
ifeq ($(OS),Windows_NT)
	SYS_PYTHON = python
	PYTHON = $(VENV)/Scripts/python.exe
	PIP = $(VENV)/Scripts/pip.exe
	RM = if exist $(VENV) rmdir /s /q $(VENV)
else
	SYS_PYTHON = python3
	PYTHON = $(VENV)/bin/python
	PIP = $(VENV)/bin/pip
	RM = rm -rf $(VENV)
endif

.PHONY: all install run clean

# Alvo padrão: prepara o ambiente (se não existir) e roda o projeto
all: run

# Cria a venv e instala as bibliotecas do requirements.txt
$(VENV):
	$(SYS_PYTHON) -m venv $(VENV)
	$(PIP) install -r $(REQ)

# Força a verificação/instalação dos pacotes
install: $(VENV)
	$(PIP) install -r $(REQ)

# Executa o script principal usando o Python da venv
run: $(VENV)
	$(PYTHON) $(MAIN)

# Remove o ambiente virtual para uma instalação limpa
clean:
	$(RM)