"""VAT treatment of the contract price: reading what a term sheet says, and the warning shown while it is not chosen.
There is no default: if nobody chose, the contract must not say either."""

_EXCLUSIVE = ("not inclusive", "not including", "not included", "not include", "exclusive", "excluding", "excluded",
              "excl", "plus vat", "vat extra", "before vat", "\u0e44\u0e21\u0e48\u0e23\u0e27\u0e21")
_INCLUSIVE = ("inclusive", "including", "included", "incl", "\u0e23\u0e27\u0e21")

CLAUSE_PHRASE = "inclusive / exclusive of VAT"       # the either/or the price clause carries in the template


def normalise_vat(text):
    """'inclusive', 'exclusive' or '' when the text says neither, or says both, or says something else."""
    t = " ".join((text or "").lower().replace(".", " ").split())
    if not t:
        return ""
    exclusive = any(k in t for k in _EXCLUSIVE)
    for k in _EXCLUSIVE:
        t = t.replace(k, " ")
    inclusive = any(k in t for k in _INCLUSIVE)
    if exclusive == inclusive:
        return ""
    return "exclusive" if exclusive else "inclusive"


def vat_choice(term_sheet):
    return normalise_vat(getattr(term_sheet, "vat_treatment", ""))


def vat_warning(term_sheet):
    """Text of the red notice while VAT is not chosen; None once it is."""
    if vat_choice(term_sheet):
        return None
    raw = " ".join((getattr(term_sheet, "vat_treatment", "") or "").split())
    said = f" The term sheet says \u201c{raw}\u201d, which cannot be read as inclusive or exclusive." if raw else ""
    return (f"VAT is not chosen.{said} Until you choose, the price clause keeps the words \u201c{CLAUSE_PHRASE}\u201d, "
            "so the contract does not say whether the price includes VAT.")
