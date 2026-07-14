"""Pure conversion helpers shared by the UI and tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, slots=True)
class FormatOption:
    """A Pandoc format exposed by the interface."""

    label: str
    pandoc_name: str
    extension: str
    note: str = ""


INPUT_FORMATS: tuple[FormatOption, ...] = (
    FormatOption("Markdown", "markdown", ".md"),
    FormatOption("GitHub Flavored Markdown", "gfm", ".md"),
    FormatOption("CommonMark", "commonmark_x", ".md"),
    FormatOption("HTML", "html", ".html"),
    FormatOption("Microsoft Word", "docx", ".docx"),
    FormatOption("OpenDocument", "odt", ".odt"),
    FormatOption("EPUB", "epub", ".epub"),
    FormatOption("LaTeX", "latex", ".tex"),
    FormatOption("reStructuredText", "rst", ".rst"),
    FormatOption("Org Mode", "org", ".org"),
    FormatOption("Textile", "textile", ".textile"),
    FormatOption("DocBook", "docbook", ".xml"),
    FormatOption("CSV", "csv", ".csv"),
    FormatOption("TSV", "tsv", ".tsv"),
)


OUTPUT_FORMATS: tuple[FormatOption, ...] = (
    FormatOption("Microsoft Word", "docx", ".docx"),
    FormatOption("PDF", "pdf", ".pdf", "需要可用的 PDF 引擎（如 MiKTeX）"),
    FormatOption("HTML", "html5", ".html"),
    FormatOption("Markdown", "markdown", ".md"),
    FormatOption("GitHub Flavored Markdown", "gfm", ".md"),
    FormatOption("EPUB 3", "epub3", ".epub"),
    FormatOption("PowerPoint", "pptx", ".pptx"),
    FormatOption("OpenDocument", "odt", ".odt"),
    FormatOption("Rich Text Format", "rtf", ".rtf"),
    FormatOption("LaTeX", "latex", ".tex"),
    FormatOption("reStructuredText", "rst", ".rst"),
    FormatOption("纯文本", "plain", ".txt"),
)


def output_path_for(source: Path, output_format: FormatOption) -> Path:
    """Return a non-destructive default output path next to *source*."""

    candidate = source.with_suffix(output_format.extension)
    if candidate != source:
        return candidate

    return source.with_name(f"{source.stem}_converted{output_format.extension}")


def replace_output_extension(path: Path, output_format: FormatOption) -> Path:
    """Update an existing destination to match a newly selected format."""

    return path.with_suffix(output_format.extension)


def build_pandoc_arguments(
    source: Path,
    destination: Path,
    output_format: FormatOption,
    input_format: FormatOption | None = None,
) -> list[str]:
    """Build a shell-free Pandoc argument list.

    Omitting ``--from`` is intentional: Pandoc then infers the reader from the
    input filename extension, matching the behaviour promised by the UI.
    """

    arguments = [str(source)]
    if input_format is not None:
        arguments.extend(("--from", input_format.pandoc_name))
    arguments.extend(
        (
            "--to",
            output_format.pandoc_name,
            "--standalone",
            "--output",
            str(destination),
        )
    )
    return arguments


def matching_filter(options: Iterable[FormatOption]) -> str:
    """Create a QFileDialog filter for the supplied formats."""

    patterns = " ".join(f"*{item.extension}" for item in options)
    return f"支持的文档 ({patterns});;所有文件 (*.*)"


def human_file_size(size: int) -> str:
    """Format a byte count for the selected-file card."""

    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"
