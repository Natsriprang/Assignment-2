"""Reference library: clause-level texts from the author's own contracts and a public form, loaded
from data/reference/*.json. Pure Python, no AI. The AI steps select from the catalogue and quote
the full text; every use is traced back to a source label so it can be shown as a footnote."""
import json
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"

SOURCE_LABELS = {
    "th_gov_construction_contract": "Thai government form",
    "ca_long_version": "CA (long version)",
    "epc_subcontract_agreement": "EPC subcontract",
}


@dataclass(frozen=True)
class Reference:
    id: str
    doc_id: str
    source: str
    article: str
    title: str
    category: str
    our_clause: str | None
    gap: bool
    quality_notes: tuple
    text: str
    rights_note: str
    governing_law: str
    machine_translated: bool
    caveats: tuple

    @property
    def flags(self):
        flags = []
        if "not a public document" in self.rights_note.lower():
            flags.append("not public")
        if self.machine_translated:
            flags.append("machine translation")
        return flags

    @property
    def label(self):
        where = "notes on the form" if self.article == "notes" else f"clause {self.article}"
        return f"{self.source}, {where}: {self.title}"

    def excerpt(self, limit=110):
        line = " ".join(self.text.split())
        return line if len(line) <= limit else line[:limit].rstrip() + "..."


def load_references(directory=DATA_DIR):
    """All reference entries by id, in file order. Form headers (preambles) are left out."""
    directory = Path(directory)
    files = sorted(directory.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No reference files found in {directory}")
    refs = {}
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        source = SOURCE_LABELS.get(doc["id"], doc["title"][:40])
        for c in doc["clauses"]:
            if c["category"] == "preamble":
                continue
            refs[c["id"]] = Reference(
                id=c["id"], doc_id=doc["id"], source=source, article=c["article"], title=c["title"],
                category=c["category"], our_clause=c.get("our_clause"), gap=bool(c["gap"]),
                quality_notes=tuple(c["quality_notes"]), text=c["text"], rights_note=doc.get("rights_note", ""),
                governing_law=doc.get("governing_law", ""), machine_translated="translation" in doc,
                caveats=tuple(doc.get("differences_from_target", [])))
    return refs


def catalogue_lines(refs):
    """One line per entry: enough for a model to judge relevance without reading every clause."""
    lines = []
    for r in refs.values():
        first = " ".join(r.text.split("\n")[0].split())[:120]
        note = f" | notes: {r.quality_notes[0][:90]}" if r.quality_notes else ""
        lines.append(f"- {r.id} | {r.source} | {r.title} | {r.category} | starts: {first}{note}")
    return "\n".join(lines)
