"""
Procedural sound generator for SoundFlow Studio.
Generates starter soundboard sounds if the assets folder is empty.
"""

import wave
from pathlib import Path
import numpy as np


def save_wav(filepath: Path, samples: np.ndarray, sample_rate: int = 48000):
    filepath.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    int16_data = (clipped * 32767).astype(np.int16)
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16_data.tobytes())


def generate_starter_sounds(dest_dir: Path):
    sr = 48000
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. Airhorn Synth (DJ Stutter)
    t = np.linspace(0, 0.7, int(sr * 0.7), False)
    freq1, freq2 = 466.16, 622.25  # Bb4 + Eb5
    horn = np.sin(2 * np.pi * freq1 * t) + 0.6 * np.sin(2 * np.pi * freq2 * t)
    horn += 0.3 * np.sin(2 * np.pi * freq1 * 2 * t)
    # Stutter envelope
    env = np.ones_like(t)
    stutter_period = int(sr * 0.08)
    for i in range(0, int(sr * 0.35), stutter_period):
        env[i:i + int(stutter_period * 0.3)] = 0.0
    env[-int(sr * 0.2):] = np.linspace(1, 0, int(sr * 0.2))
    horn = horn * env * 0.7
    save_wav(dest_dir / "airhorn.wav", horn, sr)

    # 2. Level Up Fanfare (Arpeggio: C5, E5, G5, C6)
    notes = [523.25, 659.25, 783.99, 1046.50]
    note_dur = 0.12
    total_len = int(sr * (len(notes) * note_dur + 0.4))
    fanfare = np.zeros(total_len)
    for idx, f in enumerate(notes):
        start = int(idx * note_dur * sr)
        dur = 0.5 if idx == len(notes) - 1 else note_dur
        n_samples = int(dur * sr)
        t_note = np.linspace(0, dur, n_samples, False)
        wave_note = np.sin(2 * np.pi * f * t_note) + 0.25 * np.sin(2 * np.pi * f * 2 * t_note)
        env_note = np.exp(-4 * t_note)
        fanfare[start:start + n_samples] += wave_note * env_note * 0.6
    save_wav(dest_dir / "levelup.wav", fanfare, sr)

    # 3. 8-Bit Laser Zap
    dur = 0.25
    t_zap = np.linspace(0, dur, int(sr * dur), False)
    f_zap = np.geomspace(1200, 80, len(t_zap))
    phase = 2 * np.pi * np.cumsum(f_zap) / sr
    zap = np.sign(np.sin(phase)) * np.exp(-8 * t_zap) * 0.4
    save_wav(dest_dir / "laser.wav", zap, sr)

    # 4. Modern Notification Chime
    dur_chime = 0.45
    t_ch = np.linspace(0, dur_chime, int(sr * dur_chime), False)
    c1 = np.sin(2 * np.pi * 587.33 * t_ch) * np.exp(-10 * t_ch)  # D5
    t_ch2 = np.linspace(0, dur_chime - 0.1, int(sr * (dur_chime - 0.1)), False)
    c2 = np.sin(2 * np.pi * 880.00 * t_ch2) * np.exp(-7 * t_ch2)  # A5
    chime = np.zeros_like(t_ch)
    chime += c1 * 0.5
    chime[int(sr * 0.1):] += c2 * 0.7
    save_wav(dest_dir / "notification.wav", chime, sr)

    # 5. Bass Drop / Bruh Drop (808 Boom)
    dur_drop = 1.0
    t_drop = np.linspace(0, dur_drop, int(sr * dur_drop), False)
    f_drop = np.geomspace(160, 32, len(t_drop))
    phase_drop = 2 * np.pi * np.cumsum(f_drop) / sr
    drop = np.sin(phase_drop)
    # Saturation
    drop = np.tanh(drop * 2.0) * np.exp(-2.5 * t_drop) * 0.8
    save_wav(dest_dir / "bass_drop.wav", drop, sr)

    # 6. Coin Pickup (Retro Ping)
    t_c1 = np.linspace(0, 0.08, int(sr * 0.08), False)
    t_c2 = np.linspace(0, 0.35, int(sr * 0.35), False)
    p1 = np.sin(2 * np.pi * 987.77 * t_c1) * 0.5  # B5
    p2 = np.sin(2 * np.pi * 1318.51 * t_c2) * np.exp(-6 * t_c2) * 0.6  # E6
    coin = np.concatenate([p1, p2])
    save_wav(dest_dir / "coin.wav", coin, sr)


if __name__ == "__main__":
    sounds_path = Path(__file__).parent / "sounds"
    generate_starter_sounds(sounds_path)
    print(f"Starter sounds generated in {sounds_path}")
