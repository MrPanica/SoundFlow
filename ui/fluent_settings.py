"""
Fluent Design Settings Interface for SoundFlow Studio.
Features Windows 11 SettingCardGroup, audio device selectors, and driver maintenance.
"""

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QMessageBox, QFileDialog
)
from qfluentwidgets import (
    SettingCardGroup, CardWidget, PrimaryPushButton, PushButton, TransparentPushButton,
    ComboBox, SwitchButton, TitleLabel, SubtitleLabel, BodyLabel,
    CaptionLabel, FluentIcon, InfoBar, InfoBarPosition, LineEdit,
    RoundMenu, Action, Slider
)

from core.audio_engine import AudioEngine
from core.driver_manager import DriverManager
from .fluent_soundboard import RenameCategoryDialog
from .soundboard_tab import HotkeyCaptureDialog
from core.i18n import tr, get_i18n


class FluentSettingsInterface(QWidget):
    """Windows 11 Fluent Design Settings Interface."""

    def __init__(self, audio_engine: AudioEngine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.setObjectName("settingsInterface")

        self._build_ui()
        self._load_devices()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(36, 28, 36, 28)
        main_layout.setSpacing(16)

        # Header Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = TitleLabel(tr("settings_title", "Параметры"), self)
        lbl_sub = CaptionLabel(tr("settings_subtitle", "Управление аудиоустройствами, задержкой (Latency), языком и виртуальным драйвером"), self)
        lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        main_layout.addLayout(title_layout)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 10, 0)
        c_layout.setSpacing(16)

        # 0. Language Selection Card
        card_lang = CardWidget(container)
        l_layout = QVBoxLayout(card_lang)
        l_layout.setContentsMargins(20, 18, 20, 18)
        l_layout.setSpacing(12)

        l_title = SubtitleLabel(tr("settings_lang_group_title", "Язык интерфейса / Language"), card_lang)
        l_layout.addWidget(l_title)

        lang_row = QHBoxLayout()
        lang_col = QVBoxLayout()
        lbl_lang = BodyLabel(tr("settings_lang_label", "Выберите язык приложения:"), card_lang)
        lbl_lang_desc = CaptionLabel(tr("settings_lang_desc", "Язык интерфейса SoundFlow Studio. По умолчанию используется язык вашей системы Windows."), card_lang)
        lbl_lang_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        lang_col.addWidget(lbl_lang)
        lang_col.addWidget(lbl_lang_desc)
        lang_row.addLayout(lang_col, stretch=1)

        self.combo_lang = ComboBox(card_lang)
        self.combo_lang.setFixedHeight(34)
        self.combo_lang.setMinimumWidth(260)
        self.combo_lang.addItem(tr("settings_lang_auto", "Автоматически (Системный) / Auto (System)"), userData="auto")
        self.combo_lang.addItem(tr("settings_lang_ru", "Русский (Russian)"), userData="ru")
        self.combo_lang.addItem(tr("settings_lang_en", "English"), userData="en")

        saved_lang = self.cfg.get("language", "auto")
        idx = self.combo_lang.findData(saved_lang)
        if idx >= 0:
            self.combo_lang.setCurrentIndex(idx)
        else:
            self.combo_lang.setCurrentIndex(0)

        self.combo_lang.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self.combo_lang)
        l_layout.addLayout(lang_row)

        c_layout.addWidget(card_lang)

        # 1. Device Group (Soundpad & Voicemod paradigm)
        card_devs = CardWidget(container)
        d_layout = QVBoxLayout(card_devs)
        d_layout.setContentsMargins(20, 18, 20, 18)
        d_layout.setSpacing(14)

        d_title = SubtitleLabel(tr("settings_devs_group_title", "Маршрутизация аудиоустройств"), card_devs)
        d_layout.addWidget(d_title)

        # Monitor (Speakers/Headphones)
        mon_box = QVBoxLayout()
        mon_box.setSpacing(3)
        mon_box.addWidget(BodyLabel(tr("settings_dev_monitor_title", "1. Устройство воспроизведения для себя (Динамики / Наушники):"), card_devs))
        lbl_mon_desc = CaptionLabel(tr("settings_dev_monitor_desc", "Куда выводится звук саундборда, радио, YouTube и эффектов лично для вас."), card_devs)
        lbl_mon_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        mon_box.addWidget(lbl_mon_desc)
        self.combo_monitor = ComboBox(card_devs)
        self.combo_monitor.setFixedHeight(34)
        mon_box.addWidget(self.combo_monitor)
        d_layout.addLayout(mon_box)

        # Target Mic (Virtual Cable)
        target_box = QVBoxLayout()
        target_box.setSpacing(3)
        target_box.addWidget(BodyLabel(tr("settings_dev_target_title", "2. Вывод в микрофон (целевой виртуальный кабель, CABLE Input):"), card_devs))
        lbl_target_desc = CaptionLabel(tr("settings_dev_target_desc", "Направляет саундборд, радио и ваш голос в виртуальный кабель для Discord, игр и стримов."), card_devs)
        lbl_target_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        target_box.addWidget(lbl_target_desc)
        self.combo_target_mic = ComboBox(card_devs)
        self.combo_target_mic.setFixedHeight(34)
        target_box.addWidget(self.combo_target_mic)
        d_layout.addLayout(target_box)

        # Mic in (Physical Microphone)
        mic_box = QVBoxLayout()
        mic_box.setSpacing(3)
        mic_box.addWidget(BodyLabel(tr("settings_dev_mic_title", "3. Реальный физический микрофон (Вход):"), card_devs))
        lbl_mic_desc = CaptionLabel(tr("settings_dev_mic_desc", "Ваш физический микрофон для разговора и наложения эффектов изменения голоса (Voice FX)."), card_devs)
        lbl_mic_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        mic_box.addWidget(lbl_mic_desc)
        self.combo_mic_in = ComboBox(card_devs)
        self.combo_mic_in.setFixedHeight(34)
        mic_box.addWidget(self.combo_mic_in)
        d_layout.addLayout(mic_box)

        # Helpful routing guide card like Voicemod / Soundpad
        guide_box = CardWidget(card_devs)
        guide_box.setStyleSheet("background-color: rgba(0, 153, 255, 0.08); border: 1px solid rgba(0, 153, 255, 0.25); border-radius: 6px;")
        g_layout = QVBoxLayout(guide_box)
        g_layout.setContentsMargins(14, 10, 14, 10)
        g_layout.setSpacing(4)

        lbl_g_title = CaptionLabel(tr("settings_guide_title", "Схема работы аудио как в Soundpad и Voicemod:"), guide_box)
        lbl_g_title.setStyleSheet("font-weight: 700; color: #00f2fe;")
        g_layout.addWidget(lbl_g_title)

        lbl_g_text = CaptionLabel(
            tr(
                "settings_guide_text",
                "• В Discord, Telegram, OBS и играх (CS2, Dota 2) выберите 'CABLE Output' как входной микрофон.\n"
                "• В SoundFlow выберите ваш реальный микрофон и наушники/динамики.\n"
                "• Ваши собеседники услышат идеальный звук саундборда и ваш голос без эха!"
            ),
            guide_box
        )
        lbl_g_text.setStyleSheet("color: rgba(255, 255, 255, 0.8); line-height: 140%;")
        g_layout.addWidget(lbl_g_text)

        self.btn_guide_set_default = TransparentPushButton(FluentIcon.SETTING, tr("settings_driver_btn_set_default", "Сделать CABLE Output микрофоном по умолчанию в Windows"), guide_box)
        self.btn_guide_set_default.setFixedHeight(30)
        self.btn_guide_set_default.clicked.connect(self._set_default_recording_device)
        g_layout.addWidget(self.btn_guide_set_default)

        d_layout.addWidget(guide_box)

        c_layout.addWidget(card_devs)

        # 2. Driver Management Card
        card_drv = CardWidget(container)
        drv_layout = QVBoxLayout(card_drv)
        drv_layout.setContentsMargins(20, 18, 20, 18)
        drv_layout.setSpacing(12)

        drv_title = SubtitleLabel(tr("settings_driver_group_title", "Виртуальный аудиодрайвер"), card_drv)
        drv_layout.addWidget(drv_title)

        self.lbl_drv_status = BodyLabel(tr("radio_status_connecting", "Статус: Проверка..."), card_drv)
        drv_layout.addWidget(self.lbl_drv_status)

        drv_btns = QHBoxLayout()
        drv_btns.setSpacing(10)

        self.btn_set_default = PrimaryPushButton(FluentIcon.SETTING, tr("settings_driver_btn_set_default", "Назначить микрофоном по умолчанию"), card_drv)
        self.btn_set_default.setFixedHeight(36)
        self.btn_set_default.clicked.connect(self._set_default_recording_device)
        drv_btns.addWidget(self.btn_set_default)

        self.btn_install_drv = PushButton(FluentIcon.DOWNLOAD, tr("settings_driver_btn_install", "Установить драйвер"), card_drv)
        self.btn_install_drv.setFixedHeight(36)
        self.btn_install_drv.clicked.connect(self._install_driver)
        drv_btns.addWidget(self.btn_install_drv)

        self.btn_sound_cpl = PushButton(FluentIcon.MICROPHONE, tr("settings_driver_btn_mmsys", "Параметры Windows"), card_drv)
        self.btn_sound_cpl.setFixedHeight(36)
        self.btn_sound_cpl.clicked.connect(DriverManager.open_sound_recording_settings)
        drv_btns.addWidget(self.btn_sound_cpl)

        self.btn_open_folder = PushButton(FluentIcon.FOLDER, tr("settings_rec_dir_open", "Папка"), card_drv)
        self.btn_open_folder.setFixedHeight(36)
        self.btn_open_folder.clicked.connect(DriverManager.open_driver_folder)
        drv_layout.addLayout(drv_btns)

        # Exit microphone behavior row
        exit_mic_box = QVBoxLayout()
        exit_mic_box.setSpacing(4)
        exit_mic_box.addWidget(BodyLabel(tr("settings_exit_mic_title", "Микрофон при выходе из приложения:"), card_drv))
        lbl_exit_mic_desc = CaptionLabel(tr("settings_exit_mic_desc", "Чтобы ваш голос не пропадал в играх и Discord, когда SoundFlow закрыт"), card_drv)
        lbl_exit_mic_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        exit_mic_box.addWidget(lbl_exit_mic_desc)

        self.combo_exit_mic = ComboBox(card_drv)
        self.combo_exit_mic.setFixedHeight(34)
        self.combo_exit_mic.addItem(tr("settings_exit_mic_restore", "🔄 Возвращать реальный микрофон по умолчанию в Windows (Рекомендуется)"), userData="restore_default")
        self.combo_exit_mic.addItem(tr("settings_exit_mic_repeater", "🎙️ Фоновый ретранслятор в CABLE Output (для Discord/игр)"), userData="repeater")
        self.combo_exit_mic.addItem(tr("settings_exit_mic_both", "⚡ И возврат микрофона, и фоновый ретранслятор"), userData="both")
        self.combo_exit_mic.addItem(tr("settings_exit_mic_none", "❌ Ничего не делать (оставлять как есть)"), userData="none")

        saved_exit_mic = self.cfg.get("exit_mic_behavior", "restore_default")
        for i in range(self.combo_exit_mic.count()):
            if self.combo_exit_mic.itemData(i) == saved_exit_mic:
                self.combo_exit_mic.setCurrentIndex(i)
                break
        self.combo_exit_mic.currentIndexChanged.connect(self._on_exit_mic_changed)
        exit_mic_box.addWidget(self.combo_exit_mic)
        drv_layout.addLayout(exit_mic_box)

        # Default mic startup reminder banner switch
        remind_box = QHBoxLayout()
        remind_col = QVBoxLayout()
        remind_col.addWidget(BodyLabel(tr("settings_remind_default_mic", "Напоминать о микрофоне по умолчанию при запуске"), card_drv))
        lbl_remind_desc = CaptionLabel(tr("settings_remind_default_mic_desc", "Показывать баннер, если CABLE Output не выбран микрофоном по умолчанию в Windows"), card_drv)
        lbl_remind_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        remind_col.addWidget(lbl_remind_desc)
        remind_box.addLayout(remind_col, stretch=1)

        self.switch_remind_default_mic = SwitchButton(card_drv)
        self.switch_remind_default_mic.setChecked(not bool(self.cfg.get("hide_cable_default_banner", False)))
        self.switch_remind_default_mic.checkedChanged.connect(
            lambda c: self.cfg.set("hide_cable_default_banner", not c)
        )
        remind_box.addWidget(self.switch_remind_default_mic)
        drv_layout.addLayout(remind_box)

        c_layout.addWidget(card_drv)

        # 3. Buffer & Latency Card
        card_buf = CardWidget(container)
        b_layout = QVBoxLayout(card_buf)
        b_layout.setContentsMargins(20, 18, 20, 18)
        b_layout.setSpacing(12)

        b_title = SubtitleLabel(tr("settings_latency_group_title", "Буферизация и задержка"), card_buf)
        b_layout.addWidget(b_title)

        buf_row = QHBoxLayout()
        buf_row.addWidget(BodyLabel(tr("settings_buf_label", "Размер буфера (задержка звука):"), card_buf))
        self.combo_buf = ComboBox(card_buf)
        self.combo_buf.addItem(tr("settings_buf_512", "512 сэмплов (~10 мс - ультранизкая задержка)"), userData=512)
        self.combo_buf.addItem(tr("settings_buf_1024", "1024 сэмпла (~21 мс - стабильно, рекомендуемо)"), userData=1024)
        self.combo_buf.addItem(tr("settings_buf_2048", "2048 сэмплов (~42 мс - без щелчков на слабых ПК)"), userData=2048)
        buf_row.addWidget(self.combo_buf, stretch=1)
        b_layout.addLayout(buf_row)

        rep_row = QHBoxLayout()
        rep_row.addWidget(BodyLabel(tr("settings_replay_label", "Длительность буфера моментального клипа:"), card_buf))
        self.combo_rep = ComboBox(card_buf)
        self.combo_rep.addItem(tr("settings_replay_15", "15 секунд"), userData=15)
        self.combo_rep.addItem(tr("settings_replay_30", "30 секунд (по умолчанию)"), userData=30)
        self.combo_rep.addItem(tr("settings_replay_60", "60 секунд"), userData=60)
        rep_row.addWidget(self.combo_rep, stretch=1)
        b_layout.addLayout(rep_row)

        # Tray switch
        tray_row = QHBoxLayout()
        tray_col = QVBoxLayout()
        tray_col.addWidget(BodyLabel(tr("settings_tray_minimize", "Сворачивать в системный трей при закрытии"), card_buf))
        tray_col.addWidget(CaptionLabel(tr("settings_tray_desc", "Приложение и горячие клавиши продолжат работать в фоне во время игр"), card_buf))
        tray_row.addLayout(tray_col, stretch=1)

        self.switch_tray = SwitchButton(card_buf)
        self.switch_tray.setChecked(bool(self.cfg.get("minimize_to_tray", True)))
        tray_row.addWidget(self.switch_tray)
        b_layout.addLayout(tray_row)

        # Tray notification switch
        tray_notify_row = QHBoxLayout()
        tray_notify_col = QVBoxLayout()
        tray_notify_col.addWidget(BodyLabel(tr("settings_tray_notify", "Уведомление при сворачивании в трей"), card_buf))
        tray_notify_col.addWidget(CaptionLabel(tr("settings_tray_notify_desc", "Показывать системное сообщение о работе в фоне при закрытии окна в трей"), card_buf))
        tray_notify_row.addLayout(tray_notify_col, stretch=1)

        self.switch_tray_notify = SwitchButton(card_buf)
        self.switch_tray_notify.setChecked(bool(self.cfg.get("notify_on_minimize", True)))
        self.switch_tray_notify.checkedChanged.connect(
            lambda c: self.cfg.set("notify_on_minimize", c)
        )
        tray_notify_row.addWidget(self.switch_tray_notify)
        b_layout.addLayout(tray_notify_row)

        c_layout.addWidget(card_buf)

        # 3.1 Voice Recorder Directory Card
        card_rec_dir = CardWidget(container)
        rec_dir_layout = QVBoxLayout(card_rec_dir)
        rec_dir_layout.setContentsMargins(20, 18, 20, 18)
        rec_dir_layout.setSpacing(12)

        rec_dir_title = SubtitleLabel(tr("settings_rec_dir_title", "Папка сохранения записей диктофона:"), card_rec_dir)
        rec_dir_layout.addWidget(rec_dir_title)

        rec_dir_desc = CaptionLabel(tr("settings_rec_dir_desc", "Куда сохранять аудиозаписи из вкладки 'Микрофон и Voice FX'"), card_rec_dir)
        rec_dir_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        rec_dir_layout.addWidget(rec_dir_desc)

        rec_dir_row = QHBoxLayout()
        rec_dir_row.setSpacing(10)

        self.edit_rec_dir = LineEdit(card_rec_dir)
        self.edit_rec_dir.setFixedHeight(34)
        self.edit_rec_dir.setText(str(self.cfg.get_recordings_dir()))
        self.edit_rec_dir.setReadOnly(True)
        rec_dir_row.addWidget(self.edit_rec_dir, stretch=1)

        self.btn_browse_rec_dir = PushButton(FluentIcon.FOLDER, tr("settings_rec_dir_browse", "Обзор..."), card_rec_dir)
        self.btn_browse_rec_dir.setFixedHeight(34)
        self.btn_browse_rec_dir.clicked.connect(self._browse_recordings_dir)
        rec_dir_row.addWidget(self.btn_browse_rec_dir)

        self.btn_open_rec_dir = TransparentPushButton(FluentIcon.SHARE, tr("settings_rec_dir_open", "Открыть папку"), card_rec_dir)
        self.btn_open_rec_dir.setFixedHeight(34)
        self.btn_open_rec_dir.clicked.connect(self._open_recordings_dir)
        rec_dir_row.addWidget(self.btn_open_rec_dir)

        rec_dir_layout.addLayout(rec_dir_row)
        c_layout.addWidget(card_rec_dir)

        # 3.2 Auto Push-to-Talk (Auto-PTT) Card
        card_ptt = CardWidget(container)
        ptt_layout = QVBoxLayout(card_ptt)
        ptt_layout.setContentsMargins(20, 18, 20, 18)
        ptt_layout.setSpacing(12)

        ptt_title = SubtitleLabel(tr("settings_ptt_group", "Автоматический Push-to-Talk (Auto-PTT для игр)"), card_ptt)
        ptt_layout.addWidget(ptt_title)

        ptt_desc = CaptionLabel(tr("settings_ptt_group_desc", "Автоматически зажимает клавишу активации микрофона в играх и Discord при воспроизведении звуков, радио или TTS"), card_ptt)
        ptt_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        ptt_layout.addWidget(ptt_desc)

        ptt_switch_row = QHBoxLayout()
        ptt_switch_col = QVBoxLayout()
        ptt_switch_col.addWidget(BodyLabel(tr("settings_ptt_enable", "Включить Auto-PTT"), card_ptt))
        ptt_switch_row.addLayout(ptt_switch_col, stretch=1)
        self.switch_ptt = SwitchButton(card_ptt)
        self.switch_ptt.setChecked(bool(self.cfg.get("ptt_enabled", False)))
        self.switch_ptt.checkedChanged.connect(self._on_ptt_switch_changed)
        ptt_switch_row.addWidget(self.switch_ptt)
        ptt_layout.addLayout(ptt_switch_row)

        ptt_key_row = QHBoxLayout()
        ptt_key_col = QVBoxLayout()
        ptt_key_col.addWidget(BodyLabel(tr("settings_ptt_key", "Клавиша PTT в игре:"), card_ptt))
        ptt_key_desc = CaptionLabel(tr("settings_ptt_key_hint", "Нажмите для изменения клавиши PTT"), card_ptt)
        ptt_key_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        ptt_key_col.addWidget(ptt_key_desc)
        ptt_key_row.addLayout(ptt_key_col, stretch=1)

        self.ptt_key = str(self.cfg.get("ptt_key", "v"))
        self.btn_ptt_key = PushButton(self.ptt_key.upper(), card_ptt)
        self.btn_ptt_key.setFixedWidth(120)
        self.btn_ptt_key.setFixedHeight(34)
        self.btn_ptt_key.clicked.connect(self._capture_ptt_key)
        ptt_key_row.addWidget(self.btn_ptt_key)
        ptt_layout.addLayout(ptt_key_row)

        ptt_delay_row = QHBoxLayout()
        ptt_delay_col = QVBoxLayout()
        cur_delay = int(self.cfg.get("ptt_delay_ms", 150))
        self.lbl_ptt_delay = BodyLabel(f"{tr('settings_ptt_delay', 'Задержка отпускания клавиши (мс):')} {cur_delay} ms", card_ptt)
        ptt_delay_desc = CaptionLabel(tr("settings_ptt_delay_desc", "Время удержания клавиши PTT после окончания звука"), card_ptt)
        ptt_delay_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        ptt_delay_col.addWidget(self.lbl_ptt_delay)
        ptt_delay_col.addWidget(ptt_delay_desc)
        ptt_delay_row.addLayout(ptt_delay_col, stretch=1)

        self.slider_ptt_delay = Slider(Qt.Orientation.Horizontal, card_ptt)
        self.slider_ptt_delay.setRange(20, 500)
        self.slider_ptt_delay.setValue(cur_delay)
        self.slider_ptt_delay.setFixedWidth(200)
        self.slider_ptt_delay.valueChanged.connect(self._on_ptt_delay_changed)
        ptt_delay_row.addWidget(self.slider_ptt_delay)
        ptt_layout.addLayout(ptt_delay_row)

        c_layout.addWidget(card_ptt)

        # 3.3 Voice Ducking (Microphone Priority) Card
        card_ducking = CardWidget(container)
        ducking_layout = QVBoxLayout(card_ducking)
        ducking_layout.setContentsMargins(20, 18, 20, 18)
        ducking_layout.setSpacing(12)

        ducking_title = SubtitleLabel(tr("settings_ducking_group", "Приоритет голоса (Voice Ducking)"), card_ducking)
        ducking_layout.addWidget(ducking_title)

        ducking_desc = CaptionLabel(tr("settings_ducking_group_desc", "Автоматически приглушает саундборд, радио и стримы, когда вы говорите в реальный микрофон"), card_ducking)
        ducking_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        ducking_layout.addWidget(ducking_desc)

        duck_switch_row = QHBoxLayout()
        duck_switch_col = QVBoxLayout()
        duck_switch_col.addWidget(BodyLabel(tr("settings_ducking_enable", "Включить Voice Ducking"), card_ducking))
        duck_switch_row.addLayout(duck_switch_col, stretch=1)
        self.switch_ducking = SwitchButton(card_ducking)
        self.switch_ducking.setChecked(bool(self.cfg.get("ducking_enabled", True)))
        self.switch_ducking.checkedChanged.connect(self._on_ducking_switch_changed)
        duck_switch_row.addWidget(self.switch_ducking)
        ducking_layout.addLayout(duck_switch_row)

        duck_amount_row = QHBoxLayout()
        duck_amount_col = QVBoxLayout()
        cur_duck_amt = int(self.cfg.get("ducking_amount", 0.25) * 100)
        self.lbl_ducking_amt = BodyLabel(tr("settings_ducking_amount", "Громкость фона во время речи: {val}%", val=cur_duck_amt), card_ducking)
        duck_amt_desc = CaptionLabel(tr("settings_ducking_amount_desc", "Остаточная громкость фона во время вашей речи"), card_ducking)
        duck_amt_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        duck_amount_col.addWidget(self.lbl_ducking_amt)
        duck_amount_col.addWidget(duck_amt_desc)
        duck_amount_row.addLayout(duck_amount_col, stretch=1)

        self.slider_ducking_amt = Slider(Qt.Orientation.Horizontal, card_ducking)
        self.slider_ducking_amt.setRange(0, 80)
        self.slider_ducking_amt.setValue(cur_duck_amt)
        self.slider_ducking_amt.setFixedWidth(200)
        self.slider_ducking_amt.valueChanged.connect(self._on_ducking_amt_changed)
        duck_amount_row.addWidget(self.slider_ducking_amt)
        ducking_layout.addLayout(duck_amount_row)

        duck_thresh_row = QHBoxLayout()
        duck_thresh_col = QVBoxLayout()
        cur_thresh = int(self.cfg.get("ducking_threshold_db", -35.0))
        self.lbl_ducking_thresh = BodyLabel(tr("settings_ducking_thresh", "Порог чувствительности микрофона: {val} дБ", val=cur_thresh), card_ducking)
        duck_thresh_desc = CaptionLabel(tr("settings_ducking_thresh_desc", "Порог громкости вашей речи для срабатывания приглушения"), card_ducking)
        duck_thresh_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        duck_thresh_col.addWidget(self.lbl_ducking_thresh)
        duck_thresh_col.addWidget(duck_thresh_desc)
        duck_thresh_row.addLayout(duck_thresh_col, stretch=1)

        self.slider_ducking_thresh = Slider(Qt.Orientation.Horizontal, card_ducking)
        self.slider_ducking_thresh.setRange(-55, -15)
        self.slider_ducking_thresh.setValue(cur_thresh)
        self.slider_ducking_thresh.setFixedWidth(200)
        self.slider_ducking_thresh.valueChanged.connect(self._on_ducking_thresh_changed)
        duck_thresh_row.addWidget(self.slider_ducking_thresh)
        ducking_layout.addLayout(duck_thresh_row)

        c_layout.addWidget(card_ducking)

        # 3.4 Loudness Normalization Card
        card_norm = CardWidget(container)
        norm_layout = QVBoxLayout(card_norm)
        norm_layout.setContentsMargins(20, 18, 20, 18)
        norm_layout.setSpacing(12)

        norm_title = SubtitleLabel(tr("settings_norm_group", "Нормализация громкости (Loudness Normalization)"), card_norm)
        norm_layout.addWidget(norm_title)

        norm_desc = CaptionLabel(tr("settings_norm_group_desc", "Автоматическое выравнивание уровней звуков саундборда: усиливает тихие и мягко лимитирует громкие звуки без перегрузок"), card_norm)
        norm_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        norm_layout.addWidget(norm_desc)

        norm_switch_row = QHBoxLayout()
        norm_switch_col = QVBoxLayout()
        norm_switch_col.addWidget(BodyLabel(tr("settings_norm_enable", "Автоматическая нормализация громкости (RMS / Peak Limiter)"), card_norm))
        norm_switch_row.addLayout(norm_switch_col, stretch=1)

        self.switch_norm = SwitchButton(card_norm)
        self.switch_norm.setChecked(bool(self.cfg.get("auto_normalize", True)))
        self.switch_norm.checkedChanged.connect(self._on_norm_switch_changed)
        norm_switch_row.addWidget(self.switch_norm)
        norm_layout.addLayout(norm_switch_row)

        c_layout.addWidget(card_norm)

        # 4. Category Management Card
        card_cats = CardWidget(container)
        cat_card_layout = QVBoxLayout(card_cats)
        cat_card_layout.setContentsMargins(20, 18, 20, 18)
        cat_card_layout.setSpacing(12)

        cat_title = SubtitleLabel(tr("settings_cat_title", "Управление вкладками и категориями саундборда"), card_cats)
        cat_card_layout.addWidget(cat_title)

        cat_desc = CaptionLabel(tr("settings_cat_desc", "Создавайте собственные вкладки для удобной сортировки звуков и эффектов"), card_cats)
        cat_desc.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        cat_card_layout.addWidget(cat_desc)

        # Category addition row
        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        self.edit_new_cat = LineEdit(card_cats)
        self.edit_new_cat.setPlaceholderText(tr("soundboard_dlg_new_cat_placeholder", "Например: Приколы, Трэш, Голоса..."))
        self.edit_new_cat.setFixedHeight(34)
        add_row.addWidget(self.edit_new_cat, stretch=1)

        self.btn_add_cat = PrimaryPushButton(FluentIcon.ADD, tr("add", "Добавить"), card_cats)
        self.btn_add_cat.setFixedHeight(34)
        self.btn_add_cat.clicked.connect(self._add_category_from_settings)
        add_row.addWidget(self.btn_add_cat)
        cat_card_layout.addLayout(add_row)

        self.cat_list_layout = QVBoxLayout()
        self.cat_list_layout.setSpacing(6)
        cat_card_layout.addLayout(self.cat_list_layout)

        c_layout.addWidget(card_cats)

        # Save Button Row
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, tr("settings_btn_save", "Применить настройки"), container)
        self.btn_save.setFixedHeight(38)
        self.btn_save.clicked.connect(self._save_settings)
        btn_row.addWidget(self.btn_save)
        c_layout.addLayout(btn_row)
        c_layout.addLayout(btn_row)

        c_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=1)

        self._update_drv_status()
        self._refresh_categories_list()

    def _update_drv_status(self):
        installed = DriverManager.is_driver_installed()
        if installed:
            is_default = DriverManager.is_cable_output_default()
            if is_default:
                self.lbl_drv_status.setText(tr("settings_drv_status_ready", "Статус: Драйвер готов. CABLE Output назначен микрофоном по умолчанию в Windows (Игры и Discord слышат звук)."))
                self.lbl_drv_status.setStyleSheet("color: #4ade80;")
            else:
                self.lbl_drv_status.setText(tr("settings_drv_status_not_default", "Статус: Драйвер установлен, но CABLE Output ещё не выбран микрофоном по умолчанию в Windows."))
                self.lbl_drv_status.setStyleSheet("color: #fbbf24;")
            self.btn_install_drv.setText(tr("settings_driver_btn_reinstall", "Переустановить драйвер"))
        else:
            self.lbl_drv_status.setText(tr("settings_drv_status_not_found", "Статус: Драйвер не найден. Звук в микрофон собеседникам не идет."))
            self.lbl_drv_status.setStyleSheet("color: #f87171;")
            self.btn_install_drv.setText(tr("settings_driver_btn_install", "Установить официальный драйвер (VB-Cable)"))

    def _set_default_recording_device(self):
        main_win = self.window()
        if hasattr(main_win, "toggle_default_recording_device"):
            main_win.toggle_default_recording_device(parent_widget=self)
        else:
            DriverManager.set_default_recording_device_to_cable()
        self._update_drv_status()

    def _load_devices(self):
        devices = AudioEngine.get_audio_devices()

        self.combo_monitor.clear()
        for d in devices["outputs"]:
            self.combo_monitor.addItem(d["name"], userData=d["id"])

        saved_mic_target = self.cfg.get("mic_target_device_id")
        selected_target_idx = AudioEngine.populate_target_mic_combobox(self.combo_target_mic, saved_mic_target)
        if saved_mic_target is None and self.combo_target_mic.itemData(selected_target_idx) is not None:
            self.cfg.set("mic_target_device_id", self.combo_target_mic.itemData(selected_target_idx))

        self.combo_mic_in.clear()
        self.combo_mic_in.addItem(tr("settings_no_phys_mic", "-- Без физического микрофона --"), userData=None)
        for d in devices["inputs"]:
            self.combo_mic_in.addItem(d["name"], userData=d["id"])

        defaults = AudioEngine.get_default_devices()

        # Select saved monitor
        saved_mon = self.cfg.get("monitor_device_id")
        selected_mon_idx = 0
        if saved_mon is not None:
            for i in range(self.combo_monitor.count()):
                if self.combo_monitor.itemData(i) == saved_mon:
                    selected_mon_idx = i
                    break
        if selected_mon_idx == 0 and defaults.get("monitor") is not None:
            for i in range(self.combo_monitor.count()):
                if self.combo_monitor.itemData(i) == defaults["monitor"]:
                    selected_mon_idx = i
                    self.cfg.set("monitor_device_id", defaults["monitor"])
                    break
        self.combo_monitor.setCurrentIndex(selected_mon_idx)

        # Select saved mic input
        saved_mic_in = self.cfg.get("mic_input_device_id")
        selected_mic_idx = 0
        if saved_mic_in is not None:
            for i in range(self.combo_mic_in.count()):
                if self.combo_mic_in.itemData(i) == saved_mic_in:
                    selected_mic_idx = i
                    break

        # If no microphone saved, auto-select default physical microphone
        if selected_mic_idx == 0 and defaults.get("mic_input") is not None:
            for i in range(self.combo_mic_in.count()):
                if self.combo_mic_in.itemData(i) == defaults["mic_input"]:
                    selected_mic_idx = i
                    self.cfg.set("mic_input_device_id", defaults["mic_input"])
                    break

        self.combo_mic_in.setCurrentIndex(selected_mic_idx)

        cur_buf = self.cfg.get("buffer_size", 1024)
        for i in range(self.combo_buf.count()):
            if self.combo_buf.itemData(i) == cur_buf:
                self.combo_buf.setCurrentIndex(i)
                break

        cur_rep = self.cfg.get("instant_replay_duration", 30)
        for i in range(self.combo_rep.count()):
            if self.combo_rep.itemData(i) == cur_rep:
                self.combo_rep.setCurrentIndex(i)
                break

    def _on_language_changed(self, index: int):
        try:
            lang_code = self.combo_lang.itemData(index) or "auto"
            self.cfg.set("language", lang_code)
            get_i18n().set_language(lang_code)
            is_ru = get_i18n().current_language == "ru"
            parent_win = self.window() or self
            InfoBar.info(
                title=tr("settings_lang_saved_title", "Язык интерфейса"),
                content=tr("settings_lang_saved_msg", "Язык сохранен. Перезапустите приложение для полного применения всех названий."),
                parent=parent_win,
                position=InfoBarPosition.TOP,
                duration=3500
            )
        except Exception as e:
            print(f"[FluentSettings] _on_language_changed error: {e}")

    def _on_exit_mic_changed(self, index: int):
        val = self.combo_exit_mic.itemData(index) or "restore_default"
        self.cfg.set("exit_mic_behavior", val)

    def _on_ptt_switch_changed(self, checked: bool):
        self.cfg.set("ptt_enabled", checked)
        if hasattr(self.engine, "ptt") and self.engine.ptt:
            self.engine.ptt.update_config(enabled=checked)

    def _capture_ptt_key(self):
        dlg = HotkeyCaptureDialog(self.ptt_key, parent=self)
        if dlg.exec():
            new_key = dlg.captured_key or "v"
            self.ptt_key = new_key
            self.btn_ptt_key.setText(new_key.upper())
            self.cfg.set("ptt_key", new_key)
            if hasattr(self.engine, "ptt") and self.engine.ptt:
                self.engine.ptt.update_config(key=new_key)

    def _on_ptt_delay_changed(self, val: int):
        self.lbl_ptt_delay.setText(f"{tr('settings_ptt_delay', 'Задержка отпускания клавиши (мс):')} {val} ms")
        self.cfg.set("ptt_delay_ms", val)
        if hasattr(self.engine, "ptt") and self.engine.ptt:
            self.engine.ptt.update_config(release_delay_sec=val / 1000.0)

    def _on_ducking_switch_changed(self, checked: bool):
        self.cfg.set("ducking_enabled", checked)
        self.engine.ducking_enabled = checked

    def _on_ducking_amt_changed(self, val: int):
        self.lbl_ducking_amt.setText(tr("settings_ducking_amount", "Громкость фона во время речи: {val}%", val=val))
        amt = val / 100.0
        self.cfg.set("ducking_amount", amt)
        self.engine.ducking_amount = amt

    def _on_ducking_thresh_changed(self, val: int):
        self.lbl_ducking_thresh.setText(tr("settings_ducking_thresh", "Порог чувствительности микрофона: {val} дБ", val=val))
        self.cfg.set("ducking_threshold_db", float(val))
        self.engine.ducking_threshold_db = float(val)

    def _on_norm_switch_changed(self, checked: bool):
        self.cfg.set("auto_normalize", checked)
        self.engine.auto_normalize_enabled = checked

    def _save_settings(self):
        mon = self.combo_monitor.currentData()
        target = self.combo_target_mic.currentData()
        mic_in = self.combo_mic_in.currentData()
        buf = self.combo_buf.currentData()
        rep = self.combo_rep.currentData()
        tray = self.switch_tray.isChecked()

        self.cfg.set("monitor_device_id", mon)
        self.cfg.set("mic_target_device_id", target)
        self.cfg.set("mic_input_device_id", mic_in)
        self.cfg.set("buffer_size", buf)
        self.cfg.set("instant_replay_duration", rep)
        self.cfg.set("minimize_to_tray", tray)
        if hasattr(self, "switch_tray_notify"):
            self.cfg.set("notify_on_minimize", self.switch_tray_notify.isChecked())
        if hasattr(self, "switch_remind_default_mic"):
            self.cfg.set("hide_cable_default_banner", not self.switch_remind_default_mic.isChecked())

        # PTT, Ducking, Normalization
        ptt_enabled = self.switch_ptt.isChecked()
        ptt_delay = self.slider_ptt_delay.value()
        self.cfg.set("ptt_enabled", ptt_enabled)
        self.cfg.set("ptt_key", self.ptt_key)
        self.cfg.set("ptt_delay_ms", ptt_delay)
        if hasattr(self.engine, "ptt") and self.engine.ptt:
            self.engine.ptt.update_config(
                key=self.ptt_key,
                release_delay_sec=ptt_delay / 1000.0,
                enabled=ptt_enabled
            )

        ducking_enabled = self.switch_ducking.isChecked()
        ducking_amount = self.slider_ducking_amt.value() / 100.0
        ducking_thresh = float(self.slider_ducking_thresh.value())
        self.cfg.set("ducking_enabled", ducking_enabled)
        self.cfg.set("ducking_amount", ducking_amount)
        self.cfg.set("ducking_threshold_db", ducking_thresh)
        self.engine.ducking_enabled = ducking_enabled
        self.engine.ducking_amount = ducking_amount
        self.engine.ducking_threshold_db = ducking_thresh

        auto_norm = self.switch_norm.isChecked()
        self.cfg.set("auto_normalize", auto_norm)
        self.engine.auto_normalize_enabled = auto_norm

        self.engine.buffer_size = buf
        self.engine.instant_replay.set_duration(rep)
        self.engine.initialize_streams(
            monitor_device=mon,
            mic_target_device=target,
            mic_input_device=mic_in,
            explicit_target_set=True
        )

        main_win = self.window()
        if hasattr(main_win, "sync_all_target_mic_combos"):
            main_win.sync_all_target_mic_combos(target)

        InfoBar.success(
            title=tr("settings_saved_title", "Настройки сохранены"),
            content=tr("settings_saved_msg", "Параметры аудиоустройств успешно применены."),
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.window() or self
        )

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

    def _browse_recordings_dir(self):
        cur = str(self.cfg.get_recordings_dir())
        chosen = QFileDialog.getExistingDirectory(self, tr("settings_rec_dir_title", "Папка сохранения записей"), cur)
        if chosen:
            self.cfg.set("recordings_dir", chosen)
            self.edit_rec_dir.setText(chosen)
            InfoBar.success(
                title=tr("settings_rec_saved_title", "Папка сохранена"),
                content=tr("settings_rec_saved_msg", "Путь к папке записей успешно обновлен."),
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self.window() or self
            )

    def _open_recordings_dir(self):
        rec_dir = self.cfg.get_recordings_dir()
        try:
            import os
            os.startfile(str(rec_dir))
        except Exception as e:
            QMessageBox.warning(self, tr("warning", "Внимание"), f"Не удалось открыть папку: {e}")

    def _install_driver(self):
        success = DriverManager.launch_installer()
        if success:
            QMessageBox.information(
                self,
                tr("driver_installer_title", "Установщик запущен"),
                tr("driver_installer_msg", "Запущен официальный инсталлятор драйвера VB-Audio Cable.\n\n1. Нажмите 'Install Driver' в окне инсталлятора.\n2. Подтвердите права администратора Windows.\n3. После завершения перезапустите SoundFlow или нажмите 'Применить настройки'.")
            )
        else:
            DriverManager.open_driver_folder()

    def _refresh_categories_list(self):
        while self.cat_list_layout.count() > 0:
            item = self.cat_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for cat in self.cfg.get_categories():
            row = QWidget()
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(8, 4, 8, 4)
            r_layout.setSpacing(10)

            lbl_name = BodyLabel(f"{cat['name']} ({cat['id']})", row)
            r_layout.addWidget(lbl_name, stretch=1)

            if cat.get("system", False):
                badge = CaptionLabel(tr("settings_cat_system", "Системная вкладка"), row)
                badge.setStyleSheet("color: rgba(255, 255, 255, 0.45); font-style: italic;")
                r_layout.addWidget(badge)
            else:
                btn_rename = PushButton(FluentIcon.EDIT, tr("common_rename", "Переименовать"), row)
                btn_rename.setFixedHeight(28)
                btn_rename.clicked.connect(lambda chk, cid=cat["id"], cn=cat["name"]: self._rename_category_from_settings(cid, cn))
                r_layout.addWidget(btn_rename)

                btn_del = PushButton(FluentIcon.DELETE, tr("common_delete", "Удалить..."), row)
                btn_del.setFixedHeight(28)
                btn_del.clicked.connect(lambda chk, cid=cat["id"], cn=cat["name"], btn=btn_del: self._show_delete_menu_from_settings(cid, cn, btn))
                r_layout.addWidget(btn_del)

            self.cat_list_layout.addWidget(row)

    def _add_category_from_settings(self):
        name = self.edit_new_cat.text().strip()
        if not name:
            return
        new_cat = self.cfg.add_category(name)
        if new_cat:
            self.edit_new_cat.clear()
            self._refresh_categories_list()
            main_win = self.window()
            if hasattr(main_win, "soundboard_interface"):
                main_win.soundboard_interface.refresh_categories()

    def _rename_category_from_settings(self, cat_id: str, current_name: str):
        dlg = RenameCategoryDialog(current_name, parent=self)
        if dlg.exec():
            new_name = dlg.new_name
            if self.cfg.rename_category(cat_id, new_name):
                self._refresh_categories_list()
                main_win = self.window()
                if hasattr(main_win, "soundboard_interface"):
                    main_win.soundboard_interface.refresh_categories()
                    main_win.soundboard_interface.refresh_sounds()

    def _show_delete_menu_from_settings(self, cat_id: str, cat_name: str, button_widget):
        sound_count = sum(1 for s in self.cfg.sounds if str(s.get("category", "")).upper() == cat_id.upper())
        menu = RoundMenu(parent=self)
        menu.addAction(Action(
            FluentIcon.MOVE,
            tr("soundboard_del_cat_keep_fmt", "Сохранить звуки во «Все» [{count} шт.]").format(count=sound_count),
            triggered=lambda: self._delete_category_from_settings(cat_id, delete_sounds=False)
        ))
        menu.addAction(Action(
            FluentIcon.DELETE,
            tr("soundboard_del_cat_with_sounds_fmt", "Удалить вместе с содержимым ({count} шт.)").format(count=sound_count),
            triggered=lambda: self._delete_category_from_settings(cat_id, delete_sounds=True)
        ))
        menu.exec(button_widget.mapToGlobal(button_widget.rect().bottomLeft()))

    def _delete_category_from_settings(self, cat_id: str, delete_sounds: bool = False):
        cats = self.cfg.get_categories()
        curr_cat = next((c for c in cats if c["id"] == cat_id), None)
        name = curr_cat["name"] if curr_cat else cat_id
        sound_count = sum(1 for s in self.cfg.sounds if str(s.get("category", "")).upper() == cat_id.upper())

        if delete_sounds:
            reply = QMessageBox.warning(
                self,
                tr("soundboard_del_cat_with_sounds_title", "Удаление категории с содержимым"),
                tr("soundboard_del_cat_with_sounds_msg", "Вы действительно хотите удалить категорию «{cat}» и ВСЕ входящие в неё звуки ({count} шт.)?").format(cat=name, count=sound_count),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
        else:
            reply = QMessageBox.question(
                self,
                tr("soundboard_del_cat_confirm_title", "Удаление категории"),
                tr("soundboard_del_cat_confirm_msg", "Удалить категорию «{cat}»?\nВсе звуки ({count} шт.) сохранятся и останутся доступны во вкладке «Все» (перенесены в SFX).").format(cat=name, count=sound_count),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

        if reply == QMessageBox.StandardButton.Yes:
            self.cfg.remove_category(cat_id, delete_sounds=delete_sounds)
            self._refresh_categories_list()
            main_win = self.window()
            if hasattr(main_win, "soundboard_interface"):
                main_win.soundboard_interface.refresh_categories(select_id="ALL")
                main_win.soundboard_interface.refresh_sounds()
