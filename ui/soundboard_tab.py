"""
Soundboard Tab for SoundFlow Studio.
Features categorized grid/list of sounds, drag-and-drop addition, search/filter,
hotkey assignment, and sound fine-tuning (trim, speed, volume).
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFileDialog, QDialog, QSlider,
    QComboBox, QMessageBox, QFrame, QGridLayout
)
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QKeySequence

from .widgets import SoundCardWidget


from core.i18n import tr


class HotkeyCaptureDialog(QDialog):
    """Dialog that captures a global keyboard key combination."""

    def __init__(self, current_hotkey: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("soundboard_menu_hotkey", "Назначение горячей клавиши"))
        self.setFixedSize(360, 200)
        self.captured_key = current_hotkey

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        lbl = QLabel(tr("soundboard_dlg_press_hotkey", "Нажмите нужную клавишу или сочетание на клавиатуре:"))
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #94a3b8; font-size: 13px;")
        layout.addWidget(lbl)

        wait_text = "..." if not self.captured_key else self.captured_key.upper()
        self.key_box = QLabel(wait_text)
        self.key_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.key_box.setStyleSheet("""
            background: #1e293b;
            color: #00f2fe;
            font-size: 16px;
            font-weight: 700;
            border: 2px dashed #38bdf8;
            border-radius: 8px;
            padding: 16px;
        """)
        layout.addWidget(self.key_box)

        btn_layout = QHBoxLayout()
        self.btn_clear = QPushButton(tr("voice_fx_btn_reset", "Сбросить"))
        self.btn_clear.clicked.connect(self._clear_key)
        btn_layout.addWidget(self.btn_clear)

        btn_layout.addStretch()

        self.btn_cancel = QPushButton(tr("common_cancel", "Отмена"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(tr("common_save", "Сохранить"))
        self.btn_save.setObjectName("AccentButton")
        self.btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return

        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")

        key_seq = QKeySequence(key).toString().lower()
        if key_seq:
            # Map numpad keys cleanly
            if "keypad" in key_seq:
                key_seq = key_seq.replace("keypad+", "num ")
            parts.append(key_seq)

        self.captured_key = "+".join(parts)
        self.key_box.setText(self.captured_key.upper())

    def _clear_key(self):
        self.captured_key = ""
        self.key_box.setText("НЕТ (ОЧИЩЕНО)")


class SoundEditDialog(QDialog):
    """Dialog to adjust individual sound settings (Volume, Pitch, Speed, Trimming)."""

    def __init__(self, sound_data: Dict[str, Any], categories: Optional[List[Dict[str, Any]]] = None, parent=None):
        super().__init__(parent)
        title_tpl = tr("soundboard_dlg_edit_title", "Параметры звука: {name}")
        self.setWindowTitle(title_tpl.format(name=sound_data.get('name', 'Sound')))
        self.setFixedSize(400, 360)
        self.sound_data = sound_data.copy()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Name
        layout.addWidget(QLabel(tr("soundboard_dlg_edit_name", "Название звука:")))
        self.edit_name = QLineEdit(self.sound_data.get("name", ""))
        layout.addWidget(self.edit_name)

        # Category
        layout.addWidget(QLabel(tr("soundboard_menu_move_cat", "Категория:")))
        self.combo_category = QComboBox()
        self.combo_category.setEditable(True)

        curr_cat = str(self.sound_data.get("category", "SFX")).strip()
        available_cats = []
        if categories:
            for c in categories:
                c_id = c.get("id", "")
                c_name = c.get("name", "")
                if c_id not in ("ALL", "FAVORITES"):
                    available_cats.append(c_id)
                    self.combo_category.addItem(f"{c_name} ({c_id})", c_id)
        if not available_cats:
            for d in ["MEMES", "GAMING", "SFX", "CLIPS"]:
                self.combo_category.addItem(d, d)

        idx = self.combo_category.findData(curr_cat.upper())
        if idx >= 0:
            self.combo_category.setCurrentIndex(idx)
        else:
            self.combo_category.setCurrentText(curr_cat)

        layout.addWidget(self.combo_category)

        # Volume slider
        vol_val = int(self.sound_data.get("volume", 1.0) * 100)
        vol_tpl = tr("soundboard_dlg_edit_vol", "Громкость звука: {vol}%")
        self.lbl_vol = QLabel(vol_tpl.format(vol=vol_val))
        layout.addWidget(self.lbl_vol)
        self.slider_vol = QSlider(Qt.Orientation.Horizontal)
        self.slider_vol.setRange(0, 200)
        self.slider_vol.setValue(vol_val)
        self.slider_vol.valueChanged.connect(lambda v: self.lbl_vol.setText(vol_tpl.format(vol=v)))
        layout.addWidget(self.slider_vol)

        # Speed slider
        spd_val = int(self.sound_data.get("speed", 1.0) * 100)
        self.lbl_spd = QLabel(f"Speed: {spd_val / 100:.1f}x")
        layout.addWidget(self.lbl_spd)
        self.slider_spd = QSlider(Qt.Orientation.Horizontal)
        self.slider_spd.setRange(50, 200)
        self.slider_spd.setValue(spd_val)
        self.slider_spd.valueChanged.connect(lambda v: self.lbl_spd.setText(f"Speed: {v / 100:.1f}x"))
        layout.addWidget(self.slider_spd)

        # Playback Mode
        layout.addWidget(QLabel(tr("soundboard_dlg_edit_mode", "Режим воспроизведения:")))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(tr("soundboard_mode_normal", "Обычный (клик для старта / повторный для стопа)"), "normal")
        self.combo_mode.addItem(tr("soundboard_mode_hold", "Удерживать (играть, пока зажат хоткей)"), "hold")
        curr_mode = self.sound_data.get("play_mode", "normal")
        idx_mode = self.combo_mode.findData(curr_mode)
        if idx_mode >= 0:
            self.combo_mode.setCurrentIndex(idx_mode)
        layout.addWidget(self.combo_mode)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton(tr("common_cancel", "Отмена"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(tr("common_save", "Сохранить"))
        self.btn_save.setObjectName("AccentButton")
        self.btn_save.clicked.connect(self._save_changes)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def _save_changes(self):
        self.sound_data["name"] = self.edit_name.text().strip() or "Sound"
        cat_data = self.combo_category.currentData()
        if cat_data:
            self.sound_data["category"] = cat_data
        else:
            raw_text = self.combo_category.currentText().strip()
            self.sound_data["category"] = raw_text.split(" (")[0].strip() or "SFX"
        self.sound_data["volume"] = self.slider_vol.value() / 100.0
        self.sound_data["speed"] = self.slider_spd.value() / 100.0
        self.sound_data["play_mode"] = self.combo_mode.currentData() or "normal"
        self.accept()


class SoundboardTab(QWidget):
    """Main Soundboard view with category filters, search, and sound grid."""

    sound_play_requested = pyqtSignal(dict)  # sound_data
    sound_stop_requested = pyqtSignal(str)   # sound_id
    hotkey_updated = pyqtSignal(str, str)    # sound_id, hotkey

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.cfg = config_manager
        self.setAcceptDrops(True)

        self.sound_cards: Dict[str, SoundCardWidget] = {}
        self.current_category = "ALL"

        self._build_ui()
        self.refresh_sounds()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # Top Bar: Add Sound, Search, Category Chips
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.btn_add = QPushButton("+ Добавить звук")
        self.btn_add.setObjectName("AccentButton")
        self.btn_add.clicked.connect(self._open_file_dialog)
        top_bar.addWidget(self.btn_add)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Поиск звуков по названию...")
        self.search_box.textChanged.connect(self._filter_sounds)
        top_bar.addWidget(self.search_box, stretch=1)

        main_layout.addLayout(top_bar)

        # Category Filter Bar
        cat_layout = QHBoxLayout()
        cat_layout.setSpacing(6)

        categories = ["ALL", "FAVORITES", "MEMES", "GAMING", "SFX", "CLIPS"]
        self.cat_buttons = {}
        for cat in categories:
            btn = QPushButton(cat)
            btn.setFixedHeight(28)
            btn.setStyleSheet("""
                QPushButton {
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 14px;
                    padding: 2px 14px;
                    font-size: 11px;
                    font-weight: 700;
                    color: #94a3b8;
                }
                QPushButton:hover {
                    background: #334155;
                    color: #ffffff;
                }
            """)
            btn.clicked.connect(lambda checked, c=cat: self._set_category(c))
            cat_layout.addWidget(btn)
            self.cat_buttons[cat] = btn

        cat_layout.addStretch()
        main_layout.addLayout(cat_layout)

        # Scrollable Sound Grid
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.grid_container = QWidget()
        self.grid_layout = QVBoxLayout(self.grid_container)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(0, 0, 8, 0)
        self.grid_layout.addStretch()

        self.scroll_area.setWidget(self.grid_container)
        main_layout.addWidget(self.scroll_area, stretch=1)

    def _set_category(self, category: str):
        self.current_category = category
        for cat, btn in self.cat_buttons.items():
            if cat == category:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #00f2fe;
                        border: none;
                        border-radius: 14px;
                        padding: 2px 14px;
                        font-size: 11px;
                        font-weight: 700;
                        color: #0b0f19;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #1e293b;
                        border: 1px solid #334155;
                        border-radius: 14px;
                        padding: 2px 14px;
                        font-size: 11px;
                        font-weight: 700;
                        color: #94a3b8;
                    }
                    QPushButton:hover {
                        background: #334155;
                        color: #ffffff;
                    }
                """)
        self._filter_sounds()

    def refresh_sounds(self):
        """Clears and re-populates the sound cards from config."""
        # Clear existing
        for card in self.sound_cards.values():
            card.setParent(None)
            card.deleteLater()
        self.sound_cards.clear()

        # Populate
        sounds = self.cfg.sounds
        for s in sounds:
            card = SoundCardWidget(s)
            card.play_clicked.connect(lambda sid, d=s: self.sound_play_requested.emit(d))
            card.stop_clicked.connect(lambda sid: self.sound_stop_requested.emit(sid))
            card.hotkey_clicked.connect(self._prompt_hotkey)
            card.delete_clicked.connect(self._delete_sound)
            card.favorite_toggled.connect(self._toggle_favorite)
            card.edit_clicked.connect(self._edit_sound)

            self.sound_cards[s["id"]] = card
            # Insert before the stretch at end
            self.grid_layout.insertWidget(self.grid_layout.count() - 1, card)

        self._filter_sounds()

    def _filter_sounds(self):
        query = self.search_box.text().strip().lower()
        for s in self.cfg.sounds:
            sid = s["id"]
            card = self.sound_cards.get(sid)
            if not card:
                continue

            matches_cat = True
            if self.current_category == "FAVORITES":
                matches_cat = bool(s.get("favorite", False))
            elif self.current_category != "ALL":
                matches_cat = s.get("category", "").upper() == self.current_category

            matches_query = query in s.get("name", "").lower() if query else True
            card.setVisible(matches_cat and matches_query)

    def _prompt_hotkey(self, sound_id: str):
        sound = next((s for s in self.cfg.sounds if s["id"] == sound_id), None)
        if not sound:
            return

        dlg = HotkeyCaptureDialog(sound.get("hotkey", ""), parent=self)
        if dlg.exec():
            new_key = dlg.captured_key
            self.cfg.update_sound(sound_id, {"hotkey": new_key})
            card = self.sound_cards.get(sound_id)
            if card:
                card.set_hotkey_text(new_key)
            self.hotkey_updated.emit(sound_id, new_key)

    def _toggle_favorite(self, sound_id: str):
        sound = next((s for s in self.cfg.sounds if s["id"] == sound_id), None)
        if sound:
            is_fav = not sound.get("favorite", False)
            self.cfg.update_sound(sound_id, {"favorite": is_fav})

    def _edit_sound(self, sound_id: str):
        sound = next((s for s in self.cfg.sounds if s["id"] == sound_id), None)
        if not sound:
            return
        dlg = SoundEditDialog(sound, parent=self)
        if dlg.exec():
            self.cfg.update_sound(sound_id, dlg.sound_data)
            self.refresh_sounds()

    def _delete_sound(self, sound_id: str):
        reply = QMessageBox.question(
            self,
            "Удаление звука",
            "Вы уверены, что хотите удалить этот звук из списка?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.sound_stop_requested.emit(sound_id)
            self.cfg.remove_sound(sound_id)
            self.refresh_sounds()

    def _open_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите аудиофайлы",
            "",
            "Audio Files (*.mp3 *.wav *.ogg *.flac *.m4a);;All Files (*.*)"
        )
        for f in files:
            self.add_sound_file(f)

    def add_sound_file(self, filepath: str, category: str = "General") -> str:
        p = Path(filepath)
        if not p.exists():
            return ""

        sound_id = f"snd_{p.stem}_{os.urandom(3).hex()}"
        sound_data = {
            "id": sound_id,
            "name": p.stem.replace("_", " ").title(),
            "path": str(p),
            "category": category,
            "hotkey": "",
            "volume": 1.0,
            "pitch": 1.0,
            "speed": 1.0,
            "favorite": False
        }
        self.cfg.add_sound(sound_data)
        self.refresh_sounds()
        return sound_id

    def set_sound_playing(self, sound_id: str, is_playing: bool):
        card = self.sound_cards.get(sound_id)
        if card:
            card.set_playing(is_playing)

    # Drag & Drop Support
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            fpath = url.toLocalFile()
            if fpath.lower().endswith((".mp3", ".wav", ".ogg", ".flac", ".m4a")):
                self.add_sound_file(fpath)
