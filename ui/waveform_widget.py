"""
Interactive Audio Waveform and Timeline Scrubber Widget for SoundFlow Studio.
Renders real-time audio amplitude graph (peaks) and allows interactive scrubbing/seeking.
"""

from typing import Optional, Dict, Any
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PyQt6.QtGui import (
    QPainter, QColor, QBrush, QPen, QLinearGradient,
    QPainterPath, QMouseEvent, QFont
)
from qfluentwidgets import (
    CardWidget, TransparentToolButton, FluentIcon,
    CaptionLabel, BodyLabel, SubtitleLabel
)


class WaveformCanvas(QWidget):
    """Custom paint widget rendering audio peaks and interactive playhead."""

    seek_requested = pyqtSignal(float)   # Emits ratio (0.0 .. 1.0)
    play_from_seek_requested = pyqtSignal(float)  # Emits ratio on double click to seek and play
    drag_started = pyqtSignal()
    drag_ended = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(72)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.peaks: np.ndarray = np.array([], dtype=np.float32)
        self.progress_ratio: float = 0.0
        self.is_dragging: bool = False
        self.hover_ratio: Optional[float] = None
        self.is_active: bool = False

    def set_peaks(self, peaks: np.ndarray):
        self.peaks = peaks
        self.is_active = len(peaks) > 0
        self.update()

    def set_progress(self, ratio: float):
        if not self.is_dragging:
            self.progress_ratio = max(0.0, min(1.0, ratio))
            self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.is_active:
            self.is_dragging = True
            self.drag_started.emit()
            ratio = max(0.0, min(1.0, event.position().x() / max(1.0, self.width())))
            self.progress_ratio = ratio
            self.seek_requested.emit(ratio)
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.is_active:
            ratio = max(0.0, min(1.0, event.position().x() / max(1.0, self.width())))
            self.progress_ratio = ratio
            self.seek_requested.emit(ratio)
            self.play_from_seek_requested.emit(ratio)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        w = max(1.0, self.width())
        ratio = max(0.0, min(1.0, event.position().x() / w))
        self.hover_ratio = ratio

        if self.is_dragging and self.is_active:
            self.progress_ratio = ratio
            self.seek_requested.emit(ratio)

        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            self.drag_ended.emit()
            ratio = max(0.0, min(1.0, event.position().x() / max(1.0, self.width())))
            self.progress_ratio = ratio
            self.seek_requested.emit(ratio)
            self.update()

    def leaveEvent(self, event):
        self.hover_ratio = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        cy = h / 2.0

        # Background track container
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0, 0, w, h), 8, 8)
        painter.fillPath(bg_path, QColor(255, 255, 255, 8))

        # If no active audio loaded, draw subtle placeholder waves
        if not self.is_active or len(self.peaks) == 0:
            pen = QPen(QColor(255, 255, 255, 25), 1.5)
            painter.setPen(pen)
            num_dots = int(w / 8)
            for i in range(num_dots):
                x = i * 8 + 4
                dot_h = 6 + 10 * np.sin(i * 0.25)
                painter.drawLine(QPointF(x, cy - dot_h / 2), QPointF(x, cy + dot_h / 2))

            painter.setPen(QColor(255, 255, 255, 90))
            painter.setFont(QFont("Segoe UI Variable Display", 10))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Нажмите на любой звук саундборда для воспроизведения и перемотки")
            return

        # Draw amplitude bars
        num_bars = len(self.peaks)
        bar_step = w / float(num_bars)
        bar_w = max(1.8, bar_step * 0.65)
        playhead_x = self.progress_ratio * w
        max_bar_h = h - 16.0

        for i, peak in enumerate(self.peaks):
            bar_x = i * bar_step + (bar_step - bar_w) / 2.0
            bar_h = max(4.0, float(peak) * max_bar_h)
            bar_top = cy - bar_h / 2.0

            rect = QRectF(bar_x, bar_top, bar_w, bar_h)

            if bar_x + bar_w <= playhead_x:
                # Played: Vibrant Fluent Accent
                grad = QLinearGradient(bar_x, bar_top, bar_x, bar_top + bar_h)
                grad.setColorAt(0.0, QColor(96, 205, 255))
                grad.setColorAt(1.0, QColor(0, 120, 212))
                painter.setBrush(QBrush(grad))
                painter.setPen(Qt.PenStyle.NoPen)
            else:
                # Unplayed: Translucent Muted White/Slate
                painter.setBrush(QBrush(QColor(255, 255, 255, 55)))
                painter.setPen(Qt.PenStyle.NoPen)

            painter.drawRoundedRect(rect, bar_w / 2.0, bar_w / 2.0)

        # Draw Hover Line (if hovering and not dragging)
        if self.hover_ratio is not None and not self.is_dragging:
            hx = self.hover_ratio * w
            h_pen = QPen(QColor(255, 255, 255, 70), 1, Qt.PenStyle.DashLine)
            painter.setPen(h_pen)
            painter.drawLine(QPointF(hx, 6), QPointF(hx, h - 6))

        # Draw Playhead Scrubber Line
        playhead_pen = QPen(QColor(255, 255, 255, 230), 2)
        painter.setPen(playhead_pen)
        painter.drawLine(QPointF(playhead_x, 4), QPointF(playhead_x, h - 4))

        # Playhead scrubber thumb handle
        painter.setBrush(QBrush(QColor(96, 205, 255)))
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.drawEllipse(QPointF(playhead_x, cy), 6, 6)


class InteractiveWaveformWidget(CardWidget):
    """
    Complete Waveform Track component placed above the soundboard sound list.
    Features real-time playback synchronization, timeline scrubber, and controls.
    """

    play_pause_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    seek_requested = pyqtSignal(float)
    play_from_seek_requested = pyqtSignal(float)
    loop_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(124)

        self.current_sound_id: Optional[str] = None
        self.current_sound_data: Optional[Dict[str, Any]] = None
        self.is_playing: bool = False
        self.is_looping: bool = False
        self.total_duration_sec: float = 0.0

        # Peak cache: filepath -> np.ndarray
        self._peaks_cache: Dict[str, np.ndarray] = {}

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(8)

        # Header Row: Icon, Title, Timecode, and Controls
        header = QHBoxLayout()
        header.setSpacing(10)

        self.btn_play_pause = TransparentToolButton(FluentIcon.PLAY, self)
        self.btn_play_pause.setFixedSize(32, 32)
        self.btn_play_pause.setToolTip("Воспроизвести / Пауза")
        self.btn_play_pause.clicked.connect(self._on_play_pause_clicked)
        header.addWidget(self.btn_play_pause)

        self.btn_stop = TransparentToolButton(FluentIcon.CANCEL, self)
        self.btn_stop.setFixedSize(30, 30)
        self.btn_stop.setToolTip("Остановить")
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        header.addWidget(self.btn_stop)

        self.btn_loop = TransparentToolButton(FluentIcon.SYNC, self)
        self.btn_loop.setFixedSize(30, 30)
        self.btn_loop.setToolTip("Зациклить воспроизведение")
        self.btn_loop.clicked.connect(self._on_loop_clicked)
        header.addWidget(self.btn_loop)

        # Title & Category
        title_box = QHBoxLayout()
        title_box.setSpacing(8)
        self.lbl_title = BodyLabel("Нет выбранного звука", self)
        self.lbl_title.setStyleSheet("font-weight: 600; font-size: 13px;")
        title_box.addWidget(self.lbl_title)

        self.lbl_category = CaptionLabel("", self)
        self.lbl_category.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
            padding: 2px 6px;
            font-weight: 600;
        """)
        self.lbl_category.setVisible(False)
        title_box.addWidget(self.lbl_category)

        header.addLayout(title_box)
        header.addStretch()

        # Timecode Display: 00:00.0 / 00:00.0
        self.lbl_timecode = CaptionLabel("00:00.0 / 00:00.0", self)
        self.lbl_timecode.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; color: rgba(255, 255, 255, 0.7);")
        header.addWidget(self.lbl_timecode)

        layout.addLayout(header)

        # Interactive Waveform Canvas
        self.canvas = WaveformCanvas(self)
        self.canvas.seek_requested.connect(self._on_canvas_seek)
        self.canvas.play_from_seek_requested.connect(self._on_canvas_double_click_play)
        layout.addWidget(self.canvas)

    def load_sound(self, sound_data: Dict[str, Any], buffer: Optional[np.ndarray]):
        """Loads a sound and computes its amplitude waveform peaks."""
        self.current_sound_data = sound_data
        self.current_sound_id = sound_data.get("id")

        name = sound_data.get("name", "Звук")
        cat = sound_data.get("category", "")
        self.lbl_title.setText(name)

        if cat:
            self.lbl_category.setText(cat.upper())
            self.lbl_category.setVisible(True)
        else:
            self.lbl_category.setVisible(False)

        filepath = sound_data.get("path", "")
        peaks = None

        if filepath and filepath in self._peaks_cache:
            peaks = self._peaks_cache[filepath]
        elif buffer is not None and len(buffer) > 0:
            peaks = self._compute_peaks(buffer, num_bars=180)
            if filepath:
                self._peaks_cache[filepath] = peaks

        if peaks is not None:
            self.canvas.set_peaks(peaks)
            if buffer is not None:
                self.total_duration_sec = len(buffer) / 48000.0
        else:
            self.canvas.set_peaks(np.array([]))
            self.total_duration_sec = 0.0

        self.update_progress(0.0, self.total_duration_sec, 0.0)

    @staticmethod
    def _compute_peaks(buffer: np.ndarray, num_bars: int = 180) -> np.ndarray:
        """Extracts normalized amplitude peaks across audio buffer."""
        try:
            if buffer.ndim == 2:
                samples = np.max(np.abs(buffer), axis=1)
            else:
                samples = np.abs(buffer)

            total = len(samples)
            if total < num_bars:
                return np.pad(samples, (0, num_bars - total), mode='constant')

            chunk_size = total // num_bars
            trimmed = samples[:chunk_size * num_bars]
            peaks = np.max(trimmed.reshape(num_bars, chunk_size), axis=1)

            max_val = np.max(peaks)
            if max_val > 0.001:
                peaks = peaks / max_val
            return np.clip(peaks, 0.08, 1.0)
        except Exception:
            return np.ones(num_bars, dtype=np.float32) * 0.2

    def update_progress(self, curr_sec: float, total_sec: float, ratio: float):
        """Updates scrubber playhead and formatted timecode string."""
        if total_sec > 0:
            self.total_duration_sec = total_sec

        self.canvas.set_progress(ratio)

        # Format 00:00.0
        c_min = int(curr_sec // 60)
        c_sec = int(curr_sec % 60)
        c_ms = int((curr_sec - int(curr_sec)) * 10)

        t_min = int(self.total_duration_sec // 60)
        t_sec = int(self.total_duration_sec % 60)
        t_ms = int((self.total_duration_sec - int(self.total_duration_sec)) * 10)

        self.lbl_timecode.setText(f"{c_min:02d}:{c_sec:02d}.{c_ms:01d} / {t_min:02d}:{t_sec:02d}.{t_ms:01d}")

    def set_playing_state(self, playing: bool):
        self.is_playing = playing
        self.btn_play_pause.setIcon(FluentIcon.PAUSE if playing else FluentIcon.PLAY)

    def _on_play_pause_clicked(self):
        self.play_pause_clicked.emit()

    def _on_stop_clicked(self):
        self.set_playing_state(False)
        self.canvas.set_progress(0.0)
        self.update_progress(0.0, self.total_duration_sec, 0.0)
        self.stop_clicked.emit()

    def _on_loop_clicked(self):
        self.is_looping = not self.is_looping
        self.btn_loop.setStyleSheet(
            "background-color: rgba(0, 153, 255, 0.25); border-radius: 4px;"
            if self.is_looping else ""
        )
        self.loop_toggled.emit(self.is_looping)

    def _on_canvas_seek(self, ratio: float):
        curr = ratio * self.total_duration_sec
        self.update_progress(curr, self.total_duration_sec, ratio)
        self.seek_requested.emit(ratio)

    def _on_canvas_double_click_play(self, ratio: float):
        curr = ratio * self.total_duration_sec
        self.update_progress(curr, self.total_duration_sec, ratio)
        self.play_from_seek_requested.emit(ratio)
