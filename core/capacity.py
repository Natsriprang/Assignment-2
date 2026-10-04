"""Installed capacity with its unit (kWp or MW), kept exactly as the user entered it. The unit is chosen on the
term sheet rather than guessed."""
import re
from decimal import Decimal, InvalidOperation

UNITS = ("kWp", "MW")
_UNIT_WORDS = {"mw": "MW", "mwp": "MW", "kw": "kWp", "kwp": "kWp"}
_UNIT_TOKEN = re.compile(r"[A-Za-z]+")


def format_number(value):
    """Plain decimal text without trailing zeros: 500.00 -> '500', 0.5 -> '0.5'."""
    return format(value.normalize(), "f")


def parse_capacity(text, default_unit="kWp"):
    """(value as Decimal or None, unit). A unit written in the text wins over `default_unit`, so a term sheet
    that says '0.5 MW' is read correctly. The value is None when the text is not a positive number."""
    unit = default_unit if default_unit in UNITS else "kWp"
    text = (text or "").strip()
    for token in _UNIT_TOKEN.findall(text):
        if token.lower() in _UNIT_WORDS:
            unit = _UNIT_WORDS[token.lower()]
            text = text.replace(token, " ")
            break
    number = re.sub(r"[\s,]", "", text)
    try:
        value = Decimal(number)
    except InvalidOperation:
        return None, unit
    return (value if value.is_finite() and value > 0 else None), unit


def capacity_parts(term_sheet):
    """(number as plain text or None, unit), exactly as entered on the term sheet. No unit conversion."""
    value, unit = parse_capacity(getattr(term_sheet, "capacity", ""), getattr(term_sheet, "capacity_unit", "kWp"))
    return (format_number(value) if value is not None else None), unit
