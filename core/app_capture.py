"""
Windows Application & System Audio Capture for SoundFlow Studio.
Uses pycaw to detect audio-producing applications and PyAudioWPatch for high-performance WASAPI loopback capture.
"""

import threading
import queue
import time
from typing import List, Dict, Any, Optional
import numpy as np
import pyaudiowpatch as pyaudio

try:
    from pycaw.pycaw import AudioUtilities
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
        self.target_pid: Optional[int] = None
        self.target_app_name: Optional[str] = None

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
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        self._capture_thread = None

        # Empty the queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _capture_worker(self, device_index: Optional[int]):
        pa = None
        stream = None
        try:
            pa = pyaudio.PyAudio()

            # Find default WASAPI loopback device if not explicitly provided
            loopback_dev = None
            if device_index is not None:
                loopback_dev = pa.get_device_info_by_index(device_index)
            else:
                try:
                    loopback_dev = pa.get_default_wasapi_loopback()
                except Exception:
                    # Fallback: search for first device with isLoopbackDevice = True
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

                    # Push to both queues with drop if full
                    for q in (self.queue_monitor, self.queue_mic):
                        if q.full():
                            try:
                                q.get_nowait()
                            except queue.Empty:
                                pass
                        q.put_nowait(audio_data)

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
