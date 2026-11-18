"""
================================================================================
TopGraphics | menu_ui.py
Sistemas de Interface Gráfica em OpenGL (Menus 2D / 3D Vetoriais):
  - Menu Principal (início sem argumentos): Título TOP GRAPHICS, seletor de cenas
    (1: Porta-Aviões, 2: Cânion, 3: Hangar de Inspeção), Botão de Configurações e Sair.
  - Tela de Pausa (Pressionar ESC em jogo): Retomar, Configurações e Menu Principal.
  - Tela de Configurações (Sliders interativos para Master, SFX, Ambience, Music,
    além de botões de Aplicar e Voltar).
================================================================================
"""

import math
import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import *

from hud import draw_vector_text, _draw_hud_panel_box


class MenuUI:
    """Gerencia os estados de UI (MENU_PRINCIPAL, JOGANDO, PAUSE, CONFIGURACOES)."""
    
    ESTADO_MENU = "MENU"
    ESTADO_JOGANDO = "JOGANDO"
    ESTADO_PAUSE = "PAUSE"
    ESTADO_CONFIG = "CONFIG"

    def __init__(self):
        self.estado_atual = self.ESTADO_MENU
        self.origem_config = self.ESTADO_MENU  # Para saber para onde voltar ao sair das configurações

        # Seleção de itens ativos nos menus
        self.menu_principal_idx = 0  # 0: Cena 1, 1: Cena 2, 2: Cena 3, 3: Config, 4: Sair
        self.pause_idx = 0           # 0: Retomar, 1: Config, 2: Menu Principal
        self.config_idx = 0          # 0: Master, 1: SFX, 2: Ambience, 3: Music, 4: Aplicar, 5: Voltar

        # Valores temporários de áudio nas configurações (sincronizados ao abrir)
        self.temp_volumes = {
            "master": 0.85,
            "sfx": 0.85,
            "ambience": 0.55,
            "music": 0.35,
        }

        # Armazena a cena anterior caso pause o jogo
        self.cena_anterior_jogo = 1

    def sync_volumes_from_manager(self, audio_manager):
        """Lê os volumes atuais do AudioManager para os sliders de configuração."""
        if audio_manager is not None:
            self.temp_volumes["master"] = audio_manager.volumes.get("master", 0.85)
            self.temp_volumes["sfx"] = audio_manager.volumes.get("sfx", 0.85)
            self.temp_volumes["ambience"] = audio_manager.volumes.get("ambience", 0.55)
            self.temp_volumes["music"] = audio_manager.volumes.get("music", 0.35)

    def apply_volumes_to_manager(self, audio_manager):
        """Aplica os valores dos sliders ao AudioManager."""
        if audio_manager is not None:
            audio_manager.set_master_volume(self.temp_volumes["master"])
            audio_manager.set_category_volume("sfx", self.temp_volumes["sfx"])
            audio_manager.set_category_volume("ambience", self.temp_volumes["ambience"])
            audio_manager.set_category_volume("music", self.temp_volumes["music"])
            print("[Configurações] Volumes aplicados com sucesso!")

    def handle_key(self, key, action, app):
        """Trata a navegação por teclado nos menus, pause e configurações."""
        if action != 1:  # Apenas GLFW_PRESS
            return False

        import glfw

        # ======================================================================
        # 1. MENU PRINCIPAL
        # ======================================================================
        if self.estado_atual == self.ESTADO_MENU:
            if key == glfw.KEY_UP or key == glfw.KEY_W:
                self.menu_principal_idx = (self.menu_principal_idx - 1) % 5
                return True
            elif key == glfw.KEY_DOWN or key == glfw.KEY_S:
                self.menu_principal_idx = (self.menu_principal_idx + 1) % 5
                return True
            elif key == glfw.KEY_ENTER or key == glfw.KEY_SPACE:
                if self.menu_principal_idx == 0:
                    # Iniciar Cena 1
                    app.switch_scene(1)
                    self.estado_atual = self.ESTADO_JOGANDO
                elif self.menu_principal_idx == 1:
                    # Iniciar Cena 2
                    app.switch_scene(2)
                    self.estado_atual = self.ESTADO_JOGANDO
                elif self.menu_principal_idx == 2:
                    # Iniciar Cena 3 (Inspeção)
                    app.switch_scene(3)
                    self.estado_atual = self.ESTADO_JOGANDO
                elif self.menu_principal_idx == 3:
                    # Ir para Configurações
                    self.sync_volumes_from_manager(app.audio)
                    self.origem_config = self.ESTADO_MENU
                    self.config_idx = 0
                    self.estado_atual = self.ESTADO_CONFIG
                elif self.menu_principal_idx == 4:
                    # Sair
                    glfw.set_window_should_close(app.window, True)
                return True

        # ======================================================================
        # 2. TELA DE PAUSE (Chamada ao teclar ESC durante o jogo)
        # ======================================================================
        elif self.estado_atual == self.ESTADO_PAUSE:
            if key == glfw.KEY_UP or key == glfw.KEY_W:
                self.pause_idx = (self.pause_idx - 1) % 3
                return True
            elif key == glfw.KEY_DOWN or key == glfw.KEY_S:
                self.pause_idx = (self.pause_idx + 1) % 3
                return True
            elif key == glfw.KEY_ENTER or key == glfw.KEY_SPACE:
                if self.pause_idx == 0:
                    # Retomar / Resumir
                    self.estado_atual = self.ESTADO_JOGANDO
                elif self.pause_idx == 1:
                    # Abrir Configurações
                    self.sync_volumes_from_manager(app.audio)
                    self.origem_config = self.ESTADO_PAUSE
                    self.config_idx = 0
                    self.estado_atual = self.ESTADO_CONFIG
                elif self.pause_idx == 2:
                    # Voltar para o Menu Principal
                    self.estado_atual = self.ESTADO_MENU
                    app.audio.set_music_context("music_menu_inspection")
                return True
            elif key == glfw.KEY_ESCAPE:
                # Atalho ESC para despausar diretamente
                self.estado_atual = self.ESTADO_JOGANDO
                return True

        # ======================================================================
        # 3. TELA DE CONFIGURAÇÕES (Sliders de Volume + Aplicar / Voltar)
        # ======================================================================
        elif self.estado_atual == self.ESTADO_CONFIG:
            keys_slider_map = {0: "master", 1: "sfx", 2: "ambience", 3: "music"}

            if key == glfw.KEY_UP or key == glfw.KEY_W:
                self.config_idx = (self.config_idx - 1) % 6
                return True
            elif key == glfw.KEY_DOWN or key == glfw.KEY_S:
                self.config_idx = (self.config_idx + 1) % 6
                return True
            elif key == glfw.KEY_LEFT or key == glfw.KEY_A:
                if self.config_idx in keys_slider_map:
                    k = keys_slider_map[self.config_idx]
                    self.temp_volumes[k] = max(0.0, self.temp_volumes[k] - 0.05)
                return True
            elif key == glfw.KEY_RIGHT or key == glfw.KEY_D:
                if self.config_idx in keys_slider_map:
                    k = keys_slider_map[self.config_idx]
                    self.temp_volumes[k] = min(1.0, self.temp_volumes[k] + 0.05)
                return True
            elif key == glfw.KEY_ENTER or key == glfw.KEY_SPACE:
                if self.config_idx == 4:
                    # Botão APLICAR: salva e sai para a origem (Menu ou Pause)
                    self.apply_volumes_to_manager(app.audio)
                    self.estado_atual = self.origem_config
                elif self.config_idx == 5:
                    # Botão VOLTAR: descarta alterações e retorna
                    self.estado_atual = self.origem_config
                return True
            elif key == glfw.KEY_ESCAPE:
                # ESC nas configurações equivale a Voltar sem aplicar
                self.estado_atual = self.origem_config
                return True

        # ======================================================================
        # 4. EM JOGO (JOGANDO)
        # ======================================================================
        elif self.estado_atual == self.ESTADO_JOGANDO:
            if key == glfw.KEY_ESCAPE:
                # Abre o menu de pausa nas cenas 1, 2 ou 3
                self.pause_idx = 0
                self.estado_atual = self.ESTADO_PAUSE
                return True

        return False

    def draw(self, width, height):
        """Renderiza a interface 2D correspondente ao estado atual."""
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        gluOrtho2D(0, width, 0, height)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_LINE_BIT | GL_POLYGON_BIT)
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        glDisable(GL_DEPTH_TEST)
        glDisable(GL_LIGHTING)
        glDisable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LINE_SMOOTH)

        if self.estado_atual == self.ESTADO_MENU:
            self._draw_menu_principal(width, height)
        elif self.estado_atual == self.ESTADO_PAUSE:
            self._draw_pause_menu(width, height)
        elif self.estado_atual == self.ESTADO_CONFIG:
            self._draw_config_menu(width, height)

        glPopAttrib()
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)

    def _draw_menu_principal(self, width, height):
        """Desenha o Menu Principal da aplicação."""
        # Fundo escuro semitranslucido
        glColor4f(0.02, 0.05, 0.09, 0.92)
        glBegin(GL_QUADS)
        glVertex2f(0, 0); glVertex2f(width, 0); glVertex2f(width, height); glVertex2f(0, height)
        glEnd()

        cx, cy = width * 0.5, height * 0.5

        # Título principal
        glColor4f(0.20, 0.95, 0.45, 1.0)
        draw_vector_text("TOP GRAPHICS - F-14 TOMCAT", cx, cy + 180.0, scale=18.0, align="center")
        glColor4f(0.60, 0.85, 0.95, 0.90)
        draw_vector_text("SIMULADOR DE VOO 3D & HANGAR DE INSPECAO", cx, cy + 140.0, scale=9.0, align="center")

        # Opções do menu
        opcoes = [
            "[ 1 ] INICIAR CENA 1: OCEANO + PORTA-AVIOES (CVN-65)",
            "[ 2 ] INICIAR CENA 2: CANION PROCEDURAL (TRENCH RUN)",
            "[ 3 ] INICIAR CENA 3: HANGAR DE INSPECAO E SKINS",
            "[ 4 ] CONFIGURACOES DE AUDIO",
            "[ 5 ] SAIR DA APLICACAO",
        ]

        box_w, box_h = 560.0, 240.0
        bx0, by0 = cx - box_w * 0.5, cy - 80.0
        _draw_hud_panel_box(bx0, by0, bx0 + box_w, by0 + box_h, cut=8.0)

        for i, texto in enumerate(opcoes):
            y_pos = by0 + box_h - 42.0 - i * 38.0
            if i == self.menu_principal_idx:
                glColor4f(0.35, 1.0, 0.55, 1.0)
                draw_vector_text(f"> {texto} <", cx, y_pos, scale=10.0, align="center")
            else:
                glColor4f(0.70, 0.85, 0.78, 0.80)
                draw_vector_text(texto, cx, y_pos, scale=9.0, align="center")

        glColor4f(0.45, 0.75, 0.88, 0.75)
        draw_vector_text("USE SETAS [CIMA/BAIXO] E [ENTER] PARA SELECIONAR", cx, cy - 150.0, scale=8.0, align="center")

    def _draw_pause_menu(self, width, height):
        """Desenha o Menu de Pausa (Pressionar ESC em jogo)."""
        # Overlay escuro translúcido
        glColor4f(0.01, 0.03, 0.06, 0.75)
        glBegin(GL_QUADS)
        glVertex2f(0, 0); glVertex2f(width, 0); glVertex2f(width, height); glVertex2f(0, height)
        glEnd()

        cx, cy = width * 0.5, height * 0.5

        box_w, box_h = 420.0, 220.0
        bx0, by0 = cx - box_w * 0.5, cy - box_h * 0.5
        _draw_hud_panel_box(bx0, by0, bx0 + box_w, by0 + box_h, cut=8.0)

        glColor4f(1.0, 0.65, 0.20, 1.0)
        draw_vector_text("- JOGO PAUSADO -", cx, by0 + box_h - 32.0, scale=12.0, align="center")

        opcoes = [
            "RETOMAR SIMULACAO",
            "CONFIGURACOES DE AUDIO",
            "VOLTAR AO MENU PRINCIPAL",
        ]

        for i, texto in enumerate(opcoes):
            y_pos = by0 + box_h - 84.0 - i * 44.0
            if i == self.pause_idx:
                glColor4f(0.35, 1.0, 0.55, 1.0)
                draw_vector_text(f"> {texto} <", cx, y_pos, scale=9.5, align="center")
            else:
                glColor4f(0.75, 0.88, 0.82, 0.85)
                draw_vector_text(texto, cx, y_pos, scale=9.0, align="center")

    def _draw_config_menu(self, width, height):
        """Desenha a Tela de Configurações de Áudio (Sliders + Botões)."""
        glColor4f(0.02, 0.05, 0.09, 0.92)
        glBegin(GL_QUADS)
        glVertex2f(0, 0); glVertex2f(width, 0); glVertex2f(width, height); glVertex2f(0, height)
        glEnd()

        cx, cy = width * 0.5, height * 0.5

        box_w, box_h = 540.0, 360.0
        bx0, by0 = cx - box_w * 0.5, cy - box_h * 0.5 + 20.0
        _draw_hud_panel_box(bx0, by0, bx0 + box_w, by0 + box_h, cut=8.0)

        glColor4f(0.25, 1.0, 0.65, 1.0)
        draw_text_title = "CONFIGURACOES DE AUDIO"
        draw_vector_text(draw_text_title, cx, by0 + box_h - 35.0, scale=12.0, align="center")

        sliders = [
            ("VOLUME GERAL (MASTER)", "master"),
            ("SOUND EFFECTS (SFX)", "sfx"),
            ("SOM AMBIENTE", "ambience"),
            ("TRILHA MUSICAL (MUSIC)", "music"),
        ]

        for i, (label, key) in enumerate(sliders):
            y_pos = by0 + box_h - 90.0 - i * 52.0
            val = self.temp_volumes[key]
            pct = int(round(val * 100.0))

            if i == self.config_idx:
                glColor4f(0.35, 1.0, 0.55, 1.0)
                draw_vector_text(f"> {label}: {pct:03d}% <", cx, y_pos, scale=9.0, align="center")
            else:
                glColor4f(0.75, 0.88, 0.82, 0.85)
                draw_vector_text(f"{label}: {pct:03d}%", cx, y_pos, scale=8.5, align="center")

            # Desenha barra visual do slider
            bar_w, bar_h = 320.0, 10.0
            bar_x = cx - bar_w * 0.5
            bar_y = y_pos - 18.0

            glColor4f(0.15, 0.45, 0.25, 0.60)
            glBegin(GL_QUADS)
            glVertex2f(bar_x, bar_y); glVertex2f(bar_x + bar_w, bar_y)
            glVertex2f(bar_x + bar_w, bar_y + bar_h); glVertex2f(bar_x, bar_y + bar_h)
            glEnd()

            fill_w = bar_w * val
            glColor4f(0.25, 0.95, 0.45, 0.90)
            glBegin(GL_QUADS)
            glVertex2f(bar_x, bar_y); glVertex2f(bar_x + fill_w, bar_y)
            glVertex2f(bar_x + fill_w, bar_y + bar_h); glVertex2f(bar_x, bar_y + bar_h)
            glEnd()

        # Botões Aplicar e Voltar
        botoes = [("APLICAR", 4), ("VOLTAR", 5)]
        for label, idx in botoes:
            y_pos = by0 + 52.0 if idx == 5 else by0 + 104.0
            if self.config_idx == idx:
                glColor4f(0.35, 1.0, 0.55, 1.0)
                draw_vector_text(f"> {label} <", cx, y_pos, scale=9.0, align="center")
            else:
                glColor4f(0.75, 0.88, 0.82, 0.85)
                draw_vector_text(label, cx, y_pos, scale=8.5, align="center")

        glColor4f(0.45, 0.75, 0.88, 0.75)
        draw_vector_text("USE [ESQ/DIR] PARA AJUSTAR SLIDERS E [ENTER] PARA CONFIRMAR", cx, by0 - 28.0, scale=7.5, align="center")
