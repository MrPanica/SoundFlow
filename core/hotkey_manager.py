"""
Global Hotkey Manager for SoundFlow Studio using the keyboard library.
Registers and handles system-wide hotkeys even when games or full-screen apps are focused.
Supports both trigger mode and hold mode ("Play while held").
"""

import threading
from typing import Dict, Callable, Optional, Any, List
import keyboard


class HotkeyManager:
    """Manages global hotkeys for sound triggers, stream toggles, and shortcuts."""

    def __init__(self):
        self._registered: Dict[str, Any] = {}
        self._holds: Dict[str, Dict[str, Any]] = {}
        self._hook_handle = None
        self._lock = threading.RLock()

    def _ensure_hook(self):
        if self._hook_handle is None:
            try:
                self._hook_handle = keyboard.hook(self._on_keyboard_event)
            except Exception as e:
                print(f"[HotkeyManager] Failed to install keyboard hook: {e}")

    def _on_keyboard_event(self, event):
        if not self._holds:
            return

        k_name = (event.name or "").lower()
        scan = getattr(event, "scan_code", None)
        event_type = event.event_type  # 'down' or 'up'

        with self._lock:
            for combo, data in list(self._holds.items()):
                main_key = data["main_key"]
                mods = data["modifiers"]

                # Match main key by name or scan code
                if k_name == main_key or (data.get("scan_code") is not None and scan == data["scan_code"]):
                    if event_type == "down":
                        if not data["is_pressed"]:
                            # Check modifiers
                            mods_ok = True
                            for m in mods:
                                try:
                                    if not keyboard.is_pressed(m):
                                        mods_ok = False
                                        break
                                except Exception:
                                    pass
                            if mods_ok:
                                data["is_pressed"] = True
                                try:
                                    data["press_cb"]()
                                except Exception as err:
                                    print(f"[HotkeyManager] Hold press callback error for '{combo}': {err}")
                    elif event_type == "up":
                        if data["is_pressed"]:
                            data["is_pressed"] = False
                            try:
                                data["release_cb"]()
                            except Exception as err:
                                print(f"[HotkeyManager] Hold release callback error for '{combo}': {err}")

                # Also if modifier is released while holding, release the hold
                elif event_type == "up" and k_name in mods:
                    if data["is_pressed"]:
                        data["is_pressed"] = False
                        try:
                            data["release_cb"]()
                        except Exception as err:
                            print(f"[HotkeyManager] Hold release callback error on modifier up for '{combo}': {err}")

    def register(self, key_combination: str, callback: Callable[[], None]) -> bool:
        """Registers a global hotkey combination (e.g. 'ctrl+f9', 'num 1', 'f5')."""
        if not key_combination:
            return False

        combo = key_combination.strip().lower()
        with self._lock:
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

    def register_hold(self, key_combination: str, on_press: Callable[[], None], on_release: Callable[[], None]) -> bool:
        """Registers a hold-style hotkey ('Play while held'). Triggers on_press once on down, on_release on up."""
        if not key_combination:
            return False

        combo = key_combination.strip().lower()
        parts = [p.strip() for p in combo.split("+") if p.strip()]
        if not parts:
            return False

        main_key = parts[-1]
        modifiers = parts[:-1]

        with self._lock:
            self.unregister(combo)

            scan = None
            try:
                scans = keyboard.key_to_scan_codes(main_key)
                if scans:
                    scan = scans[0]
            except Exception:
                pass

            self._holds[combo] = {
                "main_key": main_key,
                "modifiers": modifiers,
                "scan_code": scan,
                "press_cb": on_press,
                "release_cb": on_release,
                "is_pressed": False
            }
            self._ensure_hook()
            return True

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

            if combo in self._holds:
                hold_data = self._holds.pop(combo)
                if hold_data.get("is_pressed", False):
                    try:
                        hold_data["release_cb"]()
                    except Exception:
                        pass

            if not self._holds and self._hook_handle is not None:
                try:
                    keyboard.unhook(self._hook_handle)
                except Exception:
                    pass
                self._hook_handle = None

    def clear_all(self):
        """Unregisters all global hotkeys."""
        with self._lock:
            for combo in list(self._registered.keys()):
                try:
                    keyboard.remove_hotkey(combo)
                except Exception:
                    pass
            self._registered.clear()

            for combo, hold_data in list(self._holds.items()):
                if hold_data.get("is_pressed", False):
                    try:
                        hold_data["release_cb"]()
                    except Exception:
                        pass
            self._holds.clear()

            if self._hook_handle is not None:
                try:
                    keyboard.unhook(self._hook_handle)
                except Exception:
                    pass
                self._hook_handle = None

            try:
                keyboard.unhook_all()
            except Exception:
                pass
