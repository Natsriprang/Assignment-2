"""Tests for keeping an Apply final and the model's mistakes out of the proposals: what is applied is never proposed again (B), the
figure a request moves TO is the one written (D), a provision must contain a word of the request (C), a clause is included only when
its own subject is named (E), and the model is told what is applied (A). Run: python -m tests.test_stability"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.interpret import (SYSTEM_PROMPT, Interpretation, UnmappedRequest, _content_stems, _names_clause, _same_request, _stem, interpret_request,
                          settle, validate)
from core.draft_state import library_for
from core.figures import target_figures
from core.wording import find_unit
from tests.test_interpret import FakeClient, action, dev, empty, sample_term_sheet

QUOTE = "at the rate of 0.05 (zero point zero five) percent of the Contract Price per day"
NOW = "at the rate of 0.03 (zero point zero three) percent of the Contract Price per day"
YES = "Yes, by \u201creduce delay damage to 0.03%\u201d I meant the 'Completion Deadline' clause."
OLD = find_unit(next(c for c in library_for({}) if c.key == "completion_deadline"), QUOTE)[1]
NEW = OLD.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)")
EDIT_LD = {"id": "ld", "clause_key": "completion_deadline", "change_type": "modify", "old": OLD, "new": NEW, "summary": "s"}
EDIT_FM = {"id": "fm", "clause_key": "force_majeure", "change_type": "remove", "old": "7) epidemic.", "new": "", "summary": "s"}
APPLIED = [{"kind": "wording", "key": "completion_deadline", "evidence": "reduce delay damage to 0.03%"},
           {"kind": "wording", "key": "force_majeure", "evidence": "remove epidemic from clause"},
           {"kind": "clause", "key": "suspension", "evidence": "drop suspension", "action": "exclude"}]


def after_apply():
    return library_for({}, edits=[EDIT_LD, EDIT_FM])


# ---------------------------------------------------------------- D: the figure a request moves to
def test_the_figure_a_request_moves_to():
    assert target_figures("Reduce the delay damage from 0.05% to 0.03%.") == {0.03}
    assert target_figures(YES) == {0.03} and target_figures("make it 15 days") == {15.0} and target_figures("change 30 days to 45 days") == {45.0}
    assert target_figures("reduce it to 0.03% per day or 0.02%") == {0.03, 0.02} and target_figures("no figures") == set()


def test_a_request_that_is_already_in_the_clause_is_not_reversed_by_the_figure_the_model_mentions_as_the_old_one():
    for new_text in ("", NEW.replace("Unless otherwise", "Unless otherwise expressly")):
        raw = empty(deviations=[dev("completion_deadline", NOW, change="Reduce the delay damage from 0.05% to 0.03%.", evidence=YES,
                                    term="delay damage", match="confirmed_by_user", new_text=new_text)])
        result = validate(raw, after_apply(), YES, "Question: 'Completion Deadline' ...")
        assert result.deviations == [], [d.new_text[-60:] for d in result.deviations]
        assert any("already has that wording" in n for n in result.notes)


def test_the_figure_is_still_written_when_the_clause_does_not_have_it_yet():
    raw = empty(deviations=[dev("completion_deadline", QUOTE, change="Reduce the delay damage from 0.05% to 0.03%.", evidence="reduce delay damage to 0.03%",
                                term="delay damage", new_text="")])
    d = validate(raw, library_for({}), "reduce delay damage to 0.03%").deviations[0]
    assert d.written_by == "figure" and "0.03 (zero point zero three)" in d.new_text and "0.05 (zero point zero five)" not in d.new_text


# ---------------------------------------------------------------- B: what is applied is never proposed again
def test_the_same_request_is_the_same_words_or_the_words_inside_a_longer_answer():
    assert _same_request("reduce delay damage to 0.03%", YES) and _same_request("Drop Suspension", "drop  suspension")
    assert not _same_request("reduce delay damage to 0.03%", "reduce delay damage to 0.04%") and not _same_request("", "x") and not _same_request("ab", "abc ab cd")


def test_whatever_the_model_lists_again_for_an_applied_request_is_dropped_in_every_list():
    from ai.interpret import ClauseAction, Deviation
    r = Interpretation()
    r.deviations = [Deviation("completion_deadline", "s", "reduce", YES, "modify", QUOTE, True, OLD, "x"),
                    Deviation("completion_deadline", "s", "other", "make the damages 0.04%", "modify", QUOTE, True, OLD, "y")]
    r.clause_actions = [ClauseAction("suspension", "exclude", "r", "comment", "drop suspension", True)]
    r.unmapped_requests = [UnmappedRequest("remove epidemic from clause", "remove epidemic from clause", True),
                           UnmappedRequest("add a drone clause", "add a drone clause", True)]
    settle(r, after_apply(), applied_entries=APPLIED)
    assert [d.evidence for d in r.deviations] == ["make the damages 0.04%"], "a different request about the same sentence is new"
    assert r.clause_actions == [] and [u.request for u in r.unmapped_requests] == ["add a drone clause"]
    assert sum("already applied" in n for n in r.notes) == 3


def test_a_deviation_for_another_clause_with_the_same_words_is_not_dropped():
    from ai.interpret import Deviation
    r = Interpretation()
    r.deviations = [Deviation("suspension", "s", "reduce", "reduce delay damage to 0.03%", "modify", "q", True, "o", "n")]
    assert len(settle(r, after_apply(), applied_entries=APPLIED).deviations) == 1


def test_an_applied_request_is_dropped_through_the_call_too_and_comes_back_when_it_is_no_longer_applied():
    raw = empty(deviations=[dev("force_majeure", "3) protests and/or other strikes or labor disputes; or", change_type="remove_part", change="Remove epidemic from clause.",
                                evidence="remove epidemic from clause", term="force majeure", new_text="")])
    conversation = [{"role": "user", "content": "remove epidemic from clause"}]
    kept = interpret_request(sample_term_sheet(), after_apply(), FakeClient(raw), conversation=conversation, applied_entries=APPLIED)
    assert kept.deviations == [] and kept.unmapped_requests == []
    undone = interpret_request(sample_term_sheet(), after_apply(), FakeClient(raw), conversation=conversation, applied_entries=[])
    assert undone.deviations == [] and len(undone.unmapped_requests) == 1, "not applied any more: the mismatch check (C) turns it into a question"


# ---------------------------------------------------------------- C: the provision must contain a word of the request
def test_a_provision_the_request_is_not_about_becomes_a_question_not_a_proposal():
    raw = empty(deviations=[dev("force_majeure", "3) protests and/or other strikes or labor disputes; or", change_type="remove_part", change="Remove epidemic from clause.",
                                evidence="remove epidemic from clause", term="force majeure", match="same_term", new_text="")])
    result = validate(raw, after_apply(), "remove epidemic from clause")
    assert result.deviations == [] and len(result.unmapped_requests) == 1
    u = result.unmapped_requests[0]
    assert u.candidate_key == "force_majeure" and u.candidate_quote == "3) protests and/or other strikes or labor disputes; or" and u.evidence_verified
    assert any("does not contain the words of the request" in n for n in result.notes)


def test_a_provision_that_has_a_word_of_the_request_is_proposed():
    for key, quote, evidence, term, kind in (("force_majeure", "7) epidemic.", "exclude epidemics and lockdowns for payment", "force majeure", "remove_part"),
                                             ("completion_deadline", QUOTE, "reduce the delay damages to 0.03%", "liquidated damages", "modify")):
        library = library_for({})
        raw = empty(deviations=[dev(key, quote, change_type=kind, change="c", evidence=evidence, term=term, new_text="")])
        assert validate(raw, library, evidence).deviations, evidence


def test_a_request_with_only_instruction_words_cannot_be_checked_and_passes():
    assert _content_stems("make it 15 please") == set() and _content_stems("change it to 0.03%") == set()
    raw = empty(deviations=[dev("completion_deadline", QUOTE, change="c", evidence="change it to 0.03%", term="liquidated damages", new_text="")])
    assert validate(raw, library_for({}), "change it to 0.03%").deviations, "no word to compare: the model's choice stands"


def test_a_provision_the_user_confirmed_in_answer_to_a_question_is_not_checked():
    raw = empty(deviations=[dev("completion_deadline", QUOTE, change="c", evidence="reduce default interest", term="default interest",
                                match="confirmed_by_user", new_text="")])
    convo_assistant = "Question: The closest provision is 'Completion Deadline'. Is that what you meant?"
    result = validate(raw, library_for({}), "reduce default interest to 0.03%", convo_assistant)
    assert len(result.deviations) == 1


# ---------------------------------------------------------------- E: a clause is included only when its subject is named
OWNER = "Owner\u2019s Representations and Warranties (Optional)"


def test_the_stems_of_singular_and_plural_agree():
    assert _stem("damage") == _stem("damages") and _stem("warranty") == _stem("warranties") and _stem("epidemic") == _stem("epidemics")


def test_a_new_clause_that_shares_one_word_with_an_optional_clause_is_a_question():
    raw = empty(clause_actions=[action("owner_representations", "include", "add a warranty clause",
                                       reason="'Owner\u2019s Representations and Warranties' is the only relevant optional clause.")])
    result = validate(raw, library_for({}), "add a warranty clause")
    assert result.clause_actions == [] and len(result.unmapped_requests) == 1
    u = result.unmapped_requests[0]
    assert (u.candidate_key, u.evidence, u.candidate_change) == ("owner_representations", "add a warranty clause", f"Add the '{OWNER}' clause")
    assert u.candidate_quote.startswith("The Owner represents and warrants")


def test_a_request_that_names_the_clause_includes_it():
    for evidence in ("add owner's representations", "add the owner representations and warranties clause", "owner representations please"):
        raw = empty(clause_actions=[action("owner_representations", "include", evidence)])
        assert [a.clause_key for a in validate(raw, library_for({}), evidence).clause_actions] == ["owner_representations"], evidence


def test_the_users_yes_to_the_question_includes_it_and_a_no_does_not():
    yes = "Yes, by \u201cadd a warranty clause\u201d I meant the 'Owner\u2019s Representations and Warranties (Optional)' clause."
    no = "No, by \u201cadd a warranty clause\u201d I did not mean the 'Owner\u2019s Representations and Warranties (Optional)' clause."
    assert len(validate(empty(clause_actions=[action("owner_representations", "include", yes)]), library_for({}), yes).clause_actions) == 1
    result = validate(empty(clause_actions=[action("owner_representations", "include", no)]), library_for({}), no)
    assert result.clause_actions == [] and result.unmapped_requests == [] and any("not what they meant" in n for n in result.notes)


def test_an_exclusion_and_a_condition_for_the_clause_are_not_subject_to_the_subject_check():
    ex = validate(empty(clause_actions=[action("suspension", "exclude", "drop the stop-work thing")]), library_for({}), "drop the stop-work thing")
    assert len(ex.clause_actions) == 1
    cond = validate(empty(clause_actions=[action("owner_representations", "include", "The Owner owns the roof.", basis="term_sheet")]), library_for({}),
                    "additional condition for clause key owner_representations (Owner's Representations): The Owner owns the roof.")
    assert len(cond.clause_actions) == 1


def test_names_clause_by_half_of_its_title_words():
    owner = next(c for c in library_for({}) if c.key == "owner_representations")
    assert not _names_clause("add a warranty clause", owner) and _names_clause("owner representations", owner) and _names_clause("", owner)


# ---------------------------------------------------------------- A: the model is told
def test_the_prompt_says_applied_requests_are_done_and_a_shared_word_is_not_a_match():
    p = " ".join(SYSTEM_PROMPT.split())
    for phrase in ('start with "Applied to the draft:" are requests that are done', "Never list them again, in any list and never as a question",
                   "Use it only when the user names that clause's own subject", "merely shares one word with an optional clause", "is NOT that clause"):
        assert phrase in p, phrase


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} stability tests passed.")
