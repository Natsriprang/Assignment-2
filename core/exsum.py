"""What the summary of the contract takes from the term sheet and from the draft by code, without any AI: the table of facts, the exact words
that were changed from the template, and the figures that the AI is allowed to write. Pure code.

The table of facts is code because it must be right: the parties, the price, the dates and the caps are written from the term sheet, so they
cannot be wrong. The AI writes only what the facts do not say, and every figure it writes is checked against the clause and the term sheet."""
import difflib
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache

from core.clause_data import build_library
from core.clause_params import MARKER, PARAMS, effective, format_number, limits_of, limits_text
from core.governing_law import law_name
from core.vat import vat_choice
from core.wording import norm
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


CAP_NAMES = {"ld_cap": "Cap on delay damages", "damages_cap": "Cap on total damages deducted"}


@lru_cache(maxsize=1)
def _cap_places():
    """{parameter key: (clause key, the words written just before its figure)}, read from the template: where each cap is written and how its
    sentence leads into the figure."""
    places = {}
    for clause in build_library():
        texts = list(clause.plain_paragraphs)
        for item in clause.items:
            texts += [item.text] + list(item.lettered)
        for table in clause.tables:
            texts += [cell for row in table["rows"] for cell in row]
        for text in texts:
            for m in MARKER.finditer(text):
                places[m.group(1)] = (clause.key, re.split(r"\{pct", m.group(2))[0].strip(" ,"))
    return places


def _sentences_of(clause):
    out = list(clause.plain_paragraphs)
    for item in clause.items:
        out += [item.text] + list(item.lettered)
    return [norm(x) for x in out]


def draft_caps(library, ts):
    """[(label, what the draft says)] for each cap on damages, read from the clauses as they stand, not from the term sheet: a request to take a
    cap out, or to change its figure, is a change to the sentence, and the term sheet does not know about it. Where the draft and the term sheet
    differ the row says what the term sheet says."""
    wanted = effective(limits_of(ts))
    rows = []
    for key in PARAMS:
        label, (clause_key, anchor) = CAP_NAMES[key], _cap_places()[key]
        clause = next((c for c in library if c.key == clause_key), None)
        if clause is None or not clause.included:
            rows.append((label, "not in the draft: the clause was taken out"))
            continue
        found = None
        for sentence in _sentences_of(clause):
            m = re.search(re.escape(anchor) + r"\s+(\d+(?:\.\d+)?)", sentence, re.IGNORECASE)
            if m:
                found = m.group(1)
                break
        said = f"{format_number(Decimal(found))}% of the Contract Price" if found else "none"
        term_sheet = wanted[key]
        if (found is None) != (term_sheet is None) or (found is not None and Decimal(found) != Decimal(str(term_sheet))):
            said += f" (the term sheet says {'no cap' if term_sheet is None else format_number(term_sheet) + '%'}; the draft was changed)"
        rows.append((label, said))
    return rows


def fact_rows(ts, library=None):
    """[(label, value)] for what the term sheet says about the deal, in the order a reader looks for it. A row with no value is left out. The
    caps on damages are read from the draft when `library` (the clauses as they stand) is given."""
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
    if library is None:
        rows.append(("Caps on damages", limits_text(limits_of(ts))))
    else:
        rows += draft_caps(library, ts)                                  # what the draft says, which a change to its wording may have moved
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


def word_changes(before, after):
    """[(removed, added)]: the words that differ between two versions of a sentence, as they are written ("0.05 (zero point zero five)" and
    "0.5 (zero point five)"). A side with nothing is "". Case and the punctuation at the end of a word do not count as a difference, so a
    full stop that moves to the end of the sentence does not show as a change. Changes that are only a word or two apart are one change, and
    a bracket that a change opens is closed in it, so that a figure and its words in brackets are shown whole."""
    b, a = norm(before).split(), norm(after).split()
    clean = lambda words: [w.lower().strip(".,;:") for w in words]
    matcher = difflib.SequenceMatcher(None, clean(b), clean(a), autojunk=False)
    spans = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if spans and i1 - spans[-1][1] <= 2:                          # one or two words between: the same change
            spans[-1][1], spans[-1][3] = i2, j2
        else:
            spans.append([i1, i2, j1, j2])
    out = []
    for i1, i2, j1, j2 in spans:
        while (" ".join(b[i1:i2]).count("(") > " ".join(b[i1:i2]).count(")") or " ".join(a[j1:j2]).count("(") > " ".join(a[j1:j2]).count(")")) \
                and i2 < len(b) and j2 < len(a):
            i2, j2 = i2 + 1, j2 + 1
        out.append((" ".join(b[i1:i2]).strip(" .,;:"), " ".join(a[j1:j2]).strip(" .,;:")))
    return out


def change_line(removed, added):
    """One change as a line: “0.05 (zero point zero five)” → “0.5 (zero point five)”, or taken out / added."""
    if removed and added:
        return f"\u201c{removed}\u201d \u2192 \u201c{added}\u201d"
    return f"taken out: \u201c{removed}\u201d" if removed else f"added: \u201c{added}\u201d"


def _without_brackets(text):
    return re.sub(r"\s*\([^)]*\)", "", text).strip()


def plain_change(removed, added):
    """A change in plain words that code can make without knowing what the words are about: the number words in brackets are left out and there
    are no quotation marks or arrows ("0.05 (zero point zero five)" to "0.5 (zero point five)" gives "changed from 0.05 to 0.5"). Used when the AI
    wrote no plain sentence for the change, or none that passed the checks."""
    r, a = _without_brackets(removed), _without_brackets(added)
    if r and a:
        return f"changed from {r} to {a}"
    return f"removed: {r}" if r else f"added: {a}"
