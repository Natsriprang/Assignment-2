"""The facts about a draft that code can check without any AI: are the Parties named and identified, is the work described, is the price
stated, are the signatories named. They come from the term sheet, which is what fills the draft. Pure code. The summary of the contract lists
what is still missing before the draft is sent to the other Party."""
from dataclasses import dataclass, field

from core.signatures import names_of


@dataclass
class Fact:
    key: str
    ok: bool
    missing: list = field(default_factory=list)       # the plain names of what is not there


def _text(ts, name):
    return " ".join(str(getattr(ts, name, "") or "").split())


def _fact(key, ts, wanted):
    """`wanted` is [(plain name, field name)] or [(plain name, callable)]: every one must hold a value."""
    missing = [label for label, name in wanted if not (name(ts) if callable(name) else _text(ts, name))]
    return Fact(key, not missing, missing)


def facts(ts):
    """{fact key: Fact} for a term sheet (None or an older term sheet object gives facts that fail)."""
    return {f.key: f for f in (
        _fact("parties_named", ts, [("the Owner's name", "owner_name"), ("the Contractor's name", "contractor_name")]),
        _fact("parties_identified", ts, [("the Owner's registration number", "owner_reg_no"), ("the Owner's address", "owner_address"),
                                         ("the Contractor's registration number", "contractor_reg_no"), ("the Contractor's address", "contractor_address")]),
        _fact("signatories_named", ts, [("the Owner's authorised signatory", lambda t: names_of(getattr(t, "owner_signatory", ""))),
                                        ("the Contractor's authorised signatory", lambda t: names_of(getattr(t, "contractor_signatory", "")))]),
        _fact("work_described", ts, [("the project name", "project_name"), ("the project location", "project_location"), ("the capacity", "capacity")]),
        _fact("price_stated", ts, [("the contract price", "contract_price_number")]),
    )}


def missing_before_sending(ts):
    """The plain names of what the term sheet still lacks, each once, in the order of the facts."""
    out = []
    for fact in facts(ts).values():
        out += [m for m in fact.missing if m not in out]
    return out
