"""
Fluent Design Online Radio & Web Stream Interface for SoundFlow Studio.
Features Windows 11 Fluent cards, YouTube, YouTube Shorts, YouTube Music, Twitch,
Play/Pause toggle ('Остановить' <-> 'Продолжить'), [-10s] / [+10s] seeking,
thread-safe Qt signals, track time display, and playlist auto-advance.
"""

from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QMessageBox, QDialog
)
from qfluentwidgets import (
    CardWidget, PrimaryPushButton, PushButton, TransparentToolButton,
    LineEdit, Slider, TitleLabel, SubtitleLabel, BodyLabel,
    CaptionLabel, FluentIcon, RoundMenu, Action, SwitchButton, ComboBox,
    InfoBar, InfoBarPosition, IconWidget
)

from core.radio_streamer import clean_and_normalize_stream_url


class TimelineSlider(Slider):
    """Fluent Slider for Timeline Scrubbing that emits seeking on click and drag-release."""
    seekRequested = pyqtSignal(float)

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.is_scrubbing = False

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self.is_scrubbing = True
            super().mousePressEvent(e)
            val = self._posToValue(e.pos())
            self.setValue(val)
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        if self.is_scrubbing:
            super().mouseMoveEvent(e)
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton and self.is_scrubbing:
            self.is_scrubbing = False
            ratio = self.value() / float(self.maximum()) if self.maximum() > 0 else 0.0
            self.seekRequested.emit(ratio)
        super().mouseReleaseEvent(e)


class AddStationDialog(QDialog):
    """Dialog to add a custom online radio station or stream preset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новая станция или стрим")
        self.setFixedSize(480, 360)
        self.setStyleSheet("background-color: #202020; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel("Добавить станцию или стрим", self))

        layout.addWidget(BodyLabel("Название:", self))
        self.edit_name = LineEdit(self)
        self.edit_name.setPlaceholderText("Например: Моё любимое радио или Стрим")
        self.edit_name.setFixedHeight(32)
        layout.addWidget(self.edit_name)

        layout.addWidget(BodyLabel("URL аудиопотока или ссылки:", self))
        self.edit_url = LineEdit(self)
        self.edit_url.setPlaceholderText("YouTube, YouTube Shorts, YouTube Music, Twitch, MP3, AAC, Icecast...")
        self.edit_url.setFixedHeight(32)
        layout.addWidget(self.edit_url)

        layout.addWidget(BodyLabel("Жанр / Категория (необязательно):", self))
        self.edit_genre = LineEdit(self)
        self.edit_genre.setPlaceholderText("Например: Rock, Lofi, EDM, YouTube, Подкаст")
        self.edit_genre.setFixedHeight(32)
        layout.addWidget(self.edit_genre)

        hint = CaptionLabel("Поддерживаются радиостанции (Icecast, MP3, AAC), ссылки YouTube, YouTube Shorts и Twitch.", self)
        hint.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 11px;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = PushButton("Отмена", self)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_add = PrimaryPushButton(FluentIcon.ADD, "Добавить", self)
        btn_add.clicked.connect(self._validate)
        btn_row.addWidget(btn_add)
        layout.addLayout(btn_row)

    def _validate(self):
        if not self.edit_name.text().strip():
            QMessageBox.warning(self, "Внимание", "Введите название станции.")
            return
        if not self.edit_url.text().strip():
            QMessageBox.warning(self, "Внимание", "Введите URL аудиопотока или ссылку.")
            return
        self.accept()

    def get_data(self) -> Dict[str, str]:
        return {
            "name": self.edit_name.text().strip(),
            "url": clean_and_normalize_stream_url(self.edit_url.text().strip()),
            "genre": self.edit_genre.text().strip() or "Custom"
        }


class FluentStationCard(CardWidget):
    """Card for a single radio station preset."""

    def __init__(self, station_data: Dict[str, Any], on_play_cb, on_delete_cb, parent=None):
        super().__init__(parent)
        self.station_data = station_data
        self.on_play_cb = on_play_cb
        self.on_delete_cb = on_delete_cb
        self.setFixedHeight(68)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        icon_btn = TransparentToolButton(FluentIcon.MEGAPHONE, self)
        icon_btn.setFixedSize(36, 36)
        layout.addWidget(icon_btn)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        t_row = QHBoxLayout()
        t_row.setSpacing(8)
        lbl_name = BodyLabel(station_data.get("name", "Station"), self)
        lbl_name.setStyleSheet("font-weight: 600;")
        t_row.addWidget(lbl_name)

        lbl_genre = CaptionLabel(station_data.get("genre", "Radio").upper(), self)
        lbl_genre.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
            padding: 2px 6px;
            font-weight: 600;
        """)
        t_row.addWidget(lbl_genre)
        t_row.addStretch()
        info_col.addLayout(t_row)

        lbl_desc = CaptionLabel(station_data.get("description", station_data.get("url", "")), self)
        lbl_desc.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        info_col.addWidget(lbl_desc)

        layout.addLayout(info_col, stretch=1)

        btn_tune = PushButton(FluentIcon.PLAY, "В эфир", self)
        btn_tune.setFixedHeight(32)
        btn_tune.clicked.connect(lambda: on_play_cb(self.station_data))
        layout.addWidget(btn_tune)

    def _show_context_menu(self, pos):
        menu = RoundMenu(parent=self)

        act_play = Action(FluentIcon.PLAY, "Включить в эфир", self)
        act_play.triggered.connect(lambda: self.on_play_cb(self.station_data))
        menu.addAction(act_play)

        menu.addSeparator()

        act_del = Action(FluentIcon.DELETE, "Удалить радиостанцию", self)
        act_del.triggered.connect(lambda: self.on_delete_cb(self.station_data))
        menu.addAction(act_del)

        menu.exec(self.mapToGlobal(pos))


class FluentRadioInterface(QWidget):
    """Windows 11 Fluent Design Radio & Stream Interface with Thread-Safe Signals."""

    # Thread-safe Qt Signals for background audio worker updates
    sig_metadata_received = pyqtSignal(dict)
    sig_status_received = pyqtSignal(str)

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.setObjectName("radioInterface")

        self._last_played_url: Optional[str] = None
        self._last_played_name: Optional[str] = None
        self._is_user_scrubbing = False

        self._build_ui()
        self._load_target_devices()
        self._setup_stream_callbacks()

        # Connect thread-safe signals to GUI thread slots
        self.sig_metadata_received.connect(self._on_metadata_received_main_thread)
        self.sig_status_received.connect(self._on_engine_status_changed_main_thread)

        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self._on_timer_tick)
        self.progress_timer.start(500)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        # Header Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = TitleLabel("Интернет-Радио, YouTube & Стримы", self)
        lbl_sub = CaptionLabel(
            "Трансляция онлайн-радиостанций, YouTube, YouTube Shorts, Twitch и стримов для себя (динамики/наушники) и в микрофон собеседникам",
            self
        )
        lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        layout.addLayout(title_layout)

        # 1. Custom Stream / YouTube URL Input Card (Moved above player)
        card_custom = CardWidget(self)
        c_layout = QHBoxLayout(card_custom)
        c_layout.setContentsMargins(16, 12, 16, 12)
        c_layout.setSpacing(10)

        self.edit_url = LineEdit(card_custom)
        self.edit_url.setPlaceholderText("Вставьте ссылку: YouTube, YouTube Shorts, YouTube Music, Twitch, радио (mp3/aac)...")
        self.edit_url.setFixedHeight(34)
        self.edit_url.returnPressed.connect(self._play_custom_url)
        c_layout.addWidget(self.edit_url, stretch=1)

        self.btn_play_custom = PrimaryPushButton(FluentIcon.PLAY, "Запустить", card_custom)
        self.btn_play_custom.setFixedHeight(34)
        self.btn_play_custom.setToolTip("Запустить воспроизведение звука прямо сейчас")
        self.btn_play_custom.clicked.connect(lambda: self._play_custom_url(autoplay=True))
        c_layout.addWidget(self.btn_play_custom)

        self.btn_preview_custom = PushButton(FluentIcon.VIEW, "Посмотреть", card_custom)
        self.btn_preview_custom.setFixedHeight(34)
        self.btn_preview_custom.setToolTip("Загрузить информацию о видео в плеер без немедленного включения звука")
        self.btn_preview_custom.clicked.connect(lambda: self._play_custom_url(autoplay=False))
        c_layout.addWidget(self.btn_preview_custom)

        layout.addWidget(card_custom)

        # 2. Now Playing Player Card
        self.card_np = CardWidget(self)
        np_layout = QVBoxLayout(self.card_np)
        np_layout.setContentsMargins(20, 16, 20, 16)
        np_layout.setSpacing(10)

        # Header row: Station Name, Status, Playlist badge
        h_top = QHBoxLayout()
        h_top.setSpacing(8)

        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        self.lbl_station_name = SubtitleLabel("РАДИО: НЕ ВОСПРОИЗВОДИТСЯ", self.card_np)
        self.lbl_artist = CaptionLabel("", self.card_np)
        self.lbl_artist.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-weight: 600;")
        info_box.addWidget(self.lbl_station_name)
        info_box.addWidget(self.lbl_artist)
        h_top.addLayout(info_box, stretch=1)

        self.lbl_playlist_badge = CaptionLabel("", self.card_np)
        self.lbl_playlist_badge.setStyleSheet("""
            background-color: rgba(0, 153, 255, 0.15);
            border: 1px solid rgba(0, 153, 255, 0.4);
            border-radius: 4px;
            padding: 3px 8px;
            font-weight: 600;
            color: #00f2fe;
        """)
        self.lbl_playlist_badge.setVisible(False)
        h_top.addWidget(self.lbl_playlist_badge)

        self.lbl_status = CaptionLabel("Остановлено", self.card_np)
        self.lbl_status.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        h_top.addWidget(self.lbl_status)

        np_layout.addLayout(h_top)

        # Track title row
        self.lbl_track_title = BodyLabel("Выберите станцию из списка ниже или вставьте ссылку...", self.card_np)
        self.lbl_track_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #00b0ff;")
        np_layout.addWidget(self.lbl_track_title)

        # Timeline Slider & Duration row (for recorded audio / YouTube / YouTube Music)
        self.timeline_box = QWidget(self.card_np)
        tl_layout = QHBoxLayout(self.timeline_box)
        tl_layout.setContentsMargins(0, 0, 0, 0)
        tl_layout.setSpacing(10)

        self.lbl_curr_time = CaptionLabel("00:00", self.timeline_box)
        self.lbl_curr_time.setFixedWidth(40)
        tl_layout.addWidget(self.lbl_curr_time)

        self.slider_progress = TimelineSlider(Qt.Orientation.Horizontal, self.timeline_box)
        self.slider_progress.setRange(0, 1000)
        self.slider_progress.setValue(0)
        self.slider_progress.seekRequested.connect(self._on_slider_seek_requested)
        self.slider_progress.sliderMoved.connect(self._on_slider_moved)
        tl_layout.addWidget(self.slider_progress, stretch=1)

        self.lbl_total_time = CaptionLabel("00:00", self.timeline_box)
        self.lbl_total_time.setFixedWidth(40)
        tl_layout.addWidget(self.lbl_total_time)

        np_layout.addWidget(self.timeline_box)

        # Media Control Buttons row
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        # Playlist Prev
        self.btn_prev = TransparentToolButton(FluentIcon.SKIP_BACK, self.card_np)
        self.btn_prev.setFixedSize(34, 34)
        self.btn_prev.setToolTip("Предыдущий трек в плейлисте")
        self.btn_prev.clicked.connect(self._play_prev_track)
        self.btn_prev.setEnabled(False)
        btn_bar.addWidget(self.btn_prev)

        # Seek -10s
        self.btn_seek_back = PushButton(FluentIcon.SKIP_BACK, "-10с", self.card_np)
        self.btn_seek_back.setFixedHeight(32)
        self.btn_seek_back.setToolTip("Перемотать на 10 секунд назад")
        self.btn_seek_back.clicked.connect(lambda: self.engine.radio.seek_relative(-10.0))
        btn_bar.addWidget(self.btn_seek_back)

        # Main Play/Stop Toggle button: Starts as "Воспроизвести" (Play)
        self.btn_stop = PrimaryPushButton(FluentIcon.PLAY, "Воспроизвести", self.card_np)
        self.btn_stop.setFixedHeight(34)
        self.btn_stop.setFixedWidth(140)
        self.btn_stop.clicked.connect(self._toggle_play_pause)
        btn_bar.addWidget(self.btn_stop)

        # Seek +10s
        self.btn_seek_fwd = PushButton(FluentIcon.SKIP_FORWARD, "+10с", self.card_np)
        self.btn_seek_fwd.setFixedHeight(32)
        self.btn_seek_fwd.setToolTip("Перемотать на 10 секунд вперед")
        self.btn_seek_fwd.clicked.connect(lambda: self.engine.radio.seek_relative(10.0))
        btn_bar.addWidget(self.btn_seek_fwd)

        # Playlist Next
        self.btn_next = TransparentToolButton(FluentIcon.SKIP_FORWARD, self.card_np)
        self.btn_next.setFixedSize(34, 34)
        self.btn_next.setToolTip("Следующий трек в плейлисте")
        self.btn_next.clicked.connect(self._play_next_track)
        self.btn_next.setEnabled(False)
        btn_bar.addWidget(self.btn_next)

        btn_bar.addStretch()

        # Open in Browser button
        self.btn_open_browser = PushButton(FluentIcon.GLOBE, "В браузере", self.card_np)
        self.btn_open_browser.setFixedHeight(32)
        self.btn_open_browser.setToolTip("Открыть текущее видео или трансляцию в интернет-браузере")
        self.btn_open_browser.clicked.connect(self._open_url_in_browser)
        btn_bar.addWidget(self.btn_open_browser)

        np_layout.addLayout(btn_bar)

        layout.addWidget(self.card_np)

        # 3. Routing & Volume Control Card (Monitor / Mic switches + target device selector)
        card_vol = CardWidget(self)
        cv_main_layout = QVBoxLayout(card_vol)
        cv_main_layout.setContentsMargins(20, 16, 20, 16)
        cv_main_layout.setSpacing(14)

        lbl_vol_title = SubtitleLabel("Маршрутизация и громкость трансляции", card_vol)
        lbl_vol_title.setStyleSheet("font-size: 15px; font-weight: 600;")
        cv_main_layout.addWidget(lbl_vol_title)

        v_layout = QHBoxLayout()
        v_layout.setSpacing(24)

        # 3A. Monitor Channel ("Слышать самому")
        mon_col = QVBoxLayout()
        mon_col.setSpacing(6)

        mon_header = QHBoxLayout()
        mon_header.setSpacing(8)
        icon_mon = IconWidget(FluentIcon.VOLUME, card_vol)
        icon_mon.setFixedSize(16, 16)
        mon_header.addWidget(icon_mon)
        lbl_mon_head = BodyLabel("Слышать самому", card_vol)
        lbl_mon_head.setStyleSheet("font-weight: 600; font-size: 13px;")
        mon_header.addWidget(lbl_mon_head)
        mon_header.addStretch()

        self.switch_mon = SwitchButton(card_vol)
        self.switch_mon.setOnText("Вкл")
        self.switch_mon.setOffText("Выкл")
        mon_init_state = bool(self.cfg.get("radio_monitor_enabled", True))
        self.switch_mon.setChecked(mon_init_state)
        self.engine.radio_monitor_enabled = mon_init_state
        self.switch_mon.checkedChanged.connect(self._on_mon_switch_changed)
        mon_header.addWidget(self.switch_mon)
        mon_col.addLayout(mon_header)

        lbl_mon_hint = CaptionLabel("Воспроизводить стрим в ваших динамиках / наушниках", card_vol)
        lbl_mon_hint.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        mon_col.addWidget(lbl_mon_hint)

        init_mon_vol = int(self.cfg.get("radio_monitor_vol", 0.7) * 100)
        self.engine.radio_monitor_vol = init_mon_vol / 100.0
        self.lbl_mon = CaptionLabel(f"Громкость для себя: {init_mon_vol}%" if mon_init_state else "Отключено (звук не слышен лично вам)", card_vol)
        mon_col.addWidget(self.lbl_mon)

        self.slider_mon = Slider(Qt.Orientation.Horizontal, card_vol)
        self.slider_mon.setRange(0, 150)
        self.slider_mon.setValue(init_mon_vol)
        self.slider_mon.setEnabled(mon_init_state)
        self.slider_mon.valueChanged.connect(self._on_mon_vol)
        mon_col.addWidget(self.slider_mon)

        mon_col.addStretch()
        v_layout.addLayout(mon_col, stretch=1)

        # 3B. Mic Target Channel ("Транслировать в микрофон")
        mic_col = QVBoxLayout()
        mic_col.setSpacing(6)

        mic_header = QHBoxLayout()
        mic_header.setSpacing(8)
        icon_mic = IconWidget(FluentIcon.MICROPHONE, card_vol)
        icon_mic.setFixedSize(16, 16)
        mic_header.addWidget(icon_mic)
        lbl_mic_head = BodyLabel("Транслировать в микрофон", card_vol)
        lbl_mic_head.setStyleSheet("font-weight: 600; font-size: 13px;")
        mic_header.addWidget(lbl_mic_head)
        mic_header.addStretch()

        self.switch_mic = SwitchButton(card_vol)
        self.switch_mic.setOnText("Вкл")
        self.switch_mic.setOffText("Выкл")
        mic_init_state = bool(self.cfg.get("radio_mic_enabled", True))
        self.switch_mic.setChecked(mic_init_state)
        self.engine.radio_mic_enabled = mic_init_state
        self.switch_mic.checkedChanged.connect(self._on_mic_switch_changed)
        mic_header.addWidget(self.switch_mic)
        mic_col.addLayout(mic_header)

        lbl_mic_hint = CaptionLabel("Направлять в виртуальный кабель (Discord, игры, OBS)", card_vol)
        lbl_mic_hint.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        mic_col.addWidget(lbl_mic_hint)

        init_mic_vol = int(self.cfg.get("radio_mic_vol", 0.9) * 100)
        self.engine.radio_mic_vol = init_mic_vol / 100.0
        self.lbl_mic = CaptionLabel(f"Громкость в микрофон: {init_mic_vol}%" if mic_init_state else "Отключено (звук не идет в микрофон)", card_vol)
        mic_col.addWidget(self.lbl_mic)

        self.slider_mic = Slider(Qt.Orientation.Horizontal, card_vol)
        self.slider_mic.setRange(0, 150)
        self.slider_mic.setValue(init_mic_vol)
        self.slider_mic.setEnabled(mic_init_state)
        self.slider_mic.valueChanged.connect(self._on_mic_vol)
        mic_col.addWidget(self.slider_mic)

        lbl_target_mic = CaptionLabel("Устройство вывода в микрофон (целевой виртуальный кабель):", card_vol)
        lbl_target_mic.setStyleSheet("color: rgba(255, 255, 255, 0.55); margin-top: 4px;")
        mic_col.addWidget(lbl_target_mic)

        self.combo_target_mic = ComboBox(card_vol)
        self.combo_target_mic.setFixedHeight(32)
        self.combo_target_mic.setEnabled(mic_init_state)
        self.combo_target_mic.currentIndexChanged.connect(self._on_target_mic_changed)
        mic_col.addWidget(self.combo_target_mic)

        v_layout.addLayout(mic_col, stretch=1)
        cv_main_layout.addLayout(v_layout)

        layout.addWidget(card_vol)

        # 4. Presets List Card
        card_list_header = QHBoxLayout()
        lbl_list = SubtitleLabel("Популярные радиостанции и стримы", self)
        lbl_list.setStyleSheet("font-size: 15px; margin-top: 4px;")
        card_list_header.addWidget(lbl_list)
        card_list_header.addStretch()

        self.btn_add_st = PushButton(FluentIcon.ADD, "Добавить станцию", self)
        self.btn_add_st.setFixedHeight(32)
        self.btn_add_st.clicked.connect(self._prompt_add_station)
        card_list_header.addWidget(self.btn_add_st)
        layout.addLayout(card_list_header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        self.stations_container = QWidget()
        self.s_layout = QVBoxLayout(self.stations_container)
        self.s_layout.setContentsMargins(0, 0, 10, 0)
        self.s_layout.setSpacing(8)

        scroll.setWidget(self.stations_container)
        layout.addWidget(scroll, stretch=1)

        self._refresh_stations_list()

    def _setup_stream_callbacks(self):
        # Thread-safe redirection: worker thread emits signal, Qt dispatches to main GUI thread!
        self.engine.radio.on_metadata_changed = lambda meta: self.sig_metadata_received.emit(meta)
        self.engine.radio.on_status_changed = lambda status: self.sig_status_received.emit(status)

    def _refresh_stations_list(self):
        while self.s_layout.count():
            item = self.s_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for s in self.cfg.stations:
            card = FluentStationCard(s, self._play_station, self._delete_station, self.stations_container)
            self.s_layout.addWidget(card)

        self.s_layout.addStretch()

    def _prompt_add_station(self):
        dlg = AddStationDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.cfg.add_station(name=data["name"], url=data["url"], genre=data["genre"])
            self._refresh_stations_list()

    def _delete_station(self, station_data: Dict[str, Any]):
        name = station_data.get("name", "Радиостанция")
        s_id = station_data.get("id")
        reply = QMessageBox.question(
            self,
            "Удаление радиостанции",
            f"Вы уверены, что хотите удалить «{name}» из списка?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if s_id:
                self.cfg.remove_station(s_id)
            else:
                self.cfg.stations = [s for s in self.cfg.stations if s.get("name") != name]
                self.cfg.save_stations()
            self._refresh_stations_list()

    def _play_station(self, station_data: Dict[str, Any]):
        url = station_data.get("url", "")
        name = station_data.get("name", "Online Radio")
        if not url:
            return
        self._last_played_url = url
        self._last_played_name = name

        self.lbl_station_name.setText(f"РАДИО: {name.upper()}")
        self.lbl_artist.setText("")
        self.lbl_status.setText("Подключение...")
        self.lbl_track_title.setText("Буферизация потока...")
        self._update_toggle_btn(playing=True)

        self.engine.radio.play(url, name)

    def _play_custom_url(self, autoplay: bool = True):
        raw_url = self.edit_url.text().strip()
        if not raw_url:
            InfoBar.warning(
                title="Не указана ссылка",
                content="Введите корректный URL видео, стрима или радио.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3500
            )
            return

        url = clean_and_normalize_stream_url(raw_url)
        name = "Пользовательский поток"
        if "shorts" in raw_url.lower():
            name = "YouTube Shorts"
        elif "youtube.com" in url or "youtu.be" in url:
            name = "YouTube"
        elif "music.youtube.com" in url:
            name = "YouTube Music"
        elif "twitch.tv" in url:
            name = "Twitch"

        self._last_played_url = url
        self._last_played_name = name

        self.lbl_station_name.setText(f"СТРИМ: {name.upper()}")
        self.lbl_artist.setText("")

        self.btn_play_custom.setEnabled(False)
        if hasattr(self, "btn_preview_custom"):
            self.btn_preview_custom.setEnabled(False)

        if autoplay:
            self.lbl_status.setText("Подключение к медиасерверу...")
            self.lbl_track_title.setText("Анализ и буферизация потока...")
            self._update_toggle_btn(playing=True)
            self.engine.radio.play(url, name)
        else:
            self.lbl_status.setText("Загрузка информации...")
            self.lbl_track_title.setText("Получение информации о видео...")
            self._update_toggle_btn(playing=False)
            self.engine.radio.prepare(url, name)

    def _open_url_in_browser(self):
        """Opens the stream or video URL in the user's default web browser."""
        raw_url = self.edit_url.text().strip()
        if not raw_url:
            raw_url = getattr(self.engine.radio, "current_web_url", None) or self.engine.radio.current_url or self._last_played_url
        if not raw_url:
            InfoBar.warning(
                title="Нет ссылки",
                content="Вставьте ссылку на видео или трансляцию, чтобы открыть её в браузере.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3500
            )
            return

        url = raw_url
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        QDesktopServices.openUrl(QUrl(url))

    def _toggle_play_pause(self):
        """Toggles between 'Остановить' and 'Воспроизвести/Продолжить'."""
        if self.engine.radio.is_playing:
            # User wants to STOP / PAUSE
            self._last_played_url = self.engine.radio.current_url or self._last_played_url
            self._last_played_name = self.engine.radio.current_name or self._last_played_name
            self.engine.radio.pause()
            self._update_toggle_btn(playing=False)
            self.lbl_status.setText("Приостановлено")
        else:
            # User wants to RESUME / PLAY
            target_url = self.engine.radio.current_url or self._last_played_url
            target_name = self.engine.radio.current_name or self._last_played_name
            if target_url:
                self._update_toggle_btn(playing=True)
                self.lbl_status.setText("Подключение...")
                if getattr(self.engine.radio, "is_paused", False):
                    self.engine.radio.resume()
                else:
                    self.engine.radio.play(target_url, target_name or "Пользовательский поток")
            else:
                QMessageBox.information(self, "Информация", "Выберите станцию или введите URL для воспроизведения.")

    def stop_radio(self):
        """Full stop requested by parent or hotkey."""
        self._last_played_url = self.engine.radio.current_url or self._last_played_url
        self._last_played_name = self.engine.radio.current_name or self._last_played_name
        self.engine.radio.stop()
        self._update_toggle_btn(playing=False)
        self.lbl_station_name.setText("РАДИО: НЕ ВОСПРОИЗВОДИТСЯ")
        self.lbl_artist.setText("")
        self.lbl_status.setText("Остановлено")
        self.lbl_track_title.setText("Выберите станцию из списка или вставьте ссылку...")

    def _update_toggle_btn(self, playing: bool):
        if playing:
            self.btn_stop.setText("Остановить")
            self.btn_stop.setIcon(FluentIcon.PAUSE)
        else:
            if getattr(self.engine.radio, "is_paused", False):
                self.btn_stop.setText("Продолжить")
            else:
                self.btn_stop.setText("Воспроизвести")
            self.btn_stop.setIcon(FluentIcon.PLAY)

    def _play_next_track(self):
        self.engine.radio.play_next()

    def _play_prev_track(self):
        self.engine.radio.play_prev()

    def _on_metadata_received_main_thread(self, meta: Dict[str, Any]):
        """Executed strictly on the Qt GUI main thread via sig_metadata_received."""
        title = meta.get("title") or "Онлайн-поток"
        artist = meta.get("artist") or ""
        duration = meta.get("duration")
        is_live = meta.get("is_live", True)
        playlist_count = meta.get("playlist_count", 0)
        playlist_index = meta.get("playlist_index", 0)

        self.lbl_track_title.setText(title)
        self.lbl_artist.setText(artist if artist else "")

        # Playlist badge
        if playlist_count > 1:
            self.lbl_playlist_badge.setText(f"Плейлист: {playlist_index + 1} / {playlist_count}")
            self.lbl_playlist_badge.setVisible(True)
            self.btn_prev.setEnabled(playlist_index > 0)
            self.btn_next.setEnabled(playlist_index < playlist_count - 1)
        else:
            self.lbl_playlist_badge.setVisible(False)
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)

        # Seeking buttons visibility/enablement
        seek_enabled = not is_live and (duration is not None and duration > 0)
        self.btn_seek_back.setEnabled(seek_enabled)
        self.btn_seek_fwd.setEnabled(seek_enabled)
        self.slider_progress.setEnabled(seek_enabled)

        if duration and duration > 0:
            m = int(duration) // 60
            s = int(duration) % 60
            self.lbl_total_time.setText(f"{m:02d}:{s:02d}")
        else:
            self.lbl_total_time.setText("LIVE")

    def _on_engine_status_changed_main_thread(self, status: str):
        """Executed strictly on the Qt GUI main thread via sig_status_received."""
        self.lbl_status.setText(status)
        self.btn_play_custom.setEnabled(True)
        if hasattr(self, "btn_preview_custom"):
            self.btn_preview_custom.setEnabled(True)

        if status in ("В эфире", "Воспроизведение"):
            self._update_toggle_btn(playing=True)
        elif status in ("Остановлено", "Приостановлено"):
            self._update_toggle_btn(playing=False)
        elif status == "Готов к воспроизведению":
            self._update_toggle_btn(playing=False)
        elif "Ошибка" in status:
            self._update_toggle_btn(playing=False)
            self.lbl_track_title.setText("Не удалось загрузить поток. Нажмите «В браузере», чтобы открыть в интернете.")
            InfoBar.warning(
                title="Внимание к потоку",
                content=f"{status}. Возможно, сервис заблокирован или временно недоступен. Вы можете открыть его кнопкой «В браузере».",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=6000
            )

    def _on_slider_moved(self, val: int):
        duration = self.engine.radio.duration_sec
        if duration and duration > 0:
            curr_pos = (val / float(self.slider_progress.maximum())) * duration
            m = int(curr_pos) // 60
            s = int(curr_pos) % 60
            self.lbl_curr_time.setText(f"{m:02d}:{s:02d}")

    def _on_slider_seek_requested(self, ratio: float):
        duration = self.engine.radio.duration_sec
        if duration and duration > 0:
            target_sec = ratio * duration
            self.engine.radio.seek_to(target_sec)
            m = int(target_sec) // 60
            s = int(target_sec) % 60
            self.lbl_curr_time.setText(f"{m:02d}:{s:02d}")

    def _on_timer_tick(self):
        if self.engine.radio.is_playing:
            curr_pos = self.engine.radio.current_pos_sec
            duration = self.engine.radio.duration_sec

            if not getattr(self.slider_progress, "is_scrubbing", False) and duration and duration > 0:
                ratio = min(1.0, curr_pos / float(duration))
                self.slider_progress.setValue(int(ratio * 1000))

            if not getattr(self.slider_progress, "is_scrubbing", False):
                m = int(curr_pos) // 60
                s = int(curr_pos) % 60
                self.lbl_curr_time.setText(f"{m:02d}:{s:02d}")

    def _load_target_devices(self):
        """Loads available audio output devices for target microphone into combo box."""
        devices = self.engine.get_audio_devices()
        self.combo_target_mic.blockSignals(True)
        self.combo_target_mic.clear()
        self.combo_target_mic.addItem("-- Без трансляции в микрофон --", userData=None)

        saved_target = self.cfg.get("mic_target_device_id")
        selected_index = 0
        cable_wasapi_idx = None
        cable_any_idx = None

        for d in devices["outputs"]:
            idx = self.combo_target_mic.count()
            self.combo_target_mic.addItem(d["name"], userData=d["id"])
            if saved_target is not None and d["id"] == saved_target:
                selected_index = idx

            name_lower = d["name"].lower()
            api_lower = d.get("hostapi", "").lower()
            if "cable input" in name_lower or "vb-audio" in name_lower or "virtual" in name_lower:
                if "wasapi" in api_lower and cable_wasapi_idx is None:
                    cable_wasapi_idx = idx
                elif cable_any_idx is None:
                    cable_any_idx = idx

        # Auto-select virtual cable (microphone target) by default if nothing saved
        if (saved_target is None or selected_index == 0):
            best_idx = cable_wasapi_idx if cable_wasapi_idx is not None else cable_any_idx
            if best_idx is not None:
                selected_index = best_idx
                auto_dev_id = self.combo_target_mic.itemData(selected_index)
                self.cfg.set("mic_target_device_id", auto_dev_id)
                self.engine.mic_target_device_id = auto_dev_id
                # Ensure engine streams know about target device
                if self.engine.mic_target_stream is None and auto_dev_id is not None:
                    self.engine.initialize_streams(
                        monitor_device=self.engine.monitor_device_id,
                        mic_target_device=auto_dev_id,
                        mic_input_device=self.engine.mic_input_device_id
                    )

        self.combo_target_mic.setCurrentIndex(selected_index)
        self.combo_target_mic.blockSignals(False)

    def _on_target_mic_changed(self, index: int):
        dev_id = self.combo_target_mic.itemData(index)
        if dev_id == self.engine.mic_target_device_id:
            return
        self.engine.mic_target_device_id = dev_id
        self.cfg.set("mic_target_device_id", dev_id)
        # Reinitialize audio streams with new target device
        self.engine.initialize_streams(
            monitor_device=self.engine.monitor_device_id,
            mic_target_device=dev_id,
            mic_input_device=self.engine.mic_input_device_id
        )

    def _on_mon_switch_changed(self, is_checked: bool):
        self.engine.radio_monitor_enabled = is_checked
        self.cfg.set("radio_monitor_enabled", is_checked)
        self.slider_mon.setEnabled(is_checked)
        if is_checked:
            self.lbl_mon.setText(f"Громкость для себя: {self.slider_mon.value()}%")
        else:
            self.lbl_mon.setText("Отключено (звук не слышен лично вам)")

    def _on_mic_switch_changed(self, is_checked: bool):
        self.engine.radio_mic_enabled = is_checked
        self.cfg.set("radio_mic_enabled", is_checked)
        self.slider_mic.setEnabled(is_checked)
        self.combo_target_mic.setEnabled(is_checked)
        if is_checked:
            self.lbl_mic.setText(f"Громкость в микрофон: {self.slider_mic.value()}%")
        else:
            self.lbl_mic.setText("Отключено (звук не идет в микрофон)")

    def _on_mon_vol(self, val: int):
        if self.switch_mon.isChecked():
            self.lbl_mon.setText(f"Громкость для себя: {val}%")
        self.engine.radio_monitor_vol = val / 100.0
        self.cfg.set("radio_monitor_vol", self.engine.radio_monitor_vol)

    def _on_mic_vol(self, val: int):
        if self.switch_mic.isChecked():
            self.lbl_mic.setText(f"Громкость в микрофон: {val}%")
        self.engine.radio_mic_vol = val / 100.0
        self.cfg.set("radio_mic_vol", self.engine.radio_mic_vol)
