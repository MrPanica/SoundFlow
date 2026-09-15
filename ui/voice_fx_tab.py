"""
Voice FX and Microphone DSP Tab for SoundFlow Studio.
Provides real-time voice changer presets, noise gate, and microphone monitoring.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QFrame, QGroupBox, QGridLayout
)

from .widgets import VUMeterWidget


class VoiceFXTab(QWidget):
    """Tab for microphone pass-through, voice modulation effects, and noise gate."""

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.active_preset = "normal"

        self._build_ui()

        # Timer for live mic meter
        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self._update_meters)
        self.meter_timer.start(33)  # ~30 fps

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Master Mic Toggle Card
        top_card = QFrame()
        top_card.setStyleSheet("""
            QFrame {
                background: #131d31;
                border: 1px solid #1e293b;
                border-radius: 12px;
                padding: 16px;
            }
        """)
        t_layout = QVBoxLayout(top_card)
        t_layout.setSpacing(12)

        toggle_row = QHBoxLayout()
        self.btn_toggle_mic = QPushButton("🎙️ ВКЛЮЧИТЬ МИКРОФОН В МИКСЕР (PASSTHROUGH)")
        self.btn_toggle_mic.setFixedHeight(46)
        self.btn_toggle_mic.setObjectName("AccentButton")
        self.btn_toggle_mic.setStyleSheet("font-size: 14px; font-weight: 800; border-radius: 8px;")
        self.btn_toggle_mic.clicked.connect(self._toggle_mic_passthrough)
        toggle_row.addWidget(self.btn_toggle_mic, stretch=1)
        t_layout.addLayout(toggle_row)

        # Live Mic Level Meter
        meter_row = QHBoxLayout()
        self.mic_vu = VUMeterWidget(label="ВХОДНОЙ СИГНАЛ МИКРОФОНА")
        meter_row.addWidget(self.mic_vu, stretch=1)
        t_layout.addLayout(meter_row)

        layout.addWidget(top_card)

        # 2. Noise Gate Section
        gate_group = QGroupBox("ШУМОПОДАВИТЕЛЬ (NOISE GATE)")
        g_layout = QVBoxLayout(gate_group)
        g_layout.setSpacing(10)

        gate_row = QHBoxLayout()
        self.lbl_threshold = QLabel("Порог срабатывания: -45 dB")
        self.lbl_threshold.setFixedWidth(200)
        self.slider_gate = QSlider(Qt.Orientation.Horizontal)
        self.slider_gate.setRange(-70, -15)
        self.slider_gate.setValue(-45)
        self.slider_gate.valueChanged.connect(self._on_gate_threshold_change)
        gate_row.addWidget(self.lbl_threshold)
        gate_row.addWidget(self.slider_gate)
        g_layout.addLayout(gate_row)

        lbl_gate_hint = QLabel("💡 Фоновый шум тише установленного порога будет автоматически глушиться.")
        lbl_gate_hint.setStyleSheet("color: #64748b; font-size: 11px;")
        g_layout.addWidget(lbl_gate_hint)

        layout.addWidget(gate_group)

        # 3. Voice Changer Presets Grid
        fx_group = QGroupBox("ПРЕСЕТЫ МОДУЛЯЦИИ ГОЛОСА (VOICE CHANGER)")
        fx_layout = QGridLayout(fx_group)
        fx_layout.setSpacing(12)

        presets = [
            ("normal", "🎭 Обычный голос", "Чистый естественный голос без эффектов"),
            ("helium", "🐿️ Бурундук / Helium", "Высокий забавный мультяшный голос"),
            ("monster", "👹 Демон / Monster", "Глубокий зловещий бас с сатурацией"),
            ("robot", "🤖 Кибер-Робот", "Металлический голос с кольцевым модулятором"),
            ("megaphone", "📢 Мегафон / Рация", "Эффект переговоров по военной рации"),
            ("echo", "🌌 Эхо в пещере", "Пространственные повторы и задержка")
        ]

        self.preset_buttons = {}
        for idx, (p_id, p_name, p_desc) in enumerate(presets):
            row = idx // 2
            col = idx % 2

            btn = QPushButton(f"{p_name}\n{p_desc}")
            btn.setFixedHeight(56)
            btn.setStyleSheet("""
                QPushButton {
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 8px;
                    font-size: 12px;
                    text-align: left;
                }
                QPushButton:hover {
                    border-color: #38bdf8;
                    background: #16243d;
                }
            """)
            btn.clicked.connect(lambda checked, pid=p_id: self._select_preset(pid))
            fx_layout.addWidget(btn, row, col)
            self.preset_buttons[p_id] = btn

        layout.addWidget(fx_group)
        layout.addStretch()

        self._update_preset_styling()

    def _toggle_mic_passthrough(self):
        enabled = not self.engine.mic_passthrough_enabled
        self.engine.mic_passthrough_enabled = enabled
        if enabled:
            self.btn_toggle_mic.setText("🟢 МИКРОФОН АКТИВЕН В МИКСЕРЕ (ОТКЛЮЧИТЬ)")
            self.btn_toggle_mic.setStyleSheet("background: #10b981; color: #ffffff; font-size: 14px; font-weight: 800; border-radius: 8px;")
        else:
            self.btn_toggle_mic.setText("🎙️ ВКЛЮЧИТЬ МИКРОФОН В МИКСЕР (PASSTHROUGH)")
            self.btn_toggle_mic.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:1 #4facfe); color: #0b0f19; font-size: 14px; font-weight: 800; border-radius: 8px;")

    def _on_gate_threshold_change(self, val: int):
        self.lbl_threshold.setText(f"Порог срабатывания: {val} dB")
        self.engine.voice_fx.set_gate_threshold(float(val))

    def _select_preset(self, preset_id: str):
        self.active_preset = preset_id
        self.engine.voice_fx.set_preset(preset_id)
        self._update_preset_styling()

    def _update_preset_styling(self):
        for pid, btn in self.preset_buttons.items():
            if pid == self.active_preset:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #0f2d4a;
                        border: 2px solid #00f2fe;
                        border-radius: 8px;
                        padding: 8px;
                        font-size: 12px;
                        font-weight: 700;
                        color: #ffffff;
                        text-align: left;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #1e293b;
                        border: 1px solid #334155;
                        border-radius: 8px;
                        padding: 8px;
                        font-size: 12px;
                        text-align: left;
                        color: #94a3b8;
                    }
                    QPushButton:hover {
                        border-color: #38bdf8;
                        background: #16243d;
                        color: #ffffff;
                    }
                """)

    def _update_meters(self):
        peak = self.engine.mic_in_peak
        self.mic_vu.set_levels(peak, peak)
