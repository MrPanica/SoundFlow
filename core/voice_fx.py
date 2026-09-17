"""
Real-time DSP Audio Effects and Voice Processing for SoundFlow Studio.
Features:
- HighQualityPitchShifter: Phase-aligned, non-comb-filtering granular pitch shifter with adaptive grain sizing.
- VocalTractFilter: Real-time Vocal Tract Length (formant) transformation with high-pass chest rumble cutoff,
  formant peak resonators, and vocal air/breathiness enhancement.
- Realistic Human Presets (Female, Child, Male, Helium, Monster, etc.).
- Noise Gate, 2-Band Tone EQ, Ring Modulation (Robot), Megaphone Saturation, and Spatial Echo Delay.
"""

import numpy as np
from typing import Dict, Any, Optional

DEFAULT_PARAMS: Dict[str, Any] = {
    "pitch_semitones": 0.0,    # -12.0 to +12.0 semitones
    "formant_shift": 0.0,      # -0.50 to +0.50 (Vocal Tract Length: -50% to +50%)
    "hpf_cutoff_hz": 30.0,     # 20.0 to 450.0 Hz (highpass rumble/chest resonance filter)
    "lpf_cutoff_hz": 20000.0,  # 1000.0 to 20000.0 Hz (lowpass filter for warmth/band limiting)
    "air_presence": 0.0,       # -12.0 to +12.0 dB (breathiness/clarity above 4.5 kHz)
    "eq_bass": 0.0,            # -12.0 to +12.0 dB
    "eq_treble": 0.0,          # -12.0 to +12.0 dB
    "grain_size": 1024,        # 512 to 2048 samples
    "robot_enabled": False,
    "robot_freq": 75.0,        # 20.0 to 400.0 Hz
    "robot_depth": 0.82,       # 0.0 to 1.0
    "megaphone_enabled": False,
    "megaphone_drive": 2.8,    # 1.0 to 5.0
    "echo_enabled": False,
    "echo_delay_ms": 240.0,    # 50.0 to 800.0 ms
    "echo_feedback": 0.38,     # 0.0 to 0.85
    "echo_wet": 0.45,          # 0.0 to 1.0
    "gate_enabled": False,     # Noise gate enabled
    "gate_threshold_db": -55.0 # -70.0 to -15.0 dB
}

BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "normal": {
        **DEFAULT_PARAMS,
        "name": "🎭 Обычный голос",
        "description": "Чистый естественный голос без эффектов"
    },
    "female": {
        **DEFAULT_PARAMS,
        "name": "👩 Женский голос",
        "description": "Естественный чистый женский тембр (золотой стандарт Clownfish/Voicemod)",
        "pitch_semitones": 4.8,
        "formant_shift": 0.14,
        "hpf_cutoff_hz": 125.0,
        "lpf_cutoff_hz": 12000.0,
        "air_presence": 1.2,
        "eq_bass": -1.5,
        "eq_treble": 0.5,
        "grain_size": 1536
    },
    "child": {
        **DEFAULT_PARAMS,
        "name": "🧒 Ребёнок",
        "description": "Звонкий и чистый детский тембр (эталон Clownfish Baby Pitch)",
        "pitch_semitones": 7.5,
        "formant_shift": 0.25,
        "hpf_cutoff_hz": 170.0,
        "lpf_cutoff_hz": 14000.0,
        "air_presence": 1.5,
        "eq_bass": -3.0,
        "eq_treble": 1.0,
        "grain_size": 1408
    },
    "male": {
        **DEFAULT_PARAMS,
        "name": "👨 Мужской глубокий",
        "description": "Плотный низкий мужской баритон",
        "pitch_semitones": -3.2,
        "formant_shift": -0.10,
        "hpf_cutoff_hz": 45.0,
        "lpf_cutoff_hz": 18000.0,
        "eq_bass": 4.0,
        "eq_treble": -1.5,
        "grain_size": 1600
    },
    "monster": {
        **DEFAULT_PARAMS,
        "name": "👹 Демон / Monster",
        "description": "Глубокий зловещий бас с удлинённым голосовым трактом",
        "pitch_semitones": -7.0,
        "formant_shift": -0.22,
        "hpf_cutoff_hz": 40.0,
        "lpf_cutoff_hz": 16000.0,
        "eq_bass": 5.5,
        "eq_treble": -2.0,
        "echo_enabled": True,
        "echo_delay_ms": 115.0,
        "echo_feedback": 0.28,
        "echo_wet": 0.28,
        "grain_size": 1792
    },
    "helium": {
        **DEFAULT_PARAMS,
        "name": "🐿️ Бурундук / Helium",
        "description": "Высокий забавный мультяшный голос",
        "pitch_semitones": 10.5,
        "formant_shift": 0.32,
        "hpf_cutoff_hz": 210.0,
        "lpf_cutoff_hz": 16000.0,
        "eq_bass": -5.0,
        "eq_treble": 2.5,
        "grain_size": 1024
    },
    "robot": {
        **DEFAULT_PARAMS,
        "name": "🤖 Кибер-Робот",
        "description": "Металлический голос с модуляцией",
        "robot_enabled": True,
        "robot_freq": 80.0,
        "robot_depth": 0.88,
        "hpf_cutoff_hz": 80.0,
        "lpf_cutoff_hz": 8500.0,
        "grain_size": 1024
    },
    "megaphone": {
        **DEFAULT_PARAMS,
        "name": "📢 Мегафон / Рация",
        "description": "Эффект переговоров по военной рации",
        "megaphone_enabled": True,
        "megaphone_drive": 2.6,
        "hpf_cutoff_hz": 450.0,
        "lpf_cutoff_hz": 3200.0,
        "eq_bass": -6.0,
        "eq_treble": 2.0
    },
    "telephone": {
        **DEFAULT_PARAMS,
        "name": "☎️ Телефонный звонок",
        "description": "Узкополосный звук старого телефона",
        "megaphone_enabled": True,
        "megaphone_drive": 1.4,
        "hpf_cutoff_hz": 320.0,
        "lpf_cutoff_hz": 3400.0,
        "eq_bass": -10.0,
        "eq_treble": 1.0
    },
    "astronaut": {
        **DEFAULT_PARAMS,
        "name": "👨‍🚀 Космонавт (NASA)",
        "description": "Радиопереговоры из открытого космоса",
        "megaphone_enabled": True,
        "megaphone_drive": 1.5,
        "hpf_cutoff_hz": 320.0,
        "lpf_cutoff_hz": 3100.0,
        "eq_bass": -7.0,
        "eq_treble": 1.5,
        "echo_enabled": True,
        "echo_delay_ms": 105.0,
        "echo_feedback": 0.22,
        "echo_wet": 0.24
    },
    "radio": {
        **DEFAULT_PARAMS,
        "name": "📻 Старое радио",
        "description": "Винтажный радиоприемник с узкой полосой",
        "megaphone_enabled": True,
        "megaphone_drive": 1.3,
        "hpf_cutoff_hz": 220.0,
        "lpf_cutoff_hz": 4200.0,
        "eq_bass": -3.5,
        "eq_treble": 1.0
    },
    "cave": {
        **DEFAULT_PARAMS,
        "name": "🦇 Пещера / Грот",
        "description": "Глубокое гулкое эхо подземного грота",
        "pitch_semitones": -0.5,
        "hpf_cutoff_hz": 50.0,
        "lpf_cutoff_hz": 9500.0,
        "eq_bass": 2.0,
        "echo_enabled": True,
        "echo_delay_ms": 320.0,
        "echo_feedback": 0.52,
        "echo_wet": 0.45
    },
    "stadium": {
        **DEFAULT_PARAMS,
        "name": "🏟️ Стадион / Концерт",
        "description": "Огромный стадионный объём и реверберация",
        "pitch_semitones": 0.0,
        "hpf_cutoff_hz": 60.0,
        "lpf_cutoff_hz": 10000.0,
        "echo_enabled": True,
        "echo_delay_ms": 440.0,
        "echo_feedback": 0.48,
        "echo_wet": 0.42
    },
    "ghost": {
        **DEFAULT_PARAMS,
        "name": "👻 Призрак / Phantom",
        "description": "Загадочный мистический потусторонний голос",
        "pitch_semitones": 1.5,
        "hpf_cutoff_hz": 70.0,
        "lpf_cutoff_hz": 8000.0,
        "robot_enabled": True,
        "robot_freq": 30.0,
        "robot_depth": 0.38,
        "echo_enabled": True,
        "echo_delay_ms": 280.0,
        "echo_feedback": 0.40,
        "echo_wet": 0.35
    },
    "alien": {
        **DEFAULT_PARAMS,
        "name": "👽 Пришелец",
        "description": "Инопланетная модуляция и эхо",
        "pitch_semitones": 3.5,
        "hpf_cutoff_hz": 80.0,
        "lpf_cutoff_hz": 9000.0,
        "robot_enabled": True,
        "robot_freq": 92.0,
        "robot_depth": 0.55,
        "echo_enabled": True,
        "echo_delay_ms": 160.0,
        "echo_feedback": 0.30,
        "echo_wet": 0.30
    },
    "echo": {
        **DEFAULT_PARAMS,
        "name": "🌌 Пространственное эхо",
        "description": "Повторы с затуханием",
        "echo_enabled": True,
        "echo_delay_ms": 240.0,
        "echo_feedback": 0.38,
        "echo_wet": 0.45
    }
}


class HighQualityPitchShifter:
    """
    Real-time pitch shifter with correlation-aligned phase crossfading and adaptive grain sizes.
    Completely eliminates the 180-degree comb-filter null and metallic buzz of naive granular loops.
    """

    def __init__(self, sample_rate: int = 48000, grain_size: int = 1024):
        self.sample_rate = sample_rate
        self.grain_size = grain_size
        self.buf_size = max(grain_size * 16, 32768)
        self.buffer = np.zeros((self.buf_size, 2), dtype=np.float32)
        self.write_pos = 0
        self.phase = 0.0
        self.offset1 = 0.0
        self.offset2 = 0.0
        self.max_lag = 120
        self.corr_len = 160

    def reset(self):
        self.buffer.fill(0.0)
        self.write_pos = 0
        self.phase = 0.0
        self.offset1 = 0.0
        self.offset2 = 0.0

    def _find_alignment(self, cw_idx: float, p_active: float, offset_active: float, p_target: float, g_size: int) -> float:
        """Finds optimal lag tau to align target grain in-phase with the currently active grain."""
        r_active = int(cw_idx - p_active * g_size - offset_active) % self.buf_size
        r_target = int(cw_idx - p_target * g_size) % self.buf_size

        t_idx = (r_active + np.arange(self.corr_len)) % self.buf_size
        s_idx = (r_target - self.max_lag + np.arange(self.corr_len + 2 * self.max_lag)) % self.buf_size

        tmpl = self.buffer[t_idx, 0]
        search = self.buffer[s_idx, 0]

        std_t = float(np.std(tmpl))
        std_s = float(np.std(search))
        if std_t > 1e-4 and std_s > 1e-4:
            corr = np.correlate(search, tmpl, mode='valid')
            best_lag = int(np.argmax(corr)) - self.max_lag
            return -float(best_lag)
        return 0.0

    def process(self, chunk: np.ndarray, semitones: float, grain_size: Optional[int] = None) -> np.ndarray:
        if abs(semitones) < 0.1:
            return chunk
        n = len(chunk)
        if n == 0:
            return chunk

        # Adaptive grain size: maintain full 30-35ms grains to capture complete vocal glottal periods
        if grain_size is not None:
            g_size = int(grain_size)
        elif semitones > 6.0:
            g_size = 1408
        elif semitones > 2.0:
            g_size = 1536
        elif semitones < -4.0:
            g_size = 1792
        elif semitones < -1.0:
            g_size = 1536
        else:
            g_size = self.grain_size

        mono = (chunk.ndim == 1)
        if mono:
            chunk_2d = np.column_stack([chunk, chunk])
        elif chunk.shape[1] == 1:
            chunk_2d = np.column_stack([chunk[:, 0], chunk[:, 0]])
        else:
            chunk_2d = chunk

        rate = float(2.0 ** (semitones / 12.0))

        # Contiguous slice write into circular ring buffer
        end_pos = self.write_pos + n
        if end_pos <= self.buf_size:
            self.buffer[self.write_pos:end_pos] = chunk_2d
        else:
            first = self.buf_size - self.write_pos
            self.buffer[self.write_pos:] = chunk_2d[:first]
            self.buffer[:end_pos - self.buf_size] = chunk_2d[first:]
        self.write_pos = end_pos % self.buf_size

        t = np.arange(n, dtype=np.float32)
        delta_phase = (1.0 - rate) / float(g_size)
        cur_write = self.write_pos - n + t

        p1_raw = self.phase + t * delta_phase
        p1 = p1_raw % 1.0
        p2 = (p1 + 0.5) % 1.0

        off1_arr = np.full(n, self.offset1, dtype=np.float32)
        off2_arr = np.full(n, self.offset2, dtype=np.float32)

        # Detect wrap for grain 1 (at amplitude ~ 0): align grain 1 with grain 2
        fl1 = np.floor(p1_raw).astype(np.int32)
        wrap_mask1 = (fl1 != fl1[0])
        if np.any(wrap_mask1):
            idx1 = int(np.argmax(wrap_mask1))
            self.offset1 = self._find_alignment(cur_write[idx1], p2[idx1], self.offset2, p1[idx1], g_size)
            off1_arr[idx1:] = self.offset1

        # Detect wrap for grain 2 (at amplitude ~ 0): align grain 2 with grain 1
        p2_raw = p1_raw + 0.5
        fl2 = np.floor(p2_raw).astype(np.int32)
        wrap_mask2 = (fl2 != fl2[0])
        if np.any(wrap_mask2):
            idx2 = int(np.argmax(wrap_mask2))
            self.offset2 = self._find_alignment(cur_write[idx2], p1[idx2], self.offset1, p2[idx2], g_size)
            off2_arr[idx2:] = self.offset2

        self.phase = (self.phase + n * delta_phase) % 1.0

        # Equal-power complementary sinusoidal windowing:
        # sin^2(p1 * pi) + cos^2(p1 * pi) == 1.0 at every single sample.
        w1 = np.sin(p1 * np.pi)[:, np.newaxis]
        w2 = np.sin(p2 * np.pi)[:, np.newaxis]

        delay1 = p1 * g_size + off1_arr
        delay2 = p2 * g_size + off2_arr

        r1 = (cur_write - delay1) % self.buf_size
        r2 = (cur_write - delay2) % self.buf_size

        idx1_f = r1.astype(np.int32) % self.buf_size
        idx1_c = (idx1_f + 1) % self.buf_size
        frac1 = np.clip(r1 - idx1_f, 0.0, 1.0)[:, np.newaxis]

        idx2_f = r2.astype(np.int32) % self.buf_size
        idx2_c = (idx2_f + 1) % self.buf_size
        frac2 = np.clip(r2 - idx2_f, 0.0, 1.0)[:, np.newaxis]

        s1 = self.buffer[idx1_f] * (1.0 - frac1) + self.buffer[idx1_c] * frac1
        s2 = self.buffer[idx2_f] * (1.0 - frac2) + self.buffer[idx2_c] * frac2

        out = s1 * w1 + s2 * w2
        if mono:
            return out[:, 0]
        elif chunk.shape[1] == 1:
            return out[:, :1]
        return out


FastGranularPitchShifter = HighQualityPitchShifter


class BiquadFilter:
    """Fast Direct Form II Transposed Biquad IIR Filter in pure NumPy."""

    def __init__(self):
        self.b0 = 1.0
        self.b1 = 0.0
        self.b2 = 0.0
        self.a1 = 0.0
        self.a2 = 0.0
        self.s1 = 0.0
        self.s2 = 0.0

    def reset(self):
        self.s1 = 0.0
        self.s2 = 0.0

    def set_coeffs(self, b0: float, b1: float, b2: float, a1: float, a2: float):
        self.b0 = float(b0)
        self.b1 = float(b1)
        self.b2 = float(b2)
        self.a1 = float(a1)
        self.a2 = float(a2)

    def process(self, x: np.ndarray) -> np.ndarray:
        y = np.empty_like(x, dtype=np.float32)
        b0, b1, b2 = self.b0, self.b1, self.b2
        a1, a2 = self.a1, self.a2
        s1, s2 = self.s1, self.s2
        for i in range(len(x)):
            xi = float(x[i])
            yi = b0 * xi + s1
            s1 = b1 * xi - a1 * yi + s2
            s2 = b2 * xi - a2 * yi
            y[i] = yi
        self.s1 = s1
        self.s2 = s2
        return y


class VocalTractFilter:
    """
    Applies real-time vocal tract length (formant) transformation and acoustic conditioning.
    Implemented in pure NumPy with zero external heavy scientific library dependencies.
    Includes:
    - High-Pass Filter (Butterworth) to remove male chest resonance (<160-220 Hz)
    - Low-Pass Filter (Butterworth) to remove harsh digital highs / model telephone/radio bandwidth
    - Formant Resonators (F1, F2) shifted by formant_scale (e.g. 1.14x for female, 1.25x for child)
    - High-Shelf Air & Breathiness boost (>4.5 kHz)
    """

    def __init__(self, sample_rate: int = 48000):
        self.sr = sample_rate
        self.hpf = BiquadFilter()
        self.lpf = BiquadFilter()
        self.formant1 = BiquadFilter()
        self.formant2 = BiquadFilter()
        self.air_shelf = BiquadFilter()

        self.last_hpf_fc = 0.0
        self.last_lpf_fc = 0.0
        self.last_formant_shift = 999.0
        self.last_air_db = 999.0

    def reset(self):
        self.hpf.reset()
        self.lpf.reset()
        self.formant1.reset()
        self.formant2.reset()
        self.air_shelf.reset()
        self.last_hpf_fc = 0.0
        self.last_lpf_fc = 0.0
        self.last_formant_shift = 999.0
        self.last_air_db = 999.0

    def process(
        self,
        chunk: np.ndarray,
        hpf_fc: float = 30.0,
        formant_shift: float = 0.0,
        air_db: float = 0.0,
        lpf_fc: float = 20000.0,
    ) -> np.ndarray:
        if len(chunk) == 0:
            return chunk

        mono = (chunk.ndim == 1)
        if mono:
            x = chunk.astype(np.float32).copy()
        else:
            x = chunk[:, 0].astype(np.float32).copy()

        # 1. High-Pass Butterworth Filter (Removes chest rumble below hpf_fc)
        if hpf_fc >= 45.0:
            if abs(hpf_fc - self.last_hpf_fc) > 2.0:
                fc = min(max(hpf_fc, 20.0), self.sr * 0.45)
                w0 = 2.0 * np.pi * fc / self.sr
                cos_w = np.cos(w0)
                sin_w = np.sin(w0)
                alpha = sin_w * 0.70710678  # Q = 1/sqrt(2) for Butterworth
                a0 = 1.0 + alpha
                b0 = ((1.0 + cos_w) * 0.5) / a0
                b1 = -(1.0 + cos_w) / a0
                b2 = ((1.0 + cos_w) * 0.5) / a0
                a1 = (-2.0 * cos_w) / a0
                a2 = (1.0 - alpha) / a0
                self.hpf.set_coeffs(b0, b1, b2, a1, a2)
                self.last_hpf_fc = hpf_fc
            x = self.hpf.process(x)

        # 2. Formant Resonators (F1 and F2 scaling for vocal tract length)
        if abs(formant_shift) > 0.02:
            if abs(formant_shift - self.last_formant_shift) > 0.02:
                scale = 1.0 + float(formant_shift)
                f1 = min(self.sr * 0.45, max(250.0, 650.0 * scale))
                f2 = min(self.sr * 0.45, max(900.0, 2150.0 * scale))

                # Broad organic vocal tract formant F1 (Q=0.85, subtle natural boost)
                w1 = 2.0 * np.pi * f1 / self.sr
                cos_w1 = np.cos(w1)
                alpha1 = np.sin(w1) / (2.0 * 0.85)
                A1 = 10.0 ** (1.2 / 40.0)
                a0_1 = 1.0 + alpha1 / A1
                self.formant1.set_coeffs(
                    (1.0 + alpha1 * A1) / a0_1,
                    (-2.0 * cos_w1) / a0_1,
                    (1.0 - alpha1 * A1) / a0_1,
                    (-2.0 * cos_w1) / a0_1,
                    (1.0 - alpha1 / A1) / a0_1
                )

                # Broad organic vocal tract formant F2 (Q=0.85, non-ringing)
                w2 = 2.0 * np.pi * f2 / self.sr
                cos_w2 = np.cos(w2)
                alpha2 = np.sin(w2) / (2.0 * 0.85)
                A2 = 10.0 ** (1.5 / 40.0)
                a0_2 = 1.0 + alpha2 / A2
                self.formant2.set_coeffs(
                    (1.0 + alpha2 * A2) / a0_2,
                    (-2.0 * cos_w2) / a0_2,
                    (1.0 - alpha2 * A2) / a0_2,
                    (-2.0 * cos_w2) / a0_2,
                    (1.0 - alpha2 / A2) / a0_2
                )
                self.last_formant_shift = formant_shift

            f_res = self.formant1.process(x)
            f_res = self.formant2.process(f_res)
            x = 0.80 * x + 0.20 * f_res

        # 3. Vocal Air / Breathiness High Shelf (> 4500 Hz)
        if abs(air_db) > 0.5:
            if abs(air_db - self.last_air_db) > 0.5:
                A = 10.0 ** (air_db / 40.0)
                w0 = 2.0 * np.pi * min(4800.0, self.sr * 0.45) / self.sr
                cos_w = np.cos(w0)
                sin_w = np.sin(w0)
                two_sqrt_A_alpha = 2.0 * np.sqrt(A) * (sin_w * 0.70710678)
                a0 = (A + 1.0) - (A - 1.0) * cos_w + two_sqrt_A_alpha
                b0 = (A * ((A + 1.0) + (A - 1.0) * cos_w + two_sqrt_A_alpha)) / a0
                b1 = (-2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w)) / a0
                b2 = (A * ((A + 1.0) + (A - 1.0) * cos_w - two_sqrt_A_alpha)) / a0
                a1 = (2.0 * ((A - 1.0) - (A + 1.0) * cos_w)) / a0
                a2 = ((A + 1.0) - (A - 1.0) * cos_w - two_sqrt_A_alpha) / a0
                self.air_shelf.set_coeffs(b0, b1, b2, a1, a2)
                self.last_air_db = air_db
            x = self.air_shelf.process(x)

        # 4. Low-Pass Butterworth Filter (Cuts harsh digital highs / simulates warm bandpass)
        if lpf_fc < 18000.0:
            if abs(lpf_fc - self.last_lpf_fc) > 2.0:
                fc = min(max(lpf_fc, 500.0), self.sr * 0.45)
                w0 = 2.0 * np.pi * fc / self.sr
                cos_w = np.cos(w0)
                sin_w = np.sin(w0)
                alpha = sin_w * 0.70710678  # Q = 1/sqrt(2) for Butterworth
                a0 = 1.0 + alpha
                b0 = ((1.0 - cos_w) * 0.5) / a0
                b1 = (1.0 - cos_w) / a0
                b2 = ((1.0 - cos_w) * 0.5) / a0
                a1 = (-2.0 * cos_w) / a0
                a2 = (1.0 - alpha) / a0
                self.lpf.set_coeffs(b0, b1, b2, a1, a2)
                self.last_lpf_fc = lpf_fc
            x = self.lpf.process(x)

        if mono:
            return x.astype(np.float32)
        elif chunk.shape[1] == 1:
            return x[:, np.newaxis].astype(np.float32)
        else:
            return np.column_stack([x, x]).astype(np.float32)


class VoiceFXProcessor:
    """Processes real-time audio frames with fully configurable DSP voice effects."""

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.active_preset_name = "normal"

        # Parameters
        self.params = dict(DEFAULT_PARAMS)

        # Real-time pitch shifter & vocal tract formant filter
        self.pitch_shifter = HighQualityPitchShifter(sample_rate=sample_rate, grain_size=1024)
        self.vocal_filter = VocalTractFilter(sample_rate=sample_rate)

        # Gate state (fast attack, smooth natural release)
        self.gate_gain = 1.0
        self.attack_coeff = 0.4
        self.release_coeff = 0.02

        # Robot ring modulator state
        self.robot_phase = 0.0

        # Echo buffer (2 seconds max) with warm acoustic damping state
        self.echo_buffer = np.zeros(sample_rate * 2, dtype=np.float32)
        self.echo_idx = 0
        self._echo_damp_state = 0.0

        # EQ filter states (for smooth low/high pass filtering across chunks)
        self._bass_filter_state = 0.0
        self._treble_filter_state = 0.0

    def reset_to_default(self):
        self.active_preset_name = "normal"
        self.params = dict(DEFAULT_PARAMS)
        self.pitch_shifter.reset()
        self.vocal_filter.reset()
        self.echo_buffer.fill(0.0)
        self.echo_idx = 0
        self._echo_damp_state = 0.0
        self._bass_filter_state = 0.0
        self._treble_filter_state = 0.0
        self.gate_gain = 1.0

    def get_params(self) -> Dict[str, Any]:
        return dict(self.params)

    def set_params(self, params: Dict[str, Any]):
        for k, v in params.items():
            if k in self.params:
                self.params[k] = type(self.params[k])(v)

    def set_preset(self, preset_name: str):
        self.active_preset_name = preset_name
        if preset_name in BUILTIN_PRESETS:
            preset_data = BUILTIN_PRESETS[preset_name]
            for k in DEFAULT_PARAMS:
                if k in preset_data:
                    self.params[k] = preset_data[k]
        else:
            self.reset_to_default()

    def set_gate_threshold(self, threshold_db: float):
        self.params["gate_threshold_db"] = float(threshold_db)

    def process(self, input_chunk: np.ndarray) -> np.ndarray:
        """
        Process a chunk of float32 mono or stereo audio.
        input_chunk: shape (N,) or (N, C) in range [-1.0, 1.0]
        """
        if len(input_chunk) == 0:
            return input_chunk

        # For large buffers (e.g. from TTS synthesis or file playback), process in 1024-sample blocks
        # to ensure pitch shifter and echo buffers don't overflow or throw dimension errors.
        if len(input_chunk) > 2048:
            block_size = 1024
            out_blocks = []
            for start in range(0, len(input_chunk), block_size):
                sub_chunk = input_chunk[start:start + block_size]
                out_blocks.append(self.process(sub_chunk))
            return np.concatenate(out_blocks, axis=0)

        chunk = input_chunk.astype(np.float32).copy()
        is_stereo = chunk.ndim == 2 and chunk.shape[1] > 1

        # 1. Noise Gate (only if explicitly enabled)
        if self.params.get("gate_enabled", False):
            rms = np.sqrt(np.mean(np.square(chunk))) + 1e-9
            db = 20.0 * np.log10(rms)
            target_gain = 1.0 if db >= self.params.get("gate_threshold_db", -55.0) else 0.0

            if target_gain > self.gate_gain:
                self.gate_gain += self.attack_coeff * (target_gain - self.gate_gain)
            else:
                self.gate_gain += self.release_coeff * (target_gain - self.gate_gain)

            if self.gate_gain < 0.005:
                return np.zeros_like(chunk)

            chunk *= self.gate_gain
        else:
            self.gate_gain = 1.0

        # 2. Pitch Shifting (Glottal excitation F0 shift) FIRST
        pitch_semi = float(self.params.get("pitch_semitones", 0.0))
        grain_size = int(self.params.get("grain_size", 1024))
        if abs(pitch_semi) > 0.15:
            chunk = self.pitch_shifter.process(chunk, pitch_semi, grain_size=grain_size)

        # 3. Vocal Tract Formant Filtering & HPF Rumble Cut AFTER pitch shift
        # This accurately shapes vocal tract resonances at their true human target positions
        hpf_fc = float(self.params.get("hpf_cutoff_hz", 30.0))
        lpf_fc = float(self.params.get("lpf_cutoff_hz", 20000.0))
        formant_shift = float(self.params.get("formant_shift", 0.0))
        air_db = float(self.params.get("air_presence", 0.0))
        if hpf_fc >= 45.0 or lpf_fc < 18000.0 or abs(formant_shift) > 0.02 or abs(air_db) > 0.5:
            chunk = self.vocal_filter.process(
                chunk, hpf_fc=hpf_fc, formant_shift=formant_shift, air_db=air_db, lpf_fc=lpf_fc
            )

        # 4. 2-Band Tone EQ (Bass & Treble)
        eq_bass = self.params.get("eq_bass", 0.0)
        eq_treble = self.params.get("eq_treble", 0.0)
        if abs(eq_bass) > 0.5 or abs(eq_treble) > 0.5:
            chunk = self._apply_tone_eq(chunk, eq_bass, eq_treble, is_stereo)

        # 5. Robot Ring Modulator
        if self.params.get("robot_enabled", False):
            freq = self.params.get("robot_freq", 75.0)
            depth = self.params.get("robot_depth", 0.8)
            num_samples = len(chunk)
            t = (np.arange(num_samples) + self.robot_phase) / self.sample_rate
            carrier = np.sin(2.0 * np.pi * freq * t).astype(np.float32)
            self.robot_phase = (self.robot_phase + num_samples) % self.sample_rate

            mod = (1.0 - depth) + depth * (0.5 + 0.5 * carrier)
            if is_stereo:
                chunk[:, 0] *= mod
                chunk[:, 1] *= mod
            else:
                chunk *= mod

        # 6. Megaphone / Overdrive Distortion
        if self.params.get("megaphone_enabled", False):
            drive = self.params.get("megaphone_drive", 2.8)
            diff = np.diff(chunk, axis=0, prepend=0)
            chunk = 0.55 * chunk + 0.45 * diff
            chunk = np.tanh(chunk * drive) * (1.0 / np.sqrt(drive))

        # 7. Spatial Echo / Delay with warm physical acoustic damping
        if self.params.get("echo_enabled", False):
            delay_ms = self.params.get("echo_delay_ms", 250.0)
            feedback = self.params.get("echo_feedback", 0.4)
            wet = self.params.get("echo_wet", 0.5)

            delay_samples = max(1, int((delay_ms / 1000.0) * self.sample_rate))
            num_samples = len(chunk)
            mono = chunk[:, 0] if is_stereo else chunk
            delayed_samples = np.zeros(num_samples, dtype=np.float32)
            buf_len = len(self.echo_buffer)

            damping = 0.35  # warm acoustic air/wall absorption
            for i in range(num_samples):
                read_idx = (self.echo_idx - delay_samples + buf_len) % buf_len
                delayed = self.echo_buffer[read_idx]
                damped = (1.0 - damping) * delayed + damping * self._echo_damp_state
                self._echo_damp_state = damped
                delayed_samples[i] = delayed
                self.echo_buffer[self.echo_idx] = mono[i] + damped * feedback
                self.echo_idx = (self.echo_idx + 1) % buf_len

            if is_stereo:
                chunk[:, 0] += delayed_samples * wet
                chunk[:, 1] += delayed_samples * wet
            else:
                chunk += delayed_samples * wet

        # 8. Soft Peak Limiter
        np.clip(chunk, -0.98, 0.98, out=chunk)
        return chunk

    def _apply_tone_eq(self, chunk: np.ndarray, bass_db: float, treble_db: float, is_stereo: bool) -> np.ndarray:
        """Fast 2-band low/high shelf EQ."""
        bass_mult = 10.0 ** (bass_db / 20.0) - 1.0
        treble_mult = 10.0 ** (treble_db / 20.0) - 1.0
        alpha = 0.95

        if is_stereo:
            for ch in range(2):
                sig = chunk[:, ch]
                lows = np.zeros_like(sig)
                prev = self._bass_filter_state
                for i in range(len(sig)):
                    prev = alpha * prev + (1.0 - alpha) * sig[i]
                    lows[i] = prev
                self._bass_filter_state = prev

                highs = sig - lows
                chunk[:, ch] = sig + lows * (bass_mult * 0.5) + highs * (treble_mult * 0.5)
        else:
            sig = chunk
            lows = np.zeros_like(sig)
            prev = self._bass_filter_state
            for i in range(len(sig)):
                prev = alpha * prev + (1.0 - alpha) * sig[i]
                lows[i] = prev
            self._bass_filter_state = prev

            highs = sig - lows
            chunk = sig + lows * (bass_mult * 0.5) + highs * (treble_mult * 0.5)

        return chunk
