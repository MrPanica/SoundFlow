"""
Settings and Audio Device Configuration Dialog for SoundFlow Studio.
Allows selecting physical microphone, monitor headphones, virtual cable target, and latency.
"""

from typing import Optional, Dict, Any, List
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QGroupBox, QFrame, QMessageBox
)

from core.audio_engine import AudioEngine


class SettingsDialog(QDialog):
    """Configuration dialog for audio devices and preferences."""

    def __init__(self, audio_engine: AudioEngine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.setWindowTitle("Настройки SoundFlow Studio")
        self.setFixedSize(540, 620)

        self._build_ui()
        self._load_devices()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Device Configuration Group
        dev_group = QGroupBox("МАРШРУТИЗАЦИЯ АУДИОУСТРОЙСТВ")
        d_layout = QVBoxLayout(dev_group)
        d_layout.setSpacing(12)

        # Monitor Device (Speakers / Headphones)
        d_layout.addWidget(QLabel("🎧 Устройство воспроизведения для себя (Динамики / Наушники):"))
        self.combo_monitor = QComboBox()
        d_layout.addWidget(self.combo_monitor)

        # Target Mic Device (Virtual Cable)
        d_layout.addWidget(QLabel("🎙️ Вывод в микрофон (VB-Audio Virtual Cable / Вывод в Discord):"))
        self.combo_target_mic = QComboBox()
        d_layout.addWidget(self.combo_target_mic)

        # Physical Mic Input
        d_layout.addWidget(QLabel("🎤 Твой реальный микрофон (для эффектов и проброса голоса):"))
        self.combo_mic_in = QComboBox()
        d_layout.addWidget(self.combo_mic_in)

        layout.addWidget(dev_group)

        # 2. Virtual Cable Setup Guide Card
        guide_card = QFrame()
        guide_card.setStyleSheet("""
            QFrame {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        g_layout = QVBoxLayout(guide_card)
        g_layout.setSpacing(6)

        g_title = QLabel("💡 Как передавать звук в Discord, игры и стримы:")
        g_title.setStyleSheet("font-weight: 700; color: #38bdf8; font-size: 12px;")
        g_layout.addWidget(g_title)

        g_text = QLabel(
            "1. Установите бесплатный кабель <b>VB-Audio Cable</b> (или Voicemeeter).<br>"
            "2. В пункте выше выберите <b>CABLE Input</b> как «Вывод в микрофон».<br>"
            "3. В настройках Discord/игры выберите микрофоном <b>CABLE Output</b>.<br>"
            "4. В SoundFlow включите «Включить микрофон в миксер», чтобы тиммейты слышали и ваш голос, и звуки!"
        )
        g_text.setTextFormat(Qt.TextFormat.RichText)
        g_text.setWordWrap(True)
        g_text.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.4;")
        g_layout.addWidget(g_text)

        layout.addWidget(guide_card)

        # 3. Preferences Group
        pref_group = QGroupBox("ПАРАМЕТРЫ И ПОВЕДЕНИЕ")
        p_layout = QVBoxLayout(pref_group)
        p_layout.setSpacing(10)

        # Buffer size
        buf_row = QHBoxLayout()
        buf_row.addWidget(QLabel("Размер буфера (задержка / Latency):"))
        self.combo_buffer = QComboBox()
        self.combo_buffer.addItem("512 сэмплов (~10 мс - ультранизкая задержка)", 512)
        self.combo_buffer.addItem("1024 сэмпла (~21 мс - стабильно, рекомендуемо)", 1024)
        self.combo_buffer.addItem("2048 сэмплов (~42 мс - без пропусков на слабых ПК)", 2048)
        current_buf = self.cfg.get("buffer_size", 1024)
        for idx in range(self.combo_buffer.count()):
            if self.combo_buffer.itemData(idx) == current_buf:
                self.combo_buffer.setCurrentIndex(idx)
                break
        buf_row.addWidget(self.combo_buffer)
        p_layout.addLayout(buf_row)

        # Replay Duration
        rep_row = QHBoxLayout()
        rep_row.addWidget(QLabel("Длительность буфера моментального клипа:"))
        self.combo_replay = QComboBox()
        self.combo_replay.addItem("15 секунд", 15)
        self.combo_replay.addItem("30 секунд (по умолчанию)", 30)
        self.combo_replay.addItem("60 секунд", 60)
        curr_dur = self.cfg.get("instant_replay_duration", 30)
        for idx in range(self.combo_replay.count()):
            if self.combo_replay.itemData(idx) == curr_dur:
                self.combo_replay.setCurrentIndex(idx)
                break
        rep_row.addWidget(self.combo_replay)
        p_layout.addLayout(rep_row)

        # Minimize to tray
        self.chk_tray = QCheckBox("Сворачивать в системный трей при закрытии (работа в фоне)")
        self.chk_tray.setChecked(bool(self.cfg.get("minimize_to_tray", True)))
        p_layout.addWidget(self.chk_tray)

        layout.addWidget(pref_group)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Применить настройки")
        btn_save.setObjectName("AccentButton")
        btn_save.clicked.connect(self._save_settings)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def _load_devices(self):
        devices = AudioEngine.get_audio_devices()

        # Monitor Devices (Outputs)
        self.combo_monitor.clear()
        for d in devices["outputs"]:
            label = f"[{d['hostapi']}] {d['name']} (ch: {d['max_out']})"
            self.combo_monitor.addItem(label, d["id"])

        # Target Mic Devices (Outputs - e.g. Virtual Cable)
        self.combo_target_mic.clear()
        self.combo_target_mic.addItem("-- Не использовать отдельный виртуальный микрофон --", None)
        for d in devices["outputs"]:
            label = f"[{d['hostapi']}] {d['name']}"
            self.combo_target_mic.addItem(label, d["id"])

        # Mic Inputs
        self.combo_mic_in.clear()
        self.combo_mic_in.addItem("-- Без физического микрофона --", None)
        for d in devices["inputs"]:
            label = f"[{d['hostapi']}] {d['name']}"
            self.combo_mic_in.addItem(label, d["id"])

        # Set saved values
        saved_mon = self.cfg.get("monitor_device_id")
        if saved_mon is not None:
            for idx in range(self.combo_monitor.count()):
                if self.combo_monitor.itemData(idx) == saved_mon:
                    self.combo_monitor.setCurrentIndex(idx)
                    break

        saved_mic_target = self.cfg.get("mic_target_device_id")
        if saved_mic_target is not None:
            for idx in range(self.combo_target_mic.count()):
                if self.combo_target_mic.itemData(idx) == saved_mic_target:
                    self.combo_target_mic.setCurrentIndex(idx)
                    break

        saved_mic_in = self.cfg.get("mic_input_device_id")
        if saved_mic_in is not None:
            for idx in range(self.combo_mic_in.count()):
                if self.combo_mic_in.itemData(idx) == saved_mic_in:
                    self.combo_mic_in.setCurrentIndex(idx)
                    break

    def _save_settings(self):
        mon_id = self.combo_monitor.currentData()
        target_id = self.combo_target_mic.currentData()
        mic_in_id = self.combo_mic_in.currentData()
        buf_size = self.combo_buffer.currentData()
        replay_dur = self.combo_replay.currentData()
        tray = self.chk_tray.isChecked()

        self.cfg.set("monitor_device_id", mon_id)
        self.cfg.set("mic_target_device_id", target_id)
        self.cfg.set("mic_input_device_id", mic_in_id)
        self.cfg.set("buffer_size", buf_size)
        self.cfg.set("instant_replay_duration", replay_dur)
        self.cfg.set("minimize_to_tray", tray)

        # Apply to engine
        self.engine.buffer_size = buf_size
        self.engine.instant_replay.set_duration(replay_dur)
        self.engine.initialize_streams(
            monitor_device=mon_id,
            mic_target_device=target_id,
            mic_input_device=mic_in_id
        )

        self.accept()
