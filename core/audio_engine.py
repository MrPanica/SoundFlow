"""
Master Audio Engine for SoundFlow Studio.
Coordinates multi-channel audio mixing, device I/O via sounddevice, soundboard playback,
app loopback mixing, radio streams, TTS, and microphone DSP processing.
"""

import threading
import time
import queue
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
    from .ptt_controller import PTTController
except ImportError:
    from core.voice_fx import VoiceFXProcessor
    from core.app_capture import AppCaptureManager
    from core.radio_streamer import RadioStreamer
    from core.instant_replay import InstantReplayBuffer
    from core.ptt_controller import PTTController


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
        self.app_stream_monitor_vol = 0.0  # 0.0 by default eliminates duplicate audio echo
        self.app_stream_mic_vol = 1.0
        self.radio_monitor_vol = 0.7
        self.radio_mic_vol = 0.9
        self._radio_monitor_enabled = True
        self._radio_mic_enabled = True
        self.tts_monitor_vol = 0.8
        self.tts_mic_vol = 1.0

        # Features state
        self.mic_passthrough_enabled = True
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

        # Incoming microphone audio buffer and decoupled jitter queues
        self._mic_in_buffer = np.zeros((self.buffer_size, 2), dtype=np.float32)
        self._mic_processed_buffer = np.zeros((self.buffer_size, 2), dtype=np.float32)
        self._mic_queue_monitor = queue.Queue(maxsize=4)
        self._mic_queue_target = queue.Queue(maxsize=4)

        # Voice recorder state
        self.mic_recording_active = False
        self.mic_recording_start_time = 0.0
        self._mic_recording_chunks: List[np.ndarray] = []

        # Callback for sound play state changes: func(sound_id: str, is_playing: bool)
        self.on_sound_state_changed: Optional[Callable[[str, bool], None]] = None
        # Callback for mic target device changes: func(device_id: Optional[int])
        self.on_mic_target_changed: Optional[Callable[[Optional[int]], None]] = None

        # Voice Ducking state
        self.ducking_enabled = True
        self.ducking_amount = 0.25
        self.ducking_threshold_db = -35.0
        self._ducking_current_gain = 1.0
        self._ducking_target_gain = 1.0
        self._ducking_hold_counter = 0

        # Loudness Normalization
        self.auto_normalize_enabled = True

        # Auto Push-to-Talk (PTT)
        self.ptt = PTTController()

    @property
    def app_stream_peak(self) -> float:
        return getattr(self.app_capture, "current_peak", 0.0)

    @property
    def radio_monitor_enabled(self) -> bool:
        return getattr(self, '_radio_monitor_enabled', True)

    @radio_monitor_enabled.setter
    def radio_monitor_enabled(self, val: bool):
        self._radio_monitor_enabled = bool(val)
        if hasattr(self, 'radio') and self.radio is not None:
            self.radio.monitor_output_enabled = self._radio_monitor_enabled and (self.monitor_stream is not None)

    @property
    def radio_mic_enabled(self) -> bool:
        return getattr(self, '_radio_mic_enabled', True)

    @radio_mic_enabled.setter
    def radio_mic_enabled(self, val: bool):
        self._radio_mic_enabled = bool(val)
        if hasattr(self, 'radio') and self.radio is not None:
            self.radio.mic_output_enabled = self._radio_mic_enabled and (self.mic_target_stream is not None)

    @property
    def is_audio_active(self) -> bool:
        """Returns True if any audio is actively playing, streaming, or passing through."""
        if bool(self.active_sounds):
            return True
        if self.tts_active_sound is not None and not self.tts_active_sound.is_finished():
            return True
        if self.radio.is_playing:
            return True
        if self.app_stream_enabled:
            return True
        if self.mic_passthrough_enabled:
            return True
        if self.monitor_peak > 0.02 or self.mic_peak > 0.02:
            return True
        return False

    @property
    def radio_stream_peak(self) -> float:
        """Returns the real-time peak volume of the radio/stream output [0.0, 1.0]."""
        if hasattr(self, "radio") and self.radio is not None and self.radio.is_playing:
            return getattr(self.radio, "current_peak", 0.0)
        return 0.0

    @property
    def app_stream_peak(self) -> float:
        """Returns the real-time peak volume of the captured application audio [0.0, 1.0]."""
        if hasattr(self, "app_capture") and self.app_capture is not None and self.app_capture.is_capturing:
            return getattr(self.app_capture, "current_peak", 0.0)
        return 0.0

    # ---------------- Device Querying ----------------
    @staticmethod
    def get_audio_devices() -> Dict[str, List[Dict[str, Any]]]:
        """Returns clean, deduplicated dictionary of inputs and outputs prioritizing WASAPI."""
        inputs = []
        outputs = []
        try:
            devs = sd.query_devices()
            hostapis = sd.query_hostapis()

            has_wasapi = False
            raw_inputs = []
            raw_outputs = []

            for i, d in enumerate(devs):
                api_name = hostapis[d["hostapi"]]["name"] if d["hostapi"] < len(hostapis) else "Unknown"
                api_lower = api_name.lower()
                # Completely skip low-level WDM-KS devices
                if "wdm-ks" in api_lower or "wdm" in api_lower:
                    continue

                if "wasapi" in api_lower:
                    has_wasapi = True

                info = {
                    "id": i,
                    "name": d["name"],
                    "hostapi": api_name,
                    "max_in": d["max_input_channels"],
                    "max_out": d["max_output_channels"],
                    "default_rate": d["default_samplerate"]
                }
                if d["max_input_channels"] > 0:
                    raw_inputs.append(info)
                if d["max_output_channels"] > 0:
                    raw_outputs.append(info)

            # If WASAPI is present on Windows, use WASAPI devices to eliminate all MME/DirectSound duplicates
            if has_wasapi:
                inputs = [d for d in raw_inputs if "wasapi" in d["hostapi"].lower()]
                outputs = [d for d in raw_outputs if "wasapi" in d["hostapi"].lower()]
            else:
                inputs = raw_inputs
                outputs = raw_outputs
        except Exception as e:
            print(f"[AudioEngine] Query devices error: {e}")

        return {"inputs": inputs, "outputs": outputs}

    @classmethod
    def get_default_devices(cls) -> Dict[str, Optional[int]]:
        """Intelligently detects best default monitor, mic target, and mic input device IDs."""
        devs = cls.get_audio_devices()
        inputs = devs.get("inputs", [])
        outputs = devs.get("outputs", [])

        # 1. Best physical microphone (non-virtual, non-cable)
        best_mic_in = None
        for d in inputs:
            n = d["name"].lower()
            if not any(k in n for k in ["cable", "virtual", "стерео микшер", "stereo mix"]):
                best_mic_in = d["id"]
                break
        if best_mic_in is None and inputs:
            best_mic_in = inputs[0]["id"]

        # 2. Best monitor output (headphones / speakers)
        best_monitor = None
        for d in outputs:
            n = d["name"].lower()
            if not any(k in n for k in ["cable", "virtual"]):
                best_monitor = d["id"]
                break
        if best_monitor is None and outputs:
            best_monitor = outputs[0]["id"]

        # 3. Best virtual cable target (CABLE Input, avoiding 16ch if 2ch exists)
        best_cable = None
        for d in outputs:
            n = d["name"].lower()
            if "cable input" in n and "16ch" not in n:
                best_cable = d["id"]
                break
        if best_cable is None:
            for d in outputs:
                n = d["name"].lower()
                if "cable" in n or "virtual" in n:
                    best_cable = d["id"]
                    break

        return {
            "monitor": best_monitor,
            "mic_target": best_cable,
            "mic_input": best_mic_in
        }

    @classmethod
    def get_target_mic_devices(cls) -> List[Dict[str, Any]]:
        """
        Returns a filtered and ordered list of output devices suitable for streaming into microphone.
        - Prioritizes virtual cables (CABLE Input, VoiceMeeter, etc.)
        - Excludes broken 16-channel endpoints (e.g. CABLE In 16ch)
        - Clearly differentiates virtual cables from physical playback devices
        """
        devs = cls.get_audio_devices()
        outputs = devs.get("outputs", [])
        cables = []
        others = []

        for d in outputs:
            name_lower = d["name"].lower()
            if "16ch" in name_lower:
                continue

            if any(k in name_lower for k in ["cable input", "vb-audio", "voicemeeter", "virtual cable", "line "]):
                display_name = d["name"]
                if "cable input" in name_lower:
                    display_name = f"{d['name']} ⭐ [Для игр и Discord]"
                cables.append({**d, "display_name": display_name, "is_virtual": True})
            else:
                display_name = f"{d['name']} (Физический выход)"
                others.append({**d, "display_name": display_name, "is_virtual": False})

        # Put virtual cables first so user immediately sees the right device
        return cables + others

    @classmethod
    def populate_target_mic_combobox(cls, combo, current_dev_id: Optional[int] = None) -> int:
        """
        Populates a target microphone combo box with clean labels and auto-selects current or best cable.
        Returns the selected index.
        """
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("-- Без трансляции в микрофон --", userData=None)

        devices = cls.get_target_mic_devices()
        selected_idx = 0
        cable_first_idx = None

        for d in devices:
            idx = combo.count()
            combo.addItem(d["display_name"], userData=d["id"])
            if d.get("is_virtual") and cable_first_idx is None:
                cable_first_idx = idx
            if current_dev_id is not None and d["id"] == current_dev_id:
                selected_idx = idx

        # If no specific device was saved or found, but virtual cable exists, auto-select it
        if selected_idx == 0 and current_dev_id is None and cable_first_idx is not None:
            selected_idx = cable_first_idx

        combo.setCurrentIndex(selected_idx)
        combo.blockSignals(False)
        return selected_idx


    def set_mic_target_device(self, device_id: Optional[int]) -> bool:
        """
        Safely changes or disables ONLY the target microphone output stream (e.g. VB-Audio CABLE Input),
        without stopping or restarting monitor headphones or physical microphone streams.
        """
        # If requested device is identical and stream is active, nothing to do
        if device_id == self.mic_target_device_id:
            if device_id is None or (self.mic_target_stream is not None and self.mic_target_stream.active):
                return True

        # Stop existing target mic stream safely
        if self.mic_target_stream is not None:
            try:
                self.mic_target_stream.stop()
                self.mic_target_stream.close()
            except Exception as e:
                print(f"[AudioEngine] Note closing previous mic target stream: {e}")
            self.mic_target_stream = None

        self.mic_target_device_id = device_id

        # If user selected None (-- Без трансляции в микрофон --)
        if device_id is None:
            if hasattr(self, 'radio') and self.radio is not None:
                self.radio.mic_output_enabled = False
            if self.on_mic_target_changed:
                try:
                    self.on_mic_target_changed(None)
                except Exception:
                    pass
            print("[AudioEngine] Mic target broadcast disabled (device=None)")
            return True

        # Do not allow opening mic target stream on the exact same device as monitor (prevents dual-claim conflicts)
        if self.monitor_device_id is not None and device_id == self.monitor_device_id:
            print(f"[AudioEngine] Mic target {device_id} is identical to monitor device, skipping separate stream.")
            if self.on_mic_target_changed:
                try:
                    self.on_mic_target_changed(device_id)
                except Exception:
                    pass
            return True

        try:
            self.mic_target_stream = sd.OutputStream(
                device=device_id,
                channels=2,
                samplerate=self.sample_rate,
                blocksize=self.buffer_size,
                callback=self._mic_target_callback
            )
            self.mic_target_stream.start()
            if hasattr(self, 'radio') and self.radio is not None:
                self.radio.mic_output_enabled = self._radio_mic_enabled
            if self.on_mic_target_changed:
                try:
                    self.on_mic_target_changed(device_id)
                except Exception:
                    pass
            print(f"[AudioEngine] Mic target stream started on device {device_id}")
            return True
        except Exception as e:
            print(f"[AudioEngine] Failed to start mic target stream on device {device_id}: {e}")
            self.mic_target_stream = None
            self.mic_target_device_id = None
            if self.on_mic_target_changed:
                try:
                    self.on_mic_target_changed(None)
                except Exception:
                    pass
            return False

    def initialize_streams(
        self,
        monitor_device: Optional[int] = None,
        mic_target_device: Optional[int] = None,
        mic_input_device: Optional[int] = None,
        explicit_target_set: bool = False
    ):
        """Initializes or updates the audio output and input streams with auto-detection fallback."""
        self.stop_streams()

        defaults = self.get_default_devices()
        devs = self.get_audio_devices()
        valid_input_ids = {d["id"] for d in devs.get("inputs", [])}
        valid_output_ids = {d["id"] for d in devs.get("outputs", [])}

        # Resolve monitor device
        if monitor_device is None or monitor_device not in valid_output_ids:
            monitor_device = defaults.get("monitor")
        self.monitor_device_id = monitor_device

        # Resolve mic target device
        if mic_target_device is not None and mic_target_device in valid_output_ids:
            tgt_name = next((d["name"].lower() for d in devs.get("outputs", []) if d["id"] == mic_target_device), "")
            if "16ch" in tgt_name and defaults.get("mic_target") is not None:
                mic_target_device = defaults.get("mic_target")
        elif not explicit_target_set and mic_target_device is None:
            # Only auto-fallback on initial setup if caller did not explicitly request None
            mic_target_device = defaults.get("mic_target")

        # Resolve mic input device
        if mic_input_device is None or mic_input_device not in valid_input_ids:
            mic_input_device = defaults.get("mic_input")
        self.mic_input_device_id = mic_input_device

        # 1. Open Monitor Output Stream
        if self.monitor_device_id is not None:
            try:
                self.monitor_stream = sd.OutputStream(
                    device=self.monitor_device_id,
                    channels=2,
                    samplerate=self.sample_rate,
                    blocksize=self.buffer_size,
                    callback=self._monitor_callback
                )
                self.monitor_stream.start()
                if hasattr(self, 'radio') and self.radio is not None:
                    self.radio.monitor_output_enabled = self._radio_monitor_enabled
            except Exception as e:
                print(f"[AudioEngine] Failed to start monitor stream on device {self.monitor_device_id}: {e}")

        # 2. Open Target Mic Output Stream safely via set_mic_target_device
        self.set_mic_target_device(mic_target_device)

        # 3. Open Microphone Input Stream
        if self.mic_input_device_id is not None:
            self.start_mic_input(self.mic_input_device_id)

    def start_mic_input(self, device_id: Optional[int] = None) -> bool:
        """Starts or restarts the physical microphone input stream."""
        if device_id is not None:
            self.mic_input_device_id = device_id
        elif self.mic_input_device_id is None:
            self.mic_input_device_id = self.get_default_devices().get("mic_input")

        if self.mic_input_device_id is None:
            print("[AudioEngine] No valid microphone input device available.")
            return False

        if self.mic_input_stream is not None:
            try:
                if self.mic_input_stream.active and getattr(self.mic_input_stream, "device", None) == self.mic_input_device_id:
                    return True
                self.mic_input_stream.stop()
                self.mic_input_stream.close()
            except Exception:
                pass
            self.mic_input_stream = None

        self._clear_mic_queues()

        try:
            self.mic_input_stream = sd.InputStream(
                device=self.mic_input_device_id,
                channels=1,
                samplerate=self.sample_rate,
                blocksize=self.buffer_size,
                callback=self._mic_input_callback
            )
            self.mic_input_stream.start()
            print(f"[AudioEngine] Microphone input stream started on device {self.mic_input_device_id}")
            return True
        except Exception as e:
            print(f"[AudioEngine] Failed to start mic input stream on device {self.mic_input_device_id}: {e}")
            self.mic_input_stream = None
            return False

    def stop_mic_input(self):
        """Stops the microphone input stream."""
        if self.mic_input_stream is not None:
            try:
                self.mic_input_stream.stop()
                self.mic_input_stream.close()
            except Exception:
                pass
            self.mic_input_stream = None
        self._clear_mic_queues()
        self.mic_in_peak = 0.0

    def _clear_mic_queues(self):
        for q in (self._mic_queue_monitor, self._mic_queue_target):
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

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
        if hasattr(self, 'radio') and self.radio is not None:
            self.radio.monitor_output_enabled = False
            self.radio.mic_output_enabled = False
        self._clear_mic_queues()

    # ---------------- Callbacks ----------------
    def _mic_input_callback(self, indata, frames, time_info, status):
        """Receives raw microphone data, processes DSP effects once, and distributes to queues."""
        if status:
            pass
        mono = indata[:, 0]
        # Calculate mic input peak for UI meter
        peak = float(np.max(np.abs(mono))) if len(mono) > 0 else 0.0
        self.mic_in_peak = peak

        # Voice Ducking detection
        if getattr(self, "ducking_enabled", True) and len(mono) > 0:
            mic_rms = float(np.sqrt(np.mean(mono**2))) + 1e-9
            mic_db = 20.0 * np.log10(mic_rms)
            if mic_db > getattr(self, "ducking_threshold_db", -35.0):
                self._ducking_target_gain = getattr(self, "ducking_amount", 0.25)
                self._ducking_hold_counter = int(0.35 * self.sample_rate)
            else:
                if self._ducking_hold_counter > 0:
                    self._ducking_hold_counter -= len(mono)
                else:
                    self._ducking_target_gain = 1.0

        # Stereo buffer
        raw_stereo = np.column_stack([mono, mono])
        self._mic_in_buffer = raw_stereo
        if self.mic_passthrough_enabled or getattr(self, "mic_recording_active", False):
            processed = self.voice_fx.process(raw_stereo)
        else:
            processed = raw_stereo
        self._mic_processed_buffer = processed

        if getattr(self, "mic_recording_active", False):
            if hasattr(self, "_mic_recording_chunks"):
                self._mic_recording_chunks.append(processed.copy())

        # Push to monitor preview queue
        if self.mic_monitor_preview:
            if self._mic_queue_monitor.full():
                try:
                    self._mic_queue_monitor.get_nowait()
                except queue.Empty:
                    pass
            try:
                self._mic_queue_monitor.put_nowait(processed)
            except queue.Full:
                pass

        # Push to mic target queue
        if self._mic_queue_target.full():
            try:
                self._mic_queue_target.get_nowait()
            except queue.Empty:
                pass
        try:
            self._mic_queue_target.put_nowait(processed)
        except queue.Full:
            pass

    def _monitor_callback(self, outdata, frames, time_info, status):
        """Mixes audio for the user's headphones/speakers."""
        out = np.zeros((frames, 2), dtype=np.float32)

        # Smooth ducking gain
        if getattr(self, "ducking_enabled", True):
            alpha = 0.18 if self._ducking_target_gain < self._ducking_current_gain else 0.03
            self._ducking_current_gain += (self._ducking_target_gain - self._ducking_current_gain) * alpha
        else:
            self._ducking_current_gain = 1.0
        duck = self._ducking_current_gain

        with self._lock:
            mic_active = (self.mic_target_stream is not None)

            # 1. Mix Soundboard sounds (monitor channel)
            finished_ids = []
            for sid, sound in list(self.active_sounds.items()):
                mon_chunk = sound.read_chunk_monitor(frames)
                out += mon_chunk * self.soundboard_monitor_vol * duck
                if not mic_active:
                    sound.finished_mic = True
                if sound.is_finished:
                    finished_ids.append(sid)

            for sid in finished_ids:
                sound = self.active_sounds.pop(sid, None)
                if sound and sound.play_mic:
                    if hasattr(self, "ptt") and self.ptt:
                        self.ptt.stop_broadcast()
                if self.on_sound_state_changed:
                    self.on_sound_state_changed(sid, False)

            # 2. Mix App Audio Capture (monitor channel)
            # Only mix into headphones if monitor volume is explicitly raised > 0 AND mute_self is false
            if self.app_stream_enabled and self.app_stream_monitor_vol > 0.001 and not getattr(self.app_capture, "mute_self", False):
                app_chunk = self.app_capture.get_chunk_monitor()
                if app_chunk is not None:
                    chunk_len = len(app_chunk)
                    if chunk_len == frames:
                        out += app_chunk * self.app_stream_monitor_vol * duck
                    elif chunk_len > frames:
                        out += app_chunk[:frames] * self.app_stream_monitor_vol * duck
                    elif chunk_len > 0:
                        out[:chunk_len] += app_chunk * self.app_stream_monitor_vol * duck

            # 3. Mix Radio Stream (monitor channel)
            if self.radio.is_playing and self.radio_monitor_enabled:
                radio_chunk = self.radio.read_frames_monitor(frames)
                if radio_chunk is not None:
                    chunk_len = len(radio_chunk)
                    if chunk_len == frames:
                        out += radio_chunk * self.radio_monitor_vol * duck
                    elif chunk_len > frames:
                        out += radio_chunk[:frames] * self.radio_monitor_vol * duck
                    elif chunk_len > 0:
                        out[:chunk_len] += radio_chunk * self.radio_monitor_vol * duck

            # 4. Mix TTS (monitor channel)
            if self.tts_active_sound:
                if not mic_active:
                    self.tts_active_sound.finished_mic = True
                if not self.tts_active_sound.finished_monitor:
                    tts_mon = self.tts_active_sound.read_chunk_monitor(frames)
                    out += tts_mon * self.tts_monitor_vol * duck
                if self.tts_active_sound.is_finished:
                    if self.tts_active_sound.play_mic and hasattr(self, "ptt") and self.ptt:
                        self.ptt.stop_broadcast()
                    self.tts_active_sound = None

            # 5. Mix Live Microphone Preview ("Hear Myself" in headphones)
            if self.mic_passthrough_enabled and self.mic_monitor_preview:
                try:
                    mic_chunk = self._mic_queue_monitor.get_nowait()
                    chunk_len = len(mic_chunk)
                    if chunk_len == frames:
                        out += mic_chunk * self.mic_preview_volume
                    elif chunk_len > frames:
                        out += mic_chunk[:frames] * self.mic_preview_volume
                    elif chunk_len > 0:
                        out[:chunk_len] += mic_chunk * self.mic_preview_volume
                except queue.Empty:
                    pass

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
            duck = getattr(self, "_ducking_current_gain", 1.0)

            # 1. Microphone Passthrough + DSP Effects
            if self.mic_passthrough_enabled:
                try:
                    mic_chunk = self._mic_queue_target.get_nowait()
                    chunk_len = len(mic_chunk)
                    if chunk_len == frames:
                        out += mic_chunk
                    elif chunk_len > frames:
                        out += mic_chunk[:frames]
                    elif chunk_len > 0:
                        out[:chunk_len] += mic_chunk
                except queue.Empty:
                    pass

            # 2. Soundboard sounds (mic channel)
            finished_ids = []
            for sid, sound in list(self.active_sounds.items()):
                mic_chunk = sound.read_chunk_mic(frames)
                out += mic_chunk * self.soundboard_mic_vol * duck
                if not mon_active:
                    sound.finished_monitor = True
                if sound.is_finished:
                    finished_ids.append(sid)

            for sid in finished_ids:
                sound = self.active_sounds.pop(sid, None)
                if sound and sound.play_mic:
                    if hasattr(self, "ptt") and self.ptt:
                        self.ptt.stop_broadcast()
                if self.on_sound_state_changed:
                    self.on_sound_state_changed(sid, False)

            # 3. App Audio Stream (mic channel)
            if self.app_stream_enabled:
                app_chunk = self.app_capture.get_chunk_mic()
                if app_chunk is not None:
                    chunk_len = len(app_chunk)
                    if chunk_len == frames:
                        out += app_chunk * self.app_stream_mic_vol * duck
                    elif chunk_len > frames:
                        out += app_chunk[:frames] * self.app_stream_mic_vol * duck
                    elif chunk_len > 0:
                        out[:chunk_len] += app_chunk * self.app_stream_mic_vol * duck

            # 4. Radio Stream (mic channel)
            if self.radio.is_playing and self.radio_mic_enabled:
                radio_chunk = self.radio.read_frames_mic(frames)
                if radio_chunk is not None:
                    chunk_len = len(radio_chunk)
                    if chunk_len == frames:
                        out += radio_chunk * self.radio_mic_vol * duck
                    elif chunk_len > frames:
                        out += radio_chunk[:frames] * self.radio_mic_vol * duck
                    elif chunk_len > 0:
                        out[:chunk_len] += radio_chunk * self.radio_mic_vol * duck

            # 5. TTS (mic channel)
            if self.tts_active_sound:
                if not mon_active:
                    self.tts_active_sound.finished_monitor = True
                if not self.tts_active_sound.finished_mic:
                    tts_mic = self.tts_active_sound.read_chunk_mic(frames)
                    out += tts_mic * self.tts_mic_vol * duck
                if self.tts_active_sound.is_finished:
                    if self.tts_active_sound.play_mic and hasattr(self, "ptt") and self.ptt:
                        self.ptt.stop_broadcast()
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

        # Loudness Normalization
        if getattr(self, "auto_normalize_enabled", True) and len(sound_data) > 0:
            peak = float(np.max(np.abs(sound_data)))
            if peak > 0.01:
                rms = float(np.sqrt(np.mean(sound_data**2))) + 1e-7
                target_rms = 0.16
                norm_gain = min(target_rms / rms, 0.95 / peak)
                norm_gain = float(np.clip(norm_gain, 0.2, 3.5))
                sound_data = sound_data * norm_gain

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

        if hasattr(self, "ptt") and self.ptt:
            self.ptt.start_broadcast()

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

    def is_sound_playing(self, sound_id: str) -> bool:
        """Returns True if the specified sound is currently playing."""
        with self._lock:
            active = self.active_sounds.get(sound_id)
            return active is not None and not active.is_finished

    def stop_sound(self, sound_id: str):
        with self._lock:
            sound = self.active_sounds.pop(sound_id, None)
            if sound and sound.play_mic:
                if hasattr(self, "ptt") and self.ptt:
                    self.ptt.stop_broadcast()
        if self.on_sound_state_changed:
            self.on_sound_state_changed(sound_id, False)

    def stop_all(self):
        """Instantly stops all sounds, radio, and TTS."""
        with self._lock:
            self.active_sounds.clear()
            self.tts_active_sound = None
        if hasattr(self, "ptt") and self.ptt:
            self.ptt.force_release()
        self.radio.stop()
        self.app_stream_enabled = False
        if hasattr(self, "app_capture") and getattr(self.app_capture, "is_capturing", False):
            self.app_capture.stop_capture()

    def stop_tts(self):
        """Immediately stops any ongoing TTS speech playback."""
        with self._lock:
            prev = self.tts_active_sound
            self.tts_active_sound = None
        if prev and prev.play_mic:
            if hasattr(self, "ptt") and self.ptt:
                self.ptt.stop_broadcast()

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

        if play_mic and hasattr(self, "ptt") and self.ptt:
            self.ptt.start_broadcast()

    @property
    def is_audio_active(self) -> bool:
        """Returns True if any audio is actively playing or sound is passing to mic/monitor."""
        with self._lock:
            if len(self.active_sounds) > 0 or self.tts_active_sound is not None:
                return True
        if getattr(self.radio, "is_playing", False):
            return True
        if getattr(self, "app_stream_enabled", False):
            return True
        if getattr(self, "mic_passthrough_enabled", False) and getattr(self, "mic_in_peak", 0.0) > 0.03:
            return True
        if getattr(self, "monitor_peak", 0.0) > 0.03 or getattr(self, "mic_peak", 0.0) > 0.03:
            return True
        return False

    # ---------------- Voice Recorder ----------------
    def start_mic_recording(self):
        """Starts recording audio from microphone with active voice changer FX."""
        with self._lock:
            self._mic_recording_chunks = []
            self.mic_recording_start_time = time.time()
            self.mic_recording_active = True
        # Ensure microphone stream is actively running
        if self.mic_input_stream is None or not self.mic_input_stream.active:
            self.start_mic_input(self.mic_input_device_id)

    def stop_mic_recording(self, output_path: Path) -> bool:
        """Stops recording and saves accumulated audio to 16-bit stereo WAV."""
        with self._lock:
            self.mic_recording_active = False
            chunks = list(getattr(self, "_mic_recording_chunks", []))
            self._mic_recording_chunks = []
        if not chunks:
            return False
        try:
            import wave
            audio = np.vstack(chunks)
            int_data = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(int_data.tobytes())
            return True
        except Exception as e:
            print(f"[AudioEngine] Failed to save recorded audio file {output_path}: {e}")
            return False

    def get_mic_recording_duration(self) -> float:
        """Returns elapsed recording duration in seconds."""
        if getattr(self, "mic_recording_active", False):
            return max(0.0, time.time() - getattr(self, "mic_recording_start_time", time.time()))
        return 0.0
