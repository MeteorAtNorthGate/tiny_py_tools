"""Undoable document transactions; immutable image bytes are shared by snapshots."""
from copy import deepcopy
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from .document import Document


class SnapshotCommand(QUndoCommand):
    def __init__(self, controller, label, before, after):
        super().__init__(label)
        self.controller, self.before, self.after = controller, before, after

    def undo(self):
        self.controller.document = deepcopy(self.before)
        self.controller.changed.emit()

    def redo(self):
        self.controller.document = deepcopy(self.after)
        self.controller.changed.emit()


class DocumentController(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = Document()
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(100)

    def perform(self, label: str, mutation: Callable[[Document], None]):
        before = deepcopy(self.document)
        try:
            mutation(self.document)
            if self.document != before:
                after = deepcopy(self.document)
                self.undo_stack.push(SnapshotCommand(self, label, before, after))
        except Exception:
            self.document = before
            raise

    def replace(self, document: Document):
        self.document = document
        self.undo_stack.clear()
        self.undo_stack.setClean()
        self.changed.emit()
