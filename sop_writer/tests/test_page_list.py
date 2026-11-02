"""Page selection, context-sensitive clipboard operations and real Qt row moves."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
import unittest
from unittest.mock import patch

from PySide6.QtCore import QModelIndex, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from sop_studio.app import MainWindow
from sop_studio.document import Document, Element, Page
from sop_studio.rendering import image_bytes
from sop_studio.style import apply_style


APP = QApplication.instance() or QApplication([])
apply_style(APP)


def flush():
    for _ in range(4):
        APP.processEvents()


class PageListTests(unittest.TestCase):
    def setUp(self):
        self.window = MainWindow(test_mode=True)
        self.window.show()
        self.window.activateWindow()
        flush()
        document = Document(pages=[
            Page(width=640, height=640, elements=[Element(text="第一页", width=500)]),
            Page(width=800, height=600, elements=[Element(text="第二页", width=600, text_stroke_color="#3366ee",
                                                       text_stroke_width=2.5, text_stroke_alignment="center",
                                                       text_opacity=.7, background="#eef2fa",
                                                       box_stroke_color="#99aabb", box_stroke_width=3, box_opacity=.4)]),
            Page(width=600, height=900, elements=[Element(text="第三页", width=450)]),
        ])
        image = QImage(96, 64, QImage.Format.Format_RGB32)
        image.fill(QColor("#3366ee"))
        self.asset = document.add_asset(image_bytes(image))
        document.pages[1].elements.append(Element(kind="image", asset=self.asset, y=180, width=96, height=64))
        self.window.controller.replace(document)
        flush()
        self.window.canvas.fit_width(document.pages[0].id)

    def tearDown(self):
        APP.clipboard().clear()
        self.window.close()
        flush()

    def pages(self):
        return self.window.controller.document.pages

    def click_page(self, index):
        widget = self.window.page_list
        item = widget.item(index)
        widget.scrollToItem(item)
        flush()
        QTest.mouseClick(widget.viewport(), Qt.MouseButton.LeftButton, pos=widget.visualItemRect(item).center())
        flush()

    def shortcut(self, key, target=None):
        target = target or self.window.page_list
        QTest.keyClick(target, key, Qt.KeyboardModifier.ControlModifier)
        flush()

    def test_active_page_is_implicit_and_does_not_select_a_thumbnail(self):
        window = self.window
        self.assertIsNone(window.selected_page_id)
        self.assertEqual(window.page_list.selectedItems(), [])
        window.activate_page(self.pages()[1].id)
        self.assertEqual(window.current_page().id, self.pages()[1].id)
        self.assertEqual(window.page_list.selectedItems(), [])
        element = self.pages()[2].elements[0]
        window.canvas.select_element(element.id)
        self.assertEqual(window.current_page().id, self.pages()[2].id)
        self.assertIsNone(window.selected_page_id)
        self.assertEqual(window.page_list.selectedItems(), [])

    def test_clicking_a_thumbnail_selects_a_page_and_canvas_click_clears_only_its_blue_box(self):
        window = self.window
        window.canvas.select_element(self.pages()[0].elements[0].id)
        self.click_page(1)
        page_id = self.pages()[1].id
        self.assertEqual(window.selected_page_id, page_id)
        self.assertEqual(window.current_page().id, page_id)
        self.assertEqual(len(window.page_list.selectedItems()), 1)
        self.assertEqual(window.canvas.selected_id(), "")
        point = window.canvas.mapFromScene(window.canvas.origins[page_id] + QPointF(300, 350))
        QTest.mouseClick(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
        flush()
        self.assertIsNone(window.selected_page_id)
        self.assertEqual(window.page_list.selectedItems(), [])
        self.assertEqual(window.current_page().id, page_id)

    def test_ctrl_m_adds_a_page_after_the_current_page_with_matching_dimensions(self):
        window = self.window
        self.click_page(1)
        source = replace(self.pages()[1])
        self.shortcut(Qt.Key.Key_M)
        new_page = self.pages()[2]
        self.assertEqual(len(self.pages()), 4)
        self.assertEqual((new_page.width, new_page.height), (source.width, source.height))
        self.assertEqual(new_page.elements, [])
        self.assertEqual(window.active_page_id, new_page.id)
        self.assertEqual(window.selected_page_id, new_page.id)
        window.undo()
        flush()
        self.assertEqual(len(self.pages()), 3)
        self.assertIsNone(window.selected_page_id)
        self.assertEqual(window.page_list.selectedItems(), [])

    def test_switching_from_page_selection_to_an_element_keeps_element_shortcuts_working(self):
        window = self.window
        self.click_page(1)
        element = self.pages()[1].elements[0]
        item = window.canvas.items_by_id[element.id]
        point = window.canvas.mapFromScene(item.mapToScene(QPointF(20, 20)))
        QTest.mouseClick(window.canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
        flush()
        self.assertEqual(window.canvas.selected_id(), element.id)
        self.assertIsNone(window.selected_page_id)
        initial_x = window.selected()[1].x
        for _ in range(2):
            QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_Right)
            flush()
            self.assertEqual(window.canvas.selected_id(), element.id)
        self.assertEqual(window.selected()[1].x, initial_x + 2)
        self.shortcut(Qt.Key.Key_C, window.canvas.viewport())
        self.assertFalse(window.has_page_clipboard())
        self.shortcut(Qt.Key.Key_V, window.canvas.viewport())
        self.assertEqual(len(self.pages()), 3)
        self.assertEqual(len(self.pages()[1].elements), 3)

    def test_ctrl_m_from_canvas_adds_an_implicit_page_and_commits_text_editing(self):
        window = self.window
        window.canvas.select_element(self.pages()[0].elements[0].id)
        window.canvas.setFocus()
        QTest.keyClick(window.canvas.viewport(), Qt.Key.Key_F2)
        item = window.canvas.editing_item()
        cursor = item.text_item.textCursor()
        cursor.insertText(" · 已编辑")
        item.text_item.setTextCursor(cursor)
        self.shortcut(Qt.Key.Key_M, window.canvas.viewport())
        self.assertEqual(len(self.pages()), 4)
        self.assertTrue(self.pages()[0].elements[0].text.endswith("已编辑"))
        self.assertIsNone(window.canvas.editing_item())
        self.assertEqual(window.active_page_id, self.pages()[1].id)
        self.assertIsNone(window.selected_page_id)

    def test_ctrl_c_v_duplicates_the_explicit_page_with_styles_assets_and_fresh_ids(self):
        window = self.window
        self.click_page(1)
        source = self.pages()[1]
        self.shortcut(Qt.Key.Key_C)
        self.assertTrue(window.has_page_clipboard())
        self.shortcut(Qt.Key.Key_V)
        copied = self.pages()[2]
        self.assertEqual(len(self.pages()), 4)
        self.assertNotEqual(copied.id, source.id)
        self.assertEqual((copied.width, copied.height), (source.width, source.height))
        for original, element in zip(source.elements, copied.elements):
            self.assertNotEqual(element.id, original.id)
            self.assertEqual(element, replace(original, id=element.id))
        self.assertEqual(window.selected_page_id, copied.id)
        self.assertEqual(window.page_list.selected_page_id(), copied.id)
        self.assertFalse(QImage.fromData(window.controller.document.assets[copied.elements[1].asset]).isNull())
        self.shortcut(Qt.Key.Key_V)
        all_ids = [page.id for page in self.pages()] + [element.id for page in self.pages() for element in page.elements]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(len(window.controller.document.assets), 1)
        window.undo()
        flush()
        self.assertEqual(len(self.pages()), 4)
        window.redo()
        flush()
        self.assertEqual(len(self.pages()), 5)

    def test_copied_page_survives_replacing_the_document(self):
        window = self.window
        self.click_page(1)
        self.shortcut(Qt.Key.Key_C)
        source = window.page_clipboard[0]
        window.controller.replace(Document())
        flush()
        self.shortcut(Qt.Key.Key_V)
        self.assertEqual(len(self.pages()), 2)
        self.assertEqual(self.pages()[1].elements[0].text, source.elements[0].text)
        self.assertIn(self.asset, window.controller.document.assets)

    def test_copying_normal_text_replaces_the_page_clipboard_and_pastes_an_element(self):
        window = self.window
        self.click_page(1)
        self.shortcut(Qt.Key.Key_C)
        APP.clipboard().setText("普通文字")
        self.assertFalse(window.has_page_clipboard())
        self.shortcut(Qt.Key.Key_V)
        self.assertEqual(len(self.pages()), 3)
        self.assertEqual(self.pages()[1].elements[-1].text, "普通文字")
        self.assertIsNone(window.selected_page_id)
        self.assertEqual(window.page_list.selectedItems(), [])

    def test_copy_paste_in_a_text_field_keeps_its_native_behavior_with_a_page_selected(self):
        window = self.window
        self.click_page(1)
        window.title_input.setFocus()
        window.title_input.setText("ABCD")
        window.title_input.setSelection(1, 2)
        self.shortcut(Qt.Key.Key_C, window.title_input)
        self.assertEqual(APP.clipboard().text(), "BC")
        self.assertFalse(window.has_page_clipboard())
        APP.clipboard().setText("ZZ")
        self.shortcut(Qt.Key.Key_V, window.title_input)
        self.assertEqual(window.title_input.text(), "AZZD")
        self.assertEqual(len(self.pages()), 3)

    def test_delete_uses_the_explicit_page_and_can_be_undone_without_confirmation(self):
        window = self.window
        self.click_page(1)
        deleted = self.pages()[1]
        following_id = self.pages()[2].id
        with patch("sop_studio.app.QMessageBox.question", side_effect=AssertionError("Unexpected confirmation")):
            QTest.keyClick(window.page_list, Qt.Key.Key_Delete)
        flush()
        self.assertEqual(len(self.pages()), 2)
        self.assertNotIn(deleted.id, [page.id for page in self.pages()])
        self.assertEqual(window.selected_page_id, following_id)
        window.undo()
        flush()
        self.assertEqual(self.pages()[1], deleted)
        self.assertEqual(window.page_list.page_ids(), [page.id for page in self.pages()])

    def test_deleting_the_last_page_keeps_one_blank_page(self):
        window = self.window
        window.controller.replace(Document(pages=[Page(elements=[Element(text="保留文档")])]))
        flush()
        self.click_page(0)
        QTest.keyClick(window.page_list, Qt.Key.Key_Delete)
        flush()
        self.assertEqual(len(self.pages()), 1)
        self.assertEqual(self.pages()[0].elements, [])
        window.undo()
        flush()
        self.assertEqual(self.pages()[0].elements[0].text, "保留文档")

    def test_escape_and_blank_area_clear_the_explicit_selection_but_keep_the_active_page(self):
        window = self.window
        self.click_page(1)
        page_id = window.active_page_id
        QTest.keyClick(window.page_list, Qt.Key.Key_Escape)
        self.assertIsNone(window.selected_page_id)
        self.assertEqual(window.active_page_id, page_id)
        QTest.keyClick(window.page_list, Qt.Key.Key_Delete)
        self.assertEqual(len(self.pages()), 3)
        self.click_page(1)
        blank = QPoint(20, window.page_list.viewport().height() - 5)
        self.assertIsNone(window.page_list.itemAt(blank))
        QTest.mouseClick(window.page_list.viewport(), Qt.MouseButton.LeftButton, pos=blank)
        self.assertIsNone(window.selected_page_id)
        self.assertEqual(window.active_page_id, page_id)

    def test_qt_row_moves_update_document_order_and_preserve_selection_through_undo(self):
        window = self.window
        self.click_page(1)
        original_order = [page.id for page in self.pages()]
        selected = window.selected_page_id
        self.assertTrue(window.page_list.model().moveRow(QModelIndex(), 1, QModelIndex(), 0))
        flush()
        moved_order = [original_order[1], original_order[0], original_order[2]]
        self.assertEqual([page.id for page in self.pages()], moved_order)
        self.assertEqual(window.page_list.page_ids(), moved_order)
        self.assertEqual(window.selected_page_id, selected)
        self.assertEqual(window.active_page_id, selected)
        window.undo()
        flush()
        self.assertEqual(window.page_list.page_ids(), original_order)
        self.assertEqual(window.page_list.selected_page_id(), selected)
        window.redo()
        flush()
        self.assertEqual(window.page_list.page_ids(), moved_order)
        self.assertTrue(window.page_list.item(0).text().startswith("01"))
        self.assertEqual(window.page_list.horizontalScrollBar().maximum(), 0)

    def test_sidebar_can_expand_to_640_and_fields_fit_without_horizontal_scrolling(self):
        window = self.window
        window.canvas.select_element(self.pages()[1].elements[0].id)
        window.workspace_splitter.setSizes([184, 896, 400])
        flush()
        before = window.inspector_scroll.width()
        handle = window.workspace_splitter.handle(2)
        start = QPoint(0, handle.height() // 2)
        QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(handle, start - QPoint(200, 0), 20)
        QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=start - QPoint(200, 0))
        flush()
        self.assertGreater(window.inspector_scroll.width(), before)
        window.workspace_splitter.setSizes([184, 1, 10000])
        flush()
        self.assertEqual(window.inspector_scroll.width(), 640)
        self.assertEqual(window.inspector_scroll.horizontalScrollBar().maximum(), 0)
        for button in window.inspector_scroll.findChildren(QPushButton):
            self.assertNotIn(button.text(), ("复制页", "删除页", "上移页", "下移页"))


if __name__ == "__main__":
    unittest.main()
