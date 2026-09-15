"""
Driver Notification and Installation Banner for SoundFlow Studio.
Displays warnings when virtual audio cable is missing and provides 1-click installation.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox
)

from core.driver_manager import DriverManager


class DriverBanner(QFrame):
    """Notification banner warning about missing driver or confirming driver status."""

    driver_status_changed = pyqtSignal(bool)  # is_installed

    def __init__(self, audio_engine, config_manager, parent=None):
        super().__init__(parent)
        self.engine = audio_engine
        self.cfg = config_manager
        self.is_installed = False

        self._build_ui()
        self.check_driver_status(show_alert_on_success=False)

    def _build_ui(self):
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(14, 10, 14, 10)
        self.layout.setSpacing(12)

        # Icon and text layout
        self.icon_label = QLabel("⚠️")
        self.icon_label.setStyleSheet("font-size: 20px;")
        self.layout.addWidget(self.icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self.lbl_title = QLabel("ВИРТУАЛЬНЫЙ АУДИОДРАЙВЕР НЕ УСТАНОВЛЕН")
        self.lbl_title.setStyleSheet("font-weight: 800; font-size: 12px; color: #f59e0b;")
        text_col.addWidget(self.lbl_title)

        self.lbl_desc = QLabel(
            "Без драйвера передача звука в микрофон (Discord, Telegram, игры) работать не будет. "
            "Вы можете тестировать любые кнопки и слушать звук локально (динамики / наушники), но тиммейты вас не услышат."
        )
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        text_col.addWidget(self.lbl_desc)

        self.layout.addLayout(text_col, stretch=1)

        # Action Buttons
        self.btn_install = QPushButton("⬇️ Установить драйвер в 1 клик")
        self.btn_install.setObjectName("AccentButton")
        self.btn_install.setFixedHeight(34)
        self.btn_install.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f59e0b, stop:1 #d97706);
                color: #0b0f19;
                border: none;
                border-radius: 8px;
                font-weight: 800;
                font-size: 12px;
                padding: 0 14px;
            }
            QPushButton:hover {
                background: #b45309;
            }
        """)
        self.btn_install.clicked.connect(self._on_install_clicked)
        self.layout.addWidget(self.btn_install)

        self.btn_refresh = QPushButton("🔄 Проверить снова")
        self.btn_refresh.setFixedHeight(34)
        self.btn_refresh.setStyleSheet("font-size: 11px; padding: 0 10px;")
        self.btn_refresh.clicked.connect(lambda: self.check_driver_status(show_alert_on_success=True))
        self.layout.addWidget(self.btn_refresh)

    def check_driver_status(self, show_alert_on_success: bool = False):
        """Scans system for virtual audio cable."""
        installed = DriverManager.is_driver_installed()
        self.is_installed = installed

        if installed:
            cable_id = DriverManager.get_cable_device_id()
            if cable_id is not None:
                # Auto-bind in config and engine if not already set
                if self.cfg.get("mic_target_device_id") is None:
                    self.cfg.set("mic_target_device_id", cable_id)
                    self.engine.mic_target_device_id = cable_id
                    self.engine.initialize_streams(
                        monitor_device=self.cfg.get("monitor_device_id"),
                        mic_target_device=cable_id,
                        mic_input_device=self.cfg.get("mic_input_device_id")
                    )

            self.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #064e3b, stop:1 #022c22);
                    border: 1px solid #10b981;
                    border-radius: 10px;
                }
            """)
            self.icon_label.setText("🟢")
            self.lbl_title.setText("ВИРТУАЛЬНЫЙ АУДИОДРАЙВЕР УСТАНОВЛЕН И АКТИВЕН")
            self.lbl_title.setStyleSheet("font-weight: 800; font-size: 12px; color: #34d399;")
            self.lbl_desc.setText(
                "Устройство CABLE Input готово к работе! В Discord, Telegram и играх выберите 'CABLE Output' как микрофон."
            )
            self.btn_install.setVisible(False)
            self.btn_refresh.setText("Настройки звука")
            try:
                self.btn_refresh.clicked.disconnect()
            except Exception:
                pass
            self.btn_refresh.clicked.connect(lambda: self.window()._open_settings() if hasattr(self.window(), "_open_settings") else None)

            if show_alert_on_success:
                QMessageBox.information(
                    self,
                    "Драйвер обнаружен!",
                    "Виртуальный кабель VB-Audio Cable успешно обнаружен и подключен!\n"
                    "Теперь весь звук саундборда, стрима из приложений и радио транслируется в ваш микрофон."
                )
        else:
            self.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #451a03, stop:1 #1c1917);
                    border: 1px solid #f59e0b;
                    border-radius: 10px;
                }
            """)
            self.icon_label.setText("⚠️")
            self.lbl_title.setText("ВИРТУАЛЬНЫЙ АУДИОДРАЙВЕР НЕ УСТАНОВЛЕН")
            self.lbl_title.setStyleSheet("font-weight: 800; font-size: 12px; color: #f59e0b;")
            self.lbl_desc.setText(
                "Без драйвера передача звука в микрофон (Discord, Telegram, игры) работать не будет. "
                "Вы можете тестировать любые кнопки и слушать звук локально (динамики / наушники), но тиммейты вас не услышат."
            )
            self.btn_install.setVisible(True)
            self.btn_refresh.setText("🔄 Проверить снова")
            try:
                self.btn_refresh.clicked.disconnect()
            except Exception:
                pass
            self.btn_refresh.clicked.connect(lambda: self.check_driver_status(show_alert_on_success=True))

            if show_alert_on_success:
                QMessageBox.warning(
                    self,
                    "Драйвер пока не найден",
                    "Виртуальный аудиодрайвер не обнаружен.\n\n"
                    "Если вы только что установили его через установщик, Windows может потребоваться перезагрузка ПК для инициализации новых аудиоустройств."
                )

        self.driver_status_changed.emit(installed)

    def _on_install_clicked(self):
        success = DriverManager.launch_installer()
        if success:
            QMessageBox.information(
                self,
                "Запущен установщик драйвера",
                "Запущен официальный установщик драйвера VB-Audio Virtual Cable.\n\n"
                "1. В открывшемся окне нажмите 'Install Driver'.\n"
                "2. Подтвердите права администратора Windows.\n"
                "3. После завершения установки нажмите 'Проверить снова' в SoundFlow (в некоторых случаях Windows требует перезагрузку ПК)."
            )
        else:
            # Fallback if admin launch fails
            DriverManager.open_driver_folder()
            QMessageBox.information(
                self,
                "Установка драйвера",
                "Открыта папка с файлами драйвера.\nПожалуйста, запустите файл 'VBCABLE_Setup_x64.exe' от имени Администратора."
            )
