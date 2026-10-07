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


def test_a_cap_on_damages_is_part_of_its_sentence_and_a_request_about_it_is_an_ordinary_wording_change():
    flat = " ".join(SYSTEM_PROMPT.split())
    for phrase in ("A cap on damages", "is part of the sentence it is written in", "use \"remove_part\" to take the cap out", "\"modify\" to change its figure",
                   "Do not answer it with a question about where the cap is set"):
        assert phrase in flat, phrase
    assert "term sheet settings" not in flat and "setting on the Term sheet page" not in flat, "no question that has no answer buttons"
    assert "\\" not in SYSTEM_PROMPT


# ---------------------------------------------------------------- a question is asked once
ASKED = "The cap on delay damages is a setting on the Term sheet page. Do you want to change it there?"
CAP_CONVERSATION = [{"role": "user", "content": "remove limit"}, {"role": "assistant", "content": f"Question: {ASKED}"}, {"role": "user", "content": "no"}]
BASE = library_for({}, None, None, TS)


def reply_to_the_answer(payload, conversation=CAP_CONVERSATION):
    return interpret_request(TS, BASE, FakeClient(payload), conversation=conversation)


def cap_change(match="same_term"):
    return dev("completion_deadline", CAP, change_type="remove_part", change="remove cap on delay damages", evidence="change it here", term="delay damage", match=match)


def test_a_question_the_user_has_answered_is_not_listed_again_when_the_reply_acts_on_the_answer():
    result = reply_to_the_answer(empty(deviations=[cap_change()], ambiguities=[ASKED]))
    assert [d.requested_change for d in result.deviations] == ["remove cap on delay damages"]
    assert result.ambiguities == [] and "Dropped a question that was already asked and answered." in result.notes


def test_a_question_asked_again_in_nearly_the_same_words_is_dropped_too():
    reworded = "The cap on delay damages is a setting on the Term sheet page. Would you like to change it there?"
    assert reply_to_the_answer(empty(deviations=[cap_change()], ambiguities=[reworded])).ambiguities == []


def test_a_new_question_stays():
    other = "Is the 0.5% per day or per year?"
    assert reply_to_the_answer(empty(deviations=[cap_change()], ambiguities=[ASKED, other])).ambiguities == [other]


def test_a_reply_with_nothing_else_to_say_keeps_its_question_because_the_answer_may_not_have_been_clear():
    result = reply_to_the_answer(empty(ambiguities=[ASKED]))
    assert result.ambiguities == [ASKED] and result.deviations == []


def test_a_question_not_yet_answered_is_not_counted_as_asked():
    waiting = [{"role": "user", "content": "remove limit"}, {"role": "assistant", "content": f"Question: {ASKED}"}]
    assert reply_to_the_answer(empty(deviations=[cap_change()], ambiguities=[ASKED]), waiting).ambiguities == [ASKED], "no message of the user came after it"


# ---------------------------------------------------------------- a short answer typed to a question
def test_a_short_answer_to_a_question_does_not_need_the_words_of_the_provision():
    result = reply_to_the_answer(empty(deviations=[cap_change()]))
    assert [d.requested_change for d in result.deviations] == ["remove cap on delay damages"] and not result.unmapped_requests


def test_the_same_words_are_checked_when_they_answer_nothing():
    no_question = [{"role": "user", "content": "change it here"}]
    result = reply_to_the_answer(empty(deviations=[cap_change()]), no_question)
    assert result.deviations == [] and len(result.unmapped_requests) == 1, "turned into a question: the provision does not contain the words"


def test_a_long_message_is_checked_even_when_it_comes_after_a_question():
    long_words = "please change the colour of the cover page to something calmer and quieter"
    conversation = CAP_CONVERSATION[:2] + [{"role": "user", "content": long_words}]
    long_dev = dev("completion_deadline", CAP, change_type="remove_part", change="remove cap on delay damages", evidence=long_words, term="delay damage")
    result = reply_to_the_answer(empty(deviations=[long_dev]), conversation)
    assert result.deviations == [], "more than a short answer: the words are checked"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} multi-request tests passed.")
