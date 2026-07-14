"""Main PySide6 interface and Pandoc process integration."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .core import (
    INPUT_FORMATS,
    OUTPUT_FORMATS,
    FormatOption,
    build_pandoc_arguments,
    human_file_size,
    matching_filter,
    output_path_for,
    replace_output_extension,
)
from .widgets import DropZone


APP_STYLE = """
QWidget {
    color: #1f1b35;
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
}
QMainWindow, QWidget#root {
    background: #f6f4fb;
}
QScrollArea {
    background: #f6f4fb;
    border: none;
}
QFrame#mainCard {
    background: #ffffff;
    border: 1px solid #e8e4f2;
    border-radius: 24px;
}
QLabel#brandMark {
    background: #7257f5;
    color: white;
    border-radius: 10px;
    font-size: 18px;
    font-weight: 800;
}
QLabel#brandName {
    color: #17132b;
    font-size: 17px;
    font-weight: 750;
}
QLabel#eyebrow {
    color: #7357f6;
    font-size: 11px;
    font-weight: 700;
}
QLabel#title {
    color: #17132b;
    font-size: 29px;
    font-weight: 750;
}
QLabel#subtitle, QLabel#muted, QLabel#formatHint, QLabel#footerText {
    color: #777189;
}
QLabel#subtitle {
    font-size: 14px;
}
QLabel#dropTitle {
    color: #25203b;
    font-size: 16px;
    font-weight: 700;
    background: transparent;
}
QLabel#dropHint, QLabel#fileMeta {
    color: #817b91;
    background: transparent;
}
QLabel#fileName {
    color: #25203b;
    font-size: 15px;
    font-weight: 700;
    background: transparent;
}
QPushButton {
    border: none;
    border-radius: 10px;
    padding: 9px 16px;
    font-weight: 650;
}
QPushButton#ghostButton {
    color: #6349df;
    background: #f0edff;
}
QPushButton#ghostButton:hover {
    background: #e8e3ff;
}
QPushButton#linkButton {
    color: #6b50ea;
    background: transparent;
    padding: 5px 6px;
}
QPushButton#linkButton:hover {
    color: #4d34c8;
    text-decoration: underline;
}
QPushButton#convertButton {
    color: #ffffff;
    background: #7357f6;
    border-radius: 13px;
    padding: 13px 24px;
    font-size: 15px;
    font-weight: 750;
}
QPushButton#convertButton:hover {
    background: #6246e5;
}
QPushButton#convertButton:pressed {
    background: #5038c7;
}
QPushButton#convertButton:disabled {
    color: #b0a9cb;
    background: #e9e6f2;
}
QFrame#formatCard, QFrame#destinationCard, QFrame#resultCard {
    background: #faf9fd;
    border: 1px solid #ece8f4;
    border-radius: 14px;
}
QLabel#fieldLabel {
    color: #3b3550;
    font-size: 12px;
    font-weight: 700;
}
QComboBox {
    color: #242039;
    background: #ffffff;
    border: 1px solid #dcd7e8;
    border-radius: 9px;
    min-height: 38px;
    padding: 0 12px;
}
QComboBox:hover, QComboBox:focus {
    border: 1px solid #8067ef;
}
QComboBox::drop-down {
    width: 34px;
    border: none;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #756e87;
    margin-right: 12px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    color: #242039;
    border: 1px solid #dcd7e8;
    selection-background-color: #eeeaff;
    selection-color: #3e2ea3;
    outline: none;
    padding: 5px;
}
QFrame#divider {
    background: #eeeaf5;
    min-height: 1px;
    max-height: 1px;
}
QLabel#statusPill {
    color: #4b4470;
    background: #f0edf8;
    border-radius: 9px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#statusPill[state="ready"] {
    color: #237a57;
    background: #e7f7ef;
}
QLabel#statusPill[state="error"] {
    color: #a03c47;
    background: #fdebed;
}
QLabel#statusPill[state="working"] {
    color: #6a4edd;
    background: #eeeaff;
}
QLabel#statusMessage {
    color: #615a74;
}
QLabel#statusMessage[state="error"] {
    color: #b43b49;
}
QLabel#statusMessage[state="success"] {
    color: #247a59;
    font-weight: 650;
}
QProgressBar {
    background: #e9e5f2;
    border: none;
    border-radius: 3px;
    min-height: 5px;
    max-height: 5px;
}
QProgressBar::chunk {
    background: #7357f6;
    border-radius: 3px;
}
"""


class MainWindow(QMainWindow):
    """Single-window Pandoc conversion workflow."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Pandoc Studio")
        self.setMinimumSize(760, 640)
        self.resize(900, 760)

        self.source_path: Path | None = None
        self.destination_path: Path | None = None
        self.destination_was_chosen = False
        self.pandoc_path: str | None = shutil.which("pandoc")
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._conversion_active = False

        self.version_process = QProcess(self)
        self.version_process.finished.connect(self._on_version_checked)
        self.version_process.errorOccurred.connect(self._on_version_error)

        self.convert_process = QProcess(self)
        self.convert_process.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self.convert_process.readyReadStandardOutput.connect(self._read_stdout)
        self.convert_process.readyReadStandardError.connect(self._read_stderr)
        self.convert_process.started.connect(self._on_conversion_started)
        self.convert_process.finished.connect(self._on_conversion_finished)
        self.convert_process.errorOccurred.connect(self._on_conversion_error)

        self._build_ui()
        self._check_pandoc()

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setCentralWidget(scroll)

        root = QWidget()
        root.setObjectName("root")
        root.setMinimumWidth(720)
        scroll.setWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 18, 24, 18)

        card = QFrame()
        card.setObjectName("mainCard")
        card.setMaximumWidth(940)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignHCenter)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(42, 22, 42, 20)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(11)
        brand_mark = QLabel("P")
        brand_mark.setObjectName("brandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(38, 38)
        header.addWidget(brand_mark)
        brand_name = QLabel("Pandoc Studio")
        brand_name.setObjectName("brandName")
        header.addWidget(brand_name)
        header.addStretch()
        self.status_pill = QLabel("正在检测…")
        self.status_pill.setObjectName("statusPill")
        self.status_pill.setProperty("state", "working")
        header.addWidget(self.status_pill)
        layout.addLayout(header)

        layout.addSpacing(18)
        eyebrow = QLabel("DOCUMENT CONVERTER")
        eyebrow.setObjectName("eyebrow")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(eyebrow)
        layout.addSpacing(4)
        title = QLabel("把文档变成你需要的格式")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(4)
        subtitle = QLabel("拖入一个文件，选择输出格式，其余交给 Pandoc。")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(16)
        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self._set_source)
        self.drop_zone.browse_requested.connect(self._browse_source)
        layout.addWidget(self.drop_zone)
        self._build_drop_content()

        layout.addSpacing(12)
        formats = QHBoxLayout()
        formats.setSpacing(14)
        formats.addWidget(self._build_input_card(), 1)
        formats.addWidget(self._build_output_card(), 1)
        layout.addLayout(formats)

        layout.addSpacing(10)
        destination_card = QFrame()
        destination_card.setObjectName("destinationCard")
        destination_layout = QHBoxLayout(destination_card)
        destination_layout.setContentsMargins(15, 12, 12, 12)
        destination_layout.setSpacing(10)
        path_column = QVBoxLayout()
        path_column.setSpacing(3)
        path_label = QLabel("输出位置")
        path_label.setObjectName("fieldLabel")
        path_column.addWidget(path_label)
        self.destination_label = QLabel("选择文件后自动生成")
        self.destination_label.setObjectName("muted")
        self.destination_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.destination_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_column.addWidget(self.destination_label)
        destination_layout.addLayout(path_column, 1)
        self.destination_button = QPushButton("另存为…")
        self.destination_button.setObjectName("linkButton")
        self.destination_button.setEnabled(False)
        self.destination_button.clicked.connect(self._browse_destination)
        destination_layout.addWidget(self.destination_button)
        layout.addWidget(destination_card)

        layout.addSpacing(10)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.hide()
        layout.addWidget(self.progress)
        layout.addSpacing(6)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        self.status_message = QLabel("请先拖入或选择一个文档")
        self.status_message.setObjectName("statusMessage")
        self.status_message.setWordWrap(True)
        action_row.addWidget(self.status_message, 1)
        self.open_folder_button = QPushButton("打开所在文件夹")
        self.open_folder_button.setObjectName("linkButton")
        self.open_folder_button.clicked.connect(self._open_destination_folder)
        self.open_folder_button.hide()
        action_row.addWidget(self.open_folder_button)
        self.convert_button = QPushButton("Convert!  →")
        self.convert_button.setObjectName("convertButton")
        self.convert_button.setMinimumWidth(150)
        self.convert_button.setEnabled(False)
        self.convert_button.clicked.connect(self._convert)
        action_row.addWidget(self.convert_button)
        layout.addLayout(action_row)

        layout.addSpacing(12)
        divider = QFrame()
        divider.setObjectName("divider")
        layout.addWidget(divider)
        layout.addSpacing(10)
        footer = QHBoxLayout()
        footer.setSpacing(7)
        self.pandoc_indicator = QLabel("●")
        self.pandoc_indicator.setStyleSheet("color: #aaa3b8;")
        footer.addWidget(self.pandoc_indicator)
        self.pandoc_version_label = QLabel("正在从系统 PATH 检测 Pandoc…")
        self.pandoc_version_label.setObjectName("footerText")
        footer.addWidget(self.pandoc_version_label)
        footer.addStretch()
        privacy = QLabel("文件仅在本机处理")
        privacy.setObjectName("footerText")
        footer.addWidget(privacy)
        layout.addLayout(footer)

    def _build_drop_content(self) -> None:
        self.drop_stack = QStackedWidget()
        self.drop_stack.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.drop_zone.layout().addWidget(self.drop_stack)

        empty = QWidget()
        empty.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(0, 58, 0, 0)
        empty_layout.setSpacing(7)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title = QLabel("拖放文件到这里")
        empty_title.setObjectName("dropTitle")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_hint = QLabel("或点击此区域从电脑中选择")
        empty_hint.setObjectName("dropHint")
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(empty_hint)
        self.drop_stack.addWidget(empty)

        selected = QWidget()
        selected.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        selected_layout = QVBoxLayout(selected)
        selected_layout.setContentsMargins(0, 54, 0, 0)
        selected_layout.setSpacing(6)
        selected_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_name_label = QLabel()
        self.file_name_label.setObjectName("fileName")
        self.file_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selected_layout.addWidget(self.file_name_label)
        self.file_meta_label = QLabel()
        self.file_meta_label.setObjectName("fileMeta")
        self.file_meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selected_layout.addWidget(self.file_meta_label)
        change_hint = QLabel("点击或重新拖入文件可替换")
        change_hint.setObjectName("dropHint")
        change_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selected_layout.addWidget(change_hint)
        self.drop_stack.addWidget(selected)

    def _build_input_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("formatCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 13, 15, 13)
        card_layout.setSpacing(7)
        label = QLabel("自定义输入格式  ·  可选")
        label.setObjectName("fieldLabel")
        card_layout.addWidget(label)
        self.input_combo = QComboBox()
        self.input_combo.setAccessibleName("自定义输入格式")
        self.input_combo.addItem("", None)
        for option in INPUT_FORMATS:
            self.input_combo.addItem(option.label, option)
        self.input_combo.setCurrentIndex(0)
        self.input_combo.setToolTip("留空时由 Pandoc 根据文件后缀判断")
        card_layout.addWidget(self.input_combo)
        hint = QLabel("留空时按文件后缀自动判断")
        hint.setObjectName("formatHint")
        card_layout.addWidget(hint)
        return card

    def _build_output_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("formatCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(15, 13, 15, 13)
        card_layout.setSpacing(7)
        label = QLabel("输出文件格式")
        label.setObjectName("fieldLabel")
        card_layout.addWidget(label)
        self.output_combo = QComboBox()
        self.output_combo.setAccessibleName("输出文件格式")
        for option in OUTPUT_FORMATS:
            self.output_combo.addItem(f"{option.label}  ({option.extension})", option)
        self.output_combo.currentIndexChanged.connect(self._output_format_changed)
        card_layout.addWidget(self.output_combo)
        self.output_note = QLabel("转换后的文件保存在原文件旁")
        self.output_note.setObjectName("formatHint")
        card_layout.addWidget(self.output_note)
        return card

    def _browse_source(self) -> None:
        start = str(self.source_path.parent if self.source_path else Path.home())
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择要转换的文档",
            start,
            matching_filter((*INPUT_FORMATS, *OUTPUT_FORMATS)),
        )
        if filename:
            self._set_source(Path(filename))

    def _set_source(self, path: Path) -> None:
        if self._conversion_active:
            return
        if not path.exists() or not path.is_file():
            self._set_message("无法读取所选文件", "error")
            return

        self.source_path = path.resolve()
        self.destination_was_chosen = False
        self.destination_path = output_path_for(self.source_path, self._current_output_format())
        self.file_name_label.setText(self.source_path.name)
        try:
            size = human_file_size(self.source_path.stat().st_size)
        except OSError:
            size = "大小未知"
        suffix = self.source_path.suffix.lower() or "无扩展名"
        self.file_meta_label.setText(f"{suffix}  ·  {size}")
        self.drop_stack.setCurrentIndex(1)
        self.destination_button.setEnabled(True)
        self._update_destination_label()
        self._set_message("文件已就绪，选择格式后开始转换")
        self.open_folder_button.hide()
        self._update_convert_enabled()

    def _browse_destination(self) -> None:
        if self.source_path is None:
            return
        output_format = self._current_output_format()
        proposed = self.destination_path or output_path_for(self.source_path, output_format)
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "保存转换后的文档",
            str(proposed),
            f"{output_format.label} (*{output_format.extension});;所有文件 (*.*)",
        )
        if filename:
            selected = Path(filename)
            if selected.suffix.lower() != output_format.extension:
                selected = selected.with_suffix(output_format.extension)
            self.destination_path = selected.resolve()
            self.destination_was_chosen = True
            self._update_destination_label()

    def _output_format_changed(self) -> None:
        option = self._current_output_format()
        self.output_note.setText(option.note or "转换后的文件保存在原文件旁")
        if self.source_path is None:
            return
        if self.destination_was_chosen and self.destination_path is not None:
            self.destination_path = replace_output_extension(self.destination_path, option)
        else:
            self.destination_path = output_path_for(self.source_path, option)
        self._update_destination_label()
        self.open_folder_button.hide()

    def _current_input_format(self) -> FormatOption | None:
        return self.input_combo.currentData()

    def _current_output_format(self) -> FormatOption:
        option = self.output_combo.currentData()
        assert isinstance(option, FormatOption)
        return option

    def _update_destination_label(self) -> None:
        if self.destination_path is None:
            self.destination_label.setText("选择文件后自动生成")
            self.destination_label.setToolTip("")
            return
        self.destination_label.setText(str(self.destination_path))
        self.destination_label.setToolTip(str(self.destination_path))

    def _convert(self) -> None:
        if self.source_path is None or self.destination_path is None:
            return
        if self.pandoc_path is None:
            self._show_missing_pandoc()
            return
        if self.destination_path == self.source_path:
            self._set_message("输出文件不能与输入文件相同", "error")
            return
        if self.destination_path.exists():
            answer = QMessageBox.question(
                self,
                "覆盖已有文件？",
                f"“{self.destination_path.name}” 已存在。是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        try:
            self.destination_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._set_message(f"无法创建输出文件夹：{exc}", "error")
            return

        self._stdout.clear()
        self._stderr.clear()
        self._conversion_active = True
        self.open_folder_button.hide()
        self._set_busy(True)
        arguments = build_pandoc_arguments(
            self.source_path,
            self.destination_path,
            self._current_output_format(),
            self._current_input_format(),
        )
        # Relative image/include paths in Markdown and similar inputs should be
        # resolved from the source document's folder, not the app's folder.
        self.convert_process.setWorkingDirectory(str(self.source_path.parent))
        self.convert_process.start(self.pandoc_path, arguments)

    def _on_conversion_started(self) -> None:
        self._set_message("Pandoc 正在转换，请稍候…")

    def _read_stdout(self) -> None:
        self._stdout.extend(bytes(self.convert_process.readAllStandardOutput()))

    def _read_stderr(self) -> None:
        self._stderr.extend(bytes(self.convert_process.readAllStandardError()))

    def _on_conversion_finished(self, exit_code: int, _exit_status) -> None:
        if not self._conversion_active:
            return
        self._read_stdout()
        self._read_stderr()
        self._conversion_active = False
        self._set_busy(False)

        succeeded = (
            exit_code == 0
            and self.destination_path is not None
            and self.destination_path.exists()
        )
        if succeeded:
            self._set_message(f"转换完成：{self.destination_path.name}", "success")
            self.open_folder_button.show()
            return

        detail = self._decode_process_output(self._stderr) or self._decode_process_output(self._stdout)
        if not detail:
            detail = f"Pandoc 已退出，错误代码 {exit_code}。"
        self._set_message("转换失败，请查看 Pandoc 返回的错误信息", "error")
        self.status_message.setToolTip(detail)
        self._show_conversion_error(detail)

    def _on_conversion_error(self, error: QProcess.ProcessError) -> None:
        if error != QProcess.ProcessError.FailedToStart or not self._conversion_active:
            return
        self._conversion_active = False
        self.pandoc_path = None
        self._set_busy(False)
        self._set_pandoc_status(False, "无法启动 Pandoc")
        self._set_message("无法启动 Pandoc，请检查系统 PATH", "error")
        self._show_missing_pandoc()

    @staticmethod
    def _decode_process_output(buffer: bytearray) -> str:
        text = bytes(buffer).decode("utf-8", errors="replace").strip()
        # Keep error dialogs useful without letting pathological logs take over.
        return text[-6000:]

    def _set_busy(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.progress.setRange(0, 0 if busy else 1)
        if not busy:
            self.progress.setValue(0)
        self.drop_zone.setEnabled(not busy)
        self.input_combo.setEnabled(not busy)
        self.output_combo.setEnabled(not busy)
        self.destination_button.setEnabled(not busy and self.source_path is not None)
        self.convert_button.setText("正在转换…" if busy else "Convert!  →")
        pill_text = "转换中" if busy else ("READY" if self.pandoc_path else "未找到")
        pill_state = "working" if busy else ("ready" if self.pandoc_path else "error")
        self._set_status_pill(pill_text, pill_state)
        self._update_convert_enabled()

    def _update_convert_enabled(self) -> None:
        self.convert_button.setEnabled(
            self.source_path is not None
            and self.destination_path is not None
            and self.pandoc_path is not None
            and not self._conversion_active
        )

    def _set_message(self, text: str, state: str = "normal") -> None:
        self.status_message.setText(text)
        self.status_message.setProperty("state", state)
        self.status_message.setToolTip("")
        self.status_message.style().unpolish(self.status_message)
        self.status_message.style().polish(self.status_message)

    def _check_pandoc(self) -> None:
        if self.pandoc_path is None:
            self._set_pandoc_status(False, "未在系统 PATH 中找到 Pandoc")
            self._set_message("未检测到 Pandoc，请先安装并添加到 PATH", "error")
            return
        self.version_process.start(self.pandoc_path, ["--version"])

    def _on_version_checked(self, exit_code: int, _exit_status) -> None:
        output = bytes(self.version_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        first_line = output.splitlines()[0].strip() if output.splitlines() else "Pandoc"
        if exit_code == 0:
            self._set_pandoc_status(True, f"{first_line}  ·  已通过系统 PATH 连接")
        else:
            self.pandoc_path = None
            self._set_pandoc_status(False, "Pandoc 版本检测失败")
        self._update_convert_enabled()

    def _on_version_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self.pandoc_path = None
            self._set_pandoc_status(False, "无法启动 Pandoc")
            self._update_convert_enabled()

    def _set_pandoc_status(self, available: bool, message: str) -> None:
        self.pandoc_indicator.setStyleSheet(f"color: {'#32a474' if available else '#d4515f'};")
        self.pandoc_version_label.setText(message)
        self._set_status_pill("READY" if available else "未找到", "ready" if available else "error")

    def _set_status_pill(self, text: str, state: str) -> None:
        self.status_pill.setText(text)
        self.status_pill.setProperty("state", state)
        self.status_pill.style().unpolish(self.status_pill)
        self.status_pill.style().polish(self.status_pill)

    def _show_missing_pandoc(self) -> None:
        QMessageBox.warning(
            self,
            "未找到 Pandoc",
            "无法从 Windows 系统 PATH 启动 pandoc。\n\n"
            "请先安装 Pandoc，并确认在命令提示符中运行 “pandoc --version” 能看到版本信息，"
            "然后重新启动本程序。",
        )

    def _show_conversion_error(self, detail: str) -> None:
        first_line = next((line.strip() for line in detail.splitlines() if line.strip()), detail)
        if len(first_line) > 240:
            first_line = f"{first_line[:237]}…"
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("转换失败")
        dialog.setText("Pandoc 未能完成转换。")
        dialog.setInformativeText(first_line)
        dialog.setDetailedText(detail)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()

    def _open_destination_folder(self) -> None:
        if self.destination_path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.destination_path.parent)))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._conversion_active:
            answer = QMessageBox.question(
                self,
                "转换仍在进行",
                "退出会终止当前转换。确定退出吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.convert_process.kill()
            self.convert_process.waitForFinished(1500)
        event.accept()


def run() -> int:
    """Create and run the Qt application."""

    if sys.platform == "win32":
        # Lets Windows group the application correctly on the taskbar.
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PandocStudio.Desktop.1")
        except (AttributeError, OSError):
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Pandoc Studio")
    app.setApplicationDisplayName("Pandoc Studio")
    app.setOrganizationName("Pandoc Studio")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    font = QFont("Segoe UI" if os.name == "nt" else "Sans Serif", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.activateWindow)
    return app.exec()
