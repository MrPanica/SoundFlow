"""
Real-time DSP Audio Effects and Voice Processing for SoundFlow Studio.
Provides Noise Gate, Pitch Shifting, 2-Band Tone EQ, Ring Modulation (Robot),
Megaphone Saturation, and Spatial Echo Delay.
"""

import numpy as np
from typing import Dict, Any, Optional

DEFAULT_PARAMS: Dict[str, Any] = {
    "pitch_semitones": 0.0,    # -12.0 to +12.0 semitones
    "eq_bass": 0.0,            # -12.0 to +12.0 dB
    "eq_treble": 0.0,          # -12.0 to +12.0 dB
    "robot_enabled": False,
    "robot_freq": 75.0,        # 20.0 to 400.0 Hz
    "robot_depth": 0.8,        # 0.0 to 1.0
    "megaphone_enabled": False,
    "megaphone_drive": 2.8,    # 1.0 to 5.0
    "echo_enabled": False,
    "echo_delay_ms": 250.0,    # 50.0 to 800.0 ms
    "echo_feedback": 0.4,      # 0.0 to 0.85
    "echo_wet": 0.5,           # 0.0 to 1.0
    "gate_threshold_db": -45.0 # -70.0 to -15.0 dB
}

BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    "normal": {
        **DEFAULT_PARAMS,
        "name": "🎭 Обычный голос",
        "description": "Чистый естественный голос без эффектов"
    },
    "helium": {
        **DEFAULT_PARAMS,
        "name": "🐿️ Бурундук / Helium",
        "description": "Высокий забавный мультяшный голос",
        "pitch_semitones": 8.0,
        "eq_treble": 3.0
    },
    "monster": {
        **DEFAULT_PARAMS,
        "name": "👹 Демон / Monster",
        "description": "Глубокий зловещий бас",
        "pitch_semitones": -7.0,
        "eq_bass": 6.0,
        "echo_enabled": True,
        "echo_delay_ms": 160.0,
        "echo_feedback": 0.25,
        "echo_wet": 0.25
    },
    "robot": {
        **DEFAULT_PARAMS,
        "name": "🤖 Кибер-Робот",
        "description": "Металлический голос с модуляцией",
        "robot_enabled": True,
        "robot_freq": 75.0,
        "robot_depth": 0.85
    },
    "megaphone": {
        **DEFAULT_PARAMS,
        "name": "📢 Мегафон / Рация",
        "description": "Эффект переговоров по военной рации",
        "megaphone_enabled": True,
        "megaphone_drive": 3.2,
        "eq_bass": -6.0,
        "eq_treble": 4.0
    },
    "echo": {
        **DEFAULT_PARAMS,
        "name": "🌌 Пространственное эхо",
        "description": "Повторы с затуханием",
        "echo_enabled": True,
        "echo_delay_ms": 260.0,
        "echo_feedback": 0.45,
        "echo_wet": 0.55
    },
    "radio": {
        **DEFAULT_PARAMS,
        "name": "📻 Старое радио",
        "description": "Винтажный радиоприемник с узкой полосой",
        "megaphone_enabled": True,
        "megaphone_drive": 2.0,
        "eq_bass": -8.0,
        "eq_treble": -2.0
    },
    "alien": {
        **DEFAULT_PARAMS,
        "name": "👽 Пришелец",
        "description": "Инопланетная модуляция и эхо",
        "pitch_semitones": 4.0,
        "robot_enabled": True,
        "robot_freq": 115.0,
        "robot_depth": 0.65,
        "echo_enabled": True,
        "echo_delay_ms": 190.0,
        "echo_feedback": 0.35,
        "echo_wet": 0.35
    }
}


class VoiceFXProcessor:
    """Processes real-time audio frames with fully configurable DSP voice effects."""

    def __init__(self, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.active_preset_name = "normal"

        # Parameters
        self.params = dict(DEFAULT_PARAMS)

        # Gate state
        self.gate_gain = 1.0
        self.attack_coeff = 0.05
        self.release_coeff = 0.005

        # Robot ring modulator state
        self.robot_phase = 0.0

        # Echo buffer (2 seconds max)
        self.echo_buffer = np.zeros(sample_rate * 2, dtype=np.float32)
        self.echo_idx = 0

        # EQ filter states (for smooth low/high pass filtering across chunks)
        self._bass_filter_state = 0.0
        self._treble_filter_state = 0.0

    def reset_to_default(self):
        self.active_preset_name = "normal"
        self.params = dict(DEFAULT_PARAMS)

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

        chunk = input_chunk.astype(np.float32).copy()
        is_stereo = chunk.ndim == 2 and chunk.shape[1] > 1

        # 1. Noise Gate
        rms = np.sqrt(np.mean(np.square(chunk))) + 1e-9
        db = 20.0 * np.log10(rms)
        target_gain = 1.0 if db >= self.params["gate_threshold_db"] else 0.0

        if target_gain > self.gate_gain:
            self.gate_gain += self.attack_coeff * (target_gain - self.gate_gain)
        else:
            self.gate_gain += self.release_coeff * (target_gain - self.gate_gain)

        if self.gate_gain < 0.005:
            return np.zeros_like(chunk)

        chunk *= self.gate_gain

        # 2. Pitch Shifting (if semitones != 0)
        pitch_semi = self.params.get("pitch_semitones", 0.0)
        if abs(pitch_semi) > 0.2:
            pitch_factor = 2.0 ** (pitch_semi / 12.0)
            chunk = self._apply_pitch_shift(chunk, pitch_factor, is_stereo)

        # 3. 2-Band Tone EQ (Bass & Treble)
        eq_bass = self.params.get("eq_bass", 0.0)
        eq_treble = self.params.get("eq_treble", 0.0)
        if abs(eq_bass) > 0.5 or abs(eq_treble) > 0.5:
            chunk = self._apply_tone_eq(chunk, eq_bass, eq_treble, is_stereo)

        # 4. Robot Ring Modulator
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

        # 5. Megaphone / Overdrive Distortion
        if self.params.get("megaphone_enabled", False):
            drive = self.params.get("megaphone_drive", 2.8)
            # Bandpass / highpass emphasis
            diff = np.diff(chunk, axis=0, prepend=0)
            chunk = 0.55 * chunk + 0.45 * diff
            # Soft clipping saturation
            chunk = np.tanh(chunk * drive) * (1.0 / np.sqrt(drive))

        # 6. Spatial Echo / Delay
        if self.params.get("echo_enabled", False):
            delay_ms = self.params.get("echo_delay_ms", 250.0)
            feedback = self.params.get("echo_feedback", 0.4)
            wet = self.params.get("echo_wet", 0.5)

            delay_samples = max(1, int((delay_ms / 1000.0) * self.sample_rate))
            num_samples = len(chunk)
            mono = chunk[:, 0] if is_stereo else chunk
            delayed_samples = np.zeros(num_samples, dtype=np.float32)
            buf_len = len(self.echo_buffer)

            for i in range(num_samples):
                read_idx = (self.echo_idx - delay_samples + buf_len) % buf_len
                delayed_samples[i] = self.echo_buffer[read_idx]
                self.echo_buffer[self.echo_idx] = mono[i] + delayed_samples[i] * feedback
                self.echo_idx = (self.echo_idx + 1) % buf_len

            if is_stereo:
                chunk[:, 0] += delayed_samples * wet
                chunk[:, 1] += delayed_samples * wet
            else:
                chunk += delayed_samples * wet

        # 7. Final Limiter
        np.clip(chunk, -1.0, 1.0, out=chunk)
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

    def _apply_pitch_shift(self, chunk: np.ndarray, factor: float, is_stereo: bool) -> np.ndarray:
        """Fast time-domain resampling pitch shift with cross-fade windowing."""
        if abs(factor - 1.0) < 0.03:
            return chunk

        orig_len = len(chunk)
        new_len = int(orig_len / factor)
        if new_len <= 1:
            return chunk

        if is_stereo:
            resampled = np.zeros((new_len, 2), dtype=np.float32)
            indices = np.linspace(0, orig_len - 1, new_len)
            resampled[:, 0] = np.interp(indices, np.arange(orig_len), chunk[:, 0])
            resampled[:, 1] = np.interp(indices, np.arange(orig_len), chunk[:, 1])
        else:
            indices = np.linspace(0, orig_len - 1, new_len)
            resampled = np.interp(indices, np.arange(orig_len), chunk).astype(np.float32)

        if new_len >= orig_len:
            out = resampled[:orig_len]
        else:
            repeats = int(np.ceil(orig_len / new_len))
            tiled = np.tile(resampled, (repeats, 1) if is_stereo else repeats)
            out = tiled[:orig_len]

        return out
