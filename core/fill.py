"""Values taken from the term sheet and written into the clause text. Pure code, no AI.

Every fill writes only what the term sheet really holds; a value it lacks leaves the template's [*] in place. A [*]
is replaced by position (the n-th blank of a sentence), and only when the sentence has exactly the blanks the rule
expects, so an edited template cannot be filled in the wrong place."""
import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from core.capacity import capacity_parts, format_number
from core.clause_params import int_words
from core.vat import CLAUSE_PHRASE, vat_choice

BLANK = "[*]"
TEMPLATE_ROWS = 5                                   # rows of the payment table in the template

_DATE_FORMATS = ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d",
                 "%Y-%m-%d %H:%M:%S", "%d %B, %Y", "%Y/%m/%d")


def _text(ts, name):
    return " ".join((getattr(ts, name, "") or "").split())


def parse_decimal(text):
    """A positive number from text such as '10,000,000' or '10000000.50', or None."""
    try:
        value = Decimal(re.sub(r"[,\s]", "", text or ""))
    except InvalidOperation:
        return None
    return value if value.is_finite() and value > 0 else None


def format_price(value):
    return f"{int(value):,}" if value == value.to_integral() else f"{value:,.2f}"


def format_amount(value):
    return f"{value.quantize(Decimal('0.01'), ROUND_HALF_UP):,.2f}"


_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December")
_UNAMBIGUOUS = ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y", "%d %B, %Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d")


def _parse_date(text):
    text = " ".join((text or "").split())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt), fmt
        except ValueError:
            continue
    return None, None


def looks_like_date(text):
    return _parse_date(text)[0] is not None


def format_date(text):
    """'03 October 2026' and '2026-10-03' become '3 October 2026'. A numeric day/month form such as 03/10/2026 could be read
    either way, so it is kept as typed."""
    when, fmt = _parse_date(text)
    if when is None or fmt not in _UNAMBIGUOUS:
        return " ".join((text or "").split())
    return f"{when.day} {_MONTHS[when.month - 1]} {when.year}"


def fill_deadline(text, values):
    """The commencement and completion blanks. A period fills "within [*]" as typed; a calendar date turns that
    "within" into "on or before". Each of the two is decided on its own."""
    parts = text.split(BLANK)
    if len(parts) != len(values) + 1:
        return text
    out = parts[0]
    for value, rest in zip(values, parts[1:]):
        if not value:
            out += BLANK + rest
        elif looks_like_date(value):
            out = (out[:-len("within ")] + "on or before " if out.endswith("within ") else out) + format_date(value) + rest
        else:
            out += value + rest
    return out


def fill_slots(text, values):
    """values[i] replaces the i-th [*] of `text`; None keeps it. Nothing changes unless the count of [*] matches."""
    if text.count(BLANK) != len(values):
        return text
    parts = text.split(BLANK)
    out = parts[0]
    for value, rest in zip(values, parts[1:]):
        out += (BLANK if value is None else value) + rest
    return out


def _percent(inst):
    value = parse_decimal(re.sub(r"%", "", getattr(inst, "percent", "") or ""))
    return value if value is not None and value <= 100 else None


def _item(clause, index):
    return clause.items[index] if clause is not None and index < len(clause.items) else None


def fill_template(library, term_sheet):
    """Writes the term sheet's values into the template clauses of `library`, in place. Without a term sheet, or for a
    value it does not have, the template wording is left as it is."""
    if term_sheet is None:
        return library
    by_key = {c.key: c for c in library}
    ts = term_sheet

    choice = vat_choice(ts)
    price_clause = by_key.get("price_payment")
    if choice and price_clause:
        for item in price_clause.items:
            item.text = item.text.replace(CLAUSE_PHRASE, f"{choice} of VAT")

    # clause 1: capacity in the unit entered (the template's literal "kWp" follows the blank), and the location
    construction = by_key.get("construction_terms")
    if construction and construction.plain_paragraphs:
        number, unit = capacity_parts(ts)
        text = construction.plain_paragraphs[0].replace(f"{BLANK} kWp", f"{BLANK} {unit}")
        construction.plain_paragraphs[0] = fill_slots(text, [number, _text(ts, "project_location") or None])

    attachments = by_key.get("attachments")
    if attachments and len(attachments.plain_paragraphs) > 1 and _text(ts, "attachment_no"):
        attachments.plain_paragraphs[1] = attachments.plain_paragraphs[1].replace(
            f"Attachment {BLANK}", f"Attachment {_text(ts, 'attachment_no')}")

    price = parse_decimal(_text(ts, "contract_price_number"))
    price_item = _item(price_clause, 0)
    if price_item:
        typed = _text(ts, "contract_price_number")
        shown = format_price(price) if price is not None else (typed or None)
        price_item.text = fill_slots(price_item.text, [shown, _text(ts, "contract_price_words") or None])

    days_item = _item(price_clause, 2)
    if days_item:
        days = _text(ts, "payment_days")
        n = int(days) if days.isdigit() and 0 < int(days) < 1000 else None
        days_item.text = fill_slots(days_item.text, [str(n), int_words(n)] if n else [None, None])

    if price_clause and price_clause.tables:
        installments = list(getattr(ts, "installments", []) or [])

        def cells(inst):
            pct = _percent(inst) if inst else None
            return [(_text(inst, "number") or None) if inst else None,
                    f"{format_number(pct)}%" if pct is not None else None,
                    format_amount(price * pct / 100) if price is not None and pct is not None else None]

        for table in price_clause.tables:
            del table["rows"][TEMPLATE_ROWS:]                       # so filling twice gives the same table
            for r, row in enumerate(table["rows"]):                 # the template's rows keep their conditions
                for c, value in enumerate(cells(installments[r] if r < len(installments) else None)):
                    if value is not None and row[c] == BLANK:
                        row[c] = value
            for inst in installments[TEMPLATE_ROWS:]:               # more installments than rows: one more row each
                table["rows"].append([v or BLANK for v in cells(inst)] + [_text(inst, "condition") or BLANK])
        price_clause.table_rows = [tuple(row) for row in price_clause.tables[0]["rows"]]

    deadline = _item(by_key.get("completion_deadline"), 0)
    if deadline:
        deadline.text = fill_deadline(deadline.text, [_text(ts, name) for name in ("start_date", "completion_date")])
    return library


def fill_warnings(ts):
    """Problems in what the term sheet holds that the contract text cannot show, for the preview step."""
    if ts is None:
        return []
    warnings = []
    installments = [i for i in (getattr(ts, "installments", []) or []) if (i.percent or i.number or i.condition)]
    if 0 < len(installments) < TEMPLATE_ROWS:
        warnings.append(f"The term sheet has {len(installments)} installments but the payment table in the contract has "
                        f"{TEMPLATE_ROWS} rows: rows {len(installments) + 1}-{TEMPLATE_ROWS} are left blank.")
    price = parse_decimal(_text(ts, "contract_price_number"))
    pcts = [_percent(i) for i in installments]
    if price is not None and pcts and all(p is not None for p in pcts):
        total = sum(Decimal(format_amount(price * p / 100).replace(",", "")) for p in pcts)
        if abs(total - price) >= Decimal("0.02") and sum(pcts) == 100:
            warnings.append(f"The installment amounts add up to {format_amount(total)}, not {format_amount(price)}, "
                            "because of rounding.")
    days = _text(ts, "payment_days")
    if days and not (days.isdigit() and 0 < int(days) < 1000):
        warnings.append(f"Payment days \u201c{days}\u201d is not a whole number of days, so it was left blank.")
    choice = getattr(ts, "signing_place_choice", "")
    from core.term_sheet_fields import signing_place
    if choice and not signing_place(ts):
        warnings.append("The place of signing points to an address that is empty.")
    return warnings
