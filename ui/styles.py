"""
Modern Dark Glassmorphic QSS Stylesheet for SoundFlow Studio.
Features deep space tones, vibrant neon cyan and violet accents, smooth rounded corners,
and clean modern typography.
"""

MAIN_STYLE = """
/* Global Window and Base Styles */
QMainWindow, QDialog, QWidget {
    background-color: #0b0f19;
    color: #f1f5f9;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #0f172a;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #334155;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #00f2fe;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Tab Widget Styling */
QTabWidget::pane {
    border: 1px solid #1e293b;
    border-radius: 12px;
    background-color: #0f172a;
    top: -1px;
}

QTabBar::tab {
    background: #0b0f19;
    color: #94a3b8;
    padding: 10px 22px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    font-size: 13px;
    border: 1px solid transparent;
}

QTabBar::tab:hover {
    color: #e2e8f0;
    background: #1e293b;
}

QTabBar::tab:selected {
    color: #00f2fe;
    background: #0f172a;
    border: 1px solid #1e293b;
    border-bottom: 2px solid #00f2fe;
}

/* Group Boxes & Containers */
QGroupBox {
    background-color: #131d31;
    border: 1px solid #1e293b;
    border-radius: 10px;
    margin-top: 24px;
    padding: 16px;
    font-weight: 600;
    font-size: 13px;
    color: #38bdf8;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
}

/* Buttons */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e293b, stop:1 #334155);
    color: #f8fafc;
    border: 1px solid #475569;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 13px;
}

QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #334155, stop:1 #475569);
    border-color: #38bdf8;
}

QPushButton:pressed {
    background: #0284c7;
    border-color: #0284c7;
}

QPushButton:disabled {
    background: #1e293b;
    color: #64748b;
    border-color: #334155;
}

/* Accent Buttons (Cyan Glowing) */
QPushButton#AccentButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:1 #4facfe);
    color: #0b0f19;
    border: none;
    font-weight: 700;
}
QPushButton#AccentButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38bdf8, stop:1 #0284c7);
}

/* Danger / Panic Button (Red) */
QPushButton#DangerButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #ef4444, stop:1 #dc2626);
    color: #ffffff;
    border: none;
    font-weight: 700;
}
QPushButton#DangerButton:hover {
    background: #b91c1c;
}

/* Line Edits & Search Boxes */
QLineEdit {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}
QLineEdit:focus {
    border: 1px solid #00f2fe;
    background-color: #0f172a;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 6px;
    background: #1e293b;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:1 #8a2be2);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #ffffff;
    width: 16px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 8px;
    border: 2px solid #00f2fe;
}
QSlider::handle:horizontal:hover {
    background: #00f2fe;
}

/* Combo Boxes */
QComboBox {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 24px;
}
QComboBox:hover {
    border-color: #38bdf8;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: none;
}
QComboBox QAbstractItemView {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #334155;
    selection-background-color: #1e293b;
    selection-color: #00f2fe;
}

/* Tooltips */
QToolTip {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
}
"""
