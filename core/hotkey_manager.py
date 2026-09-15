"""
Global Hotkey Manager for SoundFlow Studio using the keyboard library.
Registers and handles system-wide hotkeys even when games or full-screen apps are focused.
"""

import threading
from typing import Dict, Callable, Optional
import keyboard


class HotkeyManager:
    """Manages global hotkeys for sound triggers, stream toggles, and shortcuts."""

    def __init__(self):
        self._registered: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def register(self, key_combination: str, callback: Callable[[], None]) -> bool:
        """Registers a global hotkey combination (e.g. 'ctrl+f9', 'num 1', 'f5')."""
        if not key_combination:
            return False

        combo = key_combination.strip().lower()
        with self._lock:
            # Unregister old one if exists
            self.unregister(combo)

            def safe_callback():
                try:
                    callback()
                except Exception as e:
                    print(f"[HotkeyManager] Error in callback for '{combo}': {e}")

            try:
                hook = keyboard.add_hotkey(combo, safe_callback, suppress=False)
                self._registered[combo] = hook
                return True
            except Exception as e:
                print(f"[HotkeyManager] Failed to register '{combo}': {e}")
                return False

    def unregister(self, key_combination: str):
        """Unregisters a specific hotkey."""
        combo = key_combination.strip().lower()
        with self._lock:
            if combo in self._registered:
                try:
                    keyboard.remove_hotkey(combo)
                except Exception:
                    pass
                del self._registered[combo]

    def clear_all(self):
        """Unregisters all global hotkeys."""
        with self._lock:
            for combo in list(self._registered.keys()):
                try:
                    keyboard.remove_hotkey(combo)
                except Exception:
                    pass
            self._registered.clear()
            try:
                keyboard.unhook_all()
            except Exception:
                pass
