"""
Virtual Audio Driver Manager for SoundFlow Studio.
Detects presence of virtual audio cable endpoints, binds them automatically,
and launches the built-in driver installer with administrative privileges.
"""

import os
import sys
import ctypes
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
import sounddevice as sd


class DriverManager:
    """Detects and manages installation of the built-in Virtual Audio Driver."""

    @classmethod
    def get_driver_dir(cls) -> Path:
        if hasattr(sys, "_MEIPASS"):
            d = Path(sys._MEIPASS) / "assets" / "driver"
            if d.exists():
                return d
        exe_dir = Path(sys.executable).parent
        d = exe_dir / "_internal" / "assets" / "driver"
        if d.exists():
            return d
        d2 = exe_dir / "assets" / "driver"
        if d2.exists():
            return d2
        return Path(__file__).resolve().parent.parent / "assets" / "driver"

    @classmethod
    def get_setup_exe(cls) -> Path:
        return cls.get_driver_dir() / "VBCABLE_Setup_x64.exe"

    @classmethod
    def is_driver_installed(cls) -> bool:
        """Checks if any virtual audio cable endpoint is registered in Windows."""
        return cls.get_cable_device_id() is not None

    @classmethod
    def get_cable_device_id(cls) -> Optional[int]:
        """Returns device index of CABLE Input (output device) if present, else None."""
        try:
            devices = sd.query_devices()
            # Prioritize 'CABLE Input' or 'VB-Audio'
            for idx, dev in enumerate(devices):
                name = dev["name"].lower()
                # Must be an output device (max_output_channels > 0)
                if dev["max_output_channels"] > 0:
                    if "cable input" in name or "vb-audio" in name:
                        return idx
            # Secondary check for general virtual cable
            for idx, dev in enumerate(devices):
                name = dev["name"].lower()
                if dev["max_output_channels"] > 0:
                    if "virtual" in name or "cable" in name or "voicemeeter" in name:
                        return idx
        except Exception as e:
            print(f"[DriverManager] Query error: {e}")
        return None

    @classmethod
    def get_cable_output_name(cls) -> Optional[str]:
        """Returns name of the capture device (microphone) that Discord/games should use."""
        try:
            devices = sd.query_devices()
            for dev in devices:
                name = dev["name"].lower()
                if dev["max_input_channels"] > 0:
                    if "cable output" in name or "vb-audio" in name:
                        return dev["name"]
        except Exception:
            pass
        return "CABLE Output (VB-Audio Virtual Cable)"

    @classmethod
    def launch_installer(cls) -> bool:
        """Runs the built-in VBCABLE_Setup_x64.exe with Administrator privileges."""
        setup_exe = cls.get_setup_exe()
        driver_dir = cls.get_driver_dir()
        if not setup_exe.exists():
            print(f"[DriverManager] Installer not found at {setup_exe}")
            return False

        try:
            # ShellExecute with 'runas' prompts Windows UAC for administrator elevation
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                str(setup_exe),
                None,
                str(driver_dir),
                1  # SW_SHOWNORMAL
            )
            return result > 32
        except Exception as e:
            print(f"[DriverManager] Failed to launch installer: {e}")
            return False

    @classmethod
    def open_driver_folder(cls):
        """Opens the driver files folder in Windows Explorer."""
        driver_dir = cls.get_driver_dir()
        if driver_dir.exists():
            os.startfile(str(driver_dir))
