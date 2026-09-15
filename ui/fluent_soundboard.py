"""
Fluent Design Soundboard Interface for SoundFlow Studio.
Features Windows 11 Segmented controls, CardWidgets, and modern styling.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFileDialog, QMessageBox, QMenu, QDialog
)
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from qfluentwidgets import (
    CardWidget, PrimaryPushButton, PushButton, TransparentToolButton,
    SearchLineEdit, SegmentedWidget, TitleLabel, SubtitleLabel, BodyLabel,
    CaptionLabel, FluentIcon, RoundMenu, Action, LineEdit
)

from .soundboard_tab import HotkeyCaptureDialog, SoundEditDialog
from .waveform_widget import InteractiveWaveformWidget


class RenameCategoryDialog(QDialog):
    """Clean dialog to rename an existing category."""

    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Переименовать категорию")
        self.setFixedSize(360, 150)
        self.new_name = current_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        lbl = BodyLabel("Новое название категории:", self)
        layout.addWidget(lbl)

        self.edit_name = LineEdit(self)
        self.edit_name.setText(current_name)
        self.edit_name.selectAll()
        self.edit_name.setFixedHeight(34)
        layout.addWidget(self.edit_name)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_cancel = PushButton("Отмена", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, "Сохранить", self)
        self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)

    def _on_save(self):
        val = self.edit_name.text().strip()
        if not val:
            return
        self.new_name = val
        self.accept()


class NewCategoryDialog(QDialog):
    """Clean dialog to enter name for a new category."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новая категория саундборда")
        self.setFixedSize(360, 150)
        self.category_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        lbl = BodyLabel("Введите название новой категории:", self)
        layout.addWidget(lbl)

        self.edit_name = LineEdit(self)
        self.edit_name.setPlaceholderText("Например: Приколы, Трэш, Голоса...")
        self.edit_name.setFixedHeight(34)
        layout.addWidget(self.edit_name)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_cancel = PushButton("Отмена", self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_create = PrimaryPushButton(FluentIcon.ADD, "Создать", self)
        self.btn_create.clicked.connect(self._on_create)
        btn_row.addWidget(self.btn_create)

        layout.addLayout(btn_row)

    def _on_create(self):
        val = self.edit_name.text().strip()
        if not val:
            return
        self.category_name = val
        self.accept()


class FluentSoundCard(CardWidget):
    """Modern Windows 11 Fluent Card representing a soundboard item."""

    card_clicked = pyqtSignal(dict)
    play_clicked = pyqtSignal(str)
    stop_clicked = pyqtSignal(str)
    hotkey_clicked = pyqtSignal(str)
    delete_clicked = pyqtSignal(str)
    favorite_toggled = pyqtSignal(str)
    edit_clicked = pyqtSignal(str)

    def __init__(self, sound_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.sound_data = sound_data
        self.sound_id = sound_data.get("id", "")
        self.is_playing = False
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(14)

        # 1. Play / Pause Button
        self.btn_play = TransparentToolButton(FluentIcon.PLAY, self)
        self.btn_play.setFixedSize(38, 38)
        self.btn_play.clicked.connect(self._toggle_play)
        layout.addWidget(self.btn_play)

        # 2. Info Column
        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        self.lbl_title = BodyLabel(self.sound_data.get("name", "Untitled Sound"), self)
        self.lbl_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        title_row.addWidget(self.lbl_title)

        category = self.sound_data.get("category", "General")
        self.lbl_category = CaptionLabel(category.upper(), self)
        self.lbl_category.setStyleSheet("""
            background-color: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
            padding: 2px 6px;
            font-weight: 600;
        """)
        title_row.addWidget(self.lbl_category)
        title_row.addStretch()
        info_col.addLayout(title_row)

        vol_pct = int(self.sound_data.get("volume", 1.0) * 100)
        spd_val = self.sound_data.get("speed", 1.0)
        dur_text = self.sound_data.get("duration", "")
        meta_str = f"Громкость: {vol_pct}%  •  Скорость: {spd_val:.1f}x"
        if dur_text:
            meta_str = f"{dur_text}  •  " + meta_str

        self.lbl_meta = CaptionLabel(meta_str, self)
        self.lbl_meta.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        info_col.addWidget(self.lbl_meta)

        layout.addLayout(info_col, stretch=1)

        # 3. Hotkey Pill Button
        hotkey = self.sound_data.get("hotkey", "")
        self.btn_hotkey = PushButton(f"[{hotkey.upper()}]" if hotkey else "[+ Хоткей]", self)
        self.btn_hotkey.setFixedHeight(30)
        self.btn_hotkey.setToolTip("Назначить горячую клавишу")
        self.btn_hotkey.clicked.connect(lambda: self.hotkey_clicked.emit(self.sound_id))
        layout.addWidget(self.btn_hotkey)

        # 4. Favorite Star
        self.is_fav = bool(self.sound_data.get("favorite", False))
        self.btn_fav = TransparentToolButton(
            FluentIcon.FAVORITE if self.is_fav else FluentIcon.HEART,
            self
        )
        self.btn_fav.setFixedSize(32, 32)
        self.btn_fav.clicked.connect(self._toggle_fav)
        layout.addWidget(self.btn_fav)

        # 5. More Actions
        self.btn_more = TransparentToolButton(FluentIcon.MORE, self)
        self.btn_more.setFixedSize(32, 32)
        self.btn_more.clicked.connect(self._show_menu)
        layout.addWidget(self.btn_more)

    def _toggle_play(self):
        if self.is_playing:
            self.stop_clicked.emit(self.sound_id)
        else:
            self.play_clicked.emit(self.sound_id)

    def set_playing(self, playing: bool):
        self.is_playing = playing
        self.btn_play.setIcon(FluentIcon.PAUSE if playing else FluentIcon.PLAY)

    def _toggle_fav(self):
        self.is_fav = not self.is_fav
        self.btn_fav.setIcon(FluentIcon.FAVORITE if self.is_fav else FluentIcon.HEART)
        self.favorite_toggled.emit(self.sound_id)

    def set_hotkey_text(self, hotkey: str):
        self.btn_hotkey.setText(f"[{hotkey.upper()}]" if hotkey else "[+ Хоткей]")

    def _show_menu(self):
        menu = RoundMenu(parent=self)
        menu.addAction(Action(FluentIcon.EDIT, "Настроить громкость и параметры", triggered=lambda: self.edit_clicked.emit(self.sound_id)))
        menu.addAction(Action(FluentIcon.CERTIFICATE, "Назначить горячую клавишу", triggered=lambda: self.hotkey_clicked.emit(self.sound_id)))
        menu.addSeparator()
        menu.addAction(Action(FluentIcon.DELETE, "Удалить из саундборда", triggered=lambda: self.delete_clicked.emit(self.sound_id)))
        menu.exec(self.btn_more.mapToGlobal(self.btn_more.rect().bottomLeft()))

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.card_clicked.emit(self.sound_data)


class FluentSoundboardInterface(QWidget):
    """Windows 11 Fluent Design Soundboard View."""

    sound_play_requested = pyqtSignal(dict)
    sound_stop_requested = pyqtSignal(str)
    hotkey_updated = pyqtSignal(str, str)

    def __init__(self, audio_engine, config_manager=None, parent=None):
        super().__init__(parent)
        if config_manager is None:
            self.engine = None
            self.cfg = audio_engine
        else:
            self.engine = audio_engine
            self.cfg = config_manager

        self.setObjectName("soundboardInterface")
        self.setAcceptDrops(True)

        self.cards: Dict[str, FluentSoundCard] = {}
        self.current_category = "ALL"
        self.active_playing_id: Optional[str] = None
        self.last_selected_sound: Optional[Dict[str, Any]] = None

        self._build_ui()
        self.refresh_sounds()

        # Real-time progress timer for waveform playhead (~33 FPS)
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self._update_waveform_progress)
        self.progress_timer.start(30)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 28)
        layout.setSpacing(14)

        # Header Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = TitleLabel("Саундборд", self)
        lbl_sub = CaptionLabel("Воспроизведение аудиоэффектов, горячие клавиши и управление звуками", self)
        lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        layout.addLayout(title_layout)

        # Command Bar: Add Button, Search Box, Segmented Categories
        cmd_bar = QHBoxLayout()
        cmd_bar.setSpacing(12)

        self.btn_add = PrimaryPushButton(FluentIcon.ADD, "Добавить звук", self)
        self.btn_add.setFixedHeight(34)
        self.btn_add.clicked.connect(self._open_file_dialog)
        cmd_bar.addWidget(self.btn_add)

        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText("Поиск звука по названию...")
        self.search_box.setFixedHeight(34)
        self.search_box.textChanged.connect(self._filter_sounds)
        cmd_bar.addWidget(self.search_box, stretch=1)

        layout.addLayout(cmd_bar)

        # Windows 11 Segmented Navigation Bar + Dynamic Category Buttons
        cat_bar = QHBoxLayout()
        cat_bar.setSpacing(6)

        self.seg_categories = SegmentedWidget(self)
        self.seg_categories.currentItemChanged.connect(self._on_category_changed)
        cat_bar.addWidget(self.seg_categories)

        self.btn_add_cat = TransparentToolButton(FluentIcon.ADD, self)
        self.btn_add_cat.setToolTip("Создать новую категорию / вкладку")
        self.btn_add_cat.clicked.connect(self._prompt_add_category)
        cat_bar.addWidget(self.btn_add_cat)

        self.btn_del_cat = TransparentToolButton(FluentIcon.DELETE, self)
        self.btn_del_cat.setToolTip("Удалить выбранную категорию (звуки будут перемещены в SFX)")
        self.btn_del_cat.clicked.connect(self._prompt_delete_current_category)
        self.btn_del_cat.setVisible(False)
        cat_bar.addWidget(self.btn_del_cat)

        cat_bar.addStretch()
        layout.addLayout(cat_bar)

        self.refresh_categories(select_id="ALL")

        # Real-time Interactive Waveform Track & Draggable Scrubber
        self.waveform = InteractiveWaveformWidget(self)
        self.waveform.seek_requested.connect(self._on_waveform_seek)
        self.waveform.play_from_seek_requested.connect(self._on_waveform_double_click_play)
        self.waveform.play_pause_clicked.connect(self._on_waveform_play_pause)
        self.waveform.stop_clicked.connect(self._on_waveform_stop)
        self.waveform.loop_toggled.connect(self._on_waveform_loop)
        layout.addWidget(self.waveform)

        # Scrollable Sound Grid
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.card_container = QWidget()
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(0, 0, 10, 0)
        self.card_layout.setSpacing(8)

        # Empty state message if no sounds in category
        self.lbl_empty = CaptionLabel("В этой категории пока нет звуков.\nНажмите «Добавить звук» или отметьте звёздочкой любимые звуки в саундборде.", self.card_container)
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("color: rgba(255, 255, 255, 0.45); font-size: 13px; padding: 40px 10px;")
        self.lbl_empty.setVisible(False)
        self.card_layout.addWidget(self.lbl_empty)

        self.card_layout.addStretch()

        self.scroll.setWidget(self.card_container)
        layout.addWidget(self.scroll, stretch=1)

    def refresh_categories(self, select_id: Optional[str] = None):
        target = select_id or self.current_category
        self.seg_categories.blockSignals(True)
        self.seg_categories.clear()

        cats = self.cfg.get_categories()
        existing_ids = [c["id"] for c in cats]
        for c in cats:
            self.seg_categories.addItem(c["id"], c["name"])
            item = self.seg_categories.items.get(c["id"])
            if item and not c.get("system", False):
                item.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                cid = c["id"]
                cname = c["name"]
                item.customContextMenuRequested.connect(
                    lambda pos, k=cid, n=cname, it=item: self._show_category_context_menu(k, n, it.mapToGlobal(pos))
                )

        if target not in existing_ids:
            target = "ALL"
        self.current_category = target
        self.seg_categories.setCurrentItem(target)
        self.seg_categories.blockSignals(False)

        self._update_cat_delete_button()
        self._filter_sounds()

    def _show_category_context_menu(self, cat_id: str, cat_name: str, global_pos: QPoint):
        self.seg_categories.setCurrentItem(cat_id)
        sound_count = sum(1 for s in self.cfg.sounds if str(s.get("category", "")).upper() == cat_id.upper())

        menu = RoundMenu(parent=self)
        menu.addAction(Action(
            FluentIcon.EDIT,
            f"Переименовать категорию «{cat_name}»",
            triggered=lambda: self._prompt_rename_category(cat_id, cat_name)
        ))
        menu.addAction(Action(
            FluentIcon.MOVE,
            f"Удалить категорию (переместить звуки во «Все») [{sound_count} шт.]",
            triggered=lambda: self._prompt_delete_category(cat_id, cat_name, delete_sounds=False)
        ))
        menu.addSeparator()
        menu.addAction(Action(
            FluentIcon.DELETE,
            f"Удалить вместе с содержимым ({sound_count} звуков)",
            triggered=lambda: self._prompt_delete_category(cat_id, cat_name, delete_sounds=True)
        ))
        menu.exec(global_pos)

    def _prompt_rename_category(self, cat_id: str, current_name: str):
        dlg = RenameCategoryDialog(current_name, parent=self)
        if dlg.exec():
            new_name = dlg.new_name
            if self.cfg.rename_category(cat_id, new_name):
                self.refresh_categories(select_id=cat_id)
                self.refresh_sounds()
                main_win = self.window()
                if hasattr(main_win, "settings_interface"):
                    main_win.settings_interface._refresh_categories_list()

    def _prompt_delete_category(self, cat_id: str, cat_name: str, delete_sounds: bool = False):
        sound_count = sum(1 for s in self.cfg.sounds if str(s.get("category", "")).upper() == cat_id.upper())

        if delete_sounds:
            reply = QMessageBox.warning(
                self,
                "Удаление категории с содержимым",
                f"Вы действительно хотите удалить категорию «{cat_name}» и ВСЕ входящие в неё звуки ({sound_count} шт.)?\n\n"
                "Это действие безвозвратно удалит категорию и все входящие в неё звуки из саундборда!",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
        else:
            reply = QMessageBox.question(
                self,
                "Удаление категории",
                f"Удалить категорию «{cat_name}»?\n\n"
                f"Все звуки из этой категории ({sound_count} шт.) останутся на саундборде и будут доступны во вкладке «Все» (перенесены в категорию SFX).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

        if reply == QMessageBox.StandardButton.Yes:
            if delete_sounds:
                for s in self.cfg.sounds:
                    if str(s.get("category", "")).upper() == cat_id.upper():
                        self.sound_stop_requested.emit(s["id"])

            self.cfg.remove_category(cat_id, delete_sounds=delete_sounds)
            self.refresh_categories(select_id="ALL")
            self.refresh_sounds()
            main_win = self.window()
            if hasattr(main_win, "settings_interface"):
                main_win.settings_interface._refresh_categories_list()

    def _update_cat_delete_button(self):
        cats = self.cfg.get_categories()
        curr_cat_obj = next((c for c in cats if c["id"] == self.current_category), None)
        is_custom = curr_cat_obj is not None and not curr_cat_obj.get("system", False)
        self.btn_del_cat.setVisible(is_custom)

    def _prompt_add_category(self):
        dlg = NewCategoryDialog(parent=self)
        if dlg.exec():
            name = dlg.category_name
            new_cat = self.cfg.add_category(name)
            if new_cat:
                self.refresh_categories(select_id=new_cat["id"])
                main_win = self.window()
                if hasattr(main_win, "settings_interface"):
                    main_win.settings_interface._refresh_categories_list()

    def _prompt_delete_current_category(self):
        cats = self.cfg.get_categories()
        curr_cat_obj = next((c for c in cats if c["id"] == self.current_category), None)
        if not curr_cat_obj or curr_cat_obj.get("system", False):
            return

        cat_name = curr_cat_obj.get("name", self.current_category)
        sound_count = sum(1 for s in self.cfg.sounds if str(s.get("category", "")).upper() == self.current_category.upper())

        menu = RoundMenu(parent=self)
        menu.addAction(Action(
            FluentIcon.MOVE,
            f"Сохранить звуки во «Все» [{sound_count} шт.]",
            triggered=lambda: self._prompt_delete_category(self.current_category, cat_name, delete_sounds=False)
        ))
        menu.addAction(Action(
            FluentIcon.DELETE,
            f"Удалить вместе с содержимым ({sound_count} шт.)",
            triggered=lambda: self._prompt_delete_category(self.current_category, cat_name, delete_sounds=True)
        ))
        menu.exec(self.btn_del_cat.mapToGlobal(self.btn_del_cat.rect().bottomLeft()))

    def _on_category_changed(self, cat_key: str):
        if not isinstance(cat_key, str):
            return
        self.current_category = cat_key.upper()
        self._update_cat_delete_button()
        self._filter_sounds()

    def _update_waveform_progress(self):
        if not self.engine or not self.active_playing_id:
            return
        prog = self.engine.get_sound_progress(self.active_playing_id)
        if prog:
            curr_sec, total_sec, ratio = prog
            self.waveform.update_progress(curr_sec, total_sec, ratio)
        else:
            self.set_sound_playing(self.active_playing_id, False)

    def _on_waveform_seek(self, ratio: float):
        if self.engine and self.active_playing_id:
            self.engine.seek_sound(self.active_playing_id, ratio)

    def _on_waveform_double_click_play(self, ratio: float):
        if not self.last_selected_sound:
            return
        sound_id = self.last_selected_sound["id"]
        if not self.active_playing_id or self.active_playing_id != sound_id or not self.waveform.is_playing:
            self.sound_play_requested.emit(self.last_selected_sound)
            self.active_playing_id = sound_id
            self.set_sound_playing(sound_id, True)

        if self.engine:
            self.engine.seek_sound(sound_id, ratio)
            curr_sec = ratio * self.waveform.total_duration_sec
            self.waveform.update_progress(curr_sec, self.waveform.total_duration_sec, ratio)
            self.waveform.set_playing_state(True)

    def _on_waveform_play_pause(self):
        if self.active_playing_id:
            self.sound_stop_requested.emit(self.active_playing_id)
            self.set_sound_playing(self.active_playing_id, False)
        elif self.last_selected_sound:
            self.sound_play_requested.emit(self.last_selected_sound)

    def _on_waveform_stop(self):
        if self.active_playing_id:
            self.sound_stop_requested.emit(self.active_playing_id)
            self.set_sound_playing(self.active_playing_id, False)

    def _on_waveform_loop(self, is_looping: bool):
        if self.last_selected_sound:
            self.last_selected_sound["loop"] = is_looping

    def load_sound_to_waveform(self, sound_data: Dict[str, Any]):
        self.last_selected_sound = sound_data
        buf = None
        if self.engine:
            buf = self.engine.get_sound_buffer(sound_data.get("path", ""))
        self.waveform.load_sound(sound_data, buf)

    def refresh_sounds(self):
        for c in self.cards.values():
            c.setParent(None)
            c.deleteLater()
        self.cards.clear()

        for s in self.cfg.sounds:
            card = FluentSoundCard(s, self.card_container)
            card.card_clicked.connect(self.load_sound_to_waveform)
            card.play_clicked.connect(lambda sid, d=s: self.sound_play_requested.emit(d))
            card.stop_clicked.connect(lambda sid: self.sound_stop_requested.emit(sid))
            card.hotkey_clicked.connect(self._prompt_hotkey)
            card.delete_clicked.connect(self._delete_sound)
            card.favorite_toggled.connect(self._toggle_favorite)
            card.edit_clicked.connect(self._edit_sound)

            self.cards[s["id"]] = card
            self.card_layout.insertWidget(self.card_layout.count() - 1, card)

        if self.last_selected_sound is None and len(self.cfg.sounds) > 0:
            self.load_sound_to_waveform(self.cfg.sounds[0])

        self._filter_sounds()

    def _filter_sounds(self):
        query = self.search_box.text().strip().lower()
        curr_cat = str(self.current_category).upper()
        visible_count = 0

        for s in self.cfg.sounds:
            sid = s["id"]
            card = self.cards.get(sid)
            if not card:
                continue

            matches_cat = True
            if curr_cat == "FAVORITES":
                matches_cat = bool(s.get("favorite", False))
            elif curr_cat == "ALL":
                matches_cat = True
            else:
                sound_cat = str(s.get("category", "")).upper()
                matches_cat = (sound_cat == curr_cat)

            matches_query = query in s.get("name", "").lower() if query else True
            is_visible = bool(matches_cat and matches_query)
            card.setVisible(is_visible)
            if is_visible:
                visible_count += 1

        if hasattr(self, "lbl_empty"):
            self.lbl_empty.setVisible(visible_count == 0)

    def _prompt_hotkey(self, sound_id: str):
        sound = next((s for s in self.cfg.sounds if s["id"] == sound_id), None)
        if not sound:
            return
        dlg = HotkeyCaptureDialog(sound.get("hotkey", ""), parent=self)
        if dlg.exec():
            new_key = dlg.captured_key
            self.cfg.update_sound(sound_id, {"hotkey": new_key})
            card = self.cards.get(sound_id)
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
        dlg = SoundEditDialog(sound, categories=self.cfg.get_categories(), parent=self)
        if dlg.exec():
            self.cfg.update_sound(sound_id, dlg.sound_data)
            self.refresh_sounds()

    def _delete_sound(self, sound_id: str):
        reply = QMessageBox.question(
            self,
            "Удаление звука",
            "Вы уверены, что хотите удалить этот звук?",
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
            "Аудиофайлы (*.mp3 *.wav *.ogg *.flac *.m4a);;Все файлы (*.*)"
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
        card = self.cards.get(sound_id)
        if card:
            card.set_playing(is_playing)

        if is_playing:
            self.active_playing_id = sound_id
            sound_data = next((s for s in self.cfg.sounds if s["id"] == sound_id), None)
            if sound_data:
                self.load_sound_to_waveform(sound_data)
            self.waveform.set_playing_state(True)
        else:
            if self.active_playing_id == sound_id:
                self.active_playing_id = None
                self.waveform.set_playing_state(False)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            fpath = url.toLocalFile()
            if fpath.lower().endswith((".mp3", ".wav", ".ogg", ".flac", ".m4a")):
                self.add_sound_file(fpath)
