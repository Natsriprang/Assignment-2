"""Rules the term sheet's author wrote as notes beside the fields (column D of the Excel), checked by code where a rule can be
checked exactly: a number of digits, a date that must agree with the contract no., a name that must be a full name. Pure code.
Notes that cannot be checked exactly are not enforced."""
import re
from functools import lru_cache
from pathlib import Path

from core.field_titles import title
from core.fill import date_of

TEMPLATE = Path(__file__).resolve().parent.parent / "data" / "term_sheet_template_EN.xlsx"

_DIGITS = re.compile(r"^\s*(\d+)\s+digits?\s*$", re.IGNORECASE)                       # "13 digits"
_LAST_DIGITS = re.compile(r"last\s+(\d+)\s+digits\s+of\s+the\s+contract\s+no", re.IGNORECASE)   # "...the last 6 digits of the contract no."
_FULL_NAME = re.compile(r"\bfull\s+names?\b", re.IGNORECASE)                                          # "Full name(s), matching ..."


@lru_cache(maxsize=1)
def template_notes():
    """The notes of the template shipped with the app: used until another term sheet has been imported."""
    if not TEMPLATE.exists():
        return {}
    from core.xlsx_parser import parse_xlsx_report
    return dict(parse_xlsx_report(TEMPLATE)[1].notes)


_NAME_SPLIT = re.compile(r"[\n;,&]|\s+and\s+", re.IGNORECASE)


def split_names(value):
    """The names in a signatory field: one per line, or separated by ; , & or "and"."""
    return [n.strip() for n in _NAME_SPLIT.split(value or "") if n.strip()]


def _filled(ts, name):
    return str(getattr(ts, name, "") or "").strip()


def rule_warnings(ts, notes):
    """Values that break a note which says something exact. Each is a sentence naming the field as the page does."""
    if ts is None:
        return []
    out = []
    for name, note in (notes or {}).items():
        value = _filled(ts, name)
        if not value or not note:
            continue
        m = _DIGITS.match(note)
        if m:
            compact = re.sub(r"[\s-]", "", value)
            if not compact.isdigit():
                out.append(f"{title(name)} \u201c{value}\u201d contains characters other than digits, but the term sheet's note says \u201c{note}\u201d.")
            elif len(compact) != int(m.group(1)):
                out.append(f"{title(name)} \u201c{value}\u201d has {len(compact)} digits, but the term sheet's note says \u201c{note}\u201d.")
            continue
        if _FULL_NAME.search(note):
            names = split_names(value)
            single = [n for n in names if len(n.split()) < 2]
            if single:
                one_line = " / ".join(line.strip() for line in value.split("\n") if line.strip())
                shown = ", ".join(f"\u201c{n}\u201d" for n in single)
                if single == names and len(names) == 1:
                    what = f"{title(name)} \u201c{one_line}\u201d looks like a first name only"
                else:
                    what = (f"{title(name)} \u201c{one_line}\u201d: {shown} "
                            f"{'looks like a first name only' if len(single) == 1 else 'look like first names only'}")
                out.append(f"{what}, but the term sheet's note says \u201c{note}\u201d.")
            continue
        m = _LAST_DIGITS.search(note)
        if m and name == "contract_date" and int(m.group(1)) == 6:
            when, number = date_of(value), re.sub(r"\D", "", _filled(ts, "contract_no"))
            if when is None or not number:
                continue
            expected = when.strftime("%d%m%y")
            if number[-6:] != expected:
                out.append(f"{title('contract_date')} \u201c{value}\u201d does not match the last 6 digits of {title('contract_no')} "
                           f"\u201c{_filled(ts, 'contract_no')}\u201d (day, month and year would end in {expected}), "
                           f"but the term sheet's note says \u201c{note}\u201d.")
    return out
