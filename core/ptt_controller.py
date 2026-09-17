"""
Auto Push-to-Talk (Auto-PTT) Controller for SoundFlow Studio.
Automatically simulates holding down the game or Discord voice activation key
while soundboard, radio, or TTS audio is being broadcast to the microphone,
and releases it with a configurable hold delay after playback finishes.
"""

import threading
import time
from typing import Optional
import keyboard


class PTTController:
    """Controls virtual Push-to-Talk key presses in games and voice apps."""

    def __init__(self, key: str = "v", release_delay_sec: float = 0.15, enabled: bool = False):
        self.key: str = key.strip().lower() if key else "v"
        self.release_delay_sec: float = max(0.0, float(release_delay_sec))
        self.enabled: bool = bool(enabled)

        self._active_count: int = 0
        self._is_pressed: bool = False
        self._lock = threading.RLock()
        self._release_timer: Optional[threading.Timer] = None

    def update_config(self, key: Optional[str] = None, release_delay_sec: Optional[float] = None, enabled: Optional[bool] = None):
        with self._lock:
            if key is not None:
                new_key = key.strip().lower()
                if new_key != self.key and self._is_pressed:
                    self._release_key_raw()
                self.key = new_key
            if release_delay_sec is not None:
                self.release_delay_sec = max(0.0, float(release_delay_sec))
            if enabled is not None:
                if not enabled and self._is_pressed:
                    self._release_key_raw()
                self.enabled = bool(enabled)

    def start_broadcast(self):
        """Called when a sound begins streaming into the microphone."""
        with self._lock:
            self._active_count += 1
            if self._release_timer is not None:
                self._release_timer.cancel()
                self._release_timer = None

            if not self.enabled or not self.key:
                return

            if not self._is_pressed:
                self._press_key_raw()

    def stop_broadcast(self):
        """Called when a sound stops streaming into the microphone."""
        with self._lock:
            if self._active_count > 0:
                self._active_count -= 1

            if self._active_count == 0:
                if self._release_timer is not None:
                    self._release_timer.cancel()
                    self._release_timer = None

                if not self.enabled or not self.key:
                    if self._is_pressed:
                        self._release_key_raw()
                    return

                if self._is_pressed:
                    if self.release_delay_sec > 0:
                        self._release_timer = threading.Timer(self.release_delay_sec, self._on_release_timer_expired)
                        self._release_timer.daemon = True
                        self._release_timer.start()
                    else:
                        self._release_key_raw()

    def force_release(self):
        """Immediately releases the PTT key and clears any active timers (e.g. on ESC or app exit)."""
        with self._lock:
            self._active_count = 0
            if self._release_timer is not None:
                self._release_timer.cancel()
                self._release_timer = None
            if self._is_pressed:
                self._release_key_raw()

    def _on_release_timer_expired(self):
        with self._lock:
            self._release_timer = None
            if self._active_count == 0 and self._is_pressed:
                self._release_key_raw()

    def _press_key_raw(self):
        if not self.key:
            return
        try:
            keyboard.press(self.key)
            self._is_pressed = True
        except Exception as e:
            print(f"[PTTController] Failed to press key '{self.key}': {e}")

    def _release_key_raw(self):
        if not self.key:
            self._is_pressed = False
            return
        try:
            keyboard.release(self.key)
        except Exception as e:
            print(f"[PTTController] Failed to release key '{self.key}': {e}")
        finally:
            self._is_pressed = False
