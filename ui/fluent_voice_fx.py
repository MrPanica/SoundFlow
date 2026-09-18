"""
Fluent Design Voice FX & Microphone DSP Interface for SoundFlow Studio.
Features Windows 11 Fluent cards, full parametric manual DSP controls (pitch, EQ,
robot modulation, megaphone distortion, echo/delay), preset library, import/export,
and real-time monitoring.
"""

import json
import time
from pathlib import Path
from typing import Dict, Any, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QScrollArea, QFileDialog, QMessageBox, QDialog
)
from qfluentwidgets import (
    CardWidget, SwitchButton, Slider, TitleLabel, SubtitleLabel,
    BodyLabel, CaptionLabel, PushButton, PrimaryPushButton, TransparentPushButton,
    FluentIcon, LineEdit, RoundMenu, Action, ComboBox, InfoBar
)

from .widgets import VUMeterWidget
from core.voice_fx import BUILTIN_PRESETS, DEFAULT_PARAMS
from core.i18n import tr


class SaveVoicePresetDialog(QDialog):
    """Dialog to enter a name for saving custom voice settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("voice_fx_dlg_save_title", "Сохранение пресета голоса"))
        self.setFixedSize(380, 160)
        self.setStyleSheet("background-color: #202020; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel(tr("voice_fx_dlg_save_name", "Имя нового пресета"), self))
        self.edit_name = LineEdit(self)
        self.edit_name.setPlaceholderText(tr("voice_fx_dlg_save_placeholder", "Например: Мой зловещий голос"))
        self.edit_name.setFixedHeight(34)
        layout.addWidget(self.edit_name)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = PushButton(tr("common_cancel", "Отмена"), self)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = PrimaryPushButton(FluentIcon.SAVE, tr("common_save", "Сохранить"), self)
        btn_save.clicked.connect(self._validate)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _validate(self):
        if not self.edit_name.text().strip():
            QMessageBox.warning(self, tr("warning", "Внимание"), tr("voice_fx_dlg_save_warn", "Пожалуйста, введите название пресета."))
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
        self._populate_mic_devices()
        self._populate_target_devices()

        is_mic_enabled = self.cfg.get("mic_passthrough_enabled", True)
        self.engine.mic_passthrough_enabled = is_mic_enabled
        self.switch_mic.setChecked(is_mic_enabled)

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
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(18)

        # Header Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = TitleLabel(tr("voice_fx_title", "Микрофон и Voice Changer (FX)"), container)
        lbl_sub = CaptionLabel(tr("voice_fx_subtitle", "Преобразование голоса в реальном времени, пресеты и маршрутизация в микрофон"), container)
        lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        layout.addLayout(title_layout)

        # 1. Master Microphone Card
        card_mic = CardWidget(container)
        m_layout = QVBoxLayout(card_mic)
        m_layout.setContentsMargins(20, 16, 20, 16)
        m_layout.setSpacing(14)

        # Physical Input Mic row
        mic_dev_row = QHBoxLayout()
        mic_dev_col = QVBoxLayout()
        mic_dev_col.setSpacing(2)
        dev_title = SubtitleLabel(tr("voice_fx_in_mic_title", "Входной физический микрофон"), card_mic)
        dev_desc = CaptionLabel(tr("voice_fx_in_mic_desc", "Устройство захвата вашего реального голоса для обработки и трансляции"), card_mic)
        dev_desc.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        mic_dev_col.addWidget(dev_title)
        mic_dev_col.addWidget(dev_desc)
        mic_dev_row.addLayout(mic_dev_col, stretch=1)

        self.combo_mic = ComboBox(card_mic)
        self.combo_mic.setMinimumWidth(320)
        self.combo_mic.setFixedHeight(34)
        self.combo_mic.currentIndexChanged.connect(self._on_mic_device_selected)
        mic_dev_row.addWidget(self.combo_mic)
        m_layout.addLayout(mic_dev_row)

        # Target Mic (Output Cable) row
        mic_tgt_row = QHBoxLayout()
        mic_tgt_col = QVBoxLayout()
        mic_tgt_col.setSpacing(2)
        tgt_title = SubtitleLabel(tr("voice_fx_out_mic_title", "Выходной целевой микрофон"), card_mic)
        tgt_desc = CaptionLabel(tr("voice_fx_out_mic_desc", "Куда транслировать обработанный голос (виртуальный кабель, Discord, игры)"), card_mic)
        tgt_desc.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        mic_tgt_col.addWidget(tgt_title)
        mic_tgt_col.addWidget(tgt_desc)
        mic_tgt_row.addLayout(mic_tgt_col, stretch=1)

        self.combo_target_mic = ComboBox(card_mic)
        self.combo_target_mic.setMinimumWidth(320)
        self.combo_target_mic.setFixedHeight(34)
        self.combo_target_mic.currentIndexChanged.connect(self._on_target_mic_changed)
        mic_tgt_row.addWidget(self.combo_target_mic)
        m_layout.addLayout(mic_tgt_row)

        # Guidance banner and 1-click button for games / Discord
        guide_row = QHBoxLayout()
        guide_row.setSpacing(8)
        self.lbl_mic_guide = CaptionLabel(tr("radio_guide_label", "🎮 В игре / Discord выберите микрофон: CABLE Output (VB-Audio)"), card_mic)
        self.lbl_mic_guide.setStyleSheet("color: #38bdf8; font-weight: 500;")
        self.btn_set_default_mic = TransparentPushButton(FluentIcon.SETTING, tr("mic_set_default_btn", "Сделать микрофоном по умолчанию"), card_mic)
        self.btn_set_default_mic.setFixedHeight(28)
        self.btn_set_default_mic.clicked.connect(self._set_default_mic)
        guide_row.addWidget(self.lbl_mic_guide, stretch=1)
        guide_row.addWidget(self.btn_set_default_mic)
        self.update_default_mic_btn_state()
        m_layout.addLayout(guide_row)

        sw_row = QHBoxLayout()
        sw_col = QVBoxLayout()
        sw_col.setSpacing(2)
        sw_title = SubtitleLabel(tr("voice_fx_sw_mic_title", "Включить микрофон в миксер"), card_mic)
        sw_desc = CaptionLabel(tr("voice_fx_sw_mic_desc", "Голос будет транслироваться вместе со звуками саундборда и радио в целевой микрофон"), card_mic)
        sw_desc.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        sw_col.addWidget(sw_title)
        sw_col.addWidget(sw_desc)
        sw_row.addLayout(sw_col, stretch=1)

        self.switch_mic = SwitchButton(card_mic)
        self.switch_mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_mic.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.switch_mic.setOnText(tr("switch_on", "ВКЛ"))
        self.switch_mic.setOffText(tr("switch_off", "ВЫКЛ"))
        self.switch_mic.checkedChanged.connect(self._on_mic_toggle)
        sw_row.addWidget(self.switch_mic)
        m_layout.addLayout(sw_row)

        # Live Preview ("Hear Myself")
        prev_row = QHBoxLayout()
        prev_col = QVBoxLayout()
        prev_col.setSpacing(2)
        prev_title = SubtitleLabel(tr("voice_fx_prev_title", "Прослушать себя (Предпросмотр для себя)"), card_mic)
        prev_desc = CaptionLabel(tr("voice_fx_prev_desc", "Вы услышите свой обработанный голос прямо в динамиках или наушниках в реальном времени"), card_mic)
        prev_desc.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        prev_col.addWidget(prev_title)
        prev_col.addWidget(prev_desc)
        prev_row.addLayout(prev_col, stretch=1)

        self.switch_preview = SwitchButton(card_mic)
        self.switch_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch_preview.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.switch_preview.setOnText(tr("switch_on", "ВКЛ"))
        self.switch_preview.setOffText(tr("switch_off", "ВЫКЛ"))
        self.switch_preview.checkedChanged.connect(self._on_preview_toggle)
        prev_row.addWidget(self.switch_preview)
        m_layout.addLayout(prev_row)

        vol_row = QHBoxLayout()
        self.lbl_prev_vol = BodyLabel(tr("voice_fx_prev_vol", "Громкость предпросмотра: {vol}%").format(vol=100), card_mic)
        self.lbl_prev_vol.setFixedWidth(240)
        self.slider_prev_vol = Slider(Qt.Orientation.Horizontal, card_mic)
        self.slider_prev_vol.setRange(0, 150)
        self.slider_prev_vol.setValue(100)
        self.slider_prev_vol.valueChanged.connect(self._on_prev_vol_change)
        vol_row.addWidget(self.lbl_prev_vol)
        vol_row.addWidget(self.slider_prev_vol)
        m_layout.addLayout(vol_row)

        # VU meter
        self.vu_mic = VUMeterWidget(label=tr("voice_fx_vu_in", "ВХОДНОЙ УРОВЕНЬ МИКРОФОНА"), parent=card_mic)
        m_layout.addWidget(self.vu_mic)

        layout.addWidget(card_mic)

        # 1.1 Voice Recorder Card (Диктофон)
        card_rec = CardWidget(container)
        rec_layout = QVBoxLayout(card_rec)
        rec_layout.setContentsMargins(20, 16, 20, 16)
        rec_layout.setSpacing(12)

        rec_head = QHBoxLayout()
        rec_title_col = QVBoxLayout()
        rec_title_col.setSpacing(2)
        rec_title = SubtitleLabel(tr("recorder_card_title", "Диктофон (Запись голоса и эффектов)"), card_rec)
        rec_desc = CaptionLabel(tr("recorder_card_desc", "Запись вашего микрофона со всеми эффектами в аудиофайл"), card_rec)
        rec_desc.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        rec_title_col.addWidget(rec_title)
        rec_title_col.addWidget(rec_desc)
        rec_head.addLayout(rec_title_col, stretch=1)
        rec_layout.addLayout(rec_head)

        rec_ctrl_row = QHBoxLayout()
        rec_ctrl_row.setSpacing(14)

        self.btn_record = PrimaryPushButton(FluentIcon.MICROPHONE, tr("recorder_btn_start", "Начать запись"), card_rec)
        self.btn_record.setFixedHeight(38)
        self.btn_record.clicked.connect(self._toggle_recording)
        rec_ctrl_row.addWidget(self.btn_record)

        self.lbl_rec_timer = BodyLabel("00:00", card_rec)
        self.lbl_rec_timer.setStyleSheet("font-family: Consolas, monospace; font-size: 16px; font-weight: bold; color: #38bdf8;")
        rec_ctrl_row.addWidget(self.lbl_rec_timer)

        self.lbl_rec_status = CaptionLabel(tr("recorder_status_idle", "Готов к записи"), card_rec)
        self.lbl_rec_status.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        rec_ctrl_row.addWidget(self.lbl_rec_status, stretch=1)

        self.btn_open_rec_folder = TransparentPushButton(FluentIcon.FOLDER, tr("recorder_btn_open_folder", "Открыть папку с записями"), card_rec)
        self.btn_open_rec_folder.setFixedHeight(34)
        self.btn_open_rec_folder.clicked.connect(self._open_recordings_folder)
        rec_ctrl_row.addWidget(self.btn_open_rec_folder)

        rec_layout.addLayout(rec_ctrl_row)
        layout.addWidget(card_rec)

        # 2. Manual Controls Card (Collapsible, collapsed by default)
        card_manual = CardWidget(container)
        man_layout = QVBoxLayout(card_manual)
        man_layout.setContentsMargins(20, 16, 20, 16)
        man_layout.setSpacing(14)

        # Header with expand/collapse toggle
        man_head = QHBoxLayout()
        man_title_col = QVBoxLayout()
        man_title_col.setSpacing(2)
        man_title = SubtitleLabel(tr("voice_fx_manual_card_title", "Ручные параметры DSP и форманты"), card_manual)
        man_sub = CaptionLabel(tr("voice_fx_manual_card_subtitle", "Тонкая настройка высоты, голосового тракта (формант), фильтров и тембра"), card_manual)
        man_sub.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        man_title_col.addWidget(man_title)
        man_title_col.addWidget(man_sub)
        man_head.addLayout(man_title_col)
        man_head.addStretch()

        self.btn_toggle_manual = TransparentPushButton(FluentIcon.ARROW_DOWN, tr("voice_fx_btn_toggle_manual", "Ручная настройка DSP"), card_manual)
        self.btn_toggle_manual.setFixedHeight(34)
        self.btn_toggle_manual.clicked.connect(self._toggle_manual_card)
        man_head.addWidget(self.btn_toggle_manual)
        man_layout.addLayout(man_head)

        # Collapsible controls widget - collapsed by default!
        self.manual_controls_widget = QWidget(card_manual)
        self.manual_controls_widget.setVisible(False)
        mc_layout = QVBoxLayout(self.manual_controls_widget)
        mc_layout.setContentsMargins(0, 8, 0, 0)
        mc_layout.setSpacing(14)

        # --- A. Pitch Shift ---
        pitch_row = QHBoxLayout()
        self.lbl_pitch = BodyLabel(tr("voice_fx_pitch_label", "Тональность (Pitch): {val:+d} полутонов ({factor:.2f}x)").format(val=0, factor=1.0), self.manual_controls_widget)
        self.lbl_pitch.setFixedWidth(300)
        self.slider_pitch = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_pitch.setRange(-12, 12)
        self.slider_pitch.setValue(0)
        self.slider_pitch.valueChanged.connect(self._on_pitch_change)
        pitch_row.addWidget(self.lbl_pitch)
        pitch_row.addWidget(self.slider_pitch)
        mc_layout.addLayout(pitch_row)

        # --- B. Formant Shift (Vocal Tract Length) ---
        formant_col = QVBoxLayout()
        formant_col.setSpacing(3)
        formant_row = QHBoxLayout()
        self.lbl_formant = BodyLabel(tr("voice_fx_formant_title", "Форманты / Длина голосового тракта (VTL): {val}%").format(val=0), self.manual_controls_widget)
        self.lbl_formant.setFixedWidth(300)
        self.slider_formant = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_formant.setRange(-50, 50)
        self.slider_formant.setValue(0)
        self.slider_formant.valueChanged.connect(self._on_formant_change)
        formant_row.addWidget(self.lbl_formant)
        formant_row.addWidget(self.slider_formant)
        formant_col.addLayout(formant_row)
        lbl_formant_hint = CaptionLabel(tr("voice_fx_formant_hint", "Сдвиг резонансов гортани (женский +18..22%, детский +30..35%, мужской -12%)"), self.manual_controls_widget)
        lbl_formant_hint.setStyleSheet("color: rgba(255, 255, 255, 0.45);")
        formant_col.addWidget(lbl_formant_hint)
        mc_layout.addLayout(formant_col)

        # --- C. High-Pass Filter (HPF Chest Rumble Cut) ---
        hpf_col = QVBoxLayout()
        hpf_col.setSpacing(3)
        hpf_row = QHBoxLayout()
        self.lbl_hpf = BodyLabel(tr("voice_fx_hpf_title", "Срез низких частот / Грудной гул (HPF): {val} Гц").format(val=30), self.manual_controls_widget)
        self.lbl_hpf.setFixedWidth(300)
        self.slider_hpf = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_hpf.setRange(20, 350)
        self.slider_hpf.setValue(30)
        self.slider_hpf.valueChanged.connect(self._on_hpf_change)
        hpf_row.addWidget(self.lbl_hpf)
        hpf_row.addWidget(self.slider_hpf)
        hpf_col.addLayout(hpf_row)
        lbl_hpf_hint = CaptionLabel(tr("voice_fx_hpf_hint", "Срезает мужской грудной гул для естественного женского (160 Гц) или детского (220 Гц) голоса"), self.manual_controls_widget)
        lbl_hpf_hint.setStyleSheet("color: rgba(255, 255, 255, 0.45);")
        hpf_col.addWidget(lbl_hpf_hint)
        mc_layout.addLayout(hpf_col)

        # --- D. Vocal Air & Tone EQ (Bass, Treble, Air) ---
        eq_row = QHBoxLayout()
        eq_row.setSpacing(16)

        b_col = QVBoxLayout()
        self.lbl_bass = BodyLabel(tr("voice_fx_bass_label", "Низкие частоты (Бас): {val:+d} dB").format(val=0), self.manual_controls_widget)
        self.slider_bass = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_bass.setRange(-12, 12)
        self.slider_bass.setValue(0)
        self.slider_bass.valueChanged.connect(self._on_bass_change)
        b_col.addWidget(self.lbl_bass)
        b_col.addWidget(self.slider_bass)
        eq_row.addLayout(b_col, stretch=1)

        t_col = QVBoxLayout()
        self.lbl_treble = BodyLabel(tr("voice_fx_treble_label", "Высокие частоты (Тембр): {val:+d} dB").format(val=0), self.manual_controls_widget)
        self.slider_treble = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_treble.setRange(-12, 12)
        self.slider_treble.setValue(0)
        self.slider_treble.valueChanged.connect(self._on_treble_change)
        t_col.addWidget(self.lbl_treble)
        t_col.addWidget(self.slider_treble)
        eq_row.addLayout(t_col, stretch=1)

        air_col = QVBoxLayout()
        self.lbl_air = BodyLabel(tr("voice_fx_air_title", "Воздушность / Air: {val} дБ").format(val=0), self.manual_controls_widget)
        self.slider_air = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_air.setRange(-12, 12)
        self.slider_air.setValue(0)
        self.slider_air.valueChanged.connect(self._on_air_change)
        air_col.addWidget(self.lbl_air)
        air_col.addWidget(self.slider_air)
        eq_row.addLayout(air_col, stretch=1)

        mc_layout.addLayout(eq_row)

        # --- E. Grain Size / Smoothness ---
        grain_row = QHBoxLayout()
        self.lbl_grain = BodyLabel(tr("voice_fx_smoothness_title", "Размер гранул (Smoothness): {val} семплов").format(val=1024), self.manual_controls_widget)
        self.lbl_grain.setFixedWidth(300)
        self.slider_grain = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_grain.setRange(512, 2048)
        self.slider_grain.setValue(1024)
        self.slider_grain.valueChanged.connect(self._on_grain_change)
        grain_row.addWidget(self.lbl_grain)
        grain_row.addWidget(self.slider_grain)
        mc_layout.addLayout(grain_row)

        # --- F. Robot Ring Modulator ---
        rob_row = QHBoxLayout()
        self.switch_robot = SwitchButton(self.manual_controls_widget)
        self.switch_robot.setOnText(tr("switch_on", "ВКЛ"))
        self.switch_robot.setOffText(tr("switch_off", "ВЫКЛ"))
        self.switch_robot.checkedChanged.connect(self._on_robot_toggle)
        rob_row.addWidget(self.switch_robot)

        self.lbl_robot_freq = BodyLabel(tr("voice_fx_robot_freq_label", "Частота модуляции робота: {val} Гц").format(val=75), self.manual_controls_widget)
        self.lbl_robot_freq.setFixedWidth(280)
        self.slider_robot_freq = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_robot_freq.setRange(20, 300)
        self.slider_robot_freq.setValue(75)
        self.slider_robot_freq.valueChanged.connect(self._on_robot_freq_change)
        rob_row.addWidget(self.lbl_robot_freq)
        rob_row.addWidget(self.slider_robot_freq)
        mc_layout.addLayout(rob_row)

        # --- G. Megaphone / Drive ---
        mega_row = QHBoxLayout()
        self.switch_mega = SwitchButton(self.manual_controls_widget)
        self.switch_mega.setOnText(tr("switch_on", "ВКЛ"))
        self.switch_mega.setOffText(tr("switch_off", "ВЫКЛ"))
        self.switch_mega.checkedChanged.connect(self._on_mega_toggle)
        mega_row.addWidget(self.switch_mega)

        self.lbl_mega_drive = BodyLabel(tr("voice_fx_mega_drive_label", "Мегафон / Перегруз (Drive): {drive:.1f}x").format(drive=2.8), self.manual_controls_widget)
        self.lbl_mega_drive.setFixedWidth(280)
        self.slider_mega_drive = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_mega_drive.setRange(10, 50)
        self.slider_mega_drive.setValue(28)
        self.slider_mega_drive.valueChanged.connect(self._on_mega_drive_change)
        mega_row.addWidget(self.lbl_mega_drive)
        mega_row.addWidget(self.slider_mega_drive)
        mc_layout.addLayout(mega_row)

        # --- H. Echo / Delay ---
        echo_row = QHBoxLayout()
        self.switch_echo = SwitchButton(self.manual_controls_widget)
        self.switch_echo.setOnText(tr("switch_on", "ВКЛ"))
        self.switch_echo.setOffText(tr("switch_off", "ВЫКЛ"))
        self.switch_echo.checkedChanged.connect(self._on_echo_toggle)
        echo_row.addWidget(self.switch_echo)

        self.lbl_echo_delay = BodyLabel(tr("voice_fx_echo_delay_label", "Задержка эхо: {val} мс").format(val=250), self.manual_controls_widget)
        self.lbl_echo_delay.setFixedWidth(220)
        self.slider_echo_delay = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_echo_delay.setRange(50, 700)
        self.slider_echo_delay.setValue(250)
        self.slider_echo_delay.valueChanged.connect(self._on_echo_delay_change)
        echo_row.addWidget(self.lbl_echo_delay)
        echo_row.addWidget(self.slider_echo_delay)

        self.lbl_echo_feedback = BodyLabel(tr("voice_fx_echo_feedback_label", "Затухание: {val}%").format(val=40), self.manual_controls_widget)
        self.lbl_echo_feedback.setFixedWidth(120)
        self.slider_echo_feedback = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_echo_feedback.setRange(0, 80)
        self.slider_echo_feedback.setValue(40)
        self.slider_echo_feedback.valueChanged.connect(self._on_echo_feedback_change)
        echo_row.addWidget(self.lbl_echo_feedback)
        echo_row.addWidget(self.slider_echo_feedback)
        mc_layout.addLayout(echo_row)

        # --- I. Noise Gate ---
        gate_row = QHBoxLayout()
        self.switch_gate = SwitchButton(self.manual_controls_widget)
        self.switch_gate.setOnText(tr("switch_on", "ВКЛ"))
        self.switch_gate.setOffText(tr("switch_off", "ВЫКЛ"))
        self.switch_gate.checkedChanged.connect(self._on_gate_toggle)
        gate_row.addWidget(self.switch_gate)

        self.lbl_gate = BodyLabel(tr("voice_fx_gate_label", "Шумоподавитель (Noise Gate): {val} dB").format(val=-55), self.manual_controls_widget)
        self.lbl_gate.setFixedWidth(280)
        self.slider_gate = Slider(Qt.Orientation.Horizontal, self.manual_controls_widget)
        self.slider_gate.setRange(-70, -15)
        self.slider_gate.setValue(-55)
        self.slider_gate.valueChanged.connect(self._on_gate_change)
        gate_row.addWidget(self.lbl_gate)
        gate_row.addWidget(self.slider_gate)
        mc_layout.addLayout(gate_row)

        # --- Action Buttons Row ---
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        self.btn_reset = PushButton(FluentIcon.SYNC, tr("voice_fx_btn_reset", "Сбросить в чистый голос"), self.manual_controls_widget)
        self.btn_reset.setFixedHeight(36)
        self.btn_reset.clicked.connect(self._reset_to_clean)
        btn_bar.addWidget(self.btn_reset)

        self.btn_save_preset = PrimaryPushButton(FluentIcon.SAVE, tr("voice_fx_btn_save_preset", "Сохранить как пресет..."), self.manual_controls_widget)
        self.btn_save_preset.setFixedHeight(36)
        self.btn_save_preset.clicked.connect(self._prompt_save_preset)
        btn_bar.addWidget(self.btn_save_preset)

        self.btn_export = PushButton(FluentIcon.SHARE, tr("voice_fx_export_btn", "Экспорт в файл..."), self.manual_controls_widget)
        self.btn_export.setFixedHeight(36)
        self.btn_export.clicked.connect(self._export_preset_file)
        btn_bar.addWidget(self.btn_export)

        self.btn_import = PushButton(FluentIcon.FOLDER, tr("voice_fx_import_btn", "Загрузить из файла..."), self.manual_controls_widget)
        self.btn_import.setFixedHeight(36)
        self.btn_import.clicked.connect(self._import_preset_file)
        btn_bar.addWidget(self.btn_import)

        mc_layout.addLayout(btn_bar)

        man_layout.addWidget(self.manual_controls_widget)
        layout.addWidget(card_manual)

        # 3. Presets Library Card
        self.card_presets = CardWidget(container)
        self.p_layout = QVBoxLayout(self.card_presets)
        self.p_layout.setContentsMargins(20, 16, 20, 16)
        self.p_layout.setSpacing(12)

        p_head = QHBoxLayout()
        p_title = SubtitleLabel(tr("voice_fx_library_title", "Библиотека готовых пресетов"), self.card_presets)
        p_head.addWidget(p_title)
        p_head.addStretch()
        self.p_layout.addLayout(p_head)

        p_hint = CaptionLabel(tr("voice_fx_library_hint", "Кликните по пресету для применения. Правый клик (ПКМ) на пользовательском пресете — удалить."), self.card_presets)
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
    def _toggle_manual_card(self):
        vis = not self.manual_controls_widget.isVisible()
        self.manual_controls_widget.setVisible(vis)
        self.btn_toggle_manual.setIcon(FluentIcon.ARROW_UP if vis else FluentIcon.ARROW_DOWN)

    def _on_formant_change(self, val: int):
        if self._updating_ui:
            return
        tpl = tr("voice_fx_formant_title", "Форманты / Длина голосового тракта (VTL): {val}%")
        self.lbl_formant.setText(tpl.format(val=f"{val:+d}"))
        self.engine.voice_fx.params["formant_shift"] = val / 100.0

    def _on_hpf_change(self, val: int):
        if self._updating_ui:
            return
        tpl = tr("voice_fx_hpf_title", "Срез низких частот / Грудной гул (HPF): {val} Гц")
        self.lbl_hpf.setText(tpl.format(val=val))
        self.engine.voice_fx.params["hpf_cutoff_hz"] = float(val)

    def _on_air_change(self, val: int):
        if self._updating_ui:
            return
        tpl = tr("voice_fx_air_title", "Воздушность / Air: {val} дБ")
        self.lbl_air.setText(tpl.format(val=f"{val:+d}"))
        self.engine.voice_fx.params["air_presence"] = float(val)

    def _on_grain_change(self, val: int):
        if self._updating_ui:
            return
        tpl = tr("voice_fx_smoothness_title", "Размер гранул (Smoothness): {val} семплов")
        self.lbl_grain.setText(tpl.format(val=val))
        self.engine.voice_fx.params["grain_size"] = int(val)

    def _on_pitch_change(self, val: int):
        if self._updating_ui:
            return
        factor = 2.0 ** (val / 12.0)
        self.lbl_pitch.setText(tr("voice_fx_pitch_label", "Тональность (Pitch): {val:+d} полутонов ({factor:.2f}x)").format(val=val, factor=factor))
        self.engine.voice_fx.params["pitch_semitones"] = float(val)

    def _on_bass_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_bass.setText(tr("voice_fx_bass_label", "Низкие частоты (Бас): {val:+d} dB").format(val=val))
        self.engine.voice_fx.params["eq_bass"] = float(val)

    def _on_treble_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_treble.setText(tr("voice_fx_treble_label", "Высокие частоты (Тембр): {val:+d} dB").format(val=val))
        self.engine.voice_fx.params["eq_treble"] = float(val)

    def _on_robot_toggle(self, checked: bool):
        if self._updating_ui:
            return
        self.engine.voice_fx.params["robot_enabled"] = checked

    def _on_robot_freq_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_robot_freq.setText(tr("voice_fx_robot_freq_label", "Частота модуляции робота: {val} Гц").format(val=val))
        self.engine.voice_fx.params["robot_freq"] = float(val)

    def _on_mega_toggle(self, checked: bool):
        if self._updating_ui:
            return
        self.engine.voice_fx.params["megaphone_enabled"] = checked

    def _on_mega_drive_change(self, val: int):
        if self._updating_ui:
            return
        drive = val / 10.0
        self.lbl_mega_drive.setText(tr("voice_fx_mega_drive_label", "Мегафон / Перегруз (Drive): {drive:.1f}x").format(drive=drive))
        self.engine.voice_fx.params["megaphone_drive"] = float(drive)

    def _on_echo_toggle(self, checked: bool):
        if self._updating_ui:
            return
        self.engine.voice_fx.params["echo_enabled"] = checked

    def _on_echo_delay_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_echo_delay.setText(tr("voice_fx_echo_delay_label", "Задержка эхо: {val} мс").format(val=val))
        self.engine.voice_fx.params["echo_delay_ms"] = float(val)

    def _on_echo_feedback_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_echo_feedback.setText(tr("voice_fx_echo_feedback_label", "Затухание: {val}%").format(val=val))
        self.engine.voice_fx.params["echo_feedback"] = val / 100.0

    def _on_gate_toggle(self, checked: bool):
        if self._updating_ui:
            return
        self.engine.voice_fx.params["gate_enabled"] = checked

    def _on_gate_change(self, val: int):
        if self._updating_ui:
            return
        self.lbl_gate.setText(tr("voice_fx_gate_label", "Шумоподавитель (Noise Gate): {val} dB").format(val=val))
        self.engine.voice_fx.set_gate_threshold(float(val))

    def _populate_mic_devices(self):
        self._updating_ui = True
        try:
            self.combo_mic.clear()
            devs = self.engine.get_audio_devices()
            inputs = devs.get("inputs", [])

            selected_idx = 0
            curr_dev = self.engine.mic_input_device_id or self.cfg.get("mic_input_device_id")

            for idx, d in enumerate(inputs):
                self.combo_mic.addItem(d["name"], userData=d["id"])
                if curr_dev is not None and d["id"] == curr_dev:
                    selected_idx = idx

            if inputs:
                self.combo_mic.setCurrentIndex(selected_idx)
                chosen_id = self.combo_mic.itemData(selected_idx)
                if self.engine.mic_input_device_id != chosen_id or not self.engine.mic_input_stream:
                    self.engine.start_mic_input(chosen_id)
                    self.cfg.set("mic_input_device_id", chosen_id)
            else:
                self.combo_mic.addItem(tr("voice_fx_no_mics", "-- Микрофоны не найдены --"), userData=None)
        finally:
            self._updating_ui = False

    def _populate_target_devices(self):
        self._updating_ui = True
        try:
            saved_target = self.cfg.get("mic_target_device_id")
            self.engine.populate_target_mic_combobox(self.combo_target_mic, saved_target)
        finally:
            self._updating_ui = False

    def update_default_mic_btn_state(self, is_cable: Optional[bool] = None):
        """Updates button label and icon based on whether CABLE Output is Windows default mic."""
        if not hasattr(self, "btn_set_default_mic"):
            return
        from core.driver_manager import DriverManager
        if is_cable is None:
            is_cable = DriverManager.is_cable_output_default()
        if is_cable:
            self.btn_set_default_mic.setText(tr("mic_restore_default_btn", "Вернуть стандартный микрофон"))
            self.btn_set_default_mic.setIcon(FluentIcon.RETURN)
        else:
            self.btn_set_default_mic.setText(tr("mic_set_default_btn", "Сделать микрофоном по умолчанию"))
            self.btn_set_default_mic.setIcon(FluentIcon.SETTING)

    def showEvent(self, event):
        super().showEvent(event)
        self.update_default_mic_btn_state()

    def _set_default_mic(self):
        main_win = self.window()
        if hasattr(main_win, "toggle_default_recording_device"):
            main_win.toggle_default_recording_device(parent_widget=self)
        else:
            from core.driver_manager import DriverManager
            is_cable = DriverManager.is_cable_output_default()
            if is_cable:
                DriverManager.restore_physical_recording_device()
            else:
                DriverManager.set_default_recording_device_to_cable()
                self.engine.mic_passthrough_enabled = True
                self.cfg.set("mic_passthrough_enabled", True)
                if not self.engine.mic_input_stream or not self.engine.mic_input_stream.active:
                    self.engine.start_mic_input()
            self.update_default_mic_btn_state()

    def _on_target_mic_changed(self, idx: int):
        if self._updating_ui:
            return
        dev_id = self.combo_target_mic.itemData(idx)
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

    def _on_mic_device_selected(self, idx: int):
        if self._updating_ui:
            return
        dev_id = self.combo_mic.currentData()
        if dev_id is not None:
            self.cfg.set("mic_input_device_id", dev_id)
            self.engine.start_mic_input(dev_id)

    def _on_mic_toggle(self, checked: bool):
        self.engine.mic_passthrough_enabled = checked
        self.cfg.set("mic_passthrough_enabled", checked)
        main_win = self.window()
        if hasattr(main_win, "sync_global_mic_switch"):
            main_win.sync_global_mic_switch(checked)
        if checked:
            if not self.engine.mic_input_stream or not self.engine.mic_input_stream.active:
                dev_id = self.combo_mic.currentData() if hasattr(self, 'combo_mic') else None
                self.engine.start_mic_input(dev_id)
        else:
            if hasattr(self, 'switch_preview') and self.switch_preview.isChecked():
                self.switch_preview.setChecked(False)

    def _on_preview_toggle(self, checked: bool):
        if checked:
            if not self.switch_mic.isChecked():
                self.switch_mic.setChecked(True)
            if not self.engine.mic_input_stream or not self.engine.mic_input_stream.active:
                dev_id = self.combo_mic.currentData() if hasattr(self, 'combo_mic') else None
                self.engine.start_mic_input(dev_id)
        self.engine.mic_monitor_preview = checked

    def _on_prev_vol_change(self, val: int):
        self.lbl_prev_vol.setText(tr("voice_fx_prev_vol", "Громкость предпросмотра: {vol}%").format(vol=val))
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
            self.lbl_pitch.setText(tr("voice_fx_pitch_label", "Тональность (Pitch): {val:+d} полутонов ({factor:.2f}x)").format(val=pitch, factor=factor))

            formant_val = int(round(params.get("formant_shift", 0.0) * 100))
            self.slider_formant.setValue(formant_val)
            tpl_f = tr("voice_fx_formant_title", "Форманты / Длина голосового тракта (VTL): {val}%")
            self.lbl_formant.setText(tpl_f.format(val=f"{formant_val:+d}"))

            hpf_val = int(round(params.get("hpf_cutoff_hz", 30.0)))
            self.slider_hpf.setValue(hpf_val)
            tpl_h = tr("voice_fx_hpf_title", "Срез низких частот / Грудной гул (HPF): {val} Гц")
            self.lbl_hpf.setText(tpl_h.format(val=hpf_val))

            air_val = int(round(params.get("air_presence", 0.0)))
            self.slider_air.setValue(air_val)
            tpl_a = tr("voice_fx_air_title", "Воздушность / Air: {val} дБ")
            self.lbl_air.setText(tpl_a.format(val=f"{air_val:+d}"))

            grain_val = int(round(params.get("grain_size", 1024)))
            self.slider_grain.setValue(grain_val)
            tpl_g = tr("voice_fx_smoothness_title", "Размер гранул (Smoothness): {val} семплов")
            self.lbl_grain.setText(tpl_g.format(val=grain_val))

            bass = int(round(params.get("eq_bass", 0.0)))
            self.slider_bass.setValue(bass)
            self.lbl_bass.setText(tr("voice_fx_bass_label", "Низкие частоты (Бас): {val:+d} dB").format(val=bass))

            treble = int(round(params.get("eq_treble", 0.0)))
            self.slider_treble.setValue(treble)
            self.lbl_treble.setText(tr("voice_fx_treble_label", "Высокие частоты (Тембр): {val:+d} dB").format(val=treble))

            self.switch_robot.setChecked(bool(params.get("robot_enabled", False)))
            rf = int(round(params.get("robot_freq", 75.0)))
            self.slider_robot_freq.setValue(rf)
            self.lbl_robot_freq.setText(tr("voice_fx_robot_freq_label", "Частота модуляции робота: {val} Гц").format(val=rf))

            self.switch_mega.setChecked(bool(params.get("megaphone_enabled", False)))
            md = int(round(params.get("megaphone_drive", 2.8) * 10))
            self.slider_mega_drive.setValue(md)
            self.lbl_mega_drive.setText(tr("voice_fx_mega_drive_label", "Мегафон / Перегруз (Drive): {drive:.1f}x").format(drive=md/10.0))

            self.switch_echo.setChecked(bool(params.get("echo_enabled", False)))
            ed = int(round(params.get("echo_delay_ms", 250.0)))
            self.slider_echo_delay.setValue(ed)
            self.lbl_echo_delay.setText(tr("voice_fx_echo_delay_label", "Задержка эхо: {val} мс").format(val=ed))

            ef = int(round(params.get("echo_feedback", 0.4) * 100))
            self.slider_echo_feedback.setValue(ef)
            self.lbl_echo_feedback.setText(tr("voice_fx_echo_feedback_label", "Затухание: {val}%").format(val=ef))

            self.switch_gate.setChecked(bool(params.get("gate_enabled", False)))
            gate = int(round(params.get("gate_threshold_db", -55.0)))
            self.slider_gate.setValue(gate)
            self.lbl_gate.setText(tr("voice_fx_gate_label", "Шумоподавитель (Noise Gate): {val} dB").format(val=gate))
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
            name = tr(f"preset_{pid}_name", data.get("name", pid))
            desc = tr(f"preset_{pid}_desc", data.get("description", ""))
            all_presets.append({
                "id": pid,
                "name": name,
                "desc": desc,
                "params": data,
                "custom": False
            })

        # 2. User presets
        for p in self.cfg.voice_presets:
            all_presets.append({
                "id": p.get("id"),
                "name": p.get('name', 'Preset'),
                "desc": tr("voice_fx_user_preset_desc", "Пользовательский пресет"),
                "params": p.get("params", {}),
                "custom": True
            })

        cols = 3
        for idx, item in enumerate(all_presets):
            row = idx // cols
            col = idx % cols
            card = self._create_preset_card(item)
            self.presets_grid.addWidget(card, row, col)
            self.preset_widgets[item["id"]] = card

        self._update_preset_buttons_styling()

    def _create_preset_card(self, item: Dict[str, Any]) -> CardWidget:
        card = CardWidget(self.presets_container)
        card.setFixedHeight(58)
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos, it=item, c=card: self._show_preset_context_menu(it, c.mapToGlobal(pos)))
        card.mousePressEvent = lambda e, it=item: (self._apply_preset_data(it), e.accept()) if e.button() == Qt.MouseButton.LeftButton else CardWidget.mousePressEvent(card, e)

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

        btn_apply = PushButton(FluentIcon.PLAY, tr("apply", "Применить"), card)
        btn_apply.setFixedHeight(30)
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

        act_apply = Action(FluentIcon.PLAY, tr("voice_fx_apply_preset", "Применить пресет"), self)
        act_apply.triggered.connect(lambda: self._apply_preset_data(item))
        menu.addAction(act_apply)

        act_exp = Action(FluentIcon.SHARE, tr("voice_fx_export_btn", "Экспортировать в файл..."), self)
        act_exp.triggered.connect(lambda: self._export_specific_preset(item))
        menu.addAction(act_exp)

        if item.get("custom", False):
            menu.addSeparator()
            act_del = Action(FluentIcon.DELETE, tr("voice_fx_delete_preset", "Удалить пресет"), self)
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
            QMessageBox.information(self, tr("voice_fx_saved_title", "Сохранено"), tr("voice_fx_saved_msg", "Пресет «{name}» успешно сохранен в библиотеку.").format(name=name))

    def _delete_voice_preset(self, item: Dict[str, Any]):
        p_id = item.get("id")
        p_name = item.get("name", "")
        reply = QMessageBox.question(
            self,
            tr("voice_fx_del_preset_title", "Удаление пресета"),
            tr("voice_fx_del_preset_msg", "Удалить пользовательский пресет «{name}»?").format(name=p_name),
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
            tr("voice_fx_dlg_export_title", "Экспорт настроек голоса в файл"),
            "voice_preset.json",
            "JSON Presets (*.json)"
        )
        if file_path:
            try:
                params = self.engine.voice_fx.get_params()
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump({"name": "Custom Voice Preset", "params": params}, f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, tr("voice_fx_saved_title", "Успешно"), tr("voice_fx_export_success", "Пресет успешно экспортирован."))
            except Exception as e:
                QMessageBox.critical(self, tr("error", "Ошибка"), f"Не удалось экспортировать файл: {e}")

    def _export_specific_preset(self, item: Dict[str, Any]):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            f"{tr('voice_fx_dlg_export_title', 'Экспорт пресета')} {item['name']}",
            f"{item['id']}.json",
            "JSON Presets (*.json)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump({"name": item["name"], "params": item["params"]}, f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, tr("voice_fx_saved_title", "Успешно"), tr("voice_fx_export_success", "Пресет успешно сохранен в файл."))
            except Exception as e:
                QMessageBox.critical(self, tr("error", "Ошибка"), f"Не удалось экспортировать: {e}")

    def _import_preset_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("voice_fx_dlg_import_title", "Загрузить файл пресета голоса"),
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
                QMessageBox.information(self, tr("voice_fx_saved_title", "Успешно"), tr("voice_fx_import_success", "Пресет «{name}» успешно загружен и применен.").format(name=name))
            except Exception as e:
                QMessageBox.critical(self, tr("error", "Ошибка"), f"Не удалось прочитать файл пресета: {e}")

    # ---------------- Voice Recorder Handlers ----------------
    def _toggle_recording(self):
        if not getattr(self.engine, "mic_recording_active", False):
            self._start_voice_recording()
        else:
            self._stop_voice_recording()

    def _start_voice_recording(self):
        self.engine.start_mic_recording()
        self.btn_record.setText(tr("recorder_btn_stop", "Остановить запись"))
        self.btn_record.setIcon(FluentIcon.PAUSE)
        self.btn_record.setStyleSheet("PrimaryPushButton { background-color: #ef4444; border-color: #dc2626; }")
        self.lbl_rec_status.setText(tr("recorder_status_recording", "Идёт запись... [{time}]").format(time="00:00"))
        self.lbl_rec_timer.setText("00:00")
        if not hasattr(self, "_rec_timer"):
            self._rec_timer = QTimer(self)
            self._rec_timer.timeout.connect(self._update_rec_timer)
        self._rec_timer.start(100)

    def _update_rec_timer(self):
        if getattr(self.engine, "mic_recording_active", False):
            dur = int(self.engine.get_mic_recording_duration())
            mins = dur // 60
            secs = dur % 60
            t_str = f"{mins:02d}:{secs:02d}"
            self.lbl_rec_timer.setText(t_str)
            self.lbl_rec_status.setText(tr("recorder_status_recording", "Идёт запись... [{time}]").format(time=t_str))

    def _stop_voice_recording(self):
        if hasattr(self, "_rec_timer"):
            self._rec_timer.stop()
        rec_dir = self.cfg.get_recordings_dir()
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_file = rec_dir / f"voice_record_{ts}.wav"
        saved = self.engine.stop_mic_recording(out_file)

        self.btn_record.setText(tr("recorder_btn_start", "Начать запись"))
        self.btn_record.setIcon(FluentIcon.MICROPHONE)
        self.btn_record.setStyleSheet("")
        self.lbl_rec_status.setText(tr("recorder_status_idle", "Готов к записи"))
        self.lbl_rec_timer.setText("00:00")

        if saved:
            InfoBar.success(
                tr("recorder_saved_title", "Запись сохранена"),
                tr("recorder_saved_msg", "Файл успешно сохранён: {name}").format(name=out_file.name),
                parent=self,
                duration=4000
            )

    def _open_recordings_folder(self):
        rec_dir = self.cfg.get_recordings_dir()
        try:
            import os
            os.startfile(str(rec_dir))
        except Exception as e:
            QMessageBox.warning(self, tr("warning", "Внимание"), f"Не удалось открыть папку: {e}")

    def _update_meters(self):
        peak = self.engine.mic_in_peak
        self.vu_mic.set_levels(peak, peak)
