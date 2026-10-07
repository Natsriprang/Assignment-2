"""Tests for the readiness check (ai/readiness.py): one AI call, the AI told only the elements, code overriding where the term sheet lacks
something, evidence that must be in the draft, no citation of the law. Run: python -m tests.test_readiness"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.readiness import SYSTEM_PROMPT, build_schema, check_readiness
from ai.review import Section
from core.legal_systems import AUSTRALIA, GENERIC, THAILAND, match_system
from core.readiness import facts
from tests.test_legal_systems import complete_term_sheet

DRAFT = [Section("header", "Contract header", "This agreement is made between Owner Co and Build Co."),
         Section("price", "Price", "The Owner shall pay THB 1,000,000 to the Contractor for the Works."),
         Section("signature", "Signature block", "IN WITNESS WHEREOF, the Parties have signed.\nNat Sriprang\nNoom Sriprang")]
FOUND = facts(complete_term_sheet())


class OneClient:
    def __init__(self, payload):
        self.payload, self.calls = payload, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        msg = SimpleNamespace(content=json.dumps(self.payload), refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def element(key, status="complete", reason="Shown.", quote="The Owner shall pay THB 1,000,000"):
    return {"element_key": key, "status": status, "reason": reason, "quote": quote}


def thai_all(**over):
    base = {e.key: element(e.key) for e in THAILAND.elements}
    base.update(over)
    return {"elements": list(base.values())}


def run(payload, system=THAILAND, why="", found=FOUND, sections=DRAFT):
    client = OneClient(payload)
    return check_readiness(system, why, found, sections, client), client


# ---------------------------------------------------------------- one call, and what the AI is told
def test_one_ai_call_is_made_with_the_elements_the_facts_and_the_draft():
    result, client = run(thai_all())
    assert len(client.calls) == 1 and result.system_name == "Thailand" and not result.general
    told = client.calls[0]["messages"][1]["content"]
    assert "GOVERNING LAW: Thailand" in told and "[offer_acceptance] Offer and acceptance:" in told and "[form] Form of the contract:" in told
    assert "FACTS CHECKED BY THE APP:" in told and "[capacity] nothing missing from the term sheet" in told
    assert "[key: price | title: Price]" in told and client.calls[0]["messages"][0]["content"] == SYSTEM_PROMPT


def test_the_ai_is_told_only_what_the_list_says_and_never_a_section_or_a_case():
    import re
    result, client = run(thai_all())
    told = client.calls[0]["messages"][0]["content"] + client.calls[0]["messages"][1]["content"]
    assert not re.search(r"(?i)\bsections?\s+\d|\bss\s+\d|Civil and Commercial Code|Corporations Act|\b361\b|\b150\b", told)
    assert "does not decide that a contract exists" in SYSTEM_PROMPT and "do not cite a statute" in SYSTEM_PROMPT


def test_the_schema_allows_only_the_elements_of_the_list():
    enum = build_schema([e.key for e in AUSTRALIA.elements])["properties"]["elements"]["items"]["properties"]["element_key"]["enum"]
    assert enum == ["offer_acceptance", "intention", "consideration", "capacity", "consent", "legality"]


# ---------------------------------------------------------------- the three outcomes and their evidence
def test_complete_and_not_complete_need_words_that_are_in_the_draft():
    payload = thai_all(offer_acceptance=element("offer_acceptance", "complete", "Parties, work and price are stated."),
                       reciprocal=element("reciprocal", "not_complete", "No payment date.", "The Owner shall pay THB 1,000,000"),
                       lawful_purpose=element("lawful_purpose", "cannot_tell", "Nothing shows it.", ""))
    got = {r.key: r for r in run(payload)[0].results}
    assert (got["offer_acceptance"].status, got["offer_acceptance"].quote) == ("complete", "The Owner shall pay THB 1,000,000")
    assert got["reciprocal"].status == "not_complete" and got["lawful_purpose"].status == "cannot_tell"


def test_a_conclusion_with_words_that_are_not_in_the_draft_becomes_cannot_tell():
    payload = thai_all(offer_acceptance=element("offer_acceptance", "complete", "Fine.", "words that are nowhere in the draft"),
                       reciprocal=element("reciprocal", "not_complete", "Missing.", ""))
    got = {r.key: r for r in run(payload)[0].results}
    for key in ("offer_acceptance", "reciprocal"):
        assert got[key].status == "cannot_tell" and got[key].quote == "" and "No words of the draft could be found" in got[key].reason


def test_an_element_the_ai_did_not_assess_is_cannot_tell():
    payload = {"elements": [element("offer_acceptance")]}
    got = {r.key: r for r in run(payload)[0].results}
    assert got["capacity"].status == "cannot_tell" and got["capacity"].reason == "The AI did not assess this element."
    assert [r.key for r in run(payload)[0].results] == [e.key for e in THAILAND.elements], "in the order of the list"


def test_an_unknown_status_or_a_repeated_element_is_not_trusted():
    payload = thai_all(form=element("form", "valid"))
    payload["elements"].append(element("form", "complete"))
    assert {r.key: r for r in run(payload)[0].results}["form"].status == "cannot_tell"


# ---------------------------------------------------------------- code overrides the AI
def test_an_element_that_depends_on_a_missing_fact_is_not_complete_whatever_the_ai_says():
    found = facts(complete_term_sheet(owner_reg_no="", owner_signatory=""))
    got = {r.key: r for r in run(thai_all(), found=found)[0].results}
    assert got["capacity"].status == "not_complete" and got["capacity"].by == "app"
    assert got["capacity"].reason == "Not in the term sheet: the Owner's registration number, the Owner's authorised signatory."
    assert got["form"].status == "not_complete" and got["offer_acceptance"].status == "complete" and got["offer_acceptance"].by == "ai"


def test_the_call_is_made_even_when_code_has_already_found_gaps():
    found = facts(None)
    result, client = run(thai_all(), found=found)
    assert len(client.calls) == 1 and result.counts() == {"complete": 1, "not_complete": 5, "cannot_tell": 0}, "only the element with no fact is left to the AI"


# ---------------------------------------------------------------- no citing of the law
def test_a_reason_that_cites_a_provision_of_law_is_not_shown():
    for cite in ("It meets section 361 of the Code.", "Under the Civil and Commercial Code it is fine.", "The Corporations Act allows it.", "See Article 12."):
        result, _ = run(thai_all(offer_acceptance=element("offer_acceptance", "complete", cite)))
        r = {x.key: x for x in result.results}["offer_acceptance"]
        assert "cited a provision of law" in r.reason and cite not in r.reason and result.notes, cite
    ok, _ = run(thai_all(offer_acceptance=element("offer_acceptance", "complete", "It is clause 3 of the draft that sets the price.")))
    assert "clause 3" in {x.key: x for x in ok.results}["offer_acceptance"].reason, "a clause of the draft is not a provision of law"


# ---------------------------------------------------------------- a governing law with no list
def test_a_governing_law_with_no_list_gets_the_general_list_and_a_warning():
    system, why = match_system("Singapore")
    payload = {"elements": [element(e.key) for e in GENERIC.elements]}
    result, client = run(payload, system, why)
    assert system is None and result.general and result.why == why and result.system_name == "General list"
    told = client.calls[0]["messages"][1]["content"]
    assert "No list of elements was prepared for \u201cSingapore\u201d." in told and "[parties] The Parties are identified:" in told
    assert [r.key for r in result.results] == [e.key for e in GENERIC.elements]


def test_the_counts_add_up_and_nothing_says_the_contract_is_valid():
    result, _ = run(thai_all(form=element("form", "cannot_tell", "Cannot be told.", "")))
    n = result.counts()
    assert n == {"complete": 5, "not_complete": 0, "cannot_tell": 1}
    assert "valid" not in SYSTEM_PROMPT.lower().replace("not a legal opinion", "")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} readiness tests passed.")
