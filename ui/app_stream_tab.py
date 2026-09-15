"""
Application Audio Streamer Tab for SoundFlow Studio.
Enables real-time pass-through streaming of any Windows application or game audio directly into the microphone.
"""

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QRadioButton, QButtonGroup, QFrame,
    QGroupBox, QMessageBox
)

from core.app_capture import AppCaptureManager
from ui.widgets import VUMeterWidget


class AppStreamTab(QWidget):
    """Tab for selecting a running Windows app and routing its audio live into the microphone."""

    stream_toggled = pyqtSignal(bool)  # is_active
    monitor_volume_changed = pyqtSignal(float)
    mic_volume_changed = pyqtSignal(float)

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.is_streaming = False

        self._build_ui()
        self.refresh_process_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        # Header Info Card
        header_card = QFrame()
        header_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e1b4b, stop:1 #0f172a);
                border: 1px solid #4338ca;
                border-radius: 12px;
                padding: 14px;
            }
        """)
        h_layout = QVBoxLayout(header_card)
        h_title = QLabel("🔀 Прямой стрим звука из приложения в микрофон")
        h_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #a5b4fc;")
        h_desc = QLabel(
            "Транслируйте музыку из браузера, плеера, YouTube или звуки игры напрямую тиммейтам в Discord / CS2 / Telegram.\n"
            "Звук захватывается через высокоскоростной WASAPI Loopback с задержкой менее 20 миллисекунд."
        )
        h_desc.setWordWrap(True)
        h_desc.setStyleSheet("color: #c7d2fe; font-size: 12px; margin-top: 4px;")
        h_layout.addWidget(h_title)
        h_layout.addWidget(h_desc)
        layout.addWidget(header_card)

        # 1. Process Selection Box
        proc_group = QGroupBox("1. ВЫБОР ПРИЛОЖЕНИЯ ДЛЯ ЗАХВАТА")
        p_layout = QVBoxLayout(proc_group)
        p_layout.setSpacing(10)

        sel_row = QHBoxLayout()
        self.combo_apps = QComboBox()
        self.combo_apps.setStyleSheet("font-size: 13px; font-weight: 600; min-height: 32px;")
        sel_row.addWidget(self.combo_apps, stretch=1)

        self.btn_refresh = QPushButton("🔄 Обновить список")
        self.btn_refresh.clicked.connect(self.refresh_process_list)
        sel_row.addWidget(self.btn_refresh)
        p_layout.addLayout(sel_row)

        lbl_hint = QLabel("💡 Приложение должно воспроизводить или недавно воспроизводить звук, чтобы появиться в списке.")
        lbl_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        p_layout.addWidget(lbl_hint)
        layout.addWidget(proc_group)

        # 2. Main Live Stream Toggle Button
        stream_card = QFrame()
        stream_card.setStyleSheet("""
            QFrame {
                background: #131d31;
                border: 1px solid #1e293b;
                border-radius: 12px;
                padding: 16px;
            }
        """)
        s_layout = QVBoxLayout(stream_card)
        s_layout.setSpacing(12)

        self.btn_stream_toggle = QPushButton("🔴 НАЧАТЬ ТРАНСЛЯЦИЮ В МИКРОФОН")
        self.btn_stream_toggle.setFixedHeight(54)
        self.btn_stream_toggle.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #00f2fe);
                color: #0b0f19;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:1 #38bdf8);
            }
        """)
        self.btn_stream_toggle.clicked.connect(self._toggle_stream)
        s_layout.addWidget(self.btn_stream_toggle)

        # Hotkey indicator
        hotkey_row = QHBoxLayout()
        hotkey_str = self.cfg.get("hotkeys", {}).get("app_stream_toggle", "ctrl+f9").upper()
        self.lbl_hotkey = QLabel(f"Глобальный хоткей: [ {hotkey_str} ] — работает в играх в фоне")
        self.lbl_hotkey.setStyleSheet("color: #a855f7; font-weight: 600; font-size: 12px;")
        hotkey_row.addWidget(self.lbl_hotkey)
        hotkey_row.addStretch()

        s_layout.addLayout(hotkey_row)
        layout.addWidget(stream_card)

        # 3. Volume and Mixing Controls
        vol_group = QGroupBox("2. РАЗДЕЛЬНЫЕ УРОВНИ ГРОМКОСТИ")
        v_layout = QVBoxLayout(vol_group)
        v_layout.setSpacing(12)

        # Monitor Volume (Headphones)
        mon_row = QHBoxLayout()
        self.lbl_mon_vol = QLabel("Громкость в твоих наушниках: 80%")
        self.lbl_mon_vol.setFixedWidth(240)
        self.slider_mon_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_mon_vol.setRange(0, 150)
        self.slider_mon_vol.setValue(80)
        self.slider_mon_vol.valueChanged.connect(self._on_mon_vol_change)
        mon_row.addWidget(self.lbl_mon_vol)
        mon_row.addWidget(self.slider_mon_vol)
        v_layout.addLayout(mon_row)

        # Mic Volume (Discord / Teammates)
        mic_row = QHBoxLayout()
        self.lbl_mic_vol = QLabel("Громкость в микрофон (тиммейтам): 100%")
        self.lbl_mic_vol.setFixedWidth(240)
        self.slider_mic_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_mic_vol.setRange(0, 150)
        self.slider_mic_vol.setValue(100)
        self.slider_mic_vol.valueChanged.connect(self._on_mic_vol_change)
        mic_row.addWidget(self.lbl_mic_vol)
        mic_row.addWidget(self.slider_mic_vol)
        v_layout.addLayout(mic_row)

        layout.addWidget(vol_group)
        layout.addStretch()

    def refresh_process_list(self):
        """Scans and reloads active audio processes."""
        self.combo_apps.clear()
        self.combo_apps.addItem("🔊 Все системные звуки (Полный микс ПК)", "all")

        sessions = AppCaptureManager.list_audio_sessions()
        for sess in sessions:
            name = sess["name"]
            pid = sess["pid"]
            label = f"{name} (PID: {pid})"
            self.combo_apps.addItem(label, pid)

    def _toggle_stream(self):
        if self.is_streaming:
            self.stop_stream()
        else:
            self.start_stream()

    def start_stream(self):
        self.is_streaming = True
        self.engine.app_stream_enabled = True
        self.engine.app_capture.start_capture()

        self.btn_stream_toggle.setText("🟢 В ЭФИРЕ: ЗВУК ИЗ ПРИЛОЖЕНИЯ ТРАНСЛИРУЕТСЯ В МИКРОФОН (ОСТАНОВИТЬ)")
        self.btn_stream_toggle.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #059669);
                color: #ffffff;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #047857;
            }
        """)
        self.stream_toggled.emit(True)

    def stop_stream(self):
        self.is_streaming = False
        self.engine.app_stream_enabled = False
        self.engine.app_capture.stop_capture()

        self.btn_stream_toggle.setText("🔴 НАЧАТЬ ТРАНСЛЯЦИЮ В МИКРОФОН")
        self.btn_stream_toggle.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #00f2fe);
                color: #0b0f19;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0ea5e9, stop:1 #38bdf8);
            }
        """)
        self.stream_toggled.emit(False)

    def _on_mon_vol_change(self, val: int):
        self.lbl_mon_vol.setText(f"Громкость в твоих наушниках: {val}%")
        factor = val / 100.0
        self.engine.app_stream_monitor_vol = factor
        self.monitor_volume_changed.emit(factor)

    def _on_mic_vol_change(self, val: int):
        self.lbl_mic_vol.setText(f"Громкость в микрофон (тиммейтам): {val}%")
        factor = val / 100.0
        self.engine.app_stream_mic_vol = factor
        self.mic_volume_changed.emit(factor)
