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

    @classmethod
    def get_cable_capture_endpoint_id(cls) -> Optional[str]:
        """Returns the Windows audio endpoint ID of CABLE Output capture device."""
        try:
            import pycaw.pycaw as pycaw
            enumerator = pycaw.AudioUtilities.GetDeviceEnumerator()
            collection = enumerator.EnumAudioEndpoints(pycaw.EDataFlow.eCapture.value, pycaw.AudioDeviceState.Active.value)
            count = collection.GetCount()
            all_devs = {d.id: d.FriendlyName for d in pycaw.AudioUtilities.GetAllDevices()}
            for i in range(count):
                imm_dev = collection.Item(i)
                dev_id = imm_dev.GetId()
                friendly = all_devs.get(dev_id, "").lower()
                if "cable output" in friendly or ("cable" in friendly and "16ch" not in friendly):
                    return dev_id
        except Exception as e:
            print(f"[DriverManager] get_cable_capture_endpoint_id error: {e}")
        return None

    @classmethod
    def is_cable_output_default(cls) -> bool:
        """Checks if CABLE Output is currently the Windows default recording device."""
        try:
            import pycaw.pycaw as pycaw
            enumerator = pycaw.AudioUtilities.GetDeviceEnumerator()
            cable_id = cls.get_cable_capture_endpoint_id()
            all_devs = {d.id: d.FriendlyName for d in pycaw.AudioUtilities.GetAllDevices()}
            for role in (pycaw.ERole.eConsole.value, pycaw.ERole.eCommunications.value):
                try:
                    cur_def = enumerator.GetDefaultAudioEndpoint(pycaw.EDataFlow.eCapture.value, role)
                    if cable_id and cur_def.GetId() == cable_id:
                        return True
                    def_name = all_devs.get(cur_def.GetId(), "").lower()
                    if "cable output" in def_name or ("cable" in def_name and "16ch" not in def_name):
                        return True
                except Exception:
                    pass
        except Exception as e:
            print(f"[DriverManager] is_cable_output_default error: {e}")
        return False

    @classmethod
    def set_default_recording_device_to_cable(cls) -> bool:
        """Sets CABLE Output as the Windows default recording and communication device across all roles."""
        try:
            import pycaw.pycaw as pycaw
            cable_id = cls.get_cable_capture_endpoint_id()
            if cable_id:
                pycaw.AudioUtilities.SetDefaultDevice(
                    cable_id,
                    roles=[pycaw.ERole.eConsole, pycaw.ERole.eMultimedia, pycaw.ERole.eCommunications]
                )
                print(f"[DriverManager] SetDefaultDevice succeeded for {cable_id} (all roles)")
                return True
        except Exception as e:
            print(f"[DriverManager] set_default_recording_device_to_cable error: {e}")

        # Fallback: open control panel
        cls.open_sound_recording_settings()
        return False

    @classmethod
    def open_sound_recording_settings(cls):
        """Opens Windows legacy sound recording properties dialog."""
        try:
            subprocess.Popen(["control", "mmsys.cpl,,1"], shell=True)
        except Exception as e:
            print(f"[DriverManager] Failed to open sound control panel: {e}")

    @classmethod
    def get_physical_microphone_endpoint_id(cls) -> Optional[str]:
        """Returns endpoint ID of the first non-virtual active microphone in Windows."""
        try:
            import pycaw.pycaw as pycaw
            enumerator = pycaw.AudioUtilities.GetDeviceEnumerator()
            collection = enumerator.EnumAudioEndpoints(pycaw.EDataFlow.eCapture.value, pycaw.AudioDeviceState.Active.value)
            count = collection.GetCount()
            all_devs = {d.id: d.FriendlyName for d in pycaw.AudioUtilities.GetAllDevices()}
            for i in range(count):
                imm_dev = collection.Item(i)
                dev_id = imm_dev.GetId()
                friendly = all_devs.get(dev_id, "").lower()
                if "cable" not in friendly and "virtual" not in friendly and "voicemeeter" not in friendly:
                    return dev_id
        except Exception as e:
            print(f"[DriverManager] get_physical_microphone_endpoint_id error: {e}")
        return None

    @classmethod
    def restore_physical_recording_device(cls) -> bool:
        """Restores physical microphone as the Windows default recording device across all roles."""
        try:
            import pycaw.pycaw as pycaw
            phys_id = cls.get_physical_microphone_endpoint_id()
            if phys_id:
                pycaw.AudioUtilities.SetDefaultDevice(
                    phys_id,
                    roles=[pycaw.ERole.eConsole, pycaw.ERole.eMultimedia, pycaw.ERole.eCommunications]
                )
                print(f"[DriverManager] Restored physical microphone as default: {phys_id} (all roles)")
                return True
        except Exception as e:
            print(f"[DriverManager] restore_physical_recording_device error: {e}")
        return False

    @classmethod
    def start_mic_repeater(cls, mic_id: Optional[int] = None, cable_id: Optional[int] = None) -> bool:
        """Starts headless standby mic repeater in the background."""
        cls.stop_mic_repeater()
        try:
            if getattr(sys, "frozen", False):
                exe = sys.executable
                cmd = [exe, "--repeater"]
            else:
                python_exe = sys.executable
                if "pythonw.exe" in python_exe.lower():
                    pyw = python_exe
                else:
                    pyw = str(Path(python_exe).parent / "pythonw.exe")
                    if not os.path.exists(pyw):
                        pyw = python_exe
                cmd = [pyw, "-m", "core.mic_repeater"]

            if mic_id is not None:
                cmd.extend(["--mic", str(mic_id)])
            if cable_id is not None:
                cmd.extend(["--cable", str(cable_id)])

            DETACHED_PROCESS = 0x00000008
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                cmd,
                creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
                close_fds=True,
                cwd=str(Path(__file__).resolve().parent.parent)
            )
            print(f"[DriverManager] Standby mic repeater started.")
            return True
        except Exception as e:
            print(f"[DriverManager] start_mic_repeater error: {e}")
            return False

    @classmethod
    def stop_mic_repeater(cls):
        """Stops any running standby mic repeater."""
        from core.mic_repeater import PID_FILE
        try:
            if PID_FILE.exists():
                pid_str = PID_FILE.read_text(encoding="utf-8").strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    import psutil
                    if psutil.pid_exists(pid):
                        p = psutil.Process(pid)
                        p.terminate()
                        try:
                            p.wait(timeout=1.0)
                        except Exception:
                            p.kill()
                PID_FILE.unlink(missing_ok=True)
        except Exception as e:
            print(f"[DriverManager] stop_mic_repeater note: {e}")
            try:
                PID_FILE.unlink(missing_ok=True)
            except Exception:
                pass

    @classmethod
    def is_mic_repeater_running(cls) -> bool:
        """Checks if the standby mic repeater is currently running."""
        from core.mic_repeater import PID_FILE
        try:
            if PID_FILE.exists():
                pid_str = PID_FILE.read_text(encoding="utf-8").strip()
                if pid_str.isdigit():
                    import psutil
                    return psutil.pid_exists(int(pid_str))
        except Exception:
            pass
        return False

