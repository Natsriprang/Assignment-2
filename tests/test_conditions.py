"""Tests for the additional conditions: the ten boxes, reading them from the Excel, and what the AI is given.
Run: python -m tests.test_conditions"""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from ai.interpret import SYSTEM_PROMPT, drop_roof_owner_false_alarm, interpret_request, term_sheet_text, validate
from core.clause_data import build_library
from core.conditions import CONDITION_CLAUSES, LABELS, condition_lines, conditions_of, strip_condition_prefix
from core.draft_state import library_for
from core.term_sheet_fields import TermSheet, ensure_fields
from core.xlsx_parser import parse_xlsx, parse_xlsx_report
from tests.test_interpret import FakeClient, action, dev, empty, sample_term_sheet
from tests.xlsx_helper import workbook

TEMPLATE = Path(__file__).resolve().parent.parent / "data" / "term_sheet_template_EN.xlsx"


def with_conditions(**conditions):
    ts = sample_term_sheet()
    ts.additional_conditions = dict(conditions)
    return ts


def test_there_is_a_box_for_each_of_the_ten_clauses_the_excel_has_a_row_for():
    keys = {c.key for c in build_library()}
    assert len(CONDITION_CLAUSES) == 10 and all(k in keys for k, _ in CONDITION_CLAUSES)
    assert [label for _, label in CONDITION_CLAUSES][:2] == ["Owner's Representations", "Taxation and Statutory Fees"]
    assert len({k for k, _ in CONDITION_CLAUSES}) == 10 and len(set(LABELS.values())) == 10


def test_the_template_has_a_row_for_each_box_with_the_label_the_page_uses():
    ws = openpyxl.load_workbook(TEMPLATE).active
    labels = {" ".join(str(r[0].value).split()).lower() for r in ws.iter_rows(min_col=2, max_col=2) if r[0].value}
    for key, label in CONDITION_CLAUSES:
        assert label.lower() in labels, label
    ts, report = parse_xlsx_report(TEMPLATE)
    assert report.missing == [] and report.conflicts == [] and ts.additional_conditions == {}        # the rows are empty in the template


def test_the_excel_fills_the_boxes_and_keeps_the_lines():
    ts = parse_xlsx(workbook({}, extra_rows=[("Force Majeure", "Epidemics are not force majeure.\nLockdowns are not either.", None),
                                              ("Suspension of Works", "  ", None), ("Miscellaneous", "Thai text ได้", None)]))
    assert ts.additional_conditions == {"force_majeure": "Epidemics are not force majeure.\nLockdowns are not either.", "miscellaneous": "Thai text ได้"}


def test_a_template_without_these_rows_is_not_an_error():
    ts, report = parse_xlsx_report(workbook({"project_name": "P"}))
    assert ts.additional_conditions == {} and report.missing == [] and not report.nothing_found


def test_a_repeated_row_with_different_text_is_reported_like_any_label():
    ts, report = parse_xlsx_report(workbook({}, extra_rows=[("Force Majeure", "first", None), ("Force Majeure", "second", None)]))
    assert ts.additional_conditions == {"force_majeure": "first"} and len(report.conflicts) == 1 and "Force Majeure" in report.conflicts[0]


def test_only_boxes_with_text_count_and_in_the_order_of_the_template():
    ts = with_conditions(miscellaneous=" last ", owner_representations="first", suspension="   ", force_majeure="")
    assert list(conditions_of(ts)) == ["owner_representations", "miscellaneous"] and conditions_of(ts)["miscellaneous"] == "last"
    assert conditions_of(TermSheet()) == {} and conditions_of(SimpleNamespace()) == {} and conditions_of(None) == {}


def test_the_ai_reads_each_condition_as_one_line_naming_its_clause():
    ts = with_conditions(force_majeure="Epidemics\nare not  force majeure.")
    assert condition_lines(ts) == ["additional condition for clause key force_majeure (Force Majeure): Epidemics are not force majeure."]
    text = term_sheet_text(ts)
    assert text.splitlines()[-1] == condition_lines(ts)[0] and "additional_conditions" not in text
    assert term_sheet_text(sample_term_sheet()).count("additional condition") == 0


def test_a_change_in_a_condition_changes_what_the_check_and_the_analysis_were_made_on():
    assert term_sheet_text(with_conditions(force_majeure="a")) != term_sheet_text(with_conditions(force_majeure="b"))


def test_the_prompt_tells_the_model_to_treat_a_condition_like_a_chat_request():
    for phrase in ('"additional condition for clause key"', "exactly like a request in a user message", "handle each separately",
                   "means the user may want that clause: put a suggestion for it in list 5"):
        assert phrase in " ".join(SYSTEM_PROMPT.split()), phrase


def test_the_condition_is_sent_to_the_model_with_the_term_sheet():
    client = FakeClient(empty())
    interpret_request(with_conditions(force_majeure="Epidemics are not force majeure."), library_for({}), client)
    sent = client.last_kwargs["messages"][1]["content"]
    assert "additional condition for clause key force_majeure (Force Majeure): Epidemics are not force majeure." in sent


def test_a_proposal_made_from_a_condition_is_checked_like_one_made_from_a_message():
    ts = with_conditions(suspension="The Contractor may suspend the Works if an installment is more than 15 days late.")
    sent = term_sheet_text(ts)
    suspension = next(c for c in library_for({}) if c.key == "suspension")
    quote = suspension.items[0].text.split(".")[0][:60]
    raw = empty(deviations=[dev("suspension", "", change_type="add", change="allow suspension if an installment is more than 15 days late",
                                evidence="The Contractor may suspend the Works if an installment is more than 15 days late.",
                                new_text="The Contractor may suspend the Works if an installment is more than 15 (fifteen) days late.")])
    result = validate(raw, library_for({}), sent)
    assert len(result.deviations) == 1 and result.deviations[0].evidence_verified, "the quote is found in the condition line"
    assert result.deviations[0].new_text and result.deviations[0].rewrite_problem == ""
    invented = dict(raw["deviations"][0], evidence="a sentence the user never wrote")
    assert validate(empty(deviations=[invented]), library_for({}), sent).deviations[0].evidence_verified is False


def test_a_condition_on_a_clause_that_is_out_of_the_draft_gives_a_suggestion_to_tick_it():
    library = library_for({})
    owner = next(c for c in library if c.key == "owner_representations")
    assert not owner.included, "an optional clause, out of the draft by default"
    ts = with_conditions(owner_representations="The Owner confirms that it owns the roof.")
    raw = empty(clause_actions=[action("owner_representations", "include", "The Owner confirms that it owns the roof.", basis="term_sheet")])
    result = validate(raw, library, term_sheet_text(ts))
    assert result.clause_actions == [], "an optional clause is never included by the model: the user ticks it"
    assert [(s.clause_key, s.evidence_verified) for s in result.suggestions] == [("owner_representations", True)]


def test_older_term_sheets_get_an_empty_set_of_boxes():
    assert TermSheet().additional_conditions == {} and TermSheet().additional_conditions is not TermSheet().additional_conditions
    old = ensure_fields(SimpleNamespace(project_name="P"))
    assert old.additional_conditions == {}
    junk = ensure_fields(SimpleNamespace(project_name="P", additional_conditions="x"))
    assert junk.additional_conditions == {}


# ---------------------------------------------------------------- the label is never shown
LINE = "additional condition for clause key force_majeure (Force Majeure): exclude epidemic from this clause"


def test_the_label_is_taken_off_a_condition_wherever_the_model_copied_it():
    assert strip_condition_prefix(LINE) == "exclude epidemic from this clause"
    assert strip_condition_prefix("Additional condition for clause key owner_representations (Owner's Representations):  The Owner owns the roof.") == "The Owner owns the roof."
    assert strip_condition_prefix("exclude epidemic from this clause") == "exclude epidemic from this clause" and strip_condition_prefix(None) == ""
    assert strip_condition_prefix(f"first {LINE} then {LINE}") == "first exclude epidemic from this clause then exclude epidemic from this clause"


def test_what_the_user_is_shown_has_no_label_in_it_but_is_still_checked_against_the_term_sheet():
    ts = with_conditions(force_majeure="exclude epidemic from this clause")
    raw = empty(deviations=[dev("force_majeure", "7) epidemic.", change_type="remove_part", change=LINE, evidence=LINE, term="epidemic", new_text="")],
                ambiguities=[f"Which epidemic did you mean in: {LINE}?"],
                unmapped_requests=[{"request": LINE, "evidence": LINE, "candidate_clause_key": "none", "candidate_provision_quote": "",
                                    "why_related": "", "candidate_change": ""}])
    result = validate(raw, library_for({}), term_sheet_text(ts))
    d = result.deviations[0]
    assert d.evidence == "exclude epidemic from this clause" and d.requested_change == "exclude epidemic from this clause" and d.evidence_verified
    assert result.ambiguities == ["Which epidemic did you mean in: exclude epidemic from this clause?"]
    assert result.unmapped_requests[0].request == "exclude epidemic from this clause" and result.unmapped_requests[0].evidence_verified
    assert "additional condition" not in repr(result)


def test_the_clause_text_the_model_quotes_is_left_alone():
    ts = with_conditions(force_majeure="exclude epidemic from this clause")
    raw = empty(deviations=[dev("force_majeure", "7) epidemic.", change_type="remove_part", change="x", evidence=LINE, term="epidemic", new_text="")])
    assert validate(raw, library_for({}), term_sheet_text(ts)).deviations[0].old_text == "7) epidemic."


# ---------------------------------------------------------------- the clause a condition names is a confirmed link
def test_a_condition_for_a_clause_is_not_turned_into_a_question_about_which_clause_is_meant():
    ts = with_conditions(force_majeure="exclude epidemic from this clause")
    for term_match in ("different_term", "same_term"):
        raw = empty(deviations=[dev("force_majeure", "7) epidemic.", change_type="remove_part", change="exclude epidemic", evidence=LINE,
                                    term="epidemics from this clause", match=term_match, new_text="")])
        result = validate(raw, library_for({}), term_sheet_text(ts))
        assert [d.clause_key for d in result.deviations] == ["force_majeure"] and result.unmapped_requests == [], term_match
        assert result.deviations[0].removes


def test_the_same_request_typed_in_the_chat_is_still_checked_for_the_term():
    raw = empty(deviations=[dev("force_majeure", "7) epidemic.", change_type="remove_part", change="exclude epidemic", evidence="exclude epidemic",
                                term="epidemic", match="different_term", new_text="")])
    result = validate(raw, library_for({}), term_sheet_text(sample_term_sheet()) + "\nexclude epidemic")
    assert result.deviations == [] and len(result.unmapped_requests) == 1 and result.unmapped_requests[0].candidate_key == "force_majeure"


def test_a_condition_for_another_clause_does_not_confirm_the_link():
    ts = with_conditions(suspension="exclude epidemic from this clause")
    raw = empty(deviations=[dev("force_majeure", "7) epidemic.", change_type="remove_part", change="exclude epidemic",
                                evidence="exclude epidemic from this clause", term="x", match="different_term", new_text="")])
    result = validate(raw, library_for({}), term_sheet_text(ts))
    assert result.deviations == [] and len(result.unmapped_requests) == 1                                   # it was written for the suspension clause


# ---------------------------------------------------------------- the roof owner is the Owner
def roof_action(ts, evidence="roof_owner: University of Melbourne"):
    from ai.interpret import ClauseAction, Interpretation
    result = Interpretation()
    result.clause_actions = [ClauseAction("owner_representations", "include", "Roof owner is the same as the Owner, and term sheet facts suggest inclusion.", "term_sheet", evidence, True)]
    return drop_roof_owner_false_alarm(result, ts)


def test_a_roof_owner_that_is_the_owner_does_not_add_the_owners_representations():
    for roof, owner in (("University of Melbourne", "University of Melbourne"), ("The University of Melbourne", "University of Melbourne"),
                        ("UNIVERSITY OF MELBOURNE", "university of  melbourne"), ("Solar Owner Co., Ltd.", "Solar Owner Company Limited")):
        ts = sample_term_sheet(roof_owner=roof, owner=owner)
        result = roof_action(ts, f"roof_owner: {roof}")
        assert result.clause_actions == [] and any("roof owner is the same party as the Owner" in n for n in result.notes), (roof, owner)


def test_a_different_roof_owner_becomes_a_suggestion_and_a_condition_for_that_clause_still_adds_it():
    ts = sample_term_sheet(roof_owner="Siam Roof Holdings Co., Ltd.", owner="University of Melbourne")
    result = roof_action(ts, "roof_owner: Siam Roof Holdings Co., Ltd.")
    assert result.clause_actions == [] and [s.clause_key for s in result.suggestions] == ["owner_representations"]
    same = sample_term_sheet(roof_owner="University of Melbourne", owner="University of Melbourne")
    from_condition = roof_action(same, "additional condition for clause key owner_representations (Owner's Representations): The Owner confirms it owns the roof.")
    assert from_condition.clause_actions == [] or len(from_condition.clause_actions) == 1
    nobody = roof_action(sample_term_sheet(), "roof_owner: x")
    assert nobody.clause_actions == [] and nobody.suggestions == [], "no roof owner given: nothing to suggest"


def test_a_suggestion_for_a_roof_owner_that_is_the_owner_is_dropped_too():
    from ai.interpret import Interpretation, Suggestion
    ts = sample_term_sheet(roof_owner="The University of Melbourne", owner="University of Melbourne")
    result = Interpretation()
    result.suggestions = [Suggestion("owner_representations", "x", "roof_owner: The University of Melbourne", True)]
    assert drop_roof_owner_false_alarm(result, ts).suggestions == []


def test_the_guard_is_applied_in_the_call():
    ts = sample_term_sheet(roof_owner="University of Melbourne", owner="University of Melbourne")
    raw = empty(clause_actions=[action("owner_representations", "include", "roof_owner: University of Melbourne", basis="term_sheet")])
    result = interpret_request(ts, library_for({}), FakeClient(raw))
    assert result.clause_actions == [] and result.suggestions == [] and any("same party as the Owner" in n for n in result.notes)


def test_the_prompt_says_the_link_is_confirmed_and_to_compare_the_roof_owner():
    p = " ".join(SYSTEM_PROMPT.split())
    for phrase in ('the link to the clause is already confirmed', 'term_match to "confirmed_by_user"', 'never including the words "additional condition for clause key',
                   "Compare roof_owner with owner_name yourself, word by word", "return no suggestion",
                   "which you never add yourself and whose text you never write", "the user decides by ticking it",
                   "Never include a clause because of a term sheet fact: that is a suggestion (list 5), not an action"):
        assert phrase in p, phrase


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} additional condition tests passed.")
