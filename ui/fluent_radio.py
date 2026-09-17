"""
Fluent Design Online Radio & Web Stream Interface for SoundFlow Studio.
Features Windows 11 Fluent cards, YouTube, YouTube Shorts, YouTube Music, Twitch,
Play/Pause toggle ('Остановить' <-> 'Продолжить'), [-10s] / [+10s] seeking,
thread-safe Qt signals, track time display, and playlist auto-advance.
"""

import json
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional, List
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl, QThread, QRectF
from PyQt6.QtGui import (
    QDesktopServices, QMouseEvent, QColor, QPixmap, QPainter,
    QPainterPath, QLinearGradient, QPen, QFont
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QMessageBox, QDialog, QStackedWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QApplication
)
from qfluentwidgets import (
    CardWidget, PrimaryPushButton, PushButton, TransparentPushButton, TransparentToolButton,
    LineEdit, Slider, TitleLabel, SubtitleLabel, BodyLabel,
    CaptionLabel, FluentIcon, RoundMenu, Action, SwitchButton, ComboBox,
    InfoBar, InfoBarPosition, IconWidget, SegmentedWidget, TableWidget,
    SearchLineEdit, IndeterminateProgressBar, TextEdit
)

from core.radio_streamer import clean_and_normalize_stream_url
from .widgets import VUMeterWidget
from core.i18n import tr


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


class ThumbnailDownloadThread(QThread):
    """Background non-blocking thread to fetch stream thumbnail images."""
    sig_loaded = pyqtSignal(str, bytes)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            req = urllib.request.Request(
                self.url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
                self.sig_loaded.emit(self.url, data)
        except Exception:
            pass


class StreamThumbnailWidget(QWidget):
    """Modern 16:9 rounded thumbnail preview for YouTube videos, streams, and radio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 68)
        self._pixmap: Optional[QPixmap] = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_pixmap(self, pixmap: Optional[QPixmap]):
        self._pixmap = pixmap
        self.update()

    def set_default(self):
        self._pixmap = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 8.0, 8.0)
        painter.setClipPath(path)

        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            painter.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
        else:
            grad = QLinearGradient(0, 0, self.width(), self.height())
            grad.setColorAt(0.0, QColor("#1e293b"))
            grad.setColorAt(1.0, QColor("#0f172a"))
            painter.fillRect(rect, grad)

            painter.setPen(QColor(255, 255, 255, 120))
            f = painter.font()
            f.setPointSize(20)
            painter.setFont(f)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "📻")

        # Subtle elegant border
        painter.setClipping(False)
        painter.setPen(QPen(QColor(255, 255, 255, 35), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0), 8.0, 8.0)


class StreamDebugDialog(QDialog):
    """Dialog showing technical diagnostics of the audio stream with one-click copy."""

    def __init__(self, radio_streamer, parent=None):
        super().__init__(parent)
        self.radio = radio_streamer
        self.setWindowTitle(tr("radio_err_dialog_title", "Диагностика медиапотока"))
        self.setFixedSize(620, 460)
        self.setStyleSheet("background-color: #202020; color: #ffffff;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel(tr("radio_dlg_debug_subtitle", "Техническая информация об ошибке потока"), self))

        name_str = self.radio.current_name or "N/A"
        url_str = self.radio.current_url or "N/A"
        info_text = f"{tr('radio_diagnostic_name', name=name_str)}\nURL: {url_str}"
        lbl_info = CaptionLabel(info_text, self)
        lbl_info.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 12px;")
        layout.addWidget(lbl_info)

        self.edit_details = TextEdit(self)
        self.edit_details.setReadOnly(True)
        self.edit_details.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 11px; background-color: #181818; color: #e0e0e0; border: 1px solid #333333; border-radius: 6px;")
        raw_error = self.radio.get_last_error_details()
        self.edit_details.setPlainText(raw_error)
        layout.addWidget(self.edit_details, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_copy = PrimaryPushButton(FluentIcon.COPY, tr("radio_dlg_btn_copy_clip", "Копировать в буфер"), self)
        self.btn_copy.setFixedHeight(32)
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(self.btn_copy)

        btn_row.addStretch()

        btn_close = PushButton(tr("common_close", "Закрыть"), self)
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _copy_to_clipboard(self):
        curr_url = self.radio.current_url or "Unknown URL"
        full_text = f"SoundFlow Studio Stream Diagnostic:\n{tr('radio_diagnostic_name', name=self.radio.current_name or 'N/A')}\nURL: {curr_url}\n\n{self.edit_details.toPlainText()}"
        QApplication.clipboard().setText(full_text)
        InfoBar.success(
            title=tr("radio_copied_title"),
            content=tr("radio_copied_msg"),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=2500
        )


class RadioCatalogSearchThread(QThread):
    sig_results_ready = pyqtSignal(list)
    sig_search_error = pyqtSignal(str)

    def __init__(self, countrycode: str = "RU", tag: str = "", query: str = "", parent=None):
        super().__init__(parent)
        self.countrycode = countrycode
        self.tag = tag
        self.query = query

    def run(self):
        params = {
            "limit": 60,
            "hidebroken": "true",
            "order": "votes",
            "reverse": "true"
        }
        if self.countrycode:
            params["countrycode"] = self.countrycode
        if self.tag:
            params["tag"] = self.tag
        if self.query:
            params["name"] = self.query

        query_string = urllib.parse.urlencode(params)
        servers = [
            "https://de1.api.radio-browser.info",
            "https://all.api.radio-browser.info",
            "https://nl1.api.radio-browser.info",
            "https://at1.api.radio-browser.info"
        ]

        last_err = ""
        for srv in servers:
            api_url = f"{srv}/json/stations/search?{query_string}"
            try:
                req = urllib.request.Request(
                    api_url,
                    headers={"User-Agent": "SoundFlowStudio/1.0"}
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    if resp.status == 200:
                        raw_data = resp.read().decode("utf-8")
                        stations = json.loads(raw_data)
                        self.sig_results_ready.emit(stations)
                        return
            except Exception as e:
                last_err = str(e)
                continue

        self.sig_search_error.emit(last_err or tr("radio_catalog_connect_err", "Не удалось подключиться к серверу каталога радиостанций."))


class AddStationDialog(QDialog):
    """Dialog to search and add radio stations from Radio Browser API or manual URL input."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("radio_dlg_add_title", "Добавить радиостанцию или стрим"))
        self.setMinimumSize(750, 540)
        self.setStyleSheet("background-color: #202020; color: #ffffff;")

        self._selected_data: Optional[Dict[str, str]] = None
        self._search_thread: Optional[RadioCatalogSearchThread] = None
        self._current_results: List[Dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title
        layout.addWidget(SubtitleLabel(tr("radio_dlg_add_subtitle", "Добавить радиостанцию или медиапоток"), self))

        # Segmented Navigation
        self.seg_nav = SegmentedWidget(self)
        self.seg_nav.addItem(routeKey="catalog", text=tr("radio_dlg_tab_catalog", "Каталог радиостанций (Radio-Browser)"), onClick=lambda: self.stack.setCurrentIndex(0), icon=FluentIcon.GLOBE)
        self.seg_nav.addItem(routeKey="manual", text=tr("radio_dlg_tab_manual", "Ввести вручную (URL / YouTube)"), onClick=lambda: self.stack.setCurrentIndex(1), icon=FluentIcon.EDIT)
        layout.addWidget(self.seg_nav)

        # Stacked Widget
        self.stack = QStackedWidget(self)

        # PAGE 0: Catalog
        page_cat = QWidget(self)
        cat_layout = QVBoxLayout(page_cat)
        cat_layout.setContentsMargins(0, 8, 0, 0)
        cat_layout.setSpacing(10)

        # Filter row
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        # Country combo
        self.combo_country = ComboBox(page_cat)
        self.combo_country.setFixedWidth(145)
        countries = [
            (tr("country_ru", "Россия (RU)"), "RU"),
            (tr("country_all", "Все страны"), ""),
            (tr("country_by", "Беларусь (BY)"), "BY"),
            (tr("country_kz", "Казахстан (KZ)"), "KZ"),
            (tr("country_us", "США (US)"), "US"),
            (tr("country_de", "Германия (DE)"), "DE"),
            (tr("country_gb", "Великобритания (GB)"), "GB"),
            (tr("country_fr", "Франция (FR)"), "FR"),
            (tr("country_ua", "Украина (UA)"), "UA"),
            (tr("country_pl", "Польша (PL)"), "PL")
        ]
        for name, code in countries:
            self.combo_country.addItem(name, userData=code)
        filter_layout.addWidget(self.combo_country)

        # Genre combo
        self.combo_genre = ComboBox(page_cat)
        self.combo_genre.setFixedWidth(155)
        genres = [
            (tr("genre_all", "Все жанры"), ""),
            (tr("genre_pop", "Поп / Топ-хиты"), "pop"),
            (tr("genre_rock", "Рок / Rock"), "rock"),
            (tr("genre_dance", "Клубная / Dance"), "dance"),
            (tr("genre_edm", "Электроника / EDM"), "electronic"),
            (tr("genre_lofi", "Lofi / Chillout"), "lofi"),
            (tr("genre_synthwave", "Ретровейв / Synth"), "synthwave"),
            (tr("genre_retro", "Ретро / 80-е"), "retro"),
            (tr("genre_jazz", "Джаз / Блюз"), "jazz"),
            (tr("genre_classical", "Классика"), "classical"),
            (tr("genre_hiphop", "Хип-хоп / Рэп"), "hiphop"),
            (tr("genre_news", "Новости / Разговорное"), "news"),
            (tr("genre_metal", "Метал"), "metal"),
            (tr("genre_ambient", "Релакс / Ambient"), "ambient")
        ]
        for name, code in genres:
            self.combo_genre.addItem(name, userData=code)
        filter_layout.addWidget(self.combo_genre)

        # Search line edit
        self.edit_catalog_query = SearchLineEdit(page_cat)
        self.edit_catalog_query.setPlaceholderText(tr("radio_catalog_search_placeholder", "Поиск по названию станции..."))
        self.edit_catalog_query.returnPressed.connect(self._do_catalog_search)
        filter_layout.addWidget(self.edit_catalog_query, stretch=1)

        # Search button
        self.btn_search = PrimaryPushButton(FluentIcon.SEARCH, tr("radio_dlg_btn_search", "Найти"), page_cat)
        self.btn_search.setFixedHeight(32)
        self.btn_search.clicked.connect(self._do_catalog_search)
        filter_layout.addWidget(self.btn_search)

        cat_layout.addLayout(filter_layout)

        # Progress bar
        self.progress_bar = IndeterminateProgressBar(page_cat)
        self.progress_bar.setVisible(False)
        cat_layout.addWidget(self.progress_bar)

        # Results table
        self.table = TableWidget(page_cat)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            tr("radio_col_name", "Станция"),
            tr("radio_col_genre", "Жанры / Теги"),
            tr("radio_col_country", "Страна"),
            tr("radio_col_bitrate", "Битрейт")
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(0, 220)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        cat_layout.addWidget(self.table, stretch=1)

        # Bottom catalog action bar
        cat_bottom = QHBoxLayout()
        self.lbl_found_info = CaptionLabel(tr("radio_dlg_prompt_search", "Нажмите «Найти» для загрузки станций"), page_cat)
        self.lbl_found_info.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        cat_bottom.addWidget(self.lbl_found_info)
        cat_bottom.addStretch()

        self.btn_add_from_catalog = PrimaryPushButton(FluentIcon.ADD, tr("radio_dlg_btn_add_selected", "Добавить в мои станции"), page_cat)
        self.btn_add_from_catalog.setFixedHeight(32)
        self.btn_add_from_catalog.clicked.connect(self._add_selected_catalog_station)
        cat_bottom.addWidget(self.btn_add_from_catalog)

        btn_close_cat = PushButton(tr("common_close", "Закрыть"), page_cat)
        btn_close_cat.setFixedHeight(32)
        btn_close_cat.clicked.connect(self.reject)
        cat_bottom.addWidget(btn_close_cat)

        cat_layout.addLayout(cat_bottom)
        self.stack.addWidget(page_cat)

        # PAGE 1: Manual entry
        page_man = QWidget(self)
        man_layout = QVBoxLayout(page_man)
        man_layout.setContentsMargins(0, 12, 0, 0)
        man_layout.setSpacing(12)

        man_layout.addWidget(BodyLabel(tr("radio_dlg_name_label", "Название станции или стрима:"), page_man))
        self.edit_name = LineEdit(page_man)
        self.edit_name.setPlaceholderText(tr("radio_dlg_name_placeholder", "Например: Моё любимое радио или YouTube стрим"))
        self.edit_name.setFixedHeight(32)
        man_layout.addWidget(self.edit_name)

        man_layout.addWidget(BodyLabel(tr("radio_dlg_url_label", "URL аудиопотока или ссылки:"), page_man))
        self.edit_url = LineEdit(page_man)
        self.edit_url.setPlaceholderText("YouTube, YouTube Shorts, Twitch, MP3, AAC, Icecast, m3u8...")
        self.edit_url.setFixedHeight(32)
        man_layout.addWidget(self.edit_url)

        man_layout.addWidget(BodyLabel(tr("radio_dlg_genre_label", "Жанр / Категория (необязательно):"), page_man))
        self.edit_genre = LineEdit(page_man)
        self.edit_genre.setPlaceholderText(tr("radio_dlg_genre_placeholder", "Например: Rock, Lofi, EDM, Подкаст"))
        self.edit_genre.setFixedHeight(32)
        man_layout.addWidget(self.edit_genre)

        hint = CaptionLabel(tr("radio_dlg_hint", "Поддерживаются онлайн-радиостанции (Icecast, MP3, AAC, HLS), ссылки YouTube, YouTube Shorts и Twitch."), page_man)
        hint.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 11px;")
        man_layout.addWidget(hint)

        man_layout.addStretch()

        btn_row_man = QHBoxLayout()
        btn_row_man.addStretch()
        btn_cancel_man = PushButton(tr("common_cancel", "Отмена"), page_man)
        btn_cancel_man.setFixedHeight(32)
        btn_cancel_man.clicked.connect(self.reject)
        btn_row_man.addWidget(btn_cancel_man)

        btn_add_man = PrimaryPushButton(FluentIcon.ADD, tr("common_add", "Добавить"), page_man)
        btn_add_man.setFixedHeight(32)
        btn_add_man.clicked.connect(self._validate_manual)
        btn_row_man.addWidget(btn_add_man)

        man_layout.addLayout(btn_row_man)
        self.stack.addWidget(page_man)

        layout.addWidget(self.stack, stretch=1)

        # Filters changed trigger auto-search
        self.combo_country.currentIndexChanged.connect(self._do_catalog_search)
        self.combo_genre.currentIndexChanged.connect(self._do_catalog_search)

        # Initial search on show
        QTimer.singleShot(100, self._do_catalog_search)

    def _do_catalog_search(self):
        code = self.combo_country.currentData() or ""
        tag = self.combo_genre.currentData() or ""
        query = self.edit_catalog_query.text().strip()

        self.btn_search.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.lbl_found_info.setText(tr("radio_dlg_searching", "Поиск станций в каталоге..."))

        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.terminate()

        self._search_thread = RadioCatalogSearchThread(countrycode=code, tag=tag, query=query, parent=self)
        self._search_thread.sig_results_ready.connect(self._on_catalog_results)
        self._search_thread.sig_search_error.connect(self._on_catalog_error)
        self._search_thread.start()

    def _on_catalog_results(self, stations: List[Dict[str, Any]]):
        self.progress_bar.setVisible(False)
        self.btn_search.setEnabled(True)
        self._current_results = stations
        self.table.setRowCount(0)

        if not stations:
            self.lbl_found_info.setText(tr("radio_dlg_not_found", "Станций не найдено. Попробуйте изменить параметры поиска."))
            return

        self.lbl_found_info.setText(tr("radio_dlg_found_fmt", count=len(stations)))
        self.table.setRowCount(len(stations))

        for row, st in enumerate(stations):
            name_item = QTableWidgetItem(st.get("name", "Unknown"))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            tags_item = QTableWidgetItem(st.get("tags", ""))
            tags_item.setFlags(tags_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            country_item = QTableWidgetItem(st.get("country", ""))
            country_item.setFlags(country_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            bitrate = st.get("bitrate", 0)
            bitrate_str = f"{bitrate} kbps" if bitrate > 0 else "Auto"
            bitrate_item = QTableWidgetItem(bitrate_str)
            bitrate_item.setFlags(bitrate_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, tags_item)
            self.table.setItem(row, 2, country_item)
            self.table.setItem(row, 3, bitrate_item)

        if len(stations) > 0:
            self.table.selectRow(0)

    def _on_catalog_error(self, err: str):
        self.progress_bar.setVisible(False)
        self.btn_search.setEnabled(True)
        self.lbl_found_info.setText(tr("radio_dlg_err_fmt", err=err))

    def _on_table_double_clicked(self, item):
        self._add_selected_catalog_station()

    def _add_selected_catalog_station(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._current_results):
            QMessageBox.warning(self, tr("warning", "Внимание"), tr("radio_dlg_warn_select", "Выберите станцию из списка для добавления."))
            return

        st = self._current_results[row]
        stream_url = st.get("url_resolved") or st.get("url", "")
        if not stream_url:
            QMessageBox.warning(self, tr("warning", "Внимание"), tr("radio_dlg_warn_no_url", "У данной станции отсутствует рабочий URL."))
            return

        self._selected_data = {
            "name": st.get("name", tr("radio_station_name_fallback", "Радиостанция")).strip(),
            "url": stream_url.strip(),
            "genre": st.get("tags", "").replace(",", " / ").strip() or "Online Radio"
        }
        self.accept()

    def _validate_manual(self):
        if not self.edit_name.text().strip():
            QMessageBox.warning(self, tr("warning", "Внимание"), tr("radio_dlg_warn_no_name", "Введите название станции."))
            return
        if not self.edit_url.text().strip():
            QMessageBox.warning(self, tr("warning", "Внимание"), tr("radio_dlg_warn_no_stream_url", "Введите URL аудиопотока или ссылку."))
            return

        self._selected_data = {
            "name": self.edit_name.text().strip(),
            "url": clean_and_normalize_stream_url(self.edit_url.text().strip()),
            "genre": self.edit_genre.text().strip() or tr("radio_custom_genre", "Пользовательская")
        }
        self.accept()

    def get_data(self) -> Dict[str, str]:
        return self._selected_data or {}


class FluentStationCard(CardWidget):
    """Card for a single radio station preset with synchronized play/pause toggle."""

    def __init__(self, station_data: Dict[str, Any], on_play_cb, on_delete_cb, parent=None):
        super().__init__(parent)
        self.station_data = station_data
        self.on_play_cb = on_play_cb
        self.on_delete_cb = on_delete_cb
        self.is_currently_playing = False
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

        self.btn_tune = PushButton(FluentIcon.PLAY, tr("radio_btn_on_air", "В эфир"), self)
        self.btn_tune.setFixedHeight(32)
        self.btn_tune.clicked.connect(lambda: self.on_play_cb(self.station_data))
        layout.addWidget(self.btn_tune)

    def set_playing_state(self, is_playing: bool):
        """Switches the card's button between 'В эфир' (Play) and 'Пауза' (Pause)."""
        self.is_currently_playing = is_playing
        if is_playing:
            self.btn_tune.setText(tr("radio_btn_pause_st", "Пауза"))
            self.btn_tune.setIcon(FluentIcon.PAUSE)
            self.btn_tune.setToolTip(tr("radio_tooltip_pause_st", "Приостановить воспроизведение этой радиостанции"))
        else:
            self.btn_tune.setText(tr("radio_btn_on_air", "В эфир"))
            self.btn_tune.setIcon(FluentIcon.PLAY)
            self.btn_tune.setToolTip(tr("radio_tooltip_play_st", "Включить эту радиостанцию в эфир"))

    def _show_context_menu(self, pos):
        menu = RoundMenu(parent=self)

        play_text = tr("radio_btn_pause_st", "Приостановить эфир") if self.is_currently_playing else tr("radio_btn_on_air", "Включить в эфир")
        play_icon = FluentIcon.PAUSE if self.is_currently_playing else FluentIcon.PLAY
        act_play = Action(play_icon, play_text, self)
        act_play.triggered.connect(lambda: self.on_play_cb(self.station_data))
        menu.addAction(act_play)

        menu.addSeparator()

        act_del = Action(FluentIcon.DELETE, tr("radio_act_delete_station", "Удалить радиостанцию"), self)
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
        self.station_cards: List[FluentStationCard] = []
        self._thumb_cache: Dict[str, QPixmap] = {}
        self._thumb_thread: Optional[ThumbnailDownloadThread] = None

        self._build_ui()
        self._load_target_devices()
        self._setup_stream_callbacks()

        # Connect thread-safe signals to GUI thread slots
        self.sig_metadata_received.connect(self._on_metadata_received_main_thread)
        self.sig_status_received.connect(self._on_engine_status_changed_main_thread)

        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self._on_timer_tick)
        self.progress_timer.start(500)

        self.meter_timer = QTimer(self)
        self.meter_timer.timeout.connect(self._update_radio_meter)
        self.meter_timer.start(33)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Tab-level Smooth Scroll Area for clean unconstrained scrolling
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(16)

        # Header Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = TitleLabel(tr("radio_title", "Интернет-Радио, YouTube & Стримы"), container)
        lbl_sub = CaptionLabel(
            tr("radio_subtitle", "Трансляция онлайн-радиостанций, YouTube, YouTube Shorts, Twitch и стримов для себя (динамики/наушники) и в микрофон собеседникам"),
            container
        )
        lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        layout.addLayout(title_layout)

        # 1. Custom Stream / YouTube URL Input Card (Moved above player)
        card_custom = CardWidget(container)
        c_layout = QHBoxLayout(card_custom)
        c_layout.setContentsMargins(16, 12, 16, 12)
        c_layout.setSpacing(10)

        self.edit_url = LineEdit(card_custom)
        self.edit_url.setPlaceholderText(tr("radio_custom_url_placeholder", "Вставьте ссылку: YouTube, YouTube Shorts, YouTube Music, Twitch, радио (mp3/aac)..."))
        self.edit_url.setFixedHeight(34)
        self.edit_url.returnPressed.connect(self._play_custom_url)
        c_layout.addWidget(self.edit_url, stretch=1)

        self.btn_play_custom = PrimaryPushButton(FluentIcon.PLAY, tr("radio_btn_start_stream", "Запустить"), card_custom)
        self.btn_play_custom.setFixedHeight(34)
        self.btn_play_custom.setToolTip(tr("radio_tooltip_play_now", "Запустить воспроизведение звука прямо сейчас"))
        self.btn_play_custom.clicked.connect(lambda: self._play_custom_url(autoplay=True))
        c_layout.addWidget(self.btn_play_custom)

        self.btn_preview_custom = PushButton(FluentIcon.VIEW, tr("radio_btn_preview", "Посмотреть"), card_custom)
        self.btn_preview_custom.setFixedHeight(34)
        self.btn_preview_custom.setToolTip(tr("radio_tooltip_preview", "Загрузить информацию о видео в плеер без немедленного включения звука"))
        self.btn_preview_custom.clicked.connect(lambda: self._play_custom_url(autoplay=False))
        c_layout.addWidget(self.btn_preview_custom)

        layout.addWidget(card_custom)

        # 2. Now Playing Player Card
        self.card_np = CardWidget(container)
        np_layout = QVBoxLayout(self.card_np)
        np_layout.setContentsMargins(20, 16, 20, 16)
        np_layout.setSpacing(12)

        # Top section: 16:9 Thumbnail preview (left) + Metadata & Next Video (right)
        h_media = QHBoxLayout()
        h_media.setSpacing(16)

        self.widget_thumbnail = StreamThumbnailWidget(self.card_np)
        h_media.addWidget(self.widget_thumbnail, alignment=Qt.AlignmentFlag.AlignTop)

        info_box = QVBoxLayout()
        info_box.setSpacing(3)

        # Header subrow: Station name badge, Playlist badge, Status
        h_badge_row = QHBoxLayout()
        h_badge_row.setSpacing(8)

        self.lbl_station_name = SubtitleLabel(tr("radio_np_stopped", "РАДИО: НЕ ВОСПРОИЗВОДИТСЯ"), self.card_np)
        self.lbl_station_name.setStyleSheet("font-size: 13px; font-weight: bold; color: rgba(255, 255, 255, 0.85);")
        h_badge_row.addWidget(self.lbl_station_name)

        self.lbl_playlist_badge = CaptionLabel("", self.card_np)
        self.lbl_playlist_badge.setStyleSheet("""
            background-color: rgba(0, 153, 255, 0.15);
            border: 1px solid rgba(0, 153, 255, 0.4);
            border-radius: 4px;
            padding: 2px 8px;
            font-weight: 600;
            color: #00f2fe;
        """)
        self.lbl_playlist_badge.setVisible(False)
        h_badge_row.addWidget(self.lbl_playlist_badge)

        h_badge_row.addStretch()

        self.lbl_status = CaptionLabel(tr("radio_np_status_stopped", "Остановлено"), self.card_np)
        self.lbl_status.setStyleSheet("color: rgba(255, 255, 255, 0.6); font-size: 12px;")
        h_badge_row.addWidget(self.lbl_status)

        info_box.addLayout(h_badge_row)

        # Track title
        self.lbl_track_title = BodyLabel(tr("radio_np_empty_hint", "Выберите станцию из списка ниже или вставьте ссылку..."), self.card_np)
        self.lbl_track_title.setStyleSheet("font-size: 14px; font-weight: 600; color: #38bdf8;")
        self.lbl_track_title.setWordWrap(True)
        info_box.addWidget(self.lbl_track_title)

        # Artist / Channel
        self.lbl_artist = CaptionLabel("", self.card_np)
        self.lbl_artist.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-weight: 500; font-size: 12px;")
        info_box.addWidget(self.lbl_artist)

        # Next video indicator
        self.lbl_next_track = CaptionLabel("", self.card_np)
        self.lbl_next_track.setStyleSheet("color: #00e5ff; font-weight: 500; font-size: 11px;")
        self.lbl_next_track.setVisible(False)
        info_box.addWidget(self.lbl_next_track)

        h_media.addLayout(info_box, stretch=1)
        np_layout.addLayout(h_media)

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
        self.btn_prev = TransparentToolButton(FluentIcon.PAGE_LEFT, self.card_np)
        self.btn_prev.setFixedSize(34, 34)
        self.btn_prev.setToolTip(tr("radio_btn_prev_video", "Предыдущий трек / станция"))
        self.btn_prev.clicked.connect(self._play_prev_track)
        self.btn_prev.setEnabled(False)
        btn_bar.addWidget(self.btn_prev)

        # Seek -10s
        self.btn_seek_back = PushButton(FluentIcon.LEFT_ARROW, tr("radio_btn_seek_back", "-10с"), self.card_np)
        self.btn_seek_back.setFixedHeight(32)
        self.btn_seek_back.setToolTip(tr("radio_tooltip_seek_back", "Перемотать на 10 секунд назад"))
        self.btn_seek_back.clicked.connect(lambda: self.engine.radio.seek_relative(-10.0))
        btn_bar.addWidget(self.btn_seek_back)

        # Main Play/Stop Toggle button: Starts as "Воспроизвести" (Play)
        self.btn_stop = PrimaryPushButton(FluentIcon.PLAY, tr("radio_btn_play_stream", "Воспроизвести"), self.card_np)
        self.btn_stop.setFixedHeight(34)
        self.btn_stop.setFixedWidth(140)
        self.btn_stop.clicked.connect(self._toggle_play_pause)
        btn_bar.addWidget(self.btn_stop)

        # Seek +10s (replaces confusing +30 icon with clean RIGHT_ARROW)
        self.btn_seek_fwd = PushButton(FluentIcon.RIGHT_ARROW, tr("radio_btn_seek_fwd", "+10с"), self.card_np)
        self.btn_seek_fwd.setFixedHeight(32)
        self.btn_seek_fwd.setToolTip(tr("radio_tooltip_seek_fwd", "Перемотать на 10 секунд вперед"))
        self.btn_seek_fwd.clicked.connect(lambda: self.engine.radio.seek_relative(10.0))
        btn_bar.addWidget(self.btn_seek_fwd)

        # Playlist Next
        self.btn_next = TransparentToolButton(FluentIcon.PAGE_RIGHT, self.card_np)
        self.btn_next.setFixedSize(34, 34)
        self.btn_next.setToolTip(tr("radio_btn_next_video", "Следующий трек / станция"))
        self.btn_next.clicked.connect(self._play_next_track)
        self.btn_next.setEnabled(False)
        btn_bar.addWidget(self.btn_next)

        # Playlist Drawer Toggle button
        self.btn_playlist_toggle = TransparentPushButton(FluentIcon.MENU, tr("radio_show_playlist", "Список видео"), self.card_np)
        self.btn_playlist_toggle.setFixedHeight(32)
        self.btn_playlist_toggle.clicked.connect(self._toggle_playlist_view)
        self.btn_playlist_toggle.setVisible(False)
        btn_bar.addWidget(self.btn_playlist_toggle)

        btn_bar.addStretch()

        # Open in Browser button
        self.btn_open_browser = PushButton(FluentIcon.GLOBE, tr("radio_btn_in_browser", "В браузере"), self.card_np)
        self.btn_open_browser.setFixedHeight(32)
        self.btn_open_browser.setToolTip(tr("radio_tooltip_browser", "Открыть текущее видео или трансляцию в интернет-браузере"))
        self.btn_open_browser.clicked.connect(self._open_url_in_browser)
        btn_bar.addWidget(self.btn_open_browser)

        # Stream Debug & Error Copy button
        self.btn_error_debug = TransparentToolButton(FluentIcon.INFO, self.card_np)
        self.btn_error_debug.setFixedSize(34, 34)
        self.btn_error_debug.setToolTip(tr("radio_tooltip_debug", "Диагностика медиапотока и копирование деталей ошибки"))
        self.btn_error_debug.clicked.connect(self._show_stream_debug_dialog)
        btn_bar.addWidget(self.btn_error_debug)

        np_layout.addLayout(btn_bar)

        # Dynamic Stereo VU Meter
        self.vu_radio = VUMeterWidget(label=tr("radio_vu_label", "УРОВЕНЬ ВОСПРОИЗВЕДЕНИЯ РАДИО / СТРИМА"), parent=self.card_np)
        np_layout.addWidget(self.vu_radio)

        # Collapsible Playlist Drawer View
        self.playlist_card = CardWidget(self.card_np)
        self.playlist_card.setVisible(False)
        pl_layout = QVBoxLayout(self.playlist_card)
        pl_layout.setContentsMargins(12, 10, 12, 10)
        pl_layout.setSpacing(8)

        self.playlist_table = TableWidget(self.playlist_card)
        self.playlist_table.setColumnCount(4)
        self.playlist_table.setHorizontalHeaderLabels([
            "#",
            tr("radio_col_video_title", "Название видео"),
            tr("radio_col_author", "Канал / Автор"),
            tr("radio_col_duration", "Длительность")
        ])
        self.playlist_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.playlist_table.setColumnWidth(0, 45)
        self.playlist_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.playlist_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        self.playlist_table.setColumnWidth(2, 200)
        self.playlist_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.playlist_table.setColumnWidth(3, 85)
        self.playlist_table.verticalHeader().setDefaultSectionSize(34)
        self.playlist_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.playlist_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.playlist_table.cellDoubleClicked.connect(self._on_playlist_row_double_clicked)
        self.playlist_table.setFixedHeight(250)
        pl_layout.addWidget(self.playlist_table)

        np_layout.addWidget(self.playlist_card)

        layout.addWidget(self.card_np)

        # 3. Routing & Volume Control Card (Monitor / Mic switches + target device selector)
        card_vol = CardWidget(container)
        cv_main_layout = QVBoxLayout(card_vol)
        cv_main_layout.setContentsMargins(20, 16, 20, 16)
        cv_main_layout.setSpacing(14)

        lbl_vol_title = SubtitleLabel(tr("radio_routing_title", "Маршрутизация и громкость трансляции"), card_vol)
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
        lbl_mon_head = BodyLabel(tr("radio_hear_myself", "Слышать самому"), card_vol)
        lbl_mon_head.setStyleSheet("font-weight: 600; font-size: 13px;")
        mon_header.addWidget(lbl_mon_head)
        mon_header.addStretch()

        self.switch_mon = SwitchButton(card_vol)
        self.switch_mon.setOnText(tr("switch_on", "Вкл"))
        self.switch_mon.setOffText(tr("switch_off", "Выкл"))
        mon_init_state = bool(self.cfg.get("radio_monitor_enabled", True))
        self.switch_mon.setChecked(mon_init_state)
        self.engine.radio_monitor_enabled = mon_init_state
        self.switch_mon.checkedChanged.connect(self._on_mon_switch_changed)
        mon_header.addWidget(self.switch_mon)
        mon_col.addLayout(mon_header)

        lbl_mon_hint = CaptionLabel(tr("radio_mon_hint", "Воспроизводить стрим в ваших динамиках / наушниках"), card_vol)
        lbl_mon_hint.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        mon_col.addWidget(lbl_mon_hint)

        init_mon_vol = int(self.cfg.get("radio_monitor_vol", 0.7) * 100)
        self.engine.radio_monitor_vol = init_mon_vol / 100.0
        self.lbl_mon = CaptionLabel(tr("radio_mon_vol", vol=init_mon_vol) if mon_init_state else tr("radio_mon_disabled", "Отключено (звук не слышен лично вам)"), card_vol)
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
        lbl_mic_head = BodyLabel(tr("radio_to_mic", "Транслировать в микрофон"), card_vol)
        lbl_mic_head.setStyleSheet("font-weight: 600; font-size: 13px;")
        mic_header.addWidget(lbl_mic_head)
        mic_header.addStretch()

        self.switch_mic = SwitchButton(card_vol)
        self.switch_mic.setOnText(tr("switch_on", "Вкл"))
        self.switch_mic.setOffText(tr("switch_off", "Выкл"))
        mic_init_state = bool(self.cfg.get("radio_mic_enabled", True))
        self.switch_mic.setChecked(mic_init_state)
        self.engine.radio_mic_enabled = mic_init_state
        self.switch_mic.checkedChanged.connect(self._on_mic_switch_changed)
        mic_header.addWidget(self.switch_mic)
        mic_col.addLayout(mic_header)

        lbl_mic_hint = CaptionLabel(tr("radio_mic_hint", "Направлять в виртуальный кабель (Discord, игры, OBS)"), card_vol)
        lbl_mic_hint.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        mic_col.addWidget(lbl_mic_hint)

        init_mic_vol = int(self.cfg.get("radio_mic_vol", 0.9) * 100)
        self.engine.radio_mic_vol = init_mic_vol / 100.0
        self.lbl_mic = CaptionLabel(tr("radio_mic_vol", vol=init_mic_vol) if mic_init_state else tr("radio_mic_disabled", "Отключено (звук не идет в микрофон)"), card_vol)
        mic_col.addWidget(self.lbl_mic)

        self.slider_mic = Slider(Qt.Orientation.Horizontal, card_vol)
        self.slider_mic.setRange(0, 150)
        self.slider_mic.setValue(init_mic_vol)
        self.slider_mic.setEnabled(mic_init_state)
        self.slider_mic.valueChanged.connect(self._on_mic_vol)
        mic_col.addWidget(self.slider_mic)

        lbl_target_mic = CaptionLabel(tr("radio_target_mic_label", "Устройство вывода в микрофон (целевой виртуальный кабель):"), card_vol)
        lbl_target_mic.setStyleSheet("color: rgba(255, 255, 255, 0.55); margin-top: 4px;")
        mic_col.addWidget(lbl_target_mic)

        self.combo_target_mic = ComboBox(card_vol)
        self.combo_target_mic.setFixedHeight(32)
        self.combo_target_mic.setEnabled(mic_init_state)
        self.combo_target_mic.currentIndexChanged.connect(self._on_target_mic_changed)
        mic_col.addWidget(self.combo_target_mic)

        # Guidance banner and 1-click button for games / Discord
        guide_row = QHBoxLayout()
        guide_row.setSpacing(8)
        self.lbl_mic_guide = CaptionLabel(tr("radio_guide_label", "🎮 В игре / Discord выберите микрофон: CABLE Output (VB-Audio)"), card_vol)
        self.lbl_mic_guide.setStyleSheet("color: #38bdf8; font-weight: 500;")
        self.btn_set_default_mic = TransparentPushButton(FluentIcon.SETTING, tr("radio_guide_btn", "Сделать микрофоном по умолчанию"), card_vol)
        self.btn_set_default_mic.setFixedHeight(28)
        self.btn_set_default_mic.clicked.connect(self._set_default_mic)
        guide_row.addWidget(self.lbl_mic_guide, stretch=1)
        guide_row.addWidget(self.btn_set_default_mic)
        mic_col.addLayout(guide_row)

        v_layout.addLayout(mic_col, stretch=1)
        cv_main_layout.addLayout(v_layout)

        layout.addWidget(card_vol)

        # 4. Presets List Card
        card_list_header = QHBoxLayout()
        lbl_list = SubtitleLabel(tr("radio_list_title", "Популярные радиостанции и стримы"), container)
        lbl_list.setStyleSheet("font-size: 15px; margin-top: 4px;")
        card_list_header.addWidget(lbl_list)
        card_list_header.addStretch()

        self.btn_add_st = PushButton(FluentIcon.ADD, tr("radio_btn_add_station", "Добавить станцию"), container)
        self.btn_add_st.setFixedHeight(32)
        self.btn_add_st.clicked.connect(self._prompt_add_station)
        card_list_header.addWidget(self.btn_add_st)
        layout.addLayout(card_list_header)

        self.stations_container = QWidget(container)
        self.s_layout = QVBoxLayout(self.stations_container)
        self.s_layout.setContentsMargins(0, 0, 0, 0)
        self.s_layout.setSpacing(8)
        layout.addWidget(self.stations_container)

        self.scroll_area.setWidget(container)
        main_layout.addWidget(self.scroll_area)

        self._refresh_stations_list()

    def _setup_stream_callbacks(self):
        def _safe_meta(meta):
            try:
                self.sig_metadata_received.emit(meta)
            except RuntimeError:
                pass

        def _safe_status(status):
            try:
                self.sig_status_received.emit(status)
            except RuntimeError:
                pass

        self.engine.radio.on_metadata_changed = _safe_meta
        self.engine.radio.on_status_changed = _safe_status

    def _refresh_stations_list(self):
        while self.s_layout.count():
            item = self.s_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self.station_cards = []
        for s in self.cfg.stations:
            card = FluentStationCard(s, self._toggle_station, self._delete_station, self.stations_container)
            self.station_cards.append(card)
            self.s_layout.addWidget(card)

        self.s_layout.addStretch()
        self._update_station_cards_state()

    def _toggle_station(self, station_data: Dict[str, Any]):
        """Toggles play/pause for the clicked station preset, or switches to it if another stream was playing."""
        url = station_data.get("url", "")
        name = station_data.get("name", "Online Radio")
        if not url:
            return

        curr_url = self.engine.radio.current_url or getattr(self.engine.radio, "current_web_url", None) or self._last_played_url
        web_url = getattr(self.engine.radio, "current_web_url", None)
        # If this exact station is currently playing -> PAUSE IT!
        if self.engine.radio.is_playing and (curr_url == url or web_url == url):
            self._toggle_play_pause()
            return

        # If this exact station is currently paused -> RESUME IT!
        if getattr(self.engine.radio, "is_paused", False) and (curr_url == url or web_url == url):
            self._toggle_play_pause()
            return

        # Otherwise -> start playing this new station!
        self._play_station(station_data)

    def _update_station_cards_state(self, is_playing: Optional[bool] = None):
        """Syncs all station cards' play/pause buttons with active engine radio state."""
        curr_url = self.engine.radio.current_url or getattr(self.engine.radio, "current_web_url", None) or self._last_played_url
        web_url = getattr(self.engine.radio, "current_web_url", None)
        if is_playing is None:
            is_playing = bool(self.engine.radio.is_playing)
        for card in getattr(self, "station_cards", []):
            st_url = card.station_data.get("url", "")
            if is_playing and st_url and (st_url == curr_url or (web_url and st_url == web_url)):
                card.set_playing_state(True)
            else:
                card.set_playing_state(False)

    def _prompt_add_station(self):
        dlg = AddStationDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data.get("name") and data.get("url"):
                self.cfg.add_station(name=data["name"], url=data["url"], genre=data.get("genre", "Online Radio"))
                self._refresh_stations_list()
                InfoBar.success(
                    title=tr("radio_station_added_title"),
                    content=tr("radio_station_added_msg", name=data['name']),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=3000
                )

    def _delete_station(self, station_data: Dict[str, Any]):
        name = station_data.get("name", tr("radio_station_name_fallback", "Радиостанция"))
        s_id = station_data.get("id")
        reply = QMessageBox.question(
            self,
            tr("radio_del_station_title"),
            tr("radio_del_station_msg", name=name),
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
        self.engine.radio.current_url = url
        self.engine.radio.current_web_url = url

        self.lbl_station_name.setText(tr("radio_station_prefix", name=name.upper()))
        self.lbl_artist.setText("")
        self.lbl_status.setText(tr("radio_status_connecting"))
        self.lbl_track_title.setText(tr("radio_status_buffering"))

        self.engine.radio.play(url, name)
        self._update_toggle_btn(playing=True)

    def _play_custom_url(self, autoplay: bool = True):
        raw_url = self.edit_url.text().strip()
        if not raw_url:
            InfoBar.warning(
                title=tr("radio_no_url_title"),
                content=tr("radio_no_url_msg"),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3500
            )
            return

        url = clean_and_normalize_stream_url(raw_url)
        name = tr("radio_custom_stream", "Пользовательский поток")
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

        self.lbl_station_name.setText(tr("radio_stream_prefix", name=name.upper()))
        self.lbl_artist.setText("")

        self.btn_play_custom.setEnabled(False)
        if hasattr(self, "btn_preview_custom"):
            self.btn_preview_custom.setEnabled(False)

        if autoplay:
            self.lbl_status.setText(tr("radio_connecting_server", "Подключение к медиасерверу..."))
            self.lbl_track_title.setText(tr("radio_analyzing_stream", "Анализ и буферизация потока..."))
            self._update_toggle_btn(playing=True)
            self.engine.radio.play(url, name)
        else:
            self.lbl_status.setText(tr("radio_loading_info", "Загрузка информации..."))
            self.lbl_track_title.setText(tr("radio_getting_video_info", "Получение информации о видео..."))
            self._update_toggle_btn(playing=False)
            self.engine.radio.prepare(url, name)

    def _open_url_in_browser(self):
        """Opens the stream or video URL in the user's default web browser."""
        # Top priority: what is currently loaded or playing in the player!
        raw_url = getattr(self.engine.radio, "current_web_url", None) or self.engine.radio.current_url or self._last_played_url
        if not raw_url:
            raw_url = self.edit_url.text().strip()
        if not raw_url:
            InfoBar.warning(
                title=tr("radio_no_stream_title"),
                content=tr("radio_no_active_stream_content"),
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
            self.lbl_status.setText(tr("radio_np_status_paused"))
        else:
            # User wants to RESUME / PLAY
            target_url = self.engine.radio.current_url or self._last_played_url
            target_name = self.engine.radio.current_name or self._last_played_name
            if target_url:
                if getattr(self.engine.radio, "is_paused", False):
                    self.engine.radio.resume()
                else:
                    self.engine.radio.play(target_url, target_name or tr("radio_custom_stream", "Пользовательский поток"))
                self._update_toggle_btn(playing=True)
                self.lbl_status.setText(tr("radio_status_connecting"))
            else:
                QMessageBox.information(self, tr("radio_info_title", "Информация"), tr("radio_info_select_prompt", "Выберите станцию или введите URL для воспроизведения."))

    def stop_radio(self):
        """Full stop requested by parent or hotkey."""
        self._last_played_url = self.engine.radio.current_url or self._last_played_url
        self._last_played_name = self.engine.radio.current_name or self._last_played_name
        self.engine.radio.stop()
        self._update_toggle_btn(playing=False)
        self.lbl_station_name.setText(tr("radio_np_stopped"))
        self.lbl_artist.setText("")
        self.lbl_status.setText(tr("radio_np_status_stopped"))
        self.lbl_track_title.setText(tr("radio_np_empty_hint"))
        if hasattr(self, "widget_thumbnail"):
            self.widget_thumbnail.set_default()
        if hasattr(self, "lbl_next_track"):
            self.lbl_next_track.setVisible(False)

    def _update_toggle_btn(self, playing: bool):
        if playing:
            self.btn_stop.setText(tr("radio_btn_stop_stream", "Остановить"))
            self.btn_stop.setIcon(FluentIcon.PAUSE)
        else:
            if getattr(self.engine.radio, "is_paused", False):
                self.btn_stop.setText(tr("radio_btn_continue", "Продолжить"))
            else:
                self.btn_stop.setText(tr("radio_btn_play_stream", "Воспроизвести"))
            self.btn_stop.setIcon(FluentIcon.PLAY)
        self._update_station_cards_state(is_playing=playing)

    def _play_next_track(self):
        if self.engine.radio.has_next():
            self.engine.radio.play_next()
        elif self.cfg.stations and len(self.cfg.stations) > 1 and not self.engine.radio.is_youtube_active():
            curr_url = self.engine.radio.current_url or self._last_played_url
            idx = 0
            for i, s in enumerate(self.cfg.stations):
                if s.get("url") == curr_url:
                    idx = (i + 1) % len(self.cfg.stations)
                    break
            self._play_station(self.cfg.stations[idx])

    def _play_prev_track(self):
        if self.engine.radio.has_prev():
            self.engine.radio.play_prev()
        elif self.cfg.stations and len(self.cfg.stations) > 1 and not self.engine.radio.is_youtube_active():
            curr_url = self.engine.radio.current_url or self._last_played_url
            idx = 0
            for i, s in enumerate(self.cfg.stations):
                if s.get("url") == curr_url:
                    idx = (i - 1) % len(self.cfg.stations)
                    break
            self._play_station(self.cfg.stations[idx])

    def _toggle_playlist_view(self):
        if hasattr(self, "playlist_card"):
            is_vis = not self.playlist_card.isVisible()
            self.playlist_card.setVisible(is_vis)
            queue_len = len(getattr(self.engine.radio, "playlist_queue", []))
            count_str = f" ({queue_len})" if queue_len > 1 else ""
            self.btn_playlist_toggle.setText(
                tr("radio_hide_playlist", "Скрыть список") if is_vis else f"{tr('radio_show_playlist', 'Список видео')}{count_str}"
            )

    def _on_playlist_row_double_clicked(self, row: int, col: int):
        self.engine.radio.play_playlist_index(row)

    def _update_playlist_table(self, active_index: int = 0):
        queue = getattr(self.engine.radio, "playlist_queue", [])
        if not queue:
            self.playlist_card.setVisible(False)
            self.btn_playlist_toggle.setVisible(False)
            return

        self.playlist_table.blockSignals(True)
        self.playlist_table.setRowCount(len(queue))
        for row, item in enumerate(queue):
            item_num = QTableWidgetItem(f"{row + 1}")
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            title_text = item.get("title", tr("radio_video_fmt", num=row + 1))
            item_title = QTableWidgetItem(title_text)

            channel_text = item.get("artist", "")
            item_channel = QTableWidgetItem(channel_text)

            dur = item.get("duration")
            if dur and isinstance(dur, (int, float)) and dur > 0:
                m = int(dur) // 60
                s = int(dur) % 60
                dur_text = f"{m:02d}:{s:02d}"
            else:
                dur_text = "--:--"
            item_dur = QTableWidgetItem(dur_text)
            item_dur.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if row == active_index:
                highlight_brush = QColor("#0078d4")
                item_num.setForeground(highlight_brush)
                item_title.setForeground(highlight_brush)
                item_channel.setForeground(highlight_brush)
                item_dur.setForeground(highlight_brush)
                font = item_title.font()
                font.setBold(True)
                item_title.setFont(font)

            self.playlist_table.setItem(row, 0, item_num)
            self.playlist_table.setItem(row, 1, item_title)
            self.playlist_table.setItem(row, 2, item_channel)
            self.playlist_table.setItem(row, 3, item_dur)

        self.playlist_table.selectRow(active_index)
        if self.playlist_table.item(active_index, 0):
            self.playlist_table.scrollToItem(self.playlist_table.item(active_index, 0))
        self.playlist_table.blockSignals(False)

    def _update_radio_meter(self):
        if hasattr(self, "vu_radio"):
            peak = getattr(self.engine, "radio_stream_peak", 0.0)
            self.vu_radio.set_levels(peak)

    def _on_thumbnail_downloaded(self, url: str, data: bytes):
        pm = QPixmap()
        if pm.loadFromData(data):
            self._thumb_cache[url] = pm
            if getattr(self.engine.radio, "current_thumbnail_url", None) == url:
                if hasattr(self, "widget_thumbnail"):
                    self.widget_thumbnail.set_pixmap(pm)

    def _on_metadata_received_main_thread(self, meta: Dict[str, Any]):
        """Executed strictly on the Qt GUI main thread via sig_metadata_received."""
        title = meta.get("title") or tr("radio_stream_name_fallback", "Онлайн-поток")
        artist = meta.get("artist") or ""
        duration = meta.get("duration")
        is_live = meta.get("is_live", True)
        playlist_count = meta.get("playlist_count", 0)
        playlist_index = meta.get("playlist_index", 0)
        thumb_url = meta.get("thumbnail_url")
        next_title = meta.get("next_title")
        next_artist = meta.get("next_artist")

        self.lbl_track_title.setText(title)
        self.lbl_artist.setText(artist if artist else "")

        # Thumbnail display & async download
        if hasattr(self, "widget_thumbnail"):
            if thumb_url:
                if thumb_url in self._thumb_cache:
                    self.widget_thumbnail.set_pixmap(self._thumb_cache[thumb_url])
                else:
                    self.widget_thumbnail.set_default()
                    if self._thumb_thread and self._thumb_thread.isRunning():
                        self._thumb_thread.terminate()
                    self._thumb_thread = ThumbnailDownloadThread(thumb_url, self)
                    self._thumb_thread.sig_loaded.connect(self._on_thumbnail_downloaded)
                    self._thumb_thread.start()
            else:
                self.widget_thumbnail.set_default()

        # Next video indicator
        if hasattr(self, "lbl_next_track"):
            is_yt = self.engine.radio.is_youtube_active()
            if next_title:
                sub = f" ({next_artist})" if next_artist else ""
                tpl = tr("radio_next_video", "⏭ Следующее видео: {title}") if is_yt else tr("radio_next_track", "⏭ Следующее: {title}")
                self.lbl_next_track.setText(tpl.format(title=f"{next_title}{sub}"))
                self.lbl_next_track.setVisible(True)
            elif not is_yt:
                curr_url = self.engine.radio.current_url or self._last_played_url
                if self.cfg.stations and len(self.cfg.stations) > 1:
                    for i, s in enumerate(self.cfg.stations):
                        if s.get("url") == curr_url:
                            nxt_st = self.cfg.stations[(i + 1) % len(self.cfg.stations)]
                            self.lbl_next_track.setText(tr("radio_next_station", name=nxt_st.get('name', tr('radio_station_name_fallback', 'Радиостанция'))))
                            self.lbl_next_track.setVisible(True)
                            break
                    else:
                        self.lbl_next_track.setVisible(False)
                else:
                    self.lbl_next_track.setVisible(False)
            else:
                self.lbl_next_track.setVisible(False)

        # Playlist badge and table
        is_yt = self.engine.radio.is_youtube_active()
        if playlist_count > 1:
            badge_tpl = tr("radio_playlist_badge", "Плейлист: {index} / {count}")
            self.lbl_playlist_badge.setText(badge_tpl.format(index=playlist_index + 1, count=playlist_count))
            self.lbl_playlist_badge.setVisible(True)
            self.btn_prev.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_playlist_toggle.setVisible(True)

            # Keep hidden by default unless user has already opened it
            if hasattr(self, "playlist_card") and self.playlist_card.isVisible():
                self.btn_playlist_toggle.setText(tr("radio_hide_playlist", "Скрыть список"))
            else:
                if hasattr(self, "playlist_card"):
                    self.playlist_card.setVisible(False)
                self.btn_playlist_toggle.setText(f"{tr('radio_show_playlist', 'Список видео')} ({playlist_count})")

            self._update_playlist_table(playlist_index)
        elif is_yt:
            self.lbl_playlist_badge.setVisible(False)
            self.btn_next.setEnabled(bool(self.engine.radio.has_next() or self.engine.radio.next_url))
            self.btn_prev.setEnabled(bool(self.engine.radio.has_prev()))
            self.btn_playlist_toggle.setVisible(False)
            if hasattr(self, "playlist_card"):
                self.playlist_card.setVisible(False)
        else:
            self.lbl_playlist_badge.setVisible(False)
            has_multi = len(self.cfg.stations) > 1
            self.btn_prev.setEnabled(has_multi)
            self.btn_next.setEnabled(has_multi)
            self.btn_playlist_toggle.setVisible(False)
            if hasattr(self, "playlist_card"):
                self.playlist_card.setVisible(False)

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

    def _localize_stream_status(self, status: str) -> str:
        mapping = {
            "Загрузка информации...": tr("radio_loading_info", "Загрузка информации..."),
            "Готов к воспроизведению": tr("radio_status_ready", "Готов к воспроизведению"),
            "Приостановлено": tr("radio_np_status_paused", "Приостановлено"),
            "Остановлено": tr("radio_np_status_stopped", "Остановлено"),
            "Поиск и разрешение потока...": tr("radio_status_connecting", "Поиск и разрешение потока..."),
            "Резервный декодер (miniaudio)...": tr("radio_status_buffering", "Резервный декодер (miniaudio)..."),
            "Ошибка радиопотока": tr("radio_np_status_error", "Ошибка радиопотока"),
            "В эфире": tr("radio_np_status_on_air", "В эфире"),
            "Воспроизведение": tr("radio_np_status_playing", "Воспроизведение"),
            "Ошибка: поток недоступен или заблокирован": tr("radio_err_unavailable", "Ошибка: поток недоступен или заблокирован"),
        }
        if status in mapping:
            return mapping[status]
        if status.startswith("Ошибка загрузки:"):
            return f"{tr('radio_err_load', 'Ошибка загрузки')}: " + status.split(":", 1)[1]
        if status.startswith("Ошибка потока:"):
            return f"{tr('radio_err_stream', 'Ошибка потока')}: " + status.split(":", 1)[1]
        if status.startswith("Ошибка видеопотока:"):
            return f"{tr('radio_err_video', 'Ошибка видеопотока')}: " + status.split(":", 1)[1]
        return status

    def _on_engine_status_changed_main_thread(self, status: str):
        """Executed strictly on the Qt GUI main thread via sig_status_received."""
        self.lbl_status.setText(self._localize_stream_status(status))
        self.btn_play_custom.setEnabled(True)
        if hasattr(self, "btn_preview_custom"):
            self.btn_preview_custom.setEnabled(True)

        if status in ("В эфире", "Воспроизведение", "On Air", "Playing"):
            self._update_toggle_btn(playing=True)
        elif status in ("Остановлено", "Приостановлено", "Stopped", "Paused"):
            self._update_toggle_btn(playing=False)
        elif status in ("Готов к воспроизведению", "Ready to play"):
            self._update_toggle_btn(playing=False)
        elif "Ошибка" in status or "Error" in status:
            self._update_toggle_btn(playing=False)
            self.lbl_track_title.setText(tr("radio_track_err_hint", "Не удалось воспроизвести поток. Вы можете открыть его в браузере или скопировать детали ошибки."))
            self._show_stream_error_bar(status)

    def _show_stream_error_bar(self, status: str):
        """Displays a dedicated InfoBar with buttons to Copy Error, View Debug Details, or Open in Browser."""
        bar = InfoBar(
            icon=FluentIcon.INFO,
            title=tr("radio_err_dialog_title"),
            content=tr("radio_err_dialog_msg", status=status),
            orient=Qt.Orientation.Vertical,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=12000,
            parent=self
        )
        btn_copy = PushButton(FluentIcon.COPY, tr("radio_err_btn_copy", "Копировать ошибку"), bar)
        btn_copy.setFixedHeight(28)
        btn_copy.clicked.connect(self._copy_error_details)

        btn_debug = PushButton(FluentIcon.INFO, tr("radio_err_btn_debug", "Подробнее"), bar)
        btn_debug.setFixedHeight(28)
        btn_debug.clicked.connect(self._show_stream_debug_dialog)

        btn_browser = PushButton(FluentIcon.GLOBE, tr("radio_err_btn_browser", "В браузере"), bar)
        btn_browser.setFixedHeight(28)
        btn_browser.clicked.connect(self._open_url_in_browser)

        bar.addWidget(btn_copy)
        bar.addWidget(btn_debug)
        bar.addWidget(btn_browser)
        bar.show()

    def _copy_error_details(self):
        """Copies full stream diagnostic details into Windows clipboard."""
        err = self.engine.radio.get_last_error_details()
        curr_url = getattr(self.engine.radio, "current_web_url", None) or self.engine.radio.current_url or self._last_played_url or "Unknown URL"
        name_str = self.engine.radio.current_name or self._last_played_name or tr("radio_custom_stream", "Поток")
        full_text = (
            f"SoundFlow Studio Stream Diagnostic\n"
            f"{tr('radio_diagnostic_name', name=name_str)}\n"
            f"URL: {curr_url}\n"
            f"{tr('radio_diagnostic_status', status=self.lbl_status.text())}\n"
            f"----------------------------------------\n"
            f"{tr('radio_diagnostic_error_details', err=err)}"
        )
        QApplication.clipboard().setText(full_text)
        InfoBar.success(
            title=tr("radio_copied_title"),
            content=tr("radio_copied_details_content"),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=3000
        )

    def _show_stream_debug_dialog(self):
        """Opens modal dialog with detailed error trace and copy button."""
        dlg = StreamDebugDialog(self.engine.radio, parent=self)
        dlg.exec()

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
            curr_pos = getattr(self.engine.radio, "playback_pos_sec", self.engine.radio.current_pos_sec)
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
        saved_target = self.cfg.get("mic_target_device_id")
        selected_index = self.engine.populate_target_mic_combobox(self.combo_target_mic, saved_target)
        if saved_target is None:
            auto_dev_id = self.combo_target_mic.itemData(selected_index)
            if auto_dev_id is not None:
                self.cfg.set("mic_target_device_id", auto_dev_id)
                self.engine.mic_target_device_id = auto_dev_id
                if self.engine.mic_target_stream is None:
                    self.engine.set_mic_target_device(auto_dev_id)

    def _set_default_mic(self):
        from core.driver_manager import DriverManager
        ok = DriverManager.set_default_recording_device_to_cable()
        if ok:
            InfoBar.success(
                title=tr("mic_default_success_title"),
                content=tr("mic_default_success_msg"),
                position=InfoBarPosition.TOP,
                parent=self,
                duration=4000
            )
        else:
            InfoBar.info(
                title=tr("mic_default_manual_title"),
                content=tr("mic_default_manual_msg"),
                position=InfoBarPosition.TOP,
                parent=self,
                duration=4500
            )

    def _on_target_mic_changed(self, index: int):
        dev_id = self.combo_target_mic.itemData(index)
        # Safely decouple via singleShot so ComboBoxMenu popup can finish closing animation cleanly without crash
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

    def _on_mon_switch_changed(self, is_checked: bool):
        self.engine.radio_monitor_enabled = is_checked
        self.cfg.set("radio_monitor_enabled", is_checked)
        self.slider_mon.setEnabled(is_checked)
        if is_checked:
            self.lbl_mon.setText(tr("radio_mon_vol", vol=self.slider_mon.value()))
        else:
            self.lbl_mon.setText(tr("radio_mon_disabled", "Отключено (звук не слышен лично вам)"))

    def _on_mic_switch_changed(self, is_checked: bool):
        self.engine.radio_mic_enabled = is_checked
        self.cfg.set("radio_mic_enabled", is_checked)
        self.slider_mic.setEnabled(is_checked)
        self.combo_target_mic.setEnabled(is_checked)
        if is_checked:
            self.lbl_mic.setText(tr("radio_mic_vol", vol=self.slider_mic.value()))
        else:
            self.lbl_mic.setText(tr("radio_mic_disabled", "Отключено (звук не идет в микрофон)"))

    def _on_mon_vol(self, val: int):
        if self.switch_mon.isChecked():
            self.lbl_mon.setText(tr("radio_mon_vol", vol=val))
        self.engine.radio_monitor_vol = val / 100.0
        self.cfg.set("radio_monitor_vol", self.engine.radio_monitor_vol)

    def _on_mic_vol(self, val: int):
        if self.switch_mic.isChecked():
            self.lbl_mic.setText(tr("radio_mic_vol", vol=val))
        self.engine.radio_mic_vol = val / 100.0
        self.cfg.set("radio_mic_vol", self.engine.radio_mic_vol)
