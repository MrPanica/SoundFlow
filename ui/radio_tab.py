"""
Online Radio & Live Web Audio Stream Tab for SoundFlow Studio.
Plays internet radio streams (Icecast/Shoutcast) and pipes the audio into mic and headphones.
"""

from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QGroupBox, QSlider,
    QMessageBox
)


class StationCardWidget(QFrame):
    """Card widget for an individual radio station preset."""

    play_requested = pyqtSignal(dict)  # station_data

    def __init__(self, station_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.station_data = station_data
        self.setObjectName("StationCard")
        self.setStyleSheet("""
            QFrame#StationCard {
                background: #131d31;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 10px;
            }
            QFrame#StationCard:hover {
                border-color: #38bdf8;
                background: #16243d;
            }
        """)
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        # Play icon button
        self.btn_play = QPushButton("📻")
        self.btn_play.setFixedSize(38, 38)
        self.btn_play.setObjectName("AccentButton")
        self.btn_play.setStyleSheet("border-radius: 19px; font-size: 18px; padding: 0;")
        self.btn_play.clicked.connect(lambda: self.play_requested.emit(self.station_data))
        layout.addWidget(self.btn_play)

        # Info
        info = QVBoxLayout()
        info.setSpacing(2)

        title_row = QHBoxLayout()
        lbl_name = QLabel(self.station_data.get("name", "Station"))
        lbl_name.setStyleSheet("font-weight: 700; font-size: 13px; color: #f8fafc;")
        title_row.addWidget(lbl_name)

        lbl_genre = QLabel(self.station_data.get("genre", "Radio").upper())
        lbl_genre.setStyleSheet("""
            background: #1e293b;
            color: #38bdf8;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 9px;
            font-weight: 700;
        """)
        title_row.addWidget(lbl_genre)
        title_row.addStretch()
        info.addLayout(title_row)

        lbl_desc = QLabel(self.station_data.get("description", ""))
        lbl_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        info.addWidget(lbl_desc)

        layout.addLayout(info, stretch=1)

        # Tune in button
        self.btn_tune = QPushButton("В эфир")
        self.btn_tune.setFixedHeight(28)
        self.btn_tune.setStyleSheet("font-size: 11px; padding: 2px 10px;")
        self.btn_tune.clicked.connect(lambda: self.play_requested.emit(self.station_data))
        layout.addWidget(self.btn_tune)


class RadioTab(QWidget):
    """Tab displaying radio station presets, custom URL player, and live stream status."""

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.is_active = False

        self._build_ui()

        # Connect radio callbacks
        self.engine.radio.on_title_changed = self._on_title_updated
        self.engine.radio.on_status_changed = self._on_status_updated

        # Timer to poll title updates safely on Qt GUI thread
        self.title_timer = QTimer(self)
        self.title_timer.timeout.connect(self._poll_metadata)
        self.title_timer.start(1000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 1. Now Playing Live Banner
        self.now_playing_card = QFrame()
        self.now_playing_card.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a103c, stop:1 #0f172a);
                border: 1px solid #7c3aed;
                border-radius: 12px;
                padding: 16px;
            }
        """)
        np_layout = QVBoxLayout(self.now_playing_card)
        np_layout.setSpacing(6)

        top_row = QHBoxLayout()
        self.lbl_station_name = QLabel("РАДИО: НЕ ВОСПРОИЗВОДИТСЯ")
        self.lbl_station_name.setStyleSheet("color: #c084fc; font-weight: 800; font-size: 13px; letter-spacing: 0.5px;")
        top_row.addWidget(self.lbl_station_name)

        self.lbl_status = QLabel("Остановлено")
        self.lbl_status.setStyleSheet("color: #64748b; font-size: 11px;")
        top_row.addWidget(self.lbl_status)
        top_row.addStretch()

        self.btn_stop_radio = QPushButton("■ Остановить эфир")
        self.btn_stop_radio.setObjectName("DangerButton")
        self.btn_stop_radio.setFixedHeight(28)
        self.btn_stop_radio.clicked.connect(self.stop_radio)
        top_row.addWidget(self.btn_stop_radio)

        np_layout.addLayout(top_row)

        self.lbl_track_title = QLabel("Выберите станцию ниже или введите свой URL...")
        self.lbl_track_title.setWordWrap(True)
        self.lbl_track_title.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: 700; margin-top: 4px;")
        np_layout.addWidget(self.lbl_track_title)

        layout.addWidget(self.now_playing_card)

        # 2. Custom Stream URL Input
        url_group = QGroupBox("ПОЛЬЗОВАТЕЛЬСКИЙ ПОТОК (ICECAST / SHOUTCAST / MP3 / AAC)")
        u_layout = QHBoxLayout(url_group)
        u_layout.setSpacing(10)

        self.edit_url = QLineEdit()
        self.edit_url.setPlaceholderText("https://stream.example.com/radio.mp3")
        u_layout.addWidget(self.edit_url, stretch=1)

        self.btn_play_custom = QPushButton("▶ Запустить URL")
        self.btn_play_custom.setObjectName("AccentButton")
        self.btn_play_custom.clicked.connect(self._play_custom_url)
        u_layout.addWidget(self.btn_play_custom)

        layout.addWidget(url_group)

        # 3. Volume and routing
        vol_group = QGroupBox("ГРОМКОСТЬ РАДИО")
        v_layout = QHBoxLayout(vol_group)
        v_layout.setSpacing(20)

        # Headphones
        mon_col = QVBoxLayout()
        self.lbl_mon_vol = QLabel("Для себя: 70%")
        self.slider_mon = QSlider(Qt.Orientation.Horizontal)
        self.slider_mon.setRange(0, 150)
        self.slider_mon.setValue(70)
        self.slider_mon.valueChanged.connect(self._on_mon_vol_change)
        mon_col.addWidget(self.lbl_mon_vol)
        mon_col.addWidget(self.slider_mon)
        v_layout.addLayout(mon_col)

        # Mic
        mic_col = QVBoxLayout()
        self.lbl_mic_vol = QLabel("В микрофон: 90%")
        self.slider_mic = QSlider(Qt.Orientation.Horizontal)
        self.slider_mic.setRange(0, 150)
        self.slider_mic.setValue(90)
        self.slider_mic.valueChanged.connect(self._on_mic_vol_change)
        mic_col.addWidget(self.lbl_mic_vol)
        mic_col.addWidget(self.slider_mic)
        v_layout.addLayout(mic_col)

        layout.addWidget(vol_group)

        # 4. Preset Stations List
        lbl_presets = QLabel("Популярные радиостанции:")
        lbl_presets.setStyleSheet("font-weight: 700; color: #94a3b8; font-size: 13px; margin-top: 4px;")
        layout.addWidget(lbl_presets)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        station_container = QWidget()
        self.station_layout = QVBoxLayout(station_container)
        self.station_layout.setSpacing(8)
        self.station_layout.setContentsMargins(0, 0, 8, 0)

        for s in self.cfg.stations:
            card = StationCardWidget(s)
            card.play_requested.connect(self._play_station)
            self.station_layout.addWidget(card)

        self.station_layout.addStretch()
        scroll.setWidget(station_container)
        layout.addWidget(scroll, stretch=1)

    def _play_station(self, station_data: Dict[str, Any]):
        url = station_data.get("url", "")
        name = station_data.get("name", "Online Radio")
        if not url:
            return

        self.lbl_station_name.setText(f"РАДИО: {name.upper()}")
        self.lbl_status.setText("Подключение к серверу...")
        self.lbl_track_title.setText("Буферизация аудиопотока...")
        self.engine.radio.play(url, name)
        self.is_active = True

    def _play_custom_url(self):
        url = self.edit_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, введите корректный URL аудиопотока.")
            return
        self._play_station({"name": "Пользовательский поток", "url": url, "genre": "Custom"})

    def stop_radio(self):
        self.engine.radio.stop()
        self.lbl_station_name.setText("РАДИО: НЕ ВОСПРОИЗВОДИТСЯ")
        self.lbl_status.setText("Остановлено")
        self.lbl_track_title.setText("Выберите станцию выше для включения эфира...")
        self.is_active = False

    def _on_title_updated(self, title: str):
        pass  # Handled safely via _poll_metadata

    def _on_status_updated(self, status: str):
        pass

    def _poll_metadata(self):
        if self.engine.radio.is_playing:
            title = self.engine.radio.current_title
            if title and title != self.lbl_track_title.text():
                self.lbl_track_title.setText(title)
            status = "В эфире" if self.engine.radio.is_playing else "Остановлено"
            self.lbl_status.setText(status)

    def _on_mon_vol_changed(self, val: int):
        self.lbl_mon_vol.setText(f"Для себя: {val}%")
        self.engine.radio_monitor_vol = val / 100.0

    def _on_mic_vol_change(self, val: int):
        self.lbl_mic_vol.setText(f"В микрофон: {val}%")
        self.engine.radio_mic_vol = val / 100.0
