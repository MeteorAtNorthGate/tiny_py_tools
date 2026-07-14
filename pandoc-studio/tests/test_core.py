import unittest
from pathlib import Path

from pandoc_gui.core import (
    INPUT_FORMATS,
    OUTPUT_FORMATS,
    build_pandoc_arguments,
    human_file_size,
    output_path_for,
    replace_output_extension,
)


def output_format(name: str):
    return next(item for item in OUTPUT_FORMATS if item.pandoc_name == name)


def input_format(name: str):
    return next(item for item in INPUT_FORMATS if item.pandoc_name == name)


class CoreTests(unittest.TestCase):
    def test_default_destination_uses_selected_extension(self):
        source = Path(r"C:\Users\Ada\Documents\notes.md")
        self.assertEqual(
            output_path_for(source, output_format("docx")),
            Path(r"C:\Users\Ada\Documents\notes.docx"),
        )

    def test_default_destination_never_overwrites_same_extension_source(self):
        source = Path("draft.md")
        self.assertEqual(
            output_path_for(source, output_format("markdown")),
            Path("draft_converted.md"),
        )

    def test_auto_input_omits_from_argument(self):
        arguments = build_pandoc_arguments(
            Path("notes.md"), Path("notes.docx"), output_format("docx")
        )
        self.assertNotIn("--from", arguments)
        self.assertEqual(
            arguments,
            [
                "notes.md",
                "--to",
                "docx",
                "--standalone",
                "--output",
                "notes.docx",
            ],
        )

    def test_custom_input_adds_from_argument(self):
        arguments = build_pandoc_arguments(
            Path("README"),
            Path("README.html"),
            output_format("html5"),
            input_format("gfm"),
        )
        self.assertEqual(arguments[1:3], ["--from", "gfm"])

    def test_destination_extension_follows_format(self):
        self.assertEqual(
            replace_output_extension(Path("out/custom.name"), output_format("epub3")),
            Path("out/custom.epub"),
        )

    def test_human_file_size(self):
        self.assertEqual(human_file_size(0), "0 B")
        self.assertEqual(human_file_size(1536), "1.5 KB")


if __name__ == "__main__":
    unittest.main()
