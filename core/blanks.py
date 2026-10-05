"""The blanks ([*]) still in the draft, with where each one is. Pure code."""
import re
from dataclasses import dataclass

BLANK = "[*]"


@dataclass
class Blank:
    where: str
    context: str


def _contexts(text, where):
    flat = " ".join(text.split())
    found = []
    for m in re.finditer(re.escape(BLANK), flat):
        a, b = max(0, m.start() - 45), min(len(flat), m.end() + 35)
        found.append(Blank(where, ("\u2026" if a else "") + flat[a:b] + ("\u2026" if b < len(flat) else "")))
    return found


def find_blanks(header_lines, rendered, signature=None):
    """`header_lines` are (style, text) lines of the contract header; `rendered` is renumber_and_render's output;
    `signature` is the signature block, if the draft has one."""
    blanks = []
    for _, text in header_lines:
        blanks += _contexts(text, "Contract header")
    for number, clause, lines in rendered:
        where = f"{number}. {clause.title}"
        for paragraph in clause.plain_paragraphs:
            blanks += _contexts(paragraph, where)
        for line in lines:
            blanks += _contexts(line, where)
        for table in clause.tables:
            for r, row in enumerate(table["rows"], start=1):
                if any(BLANK in cell for cell in row):
                    blanks.append(Blank(f"{where} (table, row {r})", " | ".join(cell for cell in row)))
    if signature:
        from core.signatures import signature_texts
        for text in signature_texts(signature):
            blanks += _contexts(text, "Signature block")
    return blanks
