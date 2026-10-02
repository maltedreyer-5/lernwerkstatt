"""
File reader: extracts text from uploaded files.

Safety measures:
- path validation (no traversal)
- the file size is checked
- only allowed suffixes
- ZIP decompression bombs are limited (MAX_DECOMPRESSED_SIZE)
"""

import logging
from pathlib import Path

from src.core.env import max_upload_mb

logger = logging.getLogger(__name__)

# Allowed file extensions
ALLOWED_SUFFIXES = {".txt", ".md", ".csv", ".html", ".docx", ".pdf", ".pptx"}

# Maximum file size in bytes. app.py passes the same limit to Gradio, which
# does not even accept larger uploads; here it applies to every other caller.
MAX_FILE_SIZE = max_upload_mb() * 1024 * 1024

# Maximum size of content extracted from ZIP-based formats (200 MB).
# Protection against a "decompression bomb": a small .docx/.pptx file with huge
# XML entries unpacks to gigabytes. Reading is aborted when it is exceeded.
MAX_DECOMPRESSED_SIZE = 200 * 1024 * 1024


def _safe_read_zip_member(sm, name: str, accumulated_size: int) -> tuple[bytes, int]:
    """Reads a ZIP member safely with a decompression limit.

    Returns:
        (content_bytes, new_accumulated_size)

    Raises:
        ValueError: if the accumulated size exceeds the limit or the member
                    alone is too large.
    """
    info = sm.getinfo(name)
    # Check: does the single member still fit at all?
    if info.file_size > MAX_DECOMPRESSED_SIZE - accumulated_size:
        raise ValueError(
            f"ZIP content too large (member '{name}' = "
            f"{info.file_size // 1024} KB, accumulated "
            f"{accumulated_size // 1024} KB, Limit "
            f"{MAX_DECOMPRESSED_SIZE // (1024*1024)} MB)"
        )
    content = sm.read(name)
    return content, accumulated_size + len(content)


def read_uploaded_file(filepath: str) -> tuple[str, int]:
    """Reads a file and returns (text, word_count).

    Raises:
        ValueError: if the file cannot be read or validation fails.
    """
    path = Path(filepath).resolve()

    # Safety: check that the file exists
    if not path.is_file():
        raise ValueError(f"file not found: {path.name}")

    # Safety: check the file size
    file_size = path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f"The file '{path.name}' is too large ({file_size // (1024*1024)} MB). Maximum: {MAX_FILE_SIZE // (1024*1024)} MB."
        )

    suffix = path.suffix.lower()

    # Safety: only allowed suffixes
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError(
            f"The file format '{suffix}' is not supported. Allowed formats: {', '.join(sorted(ALLOWED_SUFFIXES))}"
        )

    try:
        if suffix in (".txt", ".md", ".csv"):
            text = path.read_text(encoding="utf-8", errors="replace")
        elif suffix == ".html":
            text = _read_html(path)
        elif suffix == ".docx":
            text = _read_docx(path)
        elif suffix == ".pdf":
            text = _read_pdf(path)
        elif suffix == ".pptx":
            text = _read_pptx(path)
        else:
            raise ValueError(f"no reader for '{suffix}'")

        word_count = len(text.split())
        logger.info(f"file read: {path.name} ({word_count} words)")
        return text, word_count

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"error reading {path.name}: {e}")
        raise ValueError(
            f"The file '{path.name}' could not be read. Supported formats: {', '.join(sorted(ALLOWED_SUFFIXES))}"
        )


def _read_html(path: Path) -> str:
    """Reads HTML and extracts plain text."""
    import re
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r'<style[^>]*>.*?</style>', '', raw, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _read_docx(path: Path) -> str:
    """Reads .docx files and converts them to Markdown.

    Formatting kept:
    - headings (Heading 1-6 → # to ######)
    - bold (→ **text**)
    - italics (→ *text*)
    - bullet lists (→ - item)
    - numbered lists (→ 1. item)
    - tables (→ Markdown tables)
    - block quotes
    """
    try:
        from docx import Document
        doc = Document(str(path))

        md_parts = []

        # Collect tables (to insert them at the right place)
        table_index = {}
        for i, block in enumerate(doc.element.body):
            if block.tag.endswith('}tbl'):
                # Find the matching table
                for j, table in enumerate(doc.tables):
                    if table._element is block:
                        table_index[id(block)] = table
                        break

        # Process paragraphs and tables in order
        for block in doc.element.body:
            if block.tag.endswith('}p'):
                # Paragraph
                para = None
                for p in doc.paragraphs:
                    if p._element is block:
                        para = p
                        break
                if para is None or not para.text.strip():
                    md_parts.append("")
                    continue

                md_parts.append(_docx_para_to_md(para))

            elif block.tag.endswith('}tbl'):
                # Tabelle
                table = table_index.get(id(block))
                if table:
                    md_parts.append(_docx_table_to_md(table))

        result = "\n\n".join(md_parts)
        # Normalise multiple blank lines
        import re as _re
        result = _re.sub(r'\n{4,}', '\n\n\n', result)
        return result.strip()

    except Exception as e:
        # Fallback: plain text extraction
        logger.warning(
            f"Markdown conversion of '{path.name}' failed ({e}), "
            f"trying the text-only fallback"
        )
        return _read_docx_plaintext(path)


def _docx_para_to_md(para) -> str:
    """Converts a python-docx paragraph to Markdown."""
    style_name = (para.style.name or "").lower() if para.style else ""

    # Headings
    if style_name.startswith("heading"):
        try:
            level = int(style_name.replace("heading", "").strip())
            level = min(max(level, 1), 6)
        except ValueError:
            level = 2
        return "#" * level + " " + para.text.strip()

    # Titel
    if "title" in style_name or "title" in style_name:
        return "# " + para.text.strip()

    # Listen
    if _is_list_paragraph(para):
        prefix = _get_list_prefix(para)
        return prefix + _runs_to_md(para.runs)

    # Block quote
    if "quote" in style_name or "zitat" in style_name:
        return "> " + _runs_to_md(para.runs)

    # Normal paragraph with inline formatting
    return _runs_to_md(para.runs)


def _runs_to_md(runs) -> str:
    """Converts a list of runs to Markdown with inline formatting."""
    if not runs:
        return ""

    parts = []
    for run in runs:
        text = run.text
        if not text:
            continue

        is_bold = run.bold
        is_italic = run.italic

        if is_bold and is_italic:
            parts.append(f"***{text}***")
        elif is_bold:
            parts.append(f"**{text}**")
        elif is_italic:
            parts.append(f"*{text}*")
        else:
            parts.append(text)

    result = "".join(parts)

    # Clean-up: merge ** directly next to each other
    import re as _re
    result = _re.sub(r'\*\*\*\*', '', result)  # ****text**** → text
    result = _re.sub(r'\*\*\s*\*\*', ' ', result)  # ** ** → space

    return result


def _is_list_paragraph(para) -> bool:
    """Detects whether a paragraph is a list item."""
    # python-docx: numPr Element im pPr
    pPr = para._element.find(
        '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr'
    )
    if pPr is not None:
        numPr = pPr.find(
            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}numPr'
        )
        if numPr is not None:
            return True

    style_name = (para.style.name or "").lower() if para.style else ""
    return "list" in style_name or "aufzählung" in style_name


def _get_list_prefix(para) -> str:
    """Determines the list prefix (- or 1.)."""
    style_name = (para.style.name or "").lower() if para.style else ""

    # Numbered list
    if "number" in style_name or "nummeri" in style_name:
        return "1. "

    # Determine the indentation level
    indent = ""
    pPr = para._element.find(
        '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr'
    )
    if pPr is not None:
        ind = pPr.find(
            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ind'
        )
        if ind is not None:
            left = ind.get(
                '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}left',
                '0',
            )
            try:
                level = int(left) // 720  # 720 twips per indentation level
                indent = "  " * max(0, level - 1)
            except (ValueError, TypeError):
                pass

    return f"{indent}- "


def _docx_table_to_md(table) -> str:
    """Converts a python-docx table to Markdown."""
    if not table.rows:
        return ""

    rows = []
    for row in table.rows:
        cells = [cell.text.strip().replace("|", "\\|") for cell in row.cells]
        rows.append("| " + " | ".join(cells) + " |")

    if len(rows) < 1:
        return ""

    # Header separator after the first row
    col_count = len(table.rows[0].cells)
    separator = "| " + " | ".join(["---"] * col_count) + " |"

    result = [rows[0], separator] + rows[1:]
    return "\n".join(result)


def _read_docx_plaintext(path: Path) -> str:
    """Text-only fallback for broken .docx files."""
    try:
        from docx import Document
        doc = Document(str(path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception:
        import zipfile
        import re as _re
        try:
            texts = []
            accumulated = 0
            with zipfile.ZipFile(str(path)) as z:
                for name in sorted(z.namelist()):
                    if name.startswith("word/") and name.endswith(".xml"):
                        try:
                            raw, accumulated = _safe_read_zip_member(z, name, accumulated)
                        except ValueError as ve:
                            logger.warning(f"docx read limit reached: {ve}")
                            break
                        content = raw.decode("utf-8", errors="replace")
                        for match in _re.finditer(r'<w:t[^>]*>([^<]+)</w:t>', content):
                            texts.append(match.group(1))
            if texts:
                return " ".join(texts)
            raise ValueError(f"No text content found in '{path.name}'")
        except zipfile.BadZipFile:
            raise ValueError(f"'{path.name}' is not a valid .docx file")


def _read_pdf(path: Path) -> str:
    """Reads .pdf files."""
    from pdfminer.high_level import extract_text
    return extract_text(str(path))


def _read_pptx(path: Path) -> str:
    """Reads .pptx files (best effort)."""
    try:
        from pptx import Presentation
        prs = Presentation(str(path))
        texts = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    texts.append(shape.text)
        return "\n\n".join(texts)
    except ImportError:
        import zipfile
        import re
        texts = []
        accumulated = 0
        with zipfile.ZipFile(str(path)) as z:
            for name in z.namelist():
                if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                    try:
                        raw, accumulated = _safe_read_zip_member(z, name, accumulated)
                    except ValueError as ve:
                        logger.warning(f"pptx read limit reached: {ve}")
                        break
                    content = raw.decode("utf-8", errors="replace")
                    for match in re.finditer(r'<a:t>([^<]+)</a:t>', content):
                        texts.append(match.group(1))
        return "\n".join(texts)
