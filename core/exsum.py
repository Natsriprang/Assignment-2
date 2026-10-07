"""What the summary of the contract takes from the term sheet and from the draft by code, without any AI: the table of facts, the figures that
the AI is allowed to write, and the line that says how much of the contract was summarised. Pure code.

The table of facts is code because it must be right: the parties, the price, the dates and the caps are written from the term sheet, so they
cannot be wrong. The AI writes only what the facts do not say, and every figure it writes is checked against the clause and the term sheet."""
import re
from decimal import Decimal, InvalidOperation

from core.clause_params import limits_of, limits_text
from core.governing_law import law_name
from core.vat import vat_choice
from core.signatures import names_of

_DIGITS = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def _text(ts, name):
    return " ".join(str(getattr(ts, name, "") or "").split())


def _join(*parts, sep=", "):
    return sep.join(p for p in parts if p)


def amount(text):
    """An amount written with thousands separators ("100000" -> "100,000", "1500.5" -> "1,500.50"); text that is not a plain amount is left as typed."""
    raw = " ".join(str(text or "").split()).replace(",", "")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return " ".join(str(text or "").split())
    return f"{value:,.2f}" if "." in raw and value != value.to_integral_value() else f"{int(value):,}"


def fact_rows(ts):
    """[(label, value)] for what the term sheet says about the deal, in the order a reader looks for it. A row with no value is left out."""
    t = lambda name: _text(ts, name)
    rows = []
    owner = _join(t("owner_name"), t("owner_country")) if t("owner_name") else ""              # a country alone says nothing
    contractor = _join(t("contractor_name"), t("contractor_country")) if t("contractor_name") else ""
    if owner or contractor:
        rows.append(("Parties", _join(f"Owner: {owner}" if owner else "", f"Contractor: {contractor}" if contractor else "", sep="; ")))
    if t("roof_owner"):
        rows.append(("Roof owner", t("roof_owner")))
    project = _join(t("project_name"), t("project_location"))
    capacity = _join(t("capacity"), t("capacity_unit"), sep=" ") if t("capacity") else ""        # a unit alone says nothing
    if project or capacity:
        rows.append(("Project", _join(project, f"capacity {capacity}" if capacity else "")))
    if t("contract_price_number"):
        words = f" ({t('contract_price_words')})" if t("contract_price_words") else ""
        vat = {"exclusive": "exclusive of VAT", "inclusive": "inclusive of VAT"}.get(vat_choice(ts), t("vat_treatment"))
        rows.append(("Contract price", _join(f"THB {amount(t('contract_price_number'))}{words}", vat)))
    mode = t("deadline_mode")
    if mode == "period" and t("completion_days"):
        rows.append(("Time for the Works", f"{t('completion_days')} days"))
    elif t("start_date") or t("completion_date"):
        rows.append(("Time for the Works", f"{t('start_date') or '?'} to {t('completion_date') or '?'}"))
    installments = [i for i in getattr(ts, "installments", []) or [] if str(getattr(i, "percent", "")).strip()]
    if installments:                                                                          # the number of days alone is only a default
        share = ", ".join(f"{str(i.percent).strip()}%" for i in installments)
        rows.append(("Payment", _join(f"{len(installments)} installments ({share})" if installments else "",
                                      f"each due within {t('payment_days')} working days" if t("payment_days") else "")))
    rows.append(("Caps on damages", limits_text(limits_of(ts))))
    if law_name(getattr(ts, "governing_law", "")):
        rows.append(("Governing law", law_name(ts.governing_law)))
    signatories = _join(f"Owner: {', '.join(names_of(t('owner_signatory')))}" if names_of(t("owner_signatory")) else "",
                        f"Contractor: {', '.join(names_of(t('contractor_signatory')))}" if names_of(t("contractor_signatory")) else "", sep="; ")
    if signatories:
        rows.append(("Signatories", signatories))
    return rows


def facts_text(rows):
    return "\n".join(f"{label}: {value}" for label, value in rows)


# ---------------------------------------------------------------------------------------- the figures the AI may write
def digit_figures(text):
    """The figures written as digits in a text, "1,000,000" as one figure (and not as 1, 0 and 0)."""
    out = set()
    for m in _DIGITS.findall(str(text or "")):
        try:
            out.add(Decimal(m.replace(",", "")))
        except InvalidOperation:
            continue
    return out


def allowed_figures(*texts):
    return set().union(*(digit_figures(t) for t in texts)) if texts else set()


def unsupported_figures(text, allowed):
    """The figures written as digits in `text` that are in none of the sources: an amount, a date or a percentage that the AI made up."""
    return sorted(digit_figures(text) - allowed)


def coverage_text(summarised, skipped, standard_titles):
    """The line under the summary: how many clauses it covers and which it left out as standard wording."""
    total = summarised + skipped
    line = f"Summarised {summarised} of {total} clauses"
    if skipped:
        line += f"; left out {skipped} that use the template's standard wording with nothing specific to this deal"
    return line + "."
