"""NAV TOOLS - Light theme stylesheet."""

LIGHT_THEME_QSS = """
* { font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; color: #212121; outline: none; }
QMainWindow, QWidget, QFrame, QDialog, QScrollArea, QAbstractScrollArea, QStackedWidget, QTabWidget {
    background-color: #ffffff; border: none;
}
QWidget#sidebar { background-color: #fafafa; border-right: 1px solid #e0e0e0; }
QLabel#sidebar-logo { color: #616161; font-weight: 800; padding: 6px 0 2px 0; }
QLabel#sidebar-version { color: #9e9e9e; font-size: 9px; }
QWidget[class="sidebar-btn"] { background: transparent; border-radius: 10px; }
QWidget[class="sidebar-btn"]:hover { background-color: #e8e8e8; }
QWidget[class="sidebar-btn"][active="true"] { background-color: #e3f2fd; }
QWidget[class="sidebar-btn"] QLabel { background: transparent; color: #616161; }
QWidget[class="sidebar-btn"][active="true"] QLabel { color: #0288d1; font-weight: bold; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
    background-color: #f5f5f5; border: 1px solid #e0e0e0; border-radius: 6px; padding: 6px 10px;
}
QPushButton { background-color: #0288d1; color: #ffffff; border: none; border-radius: 6px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background-color: #0277bd; }
QPushButton:disabled { background-color: #e0e0e0; color: #9e9e9e; }
QTableWidget { background-color: #ffffff; alternate-background-color: #f5f5f5; gridline-color: #eeeeee; selection-background-color: #e3f2fd; }
QHeaderView::section { background-color: #ffffff; color: #212121; padding: 10px 8px; border-bottom: 1px solid #e0e0e0; }
QWidget#actionBar { background-color: #fafafa; border-top: 1px solid #e0e0e0; }
"""
