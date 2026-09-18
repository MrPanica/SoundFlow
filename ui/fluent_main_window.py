"""
Fluent Design Main Window for SoundFlow Studio.
Builds on Microsoft Windows 11 WinUI 3 Fluent Design System via qfluentwidgets.
Includes Mica material, NavigationInterface, TitleBar actions, and tray integration.
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
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
    setTheme, Theme, PushButton, PrimaryPushButton, TransparentToolButton,
    InfoBar, InfoBarIcon, InfoBarPosition, CardWidget,
    IconWidget, BodyLabel, CaptionLabel, SwitchButton
)

from core.config_manager import ConfigManager
from core.audio_engine import AudioEngine
from core.hotkey_manager import HotkeyManager
from core.driver_manager import DriverManager
from core.i18n import tr, get_i18n

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

        lbl_title = BodyLabel(tr("driver_not_installed_title", "Виртуальный аудиодрайвер не установлен"), self)
        lbl_title.setStyleSheet("font-weight: 700; color: #ffb74d; font-size: 13px;")
        text_col.addWidget(lbl_title)

        lbl_desc = CaptionLabel(
            tr("driver_not_installed_desc", "Без драйвера звук в микрофон (Discord, игры) не идет. Все вкладки можно тестировать для себя (динамики / наушники)."),
            self
        )
        lbl_desc.setStyleSheet("color: rgba(255, 255, 255, 0.75); font-size: 11px;")
        text_col.addWidget(lbl_desc)

        layout.addLayout(text_col, stretch=1)

        self.btn_install = PrimaryPushButton(FluentIcon.DOWNLOAD, tr("driver_install_btn", "Установить в 1 клик"), self)
        self.btn_install.setFixedHeight(32)
        self.btn_install.clicked.connect(on_install_callback)
        layout.addWidget(self.btn_install)

        self.btn_refresh = PushButton(FluentIcon.SYNC, tr("driver_refresh_btn", "Проверить снова"), self)
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.clicked.connect(on_refresh_callback)
        layout.addWidget(self.btn_refresh)


class MicConfigBanner(CardWidget):
    """Inline Windows 11 Fluent Cyan Info Card for Setting Default Game Microphone."""

    def __init__(self, on_set_default, on_dismiss, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet("""
            MicConfigBanner {
                background-color: rgba(0, 150, 255, 0.12);
                border: 1px solid rgba(0, 150, 255, 0.45);
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(14)

        icon_lbl = IconWidget(FluentIcon.MICROPHONE, self)
        icon_lbl.setFixedSize(24, 24)
        icon_lbl.setStyleSheet("color: #38bdf8;")
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        lbl_title = BodyLabel(tr("mic_config_banner_title", "Для передачи звука в игры и Discord"), self)
        lbl_title.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 13px;")
        text_col.addWidget(lbl_title)

        lbl_desc = CaptionLabel(
            tr("mic_config_banner_desc", "Назначьте 'CABLE Output' микрофоном по умолчанию в Windows, чтобы игры (CS2, Dota 2) слышали саундборд и радио."),
            self
        )
        lbl_desc.setStyleSheet("color: rgba(255, 255, 255, 0.85); font-size: 11px;")
        text_col.addWidget(lbl_desc)

        layout.addLayout(text_col, stretch=1)

        self.btn_set_default = PrimaryPushButton(FluentIcon.SETTING, tr("mic_config_set_default_btn", "Сделать по умолчанию"), self)
        self.btn_set_default.setFixedHeight(32)
        self.btn_set_default.clicked.connect(on_set_default)
        layout.addWidget(self.btn_set_default)

        self.btn_dismiss_never = PushButton(FluentIcon.HIDE, tr("mic_config_dismiss_btn", "Больше не напоминать"), self)
        self.btn_dismiss_never.setFixedHeight(32)
        self.btn_dismiss_never.clicked.connect(on_dismiss)
        layout.addWidget(self.btn_dismiss_never)

        self.btn_dismiss = TransparentToolButton(FluentIcon.CLOSE, self)
        self.btn_dismiss.setFixedSize(28, 28)
        self.btn_dismiss.setToolTip(tr("banner_dismiss_tooltip", "Больше не напоминать"))
        self.btn_dismiss.clicked.connect(on_dismiss)
        layout.addWidget(self.btn_dismiss)


class MicPillWidget(QWidget):
    """Clickable pill container for the global microphone toggle in TitleBar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("GlobalMicPill")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_btn: Optional[SwitchButton] = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.switch_btn:
            self.switch_btn.toggleChecked()
            event.accept()
        else:
            super().mousePressEvent(event)


class FluentMainWindow(FluentWindow):
    """Windows 11 Native Fluent Design Main Window."""

    def __init__(self):
        super().__init__()
        self.cfg = ConfigManager()
        get_i18n().set_language(self.cfg.get("language", "auto"))
        self.setWindowTitle(tr("app_title", "SoundFlow Studio"))
        self.resize(1060, 720)
        self.setMinimumSize(880, 580)

        # Enable Windows 11 Mica backdrop effect
        if hasattr(self, "setMicaEffectEnabled"):
            try:
                self.setMicaEffectEnabled(True)
            except Exception:
                pass

        self._is_quitting = False

        # Stop any standby mic repeater that was running while SoundFlow was closed
        DriverManager.stop_mic_repeater()

        # 1. Initialize core systems
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

        # Remember physical microphone endpoint ID if CABLE is not currently default
        try:
            if not DriverManager.is_cable_output_default():
                cur_mic = DriverManager.get_current_default_recording_endpoint_id()
                if cur_mic:
                    self.cfg.set("saved_physical_mic_id", cur_mic)
                    DriverManager._saved_physical_mic_id = cur_mic
        except Exception:
            pass

        # Initialize Auto-PTT, Voice Ducking, and Loudness Normalization from config
        if hasattr(self.engine, "ptt") and self.engine.ptt:
            self.engine.ptt.update_config(
                key=self.cfg.get("ptt_key", "v"),
                release_delay_sec=self.cfg.get("ptt_delay_ms", 150) / 1000.0,
                enabled=self.cfg.get("ptt_enabled", False)
            )
        self.engine.ducking_enabled = bool(self.cfg.get("ducking_enabled", True))
        self.engine.ducking_amount = float(self.cfg.get("ducking_amount", 0.25))
        self.engine.ducking_threshold_db = float(self.cfg.get("ducking_threshold_db", -35.0))
        self.engine.auto_normalize_enabled = bool(self.cfg.get("auto_normalize", True))

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
        self.addSubInterface(self.soundboard_interface, FluentIcon.MUSIC, tr("nav_soundboard", "Саундборд"))
        self.addSubInterface(self.app_stream_interface, FluentIcon.APPLICATION, tr("nav_app_stream", "Стрим приложений"))
        self.addSubInterface(self.radio_interface, FluentIcon.MEGAPHONE, tr("nav_radio", "Интернет-радио"))
        self.addSubInterface(self.voice_fx_interface, FluentIcon.MICROPHONE, tr("nav_voice_fx", "Микрофон и FX"))
        self.addSubInterface(self.tts_interface, FluentIcon.CHAT, tr("nav_tts", "Синтез речи (TTS)"))

        self.addSubInterface(
            self.settings_interface,
            FluentIcon.SETTING,
            tr("nav_settings", "Параметры"),
            position=NavigationItemPosition.BOTTOM
        )

    def _init_titlebar_actions(self):
        # Quick actions in titlebar
        try:
            # Global Microphone Voice Passthrough Toggle (Mute/Unmute Real Voice everywhere)
            self.mic_pill = MicPillWidget(self.titleBar)
            self.mic_pill.setObjectName("GlobalMicPill")
            mic_layout = QHBoxLayout(self.mic_pill)
            mic_layout.setContentsMargins(8, 2, 8, 2)
            mic_layout.setSpacing(6)

            self.mic_icon = IconWidget(FluentIcon.MICROPHONE, self.mic_pill)
            self.mic_icon.setFixedSize(16, 16)
            self.mic_icon.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

            self.switch_global_mic = SwitchButton(tr("titlebar_my_voice", "Мой голос"), self.mic_pill)
            self.switch_global_mic.setCursor(Qt.CursorShape.PointingHandCursor)
            self.switch_global_mic.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.switch_global_mic.mousePressEvent = lambda e: e.accept()
            self.mic_pill.switch_btn = self.switch_global_mic
            self.switch_global_mic.setOnText(tr("titlebar_on_air", "В эфире"))
            self.switch_global_mic.setOffText(tr("titlebar_muted", "Заглушен"))
            init_mic = bool(self.cfg.get("mic_passthrough_enabled", True))
            self.engine.mic_passthrough_enabled = init_mic
            self.switch_global_mic.setChecked(init_mic)
            self.switch_global_mic.setToolTip(
                tr(
                    "titlebar_mic_tooltip",
                    "Глобальный тумблер вашего микрофона (голоса) [Ctrl+F12]:\n"
                    "• ВКЛ — тиммейты слышат ваш голос в игре и Discord.\n"
                    "• ВЫКЛ — ваш голос заглушен (радио и саундборд продолжают играть)."
                )
            )
            self.switch_global_mic.checkedChanged.connect(self._on_global_mic_toggled)

            mic_layout.addWidget(self.mic_icon)
            mic_layout.addWidget(self.switch_global_mic)
            self._update_global_mic_visuals(init_mic)

            self.btn_replay = PushButton(FluentIcon.HISTORY, tr("titlebar_clip_30s", "Клип 30с"), self.titleBar)
            self.btn_replay.setFixedHeight(28)
            self.btn_replay.setToolTip(tr("titlebar_clip_tooltip", "Сохранить последние 30 секунд аудио на саундборд [Ctrl+F11]"))
            self.btn_replay.clicked.connect(self._save_replay_clip)

            self.btn_stop_all = PushButton(FluentIcon.CANCEL, tr("titlebar_stop_all", "Стоп всё [ESC]"), self.titleBar)
            self.btn_stop_all.setFixedHeight(28)
            self.btn_stop_all.clicked.connect(self._stop_all_sounds)

            self.titleBar.hBoxLayout.insertSpacing(0, 16)
            self.titleBar.hBoxLayout.insertWidget(1, self.mic_pill)
            self.titleBar.hBoxLayout.insertSpacing(2, 8)
            self.titleBar.hBoxLayout.insertWidget(3, self.btn_replay)
            self.titleBar.hBoxLayout.insertSpacing(4, 6)
            self.titleBar.hBoxLayout.insertWidget(5, self.btn_stop_all)
            self.titleBar.hBoxLayout.insertSpacing(6, 16)
        except Exception as e:
            print(f"[FluentMainWindow] TitleBar custom widgets notice: {e}")

    def _update_global_mic_visuals(self, is_checked: bool):
        if not hasattr(self, "mic_pill"):
            return
        if is_checked:
            self.mic_icon.setStyleSheet("color: #4caf50;")
            self.mic_pill.setStyleSheet("""
                #GlobalMicPill {
                    background-color: rgba(76, 175, 80, 0.12);
                    border: 1px solid rgba(76, 175, 80, 0.35);
                    border-radius: 6px;
                }
            """)
        else:
            self.mic_icon.setStyleSheet("color: #f44336;")
            self.mic_pill.setStyleSheet("""
                #GlobalMicPill {
                    background-color: rgba(244, 67, 54, 0.12);
                    border: 1px solid rgba(244, 67, 54, 0.35);
                    border-radius: 6px;
                }
            """)

    def _on_global_mic_toggled(self, is_checked: bool):
        self.engine.mic_passthrough_enabled = is_checked
        self.cfg.set("mic_passthrough_enabled", is_checked)
        self._update_global_mic_visuals(is_checked)
        if is_checked:
            if not self.engine.mic_input_stream or not self.engine.mic_input_stream.active:
                self.engine.start_mic_input()
        if hasattr(self, "voice_fx_interface") and hasattr(self.voice_fx_interface, "switch_mic"):
            self.voice_fx_interface.switch_mic.blockSignals(True)
            self.voice_fx_interface.switch_mic.setChecked(is_checked)
            self.voice_fx_interface.switch_mic.blockSignals(False)
            if not is_checked and hasattr(self.voice_fx_interface, "switch_preview"):
                if self.voice_fx_interface.switch_preview.isChecked():
                    self.voice_fx_interface.switch_preview.setChecked(False)

    def sync_global_mic_switch(self, is_checked: bool):
        """Synchronizes global titlebar mic switch when changed from Voice FX tab."""
        if hasattr(self, "switch_global_mic"):
            self.switch_global_mic.blockSignals(True)
            self.switch_global_mic.setChecked(is_checked)
            self.switch_global_mic.blockSignals(False)
            self._update_global_mic_visuals(is_checked)

    def _setup_global_content_container(self):
        """Wraps stackedWidget in a container with a persistent top banner visible on all tabs."""
        self.widgetLayout.removeWidget(self.stackedWidget)

        self.content_container = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # Global Driver Banner area at top of all tabs
        self.driver_banner_box = QWidget(self.content_container)
        self.driver_banner_layout = QVBoxLayout(self.driver_banner_box)
        self.driver_banner_layout.setContentsMargins(28, 10, 28, 0)
        self.driver_banner_layout.setSpacing(0)
        self.driver_banner_box.setVisible(False)
        self.content_layout.addWidget(self.driver_banner_box)

        # StackedWidget fills the rest underneath the banner
        self.content_layout.addWidget(self.stackedWidget, 1)
        self.widgetLayout.addWidget(self.content_container)
        self.navigationInterface.displayModeChanged.connect(self.titleBar.raise_)
        self.titleBar.raise_()

    def _check_driver_infobar(self):
        """Displays persistent inline warning at the top on ANY tab if driver is not detected or mic not configured."""
        installed = DriverManager.is_driver_installed()
        for i in reversed(range(self.driver_banner_layout.count())):
            w = self.driver_banner_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        if not installed:
            self.driver_banner = DriverWarningBanner(
                on_install_callback=self._on_install_driver,
                on_refresh_callback=self._on_refresh_driver,
                parent=self.driver_banner_box
            )
            self.driver_banner_layout.addWidget(self.driver_banner)
            self.driver_banner_box.setVisible(True)
        elif not DriverManager.is_cable_output_default():
            if self.cfg.get("hide_cable_default_banner", False):
                self.driver_banner_box.setVisible(False)
                return
            banner = MicConfigBanner(
                on_set_default=self._on_set_default_recording_device,
                on_dismiss=self._on_dismiss_cable_banner,
                parent=self.driver_banner_box
            )
            self.driver_banner_layout.addWidget(banner)
            self.driver_banner_box.setVisible(True)
        else:
            self.driver_banner_box.setVisible(False)

    def _on_dismiss_cable_banner(self):
        self.cfg.set("hide_cable_default_banner", True)
        self.driver_banner_box.setVisible(False)

    def set_global_mic_enabled(self, is_enabled: bool):
        """Sets global microphone enabled and updates all UI switches and engine state."""
        if hasattr(self, "switch_global_mic"):
            self.switch_global_mic.setChecked(is_enabled)
        else:
            self._on_global_mic_toggled(is_enabled)

    def _sync_all_default_mic_buttons(self, is_cable: Optional[bool] = None):
        """Updates default mic button text and icon across all interfaces."""
        if is_cable is None:
            is_cable = DriverManager.is_cable_output_default()
        for tab in [
            getattr(self, "app_stream_interface", None),
            getattr(self, "voice_fx_interface", None),
            getattr(self, "radio_interface", None)
        ]:
            if tab and hasattr(tab, "update_default_mic_btn_state"):
                tab.update_default_mic_btn_state(is_cable)

    def toggle_default_recording_device(self, parent_widget=None) -> bool:
        """Toggles Windows default recording device between CABLE Output and physical microphone."""
        is_cable = DriverManager.is_cable_output_default()
        parent = parent_widget or self
        if is_cable:
            ok = DriverManager.restore_physical_recording_device()
            self._sync_all_default_mic_buttons(False)
            self._check_driver_infobar()
            if ok:
                InfoBar.success(
                    title=tr("mic_restored_success_title", "Микрофон возвращен"),
                    content=tr("mic_restored_success_msg", "Основной микрофон снова назначен устройством по умолчанию в Windows."),
                    position=InfoBarPosition.TOP,
                    duration=4000,
                    parent=parent
                )
            return False
        else:
            ok = DriverManager.set_default_recording_device_to_cable()
            if self.engine.mic_target_device_id is None or self.engine.mic_target_stream is None or not self.engine.mic_target_stream.active:
                cable_target = self.engine.get_default_devices().get("mic_target")
                if cable_target is not None:
                    self.set_global_target_microphone(cable_target)
            self.set_global_mic_enabled(True)
            self._sync_all_default_mic_buttons(True)
            self._check_driver_infobar()
            if ok:
                InfoBar.success(
                    title=tr("mic_default_success_title"),
                    content=tr("mic_default_success_msg"),
                    position=InfoBarPosition.TOP,
                    duration=4500,
                    parent=parent
                )
            else:
                InfoBar.info(
                    title=tr("mic_default_manual_title"),
                    content=tr("mic_default_manual_msg"),
                    position=InfoBarPosition.TOP,
                    duration=5000,
                    parent=parent
                )
            return True

    def _on_set_default_recording_device(self):
        self.toggle_default_recording_device(parent_widget=self)

    def _on_install_driver(self):
        success = DriverManager.launch_installer()
        if success:
            QMessageBox.information(
                self,
                tr("driver_installer_title"),
                tr("driver_installer_msg")
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
                title=tr("driver_ready_title"),
                content=tr("driver_ready_msg"),
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self
            )
        else:
            QMessageBox.warning(
                self,
                tr("driver_not_found_title"),
                tr("driver_not_found_msg")
            )

    def _connect_signals(self):
        self.soundboard_interface.sound_play_requested.connect(self._on_play_sound)
        self.soundboard_interface.sound_stop_requested.connect(self._on_stop_sound)
        self.soundboard_interface.hotkey_updated.connect(self._on_sound_hotkey_updated)

        self.tts_interface.sound_saved_to_board.connect(self._on_tts_sound_saved)
        self.engine.on_sound_state_changed = self._on_engine_sound_state_changed
        self.engine.on_mic_target_changed = lambda dev_id: QTimer.singleShot(0, lambda: self.sync_all_target_mic_combos(dev_id))

    def set_global_target_microphone(self, device_id: Optional[int], source_tab=None):
        """
        Centrally changes the target microphone across the audio engine and
        synchronizes the selection across all tabs (App Stream, Radio, Voice FX, TTS, Settings).
        """
        if getattr(self, "_syncing_target_mic", False):
            return
        self._syncing_target_mic = True
        try:
            self.cfg.set("mic_target_device_id", device_id)
            self.engine.set_mic_target_device(device_id)

            for iface in [
                getattr(self, "soundboard_interface", None),
                getattr(self, "app_stream_interface", None),
                getattr(self, "radio_interface", None),
                getattr(self, "voice_fx_interface", None),
                getattr(self, "tts_interface", None),
                getattr(self, "settings_interface", None),
            ]:
                if iface is not None and iface is not source_tab:
                    if hasattr(iface, "sync_target_mic"):
                        try:
                            iface.sync_target_mic(device_id)
                        except Exception as e:
                            print(f"[FluentMainWindow] Error syncing target mic in {iface}: {e}")
        finally:
            self._syncing_target_mic = False

    def sync_all_target_mic_combos(self, device_id: Optional[int]):
        """Synchronizes all target mic combo boxes when changed from engine or settings."""
        if getattr(self, "_syncing_target_mic", False):
            return
        self._syncing_target_mic = True
        try:
            for iface in [
                getattr(self, "soundboard_interface", None),
                getattr(self, "app_stream_interface", None),
                getattr(self, "radio_interface", None),
                getattr(self, "voice_fx_interface", None),
                getattr(self, "tts_interface", None),
                getattr(self, "settings_interface", None),
            ]:
                if iface is not None and hasattr(iface, "sync_target_mic"):
                    try:
                        iface.sync_target_mic(device_id)
                    except Exception as e:
                        print(f"[FluentMainWindow] Error syncing target mic in {iface}: {e}")
        finally:
            self._syncing_target_mic = False

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
                title=tr("clip_saved_title"),
                content=tr("clip_saved_msg", name=filepath.name),
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self.soundboard_interface
            )
        else:
            QMessageBox.warning(self, tr("clip_error_title"), tr("clip_error_msg"))

    def _on_tts_sound_saved(self, filepath: str, name: str):
        self.soundboard_interface.add_sound_file(filepath, category="MEMES")

    def _register_global_hotkeys(self):
        self.hotkeys.clear_all()

        def _gui(cb):
            return lambda: QTimer.singleShot(0, cb)

        stop_key = self.cfg.get("hotkeys", {}).get("stop_all", "esc")
        self.hotkeys.register(stop_key, _gui(self._stop_all_sounds))

        stream_key = self.cfg.get("hotkeys", {}).get("app_stream_toggle", "ctrl+f9")
        self.hotkeys.register(stream_key, _gui(self.app_stream_interface._toggle_stream))

        radio_key = self.cfg.get("hotkeys", {}).get("radio_toggle", "ctrl+f10")
        def toggle_radio():
            if self.engine.radio.is_playing:
                self.radio_interface.stop_radio()
            elif len(self.cfg.stations) > 0:
                self.radio_interface._play_station(self.cfg.stations[0])
        self.hotkeys.register(radio_key, _gui(toggle_radio))

        clip_key = self.cfg.get("hotkeys", {}).get("instant_replay_clip", "ctrl+f11")
        self.hotkeys.register(clip_key, _gui(self._save_replay_clip))

        mic_key = self.cfg.get("hotkeys", {}).get("mic_mute_toggle", "ctrl+f12")
        def toggle_global_mic():
            new_state = not self.engine.mic_passthrough_enabled
            if hasattr(self, "switch_global_mic"):
                self.switch_global_mic.setChecked(new_state)
            else:
                self._on_global_mic_toggled(new_state)
        self.hotkeys.register(mic_key, _gui(toggle_global_mic))

        rand_key = self.cfg.get("random_sound_hotkey") or self.cfg.get("hotkeys", {}).get("random_sound")
        if rand_key:
            self.hotkeys.register(rand_key, _gui(self._trigger_random_sound))

        for s in self.cfg.sounds:
            hotkey = s.get("hotkey")
            if hotkey:
                self._register_sound_hotkey(s["id"], hotkey)

    def _trigger_random_sound(self):
        if hasattr(self, "soundboard_interface"):
            self.soundboard_interface._play_random_sound()

    def _register_sound_hotkey(self, sound_id: str, hotkey: str):
        sound = next((x for x in self.cfg.sounds if x["id"] == sound_id), None)
        if not sound:
            return

        play_mode = sound.get("play_mode", "normal")
        if play_mode == "hold":
            def on_press(s=sound):
                QTimer.singleShot(0, lambda: self._on_play_sound(s))
            def on_release(sid=sound_id):
                QTimer.singleShot(0, lambda: self._on_stop_sound(sid))
            self.hotkeys.register_hold(hotkey, on_press, on_release)
        else:
            def on_press(sid=sound_id):
                s = next((x for x in self.cfg.sounds if x["id"] == sid), None)
                if s:
                    if self.engine.is_sound_playing(sid):
                        self._on_stop_sound(sid)
                    else:
                        self._on_play_sound(s)
            self.hotkeys.register(hotkey, lambda: QTimer.singleShot(0, on_press))

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
        self.tray.setToolTip(tr("tray_tooltip", "SoundFlow Studio - Windows 11 Audio Hub"))

        menu = QMenu()
        act_show = menu.addAction(tr("tray_open", "Открыть SoundFlow Studio"))
        act_show.triggered.connect(self._show_window)
        act_stop = menu.addAction(tr("tray_stop_all", "Остановить все звуки (ESC)"))
        act_stop.triggered.connect(self._stop_all_sounds)
        menu.addSeparator()
        act_quit = menu.addAction(tr("tray_quit", "Выход"))
        act_quit.triggered.connect(self._quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._show_window)
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
                self.tray.setToolTip(tr("tray_tooltip_active", "SoundFlow Studio - Идет воспроизведение / трансляция"))
        else:
            if self._is_taskbar_active:
                # Smooth transition back to idle
                self._is_taskbar_active = False
                self.setWindowIcon(self.icon_idle)
                QApplication.setWindowIcon(self.icon_idle)
                if hasattr(self, "tray") and self.tray.isVisible():
                    self.tray.setIcon(self.icon_idle)
                    self.tray.setToolTip(tr("tray_tooltip", "SoundFlow Studio - Windows 11 Audio Hub"))

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

        # Stop app capture and WinRT routing so routed apps are never stranded
        try:
            if hasattr(self, "app_stream_interface") and hasattr(self.app_stream_interface, "capture_manager"):
                self.app_stream_interface.capture_manager.stop_capture()
        except Exception:
            pass
        try:
            from core.app_router import WindowsAppAudioRouter
            WindowsAppAudioRouter().restore_all()
        except Exception:
            pass

        # Handle microphone on exit so voice never breaks in Discord / games
        mic_exit_behavior = self.cfg.get("exit_mic_behavior", "restore_default")
        if mic_exit_behavior in ("restore_default", "both"):
            if DriverManager.is_cable_output_default():
                DriverManager.restore_physical_recording_device()
        if mic_exit_behavior in ("repeater", "both") and DriverManager.is_driver_installed():
            DriverManager.start_mic_repeater(
                mic_id=self.engine.mic_input_device_id,
                cable_id=self.engine.mic_target_device_id
            )

        self.close()
        QApplication.instance().quit()

    def activate_and_show(self):
        """Restores window from tray or minimized state and brings it to the foreground."""
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.raise_()
        self.activateWindow()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "titleBar"):
            self.titleBar.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        if hasattr(self, "titleBar"):
            self.titleBar.raise_()

    def closeEvent(self, event):
        if self._is_quitting:
            event.accept()
            return

        if self.cfg.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            if self.cfg.get("notify_on_minimize", True):
                self.tray.showMessage(
                    tr("tray_minimized_title", "SoundFlow Studio"),
                    tr("tray_minimized_msg", "Приложение свернуто в трей и работает в фоновом режиме. Горячие клавиши активны."),
                    self.icon_idle,
                    3000
                )
        else:
            self._is_quitting = True
            self._quit_app()
            event.accept()
