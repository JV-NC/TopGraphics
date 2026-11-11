"""
================================================================================
CEFET-MG | Departamento de Computação - Computação Gráfica
Trabalho Final: TOP GRAPHICS - Simulador de Voo 3D (F-14 Tomcat)
================================================================================
Execução (a partir da raiz do repositório):
    pip install -r requirements.txt
    python src/main.py [1|2]
================================================================================
"""

# TODO: controller integration
# TODO: implement sound effects (engine sounds, ocean ambient sounds, and a soundtrack that can be muted)
# TODO: create a project menu (title, scene selector, and control mapping on the same screen)
# TODO: implement Scenario 3 (just the aircraft in camera 3 for model analisys and reaction of the controls)
# TODO: implement HUD for plane information about velocity, altitude, landing gear, etc (all that is in window title moved in a hud)

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
from f14_model import (
    create_wing_insignia_texture, build_f14_static_fuselage_list, draw_f14_complete
)
from scene_carrier import create_ocean_texture, create_deck_texture, build_scene1_carrier_list
from scene_canyon import create_canyon_texture, build_scene2_canyon_list
from renderer_utils import setup_lighting, draw_cockpit_hud, draw_crash_overlay


# ==============================================================================
# APLICAÇÃO PRINCIPAL E LOOP DE RENDERIZAÇÃO (GLFW + OPENGL)
# ==============================================================================

class TopGraphicsApp:
    def __init__(self, initial_scene=1):
        self.scene_mode = initial_scene  # 1 = Oceano + Porta-Aviões, 2 = Cânion Procedural

        # Estados de recursos gráficos
        self.lighting_enabled = True
        self.textures_enabled = True
        self.wireframe_mode = False

        # Instância única do F-14 Tomcat
        self.player = Aircraft()
        self.player.reset(self.scene_mode)

        # Câmeras virtuais: Chase, Cockpit e Orbital
        self.camera = CameraController(self.player)

    def key_callback(self, window, key, scancode, action, mods):
        """Trata atalhos discretos de teclado para câmeras, trem de pouso, afterburner, cenas e inspeção."""
        if action != glfw.PRESS:
            return

        if key == glfw.KEY_ESCAPE:
            glfw.set_window_should_close(window, True)
        elif key == glfw.KEY_1:
            self.camera.set_mode(1)
        elif key == glfw.KEY_2:
            self.camera.set_mode(2)
        elif key == glfw.KEY_3:
            self.camera.set_mode(3)
        elif key == glfw.KEY_Q:
            self.player.toggle_gear()
        elif key == glfw.KEY_E:
            self.player.toggle_afterburner()
        elif key == glfw.KEY_M:
            self.scene_mode = 2 if self.scene_mode == 1 else 1
            self.player.reset(self.scene_mode)
            self.camera.snap_chase_to(self.player)
            nome = "Cena 1: Oceano + Porta-Aviões" if self.scene_mode == 1 else "Cena 2: Cânion Procedural"
            print(f"[Cenário] Alternado para {nome}")
        elif key == glfw.KEY_R:
            self.player.reset(self.scene_mode)
            self.camera.snap_chase_to(self.player)
            print("[Voo] Posição do F-14 reiniciada.")
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
            self.player.auto_wing_sweep = not self.player.auto_wing_sweep
            if not self.player.auto_wing_sweep:
                self.player.wing_sweep_angle = 68.0 if self.player.wing_sweep_angle < 45.0 else 20.0
            estado = "AUTOMÁTICO" if self.player.auto_wing_sweep else f"MANUAL ({self.player.wing_sweep_angle:.0f}°)"
            print(f"Enflecamento das Asas do F-14: {estado}")

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
            "Top Graphics v2 - F-14 Tomcat 3D Flight Simulator (CEFET-MG)",
            None, None
        )
        if not window:
            glfw.terminate()
            return

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

        player_fuselage_list = build_f14_static_fuselage_list(wing_tex)
        scene1_list = build_scene1_carrier_list(ocean_tex, deck_tex)
        scene2_list = build_scene2_canyon_list(canyon_tex)

        last_time = time.time()
        start_time = last_time

        print("\n" + "=" * 76)
        print(" CONTROLES DE VOO E DEMONSTRAÇÃO (TOP GRAPHICS v2 - F-14 TOMCAT)")
        print("=" * 76)
        print(" [W / S]               : Potência (Throttle) / Segure 'S' no convés para Frear")
        print(" [E]                   : Ligar / Desligar Pós-Combustor (Afterburner Boost)")
        print(" [Q]                   : Recolher / Baixar Trem de Pouso Retrátil (Gera Arrasto)")
        print(" [Setas Baixo / Cima]  : Puxar Manche (Subir/Decolar) / Empurrar (Mergulhar)")
        print(" [Setas Esq / Dir]     : Rolagem (Roll - Inclinar Asas em voo)")
        print(" [A / D]               : Guinada (Leme em voo / Direção da roda no convés)")
        print(" [G]                   : Alternar Enflecamento das Asas (Auto <-> Manual)")
        print(" [1 / 2 / 3]           : Câmeras (1: Chase, 2: Cockpit/HUD, 3: Orbital Mouse)")
        print(" [M]                   : Alternar Cenário (Porta-Aviões <-> Cânion)")
        print(" [L / T / Z]           : Ligar/Desligar Luzes (L), Texturas (T), Wireframe (Z)")
        print(" [R]                   : Reiniciar Posição do Caça imediatamente")
        print(" [ESC]                 : Sair")
        print("=" * 76 + "\n")

        while not glfw.window_should_close(window):
            now = time.time()
            dt = min(0.05, now - last_time)
            last_time = now
            sim_time = now - start_time

            glfw.poll_events()

            pitch_in = 0.0
            roll_in = 0.0
            yaw_in = 0.0
            throttle_in = 0.0
            brake_active = False

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

            # Atualiza cinemática, afterburner, trem de pouso e colisões do F-14
            self.player.update(dt, pitch_in, roll_in, yaw_in, throttle_in, brake_active, self.scene_mode)

            # Atualiza título da janela com estado do voo, trem de pouso, afterburner e alertas
            if self.player.crashed:
                title_status = f"GAME OVER: {self.player.crash_reason}"
            else:
                gear_str = "DOWN" if self.player.gear_down else "UP"
                ab_str = "ON" if self.player.afterburner else "OFF"
                ground_str = "NO CONVÉS" if self.player.on_ground else "EM VOO"
                title_status = (
                    f"{ground_str} | Vel: {self.player.speed * 10:.0f}/{self.player.max_speed * 10:.0f} kt | "
                    f"Alt: {self.player.pos[1] * 10:.0f} ft | Trem(Q): {gear_str} | AB(E): {ab_str} | "
                    f"Asas(G): {self.player.wing_sweep_angle:.0f}° | Cam: {self.camera.mode}"
                )
            glfw.set_window_title(window, f"Top Graphics v2 | {title_status}")

            width, height = glfw.get_framebuffer_size(window)
            height = max(1, height)
            glViewport(0, 0, width, height)

            if self.scene_mode == 1:
                glClearColor(0.42, 0.62, 0.85, 1.0)
            else:
                glClearColor(0.78, 0.55, 0.38, 1.0)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(60.0, width / float(height), 0.5, 3500.0)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            self.camera.apply(self.player, dt)

            if self.lighting_enabled:
                glEnable(GL_LIGHTING)
                glLightfv(GL_LIGHT0, GL_POSITION, [0.6, 0.45, 0.65, 0.0])
                # A luz pontual laranja (GL_LIGHT1) brilha intensamente quando o Afterburner está ativo
                if self.player.afterburner and self.player.throttle > 0.02 and not self.player.crashed:
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
                glCallList(scene1_list)
            else:
                glCallList(scene2_list)

            if self.textures_enabled:
                glEnable(GL_TEXTURE_2D)
            else:
                glDisable(GL_TEXTURE_2D)

            if self.camera.mode != 2:
                draw_f14_complete(self.player, player_fuselage_list, wing_tex, sim_time)

            if self.camera.mode == 2:
                draw_cockpit_hud(width, height, self.player)

            if self.player.crashed:
                draw_crash_overlay(width, height)

            glfw.swap_buffers(window)

        glfw.terminate()

def select_initial_scene():
    """Menu rápido no terminal ao iniciar a aplicação (ou via argumento de linha de comando)."""
    if len(sys.argv) > 1 and sys.argv[1] in ("1", "2"):
        return int(sys.argv[1])

    print("=" * 68)
    print("   TOP GRAPHICS - SIMULADOR DE VOO F-14 TOMCAT (CEFET-MG)")
    print("=" * 68)
    print(" Escolha o cenário inicial (você também pode alternar com 'M' em voo):")
    print("   [1] Cena 1: Oceano + Porta-Aviões (Inicia parado no convés para decolar)")
    print("   [2] Cena 2: Cânion Procedural ('Trench Run' - Inicia em voo)")
    print("=" * 68)
    try:
        choice = input(" Digite 1 ou 2 [Padrão = 1]: ").strip()
        if choice == "2":
            return 2
    except EOFError:
        pass
    return 1

if __name__ == "__main__":
    scene_choice = select_initial_scene()
    app = TopGraphicsApp(initial_scene=scene_choice)
    app.run()
