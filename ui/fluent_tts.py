"""
Fluent Design Neural Text-to-Speech Interface for SoundFlow Studio.
Features Microsoft Neural TTS, Voice Changer FX integration, customizable phrase presets,
instant play to microphone, and soundboard exporting.
"""

import time
import wave
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QMessageBox, QDialog, QScrollArea
)
import numpy as np
from qfluentwidgets import (
    CardWidget, PrimaryPushButton, PushButton, TransparentToolButton,
    TextEdit, LineEdit, ComboBox, Slider, TitleLabel, SubtitleLabel,
    BodyLabel, CaptionLabel, FluentIcon, CheckBox, RoundMenu, Action
)

from core.tts_engine import TTSEngine, AVAILABLE_VOICES
from core.voice_fx import VoiceFXProcessor, BUILTIN_PRESETS

TTS_FX_OPTIONS = [
    ("normal", "🎭 Обычный (без эффекта)"),
    ("robot", "🤖 Кибер-Робот"),
    ("helium", "🐿️ Бурундук (Helium)"),
    ("monster", "👹 Демон (Monster)"),
    ("megaphone", "📢 Мегафон / Рация"),
    ("echo", "🌌 Пространственное эхо"),
    ("radio", "📻 Старое радио"),
    ("alien", "👽 Пришелец")
]


class AddTTSPresetDialog(QDialog):
    """Dialog to create a new quick phrase preset with voice and voice-changer effect."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новый пресет быстрой фразы")
        self.setFixedSize(460, 350)
        self.setStyleSheet("background-color: #202020; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = SubtitleLabel("Добавить пресет фразы", self)
        layout.addWidget(title)

        # Text input
        layout.addWidget(BodyLabel("Текст фразы:", self))
        self.edit_text = LineEdit(self)
        self.edit_text.setPlaceholderText("Например: GG WP! Хорошая игра!")
        self.edit_text.setFixedHeight(34)
        layout.addWidget(self.edit_text)

        # Voice selection
        layout.addWidget(BodyLabel("Голос озвучки:", self))
        self.combo_voice = ComboBox(self)
        self.combo_voice.setFixedHeight(32)
        for v in AVAILABLE_VOICES:
            self.combo_voice.addItem(v["name"], userData=v["id"])
        layout.addWidget(self.combo_voice)

        # FX selection
        layout.addWidget(BodyLabel("Голосовой эффект (Voice Changer):", self))
        self.combo_fx = ComboBox(self)
        self.combo_fx.setFixedHeight(32)
        for fx_id, fx_label in TTS_FX_OPTIONS:
            self.combo_fx.addItem(fx_label, userData=fx_id)
        layout.addWidget(self.combo_fx)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = PushButton("Отмена", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_add = PrimaryPushButton(FluentIcon.ADD, "Добавить", self)
        self.btn_add.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.btn_add)

        layout.addLayout(btn_layout)

    def _validate_and_accept(self):
        text = self.edit_text.text().strip()
        if not text:
            QMessageBox.warning(self, "Внимание", "Пожалуйста, введите текст фразы.")
            return
        self.accept()

    def get_data(self) -> Dict[str, str]:
        return {
            "text": self.edit_text.text().strip(),
            "voice": self.combo_voice.currentData() or "ru-RU-DmitryNeural",
            "fx": self.combo_fx.currentData() or "normal"
        }


class FluentTTSInterface(QWidget):
    """Windows 11 Fluent Design Neural Text-To-Speech Interface."""

    sound_saved_to_board = pyqtSignal(str, str)

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.tts = TTSEngine(sample_rate=audio_engine.sample_rate)
        self.fx_processor = VoiceFXProcessor(sample_rate=audio_engine.sample_rate)
        self._last_tts_time = 0.0
        self._is_synthesizing = False
        self._active_phrase_menu = None
        self.setObjectName("ttsInterface")

        self._build_ui()
        self._refresh_quick_phrases()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        # Header Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = TitleLabel("Синтез речи (TTS) и Быстрые фразы", self)
        lbl_sub = CaptionLabel(
            "Озвучка текста нейросетевыми голосами Microsoft Neural с эффектами войс-чейнджера прямо в микрофон собеседникам",
            self
        )
        lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        layout.addLayout(title_layout)

        # 1. Main Input Card
        card_input = CardWidget(self)
        i_layout = QVBoxLayout(card_input)
        i_layout.setContentsMargins(20, 18, 20, 18)
        i_layout.setSpacing(14)

        self.text_input = TextEdit(card_input)
        self.text_input.setPlaceholderText("Введите любой текст для озвучки в микрофон или выберите фразу ниже...")
        self.text_input.setFixedHeight(85)
        i_layout.addWidget(self.text_input)

        # Settings row
        set_row = QHBoxLayout()
        set_row.setSpacing(14)

        # Voice
        v_col = QVBoxLayout()
        v_col.setSpacing(4)
        v_col.addWidget(BodyLabel("Голос озвучки:", card_input))
        self.combo_voice = ComboBox(card_input)
        self.combo_voice.setFixedHeight(32)
        for v in AVAILABLE_VOICES:
            self.combo_voice.addItem(v["name"], userData=v["id"])
        v_col.addWidget(self.combo_voice)
        set_row.addLayout(v_col, stretch=2)

        # Voice Changer FX
        fx_col = QVBoxLayout()
        fx_col.setSpacing(4)
        fx_col.addWidget(BodyLabel("Голосовой эффект (Voice FX):", card_input))
        self.combo_fx = ComboBox(card_input)
        self.combo_fx.setFixedHeight(32)
        for fx_id, fx_label in TTS_FX_OPTIONS:
            self.combo_fx.addItem(fx_label, userData=fx_id)
        fx_col.addWidget(self.combo_fx)
        set_row.addLayout(fx_col, stretch=2)

        # Rate
        s_col = QVBoxLayout()
        s_col.setSpacing(4)
        self.lbl_rate = BodyLabel("Скорость речи: 1.0x", card_input)
        s_col.addWidget(self.lbl_rate)
        self.slider_rate = Slider(Qt.Orientation.Horizontal, card_input)
        self.slider_rate.setRange(-40, 40)
        self.slider_rate.setValue(0)
        self.slider_rate.valueChanged.connect(self._on_rate_change)
        s_col.addWidget(self.slider_rate)
        set_row.addLayout(s_col, stretch=2)

        i_layout.addLayout(set_row)

        # Sidetone toggle
        self.chk_sidetone = CheckBox("Дублировать себе (слышать в динамиках / наушниках при отправке в микрофон)", card_input)
        self.chk_sidetone.setChecked(True)
        i_layout.addWidget(self.chk_sidetone)

        # Action Buttons
        act_row = QHBoxLayout()
        act_row.setSpacing(10)

        self.btn_preview = PushButton(FluentIcon.VOLUME, "Прослушать", card_input)
        self.btn_preview.setFixedHeight(38)
        self.btn_preview.clicked.connect(self._preview_now)
        act_row.addWidget(self.btn_preview, stretch=1)

        self.btn_speak = PrimaryPushButton(FluentIcon.SEND, "Сказать в микрофон", card_input)
        self.btn_speak.setFixedHeight(38)
        self.btn_speak.clicked.connect(self._speak_now)
        act_row.addWidget(self.btn_speak, stretch=1)

        self.btn_save = PushButton(FluentIcon.SAVE, "Сохранить на Саундборд", card_input)
        self.btn_save.setFixedHeight(38)
        self.btn_save.clicked.connect(self._save_to_soundboard)
        act_row.addWidget(self.btn_save, stretch=1)

        i_layout.addLayout(act_row)

        self.lbl_status = CaptionLabel("Готов к озвучке", card_input)
        self.lbl_status.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        i_layout.addWidget(self.lbl_status)

        layout.addWidget(card_input)

        # 2. Quick Phrases Presets Card
        self.card_quick = CardWidget(self)
        self.q_layout = QVBoxLayout(self.card_quick)
        self.q_layout.setContentsMargins(20, 16, 20, 16)
        self.q_layout.setSpacing(12)

        q_head = QHBoxLayout()
        q_title = SubtitleLabel("Быстрые фразы и пресеты озвучки", self.card_quick)
        q_head.addWidget(q_title)
        q_head.addStretch()

        self.btn_add_phrase = PushButton(FluentIcon.ADD, "Добавить пресет", self.card_quick)
        self.btn_add_phrase.setFixedHeight(32)
        self.btn_add_phrase.clicked.connect(self._prompt_add_phrase)
        q_head.addWidget(self.btn_add_phrase)
        self.q_layout.addLayout(q_head)

        hint = CaptionLabel("💡 Нажмите иконку ⚡ чтобы мгновенно сказать в микрофон. Правый клик (ПКМ) — удалить пресет.", self.card_quick)
        hint.setStyleSheet("color: rgba(255, 255, 255, 0.45);")
        self.q_layout.addWidget(hint)

        # Phrases container
        self.phrases_container = QWidget(self.card_quick)
        self.phrases_layout = QGridLayout(self.phrases_container)
        self.phrases_layout.setContentsMargins(0, 0, 0, 0)
        self.phrases_layout.setSpacing(8)
        self.q_layout.addWidget(self.phrases_container)

        layout.addWidget(self.card_quick)
        layout.addStretch()

    def _refresh_quick_phrases(self):
        # Clear existing items in phrases layout
        while self.phrases_layout.count():
            item = self.phrases_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        presets = list(self.cfg.tts_presets)
        for idx, p in enumerate(presets):
            row = idx // 2
            col = idx % 2
            item_widget = self._create_phrase_item(p)
            self.phrases_layout.addWidget(item_widget, row, col)

    def _create_phrase_item(self, preset: Dict[str, Any]) -> QWidget:
        card = CardWidget(self.phrases_container)
        card.setFixedHeight(48)
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos, p=preset, c=card: self._show_phrase_menu(p, c.mapToGlobal(pos)))

        h_layout = QHBoxLayout(card)
        h_layout.setContentsMargins(10, 4, 8, 4)
        h_layout.setSpacing(6)

        # Voice / FX badge
        fx = preset.get("fx", "normal")
        fx_badge = ""
        if fx == "robot":
            fx_badge = "🤖 "
        elif fx == "helium":
            fx_badge = "🐿️ "
        elif fx == "monster":
            fx_badge = "👹 "
        elif fx == "megaphone":
            fx_badge = "📢 "
        elif fx == "echo":
            fx_badge = "🌌 "
        elif fx == "radio":
            fx_badge = "📻 "
        elif fx == "alien":
            fx_badge = "👽 "

        text = preset.get("text", "")
        display_text = f"{fx_badge}{text}"

        # Main button to paste text and set voice
        btn_paste = PushButton(display_text, card)
        btn_paste.setFixedHeight(34)
        btn_paste.setStyleSheet("text-align: left; padding: 4px 8px; font-size: 12px; border: none; background: transparent;")
        btn_paste.setToolTip("Вставить фразу и параметры в поле ввода")
        btn_paste.clicked.connect(lambda checked, p=preset: self._apply_preset_to_editor(p))
        h_layout.addWidget(btn_paste, stretch=1)

        # Quick direct play to microphone button (⚡ without changing editor)
        btn_direct_mic = TransparentToolButton(FluentIcon.SEND, card)
        btn_direct_mic.setFixedSize(32, 32)
        btn_direct_mic.setToolTip("Сразу сказать в микрофон (без вставки в поле)")
        btn_direct_mic.clicked.connect(lambda checked, p=preset: self._play_preset_direct(p, play_mic=True))
        h_layout.addWidget(btn_direct_mic)

        # Quick preview button (🔊)
        btn_direct_prev = TransparentToolButton(FluentIcon.VOLUME, card)
        btn_direct_prev.setFixedSize(32, 32)
        btn_direct_prev.setToolTip("Прослушать")
        btn_direct_prev.clicked.connect(lambda checked, p=preset: self._play_preset_direct(p, play_mic=False))
        h_layout.addWidget(btn_direct_prev)

        return card

    def _show_phrase_menu(self, preset: Dict[str, Any], global_pos):
        if self._active_phrase_menu and self._active_phrase_menu.isVisible():
            return

        menu = RoundMenu(parent=self)
        self._active_phrase_menu = menu

        act_speak = Action(FluentIcon.SEND, "Сказать в микрофон", self)
        act_speak.triggered.connect(lambda: self._play_preset_direct(preset, play_mic=True))
        menu.addAction(act_speak)

        act_preview = Action(FluentIcon.VOLUME, "Прослушать", self)
        act_preview.triggered.connect(lambda: self._play_preset_direct(preset, play_mic=False))
        menu.addAction(act_preview)

        act_paste = Action(FluentIcon.EDIT, "Вставить в поле ввода", self)
        act_paste.triggered.connect(lambda: self._apply_preset_to_editor(preset))
        menu.addAction(act_paste)

        menu.addSeparator()

        act_del = Action(FluentIcon.DELETE, "Удалить пресет", self)
        act_del.triggered.connect(lambda: self._delete_preset(preset))
        menu.addAction(act_del)

        menu.exec(global_pos)
        self._active_phrase_menu = None

    def _apply_preset_to_editor(self, preset: Dict[str, Any]):
        self.text_input.setPlainText(preset.get("text", ""))
        voice = preset.get("voice", "")
        if voice:
            idx = self.combo_voice.findData(voice)
            if idx >= 0:
                self.combo_voice.setCurrentIndex(idx)
        fx = preset.get("fx", "normal")
        idx_fx = self.combo_fx.findData(fx)
        if idx_fx >= 0:
            self.combo_fx.setCurrentIndex(idx_fx)

    def _play_preset_direct(self, preset: Dict[str, Any], play_mic: bool = True):
        text = preset.get("text", "").strip()
        if not text:
            return

        now = time.time()
        if now - self._last_tts_time < 0.7 or self._is_synthesizing:
            return
        self._last_tts_time = now
        self._is_synthesizing = True

        voice = preset.get("voice") or self.combo_voice.currentData()
        fx = preset.get("fx", "normal")
        rate_val = self.slider_rate.value()
        rate_str = f"{'+' if rate_val >= 0 else ''}{rate_val}%"

        play_monitor = self.chk_sidetone.isChecked() if play_mic else True
        self.lbl_status.setText(f"Генерация пресета «{text[:18]}...»")

        def on_done(samples: Optional[np.ndarray]):
            self._is_synthesizing = False
            if samples is not None and len(samples) > 0:
                # Apply Voice Changer FX if configured
                if fx != "normal":
                    try:
                        temp_fx = VoiceFXProcessor(sample_rate=self.engine.sample_rate)
                        temp_fx.set_preset(fx)
                        samples = temp_fx.process(samples)
                    except Exception as e:
                        print(f"[TTS] Error applying FX {fx}: {e}")

                if play_mic and play_monitor:
                    self.lbl_status.setText(f"Транслируется в микрофон и для себя: «{text[:20]}»")
                elif play_mic:
                    self.lbl_status.setText(f"Транслируется в микрофон: «{text[:20]}»")
                else:
                    self.lbl_status.setText(f"Предпрослушивание: «{text[:20]}»")

                self.engine.play_tts_samples(samples, play_monitor=play_monitor, play_mic=play_mic)
            else:
                self.lbl_status.setText("Ошибка генерации речи")

        self.tts.synthesize_async(text=text, voice=voice, rate=rate_str, callback=on_done)

    def _prompt_add_phrase(self):
        dlg = AddTTSPresetDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.cfg.add_tts_preset(
                text=data["text"],
                voice=data["voice"],
                fx=data["fx"]
            )
            self._refresh_quick_phrases()
            self.lbl_status.setText(f"Добавлен новый пресет: {data['text'][:20]}...")

    def _delete_preset(self, preset: Dict[str, Any]):
        p_id = preset.get("id")
        p_text = preset.get("text", "")
        reply = QMessageBox.question(
            self,
            "Удаление пресета",
            f"Вы уверены, что хотите удалить пресет «{p_text}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if p_id:
                self.cfg.remove_tts_preset(p_id)
            else:
                # Fallback matching by text
                self.cfg.tts_presets = [p for p in self.cfg.tts_presets if p.get("text") != p_text]
                self.cfg.save_tts_presets()
            self._refresh_quick_phrases()
            self.lbl_status.setText("Пресет удален")

    def _on_rate_change(self, val: int):
        speed = 1.0 + (val / 100.0)
        self.lbl_rate.setText(f"Скорость речи: {speed:.2f}x")

    def _speak_now(self):
        self._synthesize_and_play(play_mic=True, play_monitor=self.chk_sidetone.isChecked())

    def _preview_now(self):
        self._synthesize_and_play(play_mic=False, play_monitor=True)

    def _synthesize_and_play(self, play_mic: bool = True, play_monitor: bool = True):
        text = self.text_input.toPlainText().strip()
        if not text:
            return

        now = time.time()
        if now - self._last_tts_time < 0.7 or self._is_synthesizing:
            return
        self._last_tts_time = now
        self._is_synthesizing = True

        voice = self.combo_voice.currentData() or "ru-RU-DmitryNeural"
        fx = self.combo_fx.currentData() or "normal"
        rate_val = self.slider_rate.value()
        rate_str = f"{'+' if rate_val >= 0 else ''}{rate_val}%"

        self.lbl_status.setText("Генерация нейросетью...")
        self.btn_speak.setEnabled(False)
        self.btn_preview.setEnabled(False)

        def on_done(samples: np.ndarray):
            self._is_synthesizing = False
            self.btn_speak.setEnabled(True)
            self.btn_preview.setEnabled(True)
            if samples is not None and len(samples) > 0:
                # Apply Voice FX if selected
                if fx != "normal":
                    try:
                        temp_fx = VoiceFXProcessor(sample_rate=self.engine.sample_rate)
                        temp_fx.set_preset(fx)
                        samples = temp_fx.process(samples)
                    except Exception as e:
                        print(f"[TTS] FX error: {e}")

                if play_mic and play_monitor:
                    self.lbl_status.setText("Воспроизводится в микрофон и для себя")
                elif play_mic:
                    self.lbl_status.setText("Воспроизводится в микрофон")
                else:
                    self.lbl_status.setText("Воспроизводится (предпрослушивание)")
                self.engine.play_tts_samples(samples, play_monitor=play_monitor, play_mic=play_mic)
            else:
                self.lbl_status.setText("Ошибка генерации речи")

        self.tts.synthesize_async(text=text, voice=voice, rate=rate_str, callback=on_done)

    def _save_to_soundboard(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Внимание", "Введите текст для создания звука.")
            return

        voice = self.combo_voice.currentData() or "ru-RU-DmitryNeural"
        fx = self.combo_fx.currentData() or "normal"
        rate_val = self.slider_rate.value()
        rate_str = f"{'+' if rate_val >= 0 else ''}{rate_val}%"
        self.lbl_status.setText("Генерация аудиофайла...")

        def on_done(samples: np.ndarray):
            if samples is None or len(samples) == 0:
                self.lbl_status.setText("Ошибка создания аудиофайла")
                return

            if fx != "normal":
                try:
                    temp_fx = VoiceFXProcessor(sample_rate=self.engine.sample_rate)
                    temp_fx.set_preset(fx)
                    samples = temp_fx.process(samples)
                except Exception as e:
                    print(f"[TTS] FX error: {e}")

            sounds_dir = Path(__file__).parent.parent / "assets" / "sounds"
            sounds_dir.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filepath = sounds_dir / f"tts_{timestamp}.wav"

            clipped = np.clip(samples, -1.0, 1.0)
            int16_data = (clipped * 32767).astype(np.int16)

            with wave.open(str(filepath), "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(self.engine.sample_rate)
                wf.writeframes(int16_data.tobytes())

            short_title = (text[:22] + "...") if len(text) > 22 else text
            self.lbl_status.setText(f"Сохранено на Саундборд: {short_title}")
            self.sound_saved_to_board.emit(str(filepath), short_title)

        self.tts.synthesize_async(text=text, voice=voice, rate=rate_str, callback=on_done)
