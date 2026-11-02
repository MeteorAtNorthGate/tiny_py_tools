STYLE = """
QMainWindow, QDialog { background: #f5f7fb; }
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 12px; color: #26344b; }
QMenuBar { background: #ffffff; padding: 3px 10px; border-bottom: 1px solid #e6eaf0; }
QMenuBar::item { padding: 5px 10px; }
QMenu { background: #ffffff; border: 1px solid #dae1eb; padding: 5px; }
QMenu::item { padding: 8px 26px; border-radius: 4px; }
QMenu::item:selected { background: #eaf0ff; }
QToolBar { background: #ffffff; border: none; border-bottom: 1px solid #e2e7ef; padding: 6px 12px; spacing: 6px; }
QToolButton { border: none; border-radius: 5px; padding: 6px 10px; }
QToolButton:hover { background: #edf2fc; }
QPushButton { background: #ffffff; border: 1px solid #dce3ee; border-radius: 6px; padding: 7px 13px; }
QPushButton:hover { background: #edf2ff; border-color: #a4bced; }
QPushButton:pressed, QPushButton:checked { background: #e3ecff; border-color: #628bea; color: #315fc6; }
QPushButton:disabled { color: #a7b0be; background: #f4f6f9; border-color: #e4e8ef; }
QPushButton#primary { background: #416fe8; border-color: #416fe8; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #345fce; }
QWidget#header { background: white; border-bottom: 1px solid #e2e7ef; }
QWidget#sidebar, QWidget#inspector { background: #f8fafe; }
QWidget#annotationBar { background: #f8fafe; }
QLabel#brand { color: #416fe8; font-size: 17px; font-weight: 800; }
QLabel#section { color: #758299; font-size: 11px; font-weight: 600; padding-top: 12px; padding-bottom: 5px; }
QLabel#propertyGroup { color: #64758f; font-size: 11px; font-weight: 600; padding-top: 10px; padding-bottom: 2px; }
QLabel#muted { color: #8490a3; font-size: 11px; padding: 5px 0; }
QLabel#saved { color: #7a899f; font-size: 11px; }
QLabel#inputUnit { color: #91a0b5; background: transparent; font-size: 11px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit { background: white; border: 1px solid #dce3ee; border-radius: 5px; padding: 6px; selection-background-color: #6a8ee8; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #628bea; }
QComboBox#inspectorCombo { padding-right: 26px; }
QComboBox#inspectorCombo::drop-down { border: none; width: 26px; }
QComboBox#inspectorCombo::down-arrow { image: none; border: none; }
QLineEdit#documentTitle { border: 1px solid transparent; font-size: 15px; font-weight: 600; background: transparent; }
QLineEdit#documentTitle:focus { border-color: #9bb6f2; background: #f8faff; }
QListWidget { background: transparent; border: none; outline: none; padding: 5px; }
QListWidget::item { border: 1px solid transparent; border-radius: 7px; padding: 10px 3px; margin: 4px; color: #76859d; }
QListWidget::item:selected { background: #e8efff; border-color: #a4bcf1; color: #365fc5; }
QListWidget::item:hover { background: #eef2f8; }
QScrollArea { border: none; background: #f8fafe; }
QScrollBar:vertical { background: #e9edf3; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #bac6d7; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QStatusBar { background: #ffffff; border-top: 1px solid #e1e7ef; color: #78869a; }
QSplitter::handle { background: #e0e6ef; width: 1px; }
QToolTip { background: #1f2d45; color: #ffffff; border: none; padding: 6px; }
"""

ANNOTATION_STYLE = """
QDialog#annotationWindow { background: #ffffff; }
QWidget#annotationToolbar { background: #fcfdff; border-top: 1px solid #e1e6ee; }
QToolButton#annotationTool { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 0; color: #536176; }
QToolButton#annotationTool:hover { background: #edf2fa; }
QToolButton#annotationTool:pressed { background: #dfe9fb; }
QToolButton#annotationTool:checked { background: #e8efff; border-color: #cbdafa; color: #3168df; }
QToolButton#annotationTool:disabled { background: transparent; color: #bec6d1; }
QToolButton#annotationSetting { background: transparent; border: none; border-radius: 5px; padding: 1px 3px; color: #65738a; font-size: 11px; }
QToolButton#annotationSetting:hover { background: #edf2fa; color: #3168df; }
QToolButton#annotationSetting::menu-indicator { image: none; width: 0; }
QPushButton#annotationInsert { background: #3269e2; border: none; border-radius: 6px; color: #ffffff; padding: 0 12px; font-weight: 600; }
QPushButton#annotationInsert:hover { background: #2558cb; }
QPushButton#annotationInsert:pressed { background: #1f4db7; }
QLabel#annotationMeta { color: #929daf; font-family: 'Segoe UI'; font-size: 11px; background: transparent; }
QWidget#annotationSeparator { background: #e2e7f0; }
QMenu { background: #ffffff; color: #3d4b60; border: 1px solid #e1e6ef; border-radius: 6px; padding: 5px; }
QMenu::item { padding: 7px 22px; border-radius: 4px; }
QMenu::item:selected { background: #edf3ff; }
"""


def apply_style(app):
    """The Windows offscreen Qt backend doesn't discover installed system fonts."""
    import os
    from pathlib import Path
    from PySide6.QtGui import QFont, QFontDatabase

    if not QFontDatabase.families() and os.name == "nt":
        directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf", "segoeuib.ttf"):
            QFontDatabase.addApplicationFont(str(directory / name))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Microsoft YaHei UI", 10))
