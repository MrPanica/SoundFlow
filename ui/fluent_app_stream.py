"""
Fluent Design Application Audio Stream Interface for SoundFlow Studio.
Enables real-time pass-through audio capture from running processes into microphone.
"""

import os
import subprocess
import psutil
from typing import Optional, List, Dict, Any, Set
from PyQt6.QtCore import Qt, pyqtSignal, QFileInfo, QTimer, QSize
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QFileIconProvider
)
from qfluentwidgets import (
    CardWidget, HeaderCardWidget, PrimaryPushButton, PushButton, TransparentPushButton,
    ComboBox, Slider, SearchLineEdit, TitleLabel, SubtitleLabel, BodyLabel,
    CaptionLabel, FluentIcon, InfoBar, InfoBarPosition, SwitchButton,
    SmoothScrollArea, CheckBox, Flyout, FlyoutViewBase, FlyoutAnimationType
)

from core.app_capture import AppCaptureManager
from .widgets import VUMeterWidget
from core.i18n import tr


class MultiAppItemWidget(QWidget):
    """Row item in the application picker representing a single audio process."""
    toggled = pyqtSignal(int, bool)

    def __init__(self, pid: Optional[int], name: str, icon: Any, checked: bool = False, parent=None):
        super().__init__(parent)
        self.pid = pid
        self.name = name
        self.icon = icon

        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            MultiAppItemWidget {
                border-radius: 6px;
                background-color: transparent;
            }
            MultiAppItemWidget:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        self.checkbox = CheckBox(self)
        self.checkbox.setChecked(checked)
        self.checkbox.stateChanged.connect(self._on_check_state_changed)
        layout.addWidget(self.checkbox)

        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(22, 22)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if isinstance(icon, QIcon) and not icon.isNull():
            self.icon_lbl.setPixmap(icon.pixmap(22, 22))
        elif isinstance(icon, FluentIcon):
            self.icon_lbl.setPixmap(icon.icon().pixmap(22, 22))
        layout.addWidget(self.icon_lbl)

        self.name_lbl = BodyLabel(name, self)
        self.name_lbl.setStyleSheet("font-weight: 500;")
        layout.addWidget(self.name_lbl, stretch=1)

        if pid is not None:
            self.pid_lbl = CaptionLabel(f"PID: {pid}", self)
            self.pid_lbl.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
            layout.addWidget(self.pid_lbl)

    def _on_check_state_changed(self, state):
        self.toggled.emit(self.pid if self.pid is not None else -1, self.checkbox.isChecked())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)

    def set_checked(self, checked: bool):
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(False)


class MultiAppSelectorView(FlyoutViewBase):
    """Interactive Flyout Panel for multi-selecting audio-producing applications."""
    selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(420)
        self.setFixedHeight(380)

        self._all_apps: List[Dict[str, Any]] = []
        self._selected_pids: Set[int] = set()
        self._system_mix_selected: bool = True
        self._items_map: Dict[int, MultiAppItemWidget] = {}

        v_layout = QVBoxLayout(self)
        v_layout.setContentsMargins(14, 14, 14, 14)
        v_layout.setSpacing(10)

        # 1. Search Box
        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText(tr("app_stream_search_placeholder", "Поиск приложения по имени..."))
        self.search_box.setFixedHeight(32)
        self.search_box.textChanged.connect(self._filter_list)
        v_layout.addWidget(self.search_box)

        # 2. Quick Action Buttons
        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self.btn_select_all = TransparentPushButton(
            FluentIcon.COMPLETED,
            tr("app_stream_select_all", "Выбрать все"),
            self
        )
        self.btn_select_all.setFixedHeight(28)
        self.btn_select_all.clicked.connect(self._select_all_apps)

        self.btn_clear_all = TransparentPushButton(
            FluentIcon.DELETE,
            tr("app_stream_clear_all", "Снять выбор"),
            self
        )
        self.btn_clear_all.setFixedHeight(28)
        self.btn_clear_all.clicked.connect(self._clear_all_apps)

        actions_row.addWidget(self.btn_select_all)
        actions_row.addWidget(self.btn_clear_all)
        actions_row.addStretch()
        v_layout.addLayout(actions_row)

        # 3. System Mix (all PC audio) Option
        sys_mix_name = tr("app_stream_all_system_mix", "Все системные звуки (микс ПК)")
        self.item_sys_mix = MultiAppItemWidget(
            pid=None,
            name=sys_mix_name,
            icon=FluentIcon.SPEAKERS,
            checked=True,
            parent=self
        )
        self.item_sys_mix.toggled.connect(self._on_sys_mix_toggled)
        v_layout.addWidget(self.item_sys_mix)

        # Separator line
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255, 255, 255, 0.12);")
        v_layout.addWidget(sep)

        # 4. Scrollable Container for Apps
        self.scroll_area = SmoothScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")

        self.scroll_widget = QWidget(self.scroll_area)
        self.scroll_widget.setStyleSheet("background-color: transparent;")
        self.apps_layout = QVBoxLayout(self.scroll_widget)
        self.apps_layout.setContentsMargins(0, 0, 0, 0)
        self.apps_layout.setSpacing(4)
        self.apps_layout.addStretch()

        self.scroll_area.setWidget(self.scroll_widget)
        v_layout.addWidget(self.scroll_area, stretch=1)

    def set_apps(self, apps: List[Dict[str, Any]]):
        """Populates the list with detected applications."""
        self._all_apps = apps

        # Clear existing items in scroll layout
        for i in reversed(range(self.apps_layout.count() - 1)):
            item = self.apps_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()

        self._items_map.clear()

        for app in self._all_apps:
            pid = app["pid"]
            checked = pid in self._selected_pids
            w = MultiAppItemWidget(
                pid=pid,
                name=app["name"],
                icon=app["icon"],
                checked=checked,
                parent=self.scroll_widget
            )
            w.toggled.connect(self._on_app_item_toggled)
            self._items_map[pid] = w
            self.apps_layout.insertWidget(self.apps_layout.count() - 1, w)

        self._filter_list(self.search_box.text())

    def _filter_list(self, query: str):
        q = query.strip().lower()
        for pid, widget in self._items_map.items():
            if not q:
                widget.setVisible(True)
            else:
                visible = (q in widget.name.lower()) or (q in str(pid))
                widget.setVisible(visible)

    def _on_sys_mix_toggled(self, pid_val: int, checked: bool):
        self._system_mix_selected = checked
        if checked:
            # Deselect individual apps when system mix is checked
            self._selected_pids.clear()
            for w in self._items_map.values():
                w.set_checked(False)
        self.selection_changed.emit()

    def _on_app_item_toggled(self, pid: int, checked: bool):
        if pid < 0:
            return

        if checked:
            self._selected_pids.add(pid)
            self._system_mix_selected = False
            self.item_sys_mix.set_checked(False)
        else:
            self._selected_pids.discard(pid)
            if not self._selected_pids:
                self._system_mix_selected = True
                self.item_sys_mix.set_checked(True)

        self.selection_changed.emit()

    def _select_all_apps(self):
        self._system_mix_selected = False
        self.item_sys_mix.set_checked(False)
        for pid, w in self._items_map.items():
            if w.isVisible():
                self._selected_pids.add(pid)
                w.set_checked(True)
        self.selection_changed.emit()

    def _clear_all_apps(self):
        self._selected_pids.clear()
        self._system_mix_selected = True
        self.item_sys_mix.set_checked(True)
        for w in self._items_map.values():
            w.set_checked(False)
        self.selection_changed.emit()

    def get_selected_apps(self) -> List[Dict[str, Any]]:
        """Returns list of selected apps, or empty list if system mix is active."""
        if self._system_mix_selected or not self._selected_pids:
            return []
        return [app for app in self._all_apps if app["pid"] in self._selected_pids]

    def is_system_mix(self) -> bool:
        return self._system_mix_selected or not self._selected_pids


class FluentAppStreamInterface(QWidget):
    """Windows 11 Fluent Design App Audio Streamer Interface."""

    stream_toggled = pyqtSignal(bool)

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.setObjectName("appStreamInterface")
        self.is_streaming = False

        # Cache of audio-producing processes and Windows icons
        self._audio_apps = []
        self._icon_cache = {}
        self._current_flyout: Optional[Flyout] = None

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

        # Row 2: Multi-App Dropdown Button with REAL-TIME ICON in Header
        self.selector_view = MultiAppSelectorView()
        self.selector_view.selection_changed.connect(self._on_app_selection_changed)

        self.btn_select_apps = PushButton(FluentIcon.SPEAKERS, tr("app_stream_all_system_mix", "Все системные звуки (микс ПК)"), card_capture)
        self.btn_select_apps.setFixedHeight(40)
        self.btn_select_apps.setIconSize(QSize(22, 22))
        self.btn_select_apps.setStyleSheet("""
            PushButton {
                text-align: left;
                padding-left: 12px;
                padding-right: 12px;
                font-weight: 500;
                font-size: 13px;
            }
        """)
        self.btn_select_apps.clicked.connect(self._toggle_app_flyout)
        c_layout.addWidget(self.btn_select_apps)

        # Row 3: "Mute for self only" (Заглушить только у себя) Switch & Windows Mixer Launcher
        mute_card = QFrame(card_capture)
        mute_card.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
            }
        """)
        mute_layout = QVBoxLayout(mute_card)
        mute_layout.setContentsMargins(14, 12, 14, 12)
        mute_layout.setSpacing(8)

        mute_top_row = QHBoxLayout()
        mute_top_row.setSpacing(10)
        self.lbl_mute_title = BodyLabel(
            tr("app_stream_mute_self_label", "🔇 Заглушить только у себя (трансляция без звука в наушниках)"),
            mute_card
        )
        self.lbl_mute_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.switch_mute_self = SwitchButton(mute_card)
        self.switch_mute_self.checkedChanged.connect(self._on_mute_self_toggled)

        mute_top_row.addWidget(self.lbl_mute_title, stretch=1)
        mute_top_row.addWidget(self.switch_mute_self)
        mute_layout.addLayout(mute_top_row)

        self.lbl_mute_desc = CaptionLabel(
            tr("app_stream_mute_self_desc", "Звук выбранных приложений пойдет напрямую в микрофон тиммейтам, а в ваших наушниках будет полная тишина."),
            mute_card
        )
        self.lbl_mute_desc.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        mute_layout.addWidget(self.lbl_mute_desc)

        # Windows Mixer Button
        self.btn_open_mixer = TransparentPushButton(
            FluentIcon.SETTING,
            tr("app_stream_open_mixer_btn", "⚙️ Открыть микшер Windows (направить вывод на CABLE Input)"),
            mute_card
        )
        self.btn_open_mixer.setFixedHeight(28)
        self.btn_open_mixer.setToolTip(tr("app_stream_open_mixer_tip", "В открывшемся окне Windows выберите CABLE Input в качестве устройства вывода для выбранных приложений."))
        self.btn_open_mixer.clicked.connect(self._open_windows_mixer)
        mute_layout.addWidget(self.btn_open_mixer)

        c_layout.addWidget(mute_card)

        # Row 4: Target Microphone Selection (where system sound is streamed)
        mic_row = QVBoxLayout()
        mic_row.setSpacing(6)
        lbl_target_mic = CaptionLabel(
            tr("app_stream_target_mic_label", "Куда транслировать системный звук (микрофон / виртуальный кабель):"),
            card_capture
        )
        lbl_target_mic.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-weight: 600;")
        self.combo_target_mic = ComboBox(card_capture)
        self.combo_target_mic.setFixedHeight(34)
        self.combo_target_mic.currentIndexChanged.connect(self._on_target_mic_changed)
        mic_row.addWidget(lbl_target_mic)
        mic_row.addWidget(self.combo_target_mic)

        # Guidance banner and 1-click button for games / Discord
        guide_row = QHBoxLayout()
        guide_row.setSpacing(8)
        self.lbl_mic_guide = CaptionLabel(tr("radio_guide_label", "🎮 В игре / Discord выберите микрофон: CABLE Output (VB-Audio)"), card_capture)
        self.lbl_mic_guide.setStyleSheet("color: #38bdf8; font-weight: 500;")
        self.btn_set_default_mic = TransparentPushButton(FluentIcon.SETTING, tr("radio_guide_btn", "Сделать микрофоном по умолчанию"), card_capture)
        self.btn_set_default_mic.setFixedHeight(28)
        self.btn_set_default_mic.clicked.connect(self._set_default_mic)
        guide_row.addWidget(self.lbl_mic_guide, stretch=1)
        guide_row.addWidget(self.btn_set_default_mic)
        mic_row.addLayout(guide_row)

        c_layout.addLayout(mic_row)

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

        # 2. Volume Sliders Card
        card_vol = CardWidget(self)
        v_layout = QVBoxLayout(card_vol)
        v_layout.setContentsMargins(20, 20, 20, 20)
        v_layout.setSpacing(16)

        v_title = SubtitleLabel(tr("app_stream_vol_title", "Громкость трансляции приложения"), card_vol)
        v_layout.addWidget(v_title)

        # Monitor Volume (Headphones / For Self) — Default 0% to prevent echo
        mon_row = QHBoxLayout()
        self.lbl_mon = BodyLabel(f"{tr('app_stream_vol_monitor_tip', 'Слышать в наушниках (0% = без эха):')} 0%", card_vol)
        self.lbl_mon.setFixedWidth(360)
        self.slider_mon = Slider(Qt.Orientation.Horizontal, card_vol)
        self.slider_mon.setRange(0, 150)
        self.slider_mon.setValue(0)
        self.slider_mon.valueChanged.connect(self._on_mon_vol)
        mon_row.addWidget(self.lbl_mon)
        mon_row.addWidget(self.slider_mon)
        v_layout.addLayout(mon_row)

        # Mic Target Volume (Discord / Teammates)
        mic_vol_row = QHBoxLayout()
        self.lbl_mic = BodyLabel(f"{tr('app_stream_vol_mic', 'В микрофон (тиммейтам):')} 100%", card_vol)
        self.lbl_mic.setFixedWidth(360)
        self.slider_mic = Slider(Qt.Orientation.Horizontal, card_vol)
        self.slider_mic.setRange(0, 150)
        self.slider_mic.setValue(100)
        self.slider_mic.valueChanged.connect(self._on_mic_vol)
        mic_vol_row.addWidget(self.lbl_mic)
        mic_vol_row.addWidget(self.slider_mic)
        v_layout.addLayout(mic_vol_row)

        layout.addWidget(card_vol)
        layout.addStretch()

    def _toggle_app_flyout(self):
        """Toggles the multi-app selector popup flyout anchored to the button."""
        if self._current_flyout and self._current_flyout.isVisible():
            self._current_flyout.fadeOut()
            self._current_flyout = None
            return

        self._current_flyout = Flyout.make(
            view=self.selector_view,
            target=self.btn_select_apps,
            parent=self,
            aniType=FlyoutAnimationType.PULL_UP,
            isClosable=False
        )

    def _on_app_selection_changed(self):
        """Updates the dropdown header button text and icon based on selected apps."""
        if self.selector_view.is_system_mix():
            self.btn_select_apps.setIcon(FluentIcon.SPEAKERS)
            self.btn_select_apps.setText(tr("app_stream_all_system_mix", "Все системные звуки (микс ПК)"))
        else:
            selected = self.selector_view.get_selected_apps()
            count = len(selected)
            if count == 1:
                app = selected[0]
                ic = app.get("icon")
                if isinstance(ic, QIcon) and not ic.isNull():
                    self.btn_select_apps.setIcon(ic)
                elif isinstance(ic, FluentIcon):
                    self.btn_select_apps.setIcon(ic)
                else:
                    self.btn_select_apps.setIcon(FluentIcon.APPLICATION)
                self.btn_select_apps.setText(f"{app['name']} (PID: {app['pid']})")
            elif count == 2:
                ic = selected[0].get("icon")
                if isinstance(ic, QIcon) and not ic.isNull():
                    self.btn_select_apps.setIcon(ic)
                else:
                    self.btn_select_apps.setIcon(FluentIcon.APPLICATION)
                self.btn_select_apps.setText(f"{selected[0]['name']}, {selected[1]['name']}")
            elif count > 2:
                ic = selected[0].get("icon")
                if isinstance(ic, QIcon) and not ic.isNull():
                    self.btn_select_apps.setIcon(ic)
                else:
                    self.btn_select_apps.setIcon(FluentIcon.APPLICATION)
                names_preview = f"{selected[0]['name']}, {selected[1]['name']}"
                self.btn_select_apps.setText(
                    tr("app_stream_multi_selected", count=count, names=f"{names_preview} (+{count - 2} еще)")
                )

    def _on_mute_self_toggled(self, checked: bool):
        """Handles 'Mute for self only' switch toggle."""
        self.engine.app_capture.mute_self = checked
        if checked:
            # Silence local headphones monitor to avoid any sound locally
            self.slider_mon.setValue(0)
            InfoBar.info(
                title=tr("app_stream_mute_self_label"),
                content=tr("app_stream_open_mixer_tip"),
                position=InfoBarPosition.TOP,
                parent=self,
                duration=5000
            )

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

            # Deduplicate by process name
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

        self.selector_view.set_apps(self._audio_apps)
        self._on_app_selection_changed()

    def _toggle_stream(self):
        if self.is_streaming:
            self.stop_stream()
        else:
            self.start_stream()

    def start_stream(self):
        """Starts streaming captured application audio into the virtual microphone."""
        self.is_streaming = True
        self.engine.app_stream_enabled = True

        selected = self.selector_view.get_selected_apps()
        if selected:
            self.engine.app_capture.target_pids = [a["pid"] for a in selected if a["pid"] is not None]
            self.engine.app_capture.target_app_names = [a["name"] for a in selected]
        else:
            self.engine.app_capture.target_pids = []
            self.engine.app_capture.target_app_names = []

        self.engine.app_capture.mute_self = self.switch_mute_self.isChecked()
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

    def _on_mon_vol(self, val: int):
        self.lbl_mon.setText(f"{tr('app_stream_vol_monitor_tip', 'Слышать в наушниках (0% = без эха):')} {val}%")
        self.engine.app_stream_monitor_vol = val / 100.0

    def _on_mic_vol(self, val: int):
        self.lbl_mic.setText(f"{tr('app_stream_vol_mic', 'В микрофон (тиммейтам):')} {val}%")
        self.engine.app_stream_mic_vol = val / 100.0

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
