"""
Word exporter: creates .docx files with a plain, uniform layout.

Supports: headings, running text, lists, tables, code blocks, block quotes,
inline formatting (bold, italics, code).
"""

import re
import tempfile
from datetime import datetime
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.oxml.ns import qn

from src.unit import i18n

# The product name in the provenance line. Deliberately not APP_TITLE: that
# names an installation, this names the software that produced the file.
PRODUCT = "LernWerkstatt"


def export_to_docx(
    markdown_text: str,
    title: str = "Dokument",
    footer_info: dict | None = None,
    language: str = "de",
) -> str:
    """Converts Markdown text into a .docx.

    Args:
        markdown_text: the Markdown-formatted text.
        title: document title for header and file name.
        footer_info: optional provenance information,
            e.g. {"models": ["model-a", "model-b"]}.
        language: language of the unit; determines the texts of the
            provenance note.

    Returns:
        Path to the file created.
    """
    doc = Document()

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    # Default font
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Arial"
    font.size = Pt(11)
    font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    style.paragraph_format.space_after = Pt(6)
    style.paragraph_format.line_spacing = 1.15

    # Headings
    for level, size in [(1, 16), (2, 14), (3, 12)]:
        h_style = doc.styles[f"Heading {level}"]
        h_font = h_style.font
        h_font.name = "Arial"
        h_font.size = Pt(size)
        h_font.bold = True
        h_font.color.rgb = RGBColor(0x00, 0x33, 0x66)
        h_style.paragraph_format.space_before = Pt(12)
        h_style.paragraph_format.space_after = Pt(6)

    # Header
    header = doc.sections[0].header
    header_para = header.paragraphs[0]
    header_para.text = title
    header_para.style.font.size = Pt(8)
    header_para.style.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    # Convert Markdown
    _markdown_to_docx(doc, markdown_text)

    # Herkunfts-Footer
    _add_provenance_footer(doc, footer_info, i18n.table_(language))

    # Save
    safe_title = re.sub(r'[^\w\s-]', '', title)[:50].strip().replace(' ', '_')
    if not safe_title:
        safe_title = "Dokument"
    tmp = tempfile.NamedTemporaryFile(
        suffix=".docx", prefix=f"{safe_title}_", delete=False
    )
    tmp.close()
    doc.save(tmp.name)
    return tmp.name


def _add_provenance_footer(doc, info: dict | None, T: dict[str, str]):
    """Adds a provenance footer at the end of the document."""
    # Separator line
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(18)
    run = para.add_run("\u2500" * 60)
    run.font.color.rgb = RGBColor(0xBB, 0xBB, 0xBB)
    run.font.size = Pt(8)

    # ISO date: readable in every output language without translation.
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    color = RGBColor(0x88, 0x88, 0x88)
    size = Pt(8)

    # Line 1: tool + date
    p1 = doc.add_paragraph()
    p1.paragraph_format.space_after = Pt(0)
    r1 = p1.add_run(f"{T['created_with']} {PRODUCT} \u2014 {now}")
    r1.font.size = size
    r1.font.color.rgb = color

    # Line 2: models
    if info and info.get("models"):
        p2 = doc.add_paragraph()
        p2.paragraph_format.space_after = Pt(0)
        r2 = p2.add_run(f"{T['models']}: {', '.join(info['models'])}")
        r2.font.size = size
        r2.font.color.rgb = color

    # Page footer
    footer = doc.sections[0].footer
    footer_para = footer.paragraphs[0]
    footer_para.text = f"{T['created_with']} {PRODUCT}"
    if footer_para.runs:
        footer_para.runs[0].font.size = Pt(8)
        footer_para.runs[0].font.color.rgb = RGBColor(0x99, 0x99, 0x99)


def _strip_html(text: str) -> str:
    """Removes inline HTML tags such as <b>, <i>, <code>.

    Used for <summary> contents, which may contain <b> tags but should
    appear as plain-text headings in the DOCX.
    """
    text = re.sub(r"</?(?:b|i|em|strong|code)>", "", text)
    return text.strip()


def _markdown_to_docx(doc: Document, text: str):
    """Markdown to docx with tables, code blocks, block quotes.

    Also recognises:
    - numbered headings ("1. Key message")
    - short standalone lines as subheadings
    - XML tags and LLM artefacts are cleaned up
    """
    # Pre-Cleaning: XML-Tags, Meta-Kommentare, Prompt-Fragmente
    text = re.sub(r'</?(?:abschnitt|quellmaterial|aktueller_text|'
                  r'bisheriger_text|aktueller_abschnitt|uebergang)>', '', text)
    text = re.sub(
        r'\[(?:Hinweis|Anmerkung|Keine Angabe|Im Rohmaterial)[^\]]{0,200}\]',
        '', text,
    )
    text = re.sub(r'\[M\d{1,3}(?::\s*[^\]]+)?\]\s*', '', text)
    text = re.sub(r'\[\d{1,3}\]\s*', '', text)

    # <details>/<summary> tags (collapsible sections in HTML/Markdown) do not
    # exist in DOCX — <summary> is
    # converted to a ### heading and the <details> wrappers are removed.
    text = re.sub(
        r'<summary>(.*?)</summary>',
        lambda m: f"### {_strip_html(m.group(1))}",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r'</?details>', '', text)

    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Code-Block (```)
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            _add_code_block(doc, "\n".join(code_lines))
            i += 1  # Skip closing ```
            continue

        # Tabelle (| ... | ... |)
        if stripped.startswith("|") and "|" in stripped[1:]:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            _add_table(doc, table_lines)
            continue

        # Markdown headings (# to ####)
        if stripped.startswith("#### "):
            doc.add_heading(stripped[5:], level=4)
        elif stripped.startswith("### "):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith("## "):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith("# "):
            doc.add_heading(stripped[2:], level=1)

        # Block quote
        elif stripped.startswith("> "):
            _add_blockquote(doc, stripped[2:])

        # Bullet lists
        elif stripped.startswith("- ") or stripped.startswith("* "):
            para = doc.add_paragraph(style="List Bullet")
            _add_formatted_text(para, stripped[2:])

        # Numbered headings vs. numbered lists
        elif re.match(r'^\d+\.\s', stripped):
            content = re.sub(r'^\d+\.\s', '', stripped)
            if _is_numbered_heading(stripped, lines, i):
                # Numbered heading → Heading 3
                doc.add_heading(stripped, level=3)
            else:
                # Numbered list
                para = doc.add_paragraph(style="List Number")
                _add_formatted_text(para, content)

        # Horizontale Linie
        elif stripped in ("---", "***", "___"):
            para = doc.add_paragraph()
            para.paragraph_format.space_before = Pt(6)
            para.paragraph_format.space_after = Pt(6)
            run = para.add_run("\u2500" * 60)
            run.font.color.rgb = RGBColor(0xCC, 0xCC, 0xCC)
            run.font.size = Pt(8)

        # Blank line
        elif stripped == "":
            pass

        # Short line that could be a subheading
        elif _is_subheading_line(stripped, lines, i):
            doc.add_heading(stripped, level=4)

        # Normaler Text
        else:
            para = doc.add_paragraph()
            _add_formatted_text(para, stripped)

        i += 1


def _is_numbered_heading(line: str, lines: list, index: int) -> bool:
    """Detects whether a numbered line is a heading.

    Heuristic:
    - short (< 80 characters)
    - an upper-case letter follows the number
    - the next non-empty line is longer (= running text follows)
    - does not end with punctuation such as . , ;
    """
    if len(line) > 80:
        return False

    # An upper-case letter must follow the number
    content = re.sub(r'^\d+\.\s', '', line)
    if not content or not content[0].isupper():
        return False

    # Ends with punctuation → more likely a list item
    if line.rstrip().endswith((".","," , ";", ")")):
        return False

    # Check the next non-empty line
    for j in range(index + 1, min(index + 3, len(lines))):
        next_line = lines[j].strip()
        if next_line:
            # If the next line is numbered as well → list context
            if re.match(r'^\d+\.\s', next_line):
                return False
            # If the next line is longer → heading before running text
            if len(next_line) > len(line):
                return True
            break

    return True  # when in doubt: heading


def _is_subheading_line(line: str, lines: list, index: int) -> bool:
    """Detects short standalone lines that should be subheadings.

    Criteria:
    - short (< 60 characters)
    - starts with an upper-case letter
    - does NOT end with . , ; )
    - not in brackets
    - blank line before or start of the document
    - a longer line after it (running text follows)
    """
    if len(line) > 60 or len(line) < 3:
        return False

    if not line[0].isupper():
        return False

    if line.rstrip().endswith((".", ",", ";", ")", ":")):
        return False

    if line.startswith(("[", "(", "•", "-", "*")):
        return False

    # Must come after a blank line or at the start
    has_blank_before = (index == 0)
    if index > 0:
        prev = lines[index - 1].strip()
        has_blank_before = (prev == "")

    if not has_blank_before:
        return False

    # A longer line after it?
    for j in range(index + 1, min(index + 3, len(lines))):
        next_line = lines[j].strip()
        if next_line:
            return len(next_line) > len(line) + 10
    return False


def _add_code_block(doc, code: str):
    """Inserts a formatted code block."""
    para = doc.add_paragraph()
    para.paragraph_format.space_before = Pt(6)
    para.paragraph_format.space_after = Pt(6)
    # Grey background via shading
    shading = para.paragraph_format.element.get_or_add_pPr()
    shd = shading.makeelement(qn("w:shd"), {
        qn("w:val"): "clear",
        qn("w:color"): "auto",
        qn("w:fill"): "F2F2F2",
    })
    shading.append(shd)

    run = para.add_run(code)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)


def _add_blockquote(doc, text: str):
    """Inserts a block quote with a left margin."""
    para = doc.add_paragraph()
    para.paragraph_format.left_indent = Cm(1.0)
    pf = para.paragraph_format.element.get_or_add_pPr()
    bdr = pf.makeelement(qn("w:pBdr"), {})
    left = bdr.makeelement(qn("w:left"), {
        qn("w:val"): "single",
        qn("w:sz"): "12",
        qn("w:space"): "4",
        qn("w:color"): "999999",
    })
    bdr.append(left)
    pf.append(bdr)
    _add_formatted_text(para, text)


def _add_table(doc, lines: list[str]):
    """Converts Markdown table rows into a Word table."""
    # Parse rows
    rows_raw = []
    separator_idx = -1
    for idx, line in enumerate(lines):
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Recognise the separator row (--- | --- | ---)
        if all(re.match(r'^[-:]+$', c) for c in cells):
            separator_idx = idx
            continue
        rows_raw.append(cells)

    if not rows_raw:
        return

    num_cols = max(len(r) for r in rows_raw)
    # Normalise all rows to the same number of columns
    for r in rows_raw:
        while len(r) < num_cols:
            r.append("")

    table = doc.add_table(rows=len(rows_raw), cols=num_cols)
    table.style = "Table Grid"

    for r_idx, row_data in enumerate(rows_raw):
        for c_idx, cell_text in enumerate(row_data):
            cell = table.cell(r_idx, c_idx)
            cell.text = ""
            para = cell.paragraphs[0]
            para.paragraph_format.space_after = Pt(2)
            _add_formatted_text(para, cell_text)

            # Header row bold
            if r_idx == 0:
                for run in para.runs:
                    run.bold = True

    # Table font size
    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(10)
                    run.font.name = "Arial"


def _add_formatted_text(paragraph, text: str):
    """Text with inline formatting: **bold**, *italics*, `code`."""
    # Regex: **fett**, *kursiv*, `code`
    parts = re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)', text)
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("*") and part.endswith("*"):
            run = paragraph.add_run(part[1:-1])
            run.italic = True
        elif part.startswith("`") and part.endswith("`"):
            run = paragraph.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(0x88, 0x00, 0x33)
        else:
            paragraph.add_run(part)
