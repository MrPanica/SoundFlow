"""
Main Window for SoundFlow Studio.
Houses the master header bar, VU meters, tabs, system tray, and global hotkeys coordinator.
"""

import os
import sys
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QSystemTrayIcon, QMenu, QMessageBox,
    QApplication, QFrame
)
from PyQt6.QtGui import QIcon, QAction, QPixmap, QColor, QPainter

from core.config_manager import ConfigManager
from core.audio_engine import AudioEngine
from core.hotkey_manager import HotkeyManager

from ui.styles import MAIN_STYLE
from ui.widgets import VUMeterWidget
from ui.soundboard_tab import SoundboardTab
from ui.app_stream_tab import AppStreamTab
from ui.radio_tab import RadioTab
from ui.voice_fx_tab import VoiceFXTab
from ui.tts_tab import TTSTab
from ui.settings_dialog import SettingsDialog
from ui.driver_banner import DriverBanner


class MainWindow(QMainWindow):
    """Primary application window for SoundFlow Studio."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SoundFlow Studio — Next-Gen Soundpad & Audio Station")
        self.resize(960, 680)
        self.setMinimumSize(800, 560)

        # 1. Initialize core systems
        self.cfg = ConfigManager()
        self.engine = AudioEngine(
            sample_rate=48000,
            buffer_size=self.cfg.get("buffer_size", 1024)
        )
        self.hotkeys = HotkeyManager()

        # Apply Global Style
        self.setStyleSheet(MAIN_STYLE)

        # 2. Setup Audio Streams
        self.engine.initialize_streams(
            monitor_device=self.cfg.get("monitor_device_id"),
            mic_target_device=self.cfg.get("mic_target_device_id"),
            mic_input_device=self.cfg.get("mic_input_device_id")
        )

        # 3. Populate starter sounds if library is empty
        self._check_starter_sounds()

        # 4. Build UI
        self._build_ui()

        # 5. Connect signals
        self._connect_signals()

        # 6. Setup System Tray
        self._setup_tray()

        # 7. Setup Global Hotkeys
        self._register_global_hotkeys()

        # 8. Start VU Meter Timer (~30 FPS)
        self.vu_timer = QTimer(self)
        self.vu_timer.timeout.connect(self._update_master_meters)
        self.vu_timer.start(33)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(12)

        # ---------------- Master Header Bar ----------------
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 12px;
                padding: 6px 14px;
            }
        """)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(10, 6, 10, 6)
        h_layout.setSpacing(16)

        # App Logo & Branding
        logo_layout = QVBoxLayout()
        logo_layout.setSpacing(1)
        lbl_brand = QLabel("⚡ SOUNDFLOW STUDIO")
        lbl_brand.setStyleSheet("font-size: 16px; font-weight: 900; color: #00f2fe; letter-spacing: 1px;")
        lbl_tag = QLabel("Soundpad++ & Live App Audio Hub")
        lbl_tag.setStyleSheet("font-size: 10px; color: #64748b; font-weight: 600;")
        logo_layout.addWidget(lbl_brand)
        logo_layout.addWidget(lbl_tag)
        h_layout.addLayout(logo_layout)

        h_layout.addSpacing(10)

        # Master Stereo VU Meters
        self.vu_monitor = VUMeterWidget(label="НАУШНИКИ (ВЫ)")
        self.vu_monitor.setFixedWidth(140)
        h_layout.addWidget(self.vu_monitor)

        self.vu_mic = VUMeterWidget(label="В МИКРОФОН (ДИСКОРД)")
        self.vu_mic.setFixedWidth(140)
        h_layout.addWidget(self.vu_mic)

        h_layout.addStretch()

        # Instant Replay Button (Save 30s)
        self.btn_replay_clip = QPushButton("⏺️ КЛИП (30 С)")
        self.btn_replay_clip.setFixedHeight(34)
        self.btn_replay_clip.setStyleSheet("""
            QPushButton {
                background: #1e1b4b;
                color: #a5b4fc;
                border: 1px solid #4338ca;
                border-radius: 8px;
                font-weight: 700;
                font-size: 12px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background: #312e81;
                color: #ffffff;
            }
        """)
        self.btn_replay_clip.setToolTip("Сохранить последние 30 секунд аудио на саундборд [Ctrl+F11]")
        self.btn_replay_clip.clicked.connect(self._save_replay_clip)
        h_layout.addWidget(self.btn_replay_clip)

        # Master Panic Stop Button
        self.btn_stop_all = QPushButton("■ СТОП ВСЁ [ESC]")
        self.btn_stop_all.setObjectName("DangerButton")
        self.btn_stop_all.setFixedHeight(34)
        self.btn_stop_all.clicked.connect(self._stop_all_sounds)
        h_layout.addWidget(self.btn_stop_all)

        # Settings Dialog Button
        self.btn_settings = QPushButton("⚙️ Настройки")
        self.btn_settings.setFixedHeight(34)
        self.btn_settings.clicked.connect(self._open_settings)
        h_layout.addWidget(self.btn_settings)

        main_layout.addWidget(header)

        # Driver Status & Setup Banner
        self.driver_banner = DriverBanner(self.engine, self.cfg)
        main_layout.addWidget(self.driver_banner)

        # ---------------- Main Tab Widget ----------------
        self.tabs = QTabWidget()

        # Tab 1: Soundboard
        self.tab_soundboard = SoundboardTab(self.cfg)
        self.tabs.addTab(self.tab_soundboard, "🎵 Саундборд")

        # Tab 2: App Stream
        self.tab_app_stream = AppStreamTab(self.engine, self.cfg)
        self.tabs.addTab(self.tab_app_stream, "🔀 Стрим из приложений")

        # Tab 3: Online Radio
        self.tab_radio = RadioTab(self.engine, self.cfg)
        self.tabs.addTab(self.tab_radio, "📻 Онлайн-Радио")

        # Tab 4: Voice FX
        self.tab_voice_fx = VoiceFXTab(self.engine, self.cfg)
        self.tabs.addTab(self.tab_voice_fx, "🎙️ Микрофон и Voice FX")

        # Tab 5: TTS
        self.tab_tts = TTSTab(self.engine, self.cfg)
        self.tabs.addTab(self.tab_tts, "🗣️ Нейросеть TTS")

        main_layout.addWidget(self.tabs, stretch=1)

    def _connect_signals(self):
        # Soundboard playback
        self.tab_soundboard.sound_play_requested.connect(self._on_play_sound)
        self.tab_soundboard.sound_stop_requested.connect(self._on_stop_sound)
        self.tab_soundboard.hotkey_updated.connect(self._on_sound_hotkey_updated)

        # TTS sound save
        self.tab_tts.sound_saved_to_board.connect(self._on_tts_sound_saved)

        # Audio engine playback state change
        self.engine.on_sound_state_changed = self._on_engine_sound_state_changed

    def _check_starter_sounds(self):
        """Adds starter sounds if the sound list is empty."""
        if len(self.cfg.sounds) == 0:
            sounds_dir = Path(__file__).parent.parent / "assets" / "sounds"
            if sounds_dir.exists():
                for sound_file in sounds_dir.glob("*.wav"):
                    name = sound_file.stem.replace("_", " ").title()
                    sound_data = {
                        "id": f"starter_{sound_file.stem}",
                        "name": name,
                        "path": str(sound_file),
                        "category": "SFX",
                        "hotkey": "",
                        "volume": 1.0,
                        "pitch": 1.0,
                        "speed": 1.0,
                        "favorite": False
                    }
                    self.cfg.sounds.append(sound_data)
                self.cfg.save_sounds()

    def _on_play_sound(self, sound_data: dict):
        sound_id = sound_data["id"]
        filepath = sound_data.get("path", "")
        volume = sound_data.get("volume", 1.0)
        speed = sound_data.get("speed", 1.0)
        pitch = sound_data.get("pitch", 1.0)

        success = self.engine.play_sound(
            sound_id=sound_id,
            filepath=filepath,
            volume=volume,
            speed=speed,
            pitch=pitch
        )
        if success:
            self.tab_soundboard.set_sound_playing(sound_id, True)

    def _on_stop_sound(self, sound_id: str):
        self.engine.stop_sound(sound_id)
        self.tab_soundboard.set_sound_playing(sound_id, False)

    def _stop_all_sounds(self):
        self.engine.stop_all()
        self.tab_radio.stop_radio()
        self.tab_app_stream.stop_stream()
        for s in self.cfg.sounds:
            self.tab_soundboard.set_sound_playing(s["id"], False)

    def _on_engine_sound_state_changed(self, sound_id: str, is_playing: bool):
        # Notify soundboard tab
        QTimer.singleShot(0, lambda: self.tab_soundboard.set_sound_playing(sound_id, is_playing))

    def _save_replay_clip(self):
        clips_dir = Path(__file__).parent.parent / "assets" / "sounds" / "clips"
        filepath = self.engine.instant_replay.save_clip(clips_dir)
        if filepath and filepath.exists():
            sound_id = self.tab_soundboard.add_sound_file(str(filepath), category="CLIPS")
            QMessageBox.information(
                self,
                "Клип сохранен!",
                f"Последние 30 секунд аудио успешно сохранены и добавлены на Саундборд!\nФайл: {filepath.name}"
            )
        else:
            QMessageBox.warning(self, "Внимание", "Не удалось сохранить буфер. Проверьте воспроизведение аудио.")

    def _on_tts_sound_saved(self, filepath: str, name: str):
        self.tab_soundboard.add_sound_file(filepath, category="MEMES")

    def _open_settings(self):
        dlg = SettingsDialog(self.engine, self.cfg, parent=self)
        dlg.exec()

    # ---------------- Global Hotkeys ----------------
    def _register_global_hotkeys(self):
        self.hotkeys.clear_all()

        # Panic Stop (ESC)
        stop_key = self.cfg.get("hotkeys", {}).get("stop_all", "esc")
        self.hotkeys.register(stop_key, self._stop_all_sounds)

        # App stream toggle
        stream_key = self.cfg.get("hotkeys", {}).get("app_stream_toggle", "ctrl+f9")
        self.hotkeys.register(stream_key, self.tab_app_stream._toggle_stream)

        # Radio toggle
        radio_key = self.cfg.get("hotkeys", {}).get("radio_toggle", "ctrl+f10")
        def toggle_radio():
            if self.engine.radio.is_playing:
                self.tab_radio.stop_radio()
            elif len(self.cfg.stations) > 0:
                self.tab_radio._play_station(self.cfg.stations[0])
        self.hotkeys.register(radio_key, toggle_radio)

        # Replay clip
        clip_key = self.cfg.get("hotkeys", {}).get("instant_replay_clip", "ctrl+f11")
        self.hotkeys.register(clip_key, self._save_replay_clip)

        # Per-sound hotkeys
        for s in self.cfg.sounds:
            hotkey = s.get("hotkey")
            if hotkey:
                self._register_sound_hotkey(s["id"], hotkey)

    def _register_sound_hotkey(self, sound_id: str, hotkey: str):
        def on_press(sid=sound_id):
            sound = next((x for x in self.cfg.sounds if x["id"] == sid), None)
            if sound:
                self._on_play_sound(sound)
        self.hotkeys.register(hotkey, on_press)

    def _on_sound_hotkey_updated(self, sound_id: str, hotkey: str):
        self._register_global_hotkeys()

    # ---------------- System Tray ----------------
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)

        # Load custom generated app icon
        icon = None
        for candidate in [
            Path(__file__).resolve().parent.parent / "assets" / "app_icon.png",
            Path(__file__).resolve().parent.parent / "assets" / "app_icon.ico",
            Path(sys.executable).parent / "_internal" / "assets" / "app_icon.png",
            Path(sys.executable).parent / "assets" / "app_icon.png"
        ]:
            if candidate.exists():
                icon = QIcon(str(candidate))
                break

        if icon is None or icon.isNull():
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(0, 0, 0, 0))
            p = QPainter(pixmap)
            p.setBrush(QColor("#00f2fe"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(2, 2, 28, 28, 6, 6)
            p.setPen(QColor("#0b0f19"))
            p.drawText(8, 20, "SF")
            p.end()
            icon = QIcon(pixmap)

        self.setWindowIcon(icon)
        self.tray.setIcon(icon)

        menu = QMenu()
        act_show = menu.addAction("Открыть SoundFlow")
        act_show.triggered.connect(self._show_window)

        act_stop = menu.addAction("Остановить все звуки (ESC)")
        act_stop.triggered.connect(self._stop_all_sounds)

        menu.addSeparator()
        act_quit = menu.addAction("Выход")
        act_quit.triggered.connect(self._quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self):
        self.show()
        self.activateWindow()

    def _quit_app(self):
        try:
            self.vu_timer.stop()
            self.tab_radio.title_timer.stop()
            self.tab_voice_fx.meter_timer.stop()
        except Exception:
            pass
        self.hotkeys.clear_all()
        self.engine.stop_all()
        self.engine.stop_streams()
        QApplication.quit()

    def closeEvent(self, event):
        if self.cfg.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "SoundFlow Studio",
                "Приложение свернуто в трей и продолжает работать. Горячие клавиши активны в играх.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            self._quit_app()
            event.accept()

    def _update_master_meters(self):
        self.vu_monitor.set_levels(self.engine.monitor_peak)
        self.vu_mic.set_levels(self.engine.mic_peak)
