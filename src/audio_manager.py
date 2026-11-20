"""
================================================================================
TopGraphics | audio_manager.py
Gerenciador e Mixer de Áudio em Tempo Real (Independente do Renderer OpenGL):
  - Único fluxo contínuo sounddevice.OutputStream com mixagem em NumPy.
  - Carregamento via soundfile (suporte a PCM_16, PCM_24, PCM_U8 e MS_ADPCM).
  - Pré-processamento em RAM: recorte (start_sec/end_sec), concatenação de seções
    (segments_sec), remoção de DC offset, Time-Stretch OLA sem alterar pitch
    (para caber GEARDOWN/gearup na animação do F-14), filtro passa-baixas
    (para suavizar start/shut agudos) e crossfade de loop sem cliques.
  - Seleção automática de perspectiva Interna (Câmera 2) vs Externa (Câmeras 1 e 3)
    com crossfade suave, camadas JET_WHINE + COMBUSTION + EFSC (Afterburner)
    para os 2 motores (A e B), Touchdown e Ground Roll unificados, e Ambientes 1 e 2.
================================================================================
"""

import os
import sys
import math
import time
import threading
import numpy as np

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    sd = None
    SOUNDDEVICE_AVAILABLE = False

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    sf = None
    SOUNDFILE_AVAILABLE = False

from audio_config import (
    OUTPUT_SAMPLE_RATE,
    OUTPUT_CHANNELS,
    STREAM_BLOCKSIZE,
    DEFAULT_VOLUMES,
    MUSIC_CROSSFADE_SECONDS,
    AMBIENCE_CROSSFADE_SECONDS,
    PERSPECTIVE_CROSSFADE_SECONDS,
    ENGINE_SMOOTH_TIME_SECONDS,
    AFTERBURNER_FADE_SECONDS,
    LOOP_CROSSFADE_SECONDS,
    JET_WHINE_THROTTLE_ENVELOPES,
    COMBUSTION_THROTTLE_ENVELOPES,
    GROUND_ROLL_MIN_SPEED,
    GROUND_ROLL_FULL_SPEED,
    GROUND_ROLL_MIN_RATE,
    GROUND_ROLL_MAX_RATE,
    SCENE_AUDIO_MAP,
    MENU_SFX_MAP,
    CLIP_CONFIG,
)


# ==============================================================================
# 1. UTILITÁRIOS DE DSP EM NUMPY (RESAMPLE, FILTRO PASSA-BAIXAS, TIME-STRETCH OLA)
# ==============================================================================

def _resample_audio(data, src_sr, dst_sr):
    """
    Converte a taxa de amostragem de 'data' (shape: (N, C)) de src_sr para dst_sr.
    Usa decimação inteira rápida quando possível ou interpolação linear vetorizada.
    """
    if src_sr == dst_sr or len(data) == 0:
        return data

    # Caso especial: decimação inteira exata (ex: 96000 -> 48000 ou 44100 -> 22050)
    if src_sr > dst_sr and (src_sr % dst_sr == 0):
        step = src_sr // dst_sr
        return np.ascontiguousarray(data[::step], dtype=np.float32)

    duration = len(data) / float(src_sr)
    dst_len = max(1, int(round(duration * dst_sr)))
    src_indices = np.linspace(0.0, len(data) - 1, dst_len, dtype=np.float32)
    idx_floor = np.floor(src_indices).astype(np.int32)
    idx_ceil = np.minimum(idx_floor + 1, len(data) - 1)
    frac = (src_indices - idx_floor)[:, None]

    out = data[idx_floor] * (1.0 - frac) + data[idx_ceil] * frac
    return np.ascontiguousarray(out, dtype=np.float32)


def _apply_one_pole_lowpass(data, cutoff_hz, sample_rate):
    """
    Aplica filtro passa-baixas RC de 1 polo (em cascata dupla para 12 dB/oitava)
    para suavizar arquivos de partida/desligamento muito agudos sem alterar duração.
    """
    if cutoff_hz is None or cutoff_hz <= 0.0 or len(data) == 0:
        return data

    rc = 1.0 / (2.0 * math.pi * float(cutoff_hz))
    dt = 1.0 / float(sample_rate)
    alpha = float(dt / (rc + dt))

    out = data.copy()
    # Duas passagens leves para atenuação suave de agudos estridentes
    for _ in range(2):
        for i in range(1, len(out)):
            out[i] = out[i - 1] + alpha * (out[i] - out[i - 1])
    return out


def _time_stretch_ola(data, stretch_rate, sample_rate, window_ms=36.0):
    """
    Altera a duração do áudio (stretch_rate < 1.0 acelera/encurta; > 1.0 alonga)
    SEM alterar o pitch, usando Overlap-Add (OLA) com janela de Hann em NumPy.
    Ideal para encaixar GEARDOWN.wav e gearup.wav no tempo exato da animação do F-14.
    """
    if stretch_rate is None or abs(stretch_rate - 1.0) < 1e-3 or len(data) == 0:
        return data

    n_samples, n_channels = data.shape
    win_len = int(max(256, round((window_ms / 1000.0) * sample_rate)))
    if win_len % 2 != 0:
        win_len += 1
    if n_samples <= win_len:
        return data

    hop_syn = win_len // 2
    hop_ana = max(1, int(round(hop_syn / float(stretch_rate))))

    out_len = int(round(n_samples * float(stretch_rate))) + win_len
    out = np.zeros((out_len, n_channels), dtype=np.float32)
    norm = np.zeros((out_len, 1), dtype=np.float32)
    window = np.hanning(win_len).astype(np.float32)[:, None]

    ana_pos = 0
    syn_pos = 0
    while ana_pos + win_len <= n_samples and syn_pos + win_len <= out_len:
        frame = data[ana_pos:ana_pos + win_len] * window
        out[syn_pos:syn_pos + win_len] += frame
        norm[syn_pos:syn_pos + win_len] += window
        ana_pos += hop_ana
        syn_pos += hop_syn

    valid_len = max(1, syn_pos + hop_syn)
    out = out[:valid_len]
    norm = norm[:valid_len]
    mask = norm[:, 0] > 1e-4
    out[mask] /= norm[mask]
    return np.ascontiguousarray(out, dtype=np.float32)


def _crossfade_concat_segments(segments_list, sample_rate, xfade_sec=0.03):
    """
    Concatena múltiplos trechos recortados de um mesmo arquivo aplicando
    crossfade curto entre eles para evitar cliques na emenda.
    """
    if not segments_list:
        return np.zeros((0, OUTPUT_CHANNELS), dtype=np.float32)
    if len(segments_list) == 1:
        return segments_list[0]

    xfade_len = int(round(xfade_sec * sample_rate))
    result = segments_list[0]
    for nxt in segments_list[1:]:
        eff_xfade = min(xfade_len, len(result) // 3, len(nxt) // 3)
        if eff_xfade > 4:
            fade_out = np.linspace(1.0, 0.0, eff_xfade, dtype=np.float32)[:, None]
            fade_in = np.linspace(0.0, 1.0, eff_xfade, dtype=np.float32)[:, None]
            overlap = result[-eff_xfade:] * fade_out + nxt[:eff_xfade] * fade_in
            result = np.concatenate([result[:-eff_xfade], overlap, nxt[eff_xfade:]], axis=0)
        else:
            result = np.concatenate([result, nxt], axis=0)
    return np.ascontiguousarray(result, dtype=np.float32)


def _apply_seamless_loop_crossfade(data, sample_rate, xfade_sec=LOOP_CROSSFADE_SECONDS):
    """
    Suaviza a transição entre o final e o início de um buffer em loop para eliminar
    qualquer salto de fase/amplitude (clique) no ponto de repetição.
    """
    xfade_len = int(round(xfade_sec * sample_rate))
    if xfade_len <= 4 or len(data) < xfade_len * 4:
        return data

    out = data.copy()
    t = np.linspace(0.0, 1.0, xfade_len, dtype=np.float32)[:, None]
    # Mistura suavemente a cauda final com o início e encurta a cauda redundante
    head = out[:xfade_len]
    tail = out[-xfade_len:]
    out[:xfade_len] = tail * (1.0 - t) + head * t
    return np.ascontiguousarray(out[:-xfade_len], dtype=np.float32)


def _evaluate_trapezoid_envelope(x, x0, x1, x2, x3, peak_gain):
    """
    Avalia curva trapezoidal suave (cosine-smoothed) para um valor normalizado x (throttle).
    """
    if x <= x0 or x >= x3:
        return 0.0
    if x1 <= x <= x2:
        return peak_gain
    if x < x1:
        u = (x - x0) / max(1e-5, (x1 - x0))
        return peak_gain * 0.5 * (1.0 - math.cos(math.pi * u))
    u = (x3 - x) / max(1e-5, (x3 - x2))
    return peak_gain * 0.5 * (1.0 - math.cos(math.pi * u))


# ==============================================================================
# 2. ESTRUTURA DE VOZ / CANAL DE REPRODUÇÃO NO MIXER
# ==============================================================================

class AudioVoice:
    """
    Representa um clip carregado na memória e seu estado de reprodução em tempo real
    dentro do OutputStream.
    """
    def __init__(self, name, data, config):
        self.name = name
        self.data = data  # shape (N, 2), float32 na taxa OUTPUT_SAMPLE_RATE
        self.num_frames = len(data)
        self.category = config.get("category", "sfx")
        self.loop = bool(config.get("loop", False))
        self.base_volume = float(config.get("volume", 1.0))
        self.speed = float(config.get("speed", 1.0))
        self.pan = float(config.get("pan", 0.0))

        # Limites de loop em frames (após recorte e resample)
        loop_start_sec = config.get("loop_start_sec")
        loop_end_sec = config.get("loop_end_sec")
        self.loop_start = int(round(loop_start_sec * OUTPUT_SAMPLE_RATE)) if loop_start_sec else 0
        self.loop_end = int(round(loop_end_sec * OUTPUT_SAMPLE_RATE)) if loop_end_sec else self.num_frames
        self.loop_start = max(0, min(self.loop_start, max(0, self.num_frames - 2)))
        self.loop_end = max(self.loop_start + 1, min(self.loop_end, self.num_frames))

        # Offset de fase inicial opcional (evita soma construtiva idêntica entre Motor 1 e Motor 2)
        phase_offset = float(config.get("initial_phase_offset", 0.0))
        self.cursor = float(int(phase_offset * self.num_frames) % max(1, self.num_frames))

        self.playing = False
        self.current_gain = 0.0
        self.target_gain = 0.0
        self.fade_rate = 8.0  # Ganho por segundo para rampa suave


# ==============================================================================
# 3. GERENCIADOR PRINCIPAL DE ÁUDIO (AUDIOMANAGER)
# ==============================================================================

class AudioManager:
    """
    Gerencia todas as vozes de música, motores (internos/externos), ambientes e SFX
    em um único OutputStream não-bloqueante.
    """
    def __init__(self, initial_scene=1, initial_camera_mode=1):
        self.scene_mode = initial_scene
        self.camera_mode = initial_camera_mode

        self.volumes = dict(DEFAULT_VOLUMES)
        self.muted = False
        self.music_muted = False

        self.voices = {}
        self._file_index = {}
        self._stream = None
        self._running = False
        self._lock = threading.Lock()

        # Estados rastreados para disparo único de eventos de transição
        self._prev_on_ground = True
        self._prev_crashed = False
        self._prev_throttle = 0.0
        self._last_start_sfx_time = -10.0
        self._active_music_name = None
        self._active_ambience_name = None

        self._build_asset_file_index()
        self._load_all_configured_clips()

    # --------------------------------------------------------------------------
    # INDEXAÇÃO E CARREGAMENTO DE ARQUIVOS WAV
    # --------------------------------------------------------------------------

    def _build_asset_file_index(self):
        """
        Indexa recursivamente todos os arquivos .wav/.ogg/.flac dentro de 'assets/'
        para localizá-los instantaneamente mesmo que estejam em subpastas diferentes
        ou com capitalização distinta (ex: GEARDOWN.wav vs geardown.wav).
        """
        module_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(module_dir)
        search_roots = [
            os.path.join(project_root, "assets"),
            os.path.join(module_dir, "assets"),
            os.path.join(os.getcwd(), "assets"),
        ]
        for root_dir in search_roots:
            if not os.path.isdir(root_dir):
                continue
            for dirpath, _, filenames in os.walk(root_dir):
                for fname in filenames:
                    if fname.lower().endswith((".wav", ".ogg", ".flac", ".mp3")):
                        full_p = os.path.join(dirpath, fname)
                        key_exact = fname.lower()
                        key_stem = os.path.splitext(fname)[0].lower()
                        self._file_index.setdefault(key_exact, full_p)
                        self._file_index.setdefault(key_stem, full_p)

    def _resolve_audio_path(self, configured_path):
        """Localiza o arquivo de áudio pelo caminho configurado ou pelo índice de 'assets/'."""
        if not configured_path:
            return None

        module_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(module_dir)

        for base in (project_root, module_dir, os.getcwd()):
            candidate = os.path.join(base, configured_path)
            if os.path.isfile(candidate):
                return candidate

        basename_lower = os.path.basename(configured_path).lower()
        stem_lower = os.path.splitext(basename_lower)[0]
        if basename_lower in self._file_index:
            return self._file_index[basename_lower]
        if stem_lower in self._file_index:
            return self._file_index[stem_lower]
        return None

    def _read_wav_segment(self, filepath, start_sec=None, end_sec=None):
        """
        Lê apenas o intervalo [start_sec, end_sec] de um arquivo de áudio usando soundfile,
        retornando (array_float32_stereo, samplerate).
        """
        if not SOUNDFILE_AVAILABLE:
            return None, OUTPUT_SAMPLE_RATE

        with sf.SoundFile(filepath, "r") as f:
            sr = f.samplerate
            total_frames = len(f)
            start_frame = int(round(start_sec * sr)) if start_sec is not None else 0
            stop_frame = int(round(end_sec * sr)) if end_sec is not None else total_frames

            start_frame = max(0, min(start_frame, max(0, total_frames - 1)))
            stop_frame = max(start_frame + 1, min(stop_frame, total_frames))

            f.seek(start_frame)
            frames_to_read = stop_frame - start_frame
            data = f.read(frames_to_read, dtype="float32", always_2d=True)

        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]

        return data, sr

    def _load_and_prepare_clip(self, name, cfg):
        """
        Carrega um clip do disco e aplica todos os tratamentos configurados:
          1. Leitura parcial por 'start_sec'/'end_sec' ou múltiplos 'segments_sec'.
          2. Remoção de DC offset (corrige touchc.wav etc.).
          3. Resample para OUTPUT_SAMPLE_RATE.
          4. Filtro passa-baixas opcional ('lowpass_hz') para domar agudos de start/shut.
          5. Time-Stretch OLA sem alterar pitch ('target_duration_sec' / 'time_stretch').
          6. Envelopes fade_in_sec / fade_out_sec ou crossfade de loop contínuo.
        """
        filepath = self._resolve_audio_path(cfg.get("path"))
        if filepath is None:
            for alt_p in cfg.get("alt_paths", ()):
                filepath = self._resolve_audio_path(alt_p)
                if filepath is not None:
                    break
        if filepath is None:
            if not cfg.get("optional", False):
                print(f"[Áudio] Aviso: arquivo não encontrado para '{name}' ({cfg.get('path')}).")
            return None

        try:
            segments_sec = cfg.get("segments_sec")
            if segments_sec:
                seg_arrays = []
                sr = OUTPUT_SAMPLE_RATE
                for s_sec, e_sec in segments_sec:
                    seg_data, sr = self._read_wav_segment(filepath, s_sec, e_sec)
                    if seg_data is not None and len(seg_data) > 0:
                        seg_arrays.append(seg_data)
                if not seg_arrays:
                    return None
                data = _crossfade_concat_segments(seg_arrays, sr, xfade_sec=0.025)
            else:
                data, sr = self._read_wav_segment(
                    filepath, cfg.get("start_sec"), cfg.get("end_sec")
                )
                if data is None or len(data) == 0:
                    return None

            # Remove DC offset (ex: touchc.wav possui DC offset de -0.23)
            dc_offset = np.mean(data, axis=0, keepdims=True)
            if np.max(np.abs(dc_offset)) > 1e-3:
                data = data - dc_offset

            # Converte para a taxa de amostragem única do mixer (OUTPUT_SAMPLE_RATE)
            if sr != OUTPUT_SAMPLE_RATE:
                data = _resample_audio(data, sr, OUTPUT_SAMPLE_RATE)

            # Filtro passa-baixas opcional para suavizar arquivos agudos (start/shut)
            lowpass_hz = cfg.get("lowpass_hz")
            if lowpass_hz is not None:
                data = _apply_one_pole_lowpass(data, lowpass_hz, OUTPUT_SAMPLE_RATE)

            # Time-Stretch OLA preservando pitch (ex: encaixar GEARDOWN/gearup em 1.22s)
            target_dur = cfg.get("target_duration_sec")
            stretch_factor = cfg.get("time_stretch")
            if target_dur is not None and len(data) > 0:
                current_dur = len(data) / float(OUTPUT_SAMPLE_RATE)
                if current_dur > 0.05:
                    stretch_factor = float(target_dur) / current_dur
            if stretch_factor is not None and abs(stretch_factor - 1.0) > 0.02:
                data = _time_stretch_ola(data, stretch_factor, OUTPUT_SAMPLE_RATE)

            # Envelopes de entrada e saída
            fade_in_sec = cfg.get("fade_in_sec")
            if fade_in_sec and fade_in_sec > 0.0:
                n_in = min(len(data), int(round(fade_in_sec * OUTPUT_SAMPLE_RATE)))
                if n_in > 1:
                    data[:n_in] *= np.linspace(0.0, 1.0, n_in, dtype=np.float32)[:, None]

            fade_out_sec = cfg.get("fade_out_sec")
            if fade_out_sec and fade_out_sec > 0.0:
                n_out = min(len(data), int(round(fade_out_sec * OUTPUT_SAMPLE_RATE)))
                if n_out > 1:
                    data[-n_out:] *= np.linspace(1.0, 0.0, n_out, dtype=np.float32)[:, None]

            # Crossfade de fronteira para loops contínuos perfeitos
            if cfg.get("loop", False):
                data = _apply_seamless_loop_crossfade(data, OUTPUT_SAMPLE_RATE)

            return AudioVoice(name, np.ascontiguousarray(data, dtype=np.float32), cfg)

        except Exception as exc:
            print(f"[Áudio] Erro ao processar clip '{name}': {exc}")
            return None

    def _load_all_configured_clips(self):
        """Carrega todos os clips definidos em CLIP_CONFIG antes de iniciar o stream."""
        if not SOUNDFILE_AVAILABLE:
            print("[Áudio] Biblioteca 'soundfile' não instalada (pip install soundfile). Áudio desativado.")
            return

        loaded_count = 0
        for name, cfg in CLIP_CONFIG.items():
            voice = self._load_and_prepare_clip(name, cfg)
            if voice is not None:
                self.voices[name] = voice
                loaded_count += 1

        print(f"[Áudio] {loaded_count}/{len(CLIP_CONFIG)} clips preparados em RAM ({OUTPUT_SAMPLE_RATE} Hz Estéreo).")

    # --------------------------------------------------------------------------
    # CALLBACK DE TEMPO REAL DO SOUNDDEVICE (MIXER CENTRAL)
    # --------------------------------------------------------------------------

    def _audio_callback(self, outdata, frames, time_info, status):
        """
        Callback executado em thread de alta prioridade pelo PortAudio/sounddevice.
        Não realiza I/O nem alocações pesadas; apenas mistura os buffers ativos.
        """
        outdata.fill(0.0)
        if self.muted or not self._running:
            return

        master_vol = self.volumes.get("master", 0.85)
        if master_vol <= 1e-4:
            return

        dt_block = frames / float(OUTPUT_SAMPLE_RATE)

        for voice in self.voices.values():
            if not voice.playing and voice.current_gain <= 1e-4 and voice.target_gain <= 1e-4:
                continue

            # Atualiza rampa suave de ganho por bloco (evita cliques em trocas de câmera/cena)
            if abs(voice.current_gain - voice.target_gain) > 1e-4:
                max_step = voice.fade_rate * dt_block
                if voice.current_gain < voice.target_gain:
                    voice.current_gain = min(voice.target_gain, voice.current_gain + max_step)
                else:
                    voice.current_gain = max(voice.target_gain, voice.current_gain - max_step)
            else:
                voice.current_gain = voice.target_gain

            if voice.current_gain <= 1e-4 and voice.target_gain <= 1e-4:
                if not voice.loop:
                    voice.playing = False
                continue

            cat = voice.category
            if cat == "music" and self.music_muted:
                continue

            cat_vol = self.volumes.get(cat, 1.0)
            eff_gain = master_vol * cat_vol * voice.base_volume * voice.current_gain
            if eff_gain <= 1e-4 or voice.num_frames < 2:
                continue

            # Ganho estéreo com lei de potência constante (Pan Left / Right)
            pan = voice.pan
            angle = (pan + 1.0) * (math.pi * 0.25)
            gain_l = eff_gain * math.cos(angle) * 1.4142
            gain_r = eff_gain * math.sin(angle) * 1.4142

            speed = voice.speed
            data = voice.data
            l_start = voice.loop_start
            l_end = voice.loop_end
            l_span = max(1, l_end - l_start)

            # Caminho rápido (99% dos clips: motores, ambientes e SFX em velocidade 1.0x)
            if abs(speed - 1.0) < 1e-3:
                cur_int = int(voice.cursor)
                rem = frames
                out_offset = 0

                while rem > 0:
                    if voice.loop:
                        if cur_int >= l_end or cur_int < l_start:
                            cur_int = l_start + ((cur_int - l_start) % l_span)
                        avail = l_end - cur_int
                        chunk = min(rem, avail)
                        seg = data[cur_int:cur_int + chunk]
                        outdata[out_offset:out_offset + chunk, 0] += seg[:, 0] * gain_l
                        outdata[out_offset:out_offset + chunk, 1] += seg[:, 1] * gain_r
                        cur_int += chunk
                        if cur_int >= l_end:
                            cur_int = l_start
                        out_offset += chunk
                        rem -= chunk
                    else:
                        if cur_int >= voice.num_frames:
                            voice.playing = False
                            voice.current_gain = 0.0
                            voice.target_gain = 0.0
                            break
                        avail = voice.num_frames - cur_int
                        chunk = min(rem, avail)
                        seg = data[cur_int:cur_int + chunk]
                        outdata[out_offset:out_offset + chunk, 0] += seg[:, 0] * gain_l
                        outdata[out_offset:out_offset + chunk, 1] += seg[:, 1] * gain_r
                        cur_int += chunk
                        out_offset += chunk
                        rem -= chunk
                        if cur_int >= voice.num_frames:
                            voice.playing = False
                            voice.current_gain = 0.0
                            voice.target_gain = 0.0
                            break

                voice.cursor = float(cur_int)

            # Caminho interpolado para velocidade variável (ex: ground_roll 0.85x..1.10x)
            else:
                positions = voice.cursor + np.arange(frames, dtype=np.float32) * speed
                if voice.loop:
                    wrapped = l_start + np.mod(positions - l_start, float(l_span))
                    idx0 = wrapped.astype(np.int32)
                    idx1 = l_start + ((idx0 + 1 - l_start) % l_span)
                    frac = (wrapped - idx0)[:, None]
                    seg = data[idx0] * (1.0 - frac) + data[idx1] * frac
                    outdata[:, 0] += seg[:, 0] * gain_l
                    outdata[:, 1] += seg[:, 1] * gain_r
                    voice.cursor = float(l_start + ((voice.cursor + frames * speed - l_start) % l_span))
                else:
                    valid_mask = positions < (voice.num_frames - 1)
                    if np.any(valid_mask):
                        valid_pos = positions[valid_mask]
                        idx0 = valid_pos.astype(np.int32)
                        idx1 = np.minimum(idx0 + 1, voice.num_frames - 1)
                        frac = (valid_pos - idx0)[:, None]
                        seg = data[idx0] * (1.0 - frac) + data[idx1] * frac
                        n_val = len(valid_pos)
                        outdata[:n_val, 0] += seg[:, 0] * gain_l
                        outdata[:n_val, 1] += seg[:, 1] * gain_r
                    voice.cursor += frames * speed
                    if voice.cursor >= voice.num_frames - 1:
                        voice.playing = False
                        voice.current_gain = 0.0
                        voice.target_gain = 0.0

        # Soft-clipper (tanh) de proteção contra saturação quando todas as camadas somam
        np.tanh(outdata, out=outdata)

    # --------------------------------------------------------------------------
    # CONTROLE DE CICLO DE VIDA DO STREAM (START / CLOSE)
    # --------------------------------------------------------------------------

    def start(self):
        """Inicia o OutputStream contínuo do sounddevice e configura a cena inicial."""
        if not SOUNDDEVICE_AVAILABLE or not SOUNDFILE_AVAILABLE:
            print("[Áudio] 'sounddevice' ou 'soundfile' ausente. Simulador rodará sem som.")
            return

        if self._running:
            return

        try:
            self._running = True
            # Ativa os loops contínuos de motor e ground_roll com ganho inicial zero
            for name, voice in self.voices.items():
                if voice.category == "engine" or name == "ground_roll":
                    voice.playing = True
                    voice.current_gain = 0.0
                    voice.target_gain = 0.0

            self._stream = sd.OutputStream(
                samplerate=OUTPUT_SAMPLE_RATE,
                channels=OUTPUT_CHANNELS,
                blocksize=STREAM_BLOCKSIZE,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
            self.set_scene(self.scene_mode, force_init=True)
            print("[Áudio] Fluxo OutputStream iniciado com sucesso.")
        except Exception as exc:
            self._running = False
            self._stream = None
            print(f"[Áudio] Aviso: não foi possível abrir dispositivo de áudio ({exc}).")

    def close(self):
        """Encerra o OutputStream de forma limpa e segura ao fechar a janela GLFW."""
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        print("[Áudio] Fluxo de áudio encerrado.")

    # --------------------------------------------------------------------------
    # TRANSIÇÕES DE CENÁRIO, AMBIENTE, MÚSICA E CÂMERA
    # --------------------------------------------------------------------------

    def set_scene(self, scene_mode, force_init=False):
        """
        Atualiza música, som ambiente e estado dos motores conforme o cenário:
          - Cena 1: Ambiente Oceano (WATRWave...) + Música Flight + Motores ativos
          - Cena 2: Ambiente Cânion (WINDDsgn...) + Música Flight + Motores ativos
          - Cena 3: Sem som ambiente + Música Menu/Inspeção + Motores em fade-out
        """
        if not force_init and scene_mode == self.scene_mode:
            return

        self.scene_mode = scene_mode
        scene_cfg = SCENE_AUDIO_MAP.get(scene_mode, SCENE_AUDIO_MAP[3])

        # 1. Atualiza camada de Ambiente (exclusiva para Cenas 1 e 2)
        target_amb = scene_cfg.get("ambience")
        if target_amb != self._active_ambience_name:
            # Faz fade-out no ambiente anterior
            if self._active_ambience_name and self._active_ambience_name in self.voices:
                old_v = self.voices[self._active_ambience_name]
                old_v.fade_rate = 1.0 / max(0.05, AMBIENCE_CROSSFADE_SECONDS)
                old_v.target_gain = 0.0

            # Faz fade-in no novo ambiente (se houver; Cena 3 = None)
            if target_amb and target_amb in self.voices:
                new_v = self.voices[target_amb]
                new_v.playing = True
                new_v.fade_rate = 1.0 / max(0.05, AMBIENCE_CROSSFADE_SECONDS)
                new_v.target_gain = 1.0

            self._active_ambience_name = target_amb

        # 2. Atualiza contexto de Música (mantém 'music_flight' contínua entre Cena 1 e Cena 2)
        target_music = scene_cfg.get("music")
        self.set_music_context(target_music)

        # 3. Se entrou no Menu ou Cena 3 (Inspeção), silencia suavemente motores e rolagem de solo
        if not scene_cfg.get("engines_active", False):
            self._fade_out_flight_loops()

    def sync_aircraft_state(self, on_ground, throttle, crashed=False):
        """
        Sincroniza o estado anterior da aeronave após reset/troca de cenário para evitar
        disparo falso de 'touchdown' ou 'engine_comb_start' no primeiro frame do spawn.
        """
        self._prev_on_ground = bool(on_ground)
        self._prev_throttle = float(throttle)
        self._prev_crashed = bool(crashed)

    def set_music_context(self, music_clip_name):
        """Alterna a trilha musical ativa com crossfade suave, sem reiniciar se já for a mesma."""
        if music_clip_name == self._active_music_name:
            return

        if self._active_music_name and self._active_music_name in self.voices:
            old_m = self.voices[self._active_music_name]
            old_m.fade_rate = 1.0 / max(0.1, MUSIC_CROSSFADE_SECONDS)
            old_m.target_gain = 0.0

        if music_clip_name and music_clip_name in self.voices:
            new_m = self.voices[music_clip_name]
            if not new_m.playing or new_m.current_gain <= 1e-3:
                new_m.cursor = 0.0
            new_m.playing = True
            new_m.fade_rate = 1.0 / max(0.1, MUSIC_CROSSFADE_SECONDS)
            new_m.target_gain = 1.0

        self._active_music_name = music_clip_name

    def set_camera_mode(self, camera_mode):
        """
        Define a perspectiva de áudio conforme a câmera ativa:
          - Câmeras 1 (Chase) e 3 (Orbital): Perspectiva Externa (arquivos X_...)
          - Câmera 2 (Cockpit): Perspectiva Interna (arquivos sem X_)
        """
        self.camera_mode = camera_mode

    def _fade_out_flight_loops(self):
        """Coloca todos os loops de motor, afterburner e solo em rampa de fade-out."""
        for name, voice in self.voices.items():
            if voice.category == "engine" or name == "ground_roll":
                voice.fade_rate = 4.5
                voice.target_gain = 0.0

    # --------------------------------------------------------------------------
    # ATUALIZAÇÃO CONTÍNUA POR FRAME (CHAMADA NO LOOP DO MAIN.PY)
    # --------------------------------------------------------------------------

    def update(
        self,
        dt,
        throttle,
        afterburner,
        crashed,
        aircraft_speed,
        on_ground=False,
        crash_type="solid",
        crash_reason="",
        paused=False,
    ):
        """
        Atualiza em tempo real os ganhos dos segmentos de motor (JET_WHINE, COMBUSTION,
        EFSC Afterburner), perspectiva interna/externa, rolagem no solo e eventos de
        toque no convés (touchdown) ou colisão sólida/aquática + corte (shutdown).
        """
        if not self._running:
            return

        # 0. Quando pausado (Pause/Config), silencia suavemente loops de voo sem perder o estado anterior
        if paused:
            self._fade_out_flight_loops()
            return

        # 1. No Menu Principal ou na Cena 3 (Inspeção), motores de voo e rolagem permanecem desligados
        scene_cfg = SCENE_AUDIO_MAP.get(self.scene_mode, SCENE_AUDIO_MAP[3])
        if not scene_cfg.get("engines_active", False):
            self._fade_out_flight_loops()
            self._prev_on_ground = on_ground
            self._prev_crashed = crashed
            self._prev_throttle = throttle
            return

        # 2. Se ocorreu colisão neste frame, silencia motores e dispara som de impacto + corte (shutdown)
        if crashed:
            if not self._prev_crashed:
                self._fade_out_flight_loops()
                self.trigger_crash_sfx(crash_type=crash_type, crash_reason=crash_reason)
                self.trigger_engine_shutdown()
            self._prev_crashed = True
            self._prev_on_ground = on_ground
            self._prev_throttle = throttle
            return

        # Se acabou de reiniciar de um crash (ex: pressionou 'R' antes de 2s), encerra suavemente os SFX de impacto
        if self._prev_crashed and not crashed:
            self.stop_sfx("crash_boom", fade_out_sec=0.15)
            self.stop_sfx("crash_water_splash", fade_out_sec=0.15)

        self._prev_crashed = False

        # 3. Detecta pouso (transição de ar -> solo no convés) e toca 'touchdown' (touchc.wav)
        if on_ground and not self._prev_on_ground:
            self.play_sfx("touchdown")

        # 4. Detecta início de aceleração a partir do repouso no convés (ignição de combustão)
        now = time.time()
        if on_ground and self._prev_throttle <= 0.01 and throttle > 0.02:
            if (now - self._last_start_sfx_time) > 5.0:
                self.trigger_engine_start()
                self._last_start_sfx_time = now

        self._prev_on_ground = on_ground
        self._prev_throttle = throttle

        # 5. Perspectiva ativa: Câmera 2 = 'int', Câmeras 1 e 3 = 'ext'
        active_persp = "int" if self.camera_mode == 2 else "ext"
        inactive_persp = "ext" if active_persp == "int" else "int"

        # Se estiver totalmente parado no convés com throttle zero, mantém apenas um idle suave (35%)
        t_val = float(np.clip(throttle, 0.0, 1.0))
        idle_scale = 0.38 if (on_ground and t_val < 0.01 and aircraft_speed < 0.5) else 1.0

        persp_rate = 1.0 / max(0.04, PERSPECTIVE_CROSSFADE_SECONDS)
        eng_rate = 1.0 / max(0.04, ENGINE_SMOOTH_TIME_SECONDS)
        ab_rate = 1.0 / max(0.05, AFTERBURNER_FADE_SECONDS)

        # 6. Calcula ganhos dos 4 segmentos de JET_WHINE e 4 de COMBUSTION para Motores 1 e 2
        for eng_idx in (1, 2):
            # Jet Whine (0..3)
            for seg_idx, env in enumerate(JET_WHINE_THROTTLE_ENVELOPES):
                w = _evaluate_trapezoid_envelope(t_val, *env) * idle_scale
                k_act = f"engine_{eng_idx}_jet_whine_{active_persp}_{seg_idx}"
                k_inact = f"engine_{eng_idx}_jet_whine_{inactive_persp}_{seg_idx}"

                if k_act in self.voices:
                    v = self.voices[k_act]
                    v.playing = True
                    v.fade_rate = eng_rate
                    v.target_gain = w
                if k_inact in self.voices:
                    v_off = self.voices[k_inact]
                    v_off.fade_rate = persp_rate
                    v_off.target_gain = 0.0

            # Combustion (1..4)
            for seg_idx, env in enumerate(COMBUSTION_THROTTLE_ENVELOPES, start=1):
                w = _evaluate_trapezoid_envelope(t_val, *env) * idle_scale
                k_act = f"engine_{eng_idx}_comb_{active_persp}_{seg_idx}"
                k_inact = f"engine_{eng_idx}_comb_{inactive_persp}_{seg_idx}"

                if k_act in self.voices:
                    v = self.voices[k_act]
                    v.playing = True
                    v.fade_rate = eng_rate
                    v.target_gain = w
                if k_inact in self.voices:
                    v_off = self.voices[k_inact]
                    v_off.fade_rate = persp_rate
                    v_off.target_gain = 0.0

            # 7. Camada EFSC (Afterburner operando em loop)
            ab_on = bool(afterburner and t_val > 0.02)
            ab_gain = (0.75 + 0.25 * t_val) if ab_on else 0.0
            k_ab_act = f"engine_{eng_idx}_ab_{active_persp}"
            k_ab_inact = f"engine_{eng_idx}_ab_{inactive_persp}"

            if k_ab_act in self.voices:
                v_ab = self.voices[k_ab_act]
                v_ab.playing = True
                v_ab.fade_rate = ab_rate
                v_ab.target_gain = ab_gain
            if k_ab_inact in self.voices:
                v_ab_off = self.voices[k_ab_inact]
                v_ab_off.fade_rate = persp_rate
                v_ab_off.target_gain = 0.0

        # 8. Rolagem das rodas no convés (ground_roll - roll2.wav)
        if "ground_roll" in self.voices:
            v_roll = self.voices["ground_roll"]
            if on_ground and aircraft_speed > GROUND_ROLL_MIN_SPEED:
                spd_norm = float(np.clip(
                    (aircraft_speed - GROUND_ROLL_MIN_SPEED) / (GROUND_ROLL_FULL_SPEED - GROUND_ROLL_MIN_SPEED),
                    0.0, 1.0
                ))
                v_roll.playing = True
                v_roll.fade_rate = 10.0
                v_roll.target_gain = spd_norm
                v_roll.speed = GROUND_ROLL_MIN_RATE + spd_norm * (GROUND_ROLL_MAX_RATE - GROUND_ROLL_MIN_RATE)
            else:
                v_roll.fade_rate = 12.0
                v_roll.target_gain = 0.0

    # --------------------------------------------------------------------------
    # DISPARO DE EFEITOS SONOROS PONTUAIS (SFX)
    # --------------------------------------------------------------------------

    def play_sfx(self, name, restart=True):
        """Dispara um efeito sonoro one-shot pelo identificador configurado."""
        if not self._running or name not in self.voices:
            return
        voice = self.voices[name]
        if restart or not voice.playing:
            voice.cursor = float(voice.loop_start)
        voice.current_gain = 1.0
        voice.target_gain = 1.0
        voice.fade_rate = 15.0
        voice.playing = True


    def play_menu_sfx(self, action):
        """
        Toca o efeito sonoro de interface/menu correspondente à ação ('move', 'select' ou 'pause'),
        usando o mapeamento configurável MENU_SFX_MAP em audio_config.py.
        """
        clip_name = MENU_SFX_MAP.get(action)
        if clip_name:
            self.play_sfx(clip_name, restart=True)

    def stop_sfx(self, name, fade_out_sec=0.12):
        """Interrompe um efeito sonoro com fade-out rápido para evitar clique."""
        if name not in self.voices:
            return
        voice = self.voices[name]
        if fade_out_sec <= 0.005:
            voice.playing = False
            voice.current_gain = 0.0
            voice.target_gain = 0.0
        else:
            voice.fade_rate = 1.0 / fade_out_sec
            voice.target_gain = 0.0

    def play_gear_sfx(self, deploying):
        """
        Toca o som de baixar ('gear_down') ou recolher ('gear_up') o trem de pouso,
        interrompendo o som oposto caso o jogador inverta o comando no meio do curso.
        """
        if self.scene_mode == 3:
            # Permite ouvir o trem de pouso também na Cena 3 durante a inspeção!
            pass
        if deploying:
            self.stop_sfx("gear_up", fade_out_sec=0.08)
            self.play_sfx("gear_down", restart=True)
        else:
            self.stop_sfx("gear_down", fade_out_sec=0.08)
            self.play_sfx("gear_up", restart=True)

    def trigger_engine_start(self):
        """Dispara o som de ignição/combustão inicial conforme a perspectiva da câmera."""
        persp = "int" if self.camera_mode == 2 else "ext"
        self.play_sfx(f"engine_comb_start_{persp}", restart=True)

    def trigger_engine_shutdown(self):
        """Dispara o som de corte/desligamento da turbina conforme a perspectiva da câmera."""
        persp = "int" if self.camera_mode == 2 else "ext"
        self.stop_sfx(f"engine_comb_start_{persp}", fade_out_sec=0.1)
        self.stop_sfx(f"engine_starter_{persp}", fade_out_sec=0.1)
        self.play_sfx(f"engine_shutdown_{persp}", restart=True)

    def trigger_crash_sfx(self, crash_type="solid", crash_reason=""):
        """
        Dispara os efeitos sonoros de colisão:
          - Colisão sólida (navio, convés, rochas, paredes, bunker): toca 'crash_boom' (boom_crash.wav).
          - Colisão na água (ondas do oceano): toca simultaneamente 'crash_boom' + 'crash_water_splash'
            (boom_crash.wav + water_splash.wav), combinando o impacto grave com o splash agudo.
        """
        reason_upper = str(crash_reason).upper()
        is_water = (
            crash_type == "water"
            or "OCEANO" in reason_upper
            or "AGUA" in reason_upper
            or "ÁGUA" in reason_upper
        )
        self.play_sfx("crash_boom", restart=True)
        if is_water:
            self.play_sfx("crash_water_splash", restart=True)

    # --------------------------------------------------------------------------
    # CONTROLES DE VOLUME, VELOCIDADE E MUTE (PARA ATALHOS E FUTURA GUI)
    # --------------------------------------------------------------------------

    def set_master_volume(self, value):
        self.volumes["master"] = float(np.clip(value, 0.0, 1.0))
        print(f"[Áudio] Volume Geral (Master): {int(round(self.volumes['master'] * 100))}%")

    def set_category_volume(self, category, value):
        if category in self.volumes:
            self.volumes[category] = float(np.clip(value, 0.0, 1.0))
            print(f"[Áudio] Volume '{category}': {int(round(self.volumes[category] * 100))}%")

    def set_clip_volume(self, name, value):
        if name in self.voices:
            self.voices[name].base_volume = float(max(0.0, value))

    def set_clip_speed(self, name, value):
        if name in self.voices:
            self.voices[name].speed = float(np.clip(value, 0.25, 3.0))

    def set_muted(self, muted):
        self.muted = bool(muted)
        estado = "MUDO (MUTE ATIVO)" if self.muted else "ATIVADO (SOM LIGADO)"
        print(f"[Áudio] Estado Geral: {estado}")

    def toggle_mute(self):
        self.set_muted(not self.muted)

    def set_music_muted(self, muted):
        self.music_muted = bool(muted)
        estado = "SILENCIADA" if self.music_muted else "ATIVADA"
        print(f"[Áudio] Trilha Musical: {estado}")

    def toggle_music_mute(self):
        self.set_music_muted(not self.music_muted)


# ==============================================================================
# 4. MODO UTILITÁRIO DE PRÉ-VISUALIZAÇÃO / AUDIÇÃO DE CLIPS VIA TERMINAL
# ==============================================================================
# Permite testar qualquer clip isoladamente executando:
#   python src/audio_manager.py [nome_do_clip] [duracao_segundos]

if __name__ == "__main__":
    mgr = AudioManager(initial_scene=3)
    if len(sys.argv) < 2:
        print("\nClips disponíveis em audio_config.py:")
        for k, v in mgr.voices.items():
            dur = v.num_frames / float(OUTPUT_SAMPLE_RATE)
            print(f"  - {k:<28} | cat={v.category:<8} | dur={dur:5.2f}s | loop={v.loop}")
        print("\nPara ouvir um clip específico, execute:")
        print("  python src/audio_manager.py gear_down")
        sys.exit(0)

    clip_to_test = sys.argv[1]
    play_secs = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
    mgr.start()
    if clip_to_test in mgr.voices:
        print(f"Reproduzindo '{clip_to_test}' por {play_secs:.1f}s...")
        mgr.play_sfx(clip_to_test)
        time.sleep(play_secs)
    else:
        print(f"Clip '{clip_to_test}' não encontrado ou arquivo WAV ausente.")
    mgr.close()