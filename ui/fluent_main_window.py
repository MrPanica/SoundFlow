"""
Fluent Design Main Window for SoundFlow Studio.
Builds on Microsoft Windows 11 WinUI 3 Fluent Design System via qfluentwidgets.
Includes Mica material, NavigationInterface, TitleBar actions, and tray integration.
"""

import sys
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel
)
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QColor, QBrush, QPen, QLinearGradient
)
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
    setTheme, Theme, PushButton, PrimaryPushButton,
    InfoBar, InfoBarIcon, InfoBarPosition, CardWidget,
    IconWidget, BodyLabel, CaptionLabel
)

from core.config_manager import ConfigManager
from core.audio_engine import AudioEngine
from core.hotkey_manager import HotkeyManager
from core.driver_manager import DriverManager

from .fluent_soundboard import FluentSoundboardInterface
from .fluent_app_stream import FluentAppStreamInterface
from .fluent_radio import FluentRadioInterface
from .fluent_voice_fx import FluentVoiceFXInterface
from .fluent_tts import FluentTTSInterface
from .fluent_settings import FluentSettingsInterface


class DriverWarningBanner(CardWidget):
    """Inline Windows 11 Fluent Amber Warning Card for Audio Driver."""

    def __init__(self, on_install_callback, on_refresh_callback, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet("""
            DriverWarningBanner {
                background-color: rgba(255, 170, 0, 0.12);
                border: 1px solid rgba(255, 170, 0, 0.45);
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(14)

        icon_lbl = IconWidget(FluentIcon.INFO, self)
        icon_lbl.setFixedSize(24, 24)
        icon_lbl.setStyleSheet("color: #ffa000;")
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        lbl_title = BodyLabel("Виртуальный аудиодрайвер не установлен", self)
        lbl_title.setStyleSheet("font-weight: 700; color: #ffb74d; font-size: 13px;")
        text_col.addWidget(lbl_title)

        lbl_desc = CaptionLabel("Без драйвера звук в микрофон (Discord, игры) не идет. Все вкладки можно тестировать для себя (динамики / наушники).", self)
        lbl_desc.setStyleSheet("color: rgba(255, 255, 255, 0.75); font-size: 11px;")
        text_col.addWidget(lbl_desc)

        layout.addLayout(text_col, stretch=1)

        self.btn_install = PrimaryPushButton(FluentIcon.DOWNLOAD, "Установить в 1 клик", self)
        self.btn_install.setFixedHeight(32)
        self.btn_install.clicked.connect(on_install_callback)
        layout.addWidget(self.btn_install)

        self.btn_refresh = PushButton(FluentIcon.SYNC, "Проверить снова", self)
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(on_refresh_callback)
        layout.addWidget(self.btn_refresh)


class FluentMainWindow(FluentWindow):
    """Windows 11 Native Fluent Design Main Window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SoundFlow Studio")
        self.resize(1060, 720)
        self.setMinimumSize(880, 580)

        # Enable Windows 11 Mica backdrop effect
        if hasattr(self, "setMicaEffectEnabled"):
            try:
                self.setMicaEffectEnabled(True)
            except Exception:
                pass

        self._is_quitting = False

        # 1. Initialize core systems
        self.cfg = ConfigManager()
        self.engine = AudioEngine(
            sample_rate=48000,
            buffer_size=self.cfg.get("buffer_size", 1024)
        )
        self.hotkeys = HotkeyManager()

        # 2. Setup Audio Streams
        saved_target = self.cfg.get("mic_target_device_id")
        if saved_target is None:
            devs = self.engine.get_audio_devices()
            cable_wasapi = None
            cable_any = None
            for d in devs.get("outputs", []):
                n = d["name"].lower()
                h = d.get("hostapi", "").lower()
                if "cable input" in n or "vb-audio" in n or "virtual" in n:
                    if "wasapi" in h and cable_wasapi is None:
                        cable_wasapi = d["id"]
                    elif cable_any is None:
                        cable_any = d["id"]
            best_target = cable_wasapi if cable_wasapi is not None else cable_any
            if best_target is not None:
                saved_target = best_target
                self.cfg.set("mic_target_device_id", best_target)

        self.engine.initialize_streams(
            monitor_device=self.cfg.get("monitor_device_id"),
            mic_target_device=saved_target,
            mic_input_device=self.cfg.get("mic_input_device_id")
        )
        # Sync auto-resolved device IDs back to config so they persist cleanly
        if self.engine.monitor_device_id is not None:
            self.cfg.set("monitor_device_id", self.engine.monitor_device_id)
        if self.engine.mic_target_device_id is not None:
            self.cfg.set("mic_target_device_id", self.engine.mic_target_device_id)
        if self.engine.mic_input_device_id is not None:
            self.cfg.set("mic_input_device_id", self.engine.mic_input_device_id)

        # 3. Check starter sounds
        self._check_starter_sounds()

        # 4. Create Subinterfaces
        self.soundboard_interface = FluentSoundboardInterface(self.engine, self.cfg, self)
        self.app_stream_interface = FluentAppStreamInterface(self.engine, self.cfg, self)
        self.radio_interface = FluentRadioInterface(self.engine, self.cfg, self)
        self.voice_fx_interface = FluentVoiceFXInterface(self.engine, self.cfg, self)
        self.tts_interface = FluentTTSInterface(self.engine, self.cfg, self)
        self.settings_interface = FluentSettingsInterface(self.engine, self.cfg, self)

        # 5. Add Subinterfaces to Navigation
        self._init_navigation()

        # 6. TitleBar Custom Actions
        self._init_titlebar_actions()

        # 7. Setup persistent content container with top driver banner across all tabs
        self._setup_global_content_container()

        # 8. Connect Subinterface Signals
        self._connect_signals()

        # 9. Setup System Tray
        self._setup_tray()

        # 10. Register Global Hotkeys
        self._register_global_hotkeys()

        # 11. Check driver status & show persistent banner on any tab
        self._check_driver_infobar()

        # 12. Dynamic Taskbar & Tray Audio Activity Animation
        self._setup_taskbar_icon_animator()

    def _init_navigation(self):
        self.addSubInterface(self.soundboard_interface, FluentIcon.MUSIC, "Саундборд")
        self.addSubInterface(self.app_stream_interface, FluentIcon.APPLICATION, "Стрим приложений")
        self.addSubInterface(self.radio_interface, FluentIcon.MEGAPHONE, "Интернет-радио")
        self.addSubInterface(self.voice_fx_interface, FluentIcon.MICROPHONE, "Микрофон и FX")
        self.addSubInterface(self.tts_interface, FluentIcon.CHAT, "Синтез речи (TTS)")

        self.addSubInterface(
            self.settings_interface,
            FluentIcon.SETTING,
            "Параметры",
            position=NavigationItemPosition.BOTTOM
        )

    def _init_titlebar_actions(self):
        # Quick actions in titlebar
        try:
            self.btn_replay = PushButton(FluentIcon.HISTORY, "Клип 30с", self.titleBar)
            self.btn_replay.setFixedHeight(28)
            self.btn_replay.setToolTip("Сохранить последние 30 секунд аудио на саундборд [Ctrl+F11]")
            self.btn_replay.clicked.connect(self._save_replay_clip)

            self.btn_stop_all = PushButton(FluentIcon.CANCEL, "Стоп всё [ESC]", self.titleBar)
            self.btn_stop_all.setFixedHeight(28)
            self.btn_stop_all.clicked.connect(self._stop_all_sounds)

            self.titleBar.hBoxLayout.insertSpacing(0, 20)
            self.titleBar.hBoxLayout.insertWidget(1, self.btn_replay)
            self.titleBar.hBoxLayout.insertSpacing(2, 6)
            self.titleBar.hBoxLayout.insertWidget(3, self.btn_stop_all)
            self.titleBar.hBoxLayout.insertSpacing(4, 20)
        except Exception as e:
            print(f"[FluentMainWindow] TitleBar custom widgets notice: {e}")

    def _setup_global_content_container(self):
        """Wraps stackedWidget in a container with a persistent top banner visible on all tabs."""
        self.hBoxLayout.removeWidget(self.stackedWidget)

        self.content_container = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # Global Driver Banner area at top of all tabs
        self.driver_banner_box = QWidget(self.content_container)
        self.driver_banner_layout = QVBoxLayout(self.driver_banner_box)
        self.driver_banner_layout.setContentsMargins(28, 42, 28, 0)
        self.driver_banner_layout.setSpacing(0)
        self.driver_banner_box.setVisible(False)
        self.content_layout.addWidget(self.driver_banner_box)

        # StackedWidget fills the rest underneath the banner
        self.content_layout.addWidget(self.stackedWidget, 1)
        self.hBoxLayout.addWidget(self.content_container, 1)

    def _check_driver_infobar(self):
        """Displays persistent inline warning at the top on ANY tab if driver is not detected."""
        installed = DriverManager.is_driver_installed()
        if not installed:
            for i in reversed(range(self.driver_banner_layout.count())):
                w = self.driver_banner_layout.itemAt(i).widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()

            self.driver_banner = DriverWarningBanner(
                on_install_callback=self._on_install_driver,
                on_refresh_callback=self._on_refresh_driver,
                parent=self.driver_banner_box
            )
            self.driver_banner_layout.addWidget(self.driver_banner)
            self.driver_banner_box.setVisible(True)
        else:
            self.driver_banner_box.setVisible(False)

    def _on_install_driver(self):
        success = DriverManager.launch_installer()
        if success:
            QMessageBox.information(
                self,
                "Установщик запущен",
                "Запущен официальный инсталлятор драйвера VB-Audio Virtual Cable.\n\n"
                "1. Нажмите 'Install Driver' в окне установщика.\n"
                "2. Подтвердите права администратора Windows.\n"
                "3. После завершения нажмите 'Проверить снова' в SoundFlow."
            )
        else:
            DriverManager.open_driver_folder()

    def _on_refresh_driver(self):
        installed = DriverManager.is_driver_installed()
        if installed:
            cable_id = DriverManager.get_cable_device_id()
            if cable_id is not None:
                self.cfg.set("mic_target_device_id", cable_id)
                self.engine.mic_target_device_id = cable_id
                self.engine.initialize_streams(
                    monitor_device=self.cfg.get("monitor_device_id"),
                    mic_target_device=cable_id,
                    mic_input_device=self.cfg.get("mic_input_device_id")
                )

            self.driver_banner_box.setVisible(False)

            InfoBar.success(
                title="Аудиодрайвер готов!",
                content="VB-Audio Virtual Cable обнаружен и подключен. В Discord выберите 'CABLE Output' как микрофон.",
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self
            )
        else:
            QMessageBox.warning(
                self,
                "Драйвер пока не найден",
                "Виртуальный аудиодрайвер не обнаружен.\n\n"
                "Если вы только что завершили установку, Windows может потребоваться перезагрузка ПК для активации драйвера."
            )

    def _connect_signals(self):
        self.soundboard_interface.sound_play_requested.connect(self._on_play_sound)
        self.soundboard_interface.sound_stop_requested.connect(self._on_stop_sound)
        self.soundboard_interface.hotkey_updated.connect(self._on_sound_hotkey_updated)

        self.tts_interface.sound_saved_to_board.connect(self._on_tts_sound_saved)
        self.engine.on_sound_state_changed = self._on_engine_sound_state_changed

    def _check_starter_sounds(self):
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
            self.soundboard_interface.set_sound_playing(sound_id, True)

    def _on_stop_sound(self, sound_id: str):
        self.engine.stop_sound(sound_id)
        self.soundboard_interface.set_sound_playing(sound_id, False)

    def _stop_all_sounds(self):
        self.engine.stop_all()
        self.radio_interface.stop_radio()
        self.app_stream_interface.stop_stream()
        for s in self.cfg.sounds:
            self.soundboard_interface.set_sound_playing(s["id"], False)

    def _on_engine_sound_state_changed(self, sound_id: str, is_playing: bool):
        QTimer.singleShot(0, lambda: self.soundboard_interface.set_sound_playing(sound_id, is_playing))

    def _save_replay_clip(self):
        clips_dir = Path(__file__).parent.parent / "assets" / "sounds" / "clips"
        filepath = self.engine.instant_replay.save_clip(clips_dir)
        if filepath and filepath.exists():
            sound_id = self.soundboard_interface.add_sound_file(str(filepath), category="CLIPS")
            InfoBar.success(
                title="Клип сохранен!",
                content=f"Последние 30 секунд сохранены на Саундборд: {filepath.name}",
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self.soundboard_interface
            )
        else:
            QMessageBox.warning(self, "Внимание", "Не удалось сохранить буфер.")

    def _on_tts_sound_saved(self, filepath: str, name: str):
        self.soundboard_interface.add_sound_file(filepath, category="MEMES")

    def _register_global_hotkeys(self):
        self.hotkeys.clear_all()

        stop_key = self.cfg.get("hotkeys", {}).get("stop_all", "esc")
        self.hotkeys.register(stop_key, self._stop_all_sounds)

        stream_key = self.cfg.get("hotkeys", {}).get("app_stream_toggle", "ctrl+f9")
        self.hotkeys.register(stream_key, self.app_stream_interface._toggle_stream)

        radio_key = self.cfg.get("hotkeys", {}).get("radio_toggle", "ctrl+f10")
        def toggle_radio():
            if self.engine.radio.is_playing:
                self.radio_interface.stop_radio()
            elif len(self.cfg.stations) > 0:
                self.radio_interface._play_station(self.cfg.stations[0])
        self.hotkeys.register(radio_key, toggle_radio)

        clip_key = self.cfg.get("hotkeys", {}).get("instant_replay_clip", "ctrl+f11")
        self.hotkeys.register(clip_key, self._save_replay_clip)

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

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)

        icon_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
        if not icon_path.exists():
            icon_path = Path(sys.executable).parent / "_internal" / "assets" / "app_icon.png"

        self.icon_idle = QIcon(str(icon_path)) if icon_path.exists() else self.windowIcon()
        self.setWindowIcon(self.icon_idle)
        QApplication.setWindowIcon(self.icon_idle)
        self.tray.setIcon(self.icon_idle)

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

    def _setup_taskbar_icon_animator(self):
        """Pre-renders animated active equalizer frames for Windows taskbar and tray icon."""
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
        if not icon_path.exists():
            icon_path = Path(sys.executable).parent / "_internal" / "assets" / "app_icon.png"

        if icon_path.exists():
            base_pix = QPixmap(str(icon_path))
        else:
            base_pix = self.windowIcon().pixmap(64, 64)

        bar_patterns = [
            [6, 16, 10],
            [12, 9, 18],
            [18, 14, 8],
            [10, 18, 14],
            [15, 11, 17],
            [8, 16, 12]
        ]

        self.active_icon_frames = []
        for heights in bar_patterns:
            pix_64 = base_pix.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p = QPainter(pix_64)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Dark rounded badge in TOP-RIGHT corner
            p.setBrush(QColor(10, 15, 28, 235))
            p.setPen(QPen(QColor(0, 230, 118, 220), 1.5))
            p.drawRoundedRect(QRectF(34, 2, 28, 28), 6, 6)

            # Equalizer bars with neon cyan-to-green gradient
            grad = QLinearGradient(0, 8, 0, 26)
            grad.setColorAt(0.0, QColor(0, 229, 255))
            grad.setColorAt(1.0, QColor(0, 255, 136))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)

            xs = [38, 46, 54]
            for x, h in zip(xs, heights):
                p.drawRoundedRect(QRectF(x, 26 - h, 4, h), 1.5, 1.5)
            p.end()

            pix_32 = pix_64.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            frame_icon = QIcon()
            frame_icon.addPixmap(pix_64)
            frame_icon.addPixmap(pix_32)
            self.active_icon_frames.append(frame_icon)

        self._taskbar_frame_idx = 0
        self._is_taskbar_active = False

        self.taskbar_timer = QTimer(self)
        self.taskbar_timer.setInterval(120)
        self.taskbar_timer.timeout.connect(self._update_taskbar_icon_state)
        self.taskbar_timer.start()

    def _update_taskbar_icon_state(self):
        """Checks audio activity and animates Windows taskbar & tray icon when active."""
        if self._is_quitting:
            return

        is_active = self.engine.is_audio_active
        if is_active:
            self._is_taskbar_active = True
            self._taskbar_frame_idx = (self._taskbar_frame_idx + 1) % len(self.active_icon_frames)
            current_icon = self.active_icon_frames[self._taskbar_frame_idx]
            self.setWindowIcon(current_icon)
            QApplication.setWindowIcon(current_icon)
            if hasattr(self, "tray") and self.tray.isVisible():
                self.tray.setIcon(current_icon)
                self.tray.setToolTip("SoundFlow Studio - Идет воспроизведение / трансляция")
        else:
            if self._is_taskbar_active:
                # Smooth transition back to idle
                self._is_taskbar_active = False
                self.setWindowIcon(self.icon_idle)
                QApplication.setWindowIcon(self.icon_idle)
                if hasattr(self, "tray") and self.tray.isVisible():
                    self.tray.setIcon(self.icon_idle)
                    self.tray.setToolTip("SoundFlow Studio - Windows 11 Audio Hub")

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self):
        self.show()
        self.activateWindow()

    def _quit_app(self):
        self._is_quitting = True
        try:
            if hasattr(self, "taskbar_timer"):
                self.taskbar_timer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "tray"):
                self.tray.hide()
        except Exception:
            pass
        try:
            self.radio_interface.title_timer.stop()
            self.voice_fx_interface.meter_timer.stop()
        except Exception:
            pass
        try:
            self.hotkeys.clear_all()
            self.engine.stop_all()
            self.engine.stop_streams()
        except Exception:
            pass
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if self._is_quitting:
            event.accept()
            return

        if self.cfg.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "SoundFlow Studio",
                "Приложение свернуто в трей. Горячие клавиши продолжают работать в играх.",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            self._is_quitting = True
            self._quit_app()
            event.accept()
