"""
SoundFlow Studio — Application Entry Point.
Launches the PyQt6 desktop interface and configures high-DPI scaling.
"""

import sys
import signal
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
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
    for candidate in [
        PROJECT_ROOT / "assets" / "app_icon.ico",
        PROJECT_ROOT / "assets" / "app_icon.png",
        Path(sys.executable).parent / "_internal" / "assets" / "app_icon.ico",
        Path(sys.executable).parent / "assets" / "app_icon.ico"
    ]:
        if candidate.exists():
            return QIcon(str(candidate))
    return QIcon()


def main():
    # Enable crisp rendering on high-DPI displays
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("SoundFlow Studio")
    app.setOrganizationName("SoundFlow")

    icon = get_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    # Allow graceful termination via Ctrl+C in terminal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    setTheme(Theme.DARK)
    window = FluentMainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
