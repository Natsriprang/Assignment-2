"""The signature block that closes the contract: for each party, its company name and a signing line for each authorised
signatory. Filled from the term sheet; a missing name is [*]. Pure code. Layout (Word table, preview columns) is the
renderers' business; this only says what goes in it."""
from core.field_rules import split_names

PLACEHOLDER = "[*]"
CLOSING = ("IN WITNESS WHEREOF, the Parties have caused this Agreement to be executed by their duly authorised "
           "representatives on the date first written above.")
SIGNATURE_LINE = "_" * 30


def _party(role, company, signatories):
    """One column: the role, the company, then a signing line, a name and a title for each signatory."""
    lines = [role.upper(), (company or "").strip() or PLACEHOLDER]
    for name in split_names(signatories) or [PLACEHOLDER]:
        lines += ["", SIGNATURE_LINE, name, "Authorised signatory"]
    return {"role": role, "lines": lines}


def build_signature_block(ts):
    """{"closing": text, "parties": [{"role", "lines"}, ...]}. `ts` may be None or an older term sheet object."""
    g = lambda name: getattr(ts, name, "") or ""
    return {"closing": CLOSING,
            "parties": [_party("Owner", g("owner_name"), g("owner_signatory")),
                        _party("Contractor", g("contractor_name"), g("contractor_signatory"))]}


def signature_texts(block):
    """Every line of the block, for the blanks finder."""
    return [block["closing"]] + [line for party in block["parties"] for line in party["lines"]]
