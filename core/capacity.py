"""Installed capacity with its unit (kWp or MW), and exact conversion between them. The contract header uses
MW and clause 1 uses kWp, so the unit has to be known rather than guessed."""
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


def capacity_in(term_sheet, unit):
    """The capacity as plain text in `unit` ('kWp' or 'MW'), or None when it cannot be read."""
    value, own_unit = parse_capacity(getattr(term_sheet, "capacity", ""), getattr(term_sheet, "capacity_unit", "kWp"))
    if value is None:
        return None
    if own_unit == unit:
        return format_number(value)
    return format_number(value / 1000 if unit == "MW" else value * 1000)
