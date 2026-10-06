"""The signature block that closes the contract: for each party, its company name, a signing line for each authorised
signatory, and then a signing line for each witness. Filled from the term sheet; a missing name is [*] (a party always has at
least one signatory and one witness line). Pure code. Layout (Word table, preview columns) is the
renderers' business; this only says what goes in it."""
from core.field_rules import split_names

PLACEHOLDER = "[*]"
CLOSING = ("IN WITNESS WHEREOF, the Parties have caused this Agreement to be executed by their duly authorised "
           "representatives on the date first written above.")
SIGNATURE_LINE = "_" * 30


def names_of(text):
    """The names in a signatory or witness field. The page keeps one name per line, and then only the line breaks separate names (a
    name may have a comma in it); text typed or imported on one line is split at ; , & and "and"."""
    text = text or ""
    if "\n" in text.strip():
        return [line.strip() for line in text.splitlines() if line.strip()]
    return split_names(text)


def _party(role, company, signatories, witnesses=""):
    """One column: the role, the company, then a signing line, a name and a title for each signatory, and under them the same for
    each witness."""
    lines = [role.upper(), (company or "").strip() or PLACEHOLDER]
    for name in names_of(signatories) or [PLACEHOLDER]:
        lines += ["", SIGNATURE_LINE, name, "Authorised signatory"]
    for name in names_of(witnesses) or [PLACEHOLDER]:
        lines += ["", SIGNATURE_LINE, name, "Witness"]
    return {"role": role, "lines": lines}


def build_signature_block(ts):
    """{"closing": text, "parties": [{"role", "lines"}, ...]}. `ts` may be None or an older term sheet object."""
    g = lambda name: getattr(ts, name, "") or ""
    return {"closing": CLOSING,
            "parties": [_party("Owner", g("owner_name"), g("owner_signatory"), g("owner_witnesses")),
                        _party("Contractor", g("contractor_name"), g("contractor_signatory"), g("contractor_witnesses"))]}


def signature_texts(block):
    """Every line of the block, for the blanks finder."""
    return [block["closing"]] + [line for party in block["parties"] for line in party["lines"]]
