"""
Master Audio Engine for SoundFlow Studio.
Coordinates multi-channel audio mixing, device I/O via sounddevice, soundboard playback,
app loopback mixing, radio streams, TTS, and microphone DSP processing.
"""

import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable
import numpy as np
import sounddevice as sd
import miniaudio

try:
    from .voice_fx import VoiceFXProcessor
    from .app_capture import AppCaptureManager
    from .radio_streamer import RadioStreamer
    from .instant_replay import InstantReplayBuffer
except ImportError:
    from core.voice_fx import VoiceFXProcessor
    from core.app_capture import AppCaptureManager
    from core.radio_streamer import RadioStreamer
    from core.instant_replay import InstantReplayBuffer


class ActiveSound:
    """Represents an actively playing sound instance with independent stream pointers."""
    def __init__(
        self,
        sound_id: str,
        buffer: np.ndarray,
        volume: float = 1.0,
        play_monitor: bool = True,
        play_mic: bool = True,
        loop: bool = False
    ):
        self.sound_id = sound_id
        self.buffer = buffer  # shape: (N, 2), float32
        self.volume = volume
        self.play_monitor = play_monitor
        self.play_mic = play_mic
        self.loop = loop
        self.pos_monitor = 0
        self.pos_mic = 0
        self.finished_monitor = not play_monitor
        self.finished_mic = not play_mic

    @property
    def is_finished(self) -> bool:
        m_done = self.finished_monitor or not self.play_monitor
        mic_done = self.finished_mic or not self.play_mic
        return m_done and mic_done

    def _read_slice(self, current_pos: int, num_frames: int) -> Tuple[np.ndarray, int, bool]:
        total_len = len(self.buffer)
        if total_len == 0:
            return np.zeros((num_frames, 2), dtype=np.float32), 0, True

        end_pos = current_pos + num_frames
        if end_pos <= total_len:
            raw = self.buffer[current_pos:end_pos]
            new_pos = end_pos
            finished = False
            if new_pos >= total_len:
                if self.loop:
                    new_pos = 0
                else:
                    finished = True
            return raw, new_pos, finished
        else:
            first_part = self.buffer[current_pos:]
            rem = num_frames - (total_len - current_pos)
            if self.loop:
                second_part = self.buffer[:rem]
                raw = np.vstack([first_part, second_part])
                new_pos = rem
                finished = False
            else:
                padding = np.zeros((rem, 2), dtype=np.float32)
                raw = np.vstack([first_part, padding])
                new_pos = total_len
                finished = True
            return raw, new_pos, finished

    def read_chunk_monitor(self, num_frames: int) -> np.ndarray:
        if not self.play_monitor or self.finished_monitor:
            return np.zeros((num_frames, 2), dtype=np.float32)
        chunk, self.pos_monitor, self.finished_monitor = self._read_slice(self.pos_monitor, num_frames)
        return chunk * self.volume

    def read_chunk_mic(self, num_frames: int) -> np.ndarray:
        if not self.play_mic or self.finished_mic:
            return np.zeros((num_frames, 2), dtype=np.float32)
        chunk, self.pos_mic, self.finished_mic = self._read_slice(self.pos_mic, num_frames)
        return chunk * self.volume

    def read_chunk(self, num_frames: int) -> Tuple[np.ndarray, np.ndarray]:
        """Backwards compatible read_chunk."""
        return self.read_chunk_monitor(num_frames), self.read_chunk_mic(num_frames)

    def seek(self, frame_idx: int):
        target = max(0, min(len(self.buffer) - 1, frame_idx)) if len(self.buffer) > 0 else 0
        self.pos_monitor = target
        self.pos_mic = target
        self.finished_monitor = not self.play_monitor
        self.finished_mic = not self.play_mic

    def seek_ratio(self, ratio: float):
        total = len(self.buffer)
        frame_idx = int(np.clip(ratio, 0.0, 1.0) * (total - 1)) if total > 0 else 0
        self.seek(frame_idx)

    def get_progress(self, sample_rate: int = 48000) -> Tuple[float, float, float]:
        """Returns (current_time_sec, total_time_sec, progress_ratio)."""
        total = len(self.buffer)
        curr = self.pos_monitor if self.play_monitor else self.pos_mic
        total_sec = total / float(sample_rate) if sample_rate > 0 else 0.0
        curr_sec = curr / float(sample_rate) if sample_rate > 0 else 0.0
        ratio = curr / total if total > 0 else 0.0
        return curr_sec, total_sec, ratio



class AudioEngine:
    """Master Audio Mixing and Device I/O Engine."""

    def __init__(self, sample_rate: int = 48000, buffer_size: int = 1024):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size

        # Sub-modules
        self.voice_fx = VoiceFXProcessor(sample_rate=sample_rate)
        self.app_capture = AppCaptureManager(sample_rate=sample_rate, buffer_size=buffer_size)
        self.radio = RadioStreamer(sample_rate=sample_rate, buffer_size=buffer_size)
        self.instant_replay = InstantReplayBuffer(duration_sec=30, sample_rate=sample_rate)

        # Audio streams
        self.monitor_stream: Optional[sd.OutputStream] = None
        self.mic_target_stream: Optional[sd.OutputStream] = None
        self.mic_input_stream: Optional[sd.InputStream] = None

        # Device IDs
        self.monitor_device_id: Optional[int] = None
        self.mic_target_device_id: Optional[int] = None
        self.mic_input_device_id: Optional[int] = None

        # Master & channel volumes (0.0 to 1.5)
        self.master_monitor_volume = 1.0
        self.master_mic_volume = 1.0
        self.soundboard_monitor_vol = 1.0
        self.soundboard_mic_vol = 1.0
        self.app_stream_monitor_vol = 0.8
        self.app_stream_mic_vol = 1.0
        self.radio_monitor_vol = 0.7
        self.radio_mic_vol = 0.9
        self.radio_monitor_enabled = True
        self.radio_mic_enabled = True
        self.tts_monitor_vol = 0.8
        self.tts_mic_vol = 1.0

        # Features state
        self.mic_passthrough_enabled = False
        self.mic_monitor_preview = False
        self.mic_preview_volume = 1.0
        self.app_stream_enabled = False
        self.tts_active_sound: Optional[ActiveSound] = None
        self.last_played_sound_id: Optional[str] = None

        # Active playing sounds
        self.active_sounds: Dict[str, ActiveSound] = {}
        self.sound_cache: Dict[str, np.ndarray] = {}
        self._lock = threading.Lock()

        # Metering levels: [0.0, 1.0]
        self.monitor_peak = 0.0
        self.mic_peak = 0.0
        self.mic_in_peak = 0.0

        # Incoming microphone audio buffer
        self._mic_in_buffer = np.zeros((self.buffer_size, 2), dtype=np.float32)
        self._mic_processed_buffer = np.zeros((self.buffer_size, 2), dtype=np.float32)

        # Callback for sound play state changes: func(sound_id: str, is_playing: bool)
        self.on_sound_state_changed: Optional[Callable[[str, bool], None]] = None

    # ---------------- Device Querying ----------------
    @staticmethod
    def get_audio_devices() -> Dict[str, List[Dict[str, Any]]]:
        """Returns structured dictionary of inputs and outputs."""
        inputs = []
        outputs = []
        try:
            devs = sd.query_devices()
            hostapis = sd.query_hostapis()

            for i, d in enumerate(devs):
                api_name = hostapis[d["hostapi"]]["name"] if d["hostapi"] < len(hostapis) else "Unknown"
                info = {
                    "id": i,
                    "name": d["name"],
                    "hostapi": api_name,
                    "max_in": d["max_input_channels"],
                    "max_out": d["max_output_channels"],
                    "default_rate": d["default_samplerate"]
                }
                if d["max_input_channels"] > 0:
                    inputs.append(info)
                if d["max_output_channels"] > 0:
                    outputs.append(info)
        except Exception as e:
            print(f"[AudioEngine] Query devices error: {e}")

        return {"inputs": inputs, "outputs": outputs}

    def initialize_streams(
        self,
        monitor_device: Optional[int] = None,
        mic_target_device: Optional[int] = None,
        mic_input_device: Optional[int] = None
    ):
        """Initializes or updates the audio output and input streams."""
        self.stop_streams()

        self.monitor_device_id = monitor_device
        self.mic_target_device_id = mic_target_device
        self.mic_input_device_id = mic_input_device

        # 1. Open Monitor Output Stream
        try:
            self.monitor_stream = sd.OutputStream(
                device=self.monitor_device_id,
                channels=2,
                samplerate=self.sample_rate,
                blocksize=self.buffer_size,
                callback=self._monitor_callback
            )
            self.monitor_stream.start()
        except Exception as e:
            print(f"[AudioEngine] Failed to start monitor stream on device {self.monitor_device_id}: {e}")

        # 2. Open Target Mic Output Stream (if specified and different)
        if self.mic_target_device_id is not None and self.mic_target_device_id != self.monitor_device_id:
            try:
                self.mic_target_stream = sd.OutputStream(
                    device=self.mic_target_device_id,
                    channels=2,
                    samplerate=self.sample_rate,
                    blocksize=self.buffer_size,
                    callback=self._mic_target_callback
                )
                self.mic_target_stream.start()
            except Exception as e:
                print(f"[AudioEngine] Failed to start mic target stream on device {self.mic_target_device_id}: {e}")

        # 3. Open Microphone Input Stream (if selected)
        if self.mic_input_device_id is not None:
            try:
                self.mic_input_stream = sd.InputStream(
                    device=self.mic_input_device_id,
                    channels=1,
                    samplerate=self.sample_rate,
                    blocksize=self.buffer_size,
                    callback=self._mic_input_callback
                )
                self.mic_input_stream.start()
            except Exception as e:
                print(f"[AudioEngine] Failed to start mic input stream: {e}")

    def stop_streams(self):
        """Safely stops and closes all active streams."""
        for stream in [self.monitor_stream, self.mic_target_stream, self.mic_input_stream]:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self.monitor_stream = None
        self.mic_target_stream = None
        self.mic_input_stream = None

    # ---------------- Callbacks ----------------
    def _mic_input_callback(self, indata, frames, time_info, status):
        """Receives raw microphone data, processes DSP effects once, and stores in intermediate buffer."""
        if status:
            pass
        mono = indata[:, 0]
        # Calculate mic input peak for UI meter
        peak = float(np.max(np.abs(mono))) if len(mono) > 0 else 0.0
        self.mic_in_peak = peak
        # Stereo buffer
        raw_stereo = np.column_stack([mono, mono])
        self._mic_in_buffer = raw_stereo
        if self.mic_passthrough_enabled:
            self._mic_processed_buffer = self.voice_fx.process(raw_stereo)
        else:
            self._mic_processed_buffer = raw_stereo

    def _monitor_callback(self, outdata, frames, time_info, status):
        """Mixes audio for the user's headphones/speakers."""
        out = np.zeros((frames, 2), dtype=np.float32)

        with self._lock:
            mic_active = (self.mic_target_stream is not None)

            # 1. Mix Soundboard sounds (monitor channel)
            finished_ids = []
            for sid, sound in list(self.active_sounds.items()):
                mon_chunk = sound.read_chunk_monitor(frames)
                out += mon_chunk * self.soundboard_monitor_vol
                if not mic_active:
                    sound.finished_mic = True
                if sound.is_finished:
                    finished_ids.append(sid)

            for sid in finished_ids:
                if sid in self.active_sounds:
                    del self.active_sounds[sid]
                if self.on_sound_state_changed:
                    self.on_sound_state_changed(sid, False)

            # 2. Mix App Audio Capture (monitor channel)
            if self.app_stream_enabled:
                app_chunk = self.app_capture.get_chunk_monitor()
                if app_chunk is not None and len(app_chunk) == frames:
                    out += app_chunk * self.app_stream_monitor_vol

            # 3. Mix Radio Stream (monitor channel)
            if self.radio.is_playing:
                radio_chunk = self.radio.get_chunk_monitor()
                if radio_chunk is not None and len(radio_chunk) == frames and self.radio_monitor_enabled:
                    out += radio_chunk * self.radio_monitor_vol

            # 4. Mix TTS (monitor channel)
            if self.tts_active_sound:
                if not mic_active:
                    self.tts_active_sound.finished_mic = True
                if not self.tts_active_sound.finished_monitor:
                    tts_mon = self.tts_active_sound.read_chunk_monitor(frames)
                    out += tts_mon * self.tts_monitor_vol
                if self.tts_active_sound.is_finished:
                    self.tts_active_sound = None

            # 5. Mix Live Microphone Preview ("Hear Myself" in headphones)
            if self.mic_passthrough_enabled and self.mic_monitor_preview:
                out += self._mic_processed_buffer[:frames] * self.mic_preview_volume

        # Apply master monitor volume
        out *= self.master_monitor_volume

        # Peak meter
        self.monitor_peak = float(np.max(np.abs(out))) if len(out) > 0 else 0.0

        # Push to instant replay buffer
        self.instant_replay.push(out)

        # Output with soft limiter
        np.clip(out, -1.0, 1.0, out=outdata)

    def _mic_target_callback(self, outdata, frames, time_info, status):
        """Mixes audio destined for the Virtual Microphone (Discord, Games)."""
        out = np.zeros((frames, 2), dtype=np.float32)

        with self._lock:
            mon_active = (self.monitor_stream is not None)

            # 1. Microphone Passthrough + DSP Effects
            if self.mic_passthrough_enabled:
                out += self._mic_processed_buffer[:frames]

            # 2. Soundboard sounds (mic channel)
            finished_ids = []
            for sid, sound in list(self.active_sounds.items()):
                mic_chunk = sound.read_chunk_mic(frames)
                out += mic_chunk * self.soundboard_mic_vol
                if not mon_active:
                    sound.finished_monitor = True
                if sound.is_finished:
                    finished_ids.append(sid)

            for sid in finished_ids:
                if sid in self.active_sounds:
                    del self.active_sounds[sid]
                if self.on_sound_state_changed:
                    self.on_sound_state_changed(sid, False)

            # 3. App Audio Stream (mic channel)
            if self.app_stream_enabled:
                app_chunk = self.app_capture.get_chunk_mic()
                if app_chunk is not None and len(app_chunk) == frames:
                    out += app_chunk * self.app_stream_mic_vol

            # 4. Radio Stream (mic channel)
            if self.radio.is_playing:
                radio_chunk = self.radio.get_chunk_mic()
                if radio_chunk is not None and len(radio_chunk) == frames and self.radio_mic_enabled:
                    out += radio_chunk * self.radio_mic_vol

            # 5. TTS (mic channel)
            if self.tts_active_sound:
                if not mon_active:
                    self.tts_active_sound.finished_monitor = True
                if not self.tts_active_sound.finished_mic:
                    tts_mic = self.tts_active_sound.read_chunk_mic(frames)
                    out += tts_mic * self.tts_mic_vol
                if self.tts_active_sound.is_finished:
                    self.tts_active_sound = None

        # Apply master mic volume
        out *= self.master_mic_volume

        # Mic peak meter
        self.mic_peak = float(np.max(np.abs(out))) if len(out) > 0 else 0.0

        # Output with soft limiter
        np.clip(out, -1.0, 1.0, out=outdata)

    # ---------------- Soundboard Control ----------------
    def load_audio_file(self, filepath: str) -> Optional[np.ndarray]:
        """Loads and decodes any audio file into float32 stereo array."""
        if filepath in self.sound_cache:
            return self.sound_cache[filepath]

        try:
            decoded = miniaudio.decode_file(
                filepath,
                output_format=miniaudio.SampleFormat.FLOAT32,
                nchannels=2,
                sample_rate=self.sample_rate
            )
            arr = np.array(decoded.samples, dtype=np.float32).reshape(-1, 2)
            self.sound_cache[filepath] = arr
            return arr
        except Exception as e:
            print(f"[AudioEngine] Error decoding {filepath}: {e}")
            return None

    def play_sound(
        self,
        sound_id: str,
        filepath: str,
        volume: float = 1.0,
        pitch: float = 1.0,
        speed: float = 1.0,
        trim_start: float = 0.0,
        trim_end: float = 0.0,
        loop: bool = False
    ) -> bool:
        """Starts playback of a sound by ID."""
        buffer = self.load_audio_file(filepath)
        if buffer is None or len(buffer) == 0:
            return False

        # Apply trimming if set
        start_frame = int(trim_start * self.sample_rate)
        end_frame = len(buffer) - int(trim_end * self.sample_rate)
        if 0 <= start_frame < end_frame <= len(buffer):
            sound_data = buffer[start_frame:end_frame]
        else:
            sound_data = buffer

        # Speed/pitch resampling if needed
        factor = speed * pitch
        if abs(factor - 1.0) > 0.03:
            orig_len = len(sound_data)
            new_len = int(orig_len / factor)
            if new_len > 10:
                resampled = np.zeros((new_len, 2), dtype=np.float32)
                orig_idx = np.arange(orig_len)
                target_idx = np.linspace(0, orig_len - 1, new_len)
                resampled[:, 0] = np.interp(target_idx, orig_idx, sound_data[:, 0])
                resampled[:, 1] = np.interp(target_idx, orig_idx, sound_data[:, 1])
                sound_data = resampled

        active = ActiveSound(
            sound_id=sound_id,
            buffer=sound_data,
            volume=volume,
            play_monitor=True,
            play_mic=True,
            loop=loop
        )

        with self._lock:
            self.active_sounds[sound_id] = active
            self.last_played_sound_id = sound_id

        if self.on_sound_state_changed:
            self.on_sound_state_changed(sound_id, True)

        return True

    def seek_sound(self, sound_id: str, ratio: float):
        """Seeks sound to a relative position 0.0 .. 1.0."""
        with self._lock:
            if sound_id in self.active_sounds:
                self.active_sounds[sound_id].seek_ratio(ratio)

    def get_sound_progress(self, sound_id: str) -> Optional[Tuple[float, float, float]]:
        """Returns (current_time_sec, total_time_sec, progress_ratio) or None if not playing."""
        with self._lock:
            if sound_id in self.active_sounds:
                return self.active_sounds[sound_id].get_progress(self.sample_rate)
        return None

    def get_sound_buffer(self, filepath: str) -> Optional[np.ndarray]:
        """Loads and returns the decoded float32 stereo buffer."""
        return self.load_audio_file(filepath)

    def stop_sound(self, sound_id: str):
        with self._lock:
            if sound_id in self.active_sounds:
                del self.active_sounds[sound_id]
        if self.on_sound_state_changed:
            self.on_sound_state_changed(sound_id, False)

    def stop_all(self):
        """Instantly stops all sounds, radio, and TTS."""
        with self._lock:
            self.active_sounds.clear()
            self.tts_active_sound = None
        self.radio.stop()
        self.app_stream_enabled = False

    def stop_tts(self):
        """Immediately stops any ongoing TTS speech playback."""
        with self._lock:
            self.tts_active_sound = None

    def play_tts_samples(self, samples: np.ndarray, play_monitor: bool = True, play_mic: bool = True):
        """Plays TTS samples into mic and/or monitor."""
        if samples is None or len(samples) == 0:
            return
        # Stop previous TTS playback first
        self.stop_tts()
        active = ActiveSound(
            sound_id="__tts__",
            buffer=samples,
            volume=1.0,
            play_monitor=play_monitor,
            play_mic=play_mic,
            loop=False
        )
        with self._lock:
            self.tts_active_sound = active
