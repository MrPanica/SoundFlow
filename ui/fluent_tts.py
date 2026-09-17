"""
Fluent Design Neural Text-to-Speech Interface for SoundFlow Studio.
Features Microsoft Neural TTS, Voice Changer FX integration, customizable phrase presets,
instant play to microphone, and soundboard exporting.
"""

import time
import wave
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
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
from core.i18n import tr

def get_tts_fx_options():
    return [
        ("normal", tr("preset_normal_name", "Обычный (без эффекта)")),
        ("robot", tr("preset_robot_name", "Кибер-Робот")),
        ("helium", tr("preset_helium_name", "Бурундук (Helium)")),
        ("child", tr("preset_child_name", "Ребёнок")),
        ("female", tr("preset_female_name", "Женский голос")),
        ("male", tr("preset_male_name", "Мужской глубокий")),
        ("monster", tr("preset_monster_name", "Демон (Monster)")),
        ("megaphone", tr("preset_megaphone_name", "Мегафон / Рация")),
        ("echo", tr("preset_echo_name", "Пространственное эхо")),
        ("radio", tr("preset_radio_name", "Старое радио")),
        ("alien", tr("preset_alien_name", "Пришелец"))
    ]


class TTSPresetDialog(QDialog):
    """Dialog to create or edit a quick phrase preset with voice and voice-changer effect."""

    def __init__(self, parent=None, preset: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self.preset = preset
        is_edit = preset is not None
        title_text = tr("tts_dlg_edit_title", "Редактировать пресет фразы") if is_edit else tr("tts_dlg_new_phrase_title", "Добавить пресет фразы")
        self.setWindowTitle(title_text)
        self.setFixedSize(460, 350)
        self.setStyleSheet("background-color: #202020; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = SubtitleLabel(title_text, self)
        layout.addWidget(title)

        # Text input
        layout.addWidget(BodyLabel(tr("tts_input_placeholder", "Текст фразы:"), self))
        self.edit_text = LineEdit(self)
        self.edit_text.setPlaceholderText(tr("tts_phrase_placeholder", "Например: GG WP! Отличная игра!"))
        self.edit_text.setFixedHeight(34)
        if is_edit:
            self.edit_text.setText(preset.get("text", ""))
        layout.addWidget(self.edit_text)

        # Voice selection
        layout.addWidget(BodyLabel(tr("tts_voice_label", "Голос озвучки:"), self))
        self.combo_voice = ComboBox(self)
        self.combo_voice.setFixedHeight(32)
        for v in AVAILABLE_VOICES:
            self.combo_voice.addItem(tr(f"voice_{v['id']}", v["name"]), userData=v["id"])
        if is_edit:
            idx = self.combo_voice.findData(preset.get("voice", "ru-RU-DmitryNeural"))
            if idx >= 0:
                self.combo_voice.setCurrentIndex(idx)
        layout.addWidget(self.combo_voice)

        # FX selection
        layout.addWidget(BodyLabel(tr("voice_fx_title", "Голосовой эффект (Voice Changer):"), self))
        self.combo_fx = ComboBox(self)
        self.combo_fx.setFixedHeight(32)
        for fx_id, fx_label in get_tts_fx_options():
            self.combo_fx.addItem(fx_label, userData=fx_id)
        if is_edit:
            idx_fx = self.combo_fx.findData(preset.get("fx", "normal"))
            if idx_fx >= 0:
                self.combo_fx.setCurrentIndex(idx_fx)
        layout.addWidget(self.combo_fx)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = PushButton(tr("common_cancel", "Отмена"), self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        save_label = tr("common_save", "Сохранить") if is_edit else tr("common_create", "Добавить")
        self.btn_save = PrimaryPushButton(FluentIcon.SAVE if is_edit else FluentIcon.ADD, save_label, self)
        self.btn_save.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def _validate_and_accept(self):
        text = self.edit_text.text().strip()
        if not text:
            QMessageBox.warning(self, tr("tts_warn_empty_title", "Внимание"), tr("tts_error_empty", "Пожалуйста, введите текст фразы."))
            return
        self.accept()

    def get_data(self) -> Dict[str, str]:
        return {
            "text": self.edit_text.text().strip(),
            "voice": self.combo_voice.currentData() or "ru-RU-DmitryNeural",
            "fx": self.combo_fx.currentData() or "normal"
        }


AddTTSPresetDialog = TTSPresetDialog
EditTTSPresetDialog = TTSPresetDialog


class FluentTTSInterface(QWidget):
    """Windows 11 Fluent Design Neural Text-To-Speech Interface."""

    sound_saved_to_board = pyqtSignal(str, str)
    sig_tts_direct_done = pyqtSignal(object, str, bool, bool)
    sig_tts_synthesis_done = pyqtSignal(object, str, bool, bool)
    sig_tts_save_done = pyqtSignal(str, str)
    sig_tts_error = pyqtSignal(str)

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

        self.sig_tts_direct_done.connect(self._on_direct_done_main_thread)
        self.sig_tts_synthesis_done.connect(self._on_synthesis_done_main_thread)
        self.sig_tts_save_done.connect(self._on_save_done_main_thread)
        self.sig_tts_error.connect(self._on_error_main_thread)

        self._build_ui()
        self._load_target_devices()
        self._refresh_quick_phrases()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        # Header Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = TitleLabel(tr("tts_title", "Синтез речи (TTS)"), self)
        lbl_sub = CaptionLabel(
            tr("tts_subtitle", "Озвучивание любого текста естественными голосами Microsoft Neural прямо в микрофон и наушники"),
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
        self.text_input.setPlaceholderText(tr("tts_input_placeholder", "Введите текст для озвучивания (поддерживается русский и английский)..."))
        self.text_input.setFixedHeight(85)
        i_layout.addWidget(self.text_input)

        # Settings row
        set_row = QHBoxLayout()
        set_row.setSpacing(14)

        # Voice
        v_col = QVBoxLayout()
        v_col.setSpacing(4)
        v_col.addWidget(BodyLabel(tr("tts_voice_label", "Голос озвучки:"), card_input))
        self.combo_voice = ComboBox(card_input)
        self.combo_voice.setFixedHeight(32)
        for v in AVAILABLE_VOICES:
            self.combo_voice.addItem(tr(f"voice_{v['id']}", v["name"]), userData=v["id"])
        v_col.addWidget(self.combo_voice)
        set_row.addLayout(v_col, stretch=2)

        # Voice Changer FX
        fx_col = QVBoxLayout()
        fx_col.setSpacing(4)
        fx_col.addWidget(BodyLabel(tr("voice_fx_title", "Голосовой эффект (Voice FX):"), card_input))
        self.combo_fx = ComboBox(card_input)
        self.combo_fx.setFixedHeight(32)
        for fx_id, fx_label in get_tts_fx_options():
            self.combo_fx.addItem(fx_label, userData=fx_id)
        fx_col.addWidget(self.combo_fx)
        set_row.addLayout(fx_col, stretch=2)

        # Rate
        s_col = QVBoxLayout()
        s_col.setSpacing(4)
        self.lbl_rate = BodyLabel(f"{tr('tts_speed_label', 'Скорость речи:')} 1.0x", card_input)
        s_col.addWidget(self.lbl_rate)
        self.slider_rate = Slider(Qt.Orientation.Horizontal, card_input)
        self.slider_rate.setRange(-40, 40)
        self.slider_rate.setValue(0)
        self.slider_rate.valueChanged.connect(self._on_rate_change)
        s_col.addWidget(self.slider_rate)
        set_row.addLayout(s_col, stretch=2)

        i_layout.addLayout(set_row)

        # Sidetone toggle
        self.chk_sidetone = CheckBox(tr("tts_hear_myself", "Дублировать себе (слышать в динамиках / наушниках при отправке в микрофон)"), card_input)
        self.chk_sidetone.setChecked(True)
        i_layout.addWidget(self.chk_sidetone)

        # Target Mic Dropdown Row
        mic_row = QHBoxLayout()
        mic_col = QVBoxLayout()
        mic_col.setSpacing(2)
        lbl_target_mic = CaptionLabel(tr("tts_target_mic_label", "Куда отправлять речь (микрофон / виртуальный кабель):"), card_input)
        lbl_target_mic.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-weight: 600;")
        self.combo_target_mic = ComboBox(card_input)
        self.combo_target_mic.setFixedHeight(34)
        self.combo_target_mic.currentIndexChanged.connect(self._on_target_mic_changed)
        mic_col.addWidget(lbl_target_mic)
        mic_col.addWidget(self.combo_target_mic)
        mic_row.addLayout(mic_col)
        i_layout.addLayout(mic_row)

        # Action Buttons
        act_row = QHBoxLayout()
        act_row.setSpacing(10)

        self.btn_preview = PushButton(FluentIcon.VOLUME, tr("tts_preview_tooltip", "Прослушать"), card_input)
        self.btn_preview.setFixedHeight(38)
        self.btn_preview.clicked.connect(self._preview_now)
        act_row.addWidget(self.btn_preview, stretch=1)

        self.btn_speak = PrimaryPushButton(FluentIcon.SEND, tr("tts_btn_speak", "Сказать в микрофон"), card_input)
        self.btn_speak.setFixedHeight(38)
        self.btn_speak.clicked.connect(self._speak_now)
        act_row.addWidget(self.btn_speak, stretch=1)

        self.btn_save = PushButton(FluentIcon.SAVE, tr("tts_btn_save_mp3", "Сохранить на Саундборд"), card_input)
        self.btn_save.setFixedHeight(38)
        self.btn_save.clicked.connect(self._save_to_soundboard)
        act_row.addWidget(self.btn_save, stretch=1)

        i_layout.addLayout(act_row)

        self.lbl_status = CaptionLabel(tr("tts_status_ready", "Готов к озвучке"), card_input)
        self.lbl_status.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        i_layout.addWidget(self.lbl_status)

        layout.addWidget(card_input)

        # 2. Quick Phrases Presets Card
        self.card_quick = CardWidget(self)
        self.q_layout = QVBoxLayout(self.card_quick)
        self.q_layout.setContentsMargins(20, 16, 20, 16)
        self.q_layout.setSpacing(12)

        q_head = QHBoxLayout()
        q_title = SubtitleLabel(tr("tts_quick_title", "Быстрые фразы и пресеты озвучки"), self.card_quick)
        q_head.addWidget(q_title)
        q_head.addStretch()

        self.btn_add_phrase = PushButton(FluentIcon.ADD, tr("tts_btn_add_preset", "Добавить пресет"), self.card_quick)
        self.btn_add_phrase.setFixedHeight(32)
        self.btn_add_phrase.clicked.connect(self._prompt_add_phrase)
        q_head.addWidget(self.btn_add_phrase)
        self.q_layout.addLayout(q_head)

        hint = CaptionLabel(tr("tts_quick_hint", "Нажмите иконку отправки, чтобы мгновенно сказать в микрофон. Правый клик (ПКМ) — удалить пресет."), self.card_quick)
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
        if fx != "normal":
            for fid, fname in get_tts_fx_options():
                if fid == fx:
                    fx_badge = f"[{fname}] "
                    break

        text = preset.get("text", "")
        display_text = f"{fx_badge}{text}"

        # Main button to paste text and set voice
        btn_paste = PushButton(display_text, card)
        btn_paste.setFixedHeight(34)
        btn_paste.setStyleSheet("text-align: left; padding: 4px 8px; font-size: 12px; border: none; background: transparent;")
        btn_paste.setToolTip(tr("tts_paste_tooltip", "Вставить фразу и параметры в поле ввода"))
        btn_paste.clicked.connect(lambda checked, p=preset: self._apply_preset_to_editor(p))
        h_layout.addWidget(btn_paste, stretch=1)

        # Quick direct play to microphone button (⚡ without changing editor)
        btn_direct_mic = TransparentToolButton(FluentIcon.SEND, card)
        btn_direct_mic.setFixedSize(32, 32)
        btn_direct_mic.setToolTip(tr("tts_send_direct_tooltip", "Сразу сказать в микрофон (без вставки в поле)"))
        btn_direct_mic.clicked.connect(lambda checked, p=preset: self._play_preset_direct(p, play_mic=True))
        h_layout.addWidget(btn_direct_mic)

        # Quick preview button (🔊)
        btn_direct_prev = TransparentToolButton(FluentIcon.VOLUME, card)
        btn_direct_prev.setFixedSize(32, 32)
        btn_direct_prev.setToolTip(tr("tts_preview_tooltip", "Прослушать"))
        btn_direct_prev.clicked.connect(lambda checked, p=preset: self._play_preset_direct(p, play_mic=False))
        h_layout.addWidget(btn_direct_prev)

        return card

    def _show_phrase_menu(self, preset: Dict[str, Any], global_pos):
        if self._active_phrase_menu and self._active_phrase_menu.isVisible():
            return

        menu = RoundMenu(parent=self)
        self._active_phrase_menu = menu

        act_speak = Action(FluentIcon.SEND, tr("tts_act_speak", "Сказать в микрофон"), self)
        act_speak.triggered.connect(lambda: self._play_preset_direct(preset, play_mic=True))
        menu.addAction(act_speak)

        act_preview = Action(FluentIcon.VOLUME, tr("tts_act_preview", "Прослушать"), self)
        act_preview.triggered.connect(lambda: self._play_preset_direct(preset, play_mic=False))
        menu.addAction(act_preview)

        act_paste = Action(FluentIcon.PASTE, tr("tts_act_paste", "Вставить в поле ввода"), self)
        act_paste.triggered.connect(lambda: self._apply_preset_to_editor(preset))
        menu.addAction(act_paste)

        act_edit = Action(FluentIcon.EDIT, tr("tts_act_edit", "Редактировать пресет"), self)
        act_edit.triggered.connect(lambda: self._edit_preset(preset))
        menu.addAction(act_edit)

        menu.addSeparator()

        act_del = Action(FluentIcon.DELETE, tr("tts_act_delete", "Удалить пресет"), self)
        act_del.triggered.connect(lambda: self._delete_preset(preset))
        menu.addAction(act_del)

        menu.exec(global_pos)
        self._active_phrase_menu = None

    def _edit_preset(self, preset: Dict[str, Any]):
        dlg = TTSPresetDialog(self, preset=preset)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            p_id = preset.get("id")
            if p_id:
                self.cfg.update_tts_preset(p_id, data)
            else:
                preset.update(data)
                self.cfg.save_tts_presets()
            self._refresh_quick_phrases()
            self.lbl_status.setText(tr("tts_status_preset_updated", "Пресет обновлен: {text}...", text=data['text'][:20]))

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
        self.lbl_status.setText(tr("tts_status_generating_preset", "Генерация пресета «{text}...»", text=text[:18]))

        def on_done(samples: Optional[np.ndarray]):
            if samples is not None and len(samples) > 0:
                # Apply Voice Changer FX if configured on worker thread
                if fx != "normal":
                    try:
                        temp_fx = VoiceFXProcessor(sample_rate=self.engine.sample_rate)
                        temp_fx.set_preset(fx)
                        samples = temp_fx.process(samples)
                    except Exception as e:
                        print(f"[TTS] Error applying FX {fx}: {e}")

                self.sig_tts_direct_done.emit(samples, text, play_mic, play_monitor)
            else:
                self.sig_tts_error.emit(tr("tts_status_error", "Ошибка генерации речи"))

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
            self.lbl_status.setText(tr("tts_status_preset_added", "Добавлен новый пресет: {text}...", text=data['text'][:20]))

    def _delete_preset(self, preset: Dict[str, Any]):
        p_id = preset.get("id")
        p_text = preset.get("text", "")
        reply = QMessageBox.question(
            self,
            tr("tts_dlg_del_preset_title", "Удаление пресета"),
            tr("tts_dlg_del_preset_msg", "Вы уверены, что хотите удалить пресет «{text}»?", text=p_text),
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
            self.lbl_status.setText(tr("tts_status_preset_deleted", "Пресет удален"))

    def _on_rate_change(self, val: int):
        speed = 1.0 + (val / 100.0)
        self.lbl_rate.setText(f"{tr('tts_speed_label', 'Скорость речи:')} {speed:.2f}x")

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

        self.lbl_status.setText(tr("tts_status_generating", "Генерация нейросетью..."))
        self.btn_speak.setEnabled(False)
        self.btn_preview.setEnabled(False)

        def on_done(samples: np.ndarray):
            if samples is not None and len(samples) > 0:
                # Apply Voice FX if selected on worker thread
                if fx != "normal":
                    try:
                        temp_fx = VoiceFXProcessor(sample_rate=self.engine.sample_rate)
                        temp_fx.set_preset(fx)
                        samples = temp_fx.process(samples)
                    except Exception as e:
                        print(f"[TTS] FX error: {e}")

                self.sig_tts_synthesis_done.emit(samples, text, play_mic, play_monitor)
            else:
                self.sig_tts_error.emit(tr("tts_status_error", "Ошибка генерации речи"))

        self.tts.synthesize_async(text=text, voice=voice, rate=rate_str, callback=on_done)

    def _on_direct_done_main_thread(self, samples: np.ndarray, text: str, play_mic: bool, play_monitor: bool):
        self._is_synthesizing = False
        if play_mic and play_monitor:
            self.lbl_status.setText(tr("tts_status_playing_both", "Транслируется в микрофон и для себя: «{text}»", text=text[:20]))
        elif play_mic:
            self.lbl_status.setText(tr("tts_status_playing_mic", "Транслируется в микрофон: «{text}»", text=text[:20]))
        else:
            self.lbl_status.setText(tr("tts_status_playing_monitor", "Предпрослушивание: «{text}»", text=text[:20]))
        self.engine.play_tts_samples(samples, play_monitor=play_monitor, play_mic=play_mic)

    def _on_synthesis_done_main_thread(self, samples: np.ndarray, text: str, play_mic: bool, play_monitor: bool):
        self._is_synthesizing = False
        self.btn_speak.setEnabled(True)
        self.btn_preview.setEnabled(True)
        if play_mic and play_monitor:
            self.lbl_status.setText(tr("tts_status_playback_both", "Воспроизводится в микрофон и для себя"))
        elif play_mic:
            self.lbl_status.setText(tr("tts_status_playback_mic", "Воспроизводится в микрофон"))
        else:
            self.lbl_status.setText(tr("tts_status_playback_monitor", "Воспроизводится (предпрослушивание)"))
        self.engine.play_tts_samples(samples, play_monitor=play_monitor, play_mic=play_mic)

    def _on_error_main_thread(self, err_msg: str):
        self._is_synthesizing = False
        self.btn_speak.setEnabled(True)
        self.btn_preview.setEnabled(True)
        self.lbl_status.setText(err_msg)

    def _on_save_done_main_thread(self, filepath: str, short_title: str):
        self.lbl_status.setText(tr("tts_status_saved_sb", "Сохранено на Саундборд: {title}", title=short_title))
        self.sound_saved_to_board.emit(filepath, short_title)

    def _save_to_soundboard(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, tr("tts_warn_empty_title", "Внимание"), tr("tts_warn_empty_msg", "Введите текст для создания звука."))
            return

        voice = self.combo_voice.currentData() or "ru-RU-DmitryNeural"
        fx = self.combo_fx.currentData() or "normal"
        rate_val = self.slider_rate.value()
        rate_str = f"{'+' if rate_val >= 0 else ''}{rate_val}%"
        self.lbl_status.setText(tr("tts_status_file_gen", "Генерация аудиофайла..."))

        def on_done(samples: np.ndarray):
            if samples is None or len(samples) == 0:
                self.sig_tts_error.emit(tr("tts_status_file_err", "Ошибка создания аудиофайла"))
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
            self.sig_tts_save_done.emit(str(filepath), short_title)

        self.tts.synthesize_async(text=text, voice=voice, rate=rate_str, callback=on_done)

    def _load_target_devices(self):
        """Loads available audio output devices for target microphone into combo box."""
        saved_target = self.cfg.get("mic_target_device_id")
        self.engine.populate_target_mic_combobox(self.combo_target_mic, saved_target)

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
