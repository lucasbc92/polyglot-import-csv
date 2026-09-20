"""Qt stylesheet built from the prototype's colour tokens."""

from __future__ import annotations

STYLESHEET = """
QWidget { background-color: #EEF1F5; color: #1A2330; font-size: 12px; }
QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #D9DFE7;
    border-radius: 8px;
    margin-top: 14px;
    padding: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    color: #5C6675;
    font-weight: 600;
}
/* M1: the QWidget rule above also paints every QLabel/QCheckBox/QRadioButton
   nested inside a card, so without this the native render shows grey
   rectangles behind labels and grey bars where the (often empty) error
   labels sit, and the card stops reading as a card. */
QGroupBox QLabel, QGroupBox QCheckBox, QGroupBox QRadioButton {
    background: transparent;
}
QLineEdit, QComboBox, QTableWidget {
    background-color: #FFFFFF;
    border: 1px solid #D9DFE7;
    border-radius: 6px;
    padding: 5px 8px;
}
QPushButton {
    background-color: #F7F9FC;
    border: 1px solid #B9C2CE;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #E4EDFC; }
QPushButton:disabled { color: #9AA4B2; }
QPushButton#runButton {
    background-color: #2F6FE0;
    border-color: #2F6FE0;
    color: #FFFFFF;
    font-weight: 600;
}
QPushButton#runButton[running="true"] {
    background-color: #D23A31;
    border-color: #D23A31;
}
QLabel#hintLabel { color: #5C6675; }
QLabel#errorLabel { color: #D23A31; }
QLabel#badgeLabel {
    color: #78839A;
    border: 1px solid rgba(120, 131, 154, 120);
    border-radius: 4px;
    padding: 2px 8px;
}
QFrame#consolePanel { background-color: #161A21; border-radius: 8px; }
QFrame#consolePanel QLabel { color: #D6DCE5; background: transparent; }
QFrame#consolePanel QPushButton {
    background-color: #1E242D;
    border-color: #4A5261;
    color: #D6DCE5;
}
QFrame#consolePanel QPushButton#runButton {
    background-color: #2F6FE0;
    border-color: #2F6FE0;
    color: #FFFFFF;
}
QPlainTextEdit#commandEdit {
    background-color: #1E242D;
    border: none;
    color: #D6DCE5;
    padding: 8px;
}
QTextEdit#logView {
    background-color: #161A21;
    border: none;
    color: #D6DCE5;
    padding: 8px;
}
"""
