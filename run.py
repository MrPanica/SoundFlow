"""
SoundFlow Studio — Application Entry Point.
Launches the PyQt6 desktop interface and configures high-DPI scaling.
"""

import os
import sys
import time
import signal
import atexit
import traceback
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Handle standalone background repeater process
if "--repeater" in sys.argv:
    from core.mic_repeater import main_cli
    main_cli()
    sys.exit(0)

# Global crash handler and safety microphone restoration
def emergency_crash_handler(exc_type, exc_value, exc_tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    err = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    print(f"[CRITICAL ERROR] Unhandled exception:\n{err}", file=sys.stderr)

    try:
        from core.config_manager import APP_DIR
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(APP_DIR / "crash.log", "a", encoding="utf-8") as f:
            f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Unhandled exception:\n{err}\n")
    except Exception:
        pass

    # CRITICAL: Always restore physical microphone in Windows if an unhandled crash occurs
    try:
        from core.driver_manager import DriverManager
        DriverManager.restore_physical_recording_device()
    except Exception:
        pass

sys.excepthook = emergency_crash_handler

# Clean exit hook
def on_app_exit():
    try:
        from core.driver_manager import DriverManager
        DriverManager.restore_physical_recording_device()
    except Exception:
        pass

atexit.register(on_app_exit)

def _sig_handler(signum, frame):
    on_app_exit()
    sys.exit(0)

try:
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
except Exception:
    pass

if sys.platform == "win32":
    try:
        import ctypes
        HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)
        def _win_ctrl_handler(ctrl_type):
            on_app_exit()
            return False
        _global_ctrl_ref = HandlerRoutine(_win_ctrl_handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_global_ctrl_ref, True)
    except Exception:
        pass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalSocket, QLocalServer
from qfluentwidgets import setTheme, Theme
from ui.fluent_main_window import FluentMainWindow

# Set explicit Windows AppUserModelID so taskbar displays custom icon
import ctypes
try:
    myappid = "soundflow.soundboard.studio.1.0"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass


def get_app_icon() -> QIcon:
    candidates = []
    if hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "assets" / "app_icon.ico")
        candidates.append(Path(sys._MEIPASS) / "assets" / "app_icon.png")
    candidates.extend([
        PROJECT_ROOT / "assets" / "app_icon.ico",
        PROJECT_ROOT / "assets" / "app_icon.png",
        Path(sys.executable).parent / "_internal" / "assets" / "app_icon.ico",
        Path(sys.executable).parent / "assets" / "app_icon.ico"
    ])
    for candidate in candidates:
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


SINGLE_INSTANCE_SERVER = "SoundFlow_Studio_SingleInstance_App"


def main():
    # Enable crisp rendering on high-DPI displays
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("SoundFlow Studio")
    app.setOrganizationName("SoundFlow")

    # Single-instance IPC check:
    # If SoundFlow is already running, wake up existing window and exit this instance cleanly.
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SERVER)
    if socket.waitForConnected(600):
        socket.write(b"ACTIVATE_WINDOW")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        sys.exit(0)

    # We are the primary instance: setup server to receive wake-up calls
    server = QLocalServer()
    QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)
    server.listen(SINGLE_INSTANCE_SERVER)

    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    # Allow graceful termination via Ctrl+C in terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    setTheme(Theme.DARK)
    window = FluentMainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)

    def on_ipc_connection():
        client = server.nextPendingConnection()
        if client:
            client.waitForReadyRead(500)
            msg = bytes(client.readAll()).decode("utf-8", errors="ignore")
            if "ACTIVATE_WINDOW" in msg or not msg:
                window.activate_and_show()
            client.disconnectFromServer()

    server.newConnection.connect(on_ipc_connection)

    window.activate_and_show()

    exit_code = app.exec()
    server.close()
    QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
