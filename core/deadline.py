"""How the start and completion of the Works are set: by calendar dates, or by a number of days after signing. Like VAT,
there is no default; until one is chosen the clause keeps its blanks. Pure code."""
import re

from core.fill import looks_like_date

MODES = ("calendar", "period")

_ANCHOR = (r"(?:signing|signature|execution|contract date|agreement date|effective date|"
           r"date of (?:this |the )?(?:agreement|contract))(?:\s+date)?(?:\s+of\s+(?:this\s+|the\s+)?(?:agreement|contract))?")
_PERIOD = re.compile(rf"^(?:within\s+)?(\d{{1,3}})\s*(?:calendar\s+)?days?(?:\s+(?:after|from|of)\s+(?:the\s+)?{_ANCHOR})?$", re.I)


def period_days(text):
    """N from '14 days', 'within 14 days' or '14 days after signing'; None for anything else. Working days, months and a
    period counted from something other than signing (commencement, a notice) are not read: they would change meaning."""
    value = _PERIOD.match(" ".join((text or "").replace(",", " ").split()).rstrip(".;"))
    n = int(value.group(1)) if value else 0
    return n if 0 < n < 1000 else None


def is_days(text):
    t = (text or "").strip()
    return t.isdigit() and 0 < int(t) < 1000


def deadline_choice(term_sheet):
    mode = getattr(term_sheet, "deadline_mode", "")
    return mode if mode in MODES else ""


def apply_import(ts):
    """Sets the mode (and the days) from what a term sheet said, when it can be read; otherwise leaves the mode unchosen."""
    start, completion = (ts.start_date or "").strip(), (ts.completion_date or "").strip()
    ts.deadline_mode, ts.start_days, ts.completion_days = "", "", ""
    if not (start and completion):
        return ts
    if looks_like_date(start) and looks_like_date(completion):
        ts.deadline_mode = "calendar"
    elif period_days(start) and period_days(completion):
        ts.deadline_mode, ts.start_days, ts.completion_days = "period", str(period_days(start)), str(period_days(completion))
    return ts


def deadline_warning(term_sheet):
    """Text of the red notice while the deadline is not chosen; None once it is."""
    if deadline_choice(term_sheet):
        return None
    said = [f"{label} \u201c{' '.join(v.split())}\u201d" for label, v in
            (("start", getattr(term_sheet, "start_date", "") or ""), ("completion", getattr(term_sheet, "completion_date", "") or "")) if v.strip()]
    heard = (f" The term sheet says {' and '.join(said)}, which cannot be read as calendar dates or as a number of days "
             "after signing.") if said else ""
    return (f"The completion deadline is not chosen.{heard} Choose calendar dates or a period from signing, and fill it in. "
            "Until then the deadline clause keeps its blanks.")
