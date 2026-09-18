"""
Custom reusable UI components for SoundFlow Studio.
Includes animated VU Meters, SoundCard items, Volume controls, and Badges.
"""

from typing import Optional, Callable
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QMenu, QFrame, QSizePolicy
)
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPen, QFont


class VUMeterWidget(QWidget):
    """Sleek animated horizontal stereo LED volume meter."""

    def __init__(self, label: str = "Level", parent=None):
        super().__init__(parent)
        self.label_text = label
        self.left_level = 0.0
        self.right_level = 0.0
        self.peak_left = 0.0
        self.peak_right = 0.0
        self.setFixedHeight(38)
        self.setMinimumWidth(160)

    def set_levels(self, left, right: Optional[float] = None):
        """Sets level in range [0.0, 1.0]. Accepts float or (left, right) sequence."""
        if isinstance(left, (tuple, list)):
            if len(left) >= 2:
                l_val = float(left[0] or 0.0)
                r_val = float(left[1] or 0.0)
            elif len(left) == 1:
                l_val = float(left[0] or 0.0)
                r_val = l_val
            else:
                l_val, r_val = 0.0, 0.0
        else:
            l_val = float(left or 0.0)
            r_val = l_val if right is None else float(right or 0.0)

        self.left_level = max(0.0, min(1.0, l_val))
        self.right_level = max(0.0, min(1.0, r_val))

        # Peak decay
        self.peak_left = max(self.left_level, self.peak_left * 0.92)
        self.peak_right = max(self.right_level, self.peak_right * 0.92)
        self.update()

    def reset(self):
        """Resets all meter levels and peaks to zero."""
        self.left_level = 0.0
        self.right_level = 0.0
        self.peak_left = 0.0
        self.peak_right = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Draw label
        painter.setPen(QColor("#94a3b8"))
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(0, 11, self.label_text)

        meter_y1 = 15
        meter_y2 = 25
        bar_height = 6
        bar_width = w

        # Draw background tracks
        painter.setBrush(QBrush(QColor("#1e293b")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, meter_y1, bar_width, bar_height, 3, 3)
        painter.drawRoundedRect(0, meter_y2, bar_width, bar_height, 3, 3)

        # Gradient for active level (Green -> Cyan -> Amber -> Red)
        grad = QLinearGradient(0, 0, bar_width, 0)
        grad.setColorAt(0.0, QColor("#10b981"))
        grad.setColorAt(0.65, QColor("#00f2fe"))
        grad.setColorAt(0.85, QColor("#f59e0b"))
        grad.setColorAt(1.0, QColor("#ef4444"))

        # Channel 1 (Left)
        fill_w1 = int(self.left_level * bar_width)
        if fill_w1 > 2:
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(0, meter_y1, fill_w1, bar_height, 3, 3)

        # Peak indicator L
        peak_x1 = int(self.peak_left * (bar_width - 2))
        if peak_x1 > 0:
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(peak_x1, meter_y1, peak_x1, meter_y1 + bar_height)

        # Channel 2 (Right)
        fill_w2 = int(self.right_level * bar_width)
        if fill_w2 > 2:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(0, meter_y2, fill_w2, bar_height, 3, 3)

        # Peak indicator R
        peak_x2 = int(self.peak_right * (bar_width - 2))
        if peak_x2 > 0:
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(peak_x2, meter_y2, peak_x2, meter_y2 + bar_height)


class SoundCardWidget(QFrame):
    """Visual interactive card for a soundboard item."""

    play_clicked = pyqtSignal(str)       # sound_id
    stop_clicked = pyqtSignal(str)       # sound_id
    hotkey_clicked = pyqtSignal(str)     # sound_id
    delete_clicked = pyqtSignal(str)     # sound_id
    favorite_toggled = pyqtSignal(str)   # sound_id
    edit_clicked = pyqtSignal(str)       # sound_id

    def __init__(self, sound_data: dict, parent=None):
        super().__init__(parent)
        self.sound_data = sound_data
        self.sound_id = sound_data.get("id", "")
        self.is_playing = False

        self.setObjectName("SoundCard")
        self.setStyleSheet("""
            QFrame#SoundCard {
                background: #131d31;
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 4px;
            }
            QFrame#SoundCard:hover {
                border: 1px solid #00f2fe;
                background: #16243d;
            }
        """)
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Play / Stop button
        self.btn_play = QPushButton("▶")
        self.btn_play.setFixedSize(36, 36)
        self.btn_play.setObjectName("AccentButton")
        self.btn_play.setStyleSheet("border-radius: 18px; font-size: 15px; padding: 0;")
        self.btn_play.clicked.connect(self._toggle_play)
        layout.addWidget(self.btn_play)

        # Sound Info (Title, Category, Duration)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title_layout = QHBoxLayout()
        title_layout.setSpacing(6)

        self.lbl_title = QLabel(self.sound_data.get("name", "Untitled Sound"))
        self.lbl_title.setStyleSheet("font-weight: 700; font-size: 13px; color: #f8fafc;")
        title_layout.addWidget(self.lbl_title)

        category = self.sound_data.get("category", "General")
        self.lbl_category = QLabel(category.upper())
        self.lbl_category.setStyleSheet("""
            background: #1e293b;
            color: #38bdf8;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 9px;
            font-weight: 700;
        """)
        title_layout.addWidget(self.lbl_category)
        title_layout.addStretch()

        info_layout.addLayout(title_layout)

        # Subtitle / metadata line
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(8)

        dur_text = self.sound_data.get("duration", "")
        self.lbl_meta = QLabel(dur_text if dur_text else "Ready to play")
        self.lbl_meta.setStyleSheet("color: #64748b; font-size: 11px;")
        meta_layout.addWidget(self.lbl_meta)
        meta_layout.addStretch()

        info_layout.addLayout(meta_layout)
        layout.addLayout(info_layout, stretch=1)

        # Hotkey Badge Button
        hotkey = self.sound_data.get("hotkey", "")
        self.btn_hotkey = QPushButton(f"[{hotkey.upper()}]" if hotkey else "[+ KEY]")
        self.btn_hotkey.setFixedHeight(26)
        self.btn_hotkey.setStyleSheet("""
            QPushButton {
                background: #1e293b;
                color: #a855f7;
                border: 1px solid #334155;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
                padding: 2px 8px;
            }
            QPushButton:hover {
                border-color: #a855f7;
                color: #ffffff;
                background: #3b0764;
            }
        """)
        self.btn_hotkey.setToolTip("Нажмите для назначения горячей клавиши")
        self.btn_hotkey.clicked.connect(lambda: self.hotkey_clicked.emit(self.sound_id))
        layout.addWidget(self.btn_hotkey)

        # Favorite Star Button
        self.is_fav = bool(self.sound_data.get("favorite", False))
        self.btn_fav = QPushButton("★" if self.is_fav else "☆")
        self.btn_fav.setFixedSize(28, 28)
        self.btn_fav.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {'#fbbf24' if self.is_fav else '#64748b'};
                font-size: 16px;
            }}
            QPushButton:hover {{
                color: #f59e0b;
            }}
        """)
        self.btn_fav.clicked.connect(self._toggle_fav)
        layout.addWidget(self.btn_fav)

        # More Actions Button (...)
        self.btn_more = QPushButton("⋮")
        self.btn_more.setFixedSize(28, 28)
        self.btn_more.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #94a3b8;
                font-size: 16px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        self.btn_more.clicked.connect(self._show_context_menu)
        layout.addWidget(self.btn_more)

    def _toggle_play(self):
        if self.is_playing:
            self.stop_clicked.emit(self.sound_id)
        else:
            self.play_clicked.emit(self.sound_id)

    def set_playing(self, playing: bool):
        self.is_playing = playing
        if playing:
            self.btn_play.setText("■")
            self.btn_play.setObjectName("DangerButton")
            self.btn_play.setStyleSheet("border-radius: 18px; font-size: 14px; padding: 0;")
        else:
            self.btn_play.setText("▶")
            self.btn_play.setObjectName("AccentButton")
            self.btn_play.setStyleSheet("border-radius: 18px; font-size: 15px; padding: 0;")

    def _toggle_fav(self):
        self.is_fav = not self.is_fav
        self.btn_fav.setText("★" if self.is_fav else "☆")
        self.btn_fav.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {'#fbbf24' if self.is_fav else '#64748b'};
                font-size: 16px;
            }}
        """)
        self.favorite_toggled.emit(self.sound_id)

    def set_hotkey_text(self, hotkey: str):
        self.btn_hotkey.setText(f"[{hotkey.upper()}]" if hotkey else "[+ KEY]")

    def _show_context_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px;
                color: #f8fafc;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1e293b;
                color: #00f2fe;
            }
        """)

        act_hotkey = menu.addAction("Назначить горячую клавишу...")
        act_edit = menu.addAction("Настройки звука (громкость, обрезка)...")
        menu.addSeparator()
        act_delete = menu.addAction("Удалить из саундборда")

        action = menu.exec(self.btn_more.mapToGlobal(self.btn_more.rect().bottomLeft()))
        if action == act_hotkey:
            self.hotkey_clicked.emit(self.sound_id)
        elif action == act_edit:
            self.edit_clicked.emit(self.sound_id)
        elif action == act_delete:
            self.delete_clicked.emit(self.sound_id)
