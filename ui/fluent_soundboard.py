"""
Fluent Design Soundboard Interface for SoundFlow Studio.
Features Windows 11 Segmented controls, CardWidgets, modern styling,
folder-based category import, move-to-category menu, and full i18n localization.
"""

import os
import random
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFileDialog, QMessageBox, QMenu, QDialog
)
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from qfluentwidgets import (
    CardWidget, PrimaryPushButton, PushButton, TransparentToolButton,
    SearchLineEdit, SegmentedWidget, TitleLabel, SubtitleLabel, BodyLabel,
    CaptionLabel, FluentIcon, RoundMenu, Action, LineEdit, ComboBox, InfoBar
)

from core.i18n import tr
from .soundboard_tab import HotkeyCaptureDialog, SoundEditDialog
from .waveform_widget import InteractiveWaveformWidget


class RenameCategoryDialog(QDialog):
    """Clean dialog to rename an existing category."""

    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("soundboard_dlg_rename_cat_title", "Переименовать категорию"))
        self.setFixedSize(360, 150)
        self.new_name = current_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        lbl = BodyLabel(tr("soundboard_dlg_rename_prompt", "Новое название категории:"), self)
        layout.addWidget(lbl)

        self.edit_name = LineEdit(self)
        self.edit_name.setText(current_name)
        self.edit_name.selectAll()
        self.edit_name.setFixedHeight(34)
        layout.addWidget(self.edit_name)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_cancel = PushButton(tr("common_cancel", "Отмена"), self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, tr("common_save", "Сохранить"), self)
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
        self.setWindowTitle(tr("soundboard_dlg_new_cat_title", "Новая категория саундборда"))
        self.setFixedSize(360, 150)
        self.category_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        lbl = BodyLabel(tr("soundboard_dlg_new_cat_prompt", "Введите название новой категории:"), self)
        layout.addWidget(lbl)

        self.edit_name = LineEdit(self)
        self.edit_name.setPlaceholderText(tr("soundboard_dlg_new_cat_placeholder", "Например: Приколы, Трэш, Голоса..."))
        self.edit_name.setFixedHeight(34)
        layout.addWidget(self.edit_name)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_cancel = PushButton(tr("common_cancel", "Отмена"), self)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_create = PrimaryPushButton(FluentIcon.ADD, tr("common_create", "Создать"), self)
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
    category_change_requested = pyqtSignal(str, str)  # sound_id, target_category_id
    create_category_requested = pyqtSignal(str)       # sound_id

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
        meta_str = f"Vol: {vol_pct}%  •  Speed: {spd_val:.1f}x"
        if dur_text:
            meta_str = f"{dur_text}  •  " + meta_str

        self.lbl_meta = CaptionLabel(meta_str, self)
        self.lbl_meta.setStyleSheet("color: rgba(255, 255, 255, 0.5);")
        info_col.addWidget(self.lbl_meta)

        layout.addLayout(info_col, stretch=1)

        # 3. Hotkey Pill Button
        hotkey = self.sound_data.get("hotkey", "")
        self.btn_hotkey = PushButton(f"[{hotkey.upper()}]" if hotkey else tr("soundboard_btn_hotkey_add", "[+ Хоткей]"), self)
        self.btn_hotkey.setFixedHeight(30)
        self.btn_hotkey.setToolTip(tr("soundboard_menu_hotkey", "Назначить горячую клавишу"))
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
        self.btn_hotkey.setText(f"[{hotkey.upper()}]" if hotkey else tr("soundboard_btn_hotkey_add", "[+ Хоткей]"))

    def _show_menu(self):
        menu = RoundMenu(parent=self)
        menu.addAction(Action(
            FluentIcon.EDIT,
            tr("soundboard_menu_edit", "Настроить громкость и параметры"),
            triggered=lambda: self.edit_clicked.emit(self.sound_id)
        ))
        menu.addAction(Action(
            FluentIcon.CERTIFICATE,
            tr("soundboard_menu_hotkey", "Назначить горячую клавишу"),
            triggered=lambda: self.hotkey_clicked.emit(self.sound_id)
        ))

        # Submenu: Move to Category
        move_menu = RoundMenu(tr("soundboard_menu_move_cat", "Переместить в категорию"), parent=menu)
        move_menu.setIcon(FluentIcon.FOLDER)

        # Retrieve categories from parent Soundboard interface
        p = self.parent()
        while p and not hasattr(p, "cfg"):
            p = p.parent()
        cfg = getattr(p, "cfg", None) if p else None

        current_cat = str(self.sound_data.get("category", "SFX")).upper()
        if cfg:
            for c in cfg.get_categories():
                cid = c.get("id", "")
                if cid.upper() in ("ALL", "FAVORITES"):
                    continue
                cname = c.get("name", cid)
                is_cur = (cid.upper() == current_cat)
                label = f"✓ {cname}" if is_cur else f"    {cname}"
                act = Action(label, parent=move_menu)
                act.triggered.connect(lambda checked=False, target=cid: self.category_change_requested.emit(self.sound_id, target))
                move_menu.addAction(act)

        move_menu.addSeparator()
        act_new = Action(FluentIcon.ADD, tr("soundboard_menu_new_cat", "➕ Новая категория..."), parent=move_menu)
        act_new.triggered.connect(lambda: self.create_category_requested.emit(self.sound_id))
        move_menu.addAction(act_new)

        menu.addMenu(move_menu)
        menu.addSeparator()
        menu.addAction(Action(
            FluentIcon.DELETE,
            tr("soundboard_menu_delete", "Удалить из саундборда"),
            triggered=lambda: self.delete_clicked.emit(self.sound_id)
        ))
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
        self._load_target_devices()
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
        lbl_title = TitleLabel(tr("soundboard_title", "Саундборд"), self)
        lbl_sub = CaptionLabel(tr("soundboard_subtitle", "Воспроизведение аудиоэффектов, горячие клавиши и управление звуками"), self)
        lbl_sub.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        title_layout.addWidget(lbl_title)
        title_layout.addWidget(lbl_sub)
        layout.addLayout(title_layout)

        # Command Bar: Add Button, Open Folder Button, Search Box, Target Mic
        cmd_bar = QHBoxLayout()
        cmd_bar.setSpacing(10)

        self.btn_add = PrimaryPushButton(FluentIcon.ADD, tr("soundboard_btn_add", "Добавить звук"), self)
        self.btn_add.setFixedHeight(34)
        self.btn_add.clicked.connect(self._open_file_dialog)
        cmd_bar.addWidget(self.btn_add)

        self.btn_open_folder = PushButton(FluentIcon.FOLDER, tr("soundboard_btn_open_folder", "Открыть папку"), self)
        self.btn_open_folder.setFixedHeight(34)
        self.btn_open_folder.setToolTip(tr("soundboard_open_folder_title", "Выберите папку со звуками"))
        self.btn_open_folder.clicked.connect(self._open_folder_dialog)
        cmd_bar.addWidget(self.btn_open_folder)

        self.btn_random = PushButton(FluentIcon.ROTATE, tr("soundboard_btn_random", "Случайный звук"), self)
        self.btn_random.setFixedHeight(34)
        self.btn_random.setToolTip(tr("soundboard_btn_random_tooltip", "Воспроизвести случайный звук из выбранной или текущей вкладки"))
        self.btn_random.clicked.connect(lambda: self._play_random_sound())
        cmd_bar.addWidget(self.btn_random)

        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText(tr("soundboard_search_placeholder", "Поиск звука по названию..."))
        self.search_box.setFixedHeight(34)
        self.search_box.textChanged.connect(self._filter_sounds)
        cmd_bar.addWidget(self.search_box, stretch=1)

        # Target Mic Dropdown for Soundboard
        self.combo_target_mic = ComboBox(self)
        self.combo_target_mic.setToolTip(tr("soundboard_target_mic_tooltip", "Целевой микрофон для трансляции звуков саундборда (виртуальный кабель)"))
        self.combo_target_mic.setMinimumWidth(240)
        self.combo_target_mic.setFixedHeight(34)
        self.combo_target_mic.currentIndexChanged.connect(self._on_target_mic_changed)
        cmd_bar.addWidget(self.combo_target_mic)

        layout.addLayout(cmd_bar)

        # Windows 11 Segmented Navigation Bar + Dynamic Category Buttons
        cat_bar = QHBoxLayout()
        cat_bar.setSpacing(6)

        self.seg_categories = SegmentedWidget(self)
        self.seg_categories.currentItemChanged.connect(self._on_category_changed)
        cat_bar.addWidget(self.seg_categories)

        self.btn_add_cat = TransparentToolButton(FluentIcon.ADD, self)
        self.btn_add_cat.setToolTip(tr("soundboard_btn_add_cat_tooltip", "Создать новую категорию / вкладку"))
        self.btn_add_cat.clicked.connect(self._prompt_add_category)
        cat_bar.addWidget(self.btn_add_cat)

        self.btn_del_cat = TransparentToolButton(FluentIcon.DELETE, self)
        self.btn_del_cat.setToolTip(tr("soundboard_btn_del_cat_tooltip", "Удалить выбранную категорию (звуки будут перемещены в SFX)"))
        self.btn_del_cat.clicked.connect(self._prompt_delete_current_category)
        self.btn_del_cat.setVisible(False)
        cat_bar.addWidget(self.btn_del_cat)

        cat_bar.addStretch()
        layout.addLayout(cat_bar)

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
        self.lbl_empty = CaptionLabel(
            tr("soundboard_empty_cat", "В этой категории пока нет звуков.\nНажмите «Добавить звук», «Открыть папку» или отметьте звёздочкой любимые звуки в саундборде."),
            self.card_container
        )
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("color: rgba(255, 255, 255, 0.45); font-size: 13px; padding: 40px 10px;")
        self.lbl_empty.setVisible(False)
        self.card_layout.addWidget(self.lbl_empty)

        self.card_layout.addStretch()

        self.scroll.setWidget(self.card_container)
        layout.addWidget(self.scroll, stretch=1)

        self.refresh_categories(select_id="ALL")

    def refresh_categories(self, select_id: Optional[str] = None):
        target = select_id or self.current_category
        self.seg_categories.blockSignals(True)
        self.seg_categories.clear()

        system_names = {
            "ALL": tr("soundboard_cat_all", "Все"),
            "FAVORITES": tr("soundboard_cat_favorites", "Любимые"),
            "SFX": tr("soundboard_cat_sfx", "SFX"),
            "VOICES": tr("soundboard_cat_voices", "Голоса"),
            "MUSIC": tr("soundboard_cat_music", "Музыка")
        }

        cats = self.cfg.get_categories()
        existing_ids = [c["id"] for c in cats]
        for c in cats:
            cid = c["id"]
            cname = system_names.get(cid.upper(), c["name"])
            self.seg_categories.addItem(cid, cname)
            item = self.seg_categories.items.get(cid)
            if item:
                item.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
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
        is_system = cat_id.upper() in ("ALL", "FAVORITES", "SFX", "VOICES", "MUSIC")
        sound_count = sum(1 for s in self.cfg.sounds if (cat_id.upper() == "ALL" or str(s.get("category", "")).upper() == cat_id.upper()))

        menu = RoundMenu(parent=self)
        menu.addAction(Action(
            FluentIcon.ROTATE,
            tr("soundboard_menu_random_cat", "🎲 Случайный звук из этой вкладки"),
            triggered=lambda: self._play_random_sound(category_id=cat_id)
        ))

        if not is_system:
            menu.addSeparator()
            menu.addAction(Action(
                FluentIcon.EDIT,
                f"{tr('common_rename', 'Переименовать')} «{cat_name}»",
                triggered=lambda: self._prompt_rename_category(cat_id, cat_name)
            ))
            menu.addAction(Action(
                FluentIcon.MOVE,
                f"{tr('common_delete', 'Удалить')} (сохранить звуки во «Все») [{sound_count} шт.]",
                triggered=lambda: self._prompt_delete_category(cat_id, cat_name, delete_sounds=False)
            ))
            menu.addSeparator()
            menu.addAction(Action(
                FluentIcon.DELETE,
                f"{tr('common_delete', 'Удалить')} вместе с содержимым ({sound_count} звуков)",
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
                tr("soundboard_del_cat_with_sounds_title", "Удаление категории с содержимым"),
                tr("soundboard_del_cat_with_sounds_msg", "Вы действительно хотите удалить категорию «{cat}» и ВСЕ входящие в неё звуки ({count} шт.)?").format(cat=cat_name, count=sound_count),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
        else:
            reply = QMessageBox.question(
                self,
                tr("soundboard_del_cat_confirm_title", "Удаление категории"),
                tr("soundboard_del_cat_confirm_msg", "Удалить категорию «{cat}»?\nВсе звуки ({count} шт.) останутся на саундборде во вкладке «Все».").format(cat=cat_name, count=sound_count),
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
            f"{tr('common_delete', 'Удалить')} (сохранить звуки во «Все») [{sound_count} шт.]",
            triggered=lambda: self._prompt_delete_category(self.current_category, cat_name, delete_sounds=False)
        ))
        menu.addAction(Action(
            FluentIcon.DELETE,
            f"{tr('common_delete', 'Удалить')} вместе с содержимым ({sound_count} шт.)",
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
            card.category_change_requested.connect(self._on_sound_category_change)
            card.create_category_requested.connect(self._on_sound_create_category)

            self.cards[s["id"]] = card
            self.card_layout.insertWidget(self.card_layout.count() - 1, card)

        if self.last_selected_sound is None and len(self.cfg.sounds) > 0:
            self.load_sound_to_waveform(self.cfg.sounds[0])

        self._filter_sounds()

    def _on_sound_category_change(self, sound_id: str, target_cat_id: str):
        sound = next((s for s in self.cfg.sounds if s.get("id") == sound_id), None)
        if sound:
            sound["category"] = target_cat_id
            self.cfg.save_sounds()
            self._filter_sounds()

            cats = self.cfg.get_categories()
            cat_obj = next((c for c in cats if c.get("id") == target_cat_id), None)
            cat_name = cat_obj.get("name", target_cat_id) if cat_obj else target_cat_id
            InfoBar.success(
                title=tr("soundboard_menu_move_cat", "Переместить в категорию"),
                content=f"«{sound.get('name', '')}» -> {cat_name}",
                parent=self.window(),
                duration=2500
            )

    def _on_sound_create_category(self, sound_id: str):
        dlg = NewCategoryDialog(parent=self)
        if dlg.exec():
            name = dlg.category_name
            new_cat = self.cfg.add_category(name)
            if new_cat:
                self._on_sound_category_change(sound_id, new_cat["id"])
                self.refresh_categories(select_id=new_cat["id"])
                main_win = self.window()
                if hasattr(main_win, "settings_interface"):
                    main_win.settings_interface._refresh_categories_list()

    def _filter_sounds(self):
        query = self.search_box.text().strip().lower()
        curr_cat = str(self.current_category).upper()
        visible_count = 0

        for s in self.cfg.sounds:
            card = self.cards.get(s["id"])
            if not card:
                continue

            matches_search = (query in s.get("name", "").lower())
            is_fav = bool(s.get("favorite", False))
            sound_cat = str(s.get("category", "")).upper()

            if curr_cat == "ALL":
                matches_cat = True
            elif curr_cat == "FAVORITES":
                matches_cat = is_fav
            else:
                matches_cat = (sound_cat == curr_cat)

            vis = matches_search and matches_cat
            card.setVisible(vis)
            if vis:
                visible_count += 1

        if hasattr(self, "lbl_empty") and self.lbl_empty is not None:
            self.lbl_empty.setVisible(visible_count == 0)

    def _play_random_sound(self, category_id: Optional[str] = None):
        """Picks and plays a random sound from the active or specified category."""
        target_cat = category_id if category_id is not None else self.current_category
        curr_cat = str(target_cat).upper()

        candidates = []
        for s in self.cfg.sounds:
            sound_cat = str(s.get("category", "")).upper()
            is_fav = bool(s.get("favorite", False))
            if curr_cat == "ALL":
                candidates.append(s)
            elif curr_cat == "FAVORITES":
                if is_fav:
                    candidates.append(s)
            else:
                if sound_cat == curr_cat:
                    candidates.append(s)

        if not candidates:
            if curr_cat != "ALL" and self.cfg.sounds:
                candidates = list(self.cfg.sounds)
            else:
                InfoBar.warning(
                    title=tr("soundboard_random_title", "Случайный звук"),
                    content=tr("soundboard_random_empty", "В текущей категории нет доступных звуков."),
                    parent=self.window(),
                    duration=2500
                )
                return

        chosen = random.choice(candidates)
        self.load_sound_to_waveform(chosen)
        self.sound_play_requested.emit(chosen)
        InfoBar.info(
            title=tr("soundboard_random_title", "Случайный звук"),
            content=f"🎲 {chosen.get('name', 'Sound')}",
            parent=self.window(),
            duration=2000
        )

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
            tr("common_delete", "Удаление звука"),
            tr("soundboard_menu_delete", "Вы уверены, что хотите удалить этот звук?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.sound_stop_requested.emit(sound_id)
            self.cfg.remove_sound(sound_id)
            self.refresh_sounds()

    def _open_file_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            tr("soundboard_btn_add", "Выберите аудиофайлы"),
            "",
            "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus);;All (*.*)"
        )
        for f in files:
            self.add_sound_file(f)

    def _open_folder_dialog(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            tr("soundboard_open_folder_title", "Выберите папку со звуками"),
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        if not folder_path:
            return

        folder_name = os.path.basename(os.path.normpath(folder_path))
        if not folder_name:
            folder_name = "Folder"

        valid_exts = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"}
        audio_files = []
        try:
            for root, _, files in os.walk(folder_path):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in valid_exts:
                        audio_files.append(os.path.join(root, f))
        except Exception as e:
            QMessageBox.critical(self, "SoundFlow", f"{tr('soundboard_folder_err', 'Не удалось прочитать папку')}:\n{e}")
            return

        if not audio_files:
            InfoBar.warning(
                title=tr("soundboard_folder_imported_title", "Папка со звуками"),
                content=tr("soundboard_no_audio_files", "В выбранной папке не найдено аудиофайлов (.mp3, .wav, .ogg, .flac)."),
                parent=self.window(),
                duration=3500
            )
            return

        # Insert category immediately after "ALL" (index 1)
        new_cat = self.cfg.add_category(folder_name, position=1)
        cat_id = new_cat["id"] if new_cat else "SFX"

        new_sounds = []
        for file_path in audio_files:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            new_sounds.append({
                "id": f"snd_{os.urandom(4).hex()}",
                "name": base_name.replace("_", " ").title(),
                "path": str(file_path),
                "hotkey": "",
                "volume": 1.0,
                "category": cat_id,
                "color": "#0078d4",
                "favorite": False,
                "speed": 1.0,
                "pitch": 1.0
            })

        self.cfg.batch_add_sounds(new_sounds)
        self.refresh_categories(select_id=cat_id)
        self.refresh_sounds()

        tpl = tr("soundboard_folder_imported_msg", "Импортировано {count} звуков во вкладку «{cat}».")
        InfoBar.success(
            title=tr("soundboard_folder_imported_title", "Папка импортирована"),
            content=tpl.format(count=len(audio_files), cat=folder_name),
            parent=self.window(),
            duration=4000
        )

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
            if fpath.lower().endswith((".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus")):
                self.add_sound_file(fpath)

    def _load_target_devices(self):
        """Loads available audio output devices for target microphone into combo box."""
        saved_target = self.cfg.get("mic_target_device_id")
        self.engine.populate_target_mic_combobox(self.combo_target_mic, saved_target)

    def _on_target_mic_changed(self, index: int):
        dev_id = self.combo_target_mic.itemData(index)
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
