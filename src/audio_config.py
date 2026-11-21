"""
================================================================================
TopGraphics | audio_config.py
Configuração centralizada do Sistema de Áudio (Sound Design Sprint):
  - Taxa de amostragem, canais de saída e volumes padrão por categoria.
  - Mapeamento completo dos arquivos WAV (Motores A/B internos e externos,
    Afterburner EFSC, Start/Shut recortados e filtrados, Trem de Pouso com
    time-stretch sem alterar pitch, Touchdown e Ground Roll unificados,
    Ambientes das Cenas 1 e 2, e Trilhas Musicais).
  - Curvas de crossfade por faixa de potência (throttle) baseadas no sound.cfg.
================================================================================
"""

# ==============================================================================
# 1. PARÂMETROS GERAIS DO STREAM DE SAÍDA (SOUNDDEVICE)
# ==============================================================================

OUTPUT_SAMPLE_RATE = 44100
OUTPUT_CHANNELS = 2
STREAM_BLOCKSIZE = 1024

# Volumes iniciais (0.0 a 1.0) controláveis via AudioManager e futura GUI
DEFAULT_VOLUMES = {
    "master": 0.85,
    "music": 0.35,
    "engine": 0.80,
    "ambience": 0.55,
    "sfx": 0.85,
}

# Presets para testes rápidos de velocidade/pitch (quando aplicável)
AUDIO_SPEED_TEST_PRESETS = {
    "slow": 0.85,
    "normal": 1.00,
    "fast": 1.15,
    "very_fast": 1.30,
}

# Tempos de suavização e crossfade (em segundos)
MUSIC_CROSSFADE_SECONDS = 1.50
AMBIENCE_CROSSFADE_SECONDS = 1.20
PERSPECTIVE_CROSSFADE_SECONDS = 0.18   # Transição suave Câmera 1/3 (Ext) <-> Câmera 2 (Int)
ENGINE_SMOOTH_TIME_SECONDS = 0.12      # Suavização de resposta de volume do motor ao throttle
AFTERBURNER_FADE_SECONDS = 0.22        # Fade-in/out do loop EFSC (Afterburner)
LOOP_CROSSFADE_SECONDS = 0.025         # Micro-crossfade nas bordas de loop para evitar cliques


# ==============================================================================
# 2. CURVAS DE CROSSFADE DOS SEGMENTOS DE MOTOR POR FAIXA DE THROTTLE (0.0 .. 1.0)
# ==============================================================================
# Cada tupla define (fade_in_start, peak_start, peak_end, fade_out_end, base_gain).
# Os áudios do motor operam em loop contínuo com speed=1.0 (sem alterar pitch/velocidade).

JET_WHINE_THROTTLE_ENVELOPES = [
    # Seg 0 (A_f14_0 / B_f14_0): Idle e baixa rotação
    (0.00, 0.00, 0.25, 0.45, 0.70),
    # Seg 1 (A_f14_1 / B_f14_1): Subida média-baixa
    (0.18, 0.32, 0.50, 0.64, 0.80),
    # Seg 2 (A_f14_2 / B_f14_2): Regime médio-alto
    (0.42, 0.55, 0.68, 0.78, 0.85),
    # Seg 3 (A_f14_3 / B_f14_3): Regime militar / alta potência
    (0.64, 0.74, 1.00, 1.05, 0.90),
]

COMBUSTION_THROTTLE_ENVELOPES = [
    # Seg 1 (A_COMB_1 / B_COMB_1): Combustão base (Idle -> 35%)
    (0.00, 0.00, 0.24, 0.42, 0.75),
    # Seg 2 (A_COMB_2 / B_COMB_2): Combustão intermediária (15% -> 65%)
    (0.15, 0.30, 0.50, 0.65, 0.80),
    # Seg 3 (A_COMB_3 / B_COMB_3): Combustão alta (40% -> 88%)
    (0.40, 0.55, 0.73, 0.88, 0.85),
    # Seg 4 (A_COMB_4 / B_COMB_4): Combustão máxima seca (60% -> 100%)
    (0.60, 0.78, 1.00, 1.05, 0.95),
]

# Parâmetros de rolagem no solo (Ground Roll - roll2.wav) conforme velocidade no convés
GROUND_ROLL_MIN_SPEED = 0.5            # Velocidade mínima (unidades internas) para iniciar som
GROUND_ROLL_FULL_SPEED = 28.0          # Velocidade de decolagem onde o som atinge ganho nominal
GROUND_ROLL_MIN_RATE = 0.85            # Rate mínimo (conforme sound.cfg: minimum_rate=0.85)
GROUND_ROLL_MAX_RATE = 1.10            # Rate máximo (conforme sound.cfg: maximum_rate=1.10)


# ==============================================================================
# 3. MAPEAMENTO DE CENÁRIOS PARA MÚSICA E AMBIENTE
# ==============================================================================
# Conforme diretriz:
#   - Ambiente 1 (Cena 1): WATRWave_Soft Waves Cliffs_JSE_RCoN_Stereo.wav
#   - Ambiente 2 (Cena 2): WINDDsgn_EXT, Eye Of The Storm_344 Audio_Extreme Winds Vol 1.wav
#   - Cena 3 e Menu Principal: Sem som ambiente (None)

SCENE_AUDIO_MAP = {
    1: {
        "music": "music_flight",
        "ambience": "ambience_scene1_ocean",
        "engines_active": True,
    },
    2: {
        "music": "music_flight",
        "ambience": "ambience_scene2_canyon",
        "engines_active": True,
    },
    3: {
        "music": "music_menu_inspection",
        "ambience": None,
        "engines_active": False,
    },
    "menu": {
        "music": "music_menu_inspection",
        "ambience": None,
        "engines_active": False,
    },
}

# ==============================================================================
# 3.1 MAPEAMENTO RÁPIDO DOS SONS DE MENU (FÁCIL DE TROCAR PARA TESTES)
# ==============================================================================
# Basta alterar qual clip ('menu_1', 'menu_2' ou 'menu_3') toca em cada ação:
#   - "move"  : mover entre opções ou ajustar sliders
#   - "select": confirmar opção/botão com Enter/Espaço
#   - "pause" : abrir ou fechar o menu de pause com ESC
MENU_SFX_MAP = {
    "move":   "menu_2",   # menu2.wav (0.08s, clique curto e percussivo)
    "select": "menu_1",   # menu1.wav (0.89s, confirmação encorpada)
    "pause":  "menu_3",   # menu3.wav (0.84s, transição suave/brilhante)
}



# ==============================================================================
# 4. CATÁLOGO DE CLIPS DE ÁUDIO E TRATAMENTOS DE SINAL (RECORTES / FILTROS / OLA)
# ==============================================================================
# Campos suportados por clip:
#   - path              : Caminho relativo preferencial (o loader também busca em subpastas de assets/)
#   - category          : 'engine' | 'ambience' | 'sfx' | 'music'
#   - start_sec         : Início do recorte em segundos (None = início do arquivo)
#   - end_sec           : Fim do recorte em segundos (None = fim do arquivo)
#   - segments_sec      : Lista opcional de tuplas [(s1, e1), (s2, e2)] para concatenar partes úteis
#                         (ex: unir o tranco inicial e o tranco final do trem de pouso sem o meio longo)
#   - loop_start_sec    : Início da região de loop relativa ao trecho carregado (None = 0.0)
#   - loop_end_sec      : Fim da região de loop relativa ao trecho carregado (None = fim do trecho)
#   - loop              : True para reprodução cíclica contínua, False para one-shot
#   - volume            : Ganho individual calibrado (compensando diferenças de RMS da análise)
#   - speed             : Velocidade/pitch de reprodução em tempo real (1.0 para todos os motores)
#   - pan               : Panorâmica estéreo (-1.0 = Esq, 0.0 = Centro, +1.0 = Dir)
#   - target_duration_sec: Se definido, aplica Time-Stretch OLA em NumPy (acelera/encurta SEM alterar pitch!)
#   - lowpass_hz        : Se definido, aplica filtro passa-baixas suave no carregamento (doma agudos estridentes)
#   - fade_in_sec       : Envelope de entrada suave aplicado ao sample carregado
#   - fade_out_sec      : Envelope de saída suave aplicado ao sample carregado

CLIP_CONFIG = {
    # --------------------------------------------------------------------------
    # A. MOTOR 1 (ESQUERDO - 'A') — PERSPECTIVA INTERNA (COCKPIT - CÂMERA 2)
    # --------------------------------------------------------------------------
    "engine_1_jet_whine_int_0": {
        "path": "assets/audio/aircraft/interior/A_f14_0.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": -0.15,
    },
    "engine_1_jet_whine_int_1": {
        "path": "assets/audio/aircraft/interior/A_f14_1.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": -0.15,
    },
    "engine_1_jet_whine_int_2": {
        "path": "assets/audio/aircraft/interior/A_f14_2.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.65, "speed": 1.0, "pan": -0.15,
    },
    "engine_1_jet_whine_int_3": {
        "path": "assets/audio/aircraft/interior/A_f14_3.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.48, "speed": 1.0, "pan": -0.15,
    },

    "engine_1_comb_int_1": {
        "path": "assets/audio/aircraft/interior/A_COMB_1.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": -0.15,
    },
    "engine_1_comb_int_2": {
        "path": "assets/audio/aircraft/interior/A_COMB_2.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": -0.15,
    },
    "engine_1_comb_int_3": {
        "path": "assets/audio/aircraft/interior/A_COMB_3.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": -0.15,
    },
    "engine_1_comb_int_4": {
        "path": "assets/audio/aircraft/interior/A_COMB_4.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.78, "speed": 1.0, "pan": -0.15,
    },
    "engine_1_ab_int": {
        "path": "assets/audio/aircraft/interior/A_EFSC.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.62, "speed": 1.0, "pan": -0.15,
    },

    # --------------------------------------------------------------------------
    # B. MOTOR 2 (DIREITO - 'B') — PERSPECTIVA INTERNA (COCKPIT - CÂMERA 2)
    # --------------------------------------------------------------------------
    "engine_2_jet_whine_int_0": {
        "path": "assets/audio/aircraft/interior/B_f14_0.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": 0.15,
        "initial_phase_offset": 0.37,
    },
    "engine_2_jet_whine_int_1": {
        "path": "assets/audio/aircraft/interior/B_f14_1.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": 0.15,
        "initial_phase_offset": 0.37,
    },
    "engine_2_jet_whine_int_2": {
        "path": "assets/audio/aircraft/interior/B_f14_2.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.65, "speed": 1.0, "pan": 0.15,
        "initial_phase_offset": 0.37,
    },
    "engine_2_jet_whine_int_3": {
        "path": "assets/audio/aircraft/interior/B_f14_3.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.48, "speed": 1.0, "pan": 0.15,
        "initial_phase_offset": 0.37,
    },

    "engine_2_comb_int_1": {
        "path": "assets/audio/aircraft/interior/B_COMB_1.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": 0.15,
        "initial_phase_offset": 0.43,
    },
    "engine_2_comb_int_2": {
        "path": "assets/audio/aircraft/interior/B_COMB_2.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": 0.15,
        "initial_phase_offset": 0.43,
    },
    "engine_2_comb_int_3": {
        "path": "assets/audio/aircraft/interior/B_COMB_3.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.95, "speed": 1.0, "pan": 0.15,
        "initial_phase_offset": 0.43,
    },
    "engine_2_comb_int_4": {
        "path": "assets/audio/aircraft/interior/B_COMB_4.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.78, "speed": 1.0, "pan": 0.15,
        "initial_phase_offset": 0.43,
    },
    "engine_2_ab_int": {
        "path": "assets/audio/aircraft/interior/B_EFSC.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.62, "speed": 1.0, "pan": 0.15,
        "initial_phase_offset": 0.49,
    },

    # --------------------------------------------------------------------------
    # C. MOTOR 1 (ESQUERDO - 'X_A') — PERSPECTIVA EXTERNA (CÂMERAS 1 E 3)
    # Volume atenuado nos segmentos de alto RMS (-7 a -8.5 dBFS) para evitar clipping
    # --------------------------------------------------------------------------
    "engine_1_jet_whine_ext_0": {
        "path": "assets/audio/aircraft/exterior/X_A_f14_0.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.52, "speed": 1.0, "pan": -0.18,
    },
    "engine_1_jet_whine_ext_1": {
        "path": "assets/audio/aircraft/exterior/X_A_f14_1.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.56, "speed": 1.0, "pan": -0.18,
    },
    "engine_1_jet_whine_ext_2": {
        "path": "assets/audio/aircraft/exterior/X_A_f14_2.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.28, "speed": 1.0, "pan": -0.18,
    },
    "engine_1_jet_whine_ext_3": {
        "path": "assets/audio/aircraft/exterior/X_A_f14_3.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.28, "speed": 1.0, "pan": -0.18,
    },

    "engine_1_comb_ext_1": {
        "path": "assets/audio/aircraft/exterior/X_A_COMB_1.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.52, "speed": 1.0, "pan": -0.18,
    },
    "engine_1_comb_ext_2": {
        "path": "assets/audio/aircraft/exterior/X_A_COMB_2.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.52, "speed": 1.0, "pan": -0.18,
    },
    "engine_1_comb_ext_3": {
        "path": "assets/audio/aircraft/exterior/X_A_COMB_3.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.40, "speed": 1.0, "pan": -0.18,
    },
    "engine_1_comb_ext_4": {
        "path": "assets/audio/aircraft/exterior/X_A_COMB_4.WAV",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.68, "speed": 1.0, "pan": -0.18,
    },
    "engine_1_ab_ext": {
        "path": "assets/audio/aircraft/exterior/X_A_EFSC.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.30, "speed": 1.0, "pan": -0.18,
    },

    # --------------------------------------------------------------------------
    # D. MOTOR 2 (DIREITO - 'X_B') — PERSPECTIVA EXTERNA (CÂMERAS 1 E 3)
    # --------------------------------------------------------------------------
    "engine_2_jet_whine_ext_0": {
        "path": "assets/audio/aircraft/exterior/X_B_f14_0.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.52, "speed": 1.0, "pan": 0.18,
        "initial_phase_offset": 0.37,
    },
    "engine_2_jet_whine_ext_1": {
        "path": "assets/audio/aircraft/exterior/X_B_f14_1.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.56, "speed": 1.0, "pan": 0.18,
        "initial_phase_offset": 0.37,
    },
    "engine_2_jet_whine_ext_2": {
        "path": "assets/audio/aircraft/exterior/X_B_f14_2.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.28, "speed": 1.0, "pan": 0.18,
        "initial_phase_offset": 0.37,
    },
    "engine_2_jet_whine_ext_3": {
        "path": "assets/audio/aircraft/exterior/X_B_f14_3.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.28, "speed": 1.0, "pan": 0.18,
        "initial_phase_offset": 0.37,
    },

    "engine_2_comb_ext_1": {
        "path": "assets/audio/aircraft/exterior/X_B_COMB_1.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.52, "speed": 1.0, "pan": 0.18,
        "initial_phase_offset": 0.43,
    },
    "engine_2_comb_ext_2": {
        "path": "assets/audio/aircraft/exterior/X_B_COMB_2.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.52, "speed": 1.0, "pan": 0.18,
        "initial_phase_offset": 0.43,
    },
    "engine_2_comb_ext_3": {
        "path": "assets/audio/aircraft/exterior/X_B_COMB_3.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.40, "speed": 1.0, "pan": 0.18,
        "initial_phase_offset": 0.43,
    },
    "engine_2_comb_ext_4": {
        "path": "assets/audio/aircraft/exterior/X_B_COMB_4.WAV",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.68, "speed": 1.0, "pan": 0.18,
        "initial_phase_offset": 0.43,
    },
    "engine_2_ab_ext": {
        "path": "assets/audio/aircraft/exterior/X_B_EFSC.wav",
        "category": "engine",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.33, "speed": 1.0, "pan": 0.18,
        "initial_phase_offset": 0.49,
    },

    # --------------------------------------------------------------------------
    # E. PARTIDA, IGNIÇÃO DE COMBUSTÃO E CORTE DE MOTOR (START / COMB_START / SHUT)
    # Recortados nas janelas de melhor resposta e filtrados (lowpass_hz) para
    # remover a duração excessiva (18s..43s) e a aspereza aguda (centroide ~4.8-5.4 kHz).
    # --------------------------------------------------------------------------
    "engine_starter_int": {
        "path": "assets/audio/aircraft/events/T_f14_START.wav",
        "category": "sfx",
        "start_sec": 17.0, "end_sec": 21.5,   # Trecho encorpado da rampa de partida (sem o silêncio inicial de 1.5s)
        "loop": False, "volume": 0.42, "speed": 1.0,
        "lowpass_hz": 2200.0,
        "fade_in_sec": 0.25, "fade_out_sec": 0.45,
    },
    "engine_starter_ext": {
        "path": "assets/audio/aircraft/events/X_T_f14_START.wav",
        "category": "sfx",
        "start_sec": 11.0, "end_sec": 15.2,   # Rampa ascendente antes da saturação de -1.4 dBFS
        "loop": False, "volume": 0.24, "speed": 1.0,
        "lowpass_hz": 1950.0,
        "fade_in_sec": 0.25, "fade_out_sec": 0.45,
    },
    "engine_comb_start_int": {
        "path": "assets/audio/aircraft/events/T_COMB_START.wav",
        "category": "sfx",
        "start_sec": 2.5, "end_sec": 5.8,     # Transição grave de ignição (78 Hz -> 52 Hz)
        "loop": False, "volume": 0.45, "speed": 1.0,
        "lowpass_hz": 2400.0,
        "fade_in_sec": 0.20, "fade_out_sec": 0.40,
    },
    "engine_comb_start_ext": {
        "path": "assets/audio/aircraft/events/X_T_COMB_START.wav",
        "category": "sfx",
        "start_sec": 1.5, "end_sec": 4.8,     # Evita o pico agudo de 4.9 kHz aos 5.5-8.0s
        "loop": False, "volume": 0.22, "speed": 1.0,
        "lowpass_hz": 1850.0,
        "fade_in_sec": 0.20, "fade_out_sec": 0.40,
    },
    "engine_shutdown_int": {
        "path": "assets/audio/aircraft/events/T_COMB_SHUT.wav",
        "category": "sfx",
        "start_sec": 4.2, "end_sec": 8.6,     # Rampa descendente real de corte do motor
        "loop": False, "volume": 0.45, "speed": 1.0,
        "lowpass_hz": 2300.0,
        "fade_in_sec": 0.18, "fade_out_sec": 0.45,
    },
    "engine_shutdown_ext": {
        "path": "assets/audio/aircraft/events/X_T_f14_SHUT.wav",
        "category": "sfx",
        "start_sec": 5.5, "end_sec": 11.0,    # Corta o pico estridente de 5.4 kHz (0-3.5s) e a cauda muda (12-18.4s)
        "loop": False, "volume": 0.25, "speed": 1.0,
        "lowpass_hz": 1950.0,
        "fade_in_sec": 0.20, "fade_out_sec": 0.50,
    },

    # --------------------------------------------------------------------------
    # F. TREM DE POUSO, TOQUE NO CONVÉS (UNIFICADO) E ROLAGEM NO SOLO (UNIFICADA)
    # --------------------------------------------------------------------------
    # GEARDOWN e gearup originais têm 8.75s (com 6s de zumbido constante no meio),
    # enquanto a animação do F-14 dura ~1.2s. Usamos 'segments_sec' para unir o
    # destravamento hidráulico inicial (0.0..1.5s) ao travamento final (7.4..8.5s)
    # e 'target_duration_sec' (Time-Stretch OLA sem alterar o pitch!) para caber
    # exatamente na animação mecânica das pernas do trem de pouso!
    "gear_down": {
        "path": "assets/audio/aircraft/events/GEARDOWN.wav",
        "category": "sfx",
        "segments_sec": [(0.0, 1.50), (7.40, 8.55)],
        "target_duration_sec": 1.22,
        "loop": False, "volume": 0.72, "speed": 1.0,
        "fade_in_sec": 0.02, "fade_out_sec": 0.08,
    },
    "gear_up": {
        "path": "assets/audio/aircraft/events/GEARUP.wav",
        "category": "sfx",
        "segments_sec": [(0.0, 1.50), (7.40, 8.55)],
        "target_duration_sec": 1.22,
        "loop": False, "volume": 0.72, "speed": 1.0,
        "fade_in_sec": 0.02, "fade_out_sec": 0.08,
    },

    # Contato das rodas com o solo simplificado em um único arquivo (touchc.wav)
    "touchdown": {
        "path": "assets/audio/aircraft/events/touchc.wav",
        "category": "sfx",
        "start_sec": None, "end_sec": None,
        "loop": False, "volume": 0.75, "speed": 1.0,
        "fade_in_sec": 0.005, "fade_out_sec": 0.03,
    },

    # Rolagem das rodas no convés simplificada em um único arquivo (roll2.wav)
    # Nota: RMS alto (-5.86 dBFS), por isso volume base calibrado em 0.36
    "ground_roll": {
        "path": "assets/audio/aircraft/events/roll2.wav",
        "category": "sfx",
        "start_sec": 0.15, "end_sec": 3.95,
        "loop": True, "volume": 0.36, "speed": 1.0,
    },

    # Impacto / Explosão em colisão sólida e aquática (boom_crash.wav: 1.80s, 48kHz, RMS -15.2 dBFS, Peak 0.0 dBFS)
    "crash_boom": {
        "path": "assets/audio/aircraft/events/boom_crash.wav",
        "category": "sfx",
        "start_sec": 0.0, "end_sec": 1.80,
        "loop": False, "volume": 0.78, "speed": 1.0,
        "fade_in_sec": 0.005, "fade_out_sec": 0.12,
    },

    # Colisão na água (water_splash.wav: 2.04s, 48kHz, RMS -25.9 dBFS, Peak -0.7 dBFS, centroide 4.3 kHz)
    "crash_water_splash": {
        "path": "assets/audio/aircraft/events/water_splash.wav",
        "category": "sfx",
        "start_sec": 0.0, "end_sec": 1.95,
        "loop": False, "volume": 0.95, "speed": 1.0,
        "fade_in_sec": 0.005, "fade_out_sec": 0.15,
    },

    # Atuador hidráulico dos Flaps (FLAPS.wav: 3.88s, 44.1kHz Mono MS_ADPCM, Peak -1.3 dBFS, RMS -12.8 dBFS)
    # Volume calibrado em 0.40 para compensar o RMS forte (-12.8 dBFS) sem mascarar os motores;
    # opera em loop contínuo controlado por target_gain enquanto os flaps estiverem em movimento.
    "flaps": {
        "path": "assets/audio/aircraft/events/FLAPS.wav",
        "category": "sfx",
        "start_sec": 0.08, "end_sec": 3.55,
        "loop": True, "volume": 0.40, "speed": 1.0,
        "fade_in_sec": 0.03, "fade_out_sec": 0.06,
    },

    # Atuador hidráulico dos Split Air Brakes (reaproveita FLAPS.wav com canal independente e pitch 1.18x
    # para diferenciar sutilmente o atuador menor do Beaver Tail e permitir uso simultâneo com os flaps)
    "airbrake": {
        "path": "assets/audio/aircraft/events/FLAPS.wav",
        "category": "sfx",
        "start_sec": 0.12, "end_sec": 3.45,
        "loop": True, "volume": 0.36, "speed": 1.18,
        "fade_in_sec": 0.025, "fade_out_sec": 0.05,
    },

    # --------------------------------------------------------------------------
    # G. SONS AMBIENTES (APENAS CENAS 1 E 2; CENA 3 E MENU NÃO TÊM SOM AMBIENTE)
    # Carrega janela estável de 45s com decimação direta (96kHz/192kHz -> 44.1kHz)
    # para inicialização instantânea e baixo consumo de RAM.
    # --------------------------------------------------------------------------
    "ambience_scene1_ocean": {
        "path": "assets/audio/ambience/scene1.wav",
        "category": "ambience",
        "start_sec": 2.0, "end_sec": 47.0,
        "loop": True, "volume": 1.40, "speed": 1.0,   # Compensa RMS de -36.1 dBFS
    },
    "ambience_scene2_canyon": {
        "path": "assets/audio/ambience/scene2.wav",
        "category": "ambience",
        "start_sec": 2.0, "end_sec": 47.0,
        "loop": True, "volume": 0.52, "speed": 1.0,   # Compensa RMS forte de -21.1 dBFS
    },

    # --------------------------------------------------------------------------
    # H. TRILHAS MUSICAIS (IDENTIFICADORES LÓGICOS PARA VOO E MENU/INSPEÇÃO)
    # --------------------------------------------------------------------------
    "music_flight": {
        "path": "assets/audio/music/flight.mp3",
        "category": "music",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.75, "speed": 1.0,
        "optional": True,
    },
    "music_menu_inspection": {
        "path": "assets/audio/music/menu_inspection.mp3",
        "category": "music",
        "start_sec": None, "end_sec": None,
        "loop": True, "volume": 0.75, "speed": 1.0,
        "optional": True,
    },

    # --------------------------------------------------------------------------
    # I. SONS DE INTERFACE E NAVEGAÇÃO DE MENU (assets/audio/menu/)
    # Volumes calibrados pela análise espectral/RMS (analise_audio_2.md):
    #   - menu1.wav: 0.888s, 48kHz Mono,   Peak   0.0 dBFS, RMS -16.6 dBFS -> vol 0.58
    #   - menu2.wav: 0.078s, 44.1kHz Est., Peak  -4.0 dBFS, RMS -23.3 dBFS -> vol 0.72
    #   - menu3.wav: 0.836s, 44.1kHz Est., Peak -10.1 dBFS, RMS -31.1 dBFS -> vol 1.15
    # --------------------------------------------------------------------------
    "menu_1": {
        "path": "assets/audio/menu/menu1.wav",
        "category": "sfx",
        "start_sec": None, "end_sec": None,
        "loop": False, "volume": 0.58, "speed": 1.0,
        "fade_in_sec": 0.004, "fade_out_sec": 0.04,
    },
    "menu_2": {
        "path": "assets/audio/menu/menu2.wav",
        "category": "sfx",
        "start_sec": None, "end_sec": None,
        "loop": False, "volume": 0.72, "speed": 1.0,
        "fade_in_sec": 0.002, "fade_out_sec": 0.01,
    },
    "menu_3": {
        "path": "assets/audio/menu/menu3.wav",
        "category": "sfx",
        "start_sec": None, "end_sec": None,
        "loop": False, "volume": 1.15, "speed": 1.0,
        "fade_in_sec": 0.004, "fade_out_sec": 0.04,
    },

}