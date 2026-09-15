"""
Instant Replay Rolling Buffer for SoundFlow Studio.
Continuously buffers the last N seconds of audio and saves instant clips to WAV.
"""

import time
import wave
from pathlib import Path
from typing import Optional
import numpy as np


class InstantReplayBuffer:
    """Ring buffer holding the last N seconds of stereo audio."""

    def __init__(self, duration_sec: int = 30, sample_rate: int = 48000):
        self.sample_rate = sample_rate
        self.max_samples = int(duration_sec * sample_rate)
        self.buffer = np.zeros((self.max_samples, 2), dtype=np.float32)
        self.write_pos = 0
        self.total_written = 0

    def set_duration(self, duration_sec: int):
        new_max = int(duration_sec * self.sample_rate)
        if new_max != self.max_samples:
            self.max_samples = new_max
            self.buffer = np.zeros((self.max_samples, 2), dtype=np.float32)
            self.write_pos = 0
            self.total_written = 0

    def push(self, chunk: np.ndarray):
        """Pushes new float32 stereo chunk (N, 2) into the ring buffer."""
        if len(chunk) == 0:
            return

        if chunk.ndim == 1:
            chunk = np.column_stack([chunk, chunk])

        num_samples = len(chunk)
        if num_samples >= self.max_samples:
            chunk = chunk[-self.max_samples:]
            num_samples = self.max_samples

        end_pos = self.write_pos + num_samples
        if end_pos <= self.max_samples:
            self.buffer[self.write_pos:end_pos] = chunk
            self.write_pos = end_pos % self.max_samples
        else:
            first_part = self.max_samples - self.write_pos
            self.buffer[self.write_pos:] = chunk[:first_part]
            second_part = num_samples - first_part
            self.buffer[:second_part] = chunk[first_part:]
            self.write_pos = second_part

        self.total_written += num_samples

    def get_buffered_audio(self) -> np.ndarray:
        """Returns ordered chronological array of all currently buffered audio."""
        if self.total_written < self.max_samples:
            return self.buffer[:self.write_pos].copy()
        # Ring wrap around: older part is from write_pos to end, newer part from 0 to write_pos
        return np.vstack([self.buffer[self.write_pos:], self.buffer[:self.write_pos]])

    def save_clip(self, output_dir: Path, custom_name: Optional[str] = None) -> Optional[Path]:
        """Saves current buffered audio into a 16-bit WAV file and returns its path."""
        audio = self.get_buffered_audio()
        if len(audio) == 0:
            return None

        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        name = custom_name or f"Clip_{timestamp}"
        filepath = output_dir / f"{name}.wav"

        # Convert float32 [-1.0, 1.0] to int16
        clipped = np.clip(audio, -1.0, 1.0)
        int16_data = (clipped * 32767).astype(np.int16)

        try:
            with wave.open(str(filepath), "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(int16_data.tobytes())
            return filepath
        except Exception as e:
            print(f"[InstantReplay] Error saving clip: {e}")
            return None
