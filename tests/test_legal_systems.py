"""Tests for the lists of elements per governing law and for the facts checked by code (core/legal_systems.py, core/readiness.py).
Run: python -m tests.test_legal_systems"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.legal_systems import AUSTRALIA, GENERIC, SYSTEMS, THAILAND, match_system
from core.readiness import facts, failed_for
from core.term_sheet_fields import TermSheet

FACT_KEYS = {"parties_named", "parties_identified", "signatories_named", "work_described", "price_stated"}


def complete_term_sheet(**over):
    ts = TermSheet(owner_name="Owner Co", owner_reg_no="O-1", owner_address="1 Owner Rd", owner_signatory="Nat Sriprang",
                   contractor_name="Build Co", contractor_reg_no="B-1", contractor_address="2 Builder Rd", contractor_signatory="Noom Sriprang",
                   project_name="Rooftop PV", project_location="Rayong", capacity="500", contract_price_number="1,000,000", governing_law="Thailand")
    for k, v in over.items():
        setattr(ts, k, v)
    return ts


# ---------------------------------------------------------------- which list applies to what the user typed
def test_the_governing_law_as_typed_is_matched_to_a_list():
    for text in ("Thailand", "the laws of Thailand", "Thai law", "Kingdom of Thailand", "\u0e44\u0e17\u0e22", "THAILAND."):
        assert match_system(text)[0] is THAILAND, text
    for text in ("Australia", "Victoria, Australia", "New South Wales", "Queensland", "laws of Australia"):
        assert match_system(text)[0] is AUSTRALIA, text


def test_a_law_with_no_list_or_two_lists_or_nothing_matches_none_and_says_why():
    for text, words in (("England and Wales", "No list of elements was prepared"), ("Singapore", "No list of elements was prepared"),
                        ("Thailand and Australia", "more than one"), ("", "No governing law is written"), ("   ", "No governing law is written"),
                        ("Wales", "No list of elements was prepared")):
        system, why = match_system(text)
        assert system is None and words in why, (text, why)
    assert "\u201cEngland and Wales\u201d" in match_system("the laws of England and Wales")[1]


# ---------------------------------------------------------------- the lists themselves
def test_the_lists_follow_their_sources():
    assert [e.key for e in AUSTRALIA.elements] == ["offer_acceptance", "intention", "consideration", "capacity", "consent", "legality"]
    assert [e.key for e in THAILAND.elements] == ["offer_acceptance", "lawful_purpose", "capacity", "genuine_intent", "reciprocal", "form"]
    assert not any("consideration" in e.key for e in THAILAND.elements), "the Thai source has no element called consideration"
    assert AUSTRALIA.url.startswith("https://www.thelawhandbook.org.au/") and THAILAND.url.startswith("https://www.thailawwise.com/")


def test_every_element_is_described_and_only_depends_on_facts_that_exist():
    for system in (*SYSTEMS, GENERIC):
        keys = [e.key for e in system.elements]
        assert len(keys) == len(set(keys)), system.key
        for e in system.elements:
            assert e.title and len(e.look_for) > 40 and set(e.facts) <= FACT_KEYS, (system.key, e.key)


def test_what_the_source_cites_is_never_in_what_the_ai_is_told():
    cite = re.compile(r"(?i)\bsections?\s+\d|\bss\s+\d|Civil and Commercial Code|Corporations Act")
    for system in (*SYSTEMS, GENERIC):
        for e in system.elements:
            assert not cite.search(e.look_for) and not cite.search(e.title), (system.key, e.key)
    assert any(e.cites for e in THAILAND.elements) and any(e.cites for e in AUSTRALIA.elements), "kept for the person who checks the list"


# ---------------------------------------------------------------- facts checked by code
def test_a_complete_term_sheet_has_every_fact():
    found = facts(complete_term_sheet())
    assert set(found) == FACT_KEYS and all(f.ok for f in found.values())
    assert all(failed_for(e, found) == [] for e in THAILAND.elements + AUSTRALIA.elements)


def test_a_fact_that_fails_says_what_is_missing():
    found = facts(complete_term_sheet(owner_reg_no="", contractor_address="  ", owner_signatory="", contract_price_number=""))
    assert found["parties_identified"].missing == ["the Owner's registration number", "the Contractor's address"]
    assert found["signatories_named"].missing == ["the Owner's authorised signatory"] and found["price_stated"].missing == ["the contract price"]
    capacity = next(e for e in THAILAND.elements if e.key == "capacity")
    assert failed_for(capacity, found) == ["the Owner's registration number", "the Contractor's address", "the Owner's authorised signatory"]
    assert failed_for(next(e for e in THAILAND.elements if e.key == "genuine_intent"), found) == [], "an element with no fact depends on nothing"


def test_no_term_sheet_fails_every_fact():
    assert not any(f.ok for f in facts(None).values())


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} legal system tests passed.")
