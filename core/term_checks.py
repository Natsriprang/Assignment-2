"""Checks of the term sheet that code can do exactly: blanks, and values that contradict each other. Pure code. The AI check
(ai/termcheck.py) is only for what code cannot judge."""
import re
from decimal import Decimal

from core.deadline import deadline_choice
from core.field_titles import BLANK_CHECKED, DASH, title
from core.fill import format_price, parse_decimal, date_of
from core.price_words import words_to_number
from core.term_sheet_fields import signing_place


def blank_fields(ts):
    """Titles of the fields (and installment cells) that are empty, in the order of the page."""
    if ts is None:
        return []
    blanks = []
    for name in BLANK_CHECKED:
        if name == "signing_place_choice":
            empty = not signing_place(ts)
        else:
            empty = not str(getattr(ts, name, "") or "").strip()
        if empty:
            blanks.append(title(name))
    installments = list(getattr(ts, "installments", []) or [])
    if not installments:
        blanks.append(title("installments"))
    for i, inst in enumerate(installments, start=1):
        if not (inst.percent or "").strip():
            blanks.append(f"Installment {(inst.number or '').strip() or i}: %")
    return blanks


def percent_warnings(ts):
    warnings, percents = [], []
    for inst in ts.installments:
        if not inst.percent:
            continue
        try:
            percents.append(float(inst.percent.replace("%", "").strip()))
        except ValueError:
            warnings.append(f"Installment {inst.number}: '{inst.percent}' is not a number.")
    if percents and abs(sum(percents) - 100) > 0.01:
        warnings.append(f"Installment percentages add up to {sum(percents):g}%, not 100%.")
    return warnings


def price_warnings(ts):
    """The price in words against the price in digits. Words that cannot be read completely are not judged."""
    digits = parse_decimal(re.sub(r"(?i)\b(thb|baht)\b", "", getattr(ts, "contract_price_number", "") or ""))
    words = (getattr(ts, "contract_price_words", "") or "").strip()
    read = words_to_number(words)
    if digits is None or read is None or abs(digits - read) < Decimal("0.005"):
        return []
    return [f"{title('contract_price_words')} \u201c{words}\u201d reads as {format_price(read)}, but "
            f"{title('contract_price_number')} is {format_price(digits)}."]


def date_warnings(ts):
    if deadline_choice(ts) != "calendar":
        return []
    start, completion = (getattr(ts, "start_date", "") or "").strip(), (getattr(ts, "completion_date", "") or "").strip()
    a, b = date_of(start), date_of(completion)
    if a and b and b < a:
        return [f"{title('completion_date')} ({completion}) is before {title('start_date')} ({start})."]
    return []


def contradictions(ts):
    """Values that contradict each other. Each is a sentence naming the fields as the page does."""
    if ts is None:
        return []
    return price_warnings(ts) + percent_warnings(ts) + date_warnings(ts)
