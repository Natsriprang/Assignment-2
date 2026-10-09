"""The internal approval memo that goes with the contract, in the style of the company's sign-off form: To, Subject, Documents proposed for signing,
Urgency, Details, a request for consideration, and two sign-off boxes (the proposer and the Legal Department). Pure code, no AI: every fact in it is
written from the term sheet and the draft, so it cannot be wrong, and what the term sheet does not say stays as [*] for the person to fill in.
It is an internal paper for the person who approves the signing. It is not part of the contract."""
from datetime import date

from core.capacity import capacity_parts
from core.exsum import fact_rows
from core.header import PLACEHOLDER, TITLE

FORM_TITLE = "Approval Form for Signing a Document: Memorandum, Agreement or Contract Binding the Company to an External Party"
CLOSING = "Submitted for your consideration."
FOOTER = "Internal approval memo. It is not part of the contract."
PROPOSER_HEADING = "Proposed by"
LEGAL_HEADING = "Reviewed by the Legal Department"
LEGAL_UNIT = "Legal Department"


def _v(value):
    value = " ".join(str(value or "").split())
    return value if value else PLACEHOLDER


def long_date(day):
    return f"{day.day} {day:%B %Y}"


def _subject(ts):
    capacity, unit = capacity_parts(ts)
    size = f", capacity {capacity} {unit}" if capacity else ""
    return (f"Approval to sign the {TITLE} for the photovoltaic solar power rooftop facility, "
            f"{_v(getattr(ts, 'project_name', ''))}{size}, between {_v(getattr(ts, 'owner_name', ''))} (the Owner) "
            f"and {_v(getattr(ts, 'contractor_name', ''))} (the Contractor)")


def build_memo(ts, library=None, today=None):
    """The memo as a dict: date, `fields` [(label, text)] for the table at the top, `details` [paragraph], `key_terms` [(label, value)] for the
    list under it, `closing`, and the two sign-off boxes. `library` is the draft as it stands (the caps are read from it); without it they come
    from the term sheet."""
    subject = _subject(ts)
    capacity, unit = capacity_parts(ts)
    size = f", capacity {capacity} {unit}" if capacity else ""
    document = (f"1. {TITLE} for the photovoltaic solar power rooftop facility, {_v(getattr(ts, 'project_name', ''))}{size}, "
                "1 copy (original)")
    details = [f"Please consider approving the signing of the following document: the {TITLE} for the photovoltaic solar power rooftop facility, "
               f"{_v(getattr(ts, 'project_name', ''))}{size}, between {_v(getattr(ts, 'owner_name', ''))} (the Owner) "
               f"and {_v(getattr(ts, 'contractor_name', ''))} (the Contractor)."]
    return {
        "title": FORM_TITLE,
        "date": long_date(today or date.today()),
        "fields": [("To", PLACEHOLDER), ("Subject", subject), ("Documents proposed for signing", document), ("Urgency", PLACEHOLDER)],
        "details_label": "Details",
        "details": details,
        "key_terms_label": "Key terms of the contract:",
        "key_terms": fact_rows(ts, library),
        "closing": CLOSING,
        "boxes": [
            {"heading": PROPOSER_HEADING, "name": "(                                        )", "line": "Position / Department:"},
            {"heading": LEGAL_HEADING, "name": "(                                        )", "line": LEGAL_UNIT},
        ],
        "footer": FOOTER,
    }
