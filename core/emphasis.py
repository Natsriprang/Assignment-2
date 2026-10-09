"""What is written in bold in the contract text: a defined term in quotation marks (the "Agreement", the "date of this Agreement"), with its quotation
marks, and, in the paragraphs that introduce the parties, each party's name and registration number. Pure code; the Word file and the preview both
cut their text with `segments`, so they always agree."""
import re

TERM = r"“[^”]*”"


def party_names(ts):
    """The party names and registration numbers of the term sheet that are written in bold in the header, longest first."""
    values = [" ".join(str(getattr(ts, f, "") or "").split()) for f in ("owner_name", "owner_reg_no", "contractor_name", "contractor_reg_no")]
    return sorted({v for v in values if v}, key=len, reverse=True)


def segments(text, names=()):
    """[(piece, bold)] for `text`: the pieces put together give the text again. `names` are the strings to write in bold wherever they appear."""
    parts = [re.escape(n) for n in names if n] + [TERM]
    out, last = [], 0
    for m in re.finditer("|".join(parts), text):
        if m.start() > last:
            out.append((text[last:m.start()], False))
        out.append((m.group(0), True))
        last = m.end()
    if last < len(text):
        out.append((text[last:], False))
    return out or [(text, False)]
