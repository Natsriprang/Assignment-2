"""Tests for the review round (ai/review.py): two calls every time, evidence and fixes checked by code. Run: python -m tests.test_review"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.llm import AIStepError
from ai.review import (GENERAL, MAX_FINDINGS, MAX_NEW_IN_SECOND_LOOK, Section, build_schema, build_second_schema, review_draft, sections_of)
from core.draft_state import library_for

LIBRARY = library_for({})
CLAUSE = next(c for c in LIBRARY if c.key == "completion_deadline")
LD_OLD = next(i.text for i in CLAUSE.items if "liquidated damages" in i.text)
LD_NEW = LD_OLD.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)")
TS_TEXT = "project_name: Rooftop PV\nlimits: delay damages 0.03% per day"
SECTIONS = sections_of(LIBRARY, [("title", "Header title")], ["IN WITNESS", "Owner"])


class SeqClient:
    """Returns the payloads one after the other; `refuse_at` is the index of a call the model refuses."""
    def __init__(self, *payloads, refuse_at=None):
        self.payloads, self.refuse_at, self.calls = list(payloads), refuse_at, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        n = len(self.calls)
        self.calls.append(kwargs)
        refusal = "no" if n == self.refuse_at else None
        msg = SimpleNamespace(content=json.dumps(self.payloads[min(n, len(self.payloads) - 1)]), refusal=refusal)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def finding(clause_key="completion_deadline", issue="The damages rate is not what the term sheet says.", why="Term sheet: 0.03% per day.",
            quote="0.05 (zero point zero five)", fix_type="modify", new_text=LD_NEW):
    return {"clause_key": clause_key, "issue": issue, "why": why, "quote": quote, "fix_type": fix_type, "new_text": new_text}


def first(*findings):
    return {"findings": list(findings)}


def second(verdicts=(), additional=()):
    return {"verdicts": list(verdicts), "additional": list(additional)}


def run(client, sections=None, ts_text=TS_TEXT):
    return review_draft(ts_text, SECTIONS if sections is None else sections, client)


# ---------------------------------------------------------------- always two calls
def test_two_calls_are_made_even_when_the_first_finds_nothing():
    client = SeqClient(first(), second())
    result = run(client)
    assert len(client.calls) == 2 and result.findings == [] and result.second_look_done
    assert "FINDINGS OF THE FIRST REVIEW:\n(the first review found nothing)" in client.calls[1]["messages"][1]["content"]


def test_the_second_call_is_given_the_findings_of_the_first_with_their_ids():
    client = SeqClient(first(finding()), second())
    run(client)
    content = client.calls[1]["messages"][1]["content"]
    assert "[f1] section: completion_deadline" in content and "TERM SHEET:" in content and "[key: completion_deadline" in content


# ---------------------------------------------------------------- a finding and its fix
def test_a_good_fix_is_kept_with_the_sentence_it_changes():
    f = run(SeqClient(first(finding()), second())).findings[0]
    assert (f.id, f.clause_key, f.quote_verified, f.fix_type, f.round) == ("f1", "completion_deadline", True, "modify", 1)
    assert f.old_text == " ".join(LD_OLD.split()) and f.new_text == " ".join(LD_NEW.split()) and f.fix_note == ""


def test_a_figure_that_is_not_in_the_term_sheet_drops_the_fix_and_keeps_the_finding():
    bad = LD_OLD.replace("0.05 (zero point zero five)", "0.09 (zero point zero nine)")
    f = run(SeqClient(first(finding(new_text=bad)), second())).findings[0]
    assert f.fix_type == "none" and f.new_text == "" and "figure that you did not give" in f.fix_note and f.issue


def test_a_quote_that_is_not_in_the_clause_is_blanked_and_no_fix_is_written():
    f = run(SeqClient(first(finding(quote="words that are not in the clause")), second())).findings[0]
    assert f.quote == "" and not f.quote_verified and f.fix_type == "none" and "not found" in f.fix_note


def test_a_quote_in_two_sentences_gives_no_fix():
    from core.clauses import Clause, Item
    clause = Clause(key="two", title="Two", items=[Item("The Owner shall pay within 14 days."), Item("The Contractor shall pay within 14 days.")], category="general")
    sections = [Section("two", "Two", "\n".join(i.text for i in clause.items), clause)]
    f = run(SeqClient(first(finding("two", quote="shall pay within 14 days", new_text="The Owner shall pay within 14 days.")), second()), sections).findings[0]
    assert f.quote_verified and f.fix_type == "none" and "single sentence" in f.fix_note


def test_a_new_sentence_can_be_added_at_the_end_of_a_clause():
    f = run(SeqClient(first(finding(quote="", fix_type="add", new_text="Delay damages are 0.03% per day.")), second())).findings[0]
    assert f.fix_type == "add" and f.old_text == "" and f.new_text == "Delay damages are 0.03% per day."


def test_an_unknown_clause_or_an_empty_issue_drops_the_finding():
    result = run(SeqClient(first(finding("no_such_clause"), finding(issue="  "), finding(GENERAL, quote="", fix_type="none", new_text="")), second()))
    assert [f.clause_key for f in result.findings] == [GENERAL] and result.findings[0].clause == "The draft as a whole"
    assert result.notes.count("Dropped a finding that was not valid.") == 2


def test_a_part_that_is_not_a_clause_has_findings_but_no_fix():
    f = run(SeqClient(first(finding("header", quote="Header title", new_text="Another title")), second())).findings[0]
    assert f.quote_verified and f.fix_type == "none" and "not a clause" in f.fix_note


def test_a_draft_that_is_only_text_has_no_fixes():
    sections = [Section("draft", "The draft", LD_OLD)]
    f = run(SeqClient(first(finding("draft")), second()), sections).findings[0]
    assert f.quote_verified and f.fix_type == "none"


# ---------------------------------------------------------------- the second look
def test_the_second_look_drops_what_it_says_is_wrong_and_adds_what_was_missed():
    client = SeqClient(first(finding(), finding(GENERAL, issue="Style.", quote="", fix_type="none", new_text="")),
                       second([{"finding_id": "f2", "keep": False, "reason": "Only style."}, {"finding_id": "zzz", "keep": False, "reason": "unknown"}],
                              [finding(GENERAL, issue="A missing date.", quote="", fix_type="none", new_text="")]))
    result = run(client)
    assert [(f.id, f.round) for f in result.findings] == [("f1", 1), ("g1", 2)]
    assert result.dropped == [("f2", "Style.", "Only style.")]


def test_something_the_first_review_already_found_is_not_added_again():
    client = SeqClient(first(finding()), second([], [finding(issue="Same place, other words.")]))
    assert [f.id for f in run(client).findings] == ["f1"]


def test_the_second_look_adds_at_most_three_and_everything_is_capped():
    extra = [finding(GENERAL, issue=f"Missed {n}.", quote="", fix_type="none", new_text="") for n in range(6)]
    many = [finding(GENERAL, issue=f"Found {n}.", quote="", fix_type="none", new_text="") for n in range(MAX_FINDINGS)]
    result = run(SeqClient(first(*many), second([], extra)))
    assert len(result.findings) == MAX_FINDINGS and any("Kept the first" in n for n in result.notes)
    result = run(SeqClient(first(), second([], extra)))
    assert len(result.findings) == MAX_NEW_IN_SECOND_LOOK


def test_findings_come_in_the_order_of_the_draft():
    result = run(SeqClient(first(finding(GENERAL, issue="G.", quote="", fix_type="none", new_text=""), finding()), second()))
    assert [f.clause_key for f in result.findings] == ["completion_deadline", GENERAL]


# ---------------------------------------------------------------- when a call fails
def test_a_failed_second_look_keeps_the_first_findings_and_says_so():
    result = run(SeqClient(first(finding()), second(), refuse_at=1))
    assert len(result.findings) == 1 and not result.second_look_done and any("second look could not run" in n for n in result.notes)


def test_a_failed_first_call_raises():
    try:
        run(SeqClient(first(), second(), refuse_at=0))
    except AIStepError:
        return
    raise AssertionError("the first call's failure should be raised")


# ---------------------------------------------------------------- what the model reads
def test_the_draft_is_sent_in_sections_header_included_clauses_signature():
    keys = [s.key for s in SECTIONS]
    assert keys[0] == "header" and keys[-1] == "signature" and "completion_deadline" in keys
    library = library_for({"completion_deadline": False})
    assert "completion_deadline" not in [s.key for s in sections_of(library)]
    assert SECTIONS[0].text == "Header title" and SECTIONS[-1].text == "IN WITNESS\nOwner"


def test_the_schemas_allow_the_sections_and_general_only():
    enum = build_schema(["a", "b"])["properties"]["findings"]["items"]["properties"]["clause_key"]["enum"]
    assert enum == ["a", "b", GENERAL]
    verdict = build_second_schema(["a"])["properties"]["verdicts"]["items"]["properties"]["finding_id"]
    assert verdict == {"type": "string"}, "no enum: the first review may have found nothing"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} review tests passed.")
