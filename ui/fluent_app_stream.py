"""
Fluent Design Application Audio Stream Interface for SoundFlow Studio.
Enables real-time pass-through audio capture from running processes into microphone.
"""

import os
import psutil
from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal, QFileInfo, QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QFileIconProvider
from qfluentwidgets import (
    CardWidget, HeaderCardWidget, PrimaryPushButton, PushButton, TransparentPushButton,
    ComboBox, Slider, SearchLineEdit, TitleLabel, SubtitleLabel, BodyLabel,
    CaptionLabel, FluentIcon, InfoBar, InfoBarPosition
)

from core.app_capture import AppCaptureManager
from .widgets import VUMeterWidget
from core.i18n import tr


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

        # Row 1: Search Box & Refresh Button
        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        self.search_app = SearchLineEdit(card_capture)
        self.search_app.setPlaceholderText(tr("app_stream_search_placeholder", "Поиск приложения по имени..."))
        self.search_app.setFixedHeight(34)
        self.search_app.textChanged.connect(self._filter_apps_by_search)
        search_row.addWidget(self.search_app, stretch=1)

        self.btn_refresh = PushButton(FluentIcon.SYNC, tr("app_stream_btn_refresh", "Обновить процессы"), card_capture)
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.setToolTip(tr("app_stream_refresh_tooltip", "Обновить список активных аудиосессий Windows"))
        self.btn_refresh.clicked.connect(self.refresh_process_list)
        search_row.addWidget(self.btn_refresh)
        c_layout.addLayout(search_row)

        # Row 2: Applications Dropdown (shows only audio-producing apps by default)
        self.combo_apps = ComboBox(card_capture)
        self.combo_apps.setFixedHeight(36)
        c_layout.addWidget(self.combo_apps)

        # Row 3: Target Microphone Selection (where system sound is streamed)
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

        # Big Main Stream Button (use setFont to preserve Fluent QSS icon and layout)
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

        # Monitor Volume (Local / For Self)
        mon_row = QHBoxLayout()
        self.lbl_mon = BodyLabel(f"{tr('app_stream_vol_monitor', 'Слышать самому:')} 80%", card_vol)
        self.lbl_mon.setFixedWidth(240)
        self.slider_mon = Slider(Qt.Orientation.Horizontal, card_vol)
        self.slider_mon.setRange(0, 150)
        self.slider_mon.setValue(80)
        self.slider_mon.valueChanged.connect(self._on_mon_vol)
        mon_row.addWidget(self.lbl_mon)
        mon_row.addWidget(self.slider_mon)
        v_layout.addLayout(mon_row)

        # Mic Target Volume (Discord / Teammates)
        mic_vol_row = QHBoxLayout()
        self.lbl_mic = BodyLabel(f"{tr('app_stream_vol_mic', 'В микрофон (тиммейтам):')} 100%", card_vol)
        self.lbl_mic.setFixedWidth(240)
        self.slider_mic = Slider(Qt.Orientation.Horizontal, card_vol)
        self.slider_mic.setRange(0, 150)
        self.slider_mic.setValue(100)
        self.slider_mic.valueChanged.connect(self._on_mic_vol)
        mic_vol_row.addWidget(self.lbl_mic)
        mic_vol_row.addWidget(self.slider_mic)
        v_layout.addLayout(mic_vol_row)

        layout.addWidget(card_vol)
        layout.addStretch()

    def refresh_process_list(self):
        """Scans for active sound-producing processes in Windows and caches their icons."""
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

            stem = os.path.splitext(name)[0]
            label = f"{name} (PID: {pid})"
            self._audio_apps.append({
                "label": label,
                "name": name,
                "pid": pid,
                "exe": exe_path,
                "icon": icon
            })

        query = self.search_app.text().strip() if hasattr(self, "search_app") else ""
        self._populate_combobox(query)

    def _populate_combobox(self, query: str = ""):
        self.combo_apps.clear()

        # 1. System Mix
        sys_mix_name = tr("app_stream_all_system_mix", "Все системные звуки (микс ПК)")
        self.combo_apps.addItem(
            sys_mix_name,
            icon=FluentIcon.SPEAKERS,
            userData={"pid": None, "name": sys_mix_name, "exe": ""}
        )

        q = query.lower()
        matched = []
        for app in self._audio_apps:
            if not q or q in app["name"].lower() or q in app["label"].lower():
                matched.append(app)

        for app in matched:
            self.combo_apps.addItem(
                app["label"],
                icon=app["icon"],
                userData={"pid": app["pid"], "name": app["name"], "exe": app["exe"]}
            )

        # If user searched for something specific and no audio sessions matched, search running desktop apps
        if q and len(matched) == 0:
            icon_provider = QFileIconProvider()
            seen_extra = set()
            for p in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    p_name = p.info["name"]
                    if not p_name or p_name.lower() in seen_extra:
                        continue
                    if q in p_name.lower():
                        seen_extra.add(p_name.lower())
                        exe = p.info["exe"]
                        ic = None
                        if exe and os.path.exists(exe):
                            ic = icon_provider.icon(QFileInfo(exe))
                        self.combo_apps.addItem(
                            f"{p_name} (PID: {p.info['pid']})",
                            icon=ic or FluentIcon.APPLICATION,
                            userData={"pid": p.info["pid"], "name": p_name, "exe": exe}
                        )
                        if len(seen_extra) >= 10:
                            break
                except Exception:
                    pass

    def _filter_apps_by_search(self, text: str):
        self._populate_combobox(text.strip())

    def _toggle_stream(self):
        if self.is_streaming:
            self.stop_stream()
        else:
            self.start_stream()

    def start_stream(self):
        self.is_streaming = True
        self.engine.app_stream_enabled = True

        data = self.combo_apps.currentData()
        if isinstance(data, dict):
            self.engine.app_capture.target_pid = data.get("pid")
            self.engine.app_capture.target_app_name = data.get("name")

        self.engine.app_capture.start_capture()
        self.btn_stream.setText(tr("app_stream_btn_stop", "Остановить трансляцию в микрофон (В эфире)"))
        self.btn_stream.setIcon(FluentIcon.PAUSE)
        self.stream_toggled.emit(True)

    def stop_stream(self):
        self.is_streaming = False
        self.engine.app_stream_enabled = False
        self.engine.app_capture.target_pid = None
        self.engine.app_capture.stop_capture()
        if hasattr(self, "vu_app"):
            self.vu_app.reset()
        self.btn_stream.setText(tr("app_stream_btn_start", "Начать трансляцию в микрофон"))
        self.btn_stream.setIcon(FluentIcon.PLAY)
        self.stream_toggled.emit(False)

    def _update_app_meter(self):
        if hasattr(self, "vu_app"):
            peak = getattr(self.engine, "app_stream_peak", 0.0)
            self.vu_app.set_levels(peak)

    def _on_mon_vol(self, val: int):
        self.lbl_mon.setText(f"{tr('app_stream_vol_monitor', 'Слышать самому:')} {val}%")
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
        # Safely decouple via singleShot so ComboBoxMenu popup can close cleanly
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
