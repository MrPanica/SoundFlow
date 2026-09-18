"""
SoundFlow Studio — Windows Per-App Audio Routing Manager.
Uses the native Windows 10/11 WinRT AudioPolicyConfig COM/WinRT interface
(equivalent to Windows Settings > App volume and device preferences)
to dynamically redirect targeted application audio outputs to VB-Audio CABLE Input.

Benefits:
1. True Per-App Audio Isolation:
   Only targeted applications (e.g. Chrome, Spotify) are sent to the virtual cable.
2. Complete Silence for Self ("Заглушить только у себя"):
   When routed to CABLE Input, the application no longer outputs to the physical
   speakers/headphones. The user hears 100% silence locally, while teammates
   in Discord/games hear the application crystal clear.
3. Total Echo / Feedback Elimination:
   Game sounds (CS2, TF2, etc.) remain on default Speakers/Headphones and NEVER
   touch CABLE Input. Zero game audio leakage into the microphone, zero feedback loop.
4. Clean State Restoration:
   When streaming stops or SoundFlow exits, all routed applications are automatically
   restored back to the Windows default playback endpoint.
"""

import os
import sys
import ctypes
import atexit
from typing import List, Set, Optional, Dict, Any
from pathlib import Path

ROUTER_AVAILABLE = False

try:
    from comtypes import GUID
    from pycaw.pycaw import AudioUtilities
    from pycaw.constants import AudioDeviceState
    ROUTER_AVAILABLE = True
except Exception:
    pass


class WindowsAppAudioRouter:
    """Manages per-application audio endpoint redirection on Windows 10 (1803+) and Windows 11."""

    DEVINTERFACE_AUDIO_RENDER = "#{e6327cad-dcec-4949-ae8a-991e976a79d2}"
    MMDEVAPI_TOKEN = r"\\?\SWD#MMDEVAPI#"

    def __init__(self):
        self._factory = None
        self._set_persisted = None
        self._get_persisted = None
        self._clear_all = None
        self._combase = None
        self._routed_pids: Set[int] = set()
        self._cable_input_id: Optional[str] = None
        self._is_active: bool = False

        if sys.platform == "win32" and ROUTER_AVAILABLE:
            self._init_winrt()
            atexit.register(self.restore_all)

    def _init_winrt(self):
        """Initializes WinRT RoGetActivationFactory for AudioPolicyConfig."""
        try:
            self._combase = ctypes.windll.combase
            self._combase.RoInitialize(1)

            class HSTRING(ctypes.c_void_p):
                pass

            class_name = "Windows.Media.Internal.AudioPolicyConfig"
            hstr = HSTRING()
            res = self._combase.WindowsCreateString(ctypes.c_wchar_p(class_name), len(class_name), ctypes.byref(hstr))
            if res != 0:
                return

            # Win10 21H2 / Win11 interface GUID
            guid_21h2 = GUID("{ab3d4648-e242-459f-b02f-541c70306324}")
            factory = ctypes.c_void_p()
            hr = self._combase.RoGetActivationFactory(hstr, ctypes.byref(guid_21h2), ctypes.byref(factory))
            self._combase.WindowsDeleteString(hstr)

            if hr == 0 and factory.value:
                self._factory = factory
                vtbl = ctypes.cast(factory, ctypes.POINTER(ctypes.c_void_p)).contents.value
                vtbl_ptr = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))

                # VTable indices:
                # 25: SetPersistedDefaultAudioEndpoint(this, uint processId, int flow, int role, HSTRING deviceId)
                # 26: GetPersistedDefaultAudioEndpoint(this, uint processId, int flow, int role, HSTRING* deviceId)
                # 27: ClearAllPersistedApplicationDefaultEndpoints(this)
                SetProto = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
                self._set_persisted = SetProto(vtbl_ptr[25])

                GetProto = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
                self._get_persisted = GetProto(vtbl_ptr[26])

                ClearProto = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
                self._clear_all = ClearProto(vtbl_ptr[27])
                print("[AppRouter] Windows AudioPolicyConfig factory initialized successfully.")
        except Exception as e:
            print(f"[AppRouter] Could not initialize WinRT AudioPolicyConfig: {e}")

    @property
    def is_available(self) -> bool:
        return self._factory is not None and self._set_persisted is not None

    def get_cable_input_device_id(self) -> Optional[str]:
        """Finds the MMDevice endpoint ID of 'CABLE Input (VB-Audio Virtual Cable)'."""
        if self._cable_input_id:
            return self._cable_input_id

        try:
            for dev in AudioUtilities.GetAllDevices():
                if dev.state == AudioDeviceState.Active:
                    name_low = dev.FriendlyName.lower()
                    if "cable input" in name_low and "16ch" not in name_low:
                        self._cable_input_id = dev.id
                        return dev.id

            # Fallback to any CABLE Input
            for dev in AudioUtilities.GetAllDevices():
                name_low = dev.FriendlyName.lower()
                if "cable input" in name_low:
                    self._cable_input_id = dev.id
                    return dev.id
        except Exception as e:
            print(f"[AppRouter] Error finding CABLE Input ID: {e}")

        return None

    def route_pids_to_cable(self, pids: List[int], process_names: Optional[List[str]] = None) -> bool:
        """
        Redirects the specified process IDs (and all related processes with the same executable name)
        to 'CABLE Input (VB-Audio Virtual Cable)'.
        """
        if not self.is_available:
            return False

        cable_id = self.get_cable_input_device_id()
        if not cable_id:
            print("[AppRouter] CABLE Input device not found. Cannot route processes.")
            return False

        full_dev_id = f"{self.MMDEVAPI_TOKEN}{cable_id}{self.DEVINTERFACE_AUDIO_RENDER}"

        # Collect all related PIDs for the targeted apps (e.g. all chrome.exe processes)
        target_pids = set(pids)
        if process_names:
            import psutil
            name_set = {n.lower() for n in process_names}
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    if p.info["name"] and p.info["name"].lower() in name_set:
                        target_pids.add(p.info["pid"])
                except Exception:
                    pass

        success_count = 0
        hstr = ctypes.c_void_p()
        self._combase.WindowsCreateString(ctypes.c_wchar_p(full_dev_id), len(full_dev_id), ctypes.byref(hstr))

        try:
            for pid in target_pids:
                if pid <= 4 or pid == os.getpid():
                    continue
                # Flow 0 = eRender, Role 1 = eMultimedia, Role 0 = eConsole
                hr1 = self._set_persisted(self._factory, pid, 0, 1, hstr)
                hr2 = self._set_persisted(self._factory, pid, 0, 0, hstr)
                if hr1 == 0 or hr2 == 0:
                    self._routed_pids.add(pid)
                    success_count += 1
        finally:
            self._combase.WindowsDeleteString(hstr)

        self._is_active = (len(self._routed_pids) > 0)
        print(f"[AppRouter] Successfully routed {success_count} processes to CABLE Input.")
        return self._is_active

    def restore_all(self):
        """Restores all routed applications back to the Windows default playback device."""
        if not self.is_available:
            return

        if not self._routed_pids and not self._is_active:
            return

        print(f"[AppRouter] Restoring {len(self._routed_pids)} processes to default playback device...")
        null_hstr = ctypes.c_void_p(None)

        for pid in list(self._routed_pids):
            try:
                self._set_persisted(self._factory, pid, 0, 1, null_hstr)
                self._set_persisted(self._factory, pid, 0, 0, null_hstr)
            except Exception:
                pass

        self._routed_pids.clear()
        self._is_active = False
        print("[AppRouter] All processes restored to default playback device.")
