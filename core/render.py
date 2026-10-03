"""Render a clause list to a .docx."""
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

from core.renumber import renumber_and_render


def _add_table(doc, table_data):
    t = doc.add_table(rows=1, cols=len(table_data["headers"]))
    t.style = "Light Grid Accent 1"
    for cell, text in zip(t.rows[0].cells, table_data["headers"]):
        cell.text = text
        cell.paragraphs[0].runs[0].bold = True
    for row in table_data["rows"]:
        cells = t.add_row().cells
        for cell, text in zip(cells, row):
            cell.text = text
    doc.add_paragraph()


def render_docx(clauses, out_path):
    rendered = renumber_and_render(clauses)

    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("Construction and Installation Service Agreement")
    r.bold = True
    r.font.size = Pt(14)
    doc.add_paragraph()

    for number, clause, item_lines in rendered:
        h = doc.add_paragraph()
        r = h.add_run(f"{number}.\t{clause.title}")
        r.bold = True

        for p in clause.plain_paragraphs:
            doc.add_paragraph(p)

        for i, line in enumerate(item_lines):
            p = doc.add_paragraph()
            if line.startswith("    "):
                p.paragraph_format.left_indent = Cm(1.0)
                p.add_run(line.strip())
            else:
                p.paragraph_format.left_indent = Cm(0.5)
                p.add_run(line)
            if i == 0 and clause.tables:
                for table_data in clause.tables:
                    _add_table(doc, table_data)

        if not item_lines:
            for table_data in clause.tables:
                _add_table(doc, table_data)

    doc.save(out_path)
    return rendered