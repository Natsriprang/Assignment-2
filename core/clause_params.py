"""Named parameters inside clause text, such as the caps on damages.

Authoring syntax in a clause sentence:

    ...per day\u27e6ld_cap| but not more than {pct} of the Contract Price\u27e7.

The part between \u27e6 and \u27e7 after the bar is a fragment. It is kept, with the figure filled in, when the
parameter has a value, and removed entirely when the parameter is "no cap". Two forms of the figure exist,
matching the two styles in the template:

    {pct}      ->  5 (five) percent
    {pct_sym}  ->  5% (five percent)

With the default values the resolved text is identical to the original sentence. Resolution is plain code: no
AI is involved, and the words are always generated from the number, so a figure and its words cannot disagree.
"""
import math
import re
from dataclasses import dataclass
from decimal import Decimal

MARK_OPEN, MARK_CLOSE = "\u27e6", "\u27e7"
MARKER = re.compile(MARK_OPEN + r"(\w+)\|(.*?)" + MARK_CLOSE, re.DOTALL)


@dataclass(frozen=True)
class Param:
    key: str
    label: str
    default: float | None
    allow_none: bool = True


PARAMS = {
    "ld_cap": Param("ld_cap", "Cap on delay damages (% of the Contract Price)", 5.0),
    "damages_cap": Param("damages_cap", "Cap on total damages deducted (% of the Contract Price)", 5.0),
}

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def check_percent(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Not a valid percentage: {value!r}")
    if not 0 < value <= 100:
        raise ValueError(f"A percentage must be above 0 and at most 100, got {value}")
    if len(format_number(value).partition(".")[2]) > 2:
        raise ValueError(f"At most two decimal places are supported, got {value}")


def format_number(value):
    """5.0 -> '5', 2.50 -> '2.5', 0.05 -> '0.05'."""
    return format(Decimal(str(value)).normalize(), "f")


def _int_words(n):
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")
    if n == 100:
        return "one hundred"
    raise ValueError(f"Out of range: {n}")


def number_words(value):
    whole, _, fraction = format_number(value).partition(".")
    words = _int_words(int(whole))
    if fraction:
        words += " point " + " ".join(_ONES[int(d)] for d in fraction)
    return words


def percent_phrase(value):
    """'5 (five) percent'"""
    check_percent(value)
    return f"{format_number(value)} ({number_words(value)}) percent"


def percent_phrase_symbol(value):
    """'5% (five percent)'"""
    check_percent(value)
    return f"{format_number(value)}% ({number_words(value)} percent)"


def effective(limits=None):
    """Every parameter's value: the given one, or the default when it is not given."""
    values = {key: p.default for key, p in PARAMS.items()}
    values.update(limits or {})
    for key, value in values.items():
        if key not in PARAMS:
            raise ValueError(f"Unknown parameter '{key}'")
        if value is None and not PARAMS[key].allow_none:
            raise ValueError(f"'{key}' cannot be left without a value")
        if value is not None:
            check_percent(value)
    return values


def resolve_text(text, limits=None):
    values = effective(limits)

    def fill(match):
        key, fragment = match.group(1), match.group(2)
        if key not in PARAMS:
            raise ValueError(f"Unknown parameter '{key}' in clause text")
        value = values[key]
        if value is None:
            return ""
        return fragment.replace("{pct}", percent_phrase(value)).replace("{pct_sym}", percent_phrase_symbol(value))

    return MARKER.sub(fill, text)


def resolve_clause(clause, limits=None):
    """Resolves every parameter in a clause, in place. Used on a freshly built library."""
    clause.plain_paragraphs = [resolve_text(p, limits) for p in clause.plain_paragraphs]
    for item in clause.items:
        item.text = resolve_text(item.text, limits)
        item.lettered = [resolve_text(s, limits) for s in item.lettered]
    for table in clause.tables:
        table["rows"] = [[resolve_text(cell, limits) for cell in row] for row in table["rows"]]
    clause.table_rows = [tuple(resolve_text(cell, limits) for cell in row) for row in clause.table_rows]


def limits_of(term_sheet):
    """The caps chosen on the term sheet, with defaults for anything not chosen. Tolerates a term sheet
    object saved by an older version of the app, which has no `limits` attribute."""
    chosen = getattr(term_sheet, "limits", None) or {}
    return effective({k: v for k, v in chosen.items() if k in PARAMS})


def limits_text(limits):
    parts = []
    for key, p in PARAMS.items():
        value = limits.get(key, p.default)
        parts.append(f"{p.label.split(' (')[0].lower()} {'none' if value is None else format_number(value) + '%'}")
    return "; ".join(parts)
