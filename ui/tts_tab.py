"""
Text-to-Speech (TTS) Tab for SoundFlow Studio.
Synthesizes neural speech via edge-tts on-the-fly directly into the microphone and headphones,
and allows saving phrases to the soundboard.
"""

import time
import wave
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QSlider, QGroupBox,
    QMessageBox, QFrame, QGridLayout
)
import numpy as np

from core.tts_engine import TTSEngine, AVAILABLE_VOICES


class TTSTab(QWidget):
    """Tab for real-time Text-To-Speech generation directly into microphone."""

    sound_saved_to_board = pyqtSignal(str, str)  # filepath, name

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.tts = TTSEngine(sample_rate=audio_engine.sample_rate)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Text Input Card
        input_group = QGroupBox("ВВОД ТЕКСТА ДЛЯ ОЗВУЧКИ")
        i_layout = QVBoxLayout(input_group)
        i_layout.setSpacing(10)

        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("Введите текст для озвучки в микрофон (например: 'Хорош пацаны, го на Б!')...")
        self.text_input.setFixedHeight(80)
        self.text_input.setStyleSheet("font-size: 14px; background: #0f172a; border-radius: 8px; padding: 10px;")
        i_layout.addWidget(self.text_input)

        # Settings row: Voice, Speed
        controls_row = QHBoxLayout()
        controls_row.setSpacing(14)

        # Voice dropdown
        v_col = QVBoxLayout()
        v_col.addWidget(QLabel("Нейросетевой голос:"))
        self.combo_voice = QComboBox()
        for v in AVAILABLE_VOICES:
            self.combo_voice.addItem(f"{v['name']}", v["id"])
        v_col.addWidget(self.combo_voice)
        controls_row.addLayout(v_col, stretch=1)

        # Rate / Speed slider
        s_col = QVBoxLayout()
        self.lbl_rate = QLabel("Скорость речи: 1.0x")
        s_col.addWidget(self.lbl_rate)
        self.slider_rate = QSlider(Qt.Orientation.Horizontal)
        self.slider_rate.setRange(-40, 40)
        self.slider_rate.setValue(0)
        self.slider_rate.valueChanged.connect(self._on_rate_changed)
        s_col.addWidget(self.slider_rate)
        controls_row.addLayout(s_col, stretch=1)

        i_layout.addLayout(controls_row)

        # Action Buttons
        act_row = QHBoxLayout()
        act_row.setSpacing(12)

        self.btn_speak = QPushButton("🗣️ СКАЗАТЬ В МИКРОФОН (ENTER)")
        self.btn_speak.setObjectName("AccentButton")
        self.btn_speak.setFixedHeight(44)
        self.btn_speak.setStyleSheet("font-size: 14px; font-weight: 800;")
        self.btn_speak.clicked.connect(self._speak_now)
        act_row.addWidget(self.btn_speak, stretch=2)

        self.btn_save_sound = QPushButton("💾 Сохранить на Саундборд")
        self.btn_save_sound.setFixedHeight(44)
        self.btn_save_sound.clicked.connect(self._save_to_soundboard)
        act_row.addWidget(self.btn_save_sound, stretch=1)

        i_layout.addLayout(act_row)

        self.lbl_status = QLabel("Готов к озвучке")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 11px;")
        i_layout.addWidget(self.lbl_status)

        layout.addWidget(input_group)

        # 2. Quick Phrases Presets
        phrases_group = QGroupBox("БЫСТРЫЕ ФРАЗЫ (КЛИК ДЛЯ ОЗВУЧКИ)")
        p_layout = QGridLayout(phrases_group)
        p_layout.setSpacing(10)

        quick_phrases = [
            "GG WP! Отличная игра!",
            "Всем привет, подключаюсь!",
            "Я отойду на пару минут (AFK).",
            "Осторожно, враг сзади!",
            "Да ладно, как так-то?!",
            "Hello guys, nice to meet you!"
        ]

        for idx, phrase in enumerate(quick_phrases):
            row = idx // 2
            col = idx % 2
            btn = QPushButton(f"💬 {phrase}")
            btn.setFixedHeight(38)
            btn.setStyleSheet("""
                QPushButton {
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    text-align: left;
                    padding-left: 12px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    border-color: #00f2fe;
                    background: #16243d;
                }
            """)
            btn.clicked.connect(lambda checked, p=phrase: self._quick_phrase_click(p))
            p_layout.addWidget(btn, row, col)

        layout.addWidget(phrases_group)
        layout.addStretch()

    def _on_rate_changed(self, val: int):
        speed_factor = 1.0 + (val / 100.0)
        self.lbl_rate.setText(f"Скорость речи: {speed_factor:.2f}x")

    def _get_rate_str(self) -> str:
        val = self.slider_rate.value()
        sign = "+" if val >= 0 else ""
        return f"{sign}{val}%"

    def _quick_phrase_click(self, phrase: str):
        self.text_input.setPlainText(phrase)
        self._speak_now()

    def _speak_now(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            return

        voice = self.combo_voice.currentData()
        rate = self._get_rate_str()

        self.lbl_status.setText("Генерация нейросетью...")
        self.btn_speak.setEnabled(False)

        def on_done(samples: np.ndarray):
            self.btn_speak.setEnabled(True)
            if samples is not None and len(samples) > 0:
                self.lbl_status.setText("Воспроизводится в микрофон и наушники")
                self.engine.play_tts_samples(samples)
            else:
                self.lbl_status.setText("Ошибка генерации речи (проверьте интернет-соединение)")

        self.tts.synthesize_async(text=text, voice=voice, rate=rate, callback=on_done)

    def _save_to_soundboard(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Внимание", "Введите текст для создания звука.")
            return

        voice = self.combo_voice.currentData()
        rate = self._get_rate_str()
        self.lbl_status.setText("Генерация аудиофайла для саундборда...")

        def on_done(samples: np.ndarray):
            if samples is None or len(samples) == 0:
                self.lbl_status.setText("Ошибка создания аудиофайла")
                return

            # Save as WAV in sounds dir
            sounds_dir = Path(__file__).parent.parent / "assets" / "sounds"
            sounds_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"tts_{timestamp}.wav"
            filepath = sounds_dir / filename

            clipped = np.clip(samples, -1.0, 1.0)
            int16_data = (clipped * 32767).astype(np.int16)

            with wave.open(str(filepath), "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(self.engine.sample_rate)
                wf.writeframes(int16_data.tobytes())

            short_title = (text[:24] + "...") if len(text) > 24 else text
            self.lbl_status.setText(f"Сохранено на Саундборд: {short_title}")
            self.sound_saved_to_board.emit(str(filepath), short_title)

        self.tts.synthesize_async(text=text, voice=voice, rate=rate, callback=on_done)
