"""Tests for keeping an Apply final and the model's mistakes out of the proposals: what is applied is never proposed again (B), the
figure a request moves TO is the one written (D), a provision must contain a word of the request (C), a clause is included only when
its own subject is named (E), and the model is told what is applied (A). Run: python -m tests.test_stability"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.interpret import (SYSTEM_PROMPT, Interpretation, UnmappedRequest, _content_stems, _names_clause, _same_request, _stem, _tidy_quote,
                          interpret_request, settle, term_sheet_text, validate)
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
    assert _same_request(YES, "reduce delay damage to 0.03%"), "an answer that quotes the stored request is that request"
    assert not _same_request("reduce delay damage to 0.03%", "reduce delay damage to 0.04%") and not _same_request("", "x") and not _same_request("ab", "abc ab cd")


def test_a_later_message_that_contains_the_applied_words_and_asks_for_more_is_a_new_request():
    later = "remove epidemic from clause and also take out the strikes point"
    assert not _same_request(later, "remove epidemic from clause")
    assert not _same_request("drop suspension and the inspection clause too", "drop suspension")
    r = Interpretation()
    from ai.interpret import Deviation
    point = "3) protests and/or other strikes or labor disputes; or"
    r.deviations = [Deviation("force_majeure", "s", "take out strikes", later, "remove_part", point, True, point, "")]
    settle(r, library_for({}), applied_entries=[{"kind": "wording", "key": "force_majeure", "evidence": "remove epidemic from clause"}])
    assert len(r.deviations) == 1 and not any("already applied" in n for n in r.notes)


def test_a_no_answer_that_quotes_the_applied_words_is_also_that_request():
    no = "No, by \u201creduce delay damage to 0.03%\u201d I did not mean the 'Force Majeure' clause."
    assert _same_request(no, "reduce delay damage to 0.03%")


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


def test_a_request_that_names_the_clause_gives_a_suggestion_to_tick_it_never_an_action():
    for evidence in ("add owner's representations", "add the owner representations and warranties clause", "owner representations please"):
        raw = empty(clause_actions=[action("owner_representations", "include", evidence, reason="The user names this optional clause.")])
        result = validate(raw, library_for({}), evidence)
        assert result.clause_actions == [] and [s.clause_key for s in result.suggestions] == ["owner_representations"], evidence
        assert result.suggestions[0].reason == "The user names this optional clause." and result.suggestions[0].evidence_verified


def test_the_model_cannot_dress_an_include_as_the_term_sheets_to_get_round_the_check():
    raw = empty(clause_actions=[action("owner_representations", "include", "add a warranty clause", basis="term_sheet",
                                       reason="The user requested to add a warranty clause, potentially covering representations from the owner.")])
    result = validate(raw, library_for({}), "add a warranty clause")
    assert result.clause_actions == [] and result.suggestions == [], "the words do not name the clause"
    assert len(result.unmapped_requests) == 1 and result.unmapped_requests[0].candidate_key == "owner_representations"


def test_the_users_yes_to_the_question_gives_the_suggestion_and_a_no_gives_nothing():
    yes = "Yes, by \u201cadd a warranty clause\u201d I meant the 'Owner\u2019s Representations and Warranties (Optional)' clause."
    no = "No, by \u201cadd a warranty clause\u201d I did not mean the 'Owner\u2019s Representations and Warranties (Optional)' clause."
    got = validate(empty(clause_actions=[action("owner_representations", "include", yes)]), library_for({}), yes)
    assert got.clause_actions == [] and [s.clause_key for s in got.suggestions] == ["owner_representations"]
    result = validate(empty(clause_actions=[action("owner_representations", "include", no)]), library_for({}), no)
    assert result.clause_actions == [] and result.suggestions == [] and result.unmapped_requests == [] and any("not what they meant" in n for n in result.notes)


def test_an_exclusion_of_a_standard_clause_is_still_an_action_and_a_standard_clause_can_be_brought_back():
    ex = validate(empty(clause_actions=[action("suspension", "exclude", "drop the stop-work thing")]), library_for({}), "drop the stop-work thing")
    assert len(ex.clause_actions) == 1
    library = library_for({"suspension": False})
    back = validate(empty(clause_actions=[action("suspension", "include", "bring back suspension of works")]), library, "bring back suspension of works")
    assert [(a.clause_key, a.action) for a in back.clause_actions] == [("suspension", "include")]
    cond = validate(empty(clause_actions=[action("owner_representations", "include", "The Owner owns the roof.", basis="term_sheet")]), library_for({}),
                    "additional condition for clause key owner_representations (Owner's Representations): The Owner owns the roof.")
    assert cond.clause_actions == [] and [s.clause_key for s in cond.suggestions] == ["owner_representations"]


def test_names_clause_by_half_of_its_title_words():
    owner = next(c for c in library_for({}) if c.key == "owner_representations")
    assert not _names_clause("add a warranty clause", owner) and _names_clause("owner representations", owner) and _names_clause("", owner)


# ---------------------------------------------------------------- a link the user refused stays refused
WARRANTY = "add a warranty clause"
REFUSED = [{"key": "owner_representations", "evidence": WARRANTY}]


def test_a_clause_the_user_said_no_to_is_not_proposed_again_and_the_request_stays():
    from ai.interpret import ClauseAction
    r = Interpretation()
    r.clause_actions = [ClauseAction("owner_representations", "include", "only relevant optional clause", "comment", WARRANTY, True)]
    settle(r, library_for({}), declined=REFUSED)
    assert r.clause_actions == [] and [(u.request, u.candidate_key) for u in r.unmapped_requests] == [(WARRANTY, "")]
    assert any("had refused" in n for n in r.notes)


def test_a_question_about_a_refused_clause_loses_its_candidate_and_is_not_doubled():
    r = Interpretation()
    r.unmapped_requests = [UnmappedRequest(WARRANTY, WARRANTY, True, "owner_representations", "The Owner represents", "shares a word", "Add the clause")]
    settle(r, library_for({}), declined=REFUSED)
    assert [(u.request, u.candidate_key, u.candidate_quote, u.why_related) for u in r.unmapped_requests] == [(WARRANTY, "", "", "")]
    from ai.interpret import ClauseAction
    again = Interpretation()
    again.unmapped_requests = [UnmappedRequest(WARRANTY, WARRANTY, True)]
    again.clause_actions = [ClauseAction("owner_representations", "include", "r", "comment", WARRANTY, True)]
    settle(again, library_for({}), declined=REFUSED)
    assert len(again.unmapped_requests) == 1, "the model also listing the plain request does not make two"


def test_a_refusal_is_only_about_that_clause_and_those_words():
    from ai.interpret import ClauseAction
    r = Interpretation()
    r.clause_actions = [ClauseAction("owner_representations", "include", "r", "comment", "add owner representations", True),
                        ClauseAction("suspension", "exclude", "r", "comment", WARRANTY, True)]
    r.unmapped_requests = [UnmappedRequest("add a drone clause", "add a drone clause", True, "owner_representations", "q", "w", "c")]
    settle(r, library_for({}), declined=REFUSED)
    assert len(r.clause_actions) == 2, "other words, or another clause, are not refused"
    assert r.unmapped_requests[0].candidate_key == "owner_representations"


def test_a_refusal_holds_through_the_call():
    raw = empty(clause_actions=[action("owner_representations", "include", WARRANTY, reason="only relevant optional clause")])
    result = interpret_request(sample_term_sheet(), library_for({}), FakeClient(raw), conversation=[{"role": "user", "content": WARRANTY}], declined=REFUSED)
    assert result.clause_actions == [] and [u.candidate_key for u in result.unmapped_requests] == [""]


# ---------------------------------------------------------------- a quote is used as the clause has it
def test_a_quote_with_a_full_stop_the_clause_does_not_have_is_used_without_it():
    text = "6) any change in law or government action; or\n7) epidemic."
    assert _tidy_quote("any change in law or government action.", text) == "any change in law or government action"
    assert _tidy_quote("\u201cepidemic.\u201d", text) == "epidemic" and _tidy_quote("epidemic.", text) == "epidemic."
    assert _tidy_quote("not there at all.", text) == "not there at all."
    raw = empty(deviations=[dev("force_majeure", "any change in law or government action.", change_type="remove_part", change="remove any change in law or government action",
                                evidence="also remove any change in law or government action from force majeure clauses", term="force majeure", new_text="")])
    result = validate(raw, library_for({}), "also remove any change in law or government action from force majeure clauses")
    d = result.deviations[0]
    assert d.removes and d.old_text == "6) any change in law or government action; or" and d.rewrite_problem == ""


def test_the_reason_for_not_finding_the_sentence_is_given():
    library = library_for({})
    c = next(c for c in library if c.key == "force_majeure")
    c.items[1].lettered.append(c.items[1].lettered[5])
    raw = empty(deviations=[dev("force_majeure", "any change in law or government action", change_type="remove_part", change="x",
                                evidence="remove any change in law or government action", term="force majeure", new_text="")])
    d = validate(raw, library, "remove any change in law or government action").deviations[0]
    assert d.old_text == "" and d.rewrite_problem == "That wording is in more than one place in the clause."


# ---------------------------------------------------------------- a candidate that is a clause drafted in this session
DRAFTED = [{"key": "drafted_1", "title": "Warranty", "sentences": ["The Contractor shall repair any defect within 7 (seven) days."], "before": "end"}]


def test_a_question_can_name_a_clause_drafted_in_the_session_and_its_text_is_written_with_its_title():
    from ai.interpret import candidate_question, result_lines
    library = library_for({}, None, DRAFTED)
    quote = "The Contractor shall repair any defect within 7 (seven) days."
    raw = empty(unmapped_requests=[{"request": "shorter repair", "evidence": "shorter repair", "candidate_clause_key": "drafted_1",
                                    "candidate_provision_quote": quote, "why_related": "both set a repair period", "candidate_change": "shorten it"}])
    result = validate(raw, library, "shorter repair")
    u = result.unmapped_requests[0]
    assert u.candidate_key == "drafted_1" and u.candidate_quote == quote
    assert "'Warranty'" in candidate_question(u, "Warranty")
    questions = result_lines(result, library)[1]
    assert len(questions) == 1 and "'Warranty'" in questions[0]


# ---------------------------------------------------------------- the installment rows are not something the model is asked about
def sheet_with_installments():
    from core.term_sheet_fields import Installment
    ts = sample_term_sheet()
    ts.installments = [Installment("1", "10", condition="Within 10 working days of both Parties signing this Agreement.",
                                   required_docs="(1) Electrical drawings and Single Line Diagram delivered to the Owner (2) Shop Drawings"),
                       Installment("7", "40", condition="Full handover under this Agreement.", required_docs="(1) Inspection Report, Test & Commissioning Report")]
    return ts


def test_the_model_is_not_given_the_installment_rows_but_the_rest_of_the_term_sheet_is():
    ts = sheet_with_installments()
    full, seen = term_sheet_text(ts), term_sheet_text(ts, for_model=True)
    assert "installment 1:" in full and "Electrical drawings" in full, "the page's own checks and staleness still see the rows"
    assert "installment" not in seen and "Electrical drawings" not in seen and "Inspection Report" not in seen
    assert seen.splitlines()[0] == full.splitlines()[0] and "owner_name:" in seen
    client = FakeClient(empty())
    interpret_request(ts, library_for({}), client)
    sent = client.last_kwargs["messages"][1]["content"]
    assert "installment 1:" not in sent and "Supporting documents" not in sent and "Electrical drawings" not in sent.split("<term_sheet>")[1].split("</term_sheet>")[0]


def test_a_quote_from_an_installment_row_cannot_be_verified_so_it_is_never_trusted():
    ts = sheet_with_installments()
    ev = "installment 1: 10% | Within 10 working days of both Parties signing this Agreement. | (1) Electrical drawings"
    raw = empty(deviations=[dev("price_payment", "", change_type="add", change="Add conditions for Installment 1 payment", evidence=ev,
                                new_text="(1) Electrical drawings and Single Line Diagram delivered to the Owner.")])
    result = interpret_request(ts, library_for({}), FakeClient(raw))
    assert [d.evidence_verified for d in result.deviations] == [False], "the model did not see the row, so a quote of it is not found"


def test_the_prompt_says_installment_rows_and_term_sheet_values_are_never_requests():
    p = " ".join(SYSTEM_PROMPT.split())
    assert "The term sheet lines for installments, and every other term sheet value, are filled into the contract by the system" in p


# ---------------------------------------------------------------- a reply that names a clause the draft no longer has
def test_a_reply_that_names_a_rejected_drafted_clause_is_cleaned_before_it_is_shown():
    from ai.interpret import ClauseAction, Deviation, Suggestion, forget_unknown_clauses
    library = library_for({})                                                    # no drafted clause any more
    r = Interpretation()
    r.deviations = [Deviation("drafted_6", "s", "r", "e", "modify", "q", True, "old", "new"), Deviation("suspension", "s", "r", "e", "modify", "q", True, "o", "n")]
    r.clause_actions = [ClauseAction("drafted_6", "exclude", "r", "comment", "e", True)]
    r.suggestions = [Suggestion("drafted_6", "r"), Suggestion("owner_representations", "r")]
    r.unmapped_requests = [UnmappedRequest("req", "req", True, "drafted_6", "quote", "why", "change"), UnmappedRequest("keep", "keep", True, "suspension", "q", "w", "c")]
    forget_unknown_clauses(r, library)
    assert [d.clause_key for d in r.deviations] == ["suspension"] and r.clause_actions == [] and [s.clause_key for s in r.suggestions] == ["owner_representations"]
    assert [(u.request, u.candidate_key) for u in r.unmapped_requests] == [("req", ""), ("keep", "suspension")]
    from ai.interpret import result_lines
    result_lines(r, library)                                                     # no KeyError


# ---------------------------------------------------------------- A: the model is told
def test_the_prompt_says_applied_requests_are_done_and_a_shared_word_is_not_a_match():
    p = " ".join(SYSTEM_PROMPT.split())
    for phrase in ('start with "Applied to the draft:" are requests that are done', "Never list them again, in any list and never as a question",
                   "Never use it for an optional clause", "put a suggestion in list 5 instead", "merely shares one word with an optional clause", "is NOT that clause",
                   "they are never requests to change a clause"):
        assert phrase in p, phrase


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} stability tests passed.")
