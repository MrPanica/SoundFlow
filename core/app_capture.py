"""
Windows Application & System Audio Capture for SoundFlow Studio.
Uses pycaw to detect audio-producing applications and PyAudioWPatch for high-performance WASAPI loopback capture.
Integrates WindowsAppAudioRouter for true OS-level per-app audio routing and zero-echo isolation.
"""

import threading
import queue
import time
import ctypes
import os
import psutil
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pyaudiowpatch as pyaudio

from .app_router import WindowsAppAudioRouter

try:
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
    PYCAW_AVAILABLE = True
except Exception as e:
    PYCAW_AVAILABLE = False
    print(f"[AppCapture] pycaw not available: {e}")


KNOWN_MEDIA_APPS = {
    'chrome.exe': 'Google Chrome',
    'msedge.exe': 'Microsoft Edge',
    'firefox.exe': 'Mozilla Firefox',
    'opera.exe': 'Opera Browser',
    'opera_gx.exe': 'Opera GX',
    'brave.exe': 'Brave Browser',
    'yandex.exe': 'Yandex Browser',
    'vivaldi.exe': 'Vivaldi',
    'arc.exe': 'Arc Browser',
    'spotify.exe': 'Spotify',
    'vlc.exe': 'VLC Media Player',
    'aimp.exe': 'AIMP',
    'foobar2000.exe': 'foobar2000',
    'wmplayer.exe': 'Windows Media Player',
    'mpv.exe': 'MPV Player',
    'potplayer64.exe': 'PotPlayer',
    'kmplayer.exe': 'KMPlayer',
    'discord.exe': 'Discord',
    'telegram.exe': 'Telegram',
    'steam.exe': 'Steam',
    'steamwebhelper.exe': 'Steam Web Helper',
    'obs64.exe': 'OBS Studio',
    'cs2.exe': 'Counter-Strike 2',
    'dota2.exe': 'Dota 2',
    'valorant.exe': 'VALORANT'
}

SYSTEM_EXCLUDES = {
    'svchost.exe', 'audiodg.exe', 'conhost.exe', 'dwm.exe', 'system', 'registry',
    'smss.exe', 'csrss.exe', 'wininit.exe', 'services.exe', 'lsass.exe', 'winlogon.exe',
    'fontdrvhost.exe', 'sihost.exe', 'taskhostw.exe', 'shellexperiencehost.exe',
    'searchhost.exe', 'startmenuexperiencehost.exe', 'textinputhost.exe', 'ctfmon.exe',
    'runtimebroker.exe', 'securityhealthservice.exe', 'smartscreen.exe', 'wmiprvse.exe',
    'dllhost.exe', 'spoolsv.exe', 'searchindexer.exe', 'antigravity.exe', 'antigravity-manager.exe',
    'explorer.exe', 'cmd.exe', 'pwsh.exe', 'powershell.exe', 'wsl.exe', 'wslhost.exe',
    'taskmgr.exe', 'dashost.exe', 'applicationframehost.exe', 'useroobebroker.exe',
    'gameinputredistservice.exe', 'securityhealthsystray.exe', 'unsecapp.exe'
}


class AppCaptureManager:
    """Manages audio session discovery and real-time WASAPI loopback audio capture."""

    def __init__(self, sample_rate: int = 48000, buffer_size: int = 1024):
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self.queue_monitor = queue.Queue(maxsize=3)
        self.queue_mic = queue.Queue(maxsize=3)
        self.is_capturing = False
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Streaming & routing state
        self.router = WindowsAppAudioRouter()
        self.is_routed_to_cable = False
        self.is_streaming_to_mic = False
        self.monitor_volume = 0.8
        self.mic_volume = 1.0
        self.target_pids: List[int] = []
        self.target_app_names: List[str] = []
        self.mute_self: bool = True
        self.current_peak: float = 0.0

        # Smart Process Gate (used in fallback mode)
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

    def update_targets(self, pids: List[int], names: List[str]):
        """Dynamically updates target processes and refreshes routing if stream is active."""
        self.target_pids = list(pids)
        self.target_app_names = list(names)
        self._target_meters = []
        if self.is_capturing and hasattr(self, "router") and self.router.is_available:
            self.router.restore_all()
            if self.target_pids or self.target_app_names:
                ok = self.router.route_pids_to_cable(self.target_pids, self.target_app_names)
                self.is_routed_to_cable = bool(ok)
            else:
                self.is_routed_to_cable = False

    @staticmethod
    def list_audio_sessions() -> List[Dict[str, Any]]:
        """
        Fast, comprehensive process discovery:
        1. Queries active WASAPI audio sessions via pycaw.
        2. Scans running user processes via psutil (<20ms) to immediately catch browsers and media players
           even before they begin playing sound.
        3. Groups multiple processes by executable name (e.g. all chrome.exe PIDs into one entry).
        4. Sorts with active audio sessions at the top, then media/browsers, then other apps.
        """
        cur_pid = os.getpid()
        active_sessions = {}
        if PYCAW_AVAILABLE:
            try:
                for s in AudioUtilities.GetAllSessions():
                    if s.Process:
                        try:
                            p = s.Process
                            pid = p.pid
                            name = p.name()
                            vol = s.SimpleAudioVolume.GetMasterVolume() if s.SimpleAudioVolume else 1.0
                            muted = bool(s.SimpleAudioVolume.GetMute()) if s.SimpleAudioVolume else False
                            active_sessions[pid] = {
                                "name": name,
                                "volume": round(vol, 2),
                                "muted": muted
                            }
                        except Exception:
                            pass
            except Exception as e:
                print(f"[AppCapture] Error retrieving audio sessions: {e}")

        apps: Dict[str, Dict[str, Any]] = {}
        for p in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                raw_name = p.info['name'] or ''
                name_lower = raw_name.lower()
                pid = p.info['pid']
                exe = p.info['exe'] or ''

                if not name_lower or name_lower in SYSTEM_EXCLUDES or pid == cur_pid:
                    continue

                is_active_session = pid in active_sessions
                is_known_media = name_lower in KNOWN_MEDIA_APPS

                is_user_app = False
                exe_lower = exe.lower()
                if any(k in exe_lower for k in ['program files', 'appdata\\local\\programs', 'games', 'steamapps']):
                    if not any(k in name_lower for k in ['service', 'daemon', 'helper', 'crash', 'update', 'install']):
                        is_user_app = True

                if is_active_session or is_known_media or is_user_app:
                    if name_lower not in apps:
                        display_name = KNOWN_MEDIA_APPS.get(name_lower, raw_name)
                        sess_info = active_sessions.get(pid, {})
                        apps[name_lower] = {
                            'name': raw_name,
                            'display_name': display_name,
                            'pid': pid,
                            'pids': [pid],
                            'exe': exe,
                            'volume': sess_info.get('volume', 1.0),
                            'muted': sess_info.get('muted', False),
                            'has_session': is_active_session
                        }
                    else:
                        apps[name_lower]['pids'].append(pid)
                        if is_active_session:
                            apps[name_lower]['has_session'] = True
                            if pid in active_sessions:
                                apps[name_lower]['volume'] = active_sessions[pid]['volume']
                                apps[name_lower]['muted'] = active_sessions[pid]['muted']
            except Exception:
                pass

        result = list(apps.values())
        def sort_key(x):
            priority = 0 if x['has_session'] else (1 if x['name'].lower() in KNOWN_MEDIA_APPS else 2)
            return (priority, x['display_name'].lower())

        result.sort(key=sort_key)
        return result

    def set_target_volume(self, volume: float, muted: bool = False):
        """Sets the Windows session volume of the targeted processes."""
        if not PYCAW_AVAILABLE or (not self.target_pids and not self.target_app_names):
            return

        try:
            target_pids = set(self.target_pids)
            target_names = {n.lower() for n in self.target_app_names}
            clamped_vol = max(0.0, min(1.0, float(volume)))

            for s in AudioUtilities.GetAllSessions():
                if s.Process:
                    try:
                        p = s.Process
                        if p.pid in target_pids or p.name().lower() in target_names:
                            if s.SimpleAudioVolume:
                                s.SimpleAudioVolume.SetMasterVolume(clamped_vol, None)
                                s.SimpleAudioVolume.SetMute(int(muted), None)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[AppCapture] Error setting session volume: {e}")

    def start_capture(self, loopback_device_index: Optional[int] = None):
        """
        Starts the background WASAPI loopback capture thread.
        If specific applications are selected, dynamically routes them via Windows AudioPolicyConfig
        to VB-Audio CABLE Input, isolating them from physical headphones and eliminating in-game echo.
        """
        if self.is_capturing:
            return

        self.is_capturing = True
        self._stop_event.clear()

        self.is_routed_to_cable = False
        if self.target_pids or self.target_app_names:
            if hasattr(self, "router") and self.router.is_available:
                ok = self.router.route_pids_to_cable(self.target_pids, self.target_app_names)
                if ok:
                    self.is_routed_to_cable = True
                    print(f"[AppCapture] Routed {self.target_app_names} to CABLE Input successfully.")

        self._capture_thread = threading.Thread(
            target=self._capture_worker,
            args=(loopback_device_index,),
            daemon=True,
            name="SoundFlow-AppCapture"
        )
        self._capture_thread.start()

    def stop_capture(self):
        """Stops the capture thread and restores routed applications to default playback endpoint."""
        if not self.is_capturing:
            if hasattr(self, "router") and getattr(self, "is_routed_to_cable", False):
                self.router.restore_all()
                self.is_routed_to_cable = False
            return

        self.is_capturing = False
        self._stop_event.set()
        self.current_peak = 0.0

        if hasattr(self, "router") and getattr(self, "is_routed_to_cable", False):
            try:
                self.router.restore_all()
            except Exception as e:
                print(f"[AppCapture] Error restoring routed apps: {e}")
            self.is_routed_to_cable = False

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
        Returns (is_active, peak_level). Used in fallback unrouted mode.
        """
        if not self.target_pids and not self.target_app_names:
            return True, 1.0

        now = time.time()
        if now - self._last_meter_refresh > 2.5 or not self._target_meters:
            self._target_meters = []
            try:
                sessions = AudioUtilities.GetAllSessions()
                target_pids = set(self.target_pids)
                target_names = {n.lower() for n in self.target_app_names}
                for s in sessions:
                    if s.Process:
                        p = s.Process
                        if p.pid in target_pids or p.name().lower() in target_names:
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

        is_active = (max_peak > 0.0005)
        if is_active:
            self._gate_hold_until = now + 0.18
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
            elif self.is_routed_to_cable:
                # Routed mode: capture CABLE Input [Loopback]
                for i in range(pa.get_device_count()):
                    dev = pa.get_device_info_by_index(i)
                    name_low = dev.get("name", "").lower()
                    if dev.get("isLoopbackDevice", False) and "cable input" in name_low and "16ch" not in name_low:
                        loopback_dev = dev
                        break
                if not loopback_dev:
                    for i in range(pa.get_device_count()):
                        dev = pa.get_device_info_by_index(i)
                        name_low = dev.get("name", "").lower()
                        if dev.get("isLoopbackDevice", False) and "cable" in name_low:
                            loopback_dev = dev
                            break
            else:
                # System mix mode: capture default physical playback loopback (Speakers/Headphones).
                # NEVER pick CABLE Input or any virtual cable as loopback source here to avoid feedback loop.
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

                # Fallback only if no physical device exists
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
                    # Purge any stale loopback buffer backlog to guarantee real-time latency (<25ms)
                    try:
                        while stream.get_read_available() > self.buffer_size:
                            stream.read(self.buffer_size, exception_on_overflow=False)
                    except Exception:
                        pass

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

                    raw_peak = float(np.max(np.abs(audio_data))) if len(audio_data) > 0 else 0.0

                    if self.is_routed_to_cable:
                        self.current_peak = raw_peak

                        # Routed mode: Chrome renders directly to CABLE Input.
                        # VB-Cable kernel driver pipes CABLE Input straight to CABLE Output (mic).
                        # Drain queue_mic so no stale audio lingers.
                        while not self.queue_mic.empty():
                            try:
                                self.queue_mic.get_nowait()
                            except queue.Empty:
                                break

                        # Monitor queue:
                        # If mute_self is enabled, local monitor is complete silence.
                        # If disabled (user turned ON headphones monitor), provide audio_data.
                        if not self.mute_self:
                            if self.queue_monitor.full():
                                try:
                                    self.queue_monitor.get_nowait()
                                except queue.Empty:
                                    pass
                            self.queue_monitor.put_nowait(audio_data)
                        else:
                            while not self.queue_monitor.empty():
                                try:
                                    self.queue_monitor.get_nowait()
                                except queue.Empty:
                                    break

                    else:
                        # Fallback / System Mix mode:
                        target_active = True
                        target_pk = 0.0
                        if self.target_pids or self.target_app_names:
                            target_active, target_pk = self._check_target_processes_active()

                        target_gain = 1.0 if target_active else 0.0
                        alpha = 0.35 if target_gain > self._current_gate_gain else 0.08
                        self._current_gate_gain += (target_gain - self._current_gate_gain) * alpha
                        if self._current_gate_gain < 0.005:
                            self._current_gate_gain = 0.0

                        if (self.target_pids or self.target_app_names) and self._current_gate_gain == 0.0:
                            mic_audio = np.zeros_like(audio_data)
                            self.current_peak = 0.0
                        else:
                            mic_audio = audio_data * self._current_gate_gain
                            self.current_peak = target_pk if ((self.target_pids or self.target_app_names) and target_pk > 0.0) else raw_peak

                        if self.queue_mic.full():
                            try:
                                self.queue_mic.get_nowait()
                            except queue.Empty:
                                pass
                        self.queue_mic.put_nowait(mic_audio)

                        if not self.mute_self and ((not self.target_pids and not self.target_app_names) or self._current_gate_gain > 0.0):
                            if self.queue_monitor.full():
                                try:
                                    self.queue_monitor.get_nowait()
                                except queue.Empty:
                                    pass
                            self.queue_monitor.put_nowait(mic_audio)
                        else:
                            while not self.queue_monitor.empty():
                                try:
                                    self.queue_monitor.get_nowait()
                                except queue.Empty:
                                    break

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
        """Pulls the latest available audio chunk for monitor, discarding stale chunks."""
        latest = None
        while True:
            try:
                latest = self.queue_monitor.get_nowait()
            except queue.Empty:
                break
        return latest

    def get_chunk_mic(self) -> Optional[np.ndarray]:
        """Pulls the latest available audio chunk for mic target, discarding stale chunks."""
        latest = None
        while True:
            try:
                latest = self.queue_mic.get_nowait()
            except queue.Empty:
                break
        return latest

    def get_chunk(self) -> Optional[np.ndarray]:
        """Backwards-compatible fallback."""
        return self.get_chunk_monitor()
