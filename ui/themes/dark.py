"""NAV TOOLS - Dark theme stylesheet (Slate Kinetic from Stitch)."""

DARK_THEME_QSS = """
/* ============================================================
   Global
   ============================================================ */
* {
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 15px;
    color: #dae2fd;
    outline: none;
}

QMainWindow, QWidget, QFrame, QDialog,
QScrollArea, QAbstractScrollArea,
QStackedWidget, QTabWidget {
    background-color: #0b1326;
    border: none;
}

QScrollArea > QWidget > QWidget {
    background-color: #0b1326;
}

QWidget#centralWidget {
    background-color: #0b1326;
}

/* ============================================================
   Sidebar
   ============================================================ */
QWidget#sidebar {
    background-color: #0d1529;
    border-right: 1px solid #1a2240;
}

QLabel#sidebar-logo {
    font-family: "Segoe UI", sans-serif;
    font-size: 10px;
    font-weight: 800;
    color: #8c909f;
    padding: 6px 0 2px 0;
    letter-spacing: 1px;
}

QWidget[class="sidebar-btn"] {
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 6px 4px;
    margin: 1px 2px;
}

QWidget[class="sidebar-btn"]:hover {
    background-color: #171f33;
}

QWidget[class="sidebar-btn"][active="true"] {
    background-color: #1e2d4a;
}

QWidget[class="sidebar-btn"] QLabel {
    background: transparent;
    color: #8c909f;
}

QWidget[class="sidebar-btn"]:hover QLabel {
    color: #dae2fd;
}

QWidget[class="sidebar-btn"][active="true"] QLabel {
    color: #adc6ff;
    font-weight: bold;
}

QLabel#sidebar-version {
    color: #424754;
    font-size: 9px;
}

/* ============================================================
   Config Panel (Left Panel)
   ============================================================ */
QWidget#configPanel {
    background-color: #131b2e;
    border-right: 1px solid #1a2240;
}

QLabel.section-title {
    font-family: "Segoe UI", "Manrope", sans-serif;
    font-size: 20px;
    font-weight: bold;
    color: #dae2fd;
    padding: 4px 0;
}

QLabel.field-label {
    font-size: 14px;
    font-weight: bold;
    color: #c2c6d6;
    padding: 4px 0;
}

QLabel.model-info {
    font-size: 11px;
    color: #8c909f;
    font-style: italic;
}

/* ============================================================
   Form Inputs
   ============================================================ */
QLineEdit, QSpinBox {
    background-color: #131b2e;
    border: 1px solid #2a3350;
    border-radius: 8px;
    padding: 10px 14px;
    color: #dae2fd;
    font-size: 14px;
    selection-background-color: #4d8eff;
    min-height: 22px;
}

QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #4d8eff;
}

QLineEdit:disabled, QSpinBox:disabled {
    background-color: #0e1525;
    color: #424754;
    border-color: #1a2240;
}

QComboBox {
    background-color: #131b2e;
    border: 1px solid #2a3350;
    border-radius: 8px;
    padding: 10px 14px;
    padding-right: 30px;
    color: #dae2fd;
    font-size: 14px;
    min-height: 22px;
}

QComboBox:hover {
    border: 1px solid #4d8eff;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border: none;
    border-left: 1px solid #2a3350;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: transparent;
}

QComboBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #8c909f;
}

QComboBox:hover::down-arrow {
    border-top: 6px solid #adc6ff;
}

QComboBox QAbstractItemView {
    background-color: #222a3d;
    border: 1px solid #2d3449;
    border-radius: 4px;
    selection-background-color: #4d8eff;
    selection-color: #ffffff;
    padding: 4px;
    outline: none;
}

/* ---- SpinBox Arrows ---- */
QSpinBox::up-button, QSpinBox::down-button {
    subcontrol-origin: border;
    width: 24px;
    background: transparent;
    border: none;
}

QSpinBox::up-button {
    subcontrol-position: top right;
    border-top-right-radius: 8px;
    border-bottom: 1px solid #2a3350;
}

QSpinBox::down-button {
    subcontrol-position: bottom right;
    border-bottom-right-radius: 8px;
}

QSpinBox::up-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #8c909f;
}

QSpinBox::down-arrow {
    image: none;
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #8c909f;
}

QSpinBox::up-arrow:hover {
    border-bottom: 5px solid #adc6ff;
}

QSpinBox::down-arrow:hover {
    border-top: 5px solid #adc6ff;
}

/* ============================================================
   TextEdit (Prompt Editor)
   ============================================================ */
QTextEdit, QPlainTextEdit {
    background-color: #131b2e;
    border: 1px solid #2a3350;
    border-radius: 8px;
    padding: 10px 14px;
    color: #dae2fd;
    font-size: 14px;
    selection-background-color: #4d8eff;
}

QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #4d8eff;
}

/* ============================================================
   Generic Buttons
   ============================================================ */
QPushButton {
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    border: none;
}

QPushButton#btn-primary {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #4d8eff, stop:1 #3b82f6);
    color: #ffffff;
    font-weight: bold;
    font-size: 14px;
    padding: 10px 20px;
}

QPushButton#btn-primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6ba1ff, stop:1 #4d8eff);
}

QPushButton#btn-primary:pressed {
    background-color: #2563eb;
}

QPushButton#btn-secondary {
    background-color: #222a3d;
    color: #adc6ff;
    border: 1px solid #2d3449;
}

QPushButton#btn-secondary:hover {
    background-color: #2d3449;
    border: 1px solid #4d8eff;
}

QPushButton#btn-success {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #22c55e, stop:1 #16a34a);
    color: #ffffff;
}

QPushButton#btn-success:hover {
    background-color: #16a34a;
}

QPushButton#btn-warning {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #f97316, stop:1 #ea580c);
    color: #ffffff;
}

QPushButton#btn-danger {
    background-color: #dc2626;
    color: #ffffff;
}

QPushButton#btn-danger:hover {
    background-color: #ef4444;
}

QPushButton#btn-ghost {
    background: transparent;
    color: #8c909f;
    border: 1px solid #2d3449;
}

QPushButton#btn-ghost:hover {
    background-color: #171f33;
    color: #c2c6d6;
}

QPushButton:disabled {
    background-color: #1a2240;
    color: #424754;
}

/* ============================================================
   Action Bar (Bottom Sticky)
   ============================================================ */
QWidget#actionBar {
    background-color: #0d1529;
    border-top: 1px solid #1a2240;
}

/* v2.0.22: action buttons unified outline style */
QPushButton#action-start {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #4d8eff, stop:1 #3b82f6);
    color: #ffffff;
    border: none;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    padding: 4px 14px;
}
QPushButton#action-start:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6ba1ff, stop:1 #4d8eff);
}
QPushButton#action-start:disabled {
    background: #1a2240;
    color: #555e7a;
}

QPushButton#action-pause {
    background-color: transparent;
    color: #fbbf24;
    border: 1px solid rgba(251,191,36,0.4);
    border-radius: 6px;
    font-size: 11px;
    padding: 4px 10px;
}
QPushButton#action-pause:hover {
    background-color: rgba(251,191,36,0.12);
    border-color: #fbbf24;
}
QPushButton#action-pause:disabled {
    color: #475569;
    border-color: #2a3350;
    background-color: transparent;
}

QPushButton#action-stop {
    background-color: transparent;
    color: #f87171;
    border: 1px solid rgba(248,113,113,0.4);
    border-radius: 6px;
    font-size: 11px;
    padding: 4px 10px;
}
QPushButton#action-stop:hover {
    background-color: rgba(248,113,113,0.12);
    border-color: #f87171;
}
QPushButton#action-stop:disabled {
    color: #475569;
    border-color: #2a3350;
    background-color: transparent;
}

QPushButton#action-save {
    background-color: transparent;
    color: #adc6ff;
    border: 1px solid #2d3449;
    border-radius: 6px;
    font-size: 11px;
    padding: 4px 10px;
}
QPushButton#action-save:hover {
    background-color: rgba(77,142,255,0.10);
    color: #dae2fd;
    border-color: #4d8eff;
}

QPushButton#action-resume {
    background-color: transparent;
    color: #38bdf8;
    border: 1px solid rgba(56,189,248,0.4);
    border-radius: 6px;
    font-size: 11px;
    padding: 4px 10px;
}
QPushButton#action-resume:hover {
    background-color: rgba(56,189,248,0.12);
    border-color: #38bdf8;
}
QPushButton#action-resume:disabled {
    color: #475569;
    border-color: #2a3350;
    background-color: transparent;
}

QPushButton#action-manage {
    background-color: transparent;
    color: #adc6ff;
    border: 1px solid #2d3449;
    border-radius: 6px;
    font-size: 11px;
    padding: 4px 10px;
}
QPushButton#action-manage:hover {
    background-color: rgba(77,142,255,0.10);
    color: #dae2fd;
    border-color: #4d8eff;
}

QPushButton#action-retry {
    background-color: transparent;
    color: #f97316;
    border: 1px solid rgba(249,115,22,0.4);
    border-radius: 6px;
    font-size: 11px;
    padding: 4px 10px;
}
QPushButton#action-retry:hover {
    background-color: rgba(249,115,22,0.12);
    border-color: #f97316;
}

QPushButton#action-concat {
    background-color: transparent;
    color: #2dd4bf;
    border: 1px solid rgba(45,212,191,0.4);
    border-radius: 6px;
    font-size: 11px;
    padding: 4px 10px;
}
QPushButton#action-concat:hover {
    background-color: rgba(45,212,191,0.12);
    border-color: #2dd4bf;
}

/* ============================================================
   Table (Task Table)
   ============================================================ */
QTableWidget {
    background-color: #0b1326;
    alternate-background-color: #0d1529;
    border: none;
    gridline-color: #1a2240;
    selection-background-color: #1a2a4a;
    selection-color: #dae2fd;
}

QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #1a2240;
}

QTableWidget::item:selected {
    background-color: #1a2a4a;
}

QHeaderView::section {
    background-color: #131b2e;
    color: #8c909f;
    font-weight: bold;
    font-size: 12px;
    padding: 8px;
    border: none;
    border-bottom: 2px solid #1a2240;
    border-right: 1px solid #1a2240;
}

QHeaderView::section:last {
    border-right: none;
}

/* ============================================================
   Scrollbar
   ============================================================ */
QScrollBar:vertical {
    background: #0b1326;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #2d3449;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #424754;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: #0b1326;
    height: 8px;
}

QScrollBar::handle:horizontal {
    background: #2d3449;
    border-radius: 4px;
    min-width: 30px;
}

/* ============================================================
   Badges / Labels
   ============================================================ */
QLabel.badge-free {
    background-color: #2d3449;
    color: #8c909f;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: bold;
}

QLabel.badge-tier {
    background-color: #1a2a4a;
    color: #4d8eff;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: bold;
}

QLabel.badge-success {
    background-color: #052e16;
    color: #22c55e;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
}

QLabel.badge-error {
    background-color: #450a0a;
    color: #ef4444;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
}

QLabel.badge-pending {
    background-color: #2d3449;
    color: #8c909f;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
}

QLabel.badge-running {
    background-color: #431407;
    color: #f97316;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
}

/* ============================================================
   Tab Widget (Settings Dialog)
   ============================================================ */
QTabWidget::pane {
    background-color: #131b2e;
    border: none;
    border-top: 2px solid #4d8eff;
}

QTabBar::tab {
    background-color: #0b1326;
    color: #8c909f;
    padding: 10px 20px;
    border: none;
    font-weight: 500;
}

QTabBar::tab:selected {
    color: #4d8eff;
    border-bottom: 2px solid #4d8eff;
}

QTabBar::tab:hover {
    color: #adc6ff;
    background-color: #131b2e;
}

/* ============================================================
   Toggle Switch (via QCheckBox)
   ============================================================ */
QCheckBox {
    spacing: 8px;
    color: #dae2fd;
}

QCheckBox::indicator {
    width: 36px;
    height: 20px;
    border-radius: 10px;
    background-color: #2d3449;
    border: none;
}

QCheckBox::indicator:checked {
    background-color: #4d8eff;
}

/* ============================================================
   Dialog
   ============================================================ */
QDialog {
    background-color: #131b2e;
    border: 1px solid #2d3449;
    border-radius: 8px;
}

/* ============================================================
   Tooltip
   ============================================================ */
QToolTip {
    background-color: #2d3449;
    color: #dae2fd;
    border: 1px solid #424754;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ============================================================
   Splitter
   ============================================================ */
QSplitter::handle {
    background-color: #1e2742;
    width: 5px;
    border-radius: 2px;
}

QSplitter::handle:hover {
    background-color: #4d8eff;
}

/* ============================================================
   Log Viewer (Monospace)
   ============================================================ */
QTextEdit#logViewer {
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 12px;
    background-color: #060e20;
    border: 1px solid #1a2240;
    line-height: 1.5;
}
"""
