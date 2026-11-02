"""A vertical thumbnail list with explicit selection and native row dragging."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QListWidget, QStyledItemDelegate, QStyleOptionViewItem


class PageThumbnailDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.decorationPosition = QStyleOptionViewItem.Position.Top
        option.decorationAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        option.displayAlignment = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
        if option.rect.width() > 0:
            width = max(64, min(120, option.rect.width() - 20))
            option.decorationSize = QSize(width, round(width * 170 / 120))


class PageList(QListWidget):
    order_changed = Signal(list)
    delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pageList")
        self.setViewMode(QListWidget.ViewMode.ListMode)
        self.setFlow(QListWidget.Flow.TopToBottom)
        self.setWrapping(False)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setEditTriggers(QListWidget.EditTrigger.NoEditTriggers)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragDropOverwriteMode(False)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setAutoScroll(True)
        self.setAutoScrollMargin(36)
        self.setItemDelegate(PageThumbnailDelegate(self))
        self.model().rowsMoved.connect(self.rows_moved)
        self.setToolTip("单击选择页面；Ctrl+C / Ctrl+V 复制粘贴，Delete 删除，上下拖动调整页序，Esc 取消选择。")

    def page_ids(self):
        return [self.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.count())]

    def selected_page_id(self):
        items = self.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def rows_moved(self, *args):
        self.order_changed.emit(self.page_ids())

    def clear_page_selection(self):
        self.clearSelection()
        self.setCurrentItem(None)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.itemAt(event.position().toPoint()) is None:
            self.clear_page_selection()
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.selectedItems():
                self.delete_requested.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.clear_page_selection()
            event.accept()
        else:
            super().keyPressEvent(event)
