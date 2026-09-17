"""
Fluent Design Settings Interface for SoundFlow Studio.
Features Windows 11 SettingCardGroup, audio device selectors, and driver maintenance.
"""

from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QMessageBox
)
from qfluentwidgets import (
    SettingCardGroup, CardWidget, PrimaryPushButton, PushButton,
    ComboBox, SwitchButton, TitleLabel, SubtitleLabel, BodyLabel,
    CaptionLabel, FluentIcon, InfoBar, InfoBarPosition, LineEdit,
    RoundMenu, Action
)

from core.audio_engine import AudioEngine
from core.driver_manager import DriverManager
from .fluent_soundboard import RenameCategoryDialog


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
        lbl_title = TitleLabel("Параметры", self)
        lbl_sub = CaptionLabel("Управление аудиоустройствами, задержкой (Latency) и виртуальным драйвером", self)
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

        # 1. Device Group (Soundpad & Voicemod paradigm)
        card_devs = CardWidget(container)
        d_layout = QVBoxLayout(card_devs)
        d_layout.setContentsMargins(20, 18, 20, 18)
        d_layout.setSpacing(14)

        d_title = SubtitleLabel("Маршрутизация аудиоустройств", card_devs)
        d_layout.addWidget(d_title)

        # Monitor (Speakers/Headphones)
        mon_box = QVBoxLayout()
        mon_box.setSpacing(3)
        mon_box.addWidget(BodyLabel("1. Устройство воспроизведения для себя (Динамики / Наушники):", card_devs))
        lbl_mon_desc = CaptionLabel("Куда выводится звук саундборда, радио, YouTube и эффектов лично для вас.", card_devs)
        lbl_mon_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        mon_box.addWidget(lbl_mon_desc)
        self.combo_monitor = ComboBox(card_devs)
        self.combo_monitor.setFixedHeight(34)
        mon_box.addWidget(self.combo_monitor)
        d_layout.addLayout(mon_box)

        # Target Mic (Virtual Cable)
        target_box = QVBoxLayout()
        target_box.setSpacing(3)
        target_box.addWidget(BodyLabel("2. Вывод в микрофон (целевой виртуальный кабель, CABLE Input):", card_devs))
        lbl_target_desc = CaptionLabel("Направляет саундборд, радио и ваш голос в виртуальный кабель для Discord, игр и стримов.", card_devs)
        lbl_target_desc.setStyleSheet("color: rgba(255, 255, 255, 0.55);")
        target_box.addWidget(lbl_target_desc)
        self.combo_target_mic = ComboBox(card_devs)
        self.combo_target_mic.setFixedHeight(34)
        target_box.addWidget(self.combo_target_mic)
        d_layout.addLayout(target_box)

        # Mic in (Physical Microphone)
        mic_box = QVBoxLayout()
        mic_box.setSpacing(3)
        mic_box.addWidget(BodyLabel("3. Реальный физический микрофон (Вход):", card_devs))
        lbl_mic_desc = CaptionLabel("Ваш физический микрофон для разговора и наложения эффектов изменения голоса (Voice FX).", card_devs)
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

        lbl_g_title = CaptionLabel("Схема работы аудио как в Soundpad и Voicemod:", guide_box)
        lbl_g_title.setStyleSheet("font-weight: 700; color: #00f2fe;")
        g_layout.addWidget(lbl_g_title)

        lbl_g_text = CaptionLabel(
            "• В Discord, Telegram, OBS и играх (CS2, Dota 2) выберите 'CABLE Output' как входной микрофон.\n"
            "• В SoundFlow выберите ваш реальный микрофон и наушники/динамики.\n"
            "• Ваши собеседники услышат идеальный звук саундборда и ваш голос без эха!",
            guide_box
        )
        lbl_g_text.setStyleSheet("color: rgba(255, 255, 255, 0.8); line-height: 140%;")
        g_layout.addWidget(lbl_g_text)

        d_layout.addWidget(guide_box)

        c_layout.addWidget(card_devs)

        # 2. Driver Management Card
        card_drv = CardWidget(container)
        drv_layout = QVBoxLayout(card_drv)
        drv_layout.setContentsMargins(20, 18, 20, 18)
        drv_layout.setSpacing(12)

        drv_title = SubtitleLabel("Виртуальный аудиодрайвер", card_drv)
        drv_layout.addWidget(drv_title)

        self.lbl_drv_status = BodyLabel("Статус: Проверка...", card_drv)
        drv_layout.addWidget(self.lbl_drv_status)

        drv_btns = QHBoxLayout()
        drv_btns.setSpacing(10)

        self.btn_install_drv = PrimaryPushButton(FluentIcon.DOWNLOAD, "Установить официальный драйвер (VB-Cable)", card_drv)
        self.btn_install_drv.setFixedHeight(36)
        self.btn_install_drv.clicked.connect(self._install_driver)
        drv_btns.addWidget(self.btn_install_drv)

        self.btn_open_folder = PushButton(FluentIcon.FOLDER, "Открыть папку драйвера", card_drv)
        self.btn_open_folder.setFixedHeight(36)
        self.btn_open_folder.clicked.connect(DriverManager.open_driver_folder)
        drv_btns.addWidget(self.btn_open_folder)

        drv_layout.addLayout(drv_btns)
        c_layout.addWidget(card_drv)

        # 3. Buffer & Latency Card
        card_buf = CardWidget(container)
        b_layout = QVBoxLayout(card_buf)
        b_layout.setContentsMargins(20, 18, 20, 18)
        b_layout.setSpacing(12)

        b_title = SubtitleLabel("Буферизация и задержка", card_buf)
        b_layout.addWidget(b_title)

        buf_row = QHBoxLayout()
        buf_row.addWidget(BodyLabel("Размер буфера (задержка звука):", card_buf))
        self.combo_buf = ComboBox(card_buf)
        self.combo_buf.addItem("512 сэмплов (~10 мс - ультранизкая задержка)", userData=512)
        self.combo_buf.addItem("1024 сэмпла (~21 мс - стабильно, рекомендуемо)", userData=1024)
        self.combo_buf.addItem("2048 сэмплов (~42 мс - без щелчков на слабых ПК)", userData=2048)
        buf_row.addWidget(self.combo_buf, stretch=1)
        b_layout.addLayout(buf_row)

        rep_row = QHBoxLayout()
        rep_row.addWidget(BodyLabel("Длительность буфера моментального клипа:", card_buf))
        self.combo_rep = ComboBox(card_buf)
        self.combo_rep.addItem("15 секунд", userData=15)
        self.combo_rep.addItem("30 секунд (по умолчанию)", userData=30)
        self.combo_rep.addItem("60 секунд", userData=60)
        rep_row.addWidget(self.combo_rep, stretch=1)
        b_layout.addLayout(rep_row)

        # Tray switch
        tray_row = QHBoxLayout()
        tray_col = QVBoxLayout()
        tray_col.addWidget(BodyLabel("Сворачивать в системный трей при закрытии", card_buf))
        tray_col.addWidget(CaptionLabel("Приложение и горячие клавиши продолжат работать в фоне во время игр", card_buf))
        tray_row.addLayout(tray_col, stretch=1)

        self.switch_tray = SwitchButton(card_buf)
        self.switch_tray.setChecked(bool(self.cfg.get("minimize_to_tray", True)))
        tray_row.addWidget(self.switch_tray)
        b_layout.addLayout(tray_row)

        c_layout.addWidget(card_buf)

        # 4. Category Management Card
        card_cats = CardWidget(container)
        cat_card_layout = QVBoxLayout(card_cats)
        cat_card_layout.setContentsMargins(20, 18, 20, 18)
        cat_card_layout.setSpacing(12)

        cat_title = SubtitleLabel("Управление вкладками и категориями саундборда", card_cats)
        cat_card_layout.addWidget(cat_title)

        cat_desc = CaptionLabel("Создавайте собственные вкладки для удобной сортировки звуков и эффектов", card_cats)
        cat_desc.setStyleSheet("color: rgba(255, 255, 255, 0.6);")
        cat_card_layout.addWidget(cat_desc)

        # Category addition row
        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        self.edit_new_cat = LineEdit(card_cats)
        self.edit_new_cat.setPlaceholderText("Название новой категории...")
        self.edit_new_cat.setFixedHeight(34)
        add_row.addWidget(self.edit_new_cat, stretch=1)

        self.btn_add_cat = PrimaryPushButton(FluentIcon.ADD, "Добавить", card_cats)
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
        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, "Применить настройки", container)
        self.btn_save.setFixedHeight(38)
        self.btn_save.clicked.connect(self._save_settings)
        btn_row.addWidget(self.btn_save)
        c_layout.addLayout(btn_row)

        c_layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, stretch=1)

        self._update_drv_status()
        self._refresh_categories_list()

    def _update_drv_status(self):
        installed = DriverManager.is_driver_installed()
        if installed:
            self.lbl_drv_status.setText("Статус: Аудиодрайвер установлен и готов к передаче в Discord / игры.")
            self.btn_install_drv.setText("Переустановить драйвер")
        else:
            self.lbl_drv_status.setText("Статус: Драйвер не найден. Звук в микрофон собеседникам не идет.")
            self.btn_install_drv.setText("Установить официальный драйвер (VB-Cable)")

    def _load_devices(self):
        devices = AudioEngine.get_audio_devices()

        self.combo_monitor.clear()
        for d in devices["outputs"]:
            self.combo_monitor.addItem(d["name"], userData=d["id"])

        self.combo_target_mic.clear()
        self.combo_target_mic.addItem("-- Не использовать отдельный виртуальный микрофон --", userData=None)
        cable_wasapi_idx = None
        cable_any_idx = None

        for d in devices["outputs"]:
            idx = self.combo_target_mic.count()
            self.combo_target_mic.addItem(d["name"], userData=d["id"])
            name_lower = d["name"].lower()
            api_lower = d.get("hostapi", "").lower()
            if "cable input" in name_lower and "16ch" not in name_lower:
                if "wasapi" in api_lower and cable_wasapi_idx is None:
                    cable_wasapi_idx = idx
                elif cable_any_idx is None:
                    cable_any_idx = idx
            elif "cable input" in name_lower or "vb-audio" in name_lower or "virtual" in name_lower:
                if cable_any_idx is None:
                    cable_any_idx = idx

        self.combo_mic_in.clear()
        self.combo_mic_in.addItem("-- Без физического микрофона --", userData=None)
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

        # Select saved mic target
        saved_mic_target = self.cfg.get("mic_target_device_id")
        selected_target_idx = 0
        if saved_mic_target is not None:
            # Check if saved target is 16ch
            tgt_name = ""
            for i in range(self.combo_target_mic.count()):
                if self.combo_target_mic.itemData(i) == saved_mic_target:
                    tgt_name = self.combo_target_mic.itemText(i).lower()
                    if "16ch" not in tgt_name:
                        selected_target_idx = i
                    break

        # If no target saved or was 16ch, auto-select standard virtual cable
        if selected_target_idx == 0:
            best_idx = cable_wasapi_idx if cable_wasapi_idx is not None else cable_any_idx
            if best_idx is not None:
                selected_target_idx = best_idx
                self.cfg.set("mic_target_device_id", self.combo_target_mic.itemData(selected_target_idx))

        self.combo_target_mic.setCurrentIndex(selected_target_idx)

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

        self.engine.buffer_size = buf
        self.engine.instant_replay.set_duration(rep)
        self.engine.initialize_streams(
            monitor_device=mon,
            mic_target_device=target,
            mic_input_device=mic_in
        )

        InfoBar.success(
            title="Настройки сохранены",
            content="Параметры аудиоустройств успешно применены.",
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self
        )

    def _install_driver(self):
        success = DriverManager.launch_installer()
        if success:
            QMessageBox.information(
                self,
                "Установщик запущен",
                "Запущен официальный инсталлятор драйвера VB-Audio Cable.\n\n"
                "1. Нажмите 'Install Driver' в окне инсталлятора.\n"
                "2. Подтвердите права администратора Windows.\n"
                "3. После завершения перезапустите SoundFlow или нажмите 'Применить настройки'."
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
                badge = CaptionLabel("Системная вкладка", row)
                badge.setStyleSheet("color: rgba(255, 255, 255, 0.45); font-style: italic;")
                r_layout.addWidget(badge)
            else:
                btn_rename = PushButton(FluentIcon.EDIT, "Переименовать", row)
                btn_rename.setFixedHeight(28)
                btn_rename.clicked.connect(lambda chk, cid=cat["id"], cn=cat["name"]: self._rename_category_from_settings(cid, cn))
                r_layout.addWidget(btn_rename)

                btn_del = PushButton(FluentIcon.DELETE, "Удалить...", row)
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
            f"Сохранить звуки во «Все» [{sound_count} шт.]",
            triggered=lambda: self._delete_category_from_settings(cat_id, delete_sounds=False)
        ))
        menu.addAction(Action(
            FluentIcon.DELETE,
            f"Удалить вместе с содержимым ({sound_count} шт.)",
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
                "Удаление категории с содержимым",
                f"Удалить категорию «{name}» и ВСЕ звуки в ней ({sound_count} шт.)?\n\nЗвуки будут безвозвратно удалены из саундборда!",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
        else:
            reply = QMessageBox.question(
                self,
                "Удаление категории",
                f"Удалить категорию «{name}»?\n\nВсе звуки ({sound_count} шт.) сохранятся и останутся доступны во вкладке «Все» (перенесены в SFX).",
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
