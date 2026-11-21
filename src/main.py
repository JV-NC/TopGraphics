"""
================================================================================
CEFET-MG | Departamento de Computação - Computação Gráfica
Trabalho Final: TOP GRAPHICS - Simulador de Voo 3D (F-14 Tomcat)
================================================================================
Execução (a partir da raiz do repositório):
    pip install -r requirements.txt
    python src/main.py [1|2|3]
================================================================================
"""


import sys
import time

try:
    import glfw
    from OpenGL.GL import *
    from OpenGL.GLU import *
except ImportError as e:
    print("Erro ao importar bibliotecas gráficas:", e)
    print("Instale as dependências com: pip install -r requirements.txt")
    sys.exit(1)

from flight_kinematics import Aircraft
from camera import CameraController
from gamepad_controller import (
    GamepadController,
    BTN_A, BTN_B, BTN_X, BTN_Y,
    BTN_LS, BTN_RS, BTN_START, BTN_BACK,
    BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT,
)
from f14_model import (
    create_wing_insignia_texture,
    build_f14_static_fuselage_list,
    build_f14_skinned_fuselage_list,
    draw_f14_complete,
)
from skin_manager import SkinManager
from audio_manager import AudioManager
from menu_ui import MenuUI
from scene_carrier import (
    create_ocean_texture,
    create_deck_texture,
    build_scene1_carrier_list,
    update_ocean_physics,
    draw_physical_ocean,
)
from scene_canyon import (
    create_canyon_texture,
    build_scene2_canyon_list,
    update_canyon_dust,
    draw_canyon_dust,
    reset_canyon_dust,
)
from scene_inspection import (
    apply_inspection_lighting,
    build_scene3_inspection_list,
    draw_inspection_overlay,
)
from scene_utils import (
    TIME_OF_DAY_PRESETS,
    DAY_CYCLE_HOURS_PER_SEC,
    create_cloud_vapor_texture,
    build_procedural_clouds_list,
    get_sun_state,
    apply_sunrise_lighting,
    draw_rising_sun_and_sky,
    draw_ocean_sun_glitter,
    draw_procedural_clouds,
    draw_periodic_scene,
)
from renderer_utils import setup_lighting
from hud import draw_flight_hud, draw_crash_overlay


# ==============================================================================
# APLICAÇÃO PRINCIPAL E LOOP DE RENDERIZAÇÃO (GLFW + OPENGL + MENU + ÁUDIO)
# ==============================================================================

class TopGraphicsApp:
    SCENE_NAMES = {
        1: "Cena 1: Oceano Físico de Partículas + Porta-Aviões (CVN-65)",
        2: "Cena 2: Cânion Procedural (Trench Run)",
        3: "Cena 3: Hangar de Inspeção Técnica e Customização de Skins",
    }

    def __init__(self, initial_scene=None):
        # Se initial_scene for fornecido por argumento de linha de comando, pula direto para o jogo.
        # Caso contrário, inicia no Menu Principal.
        self.has_cli_scene = initial_scene is not None
        self.scene_mode = initial_scene if initial_scene is not None else 1

        # Estados de recursos gráficos, interface e ciclo Dia/Noite
        self.lighting_enabled = True
        self.textures_enabled = True
        self.wireframe_mode = False
        self.hud_enabled = True
        self.window = None

        # Ciclo Dia/Noite (inicia no Amanhecer clássico 06:25; [C] alterna presets, [V] pausa/retoma)
        self.time_preset_idx = 0
        self.time_of_day_hours = TIME_OF_DAY_PRESETS[0]["hour"]
        self.day_cycle_paused = False

        # Instância única do F-14 Tomcat
        self.player = Aircraft()
        self.player.reset(self.scene_mode)

        # Câmeras virtuais: Chase, Cockpit e Orbital
        self.camera = CameraController(self.player)
        if self.scene_mode == 3:
            self.camera.set_mode(3, scene_mode=3)

        self.skin_manager = None

        # Sistema de Áudio independente (inicia no contexto 'menu' quando aberto pelo Menu Principal)
        initial_audio_scene = self.scene_mode if self.has_cli_scene else "menu"
        self.audio = AudioManager(
            initial_scene=initial_audio_scene,
            initial_camera_mode=self.camera.mode
        )

        # Sistema de Controle / Gamepad (Detecção nativa do SO padrão XBOX via GLFW)
        self.gamepad = GamepadController()

        # Sistema de Interface (Menu Principal, Pause, Configurações)
        self.ui = MenuUI()
        if self.has_cli_scene:
            self.ui.estado_atual = MenuUI.ESTADO_JOGANDO
            self.audio.sync_aircraft_state(self.player.on_ground, self.player.throttle, self.player.crashed)
        else:
            self.ui.estado_atual = MenuUI.ESTADO_MENU

    def switch_scene(self, target_scene, force_reset=False):
        """
        Alterna diretamente para o cenário desejado (1, 2 ou 3).
        - Quando chamado em voo via F1/F2/F3 (force_reset=False): não reinicia se já estiver no mapa atual.
        - Quando chamado pelo Menu Principal (force_reset=True): sempre reinicia a cena e sincroniza o áudio.
        """
        if (not force_reset) and target_scene == self.scene_mode:
            # Garante sincronismo de áudio caso estivesse fora de fase, sem reiniciar a aeronave
            if self.audio.scene_mode != self.scene_mode:
                self.audio.set_camera_mode(self.camera.mode)
                self.audio.set_scene(self.scene_mode, force_init=True)
            print(f"[Cenário] Você já está na {self.SCENE_NAMES[self.scene_mode]} (sem reiniciar).")
            return

        self.scene_mode = target_scene
        self.player.reset(self.scene_mode)
        reset_canyon_dust()

        if self.scene_mode == 3:
            self.camera.set_mode(3, scene_mode=3)
        else:
            self.camera.set_mode(1, scene_mode=self.scene_mode)
            self.camera.snap_chase_to(self.player)

        self.audio.set_camera_mode(self.camera.mode)
        self.audio.sync_aircraft_state(self.player.on_ground, self.player.throttle, self.player.crashed)
        self.audio.set_scene(self.scene_mode, force_init=True)
        print(f"[Cenário] Alternado para {self.SCENE_NAMES[self.scene_mode]}")

    def cycle_time_of_day(self):
        """Avança para o próximo horário do ciclo Dia/Noite (Amanhecer -> Meio-Dia -> Pôr do Sol -> Noite)."""
        self.time_preset_idx = (self.time_preset_idx + 1) % len(TIME_OF_DAY_PRESETS)
        preset = TIME_OF_DAY_PRESETS[self.time_preset_idx]
        self.time_of_day_hours = float(preset["hour"])
        hh = int(self.time_of_day_hours)
        mm = int((self.time_of_day_hours - hh) * 60.0)
        print(f"[Ciclo Dia/Noite] Horário alterado para {preset['label']} ({hh:02d}:{mm:02d})")

    def cycle_camera_mode(self):
        """Alterna ciclicamente entre as câmeras (1 -> 2 -> 3 -> 1) sincronizando o áudio."""
        if self.scene_mode == 3:
            self.camera.set_mode(3, scene_mode=3)
            self.audio.set_camera_mode(self.camera.mode)
            return
        next_cam = (self.camera.mode % 3) + 1
        self.camera.set_mode(next_cam, scene_mode=self.scene_mode)
        self.audio.set_camera_mode(self.camera.mode)

    def cycle_scene_mode(self):
        """Alterna ciclicamente entre os cenários (1 -> 2 -> 3 -> 1)."""
        next_scene = (self.scene_mode % 3) + 1
        self.switch_scene(next_scene)

    def toggle_wing_sweep_mode(self):
        """Alterna enflecamento das asas entre AUTOMÁTICO e MANUAL (20° <-> 68°)."""
        self.player.auto_wing_sweep = not self.player.auto_wing_sweep
        if not self.player.auto_wing_sweep:
            self.player.wing_sweep_angle = 68.0 if self.player.wing_sweep_angle < 45.0 else 20.0
        estado = "AUTOMÁTICO" if self.player.auto_wing_sweep else f"MANUAL ({self.player.wing_sweep_angle:.0f}°)"
        print(f"Enflecamento das Asas do F-14: {estado}")

    def handle_gamepad_gameplay_buttons(self):
        """
        Processa os botões discretos (borda de subida) do Gamepad padrão XBOX
        enquanto o simulador está no estado ESTADO_JOGANDO:
          - A       : Toggle Trem de Pouso
          - B       : Toggle Air Brake
          - X       : Toggle Afterburner
          - Y       : Alternar Cenas (1 -> 2 -> 3)
          - LS      : Toggle Flaps
          - RS      : Alternar Câmera (1 -> 2 -> 3)
          - START   : Abrir Menu de Pause
          - BACK    : Reiniciar Aeronave
          - D-Pad   : Dia/Noite, Asas, HUD, Ciclo Solar (Voo) | Skins, Paleta, HUD, Asas (Cena 3)
        """
        gp = self.gamepad
        if not gp.connected:
            return

        if gp.just_pressed(BTN_START):
            self.ui.pause_idx = 0
            self.ui.estado_atual = MenuUI.ESTADO_PAUSE
            self.audio.play_menu_sfx("pause")
            return

        if gp.just_pressed(BTN_A):
            prev_gear = self.player.gear_down
            self.player.toggle_gear()
            if self.player.gear_down != prev_gear:
                self.audio.play_gear_sfx(deploying=self.player.gear_down)

        if gp.just_pressed(BTN_B):
            self.player.toggle_airbrake()

        if gp.just_pressed(BTN_X):
            self.player.toggle_afterburner()

        if gp.just_pressed(BTN_Y):
            self.cycle_scene_mode()

        if gp.just_pressed(BTN_LS):
            self.player.toggle_flaps()

        if gp.just_pressed(BTN_RS):
            self.cycle_camera_mode()

        if gp.just_pressed(BTN_BACK):
            self.player.reset(self.scene_mode)
            reset_canyon_dust()
            if self.scene_mode == 3:
                self.camera.set_mode(3, scene_mode=3)
            else:
                self.camera.snap_chase_to(self.player)
            self.audio.set_camera_mode(self.camera.mode)
            self.audio.sync_aircraft_state(self.player.on_ground, self.player.throttle, self.player.crashed)
            print("[Voo] Posição e atitude do F-14 reiniciadas (Gamepad BACK).")

        # D-Pad contextual: Voo (Cenas 1/2) vs Inspeção/Skins (Cena 3)
        if gp.just_pressed(BTN_DPAD_UP):
            if self.scene_mode == 3:
                if self.skin_manager is not None:
                    self.skin_manager.next_pattern(scene_mode=self.scene_mode)
            else:
                self.cycle_time_of_day()

        if gp.just_pressed(BTN_DPAD_DOWN):
            if self.scene_mode == 3:
                if self.skin_manager is not None:
                    self.skin_manager.next_palette(scene_mode=self.scene_mode)
            else:
                self.toggle_wing_sweep_mode()

        if gp.just_pressed(BTN_DPAD_LEFT):
            self.hud_enabled = not self.hud_enabled
            print(f"[HUD] Interface Tática: {'ATIVADA' if self.hud_enabled else 'OCULTA'}")

        if gp.just_pressed(BTN_DPAD_RIGHT):
            if self.scene_mode == 3:
                self.toggle_wing_sweep_mode()
            else:
                self.day_cycle_paused = not self.day_cycle_paused
                estado = "FIXO (PAUSADO)" if self.day_cycle_paused else "AUTOMÁTICO (CONTÍNUO)"
                print(f"[Ciclo Dia/Noite] Progressão Solar: {estado}")

    def key_callback(self, window, key, scancode, action, mods):
        """Trata atalhos de teclado, redirecionando para a UI quando em menus ou pause."""
        if action != glfw.PRESS:
            return

        # Deixa a UI tratar os inputs se estiver no Menu Principal, Pause ou Configurações
        if self.ui.estado_atual in (MenuUI.ESTADO_MENU, MenuUI.ESTADO_PAUSE, MenuUI.ESTADO_CONFIG):
            handled = self.ui.handle_key(key, action, self)
            if handled:
                return

        # Atalhos padrão de jogo (quando ESTADO_JOGANDO)
        if self.ui.estado_atual == MenuUI.ESTADO_JOGANDO:
            if key == glfw.KEY_ESCAPE:
                # Pausa o jogo, abre o menu de pause e dispara som de abertura
                self.ui.pause_idx = 0
                self.ui.estado_atual = MenuUI.ESTADO_PAUSE
                self.audio.play_menu_sfx("pause")
                return
            elif key == glfw.KEY_1:
                self.camera.set_mode(1, scene_mode=self.scene_mode)
                self.audio.set_camera_mode(self.camera.mode)
            elif key == glfw.KEY_2:
                self.camera.set_mode(2, scene_mode=self.scene_mode)
                self.audio.set_camera_mode(self.camera.mode)
            elif key == glfw.KEY_3:
                self.camera.set_mode(3, scene_mode=self.scene_mode)
                self.audio.set_camera_mode(self.camera.mode)
            elif key == glfw.KEY_F1:
                self.switch_scene(1)
            elif key == glfw.KEY_F2:
                self.switch_scene(2)
            elif key == glfw.KEY_F3:
                self.switch_scene(3)
            elif key == glfw.KEY_Q:
                prev_gear = self.player.gear_down
                self.player.toggle_gear()
                if self.player.gear_down != prev_gear:
                    self.audio.play_gear_sfx(deploying=self.player.gear_down)
            elif key == glfw.KEY_E:
                self.player.toggle_afterburner()
            elif key == glfw.KEY_F:
                self.player.toggle_flaps()
            elif key == glfw.KEY_B:
                self.player.toggle_airbrake()
            elif key == glfw.KEY_C:
                if self.scene_mode in (1, 2):
                    self.cycle_time_of_day()
                else:
                    print("[Ciclo Dia/Noite] Disponível nas Cenas 1 (Oceano) e 2 (Cânion).")
            elif key == glfw.KEY_V:
                if self.scene_mode in (1, 2):
                    self.day_cycle_paused = not self.day_cycle_paused
                    estado = "FIXO (PAUSADO)" if self.day_cycle_paused else "AUTOMÁTICO (CONTÍNUO)"
                    print(f"[Ciclo Dia/Noite] Progressão Solar: {estado}")
            elif key == glfw.KEY_M:
                self.audio.toggle_mute()
            elif key == glfw.KEY_N:
                self.audio.toggle_music_mute()
            elif key == glfw.KEY_K:
                if self.scene_mode == 3:
                    if self.skin_manager is not None:
                        self.skin_manager.next_pattern(scene_mode=self.scene_mode)
                else:
                    print("[Skins] Customização de skin bloqueada em voo! Pressione [F3] para ir à Cena de Inspeção.")
            elif key == glfw.KEY_P:
                if self.scene_mode == 3:
                    if self.skin_manager is not None:
                        self.skin_manager.next_palette(scene_mode=self.scene_mode)
                else:
                    print("[Skins] Customização de paleta bloqueada em voo! Pressione [F3] para ir à Cena de Inspeção.")
            elif key == glfw.KEY_H:
                self.hud_enabled = not self.hud_enabled
                print(f"[HUD] Interface Tática: {'ATIVADA' if self.hud_enabled else 'OCULTA'}")
            elif key == glfw.KEY_R:
                self.player.reset(self.scene_mode)
                reset_canyon_dust()
                if self.scene_mode == 3:
                    self.camera.set_mode(3, scene_mode=3)
                else:
                    self.camera.snap_chase_to(self.player)
                self.audio.set_camera_mode(self.camera.mode)
                self.audio.sync_aircraft_state(self.player.on_ground, self.player.throttle, self.player.crashed)
                print("[Voo] Posição e atitude do F-14 reiniciadas.")
            elif key == glfw.KEY_L:
                self.lighting_enabled = not self.lighting_enabled
                print(f"Iluminação Artificial: {'ATIVADA' if self.lighting_enabled else 'DESATIVADA'}")
            elif key == glfw.KEY_T:
                self.textures_enabled = not self.textures_enabled
                print(f"Mapeamento de Texturas UV: {'ATIVADO' if self.textures_enabled else 'DESATIVADO'}")
            elif key == glfw.KEY_Z:
                self.wireframe_mode = not self.wireframe_mode
                glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe_mode else GL_FILL)
                print(f"[Malha 3D] Modo Wireframe: {'ATIVADO' if self.wireframe_mode else 'DESATIVADO'}")
            elif key == glfw.KEY_G:
                self.toggle_wing_sweep_mode()

    def mouse_button_callback(self, window, button, action, mods):
        if button == glfw.MOUSE_BUTTON_LEFT:
            x, y = glfw.get_cursor_pos(window)
            self.camera.on_mouse_button(action == glfw.PRESS, x, y)

    def cursor_pos_callback(self, window, xpos, ypos):
        self.camera.on_cursor_pos(xpos, ypos)

    def scroll_callback(self, window, xoffset, yoffset):
        self.camera.on_scroll(yoffset)

    def run(self):
        if not glfw.init():
            print("Falha ao inicializar o GLFW.")
            return

        window = glfw.create_window(
            1280, 720,
            "Top Graphics - F-14 Tomcat 3D Flight Simulator (CEFET-MG)",
            None, None
        )
        if not window:
            glfw.terminate()
            return

        self.window = window
        glfw.make_context_current(window)
        glfw.swap_interval(1)

        glfw.set_key_callback(window, self.key_callback)
        glfw.set_mouse_button_callback(window, self.mouse_button_callback)
        glfw.set_cursor_pos_callback(window, self.cursor_pos_callback)
        glfw.set_scroll_callback(window, self.scroll_callback)

        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LEQUAL)
        setup_lighting()

        ocean_tex = create_ocean_texture()
        deck_tex = create_deck_texture()
        canyon_tex = create_canyon_texture()
        wing_tex = create_wing_insignia_texture()
        cloud_vapor_tex = create_cloud_vapor_texture()

        self.skin_manager = SkinManager(default_wing_tex_id=wing_tex)

        player_fuselage_list = build_f14_static_fuselage_list(wing_tex)
        player_skinned_fuselage_list = build_f14_skinned_fuselage_list()

        scene1_list = build_scene1_carrier_list(ocean_tex, deck_tex)
        scene2_list = build_scene2_canyon_list(canyon_tex)
        scene3_list = build_scene3_inspection_list()
        clouds1_list = build_procedural_clouds_list(scene_mode=1)
        clouds2_list = build_procedural_clouds_list(scene_mode=2)

        # Inicia o stream de áudio contínuo
        self.audio.start()

        last_time = time.time()
        sim_time = 0.0

        print("\n" + "=" * 78)
        print(" TOP GRAPHICS - SIMULADOR DE VOO F-14 TOMCAT (CEFET-MG)")
        print("=" * 78)
        print(" [F1 / F2 / F3]        : Selecionar Cenário Diretamente em Jogo")
        print(" [ESC]                 : Abrir Menu de Pause (Pausa simulação e exibe opções)")
        print(" [W / S]               : Potência (Throttle) / Segure 'S' no convés para Frear")
        print(" [E]                   : Ligar / Desligar Pós-Combustor (Afterburner EFSC)")
        print(" [Q]                   : Recolher / Baixar Trem de Pouso Retrátil (SFX + Arrasto)")
        print(" [F]                   : Estender / Recolher Flaps (Ganho de Estol + FLAPS.wav, Trava >= 26°)")
        print(" [B]                   : Abrir / Fechar Split Air Brakes no Beaver Tail (Freio Aerodinâmico)")
        print(" [Setas Baixo / Cima]  : Puxar Manche (Subir/Decolar) / Empurrar (Mergulhar)")
        print(" [Setas Esq / Dir]     : Rolagem (Roll - Inclinar Asas e acionar Spoilers)")
        print(" [A / D]               : Guinada (Leme em voo / Direção da roda no convés)")
        print(" [G]                   : Alternar Enflecamento das Asas (Auto <-> Manual)")
        print(" [K / P] (Apenas F3)   : Trocar Padrão de Skin (K) e Paleta de Camuflagem (P)")
        print(" [M / N]               : Mute Geral do Áudio (M) / Mute da Música (N)")
        print(" [H]                   : Mostrar / Ocultar HUD Tático (e HUD de Skins na Cena 3)")
        print(" [1 / 2 / 3]           : Câmeras (1/3: Áudio Externo | 2: Áudio Interno Cockpit)")
        print(" [C / V]               : Alternar Horário Dia/Noite (C) / Fixar ou Retomar Ciclo (V)")
        print(" [L / T / Z]           : Ligar/Desligar Luzes (L), Texturas (T), Wireframe (Z)")
        print(" [R]                   : Reiniciar Posição/Atitude do Caça imediatamente")
        print(" [ESC]                 : Sair")
        print("-" * 78)
        print(" GAMEPAD (PADRÃO XBOX — DETECÇÃO AUTOMÁTICA DO SO VIA GLFW):")
        print("   LS (Y / X)          : Arfagem (Pitch) / Rolagem (Roll)")
        print("   LT / RT             : Reduzir Throttle (+ Freio no Convés) / Aumentar Throttle")
        print("   LB / RB             : Guinada Esquerda / Guinada Direita")
        print("   A / B / X / Y       : Trem Pouso (A) | Air Brake (B) | Afterburner (X) | Cenas (Y)")
        print("   LS (Clique)         : Toggle Flaps | RS (Clique): Alternar Câmera (1/2/3)")
        print("   RS (X / Y)          : Mover Câmera Orbital (quando na Câmera 3)")
        print("   START / BACK        : Pause (START) | Reiniciar Caça (BACK)")
        print("   D-Pad               : Menus/Sliders | Voo: Dia/Noite, Asas, HUD, Ciclo | F3: Skins/Paleta")
        print("=" * 78 + "\n")

        try:
            while not glfw.window_should_close(window):
                now = time.time()
                dt = min(0.05, now - last_time)
                last_time = now

                glfw.poll_events()
                self.gamepad.poll()

                # Se estiver em Menu Principal, Pause ou Configurações, repassa navegação do Gamepad à UI
                # e impede que o mesmo clique (ex: A=Confirmar ou B=Voltar) dispare ação de voo no mesmo frame!
                ui_was_open = self.ui.estado_atual in (MenuUI.ESTADO_MENU, MenuUI.ESTADO_PAUSE, MenuUI.ESTADO_CONFIG)
                if ui_was_open:
                    for gp_key in self.gamepad.get_menu_key_events(dt):
                        self.ui.handle_key(gp_key, glfw.PRESS, self)

                width, height = glfw.get_framebuffer_size(window)
                height = max(1, height)
                glViewport(0, 0, width, height)

                # Se estiver no Menu Principal, renderiza apenas o Menu e reproduz trilha de menu
                if self.ui.estado_atual == MenuUI.ESTADO_MENU:
                    glClearColor(0.02, 0.05, 0.09, 1.0)
                    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
                    self.audio.set_scene("menu")  # Garante música de menu/inspeção e motores desligados
                    self.audio.update(dt=0.0, throttle=0.0, afterburner=False, crashed=False, aircraft_speed=0.0, on_ground=True)
                    self.ui.draw(width, height)
                    glfw.swap_buffers(window)
                    continue

                # Se estiver na Tela de Pause ou Configurações, renderiza a cena congelada ao fundo + UI por cima
                is_paused = (self.ui.estado_atual in (MenuUI.ESTADO_PAUSE, MenuUI.ESTADO_CONFIG))
                simulation_dt = 0.0 if is_paused else dt
                sim_time += simulation_dt

                # Avança suavemente o relógio do ciclo Dia/Noite nas Cenas 1 e 2
                if (not is_paused) and (not self.day_cycle_paused) and self.scene_mode in (1, 2):
                    self.time_of_day_hours = (self.time_of_day_hours + simulation_dt * DAY_CYCLE_HOURS_PER_SEC) % 24.0

                pitch_in = 0.0
                roll_in = 0.0
                yaw_in = 0.0
                throttle_in = 0.0
                brake_active = False

                if (not is_paused) and (not ui_was_open):
                    # Botões discretos do Gamepad em jogo (A/B/X/Y/LS/RS/START/BACK/D-Pad)
                    self.handle_gamepad_gameplay_buttons()
                    # Reavalia pause caso START tenha sido pressionado neste frame
                    is_paused = (self.ui.estado_atual in (MenuUI.ESTADO_PAUSE, MenuUI.ESTADO_CONFIG))
                    simulation_dt = 0.0 if is_paused else dt

                if not is_paused:
                    if glfw.get_key(window, glfw.KEY_UP) == glfw.PRESS:
                        pitch_in -= 1.0
                    if glfw.get_key(window, glfw.KEY_DOWN) == glfw.PRESS:
                        pitch_in += 1.0
                    if glfw.get_key(window, glfw.KEY_LEFT) == glfw.PRESS:
                        roll_in -= 1.0
                    if glfw.get_key(window, glfw.KEY_RIGHT) == glfw.PRESS:
                        roll_in += 1.0
                    if glfw.get_key(window, glfw.KEY_A) == glfw.PRESS:
                        yaw_in += 1.0
                    if glfw.get_key(window, glfw.KEY_D) == glfw.PRESS:
                        yaw_in -= 1.0
                    if glfw.get_key(window, glfw.KEY_W) == glfw.PRESS:
                        throttle_in += 1.0
                    if glfw.get_key(window, glfw.KEY_S) == glfw.PRESS:
                        throttle_in -= 1.0
                        brake_active = True

                    # Soma entradas analógicas/digitais do Gamepad (funciona simultaneamente ao teclado)
                    if self.gamepad.connected:
                        pitch_in = max(-1.0, min(1.0, pitch_in + self.gamepad.pitch))
                        roll_in = max(-1.0, min(1.0, roll_in + self.gamepad.roll))
                        yaw_in = max(-1.0, min(1.0, yaw_in + self.gamepad.yaw))
                        throttle_in = max(-1.0, min(1.0, throttle_in + self.gamepad.throttle))
                        brake_active = brake_active or self.gamepad.brake_active

                        # RS X / RS Y controla a Câmera 3 (Orbital)
                        self.camera.on_gamepad_orbit(
                            self.gamepad.cam_orbit_x,
                            self.gamepad.cam_orbit_y,
                            simulation_dt
                        )

                # Atualiza cinemática da aeronave e física do oceano (pausadas se is_paused == True)
                self.player.update(simulation_dt, pitch_in, roll_in, yaw_in, throttle_in, brake_active, self.scene_mode)
                self.camera.apply_wrap_delta(self.player.last_wrap_delta)

                if self.scene_mode == 1:
                    update_ocean_physics(simulation_dt, self.player, sim_time)
                elif self.scene_mode == 2:
                    update_canyon_dust(simulation_dt, self.player, sim_time)

                # Sincroniza o áudio (pausado suavemente se pause/config)
                audio_dt = 0.0 if is_paused else dt
                self.audio.update(
                    dt=audio_dt,
                    throttle=self.player.throttle,
                    afterburner=self.player.afterburner,
                    crashed=self.player.crashed,
                    aircraft_speed=self.player.speed,
                    on_ground=self.player.on_ground,
                    crash_type=getattr(self.player, "crash_type", "solid"),
                    crash_reason=self.player.crash_reason,
                    paused=is_paused,
                    flaps_moving=getattr(self.player, "flaps_moving", False),
                    airbrake_moving=getattr(self.player, "airbrake_moving", False),
                )

                sun_state = None
                if self.scene_mode == 3:
                    apply_inspection_lighting(self.lighting_enabled)
                else:
                    sun_state = get_sun_state(
                        sim_time, self.scene_mode, time_of_day_hours=self.time_of_day_hours
                    )
                    apply_sunrise_lighting(sun_state, self.lighting_enabled)

                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

                glMatrixMode(GL_PROJECTION)
                glLoadIdentity()
                gluPerspective(60.0, width / float(height), 0.5, 3500.0)

                glMatrixMode(GL_MODELVIEW)
                glLoadIdentity()

                self.camera.apply(self.player, dt, scene_mode=self.scene_mode)

                if self.scene_mode in (1, 2):
                    draw_rising_sun_and_sky(self.player.pos, sun_state, self.scene_mode)

                if self.lighting_enabled:
                    if self.scene_mode == 3:
                        apply_inspection_lighting(True)
                    else:
                        apply_sunrise_lighting(sun_state, True)

                    if self.player.afterburner and self.player.throttle > 0.02 and not self.player.crashed and not is_paused:
                        glEnable(GL_LIGHT1)
                        afterburner_pos = self.player.pos - self.player.forward * 5.5
                        glLightfv(
                            GL_LIGHT1, GL_POSITION,
                            [afterburner_pos[0], afterburner_pos[1], afterburner_pos[2], 1.0]
                        )
                    else:
                        glDisable(GL_LIGHT1)
                else:
                    glDisable(GL_LIGHTING)

                if self.textures_enabled:
                    glEnable(GL_TEXTURE_2D)
                else:
                    glDisable(GL_TEXTURE_2D)

                if self.scene_mode == 1:
                    # 1. Porta-Aviões USS Enterprise (CVN-65) periódico
                    draw_periodic_scene(scene1_list, self.player.pos, scene_mode=1)
                    # 2. Corpo d'água físico baseado em partículas (ondas + esteira + spray + downwash)
                    draw_physical_ocean(
                        self.player,
                        ocean_tex,
                        sim_time,
                        lighting_enabled=self.lighting_enabled,
                        textures_enabled=self.textures_enabled,
                        wireframe_mode=self.wireframe_mode,
                        sun_state=sun_state,
                    )
                    # 3. Reflexo cintilante do Sol ou da Lua sobre as ondas
                    draw_ocean_sun_glitter(self.player.pos, sun_state, sim_time)
                elif self.scene_mode == 2:
                    draw_periodic_scene(scene2_list, self.player.pos, scene_mode=2)
                else:
                    glCallList(scene3_list)

                if self.textures_enabled:
                    glEnable(GL_TEXTURE_2D)
                else:
                    glDisable(GL_TEXTURE_2D)

                if self.camera.mode != 2:
                    draw_f14_complete(
                        self.player,
                        player_fuselage_list,
                        wing_tex,
                        sim_time,
                        skin_manager=self.skin_manager,
                        skinned_fuselage_dlist=player_skinned_fuselage_list,
                    )

                # Partículas de poeira e areia em voo rasante no Cânion (renderizadas após a cena e o caça)
                if self.scene_mode == 2:
                    draw_canyon_dust(sun_state=sun_state, wireframe_mode=self.wireframe_mode)

                if self.scene_mode in (1, 2):
                    active_clouds = clouds1_list if self.scene_mode == 1 else clouds2_list
                    draw_procedural_clouds(
                        active_clouds, cloud_vapor_tex, sim_time,
                        player_pos=self.player.pos, scene_mode=self.scene_mode,
                        sun_state=sun_state,
                    )

                if self.hud_enabled:
                    draw_flight_hud(
                        width, height, self.player,
                        camera_mode=self.camera.mode,
                        scene_mode=self.scene_mode,
                        sim_time=sim_time,
                        sun_state=sun_state,
                        day_cycle_paused=self.day_cycle_paused,
                    )
                    if self.scene_mode == 3:
                        draw_inspection_overlay(
                            width, height, self.player, self.skin_manager, scene_mode=self.scene_mode
                        )

                if self.player.crashed:
                    draw_crash_overlay(width, height, self.player.crash_reason)

                # Desenha a UI de Pause ou Configurações por cima do jogo congelado
                if is_paused:
                    self.ui.draw(width, height)

                glfw.swap_buffers(window)
        finally:
            self.audio.close()
            glfw.terminate()


def select_initial_scene():
    """Verifica se foi passada uma cena por argumento de linha de comando (ex: python src/main.py 1)."""
    if len(sys.argv) > 1 and sys.argv[1] in ("1", "2", "3"):
        return int(sys.argv[1])
    return None


if __name__ == "__main__":
    initial_scene_arg = select_initial_scene()
    app = TopGraphicsApp(initial_scene=initial_scene_arg)
    app.run()