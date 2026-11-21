"""
================================================================================
TopGraphics | gamepad_controller.py
Sistema Modular de Controle / Gamepad (Padrão XBOX — Detecção Nativa do SO):
  - Utiliza a API nativa de Gamepad do GLFW 3.3+ (XInput/DirectInput no Windows,
    evdev/joydev no Linux, HID no macOS), com banco de mapeamento SDL embutido
    para detecção plug-and-play automática (sem dependências extras!).
  - Inclui fallback automático para joysticks USB genéricos fora do banco SDL,
    proteção contra gatilhos em repouso 0.0 em drivers Linux, zona morta suave
    (deadzone + curva de resposta), detecção de borda (just_pressed) e navegação
    completa nos menus (Menu Principal, Pause e Configurações de Áudio).

Mapeamento Padrão XBOX:
  - LT            : Reduz Throttle (e freia no convés)
  - RT            : Aumenta Throttle
  - LB / RB       : Guinada Esquerda / Guinada Direita
  - LS Y / LS X   : Arfagem (Pitch) / Rolagem (Roll)
  - LS (Clique)   : Toggle Flaps
  - RS X / RS Y   : Mover Câmera Orbital (quando na Câmera 3)
  - RS (Clique)   : Alternar Câmera (1 -> 2 -> 3)
  - A             : Toggle Trem de Pouso (Em jogo) / Confirmar (Menus)
  - B             : Toggle Air Brake (Em jogo) / Voltar (Menus)
  - X             : Toggle Afterburner
  - Y             : Alternar Cenas (1 -> 2 -> 3)
  - START         : Abrir / Fechar Menu de Pause
  - BACK / VIEW   : Reiniciar Aeronave
  - D-Pad         : Navegar Menus / Sliders | Em voo: Dia/Noite, Asas, HUD, Ciclo
                    | Na Cena 3 (Inspeção): Skin, Paleta, HUD, Asas
================================================================================
"""

import math

try:
    import glfw
    GLFW_AVAILABLE = True
except ImportError:
    glfw = None
    GLFW_AVAILABLE = False


# Nomes lógicos padronizados (Padrão XBOX)
BTN_A = "A"
BTN_B = "B"
BTN_X = "X"
BTN_Y = "Y"
BTN_LB = "LB"
BTN_RB = "RB"
BTN_BACK = "BACK"
BTN_START = "START"
BTN_LS = "LS"
BTN_RS = "RS"
BTN_DPAD_UP = "DPAD_UP"
BTN_DPAD_RIGHT = "DPAD_RIGHT"
BTN_DPAD_DOWN = "DPAD_DOWN"
BTN_DPAD_LEFT = "DPAD_LEFT"

ALL_BUTTONS = (
    BTN_A, BTN_B, BTN_X, BTN_Y,
    BTN_LB, BTN_RB,
    BTN_BACK, BTN_START,
    BTN_LS, BTN_RS,
    BTN_DPAD_UP, BTN_DPAD_RIGHT, BTN_DPAD_DOWN, BTN_DPAD_LEFT,
)

# Parâmetros de ergonomia e resposta analógica
STICK_DEADZONE = 0.14
STICK_RESPONSE_EXP = 1.35
TRIGGER_DEADZONE = 0.06

# Temporização de repetição automática para navegação em menus/sliders
MENU_REPEAT_DELAY = 0.34
MENU_REPEAT_RATE = 0.11


def _decode_glfw_name(raw_name):
    """Converte o nome retornado pelo GLFW (bytes ou str) para string legível."""
    if raw_name is None:
        return "Gamepad Genérico"
    if isinstance(raw_name, bytes):
        return raw_name.decode("utf-8", errors="ignore").strip() or "Gamepad Genérico"
    return str(raw_name).strip() or "Gamepad Genérico"


def _shape_stick_axis(raw_val, deadzone=STICK_DEADZONE, exp=STICK_RESPONSE_EXP):
    """
    Aplica zona morta suave e curva de resposta exponencial a um eixo analógico [-1..+1],
    evitando drift involuntário no centro e dando precisão em pequenas correções de voo.
    """
    v = max(-1.0, min(1.0, float(raw_val)))
    mag = abs(v)
    if mag <= deadzone:
        return 0.0
    norm = (mag - deadzone) / max(1e-5, (1.0 - deadzone))
    shaped = norm ** exp
    return math.copysign(shaped, v)


def _extract_glfw_array(result):
    """
    Extrai com segurança uma lista Python de floats/ints do retorno de
    glfw.get_joystick_axes / get_joystick_buttons / get_joystick_hats
    (que no pyGLFW retornam tupla (ctypes_ptr, count)).
    """
    if result is None:
        return []
    if isinstance(result, tuple) and len(result) == 2:
        ptr, count = result
        if not ptr or count <= 0:
            return []
        return [ptr[i] for i in range(int(count))]
    try:
        return list(result)
    except TypeError:
        return []


class GamepadController:
    """
    Gerencia detecção automática, hot-plug, leitura analógica/digital e
    tradução de comandos de Gamepad padrão XBOX diretamente via SO (GLFW).
    """

    def __init__(self):
        self.active_jid = None
        self.device_name = ""
        self.using_standard_mapping = False

        # Estado atual e anterior dos botões para detecção de borda (just_pressed)
        self._curr_buttons = {b: False for b in ALL_BUTTONS}
        self._prev_buttons = {b: False for b in ALL_BUTTONS}

        # Saídas analógicas já tratadas (prontas para o loop de voo e câmera)
        self.pitch = 0.0        # LS Y (-1.0 empurrar/mergulhar .. +1.0 puxar/subir)
        self.roll = 0.0         # LS X (-1.0 esquerda .. +1.0 direita)
        self.yaw = 0.0          # LB (+1.0 esquerda) / RB (-1.0 direita)
        self.throttle = 0.0     # RT - LT (-1.0 reduzir .. +1.0 acelerar)
        self.brake_active = False
        self.lt_value = 0.0     # [0.0 .. 1.0]
        self.rt_value = 0.0     # [0.0 .. 1.0]
        self.cam_orbit_x = 0.0  # RS X (-1.0 .. +1.0)
        self.cam_orbit_y = 0.0  # RS Y (-1.0 .. +1.0)

        # Proteção contra drivers Linux que reportam 0.0 nos gatilhos antes do primeiro toque
        self._lt_calibrated = False
        self._rt_calibrated = False

        # Estado de auto-repeat para navegação confortável nos menus (D-Pad / LS)
        self._menu_nav_dir = None
        self._menu_nav_timer = 0.0

    @property
    def connected(self):
        return self.active_jid is not None

    def _reset_outputs(self):
        """Zera todos os eixos e botões ao desconectar o controle."""
        for b in ALL_BUTTONS:
            self._prev_buttons[b] = False
            self._curr_buttons[b] = False
        self.pitch = 0.0
        self.roll = 0.0
        self.yaw = 0.0
        self.throttle = 0.0
        self.brake_active = False
        self.lt_value = 0.0
        self.rt_value = 0.0
        self.cam_orbit_x = 0.0
        self.cam_orbit_y = 0.0
        self._menu_nav_dir = None
        self._menu_nav_timer = 0.0

    def _normalize_trigger(self, raw_val, is_left):
        """
        Normaliza eixo de gatilho de [-1.0 (solto) .. +1.0 (pressionado)] para [0.0 .. 1.0].
        Inclui guarda contra drivers que iniciam em 0.0 exato até o primeiro toque do jogador.
        """
        v = max(-1.0, min(1.0, float(raw_val)))
        if is_left:
            if not self._lt_calibrated:
                if v < -0.10 or v > 0.10:
                    self._lt_calibrated = True
                else:
                    return 0.0
        else:
            if not self._rt_calibrated:
                if v < -0.10 or v > 0.10:
                    self._rt_calibrated = True
                else:
                    return 0.0

        norm = (v + 1.0) * 0.5
        if norm <= TRIGGER_DEADZONE:
            return 0.0
        return (norm - TRIGGER_DEADZONE) / max(1e-5, (1.0 - TRIGGER_DEADZONE))

    def _scan_for_gamepad(self):
        """
        Varre automaticamente os slots do SO (GLFW_JOYSTICK_1..16), priorizando controles
        com mapeamento padrão XBOX/SDL (joystick_is_gamepad) e aceitando fallback genérico.
        """
        if not GLFW_AVAILABLE:
            return

        jid_start = getattr(glfw, "JOYSTICK_1", 0)
        jid_last = getattr(glfw, "JOYSTICK_LAST", 15)

        fallback_jid = None
        chosen_jid = None
        chosen_std = False

        for jid in range(jid_start, jid_last + 1):
            try:
                if not glfw.joystick_present(jid):
                    continue
                is_gp = bool(hasattr(glfw, "joystick_is_gamepad") and glfw.joystick_is_gamepad(jid))
                if is_gp:
                    chosen_jid = jid
                    chosen_std = True
                    break
                if fallback_jid is None:
                    fallback_jid = jid
            except Exception:
                continue

        if chosen_jid is None and fallback_jid is not None:
            chosen_jid = fallback_jid
            chosen_std = False

        if chosen_jid is not None:
            self.active_jid = chosen_jid
            self.using_standard_mapping = chosen_std
            self._lt_calibrated = False
            self._rt_calibrated = False

            raw_name = None
            try:
                if chosen_std and hasattr(glfw, "get_gamepad_name"):
                    raw_name = glfw.get_gamepad_name(chosen_jid)
                if not raw_name and hasattr(glfw, "get_joystick_name"):
                    raw_name = glfw.get_joystick_name(chosen_jid)
            except Exception:
                raw_name = None

            self.device_name = _decode_glfw_name(raw_name)
            mode_tag = "Mapeamento Padrão XBOX/SDL" if chosen_std else "Modo Fallback USB Genérico"
            print(f"[Gamepad] Conectado (Slot {chosen_jid}): {self.device_name} [{mode_tag}]")

    def _read_standard_gamepad(self, jid):
        """Lê estado padronizado XBOX diretamente via glfw.get_gamepad_state(jid)."""
        state = glfw.get_gamepad_state(jid)
        if not state:
            return False

        btns = state.buttons
        axes = state.axes
        press_val = getattr(glfw, "PRESS", 1)

        btn_map = {
            BTN_A: getattr(glfw, "GAMEPAD_BUTTON_A", 0),
            BTN_B: getattr(glfw, "GAMEPAD_BUTTON_B", 1),
            BTN_X: getattr(glfw, "GAMEPAD_BUTTON_X", 2),
            BTN_Y: getattr(glfw, "GAMEPAD_BUTTON_Y", 3),
            BTN_LB: getattr(glfw, "GAMEPAD_BUTTON_LEFT_BUMPER", 4),
            BTN_RB: getattr(glfw, "GAMEPAD_BUTTON_RIGHT_BUMPER", 5),
            BTN_BACK: getattr(glfw, "GAMEPAD_BUTTON_BACK", 6),
            BTN_START: getattr(glfw, "GAMEPAD_BUTTON_START", 7),
            BTN_LS: getattr(glfw, "GAMEPAD_BUTTON_LEFT_THUMB", 9),
            BTN_RS: getattr(glfw, "GAMEPAD_BUTTON_RIGHT_THUMB", 10),
            BTN_DPAD_UP: getattr(glfw, "GAMEPAD_BUTTON_DPAD_UP", 11),
            BTN_DPAD_RIGHT: getattr(glfw, "GAMEPAD_BUTTON_DPAD_RIGHT", 12),
            BTN_DPAD_DOWN: getattr(glfw, "GAMEPAD_BUTTON_DPAD_DOWN", 13),
            BTN_DPAD_LEFT: getattr(glfw, "GAMEPAD_BUTTON_DPAD_LEFT", 14),
        }

        for name, idx in btn_map.items():
            self._curr_buttons[name] = bool(btns[idx] == press_val)

        ax_lx = axes[getattr(glfw, "GAMEPAD_AXIS_LEFT_X", 0)]
        ax_ly = axes[getattr(glfw, "GAMEPAD_AXIS_LEFT_Y", 1)]
        ax_rx = axes[getattr(glfw, "GAMEPAD_AXIS_RIGHT_X", 2)]
        ax_ry = axes[getattr(glfw, "GAMEPAD_AXIS_RIGHT_Y", 3)]
        ax_lt = axes[getattr(glfw, "GAMEPAD_AXIS_LEFT_TRIGGER", 4)]
        ax_rt = axes[getattr(glfw, "GAMEPAD_AXIS_RIGHT_TRIGGER", 5)]

        self._apply_axes_and_yaw(ax_lx, ax_ly, ax_rx, ax_ry, ax_lt, ax_rt)
        return True

    def _read_raw_joystick_fallback(self, jid):
        """
        Fallback para controles genéricos USB caso o SO não possua perfil SDL mapeado.
        Assume layout padrão XInput/HID de 6 eixos + 10 botões + 1 hat (D-Pad).
        """
        axes = _extract_glfw_array(glfw.get_joystick_axes(jid))
        btns = _extract_glfw_array(glfw.get_joystick_buttons(jid))
        hats = _extract_glfw_array(glfw.get_joystick_hats(jid)) if hasattr(glfw, "get_joystick_hats") else []
        press_val = getattr(glfw, "PRESS", 1)

        def get_btn(i):
            return bool(i < len(btns) and btns[i] == press_val)

        def get_ax(i, default=0.0):
            return float(axes[i]) if i < len(axes) else default

        self._curr_buttons[BTN_A] = get_btn(0)
        self._curr_buttons[BTN_B] = get_btn(1)
        self._curr_buttons[BTN_X] = get_btn(2)
        self._curr_buttons[BTN_Y] = get_btn(3)
        self._curr_buttons[BTN_LB] = get_btn(4)
        self._curr_buttons[BTN_RB] = get_btn(5)
        self._curr_buttons[BTN_BACK] = get_btn(6)
        self._curr_buttons[BTN_START] = get_btn(7)
        self._curr_buttons[BTN_LS] = get_btn(8)
        self._curr_buttons[BTN_RS] = get_btn(9)

        hat_val = int(hats[0]) if hats else 0
        self._curr_buttons[BTN_DPAD_UP] = bool(hat_val & getattr(glfw, "HAT_UP", 1))
        self._curr_buttons[BTN_DPAD_RIGHT] = bool(hat_val & getattr(glfw, "HAT_RIGHT", 2))
        self._curr_buttons[BTN_DPAD_DOWN] = bool(hat_val & getattr(glfw, "HAT_DOWN", 4))
        self._curr_buttons[BTN_DPAD_LEFT] = bool(hat_val & getattr(glfw, "HAT_LEFT", 8))

        # Eixos padrão Linux/Windows HID (0:LX, 1:LY, 2:LT ou RX, 3:RX ou RY, 4:RY ou RT, 5:RT)
        ax_lx = get_ax(0, 0.0)
        ax_ly = get_ax(1, 0.0)
        if len(axes) >= 6:
            ax_rx = get_ax(3, 0.0)
            ax_ry = get_ax(4, 0.0)
            ax_lt = get_ax(2, -1.0)
            ax_rt = get_ax(5, -1.0)
        else:
            ax_rx = get_ax(2, 0.0)
            ax_ry = get_ax(3, 0.0)
            ax_lt = -1.0
            ax_rt = -1.0

        self._apply_axes_and_yaw(ax_lx, ax_ly, ax_rx, ax_ry, ax_lt, ax_rt)
        return True

    def _apply_axes_and_yaw(self, ax_lx, ax_ly, ax_rx, ax_ry, ax_lt, ax_rt):
        """Converte os 6 eixos analógicos e LB/RB nos comandos finais do simulador."""
        # LS X -> Rolagem (-1 esquerda .. +1 direita)
        self.roll = _shape_stick_axis(ax_lx)
        # LS Y -> Arfagem (-1 empurrar/mergulhar .. +1 puxar/subir, padrão manche)
        self.pitch = _shape_stick_axis(ax_ly)

        # RS X / RS Y -> Movimento da Câmera Orbital (Câmera 3)
        self.cam_orbit_x = _shape_stick_axis(ax_rx)
        self.cam_orbit_y = _shape_stick_axis(ax_ry)

        # LT -> Reduz Throttle (e aciona freio no convés) | RT -> Aumenta Throttle
        self.lt_value = self._normalize_trigger(ax_lt, is_left=True)
        self.rt_value = self._normalize_trigger(ax_rt, is_left=False)
        self.throttle = max(-1.0, min(1.0, self.rt_value - self.lt_value))
        self.brake_active = (self.lt_value > 0.15)

        # LB -> Guinada Esquerda (+1.0) | RB -> Guinada Direita (-1.0)
        yaw_l = 1.0 if self._curr_buttons[BTN_LB] else 0.0
        yaw_r = 1.0 if self._curr_buttons[BTN_RB] else 0.0
        self.yaw = yaw_l - yaw_r

    def poll(self):
        """
        Atualiza o estado do gamepad a cada frame, gerenciando hot-plug automaticamente.
        Deve ser chamado logo após glfw.poll_events().
        """
        if not GLFW_AVAILABLE:
            return

        # 1. Verifica desconexão do controle ativo
        if self.active_jid is not None:
            try:
                if not glfw.joystick_present(self.active_jid):
                    print(f"[Gamepad] Desconectado: {self.device_name}")
                    self.active_jid = None
                    self.device_name = ""
                    self.using_standard_mapping = False
                    self._reset_outputs()
            except Exception:
                self.active_jid = None
                self._reset_outputs()

        # 2. Se nenhum controle estiver ativo, procura automaticamente um conectado ao SO
        if self.active_jid is None:
            self._scan_for_gamepad()
            if self.active_jid is None:
                return

        # 3. Salva estado anterior dos botões para detecção de borda (just_pressed)
        for b in ALL_BUTTONS:
            self._prev_buttons[b] = self._curr_buttons[b]

        # 4. Lê o estado do controle (padrão XBOX/SDL ou fallback genérico)
        try:
            if self.using_standard_mapping and hasattr(glfw, "get_gamepad_state"):
                ok = self._read_standard_gamepad(self.active_jid)
                if not ok:
                    self._read_raw_joystick_fallback(self.active_jid)
            else:
                self._read_raw_joystick_fallback(self.active_jid)
        except Exception as exc:
            print(f"[Gamepad] Aviso na leitura ({exc}); reiniciando detecção.")
            self.active_jid = None
            self._reset_outputs()

    def is_held(self, button_name):
        """Retorna True enquanto o botão estiver pressionado."""
        return bool(self._curr_buttons.get(button_name, False))

    def just_pressed(self, button_name):
        """Retorna True apenas no frame exato em que o botão foi pressionado."""
        return bool(self._curr_buttons.get(button_name, False) and not self._prev_buttons.get(button_name, False))

    def get_menu_key_events(self, dt):
        """
        Traduz entradas do Gamepad (D-Pad, Left Stick, A, B e START) em eventos de
        tecla GLFW equivalentes para navegar nativamente no Menu Principal, Pause
        e Configurações de Áudio (incluindo sliders com auto-repeat suave).
        """
        if not self.connected or not GLFW_AVAILABLE:
            return []

        events = []

        # Botões de confirmação e retorno (A = Enter, B / START = ESC)
        if self.just_pressed(BTN_A):
            events.append(glfw.KEY_ENTER)
        if self.just_pressed(BTN_B) or self.just_pressed(BTN_START):
            events.append(glfw.KEY_ESCAPE)

        # Direção atual de navegação (D-Pad tem prioridade; LS funciona como alternativa)
        nav_dir = None
        if self.is_held(BTN_DPAD_UP) or self.pitch < -0.45:
            nav_dir = glfw.KEY_UP
        elif self.is_held(BTN_DPAD_DOWN) or self.pitch > 0.45:
            nav_dir = glfw.KEY_DOWN
        elif self.is_held(BTN_DPAD_LEFT) or self.roll < -0.45:
            nav_dir = glfw.KEY_LEFT
        elif self.is_held(BTN_DPAD_RIGHT) or self.roll > 0.45:
            nav_dir = glfw.KEY_RIGHT

        if nav_dir is None:
            self._menu_nav_dir = None
            self._menu_nav_timer = 0.0
        elif nav_dir != self._menu_nav_dir:
            # Novo toque: dispara imediatamente e arma o atraso inicial
            self._menu_nav_dir = nav_dir
            self._menu_nav_timer = MENU_REPEAT_DELAY
            events.append(nav_dir)
        else:
            # Segurando direção: repete em cadência suave (ideal para ajustar sliders)
            self._menu_nav_timer -= dt
            if self._menu_nav_timer <= 0.0:
                self._menu_nav_timer = MENU_REPEAT_RATE
                events.append(nav_dir)

        return events
