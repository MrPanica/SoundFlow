"""
Windows Application & System Audio Capture for SoundFlow Studio.
Uses pycaw to detect audio-producing applications and PyAudioWPatch for high-performance WASAPI loopback capture.
"""

import threading
import queue
import time
import ctypes
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pyaudiowpatch as pyaudio

try:
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    PYCAW_AVAILABLE = True
except Exception as e:
    PYCAW_AVAILABLE = False
    print(f"[AppCapture] pycaw not available: {e}")


class AppCaptureManager:
    """Manages audio session discovery and real-time WASAPI loopback audio capture."""

    def __init__(self, sample_rate: int = 48000, buffer_size: int = 1024):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.queue_monitor = queue.Queue(maxsize=100)
        self.queue_mic = queue.Queue(maxsize=100)
        self.is_capturing = False
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Streaming state
        self.is_streaming_to_mic = False
        self.monitor_volume = 0.8
        self.mic_volume = 1.0
        self.target_pids: List[int] = []
        self.target_app_names: List[str] = []
        self.mute_self: bool = True
        self.current_peak: float = 0.0

        # Smart Process Gate (isolates target processes, prevents game audio leakage)
        self._target_meters: List[Any] = []
        self._last_meter_refresh: float = 0.0
        self._gate_hold_until: float = 0.0
        self._current_gate_gain: float = 1.0

    @property
    def target_pid(self) -> Optional[int]:
        return self.target_pids[0] if self.target_pids else None

    @target_pid.setter
    def target_pid(self, val: Optional[int]):
        if val is None:
            self.target_pids = []
        else:
            self.target_pids = [val]

    @property
    def target_app_name(self) -> Optional[str]:
        return ", ".join(self.target_app_names) if self.target_app_names else None

    @target_app_name.setter
    def target_app_name(self, val: Optional[str]):
        if val is None:
            self.target_app_names = []
        else:
            self.target_app_names = [val]

    @staticmethod
    def list_audio_sessions() -> List[Dict[str, Any]]:
        """Returns a list of running processes that currently hold an active audio session."""
        sessions_info = []
        if not PYCAW_AVAILABLE:
            return sessions_info

        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                if s.Process:
                    try:
                        p = s.Process
                        pid = p.pid
                        name = p.name()
                        vol_ctrl = s.SimpleAudioVolume
                        volume = vol_ctrl.GetMasterVolume() if vol_ctrl else 1.0
                        muted = bool(vol_ctrl.GetMute()) if vol_ctrl else False
                        sessions_info.append({
                            "name": name,
                            "pid": pid,
                            "volume": round(volume, 2),
                            "muted": muted
                        })
                    except Exception:
                        continue
        except Exception as e:
            print(f"[AppCapture] Error retrieving audio sessions: {e}")

        # Deduplicate by PID
        unique = {}
        for item in sessions_info:
            unique[item["pid"]] = item
        return list(unique.values())

    def start_capture(self, loopback_device_index: Optional[int] = None):
        """Starts the background WASAPI loopback capture thread."""
        if self.is_capturing:
            return

        self.is_capturing = True
        self._stop_event.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_worker,
            args=(loopback_device_index,),
            daemon=True,
            name="SoundFlow-AppCapture"
        )
        self._capture_thread.start()

    def stop_capture(self):
        """Stops the capture thread."""
        if not self.is_capturing:
            return

        self.is_capturing = False
        self._stop_event.set()
        self.current_peak = 0.0
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        self._capture_thread = None

        # Safely empty both monitor and mic queues without crashing
        for q in (self.queue_monitor, self.queue_mic):
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    def _check_target_processes_active(self) -> Tuple[bool, float]:
        """
        Checks if any of the targeted process IDs are actively emitting sound via pycaw session meters.
        Returns (is_active, peak_level).
        """
        if not self.target_pids:
            return True, 1.0

        now = time.time()
        # Refresh session meter interface list periodically or if empty
        if now - self._last_meter_refresh > 1.2 or not self._target_meters:
            self._target_meters = []
            try:
                sessions = AudioUtilities.GetAllSessions()
                target_set = set(self.target_pids)
                for s in sessions:
                    if s.Process and s.Process.pid in target_set:
                        try:
                            meter = s._ctl.QueryInterface(IAudioMeterInformation)
                            self._target_meters.append(meter)
                        except Exception:
                            pass
            except Exception:
                pass
            self._last_meter_refresh = now

        max_peak = 0.0
        for meter in self._target_meters:
            try:
                v = meter.GetPeakValue()
                if v > max_peak:
                    max_peak = v
            except Exception:
                pass

        # Target app active if peak > 0.0005 (-66 dB)
        is_active = (max_peak > 0.0005)
        if is_active:
            self._gate_hold_until = now + 0.18  # 180ms hold hangover
            return True, max_peak
        elif now < self._gate_hold_until:
            return True, max_peak

        return False, 0.0

    def _capture_worker(self, device_index: Optional[int]):
        pa = None
        stream = None
        com_inited = False
        try:
            try:
                ctypes.windll.ole32.CoInitialize(None)
                com_inited = True
            except Exception:
                pass

            pa = pyaudio.PyAudio()

            # Find WASAPI loopback device
            loopback_dev = None
            if device_index is not None:
                loopback_dev = pa.get_device_info_by_index(device_index)
            else:
                # Prioritize default physical playback loopback (Speakers/Headphones).
                # NEVER pick CABLE Input or any virtual cable as loopback source,
                # because SoundFlow streams into CABLE Input — capturing it creates an infinite feedback echo!
                try:
                    def_lb = pa.get_default_wasapi_loopback()
                    name_low = def_lb.get("name", "").lower()
                    if "cable" not in name_low and "virtual" not in name_low and "voicemeeter" not in name_low:
                        loopback_dev = def_lb
                except Exception:
                    pass

                if not loopback_dev:
                    for i in range(pa.get_device_count()):
                        dev = pa.get_device_info_by_index(i)
                        if dev.get("isLoopbackDevice", False):
                            name_low = dev.get("name", "").lower()
                            if "cable" not in name_low and "virtual" not in name_low and "voicemeeter" not in name_low:
                                loopback_dev = dev
                                break

                # Fallback to any loopback device only if no physical device exists
                if not loopback_dev:
                    try:
                        loopback_dev = pa.get_default_wasapi_loopback()
                    except Exception:
                        for i in range(pa.get_device_count()):
                            dev = pa.get_device_info_by_index(i)
                            if dev.get("isLoopbackDevice", False):
                                loopback_dev = dev
                                break

            if not loopback_dev:
                print("[AppCapture] No WASAPI Loopback device found.")
                return

            dev_index = loopback_dev["index"]
            channels = min(2, int(loopback_dev.get("maxInputChannels", 2)))
            if channels == 0:
                channels = 2

            dev_rate = int(loopback_dev.get("defaultSampleRate", 48000))

            stream = pa.open(
                format=pyaudio.paFloat32,
                channels=channels,
                rate=dev_rate,
                input=True,
                input_device_index=dev_index,
                frames_per_buffer=self.buffer_size
            )

            while not self._stop_event.is_set():
                try:
                    raw_data = stream.read(self.buffer_size, exception_on_overflow=False)
                    audio_data = np.frombuffer(raw_data, dtype=np.float32)

                    if channels == 2:
                        audio_data = audio_data.reshape(-1, 2)
                    else:
                        audio_data = np.column_stack([audio_data, audio_data])

                    # Resample if device sample rate differs from engine sample rate
                    if dev_rate != self.sample_rate:
                        target_len = int(len(audio_data) * (self.sample_rate / dev_rate))
                        if target_len > 0:
                            resampled = np.zeros((target_len, 2), dtype=np.float32)
                            orig_indices = np.arange(len(audio_data))
                            target_indices = np.linspace(0, len(audio_data) - 1, target_len)
                            resampled[:, 0] = np.interp(target_indices, orig_indices, audio_data[:, 0])
                            resampled[:, 1] = np.interp(target_indices, orig_indices, audio_data[:, 1])
                            audio_data = resampled

                    # Apply Smart Process Gate:
                    # If specific target PIDs are selected (e.g. Browser), ensure that when the target
                    # app is silent, no background game audio or system sound leaks into the microphone!
                    target_active = True
                    target_pk = 0.0
                    if self.target_pids:
                        target_active, target_pk = self._check_target_processes_active()

                    # Smooth gate transition (prevents clicks)
                    target_gain = 1.0 if target_active else 0.0
                    alpha = 0.35 if target_gain > self._current_gate_gain else 0.08
                    self._current_gate_gain += (target_gain - self._current_gate_gain) * alpha
                    if self._current_gate_gain < 0.005:
                        self._current_gate_gain = 0.0

                    if self.target_pids and self._current_gate_gain == 0.0:
                        mic_audio = np.zeros_like(audio_data)
                        self.current_peak = 0.0
                    else:
                        mic_audio = audio_data * self._current_gate_gain
                        raw_peak = float(np.max(np.abs(mic_audio))) if len(mic_audio) > 0 else 0.0
                        self.current_peak = target_pk if (self.target_pids and target_pk > 0.0) else raw_peak

                    # Mic queue receives gated audio for streaming to microphone
                    if self.queue_mic.full():
                        try:
                            self.queue_mic.get_nowait()
                        except queue.Empty:
                            pass
                    self.queue_mic.put_nowait(mic_audio)

                    # Monitor queue: if mute_self is enabled, local monitor is complete silence (0.0)
                    if self.queue_monitor.full():
                        try:
                            self.queue_monitor.get_nowait()
                        except queue.Empty:
                            pass
                    if self.mute_self or (self.target_pids and self._current_gate_gain == 0.0):
                        self.queue_monitor.put_nowait(np.zeros_like(audio_data))
                    else:
                        self.queue_monitor.put_nowait(mic_audio)

                except Exception as ex:
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.01)

        except Exception as e:
            print(f"[AppCapture] Worker exception: {e}")
        finally:
            if stream:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if pa:
                try:
                    pa.terminate()
                except Exception:
                    pass
            if com_inited:
                try:
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass
            self.is_capturing = False

    def get_chunk_monitor(self) -> Optional[np.ndarray]:
        """Pulls the next available audio chunk for monitor."""
        try:
            return self.queue_monitor.get_nowait()
        except queue.Empty:
            return None

    def get_chunk_mic(self) -> Optional[np.ndarray]:
        """Pulls the next available audio chunk for mic target."""
        try:
            return self.queue_mic.get_nowait()
        except queue.Empty:
            return None

    def get_chunk(self) -> Optional[np.ndarray]:
        """Backwards-compatible fallback."""
        return self.get_chunk_monitor()
