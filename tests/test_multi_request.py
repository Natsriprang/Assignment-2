"""Tests for a message that holds more than one request: applying the first must not make the second look done (ai/interpret.py settle),
and the caps on damages are term sheet settings. Run: python -m tests.test_multi_request"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.interpret import SYSTEM_PROMPT, _another_part, context_summary, interpret_request
from core.draft_state import library_for
from core.wording import find_unit
from tests.test_interpret import FakeClient, dev, empty, sample_term_sheet

TS = sample_term_sheet()
RATE = "at the rate of 0.05 (zero point zero five) percent of the Contract Price per day"
CAP = "but not more than 5 (five) percent of the Contract Price"
OLD = find_unit(next(c for c in library_for({}, None, None, TS) if c.key == "completion_deadline"), RATE)[1]
NEW = OLD.replace("0.05 (zero point zero five)", "0.5 (zero point five)")
EDIT = {"id": "e1", "clause_key": "completion_deadline", "change_type": "modify", "old": OLD, "new": NEW, "summary": "s"}
LIB = library_for({}, None, None, TS, [EDIT])                       # the draft after the first request was applied
MSG = "change delay damage to 0.5% and remove limit"
YES = f"Yes, by \u201c{MSG}\u201d I meant the 'Completion Deadline' clause."
APPLIED = [{"kind": "wording", "key": "completion_deadline", "evidence": MSG, "quote": RATE}]
CONVERSATION = [{"role": "user", "content": MSG + f"\nApplied to the draft: wording change in Completion Deadline: change delay damage to 0.5% (the user's words: \u201c{MSG}\u201d). This request is done."},
                {"role": "assistant", "content": f"Question: You wrote \u201c{MSG}\u201d. No clause uses that term. The closest provision is 'Completion Deadline': \u201c{CAP}\u201d. Is that what you meant?"},
                {"role": "user", "content": YES}]


def cap_deviation(evidence, match="confirmed_by_user"):
    return dev("completion_deadline", CAP, change_type="remove_part", change="remove the cap on delay damages", evidence=evidence,
               term="delay damage limit", match=match)


def second_reply(payload, applied=APPLIED, conversation=CONVERSATION):
    return interpret_request(TS, LIB, FakeClient(payload), conversation=conversation, applied_edits=[EDIT], applied_entries=applied)


# ---------------------------------------------------------------- the second request of a message is not done because the first was applied
def test_the_second_request_survives_whatever_words_the_model_gives_as_its_evidence():
    for evidence in (MSG, YES, "remove limit"):
        result = second_reply(empty(deviations=[cap_deviation(evidence)]))
        assert [d.requested_change for d in result.deviations] == ["remove the cap on delay damages"], evidence
        assert "Dropped a request that is already applied to the draft." not in result.notes, evidence


def test_the_same_request_asked_again_is_still_done():
    again = dev("completion_deadline", "at the rate of 0.5 (zero point five) percent of the Contract Price per day", change="change delay damage to 0.5%",
                evidence="change delay damage to 0.5%")
    result = second_reply(empty(deviations=[again]))
    assert result.deviations == [] and any(n.startswith("Dropped a") for n in result.notes), "dropped, by whichever check sees it first"


def test_a_question_about_another_part_of_the_clause_is_not_dropped_either():
    question = {"request": "remove the delay damage limit", "evidence": MSG, "candidate_clause_key": "completion_deadline",
                "candidate_provision_quote": CAP, "why_related": "The clause caps the delay damages.", "candidate_change": "remove the cap"}
    result = second_reply(empty(unmapped_requests=[question]))
    assert [u.candidate_key for u in result.unmapped_requests] == ["completion_deadline"]
    same_part = dict(question, candidate_provision_quote=RATE.replace("0.05 (zero point zero five)", "0.5 (zero point five)"))
    assert second_reply(empty(unmapped_requests=[same_part])).unmapped_requests == [], "a question about the part that was applied is done"


def test_an_applied_entry_without_a_quote_behaves_as_it_did_before():
    old_shape = [{"kind": "wording", "key": "completion_deadline", "evidence": MSG}]
    result = second_reply(empty(deviations=[cap_deviation(MSG)]), applied=old_shape)
    assert result.deviations == [] and "Dropped a request that is already applied to the draft." in result.notes


def test_a_whole_clause_request_is_matched_by_the_users_words_as_before():
    applied = [{"kind": "clause", "key": "suspension", "evidence": "drop suspension"}]
    action = {"clause_key": "suspension", "action": "exclude", "reason": "r", "basis": "comment", "evidence": "drop suspension"}
    result = interpret_request(TS, library_for({}, None, None, TS), FakeClient(empty(clause_actions=[action])),
                               conversation=[{"role": "user", "content": "drop suspension"}], applied_entries=applied)
    assert result.clause_actions == []


# ---------------------------------------------------------------- telling parts of a clause apart
def test_two_quotes_are_another_part_when_their_own_words_differ():
    assert _another_part(RATE, CAP) is True
    assert _another_part(RATE, "at the rate of 0.5 (zero point five) percent of the Contract Price per day") is False
    assert _another_part(RATE, "0.05 (zero point zero five) percent") is False, "one quote inside the other"
    assert _another_part(RATE, "") is False and _another_part("", CAP) is False, "no quote says nothing"
    assert _another_part("percent of the contract", "the percent contract of") is False, "only plain words: nothing to tell them apart"


# ---------------------------------------------------------------- what the model is told
def test_the_prompt_says_each_request_has_its_own_evidence_and_done_covers_only_the_request_it_describes():
    flat = " ".join(SYSTEM_PROMPT.split())
    for phrase in ("A user message may hold several requests", "Give each request its own evidence", "never the whole message",
                   "is done only for the request it describes", "is not done until it has an \"Applied to the draft:\" line of its own"):
        assert phrase in flat, phrase


def test_the_caps_on_damages_are_term_sheet_settings_and_a_request_to_change_them_is_a_question():
    flat = " ".join(SYSTEM_PROMPT.split())
    for phrase in ("Cap on delay damages", "Cap on total damages deducted", "are term sheet settings, not wording", "make no deviation and no exclusion",
                   "The cap on delay damages is a setting on the Term sheet page"):
        assert phrase in flat, phrase
    assert "\\" not in SYSTEM_PROMPT


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} multi-request tests passed.")
