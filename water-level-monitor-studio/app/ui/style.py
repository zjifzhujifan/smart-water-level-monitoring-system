APP_QSS = """
QMainWindow, QDialog {
    background: #101622;
    color: #e8edf7;
    font-family: "PingFang SC", "Microsoft YaHei", Arial;
    font-size: 13px;
}
QWidget {
    color: #e8edf7;
}
QDialog#LoginDialog {
    background: #0b1827;
}
QFrame#LoginShell {
    background: #0b1827;
    border: 1px solid #24344b;
    border-radius: 10px;
}
QFrame#LoginIntro {
    background: transparent;
}
QLabel#LoginTitle {
    color: #f1f6ff;
    font-size: 24px;
    font-weight: 800;
}
QLabel#LoginSubTitle {
    color: #9badc6;
    font-size: 14px;
    font-weight: 600;
}
QLabel#LoginHint {
    color: #6f829d;
    font-size: 11px;
    line-height: 18px;
}
QFrame#LoginForm, QFrame#LoginRight, QFrame#RoleRow {
    background: transparent;
    border: none;
}
QLineEdit#LoginField {
    font-size: 14px;
    font-weight: 600;
    padding: 0 12px;
}
QPushButton#RoleButton {
    background: #0f1a2b;
    border: 1px solid #2d4768;
    border-radius: 8px;
    padding: 0 10px;
    color: #aebbd0;
    font-size: 13px;
    font-weight: 700;
}
QPushButton#RoleButton:hover {
    background: #14243a;
}
QPushButton#RoleButton:checked {
    background: #173455;
    border-color: #37d5ff;
    color: #ffffff;
}
QCheckBox#LoginCheck {
    color: #e8edf7;
    font-size: 13px;
    font-weight: 700;
    spacing: 10px;
}
QCheckBox#LoginCheck::indicator {
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1px solid #355273;
    background: #0f1a2b;
}
QCheckBox#LoginCheck::indicator:checked {
    background: #1f7aec;
    border-color: #37d5ff;
}
QFrame#Panel, QGroupBox {
    background: #151d2c;
    border: 1px solid #263247;
    border-radius: 8px;
}
QFrame#Sidebar {
    background: #080f1b;
    border-right: 1px solid #263247;
}
QFrame#BrandPanel {
    background: #0d1727;
    border: 1px solid #20304a;
    border-radius: 8px;
}
QLabel#BrandBadge {
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
    border-radius: 8px;
    background: #10243a;
    border: 1px solid #2c5876;
    color: #37d5ff;
    font-size: 14px;
    font-weight: 800;
}
QLabel#BrandTitle {
    color: #f4f7fb;
    font-size: 16px;
    font-weight: 800;
}
QLabel#BrandSubTitle {
    color: #7f90aa;
    font-size: 11px;
}
QLabel#Title {
    font-size: 22px;
    font-weight: 700;
}
QLabel#SubTitle {
    color: #8fa0bc;
}
QLabel#SidebarMeta {
    color: #9badc6;
    font-size: 12px;
    font-weight: 600;
}
QPushButton {
    background: #23314a;
    border: 1px solid #31425f;
    border-radius: 7px;
    padding: 8px 12px;
    color: #e8edf7;
}
QPushButton:hover {
    background: #2b3d5d;
}
QPushButton:pressed {
    background: #1d2a40;
}
QPushButton#Primary {
    background: #1f7aec;
    border-color: #1f7aec;
}
QPushButton#Danger {
    background: #b23850;
    border-color: #b23850;
}
QPushButton#NavButton {
    text-align: left;
    padding: 0 14px 0 13px;
    border: 1px solid transparent;
    border-left: 3px solid transparent;
    border-radius: 8px;
    background: transparent;
    color: #aebbd0;
    font-size: 14px;
    font-weight: 600;
}
QPushButton#NavButton:hover {
    background: #111c2d;
    border-color: #24354f;
    border-left-color: #24354f;
}
QPushButton#NavButton:checked {
    background: #162640;
    color: #ffffff;
    border-color: #2a405f;
    border-left-color: #37d5ff;
}
QPushButton#NavButton:disabled {
    color: #4f5d72;
    background: transparent;
    border-color: transparent;
}
QPushButton#SidebarExit {
    text-align: left;
    padding: 0 14px 0 13px;
    border: 1px solid #2b3445;
    border-radius: 8px;
    background: #111827;
    color: #aebbd0;
    font-size: 13px;
    font-weight: 700;
}
QPushButton#SidebarExit:hover {
    background: #251923;
    border-color: #7b3243;
    color: #ffd6de;
}
QScrollArea#NavScroll, QWidget#NavBody {
    background: transparent;
    border: none;
}
QFrame#SidebarStatus {
    background: #0d1727;
    border: 1px solid #20304a;
    border-radius: 8px;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QTextEdit {
    background: #0f1624;
    border: 1px solid #2d3d58;
    border-radius: 6px;
    padding: 7px;
    color: #e8edf7;
}
QComboBox {
    min-height: 20px;
}
QComboBox::drop-down {
    width: 30px;
    border-left: 1px solid #2d3d58;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background: #101a2b;
}
QTableWidget {
    background: #111827;
    alternate-background-color: #151f31;
    color: #dce6f8;
    border: 1px solid #263247;
    gridline-color: #22314a;
    selection-background-color: #234166;
    selection-color: #ffffff;
}
QTableWidget::viewport, QTableView::viewport {
    background: #111827;
}
QTableWidget::item {
    padding: 5px;
}
QTableWidget::item:selected {
    background: #234166;
    color: #ffffff;
}
QHeaderView::section {
    background: #1b2638;
    color: #dce6f8;
    border: 1px solid #263247;
    padding: 7px;
}
QHeaderView {
    background: #1b2638;
}
QTableCornerButton::section {
    background: #1b2638;
    border: 1px solid #263247;
}
QAbstractScrollArea::corner {
    background: #111827;
}
QComboBox QAbstractItemView {
    background: #111827;
    color: #e8edf7;
    selection-background-color: #234166;
    border: 1px solid #2d3d58;
    outline: 0;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    min-height: 36px;
    height: 36px;
    padding: 4px 10px;
}
QTabWidget::pane {
    border: 1px solid #263247;
}
QScrollBar:vertical {
    background: #111827;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: #31425f;
    border-radius: 5px;
}
QScrollBar:horizontal {
    background: #111827;
    height: 10px;
}
QScrollBar::handle:horizontal {
    background: #31425f;
    border-radius: 5px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
    border: none;
    background: transparent;
}
"""
