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

# TODO: change map selection to f1, f2 and f3 instead of cicle on M key
# TODO: controller integration
# TODO: implement sound effects (engine sounds, ocean ambient sounds, and a soundtrack that can be muted)
# TODO: create a project menu (title, scene selector, and control mapping on the same screen)

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
    create_wing_insignia_texture,
    build_f14_static_fuselage_list,
    build_f14_skinned_fuselage_list,
    draw_f14_complete,
)
from skin_manager import SkinManager
from scene_carrier import create_ocean_texture, create_deck_texture, build_scene1_carrier_list
from scene_canyon import create_canyon_texture, build_scene2_canyon_list
from scene_inspection import (
    apply_inspection_lighting,
    build_scene3_inspection_list,
    draw_inspection_overlay,
)
from scene_utils import (
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
# APLICAÇÃO PRINCIPAL E LOOP DE RENDERIZAÇÃO (GLFW + OPENGL)
# ==============================================================================

class TopGraphicsApp:
    SCENE_NAMES = {
        1: "Cena 1: Oceano + Porta-Aviões (CVN-65)",
        2: "Cena 2: Cânion Procedural (Trench Run)",
        3: "Cena 3: Hangar de Inspeção Técnica e Customização de Skins",
    }

    def __init__(self, initial_scene=1):
        self.scene_mode = initial_scene  # 1 = Porta-Aviões, 2 = Cânion, 3 = Inspeção

        # Estados de recursos gráficos e interface
        self.lighting_enabled = True
        self.textures_enabled = True
        self.wireframe_mode = False
        self.hud_enabled = True

        # Instância única do F-14 Tomcat
        self.player = Aircraft()
        self.player.reset(self.scene_mode)

        # Câmeras virtuais: Chase, Cockpit e Orbital
        self.camera = CameraController(self.player)
        if self.scene_mode == 3:
            self.camera.set_mode(3)

        self.skin_manager = None

    def key_callback(self, window, key, scancode, action, mods):
        """Trata atalhos discretos de teclado para câmeras, trem, AB, skins, HUD e cenas."""
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
        elif key == glfw.KEY_K:
            if self.skin_manager is not None:
                self.skin_manager.next_pattern()
        elif key == glfw.KEY_P:
            if self.skin_manager is not None:
                self.skin_manager.next_palette()
        elif key == glfw.KEY_H:
            self.hud_enabled = not self.hud_enabled
            print(f"[HUD] Interface Tática: {'ATIVADA' if self.hud_enabled else 'OCULTA'}")
        elif key == glfw.KEY_M:
            self.scene_mode = (self.scene_mode % 3) + 1
            self.player.reset(self.scene_mode)
            if self.scene_mode == 3:
                self.camera.set_mode(3)
            else:
                self.camera.set_mode(1)
                self.camera.snap_chase_to(self.player)
            print(f"[Cenário] Alternado para {self.SCENE_NAMES[self.scene_mode]}")
        elif key == glfw.KEY_R:
            self.player.reset(self.scene_mode)
            self.camera.snap_chase_to(self.player)
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
            "Top Graphics - F-14 Tomcat 3D Flight Simulator (CEFET-MG)",
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
        cloud_vapor_tex = create_cloud_vapor_texture()

        self.skin_manager = SkinManager(default_wing_tex_id=wing_tex)

        player_fuselage_list = build_f14_static_fuselage_list(wing_tex)
        player_skinned_fuselage_list = build_f14_skinned_fuselage_list()

        scene1_list = build_scene1_carrier_list(ocean_tex, deck_tex)
        scene2_list = build_scene2_canyon_list(canyon_tex)
        scene3_list = build_scene3_inspection_list()
        clouds1_list = build_procedural_clouds_list(scene_mode=1)
        clouds2_list = build_procedural_clouds_list(scene_mode=2)

        last_time = time.time()
        start_time = last_time

        print("\n" + "=" * 78)
        print(" CONTROLES DE VOO, INSPEÇÃO E SKINS (TOP GRAPHICS - F-14 TOMCAT)")
        print("=" * 78)
        print(" [W / S]               : Potência (Throttle) / Segure 'S' no convés para Frear")
        print(" [E]                   : Ligar / Desligar Pós-Combustor (Afterburner Boost)")
        print(" [Q]                   : Recolher / Baixar Trem de Pouso Retrátil (Gera Arrasto)")
        print(" [Setas Baixo / Cima]  : Puxar Manche (Subir/Decolar) / Empurrar (Mergulhar)")
        print(" [Setas Esq / Dir]     : Rolagem (Roll - Inclinar Asas e acionar Spoilers)")
        print(" [A / D]               : Guinada (Leme em voo / Direção da roda no convés)")
        print(" [G]                   : Alternar Enflecamento das Asas (Auto <-> Manual)")
        print(" [K]                   : Alternar Padrão de Skin (Padrão / 3 Metálicos / 3 Camos)")
        print(" [P]                   : Alternar Paleta da Camuflagem (Arctic/Desert/Navy/Urban/Woodland)")
        print(" [H]                   : Mostrar / Ocultar HUD Tático na Tela")
        print(" [1 / 2 / 3]           : Câmeras (1: Chase, 2: Cockpit/HUD, 3: Orbital Mouse)")
        print(" [M]                   : Alternar Cenário (1: Porta-Aviões -> 2: Cânion -> 3: Inspeção)")
        print(" [L / T / Z]           : Ligar/Desligar Luzes (L), Texturas (T), Wireframe (Z)")
        print(" [R]                   : Reiniciar Posição/Atitude do Caça imediatamente")
        print(" [ESC]                 : Sair")
        print("=" * 78 + "\n")

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

            # Atualiza cinemática, afterburner, trem de pouso, teleporte Roundabout e colisões
            self.player.update(dt, pitch_in, roll_in, yaw_in, throttle_in, brake_active, self.scene_mode)
            self.camera.apply_wrap_delta(self.player.last_wrap_delta)

            width, height = glfw.get_framebuffer_size(window)
            height = max(1, height)
            glViewport(0, 0, width, height)

            if self.scene_mode == 3:
                apply_inspection_lighting(self.lighting_enabled)
            else:
                sun_state = get_sun_state(sim_time, self.scene_mode)
                apply_sunrise_lighting(sun_state, self.lighting_enabled)

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            glMatrixMode(GL_PROJECTION)
            glLoadIdentity()
            gluPerspective(60.0, width / float(height), 0.5, 3500.0)

            glMatrixMode(GL_MODELVIEW)
            glLoadIdentity()

            self.camera.apply(self.player, dt)

            # 1. Cenas 1 e 2 usam Sky Dome de Nascer do Sol; Cena 3 usa Plataforma de Inspeção
            if self.scene_mode in (1, 2):
                draw_rising_sun_and_sky(self.player.pos, sun_state, self.scene_mode)

            if self.lighting_enabled:
                if self.scene_mode == 3:
                    apply_inspection_lighting(True)
                else:
                    apply_sunrise_lighting(sun_state, True)

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

            # 2. Geometria do Cenário Ativo (1, 2 ou 3)
            if self.scene_mode == 1:
                draw_periodic_scene(scene1_list, self.player.pos, scene_mode=1)
                draw_ocean_sun_glitter(self.player.pos, sun_state, sim_time)
            elif self.scene_mode == 2:
                draw_periodic_scene(scene2_list, self.player.pos, scene_mode=2)
            else:
                glCallList(scene3_list)

            if self.textures_enabled:
                glEnable(GL_TEXTURE_2D)
            else:
                glDisable(GL_TEXTURE_2D)

            # 3. F-14 Tomcat (com suporte à Skin ativa: Padrão, Metálica ou Camuflagem)
            if self.camera.mode != 2:
                draw_f14_complete(
                    self.player,
                    player_fuselage_list,
                    wing_tex,
                    sim_time,
                    skin_manager=self.skin_manager,
                    skinned_fuselage_dlist=player_skinned_fuselage_list,
                )

            # 4. Nuvens Procedurais de Vapor (apenas nos cenários externos 1 e 2)
            if self.scene_mode in (1, 2):
                active_clouds = clouds1_list if self.scene_mode == 1 else clouds2_list
                draw_procedural_clouds(
                    active_clouds, cloud_vapor_tex, sim_time,
                    player_pos=self.player.pos, scene_mode=self.scene_mode
                )

            # 5. HUD Integrado + Painel de Customização de Skins
            if self.hud_enabled:
                draw_flight_hud(
                    width, height, self.player,
                    camera_mode=self.camera.mode,
                    scene_mode=self.scene_mode,
                    sim_time=sim_time
                )
                draw_inspection_overlay(width, height, self.player, self.skin_manager)

            # 6. Alerta de Impacto (Game Over)
            if self.player.crashed:
                draw_crash_overlay(width, height, self.player.crash_reason)

            glfw.swap_buffers(window)

        glfw.terminate()


def select_initial_scene():
    """Menu rápido no terminal ao iniciar a aplicação (ou via argumento de linha de comando)."""
    if len(sys.argv) > 1 and sys.argv[1] in ("1", "2", "3"):
        return int(sys.argv[1])

    print("=" * 72)
    print("   TOP GRAPHICS - SIMULADOR DE VOO F-14 TOMCAT (CEFET-MG)")
    print("=" * 72)
    print(" Escolha o cenário inicial (você também pode alternar com 'M' em execução):")
    print("   [1] Cena 1: Oceano + Porta-Aviões (Inicia parado no convés para decolar)")
    print("   [2] Cena 2: Cânion Procedural ('Trench Run' - Inicia em voo)")
    print("   [3] Cena 3: Hangar de Inspeção 360° e Customização de Skins")
    print("=" * 72)
    try:
        choice = input(" Digite 1, 2 ou 3 [Padrão = 1]: ").strip()
        if choice in ("2", "3"):
            return int(choice)
    except EOFError:
        pass
    return 1


if __name__ == "__main__":
    scene_choice = select_initial_scene()
    app = TopGraphicsApp(initial_scene=scene_choice)
    app.run()