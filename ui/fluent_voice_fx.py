"""
Fluent Design Voice FX & Microphone DSP Interface for SoundFlow Studio.
Features Windows 11 Fluent cards, full parametric manual DSP controls (pitch, EQ,
robot modulation, megaphone distortion, echo/delay), preset library, import/export,
and real-time monitoring.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QScrollArea, QFileDialog, QMessageBox, QDialog
)
from qfluentwidgets import (
    CardWidget, SwitchButton, Slider, TitleLabel, SubtitleLabel,
    BodyLabel, CaptionLabel, PushButton, PrimaryPushButton,
    FluentIcon, LineEdit, RoundMenu, Action
)

from .widgets import VUMeterWidget
from core.voice_fx import BUILTIN_PRESETS, DEFAULT_PARAMS


class SaveVoicePresetDialog(QDialog):
    """Dialog to enter a name for saving custom voice settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Сохранение пресета голоса")
        self.setFixedSize(380, 160)
        self.setStyleSheet("background-color: #202020; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel("Имя нового пресета", self))
        self.edit_name = LineEdit(self)
        self.edit_name.setPlaceholderText("Например: Мой зловещий голос")
        self.edit_name.setFixedHeight(34)
        layout.addWidget(self.edit_name)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = PushButton("Отмена", self)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = PrimaryPushButton(FluentIcon.SAVE, "Сохранить", self)
        btn_save.clicked.connect(self._validate)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _validate(self):
        if not self.edit_name.text().strip():
            QMessageBox.warning(self, "Внимание", "Пожалуйста, введите название пресета.")
            return
        self.accept()

    def get_name(self) -> str:
        return self.edit_name.text().strip()


class FluentVoiceFXInterface(QWidget):
    """Windows 11 Fluent Design Voice Changer & DSP Interface."""

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.setObjectName("voiceFxInterface")
        self.active_preset_id = "normal"
        self._updating_ui = False

        self._build_ui()

        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self._update_meters)
        self.meter_timer.start(33)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Scroll area for clean layout
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        # Header Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = TitleLabel("Микрофон и Voice Changer", container)
        lbl_sub = CaptionLabel(
            "Проброс микрофона с ручной настройкой тональности, тембра, модуляции и эффектов в реальном времени",
            container
        )
        lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        layout.addLayout(title_layout)

        # 1. Master Mic Passthrough Switch & Preview Card
        card_mic = CardWidget(container)
        m_layout = QVBoxLayout(card_mic)
        m_layout.setContentsMargins(20, 16, 20, 16)
        m_layout.setSpacing(12)

        sw_row = QHBoxLayout()
        sw_col = QVBoxLayout()
        sw_col.setSpacing(2)
        sw_title = SubtitleLabel("Включить микрофон в миксер", card_mic)
        sw_desc = CaptionLabel("Голос будет транслироваться вместе со звуками саундборда и радио в целевой микрофон", card_mic)
        sw_desc.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        sw_col.addWidget(sw_title)
        sw_col.addWidget(sw_desc)
        sw_row.addLayout(sw_col, stretch=1)

        self.switch_mic = SwitchButton(card_mic)
        self.switch_mic.setOnText("ВКЛ")
        self.switch_mic.setOffText("ВЫКЛ")
        self.switch_mic.checkedChanged.connect(self._on_mic_toggle)
        sw_row.addWidget(self.switch_mic)
        m_layout.addLayout(sw_row)

        # Live Preview ("Hear Myself")
        prev_row = QHBoxLayout()
        prev_col = QVBoxLayout()
        prev_col.setSpacing(2)
        prev_title = SubtitleLabel("🎧 Прослушать себя (Предпросмотр для себя)", card_mic)
        prev_desc = CaptionLabel("Вы услышите свой обработанный голос прямо в динамиках или наушниках в реальном времени", card_mic)
        prev_desc.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        prev_col.addWidget(prev_title)
        prev_col.addWidget(prev_desc)
        prev_row.addLayout(prev_col, stretch=1)

        self.switch_preview = SwitchButton(card_mic)
        self.switch_preview.setOnText("ВКЛ")
        self.switch_preview.setOffText("ВЫКЛ")
        self.switch_preview.checkedChanged.connect(self._on_preview_toggle)
        prev_row.addWidget(self.switch_preview)
        m_layout.addLayout(prev_row)

        vol_row = QHBoxLayout()
        self.lbl_prev_vol = BodyLabel("Громкость предпросмотра: 100%", card_mic)
        self.lbl_prev_vol.setFixedWidth(240)
        self.slider_prev_vol = Slider(Qt.Orientation.Horizontal, card_mic)
        self.slider_prev_vol.setRange(0, 150)
        self.slider_prev_vol.setValue(100)
        self.slider_prev_vol.valueChanged.connect(self._on_prev_vol_change)
        vol_row.addWidget(self.lbl_prev_vol)
        vol_row.addWidget(self.slider_prev_vol)
        m_layout.addLayout(vol_row)

        # VU meter
        self.vu_mic = VUMeterWidget(label="ВХОДНОЙ УРОВЕНЬ МИКРОФОНА", parent=card_mic)
        m_layout.addWidget(self.vu_mic)

        layout.addWidget(card_mic)

        # 2. Manual Controls Card (Sliders for every parameter)
        card_manual = CardWidget(container)
        man_layout = QVBoxLayout(card_manual)
        man_layout.setContentsMargins(20, 16, 20, 16)
        man_layout.setSpacing(14)

        man_title = SubtitleLabel("Ручная настройка параметров голоса (DSP)", card_manual)
        man_layout.addWidget(man_title)

        # --- A. Pitch Shift ---
        pitch_row = QHBoxLayout()
        self.lbl_pitch = BodyLabel("Тональность (Pitch): 0 полутонов (1.00x)", card_manual)
        self.lbl_pitch.setFixedWidth(280)
        self.slider_pitch = Slider(Qt.Orientation.Horizontal, card_manual)
        self.slider_pitch.setRange(-12, 12)
        self.slider_pitch.setValue(0)
        self.slider_pitch.valueChanged.connect(self._on_pitch_change)
        pitch_row.addWidget(self.lbl_pitch)
        pitch_row.addWidget(self.slider_pitch)
        man_layout.addLayout(pitch_row)

        # --- B. EQ (Bass & Treble) ---
        eq_row = QHBoxLayout()
        eq_row.setSpacing(16)

        # Bass
        b_col = QVBoxLayout()
        self.lbl_bass = BodyLabel("Низкие частоты (Бас): 0 dB", card_manual)
        self.slider_bass = Slider(Qt.Orientation.Horizontal, card_manual)
        self.slider_bass.setRange(-12, 12)
        self.slider_bass.setValue(0)
        self.slider_bass.valueChanged.connect(self._on_bass_change)
        b_col.addWidget(self.lbl_bass)
        b_col.addWidget(self.slider_bass)
        eq_row.addLayout(b_col, stretch=1)

        # Treble
        t_col = QVBoxLayout()
        self.lbl_treble = BodyLabel("Высокие частоты (Тембр): 0 dB", card_manual)
        self.slider_treble = Slider(Qt.Orientation.Horizontal, card_manual)
        self.slider_treble.setRange(-12, 12)
        self.slider_treble.setValue(0)
        self.slider_treble.valueChanged.connect(self._on_treble_change)
        t_col.addWidget(self.lbl_treble)
        t_col.addWidget(self.slider_treble)
        eq_row.addLayout(t_col, stretch=1)

        man_layout.addLayout(eq_row)

        # --- C. Robot Ring Modulator ---
        rob_row = QHBoxLayout()
        self.switch_robot = SwitchButton(card_manual)
        self.switch_robot.setOnText("ВКЛ")
        self.switch_robot.setOffText("ВЫКЛ")
        self.switch_robot.checkedChanged.connect(self._on_robot_toggle)
        rob_row.addWidget(self.switch_robot)

        self.lbl_robot_freq = BodyLabel("🤖 Частота модуляции робота: 75 Гц", card_manual)
        self.lbl_robot_freq.setFixedWidth(280)
        self.slider_robot_freq = Slider(Qt.Orientation.Horizontal, card_manual)
        self.slider_robot_freq.setRange(20, 300)
        self.slider_robot_freq.setValue(75)
        self.slider_robot_freq.valueChanged.connect(self._on_robot_freq_change)
        rob_row.addWidget(self.lbl_robot_freq)
        rob_row.addWidget(self.slider_robot_freq)
        man_layout.addLayout(rob_row)

        # --- D. Megaphone / Drive ---
        mega_row = QHBoxLayout()
        self.switch_mega = SwitchButton(card_manual)
        self.switch_mega.setOnText("ВКЛ")
        self.switch_mega.setOffText("ВЫКЛ")
        self.switch_mega.checkedChanged.connect(self._on_mega_toggle)
        mega_row.addWidget(self.switch_mega)

        self.lbl_mega_drive = BodyLabel("📢 Мегафон / Перегруз (Drive): 2.8x", card_manual)
        self.lbl_mega_drive.setFixedWidth(280)
        self.slider_mega_drive = Slider(Qt.Orientation.Horizontal, card_manual)
        self.slider_mega_drive.setRange(10, 50)
        self.slider_mega_drive.setValue(28)
        self.slider_mega_drive.valueChanged.connect(self._on_mega_drive_change)
        mega_row.addWidget(self.lbl_mega_drive)
        mega_row.addWidget(self.slider_mega_drive)
        man_layout.addLayout(mega_row)

        # --- E. Echo / Delay ---
        echo_row = QHBoxLayout()
        self.switch_echo = SwitchButton(card_manual)
        self.switch_echo.setOnText("ВКЛ")
        self.switch_echo.setOffText("ВЫКЛ")
        self.switch_echo.checkedChanged.connect(self._on_echo_toggle)
        echo_row.addWidget(self.switch_echo)

        self.lbl_echo_delay = BodyLabel("🌌 Задержка эхо: 250 мс", card_manual)
        self.lbl_echo_delay.setFixedWidth(220)
        self.slider_echo_delay = Slider(Qt.Orientation.Horizontal, card_manual)
        self.slider_echo_delay.setRange(50, 700)
        self.slider_echo_delay.setValue(250)
        self.slider_echo_delay.valueChanged.connect(self._on_echo_delay_change)
        echo_row.addWidget(self.lbl_echo_delay)
        echo_row.addWidget(self.slider_echo_delay)

        self.lbl_echo_feedback = BodyLabel("Затухание: 40%", card_manual)
        self.lbl_echo_feedback.setFixedWidth(120)
        self.slider_echo_feedback = Slider(Qt.Orientation.Horizontal, card_manual)
        self.slider_echo_feedback.setRange(0, 80)
        self.slider_echo_feedback.setValue(40)
        self.slider_echo_feedback.valueChanged.connect(self._on_echo_feedback_change)
        echo_row.addWidget(self.lbl_echo_feedback)
        echo_row.addWidget(self.slider_echo_feedback)
        man_layout.addLayout(echo_row)

        # --- F. Noise Gate ---
        gate_row = QHBoxLayout()
        self.lbl_gate = BodyLabel("Шумоподавитель (Noise Gate): -45 dB", card_manual)
        self.lbl_gate.setFixedWidth(280)
        self.slider_gate = Slider(Qt.Orientation.Horizontal, card_manual)
        self.slider_gate.setRange(-70, -15)
        self.slider_gate.setValue(-45)
        self.slider_gate.valueChanged.connect(self._on_gate_change)
        gate_row.addWidget(self.lbl_gate)
        gate_row.addWidget(self.slider_gate)
        man_layout.addLayout(gate_row)

        # --- Action Buttons Row ---
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        self.btn_reset = PushButton(FluentIcon.SYNC, "Сбросить в чистый голос", card_manual)
        self.btn_reset.setFixedHeight(36)
        self.btn_reset.clicked.connect(self._reset_to_clean)
        btn_bar.addWidget(self.btn_reset)

        self.btn_save_preset = PrimaryPushButton(FluentIcon.SAVE, "Сохранить как пресет...", card_manual)
        self.btn_save_preset.setFixedHeight(36)
        self.btn_save_preset.clicked.connect(self._prompt_save_preset)
        btn_bar.addWidget(self.btn_save_preset)

        self.btn_export = PushButton(FluentIcon.SHARE, "Экспорт в файл...", card_manual)
        self.btn_export.setFixedHeight(36)
        self.btn_export.clicked.connect(self._export_preset_file)
        btn_bar.addWidget(self.btn_export)

        self.btn_import = PushButton(FluentIcon.FOLDER, "Загрузить из файла...", card_manual)
        self.btn_import.setFixedHeight(36)
        self.btn_import.clicked.connect(self._import_preset_file)
        btn_bar.addWidget(self.btn_import)

        man_layout.addLayout(btn_bar)

        layout.addWidget(card_manual)

        # 3. Presets Library Card
        self.card_presets = CardWidget(container)
        self.p_layout = QVBoxLayout(self.card_presets)
        self.p_layout.setContentsMargins(20, 16, 20, 16)
        self.p_layout.setSpacing(12)

        p_head = QHBoxLayout()
        p_title = SubtitleLabel("Библиотека готовых пресетов", self.card_presets)
        p_head.addWidget(p_title)
        p_head.addStretch()
        self.p_layout.addLayout(p_head)

        p_hint = CaptionLabel("💡 Кликните по пресету для применения. Правый клик (ПКМ) на пользовательском пресете — удалить.", self.card_presets)
        p_hint.setStyleSheet("color: rgba(255, 255, 255, 0.45);")
        self.p_layout.addWidget(p_hint)

        self.presets_container = QWidget(self.card_presets)
        self.presets_grid = QGridLayout(self.presets_container)
        self.presets_grid.setContentsMargins(0, 0, 0, 0)
        self.presets_grid.setSpacing(10)
        self.p_layout.addWidget(self.presets_container)

        layout.addWidget(self.card_presets)
        layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

        self._refresh_presets_grid()

    # ---------------- UI & DSP Binding Handlers ----------------
    def _on_pitch_change(self, val: int):
        if self._updating_ui:
            return
        factor = 2.0 ** (val / 12.0)
        self.lbl_pitch.setText(f"Тональность (Pitch): {val:+d} полутонов ({factor:.2f}x)")
        self.engine.voice_fx.params["pitch_semitones"] = float(val)

    def _on_bass_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_bass.setText(f"Низкие частоты (Бас): {val:+d} dB")
        self.engine.voice_fx.params["eq_bass"] = float(val)

    def _on_treble_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_treble.setText(f"Высокие частоты (Тембр): {val:+d} dB")
        self.engine.voice_fx.params["eq_treble"] = float(val)

    def _on_robot_toggle(self, checked: bool):
        if self._updating_ui:
            return
        self.engine.voice_fx.params["robot_enabled"] = checked

    def _on_robot_freq_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_robot_freq.setText(f"🤖 Частота модуляции робота: {val} Гц")
        self.engine.voice_fx.params["robot_freq"] = float(val)

    def _on_mega_toggle(self, checked: bool):
        if self._updating_ui:
            return
        self.engine.voice_fx.params["megaphone_enabled"] = checked

    def _on_mega_drive_change(self, val: int):
        if self._updating_ui:
            return
        drive = val / 10.0
        self.lbl_mega_drive.setText(f"📢 Мегафон / Перегруз (Drive): {drive:.1f}x")
        self.engine.voice_fx.params["megaphone_drive"] = float(drive)

    def _on_echo_toggle(self, checked: bool):
        if self._updating_ui:
            return
        self.engine.voice_fx.params["echo_enabled"] = checked

    def _on_echo_delay_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_echo_delay.setText(f"🌌 Задержка эхо: {val} мс")
        self.engine.voice_fx.params["echo_delay_ms"] = float(val)

    def _on_echo_feedback_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_echo_feedback.setText(f"Затухание: {val}%")
        self.engine.voice_fx.params["echo_feedback"] = val / 100.0

    def _on_gate_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_gate.setText(f"Шумоподавитель (Noise Gate): {val} dB")
        self.engine.voice_fx.set_gate_threshold(float(val))

    def _on_mic_toggle(self, checked: bool):
        self.engine.mic_passthrough_enabled = checked
        if not checked and hasattr(self, 'switch_preview') and self.switch_preview.isChecked():
            self.switch_preview.setChecked(False)

    def _on_preview_toggle(self, checked: bool):
        if checked and not self.switch_mic.isChecked():
            self.switch_mic.setChecked(True)
        self.engine.mic_monitor_preview = checked

    def _on_prev_vol_change(self, val: int):
        self.lbl_prev_vol.setText(f"Громкость предпросмотра: {val}%")
        self.engine.mic_preview_volume = val / 100.0

    def _reset_to_clean(self):
        self.engine.voice_fx.reset_to_default()
        self.active_preset_id = "normal"
        self._sync_ui_from_dsp()
        self._update_preset_buttons_styling()

    def _sync_ui_from_dsp(self):
        self._updating_ui = True
        try:
            params = self.engine.voice_fx.get_params()

            pitch = int(round(params.get("pitch_semitones", 0.0)))
            self.slider_pitch.setValue(pitch)
            factor = 2.0 ** (pitch / 12.0)
            self.lbl_pitch.setText(f"Тональность (Pitch): {pitch:+d} полутонов ({factor:.2f}x)")

            bass = int(round(params.get("eq_bass", 0.0)))
            self.slider_bass.setValue(bass)
            self.lbl_bass.setText(f"Низкие частоты (Бас): {bass:+d} dB")

            treble = int(round(params.get("eq_treble", 0.0)))
            self.slider_treble.setValue(treble)
            self.lbl_treble.setText(f"Высокие частоты (Тембр): {treble:+d} dB")

            self.switch_robot.setChecked(bool(params.get("robot_enabled", False)))
            rf = int(round(params.get("robot_freq", 75.0)))
            self.slider_robot_freq.setValue(rf)
            self.lbl_robot_freq.setText(f"🤖 Частота модуляции робота: {rf} Гц")

            self.switch_mega.setChecked(bool(params.get("megaphone_enabled", False)))
            md = int(round(params.get("megaphone_drive", 2.8) * 10))
            self.slider_mega_drive.setValue(md)
            self.lbl_mega_drive.setText(f"📢 Мегафон / Перегруз (Drive): {md/10.0:.1f}x")

            self.switch_echo.setChecked(bool(params.get("echo_enabled", False)))
            ed = int(round(params.get("echo_delay_ms", 250.0)))
            self.slider_echo_delay.setValue(ed)
            self.lbl_echo_delay.setText(f"🌌 Задержка эхо: {ed} мс")

            ef = int(round(params.get("echo_feedback", 0.4) * 100))
            self.slider_echo_feedback.setValue(ef)
            self.lbl_echo_feedback.setText(f"Затухание: {ef}%")

            gate = int(round(params.get("gate_threshold_db", -45.0)))
            self.slider_gate.setValue(gate)
            self.lbl_gate.setText(f"Шумоподавитель (Noise Gate): {gate} dB")
        finally:
            self._updating_ui = False

    # ---------------- Presets Grid & Management ----------------
    def _refresh_presets_grid(self):
        while self.presets_grid.count():
            item = self.presets_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.preset_widgets = {}

        # 1. Built-in presets
        all_presets = []
        for pid, data in BUILTIN_PRESETS.items():
            all_presets.append({
                "id": pid,
                "name": data.get("name", pid),
                "desc": data.get("description", ""),
                "params": data,
                "custom": False
            })

        # 2. User presets
        for p in self.cfg.voice_presets:
            all_presets.append({
                "id": p.get("id"),
                "name": f"⭐ {p.get('name', 'Preset')}",
                "desc": "Пользовательский пресет",
                "params": p.get("params", {}),
                "custom": True
            })

        for idx, item in enumerate(all_presets):
            row = idx // 2
            col = idx % 2
            card = self._create_preset_card(item)
            self.presets_grid.addWidget(card, row, col)
            self.preset_widgets[item["id"]] = card

        self._update_preset_buttons_styling()

    def _create_preset_card(self, item: Dict[str, Any]) -> CardWidget:
        card = CardWidget(self.presets_container)
        card.setFixedHeight(56)
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos, it=item, c=card: self._show_preset_context_menu(it, c.mapToGlobal(pos)))

        h = QHBoxLayout(card)
        h.setContentsMargins(12, 6, 12, 6)
        h.setSpacing(8)

        info = QVBoxLayout()
        info.setSpacing(1)
        lbl_name = BodyLabel(item["name"], card)
        lbl_name.setStyleSheet("font-weight: 600; font-size: 13px;")
        lbl_desc = CaptionLabel(item["desc"], card)
        lbl_desc.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 11px;")
        info.addWidget(lbl_name)
        info.addWidget(lbl_desc)
        h.addLayout(info, stretch=1)

        btn_apply = PushButton(FluentIcon.PLAY, "Применить", card)
        btn_apply.setFixedHeight(32)
        btn_apply.clicked.connect(lambda checked, it=item: self._apply_preset_data(it))
        h.addWidget(btn_apply)

        return card

    def _apply_preset_data(self, item: Dict[str, Any]):
        self.active_preset_id = item["id"]
        params = item.get("params", {})
        self.engine.voice_fx.set_params(params)
        self._sync_ui_from_dsp()
        self._update_preset_buttons_styling()

    def _update_preset_buttons_styling(self):
        for pid, card in self.preset_widgets.items():
            if pid == self.active_preset_id:
                card.setStyleSheet("""
                    CardWidget {
                        background-color: rgba(0, 153, 255, 0.15);
                        border: 1.5px solid #0099ff;
                        border-radius: 6px;
                    }
                """)
            else:
                card.setStyleSheet("""
                    CardWidget {
                        background-color: rgba(255, 255, 255, 0.04);
                        border: 1px solid rgba(255, 255, 255, 0.07);
                        border-radius: 6px;
                    }
                    CardWidget:hover {
                        background-color: rgba(255, 255, 255, 0.07);
                    }
                """)

    def _show_preset_context_menu(self, item: Dict[str, Any], global_pos):
        menu = RoundMenu(parent=self)

        act_apply = Action(FluentIcon.PLAY, "Применить пресет", self)
        act_apply.triggered.connect(lambda: self._apply_preset_data(item))
        menu.addAction(act_apply)

        act_exp = Action(FluentIcon.SHARE, "Экспортировать в файл...", self)
        act_exp.triggered.connect(lambda: self._export_specific_preset(item))
        menu.addAction(act_exp)

        if item.get("custom", False):
            menu.addSeparator()
            act_del = Action(FluentIcon.DELETE, "Удалить пресет", self)
            act_del.triggered.connect(lambda: self._delete_voice_preset(item))
            menu.addAction(act_del)

        menu.exec(global_pos)

    def _prompt_save_preset(self):
        dlg = SaveVoicePresetDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.get_name()
            current_params = self.engine.voice_fx.get_params()
            new_p = self.cfg.add_voice_preset(name, current_params)
            self._refresh_presets_grid()
            if new_p:
                self._apply_preset_data({"id": new_p["id"], "params": new_p["params"]})
            QMessageBox.information(self, "Сохранено", f"Пресет «{name}» успешно сохранен в библиотеку.")

    def _delete_voice_preset(self, item: Dict[str, Any]):
        p_id = item.get("id")
        p_name = item.get("name", "")
        reply = QMessageBox.question(
            self,
            "Удаление пресета",
            f"Удалить пользовательский пресет «{p_name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cfg.remove_voice_preset(p_id)
            if self.active_preset_id == p_id:
                self._reset_to_clean()
            self._refresh_presets_grid()

    def _export_preset_file(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт настроек голоса в файл",
            "voice_preset.json",
            "JSON Presets (*.json)"
        )
        if file_path:
            try:
                params = self.engine.voice_fx.get_params()
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump({"name": "Custom Voice Preset", "params": params}, f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, "Успешно", "Пресет успешно экспортирован.")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать файл: {e}")

    def _export_specific_preset(self, item: Dict[str, Any]):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"Экспорт пресета {item['name']}",
            f"{item['id']}.json",
            "JSON Presets (*.json)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump({"name": item["name"], "params": item["params"]}, f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, "Успешно", "Пресет успешно сохранен в файл.")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать: {e}")

    def _import_preset_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Загрузить файл пресета голоса",
            "",
            "JSON Presets (*.json)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                params = data.get("params", data)
                name = data.get("name", Path(file_path).stem)

                # Save as custom preset
                new_p = self.cfg.add_voice_preset(name, params)
                self.engine.voice_fx.set_params(params)
                self._sync_ui_from_dsp()
                self._refresh_presets_grid()
                if new_p:
                    self.active_preset_id = new_p["id"]
                    self._update_preset_buttons_styling()
                QMessageBox.information(self, "Успешно", f"Пресет «{name}» успешно загружен и применен.")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать файл пресета: {e}")

    def _update_meters(self):
        peak = self.engine.mic_in_peak
        self.vu_mic.set_levels(peak, peak)
