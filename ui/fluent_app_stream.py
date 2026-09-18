"""
Fluent Design Application Audio Stream Interface for SoundFlow Studio.
Enables real-time pass-through audio capture from running processes into microphone.
"""

import os
import subprocess
import psutil
from typing import Optional, List, Dict, Any, Set
from PyQt6.QtCore import Qt, pyqtSignal, QFileInfo, QTimer, QSize, QPoint, QRectF
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QAction
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QFileIconProvider,
    QPushButton, QStyle, QListWidgetItem
)
from qfluentwidgets import (
    CardWidget, PrimaryPushButton, PushButton, TransparentPushButton,
    ComboBox, Slider, TitleLabel, SubtitleLabel, BodyLabel,
    CaptionLabel, FluentIcon, InfoBar, InfoBarPosition, SwitchButton,
    RoundMenu, Action, MenuAnimationType, IconWidget
)
from qfluentwidgets.components.widgets.menu import ShortcutMenuItemDelegate

from core.app_capture import AppCaptureManager
from .widgets import VUMeterWidget
from core.i18n import tr


class AppSelectButton(QPushButton):
    """
    Windows 11 Fluent DropDown Push Button for application selection.
    Ensures icon is strictly left-aligned at x=14, text is left-aligned, and chevron arrow is on the right.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._app_icon: Any = FluentIcon.SPEAKERS
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            AppSelectButton {
                text-align: left;
                padding-left: 46px;
                padding-right: 34px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.05);
                color: white;
                font-size: 13px;
                font-weight: 500;
            }
            AppSelectButton:hover {
                background-color: rgba(255, 255, 255, 0.09);
                border-color: rgba(255, 255, 255, 0.16);
            }
            AppSelectButton:pressed {
                background-color: rgba(255, 255, 255, 0.04);
            }
        """)

    def setAppIcon(self, icon: Any):
        self._app_icon = icon
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)

        # 1. Left-aligned leading icon (x=14, size=22x22)
        if self._app_icon:
            y = int((self.height() - 22) / 2)
            if isinstance(self._app_icon, FluentIcon):
                self._app_icon.render(painter, QRectF(14, y, 22, 22))
            elif isinstance(self._app_icon, QIcon) and not self._app_icon.isNull():
                pix = self._app_icon.pixmap(22, 22)
                painter.drawPixmap(14, y, pix)

        # 2. Right-aligned dropdown chevron arrow (x=width-24, size=10x10)
        arrow_y = (self.height() - 10) / 2
        rect = QRectF(self.width() - 24, arrow_y, 10, 10)
        FluentIcon.ARROW_DOWN.render(painter, rect)


class AppMenuItemDelegate(ShortcutMenuItemDelegate):
    """
    Renders RoundMenu items with their native icon on the left,
    and a crisp Fluent checkmark indicator on the right when checked.
    """

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if self._isSeparator(index):
            return

        action = index.data(Qt.ItemDataRole.UserRole)
        if isinstance(action, QAction) and action.isChecked():
            painter.save()
            painter.setRenderHints(QPainter.RenderHint.Antialiasing)
            if not (option.state & QStyle.StateFlag.State_MouseOver):
                painter.setOpacity(0.85)

            s = 14
            x = option.rect.right() - 24
            y = option.rect.center().y() - s / 2
            FluentIcon.ACCEPT.render(painter, QRectF(x, y, s, s))
            painter.restore()


class MultiSelectAppMenu(RoundMenu):
    """
    Custom RoundMenu for selecting multiple applications.
    Checkable items do not close the menu when clicked, enabling seamless multi-selection.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.view.setItemDelegate(AppMenuItemDelegate(self.view))
        self.view.setObjectName("multiSelectAppMenu")
        self.view.setMaxVisibleItems(14)

    def _adjustItemText(self, item: QListWidgetItem, action: QAction):
        w = super()._adjustItemText(item, action)
        item.setSizeHint(QSize(w + 36, self.itemHeight))
        return w

    def _onItemClicked(self, item):
        action = item.data(Qt.ItemDataRole.UserRole)
        if action not in self._actions or not action.isEnabled():
            return
        if action.isCheckable():
            action.setChecked(not action.isChecked())
            action.triggered.emit(action.isChecked())
            self.view.viewport().update()
            # Do NOT close menu so user can continue picking applications
            return
        super()._onItemClicked(item)


class FluentAppStreamInterface(QWidget):
    """Windows 11 Fluent Design App Audio Streamer Interface."""

    stream_toggled = pyqtSignal(bool)

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.setObjectName("appStreamInterface")
        self.is_streaming = False

        # Application processes & selection state
        self._audio_apps: List[Dict[str, Any]] = []
        self._selected_pids: Set[int] = set()
        self._is_system_mix: bool = True
        self._icon_cache: Dict[str, QIcon] = {}

        self.menu_apps: Optional[MultiSelectAppMenu] = None

        self._build_ui()
        self._load_target_devices()
        self.refresh_process_list()

        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self._update_app_meter)
        self.meter_timer.start(33)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(18)

        # Header Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = TitleLabel(tr("app_stream_title", "Стрим звука из приложений"), self)
        lbl_sub = CaptionLabel(
            tr("app_stream_subtitle", "Трансляция звука из любого процесса Windows (браузер, Spotify, плеер, игра) прямо в микрофон"),
            self
        )
        lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        layout.addLayout(title_layout)

        # 1. Main Capture Card
        card_capture = CardWidget(self)
        c_layout = QVBoxLayout(card_capture)
        c_layout.setContentsMargins(20, 20, 20, 20)
        c_layout.setSpacing(16)

        c_title = SubtitleLabel(tr("app_stream_card_title", "Захват и трансляция"), card_capture)
        c_layout.addWidget(c_title)

        # Row 1: Refresh Button & App Selection Bar
        top_app_row = QHBoxLayout()
        top_app_row.setSpacing(10)

        lbl_picker = CaptionLabel(tr("app_stream_select_btn_text", "Выберите приложения для трансляции:"), card_capture)
        lbl_picker.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-weight: 600;")
        top_app_row.addWidget(lbl_picker, stretch=1)

        self.btn_refresh = PushButton(FluentIcon.SYNC, tr("app_stream_btn_refresh", "Обновить процессы"), card_capture)
        self.btn_refresh.setFixedHeight(32)
        self.btn_refresh.setToolTip(tr("app_stream_refresh_tooltip", "Обновить список активных аудиосессий Windows"))
        self.btn_refresh.clicked.connect(self.refresh_process_list)
        top_app_row.addWidget(self.btn_refresh)
        c_layout.addLayout(top_app_row)

        # Row 2: DropDown Button for Application Picker
        self.btn_select_apps = AppSelectButton(card_capture)
        self.btn_select_apps.setText(tr("app_stream_all_system_mix", "Все системные звуки (микс ПК)"))
        self.btn_select_apps.setAppIcon(FluentIcon.SPEAKERS)
        self.btn_select_apps.clicked.connect(self._show_apps_menu)
        c_layout.addWidget(self.btn_select_apps)

        # Dynamic Stereo VU Meter
        self.vu_app = VUMeterWidget(label=tr("app_stream_vu_label", "УРОВЕНЬ ЗВУКА ПРИЛОЖЕНИЯ"), parent=card_capture)
        c_layout.addWidget(self.vu_app)

        # Big Main Stream Button
        self.btn_stream = PrimaryPushButton(FluentIcon.PLAY, tr("app_stream_btn_start", "Начать трансляцию в микрофон"), card_capture)
        self.btn_stream.setFixedHeight(44)
        btn_font = self.btn_stream.font()
        btn_font.setPointSize(11)
        btn_font.setBold(True)
        self.btn_stream.setFont(btn_font)
        self.btn_stream.clicked.connect(self._toggle_stream)
        c_layout.addWidget(self.btn_stream)

        # Hotkey badge
        hotkey_str = self.cfg.get("hotkeys", {}).get("app_stream_toggle", "ctrl+f9").upper()
        self.lbl_hotkey = CaptionLabel(tr("app_stream_hotkey_label", hotkey=hotkey_str), card_capture)
        self.lbl_hotkey.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        c_layout.addWidget(self.lbl_hotkey)

        layout.addWidget(card_capture)

        # 2. Audio Routing & Volume Card (2-Column Layout matching Radio tab)
        card_vol = CardWidget(self)
        cv_main_layout = QVBoxLayout(card_vol)
        cv_main_layout.setContentsMargins(20, 20, 20, 20)
        cv_main_layout.setSpacing(16)

        lbl_vol_title = SubtitleLabel(tr("app_stream_vol_title", "Управление звуком и выводом"), card_vol)
        cv_main_layout.addWidget(lbl_vol_title)

        v_layout = QHBoxLayout()
        v_layout.setSpacing(24)

        # --- Column 1: Monitor Channel ("Слышать самому" / Заглушить только у себя) ---
        mon_col = QVBoxLayout()
        mon_col.setSpacing(6)

        mon_header = QHBoxLayout()
        mon_header.setSpacing(8)
        icon_mon = IconWidget(FluentIcon.VOLUME, card_vol)
        icon_mon.setFixedSize(16, 16)
        mon_header.addWidget(icon_mon)
        lbl_mon_head = BodyLabel(tr("app_stream_hear_myself", "Слышать самому"), card_vol)
        lbl_mon_head.setStyleSheet("font-weight: 600; font-size: 13px;")
        mon_header.addWidget(lbl_mon_head)
        mon_header.addStretch()

        self.switch_mon = SwitchButton(card_vol)
        self.switch_mon.setOnText(tr("switch_on", "Вкл"))
        self.switch_mon.setOffText(tr("switch_off", "Выкл"))
        # Default OFF (0% monitor) to prevent duplicate audio echo; mute_self is enabled when OFF
        mon_init_state = bool(self.cfg.get("app_stream_monitor_enabled", False))
        self.switch_mon.setChecked(mon_init_state)
        self.engine.app_capture.mute_self = not mon_init_state
        self.switch_mon.checkedChanged.connect(self._on_mon_switch_changed)
        mon_header.addWidget(self.switch_mon)
        mon_col.addLayout(mon_header)

        lbl_mon_hint = CaptionLabel(
            tr("app_stream_mon_hint", "Воспроизводить захваченный звук в ваших динамиках / наушниках"),
            card_vol
        )
        lbl_mon_hint.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        mon_col.addWidget(lbl_mon_hint)

        init_mon_vol = int(self.cfg.get("app_stream_monitor_vol", 0.0) * 100)
        self.engine.app_stream_monitor_vol = (init_mon_vol / 100.0) if mon_init_state else 0.0
        self.lbl_mon = CaptionLabel(
            tr("app_stream_mon_vol", vol=init_mon_vol) if mon_init_state else tr("app_stream_mon_disabled", "Отключено (заглушено у себя, звук идет только тиммейтам)"),
            card_vol
        )
        mon_col.addWidget(self.lbl_mon)

        self.slider_mon = Slider(Qt.Orientation.Horizontal, card_vol)
        self.slider_mon.setRange(0, 150)
        self.slider_mon.setValue(init_mon_vol)
        self.slider_mon.setEnabled(mon_init_state)
        self.slider_mon.valueChanged.connect(self._on_mon_vol)
        mon_col.addWidget(self.slider_mon)

        mon_col.addStretch()
        v_layout.addLayout(mon_col, stretch=1)

        # --- Column 2: Mic Target Channel ("Транслировать в микрофон") ---
        mic_col = QVBoxLayout()
        mic_col.setSpacing(6)

        mic_header = QHBoxLayout()
        mic_header.setSpacing(8)
        icon_mic = IconWidget(FluentIcon.MICROPHONE, card_vol)
        icon_mic.setFixedSize(16, 16)
        mic_header.addWidget(icon_mic)
        lbl_mic_head = BodyLabel(tr("app_stream_to_mic", "Транслировать в микрофон"), card_vol)
        lbl_mic_head.setStyleSheet("font-weight: 600; font-size: 13px;")
        mic_header.addWidget(lbl_mic_head)
        mic_header.addStretch()

        self.switch_mic = SwitchButton(card_vol)
        self.switch_mic.setOnText(tr("switch_on", "Вкл"))
        self.switch_mic.setOffText(tr("switch_off", "Выкл"))
        mic_init_state = bool(self.cfg.get("app_stream_mic_enabled", True))
        self.switch_mic.setChecked(mic_init_state)
        self.switch_mic.checkedChanged.connect(self._on_mic_switch_changed)
        mic_header.addWidget(self.switch_mic)
        mic_col.addLayout(mic_header)

        lbl_mic_hint = CaptionLabel(
            tr("app_stream_mic_hint", "Направлять в виртуальный кабель (Discord, игры, OBS)"),
            card_vol
        )
        lbl_mic_hint.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        mic_col.addWidget(lbl_mic_hint)

        init_mic_vol = int(self.cfg.get("app_stream_mic_vol", 1.0) * 100)
        self.engine.app_stream_mic_vol = (init_mic_vol / 100.0) if mic_init_state else 0.0
        self.lbl_mic = CaptionLabel(
            tr("app_stream_mic_vol_label", vol=init_mic_vol) if mic_init_state else tr("app_stream_mic_disabled", "Отключено (звук не идет в микрофон)"),
            card_vol
        )
        mic_col.addWidget(self.lbl_mic)

        self.slider_mic = Slider(Qt.Orientation.Horizontal, card_vol)
        self.slider_mic.setRange(0, 150)
        self.slider_mic.setValue(init_mic_vol)
        self.slider_mic.setEnabled(mic_init_state)
        self.slider_mic.valueChanged.connect(self._on_mic_vol)
        mic_col.addWidget(self.slider_mic)

        lbl_target_mic = CaptionLabel(
            tr("app_stream_target_mic_label", "Устройство вывода в микрофон (целевой виртуальный кабель):"),
            card_vol
        )
        lbl_target_mic.setStyleSheet("color: rgba(255, 255, 255, 0.55); margin-top: 4px;")
        mic_col.addWidget(lbl_target_mic)

        self.combo_target_mic = ComboBox(card_vol)
        self.combo_target_mic.setFixedHeight(32)
        self.combo_target_mic.setEnabled(mic_init_state)
        self.combo_target_mic.currentIndexChanged.connect(self._on_target_mic_changed)
        mic_col.addWidget(self.combo_target_mic)

        # Guidance and Tools Row (Windows Mixer and Default Mic setup)
        self.lbl_mic_guide = CaptionLabel(tr("radio_guide_label", "🎮 В игре / Discord выберите микрофон: CABLE Output (VB-Audio)"), card_vol)
        self.lbl_mic_guide.setStyleSheet("color: #38bdf8; font-weight: 500;")
        mic_col.addWidget(self.lbl_mic_guide)

        guide_btns_row = QHBoxLayout()
        guide_btns_row.setSpacing(8)

        self.btn_open_mixer = TransparentPushButton(
            FluentIcon.SETTING,
            tr("app_stream_open_mixer_btn", "⚙️ Микшер Windows"),
            card_vol
        )
        self.btn_open_mixer.setFixedHeight(28)
        self.btn_open_mixer.setToolTip(tr("app_stream_open_mixer_tip", "Открыть микшер громкости Windows"))
        self.btn_open_mixer.clicked.connect(self._open_windows_mixer)
        guide_btns_row.addWidget(self.btn_open_mixer)

        self.btn_set_default_mic = TransparentPushButton(
            FluentIcon.SETTING,
            tr("radio_guide_btn", "Сделать микрофоном по умолчанию"),
            card_vol
        )
        self.btn_set_default_mic.setFixedHeight(28)
        self.btn_set_default_mic.clicked.connect(self._set_default_mic)
        guide_btns_row.addWidget(self.btn_set_default_mic)
        guide_btns_row.addStretch()

        mic_col.addLayout(guide_btns_row)
        v_layout.addLayout(mic_col, stretch=1)

        cv_main_layout.addLayout(v_layout)
        layout.addWidget(card_vol)
        layout.addStretch()

    def _show_apps_menu(self):
        """Builds and displays the MultiSelectAppMenu directly beneath the dropdown button."""
        self.menu_apps = MultiSelectAppMenu(parent=self)

        # 1. System Mix Action
        act_mix = Action(FluentIcon.SPEAKERS, tr("app_stream_all_system_mix", "Все системные звуки (микс ПК)"), self.menu_apps)
        act_mix.setCheckable(True)
        act_mix.setChecked(self._is_system_mix)
        act_mix.triggered.connect(self._on_mix_toggled)
        self.menu_apps.addAction(act_mix)

        self.menu_apps.addSeparator()

        # 2. Quick Select/Clear Actions
        act_all = Action(FluentIcon.COMPLETED, tr("app_stream_select_all", "Выбрать все приложения"), self.menu_apps)
        act_all.triggered.connect(self._on_select_all)
        self.menu_apps.addAction(act_all)

        act_clear = Action(FluentIcon.DELETE, tr("app_stream_clear_all", "Снять выбор (Все звуки)"), self.menu_apps)
        act_clear.triggered.connect(self._on_clear_all)
        self.menu_apps.addAction(act_clear)

        self.menu_apps.addSeparator()

        # 3. Application Items
        for app in self._audio_apps:
            pid = app["pid"]
            ic = app.get("icon")
            if not ic or (isinstance(ic, QIcon) and ic.isNull()):
                ic = FluentIcon.APPLICATION

            label = f"{app['name']} (PID: {pid})"
            act_app = Action(ic, label, self.menu_apps)
            act_app.setCheckable(True)
            act_app.setChecked(pid in self._selected_pids)
            act_app.triggered.connect(lambda chk, p=pid: self._on_app_toggled(p, chk))
            self.menu_apps.addAction(act_app)

        self.menu_apps.addSeparator()

        # 4. Explicit Done / Close action
        act_done = Action(FluentIcon.ACCEPT, tr("app_stream_apply_close", "✓ Готово (закрыть список)"), self.menu_apps)
        self.menu_apps.addAction(act_done)

        # Anchor menu nicely beneath the button
        pos = self.btn_select_apps.mapToGlobal(QPoint(0, self.btn_select_apps.height() + 4))
        self.menu_apps.view.setMinimumWidth(max(self.btn_select_apps.width(), 420))
        self.menu_apps.exec(pos, aniType=MenuAnimationType.DROP_DOWN)

    def _on_mix_toggled(self, checked: bool):
        if checked:
            self._is_system_mix = True
            self._selected_pids.clear()
        else:
            if not self._selected_pids:
                self._is_system_mix = True
        self._update_selection_state()

    def _on_app_toggled(self, pid: int, checked: bool):
        if checked:
            self._selected_pids.add(pid)
            self._is_system_mix = False
        else:
            self._selected_pids.discard(pid)
            if not self._selected_pids:
                self._is_system_mix = True
        self._update_selection_state()

    def _on_select_all(self):
        self._is_system_mix = False
        for app in self._audio_apps:
            self._selected_pids.add(app["pid"])
        self._update_selection_state()
        if self.menu_apps:
            self.menu_apps.view.viewport().update()

    def _on_clear_all(self):
        self._is_system_mix = True
        self._selected_pids.clear()
        self._update_selection_state()
        if self.menu_apps:
            self.menu_apps.view.viewport().update()

    def _update_selection_state(self):
        """Updates the dropdown header button text, icon, and active engine targets."""
        if self._is_system_mix or not self._selected_pids:
            self.btn_select_apps.setAppIcon(FluentIcon.SPEAKERS)
            self.btn_select_apps.setText(tr("app_stream_all_system_mix", "Все системные звуки (микс ПК)"))
            self.engine.app_capture.target_pids = []
            self.engine.app_capture.target_app_names = []
        else:
            selected_apps = [a for a in self._audio_apps if a["pid"] in self._selected_pids]
            count = len(selected_apps)
            if count == 1:
                app = selected_apps[0]
                ic = app.get("icon")
                self.btn_select_apps.setAppIcon(ic if ic else FluentIcon.APPLICATION)
                self.btn_select_apps.setText(f"{app['name']} (PID: {app['pid']})")
                self.engine.app_capture.target_pids = [app["pid"]]
                self.engine.app_capture.target_app_names = [app["name"]]
            elif count == 2:
                ic = selected_apps[0].get("icon")
                self.btn_select_apps.setAppIcon(ic if ic else FluentIcon.APPLICATION)
                self.btn_select_apps.setText(f"{selected_apps[0]['name']}, {selected_apps[1]['name']}")
                self.engine.app_capture.target_pids = [a["pid"] for a in selected_apps]
                self.engine.app_capture.target_app_names = [a["name"] for a in selected_apps]
            else:
                ic = selected_apps[0].get("icon")
                self.btn_select_apps.setAppIcon(ic if ic else FluentIcon.APPLICATION)
                names_preview = f"{selected_apps[0]['name']}, {selected_apps[1]['name']}"
                self.btn_select_apps.setText(
                    tr("app_stream_multi_selected", count=count, names=f"{names_preview} (+{count - 2})")
                )
                self.engine.app_capture.target_pids = [a["pid"] for a in selected_apps]
                self.engine.app_capture.target_app_names = [a["name"] for a in selected_apps]

    def _on_mon_switch_changed(self, checked: bool):
        """Handles 'Слышать самому' toggle (OFF = Mute for self only)."""
        self.cfg.set("app_stream_monitor_enabled", checked)
        self.engine.app_capture.mute_self = not checked
        self.slider_mon.setEnabled(checked)

        if checked:
            vol = self.slider_mon.value()
            self.engine.app_stream_monitor_vol = vol / 100.0
            self.lbl_mon.setText(tr("app_stream_mon_vol", vol=vol))
        else:
            self.engine.app_stream_monitor_vol = 0.0
            self.lbl_mon.setText(tr("app_stream_mon_disabled", "Отключено (заглушено у себя, звук идет только тиммейтам)"))

    def _on_mon_vol(self, val: int):
        self.cfg.set("app_stream_monitor_vol", val / 100.0)
        if self.switch_mon.isChecked():
            self.engine.app_stream_monitor_vol = val / 100.0
            self.lbl_mon.setText(tr("app_stream_mon_vol", vol=val))

    def _on_mic_switch_changed(self, checked: bool):
        """Handles 'Транслировать в микрофон' toggle."""
        self.cfg.set("app_stream_mic_enabled", checked)
        self.slider_mic.setEnabled(checked)
        self.combo_target_mic.setEnabled(checked)

        if checked:
            vol = self.slider_mic.value()
            self.engine.app_stream_mic_vol = vol / 100.0
            self.lbl_mic.setText(tr("app_stream_mic_vol_label", vol=vol))
        else:
            self.engine.app_stream_mic_vol = 0.0
            self.lbl_mic.setText(tr("app_stream_mic_disabled", "Отключено (звук не идет в микрофон)"))

    def _on_mic_vol(self, val: int):
        self.cfg.set("app_stream_mic_vol", val / 100.0)
        if self.switch_mic.isChecked():
            self.engine.app_stream_mic_vol = val / 100.0
            self.lbl_mic.setText(tr("app_stream_mic_vol_label", vol=val))

    def _open_windows_mixer(self):
        """Launches Windows App Volume Mixer settings page."""
        try:
            subprocess.Popen(["powershell", "-Command", "Start-Process ms-settings:apps-volume"])
        except Exception as e:
            print(f"[AppStream] Error launching ms-settings:apps-volume: {e}")

    def refresh_process_list(self):
        """Scans for active sound-producing processes in Windows and extracts their icons."""
        icon_provider = QFileIconProvider()
        cur_pid = os.getpid()
        ignored = {"svchost.exe", "audiodg.exe", "conhost.exe", "dwm.exe", "system", "registry"}

        self._audio_apps = []
        seen_names = set()
        seen_pids = {cur_pid}

        audio_sessions = AppCaptureManager.list_audio_sessions()
        for s in audio_sessions:
            pid = s.get("pid")
            name = s.get("name", "")
            if not name or pid in seen_pids or name.lower() in ignored:
                continue

            if name.lower() in seen_names:
                continue

            seen_pids.add(pid)
            seen_names.add(name.lower())

            exe_path = ""
            try:
                proc = psutil.Process(pid)
                exe_path = proc.exe()
            except Exception:
                pass

            icon = None
            if exe_path in self._icon_cache:
                icon = self._icon_cache[exe_path]
            elif exe_path and os.path.exists(exe_path):
                ic = icon_provider.icon(QFileInfo(exe_path))
                if ic and not ic.isNull():
                    icon = ic
                    self._icon_cache[exe_path] = icon

            if not icon:
                icon = FluentIcon.APPLICATION

            label = f"{name} (PID: {pid})"
            self._audio_apps.append({
                "label": label,
                "name": name,
                "pid": pid,
                "exe": exe_path,
                "icon": icon
            })

        self._update_selection_state()

    def _toggle_stream(self):
        if self.is_streaming:
            self.stop_stream()
        else:
            self.start_stream()

    def start_stream(self):
        """Starts streaming captured application audio into the virtual microphone."""
        self.is_streaming = True
        self.engine.app_stream_enabled = True

        if self._is_system_mix or not self._selected_pids:
            self.engine.app_capture.target_pids = []
            self.engine.app_capture.target_app_names = []
        else:
            selected_apps = [a for a in self._audio_apps if a["pid"] in self._selected_pids]
            self.engine.app_capture.target_pids = [a["pid"] for a in selected_apps]
            self.engine.app_capture.target_app_names = [a["name"] for a in selected_apps]

        self.engine.app_capture.mute_self = not self.switch_mon.isChecked()
        self.engine.app_capture.start_capture()

        self.btn_stream.setText(tr("app_stream_btn_stop", "Остановить трансляцию (В эфире)"))
        self.btn_stream.setIcon(FluentIcon.PAUSE)
        self.stream_toggled.emit(True)

    def stop_stream(self):
        """Stops the audio stream cleanly without crashing."""
        try:
            self.is_streaming = False
            self.engine.app_stream_enabled = False
            self.engine.app_capture.target_pids = []
            self.engine.app_capture.target_app_names = []
            self.engine.app_capture.stop_capture()
            if hasattr(self, "vu_app"):
                self.vu_app.reset()
        except Exception as e:
            print(f"[AppStream] Error stopping stream: {e}")
        finally:
            self.is_streaming = False
            self.btn_stream.setText(tr("app_stream_btn_start", "Начать трансляцию в микрофон"))
            self.btn_stream.setIcon(FluentIcon.PLAY)
            self.stream_toggled.emit(False)

    def _update_app_meter(self):
        if hasattr(self, "vu_app"):
            peak = getattr(self.engine, "app_stream_peak", 0.0)
            self.vu_app.set_levels(peak)

    def _load_target_devices(self):
        """Loads available audio output devices for target microphone into combo box."""
        saved_target = self.cfg.get("mic_target_device_id")
        self.engine.populate_target_mic_combobox(self.combo_target_mic, saved_target)

    def _set_default_mic(self):
        from core.driver_manager import DriverManager
        ok = DriverManager.set_default_recording_device_to_cable()
        if ok:
            InfoBar.success(
                title=tr("mic_default_success_title"),
                content=tr("mic_default_success_msg"),
                position=InfoBarPosition.TOP,
                parent=self,
                duration=4000
            )
        else:
            InfoBar.info(
                title=tr("mic_default_manual_title"),
                content=tr("mic_default_manual_msg"),
                position=InfoBarPosition.TOP,
                parent=self,
                duration=4500
            )

    def _on_target_mic_changed(self, index: int):
        dev_id = self.combo_target_mic.itemData(index)
        QTimer.singleShot(20, lambda: self._apply_target_mic(dev_id))

    def _apply_target_mic(self, dev_id: Optional[int]):
        main_win = self.window()
        if hasattr(main_win, "set_global_target_microphone"):
            main_win.set_global_target_microphone(dev_id, source_tab=self)
        else:
            self.cfg.set("mic_target_device_id", dev_id)
            self.engine.set_mic_target_device(dev_id)

    def sync_target_mic(self, dev_id: Optional[int]):
        """Synchronizes combo box selection from external changes."""
        self.combo_target_mic.blockSignals(True)
        found = False
        for i in range(self.combo_target_mic.count()):
            if self.combo_target_mic.itemData(i) == dev_id:
                self.combo_target_mic.setCurrentIndex(i)
                found = True
                break
        if not found and dev_id is None:
            self.combo_target_mic.setCurrentIndex(0)
        self.combo_target_mic.blockSignals(False)

