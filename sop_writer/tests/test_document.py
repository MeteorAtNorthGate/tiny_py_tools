import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from sop_studio.document import Document, Element, Page, load_document, save_document


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "操作说明.sopx"

    def test_roundtrip_all_pages_text_styles_and_embedded_assets(self):
        document = Document(title="设备操作规程")
        # Persistence validates PNG identity; decoding is checked separately by Qt.
        png = b"\x89PNG\r\n\x1a\nembedded-image"
        asset = document.add_asset(png)
        document.add_asset(b"unused image from history")
        document.pages[0].elements = [Element(text="第一步\n确认设备", bold=True, color="#1a2b3c"),
                                       Element(kind="image", asset=asset, width=300, height=240)]
        document.pages.append(Page(width=1440, height=900, elements=[Element(text="完成。")]))
        save_document(document, self.path)
        recovered = load_document(self.path)
        self.assertEqual(recovered.pages, document.pages)
        self.assertEqual(recovered.title, document.title)
        self.assertEqual(recovered.assets, {asset: png})
        with zipfile.ZipFile(self.path) as archive:
            self.assertEqual(len(archive.namelist()), 2)

    def test_failed_replacement_preserves_previous_file(self):
        save_document(Document(title="旧版本"), self.path)
        with patch("sop_studio.document.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaises(PermissionError):
                save_document(Document(title="新版本"), self.path)
        self.assertEqual(load_document(self.path).title, "旧版本")
        self.assertEqual([p.name for p in self.path.parent.iterdir()], [self.path.name])

    def test_invalid_geometry_rejected_before_overwriting(self):
        save_document(Document(title="有效文档"), self.path)
        bad = Document(pages=[Page(elements=[Element(x=float("nan"))])])
        with self.assertRaises(ValueError):
            save_document(bad, self.path)
        self.assertEqual(load_document(self.path).title, "有效文档")

    def test_missing_asset_and_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            save_document(Document(pages=[Page(elements=[Element(kind="image", asset="missing")])]), self.path)
        page = Page()
        with self.assertRaises(ValueError):
            save_document(Document(pages=[page, page]), self.path)

    def test_foreign_or_corrupt_file_has_actionable_error(self):
        self.path.write_text("not a zip", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "有效"):
            load_document(self.path)
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("document.json", json.dumps({"format": "sop-studio", "version": 999}))
        with self.assertRaisesRegex(ValueError, "版本"):
            load_document(self.path)

    def test_tampered_image_is_not_silently_accepted(self):
        from dataclasses import asdict
        document = Document()
        key = document.add_asset(b"\x89PNG\r\n\x1a\noriginal")
        document.pages[0].elements.append(Element(kind="image", asset=key))
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("document.json", json.dumps({"format": "sop-studio", "version": 1, "title": document.title,
                                                          "pages": [asdict(p) for p in document.pages]}))
            archive.writestr(f"assets/{key}.png", b"\x89PNG\r\n\x1a\nmodified")
        with self.assertRaisesRegex(ValueError, "校验"):
            load_document(self.path)


if __name__ == "__main__":
    unittest.main()
