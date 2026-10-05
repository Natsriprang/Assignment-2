"""The "Additional conditions" of the term sheet: changes the user wants to a clause's standard wording, written in the Excel
(one box per clause, "for Legal to review") instead of typed in the chat. They are read by the same AI step as a chat message."""

import re

PREFIX = re.compile(r"additional condition for clause key [a-z_]+ \([^)]*\):\s*", re.IGNORECASE)


def strip_condition_prefix(text):
    """The text without the words that introduce a condition for the AI ("additional condition for clause key force_majeure (Force
    Majeure): ..."). Those words are only a label for the model; the user never wrote them, so they are never shown."""
    return PREFIX.sub("", text or "").strip()


# (clause key, the label of its row in the Excel template and of its box on the Term sheet page)
CONDITION_CLAUSES = [
    ("owner_representations", "Owner's Representations"),
    ("taxation", "Taxation and Statutory Fees"),
    ("personnel_responsibility", "Contractor Personnel Responsibility"),
    ("confidentiality", "Confidentiality and Use of Information"),
    ("suspension", "Suspension of Works"),
    ("inspection", "Inspection of Works"),
    ("drawing_discrepancy", "Discrepancy in Work Drawings"),
    ("termination", "Breach and Termination"),
    ("force_majeure", "Force Majeure"),
    ("miscellaneous", "Miscellaneous"),
]
LABELS = dict(CONDITION_CLAUSES)


def conditions_of(term_sheet):
    """{clause key: text} for the boxes that have text, in the order of the template. Older term sheet objects have none."""
    held = getattr(term_sheet, "additional_conditions", None) or {}
    return {key: held[key].strip() for key, _ in CONDITION_CLAUSES if (held.get(key) or "").strip()}


def condition_lines(term_sheet):
    """One line per condition for the text the AI reads. Lines and spaces are collapsed so that a quote the AI copies from it can
    be found again whatever the layout of the cell."""
    return [f"additional condition for clause key {key} ({LABELS[key]}): {' '.join(text.split())}"
            for key, text in conditions_of(term_sheet).items()]
