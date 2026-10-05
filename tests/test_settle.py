"""Tests for keeping the result steady between replies: a proposal not yet applied or rejected stays, and a question about a change
that is proposed or already in the draft is dropped. Run: python -m tests.test_settle"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.interpret import Deviation, Interpretation, UnmappedRequest, SYSTEM_PROMPT, settle, validate
from core.draft_state import library_for
from core.wording import find_unit
from tests.test_interpret import empty

QUOTE = "at the rate of 0.05 (zero point zero five) percent of the Contract Price per day"
ASK = "reduce the delay damage to 0.03%"


def lib(edits=None):
    return library_for({}, edits=edits)


def old_ld(library=None):
    return find_unit(next(c for c in (library or lib()) if c.key == "completion_deadline"), QUOTE)[1]


def pending(figure="0.03", new_figure="0.03 (zero point zero three)"):
    return Deviation("completion_deadline", "delay damages rate", f"Reduce the delay damages rate to {figure}% per day", ASK.replace("0.03", figure),
                     "modify", QUOTE, True, old_ld(), old_ld().replace("0.05 (zero point zero five)", new_figure))


def question(text="reduce the delay damages under completion deadline to 0.03% per day", key="completion_deadline"):
    return UnmappedRequest(text, text, False, key, QUOTE, "similar subject", "reduce it to 0.03% per day")


def result(**kw):
    r = Interpretation()
    for k, v in kw.items():
        setattr(r, k, v)
    return r


# ---------------------------------------------------------------- the reported case
def test_a_proposal_not_applied_stays_when_the_model_turns_it_into_a_question():
    p = pending()
    r = settle(result(unmapped_requests=[question(), UnmappedRequest("add a two year warranty clause", "add a two year warranty clause")]),
               lib(), [p])
    assert [d.clause_key for d in r.deviations] == ["completion_deadline"] and r.deviations[0].new_text == p.new_text and r.deviations[0].carried
    assert [u.request for u in r.unmapped_requests] == ["add a two year warranty clause"]               # the warranty request is untouched, the question is gone
    assert any("Kept the proposal for 'Completion Deadline'" in n for n in r.notes) and any("already proposed above" in n for n in r.notes)


def test_a_proposal_stays_when_the_new_reply_says_nothing_about_it():
    r = settle(result(unmapped_requests=[UnmappedRequest("add a two year warranty clause", "x")]), lib(), [pending()])
    assert len(r.deviations) == 1 and r.deviations[0].carried and len(r.unmapped_requests) == 1


def test_a_proposal_that_the_model_lists_again_is_not_doubled():
    again = pending()
    r = settle(result(deviations=[again]), lib(), [pending()])
    assert r.deviations == [again] and not again.carried


def test_a_new_proposal_for_the_same_sentence_replaces_the_old_one():
    newer = pending("0.04", "0.04 (zero point zero four)")
    r = settle(result(deviations=[newer]), lib(), [pending()])
    assert r.deviations == [newer] and "0.04" in r.deviations[0].new_text


def test_a_question_with_other_figures_means_the_user_changed_the_request():
    other = question("make the delay damages 0.04% per day")
    other.candidate_change = "make it 0.04% per day"
    r = settle(result(unmapped_requests=[other]), lib(), [pending()])
    assert r.deviations == [] and r.unmapped_requests == [other]


def test_a_question_without_figures_is_kept_and_the_proposal_too():
    q = UnmappedRequest("what about the late payment", "what about the late payment", True, "completion_deadline", QUOTE, "x", "")
    r = settle(result(unmapped_requests=[q]), lib(), [pending()])
    assert len(r.deviations) == 1 and r.unmapped_requests == [q]


def test_a_proposal_whose_sentence_has_since_changed_is_dropped():
    changed = lib([{"id": "x", "clause_key": "completion_deadline", "change_type": "modify", "old": old_ld(),
                    "new": "A completely different sentence.", "summary": "s"}])
    assert settle(result(), changed, [pending()]).deviations == []
    assert settle(result(), lib(), [Deviation("no_such_clause", "s", "r", "e", "modify", "q", True, "old", "new")]).deviations == []


# ---------------------------------------------------------------- an added sentence
def test_an_added_sentence_stays_until_it_is_in_the_clause():
    add = Deviation("completion_deadline", "warranty", "add a 24 months warranty", "add a 24 months warranty", "add", "", True, "",
                    "The warranty period is 24 (twenty-four) months.")
    assert len(settle(result(), lib(), [add]).deviations) == 1
    done = lib([{"id": "x", "clause_key": "completion_deadline", "change_type": "add", "old": "", "new": add.new_text, "summary": "s"}])
    assert settle(result(), done, [add]).deviations == []
    again = Deviation("completion_deadline", "warranty", "r", "e", "add", "", True, "", add.new_text)
    assert settle(result(deviations=[again]), lib(), [add]).deviations == [again]


# ---------------------------------------------------------------- a change already in the draft
def applied_edit():
    p = pending()
    return {"id": "x", "clause_key": "completion_deadline", "change_type": "modify", "old": p.old_text, "new": p.new_text, "summary": "s"}


def test_a_question_about_a_change_already_in_the_draft_is_dropped():
    r = settle(result(unmapped_requests=[question()]), lib([applied_edit()]), [], [applied_edit()])
    assert r.unmapped_requests == [] and any("already in the draft" in n for n in r.notes)


def test_a_question_with_other_figures_or_about_another_clause_is_kept():
    other = question("make the delay damages 0.04% per day")
    other.candidate_change = "make it 0.04% per day"
    elsewhere = question(key="suspension")
    r = settle(result(unmapped_requests=[other, elsewhere]), lib([applied_edit()]), [], [applied_edit()])
    assert r.unmapped_requests == [other, elsewhere]


def test_a_question_without_a_candidate_is_never_dropped_here():
    plain = UnmappedRequest("add a two year warranty clause", "add a two year warranty clause")
    assert settle(result(unmapped_requests=[plain]), lib([applied_edit()]), [], [applied_edit()]).unmapped_requests == [plain]


# ---------------------------------------------------------------- through validate and the prompt
def test_what_validate_returns_is_settled_the_same_way():
    raw = empty(unmapped_requests=[{"request": "reduce the delay damages to 0.03%", "evidence": ASK, "candidate_clause_key": "completion_deadline",
                                    "candidate_provision_quote": QUOTE, "why_related": "similar", "candidate_change": "reduce to 0.03%"}])
    r = settle(validate(raw, lib(), ASK), lib(), [pending()])
    assert len(r.deviations) == 1 and r.unmapped_requests == []


def test_the_prompt_tells_the_model_a_proposal_stands():
    assert "stands until the user applies it, rejects it or asks for something different" in SYSTEM_PROMPT
    assert "never turn it into a question later" in SYSTEM_PROMPT


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} settle tests passed.")
