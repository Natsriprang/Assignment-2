"""Tests for the review round (ai/review.py): two independent reads, only what both reads found is a finding, narrow findings, evidence
checked in two places, fixes checked by code, and the temperature of every call. Run: python -m tests.test_review"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ai.llm as llm
from ai.llm import AIStepError, chat_create
from ai.review import (CHANGES_PROMPT, MAX_FINDINGS, READ_FROM_CHANGES, READ_FROM_TERM_SHEET, TERM_SHEET_PROMPT, Section, build_schema,
                       dependency_findings, review_draft, sections_of)
from core.clauses import Clause, Item
from core.draft_state import library_for

LIBRARY = library_for({})
CLAUSE = next(c for c in LIBRARY if c.key == "completion_deadline")
LD_OLD = next(i.text for i in CLAUSE.items if "liquidated damages" in i.text)
LD_NEW = LD_OLD.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)")
TS_TEXT = "project_name: Rooftop PV\nlimits: delay damages 0.03% per day"
SECTIONS = sections_of(LIBRARY, [("title", "Header title")], ["IN WITNESS", "Owner"])
CHANGES = [{"id": "c1", "kind": "wording_change", "clause": "Completion Deadline", "text": LD_OLD}]


class SeqClient:
    """Returns the payloads one after the other; `refuse_at` is the index (or indexes) of a call the model refuses."""
    def __init__(self, *payloads, refuse_at=()):
        self.payloads, self.calls = list(payloads), []
        self.refuse_at = {refuse_at} if isinstance(refuse_at, int) else set(refuse_at)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        n = len(self.calls)
        self.calls.append(kwargs)
        msg = SimpleNamespace(content=json.dumps(self.payloads[min(n, len(self.payloads) - 1)]), refusal="no" if n in self.refuse_at else None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def finding(kind="term_sheet_mismatch", clause_key="completion_deadline", issue="The damages rate is not what the term sheet says.",
            why="Term sheet: 0.03% per day.", term_sheet_says="delay damages 0.03% per day", quote="0.05 (zero point zero five)",
            other_clause_key="", other_quote="", fix_type="modify", new_text=LD_NEW):
    return {"kind": kind, "clause_key": clause_key, "issue": issue, "why": why, "term_sheet_says": term_sheet_says, "quote": quote,
            "other_clause_key": other_clause_key, "other_quote": other_quote, "fix_type": fix_type, "new_text": new_text}


def first(*findings):
    return {"findings": list(findings)}


def run(client, sections=None, ts_text=TS_TEXT, changes=CHANGES):
    return review_draft(ts_text, SECTIONS if sections is None else sections, client, changes=changes)


def one(payload, sections=None, ts_text=TS_TEXT, changes=CHANGES):
    """The result of a run in which both reads say the same."""
    return run(SeqClient(payload, payload), sections, ts_text, changes)


def pair(p1, p2, **kw):
    return run(SeqClient(p1, p2), **kw)


# ---------------------------------------------------------------- always two calls, two independent reads
def test_two_calls_are_made_even_when_nothing_is_found():
    client = SeqClient(first(), first())
    result = run(client)
    assert len(client.calls) == 2 and result.findings == [] and result.single == [] and result.both_done


def test_the_two_reads_get_the_same_input_and_neither_sees_the_other_ones_answer():
    client = SeqClient(first(finding()), first(finding()))
    run(client)
    users = [c["messages"][1]["content"] for c in client.calls]
    assert users[0] == users[1] and "FINDINGS" not in users[0] and "0.05 (zero point zero five)" in users[0] and "TERM SHEET:" in users[0]


def test_the_two_reads_start_from_opposite_ends():
    client = SeqClient(first(), first())
    run(client)
    assert [c["messages"][0]["content"] for c in client.calls] == [TERM_SHEET_PROMPT, CHANGES_PROMPT]
    assert "start from the term sheet" in TERM_SHEET_PROMPT and "start from the draft" in CHANGES_PROMPT
    assert "start from the draft" not in TERM_SHEET_PROMPT and "start from the term sheet" not in CHANGES_PROMPT


def test_the_changed_sentences_are_listed_and_a_draft_with_no_change_says_so():
    client = SeqClient(first(), first())
    run(client)
    assert "[c1 | a sentence changed or added | clause: Completion Deadline]" in client.calls[0]["messages"][1]["content"]
    client = SeqClient(first(), first())
    run(client, changes=())
    assert "(none: the draft is the standard template)" in client.calls[0]["messages"][1]["content"]


# ---------------------------------------------------------------- only what both reads found is a finding
def test_a_finding_both_reads_made_is_shown():
    result = one(first(finding()))
    f = result.findings[0]
    assert (f.id, f.kind, f.clause_key, f.confirmed, f.route, f.source) == ("f1", "term_sheet_mismatch", "completion_deadline", True, "", "ai")
    assert result.single == []


def test_a_finding_only_one_read_made_is_listed_apart_with_the_read_that_made_it():
    result = pair(first(finding()), first())
    assert result.findings == [] and [(f.issue, f.route) for f in result.single] == [("The damages rate is not what the term sheet says.", READ_FROM_TERM_SHEET)]
    result = pair(first(), first(finding()))
    assert result.findings == [] and [f.route for f in result.single] == [READ_FROM_CHANGES]


def test_quotes_that_overlap_are_the_same_finding():
    longer = "at the rate of 0.05 (zero point zero five) percent"
    assert longer in " ".join(LD_OLD.split())
    result = pair(first(finding()), first(finding(quote=longer)))
    assert len(result.findings) == 1 and result.single == []


def test_findings_about_other_words_other_clauses_or_other_matters_are_not_the_same():
    other_clause = Clause(key="other", title="Other", items=[Item(LD_OLD)], category="general")
    sections = SECTIONS + [Section("other", "Other", LD_OLD, other_clause)]
    result = pair(first(finding()), first(finding(clause_key="other")), sections=sections)
    assert result.findings == [] and len(result.single) == 2
    result = pair(first(finding()), first(finding(term_sheet_says="project_name: Rooftop PV")))
    assert result.findings == [] and len(result.single) == 2, "the same sentence, but a different matter of the term sheet"
    result = pair(first(finding()), first(finding(quote="liquidated damages", fix_type="none", new_text="")))
    assert result.findings == [] and len(result.single) == 2


def test_two_sentences_that_disagree_are_one_finding_whichever_is_named_first():
    sections = [Section("a", "Termination", "The Owner may terminate on 30 (thirty) days notice."),
                Section("b", "Notice", "A notice of termination takes effect after 45 (forty-five) days.")]
    changes = [{"id": "c1", "kind": "wording_change", "clause": "Termination", "text": "The Owner may terminate on 30 (thirty) days notice. A notice of termination takes effect after 45 (forty-five) days."}]
    straight = finding(kind="contradiction", clause_key="a", term_sheet_says="", quote="terminate on 30 (thirty) days notice", other_clause_key="b",
                       other_quote="takes effect after 45 (forty-five) days", fix_type="none", new_text="", issue="Two different notice periods.")
    swapped = finding(kind="contradiction", clause_key="b", term_sheet_says="", quote="takes effect after 45 (forty-five) days", other_clause_key="a",
                      other_quote="terminate on 30 (thirty) days notice", fix_type="none", new_text="", issue="Notice periods differ.")
    result = pair(first(straight), first(swapped), sections=sections, changes=changes)
    f = result.findings[0]
    assert len(result.findings) == 1 and (f.kind, f.clause, f.other_clause, f.fix_type) == ("contradiction", "Termination", "Notice", "none")
    assert f.quote == "terminate on 30 (thirty) days notice" and f.other_quote == "takes effect after 45 (forty-five) days"


def test_findings_are_numbered_and_come_in_the_order_of_the_draft():
    sections = [Section("late", "Late", "The Owner pays within 10 days."), Section("early", "Early", "The Owner pays within 20 days.")]
    changes = [{"id": "c1", "kind": "wording_change", "clause": "x", "text": "The Owner pays within 10 days. The Owner pays within 20 days."}]
    payload = first(finding(clause_key="early", quote="pays within 20 days", fix_type="none", new_text=""),
                    finding(clause_key="late", quote="pays within 10 days", fix_type="none", new_text=""))
    result = one(payload, sections, TS_TEXT, changes)
    assert [(f.id, f.clause_key) for f in result.findings] == [("f1", "late"), ("f2", "early")]


def test_findings_are_capped():
    many = [finding(issue=f"Found {n}.", quote="0.05 (zero point zero five)", term_sheet_says="delay damages 0.03% per day", fix_type="none", new_text="")
            for n in range(MAX_FINDINGS + 3)]
    result = one(first(*many))
    assert len(result.findings) == MAX_FINDINGS and any("Kept the first" in n for n in result.notes)
    assert [f.id for f in result.findings] == [f"f{n}" for n in range(1, MAX_FINDINGS + 1)]


# ---------------------------------------------------------------- the fix the two reads agree on
VARIANT = LD_NEW.replace("percent", "per cent", 1)


def test_the_fix_both_reads_wrote_is_offered():
    f = one(first(finding())).findings[0]
    assert f.fix_type == "modify" and f.old_text == " ".join(LD_OLD.split()) and f.new_text == " ".join(LD_NEW.split()) and f.fix_note == ""


def test_the_fix_of_the_read_that_has_one_is_offered_when_the_other_has_none():
    f = pair(first(finding(fix_type="none", new_text="")), first(finding())).findings[0]
    assert f.fix_type == "modify" and f.new_text == " ".join(LD_NEW.split())
    f = pair(first(finding()), first(finding(fix_type="none", new_text=""))).findings[0]
    assert f.fix_type == "modify"


def test_two_different_fixes_mean_no_fix():
    assert one(first(finding(new_text=VARIANT))).findings[0].fix_type == "modify", "the variant is a valid fix on its own"
    f = pair(first(finding()), first(finding(new_text=VARIANT))).findings[0]
    assert f.fix_type == "none" and f.new_text == "" and "different fixes" in f.fix_note


def test_a_figure_that_is_not_in_the_term_sheet_drops_the_fix_and_keeps_the_finding():
    bad = LD_OLD.replace("0.05 (zero point zero five)", "0.09 (zero point zero nine)")
    f = one(first(finding(new_text=bad))).findings[0]
    assert f.fix_type == "none" and f.new_text == "" and "figure that you did not give" in f.fix_note


def test_a_new_sentence_can_be_added_at_the_end_of_a_clause():
    f = one(first(finding(fix_type="add", new_text="Delay damages are 0.03% per day."))).findings[0]
    assert f.fix_type == "add" and f.old_text == "" and f.new_text == "Delay damages are 0.03% per day."


def test_a_quote_in_two_sentences_gives_no_fix():
    clause = Clause(key="two", title="Two", items=[Item("The Owner shall pay within 14 days."), Item("The Contractor shall pay within 14 days.")], category="general")
    sections = [Section("two", "Two", "\n".join(i.text for i in clause.items), clause)]
    changes = [{"id": "c1", "kind": "wording_change", "clause": "Two", "text": "The Owner shall pay within 14 days."}]
    f = one(first(finding(clause_key="two", quote="shall pay within 14 days", new_text="The Owner shall pay within 14 days.")), sections, TS_TEXT, changes).findings[0]
    assert f.fix_type == "none" and "single sentence" in f.fix_note


def test_a_table_cell_gets_no_fix():
    clause = Clause(key="p", title="P", items=[Item("The payments are in the table.")],
                    tables=[{"headers": ["No", "Condition"], "rows": [["1", "Within 10 days of signing"]]}], category="general")
    sections = [Section("p", "P", "The payments are in the table.\nWithin 10 days of signing", clause)]
    f = one(first(finding(clause_key="p", quote="Within 10 days of signing", new_text="Within 10 days of signing and mobilisation")), sections, TS_TEXT, ()).findings[0]
    assert f.fix_type == "none" and "table cell" in f.fix_note


PRICE_OLD = "The Owner agrees to pay the Contractor the fixed total amount of THB 1,000,000 (One million), exclusive of VAT."


def price_run(new_text, ts, says="One-hundred Thousand"):
    clause = Clause(key="price", title="Price", items=[Item(PRICE_OLD)], category="general")
    sections = [Section("price", "Price", PRICE_OLD, clause)]
    changes = [{"id": "c1", "kind": "wording_change", "clause": "Price", "text": PRICE_OLD}]
    return one(first(finding(clause_key="price", issue="The price in words differs.", quote="THB 1,000,000 (One million)",
                             term_sheet_says=says, new_text=new_text)), sections, ts, changes).findings[0]


def test_a_fix_that_makes_an_amount_and_its_words_disagree_is_not_offered():
    ts = "contract_price_number: 1,000,000\ncontract_price_words: One-hundred Thousand"
    f = price_run(PRICE_OLD.replace("(One million)", "(One-hundred Thousand)"), ts)
    assert f.fix_type == "none" and "do not agree" in f.fix_note and "One-hundred Thousand" in f.fix_note and f.quote, "the finding itself stays"


def test_a_fix_whose_amount_and_words_agree_is_offered():
    ts = "contract_price_number: 1,500,000\ncontract_price_words: One million five hundred thousand"
    f = price_run(PRICE_OLD.replace("1,000,000 (One million)", "1,500,000 (One million five hundred thousand)"), ts, "One million five hundred thousand")
    assert f.fix_type == "modify" and "1,500,000" in f.new_text


# ---------------------------------------------------------------- evidence in two places
def test_a_quote_that_is_not_in_the_section_leaves_the_finding_out():
    result = one(first(finding(quote="words that are not in the clause")))
    assert result.findings == [] and any("not found in the draft" in n for n in result.notes)


def test_with_changed_sentences_a_quote_must_be_inside_one_of_them():
    other = next(i.text for i in CLAUSE.items if i.text != LD_OLD)
    quote = " ".join(other.split()[:6])
    result = one(first(finding(quote=quote, fix_type="none", new_text="")))
    assert result.findings == [] and any("not about a changed sentence" in n for n in result.notes)
    assert len(one(first(finding(quote=quote, fix_type="none", new_text="")), changes=()).findings) == 1, "no changed sentence: the whole draft is checked"


def test_term_sheet_words_that_are_not_in_the_term_sheet_leave_the_finding_out():
    result = one(first(finding(term_sheet_says="rate of 9% a day")))
    assert result.findings == [] and any("not found in the term sheet" in n for n in result.notes)
    assert one(first(finding(term_sheet_says=""))).findings == [], "a difference from the term sheet needs words of the term sheet"


def test_a_finding_that_says_the_draft_differs_when_it_already_says_it_is_left_out():
    sections = [Section("misc", "Miscellaneous", "This Agreement shall be governed by the laws of Thailand.")]
    changes = [{"id": "c1", "kind": "wording_change", "clause": "Miscellaneous", "text": "This Agreement shall be governed by the laws of Thailand."}]
    bad = finding(clause_key="misc", issue="Governing law discrepancy.", quote="governed by the laws of Thailand", term_sheet_says="Thailand", fix_type="none", new_text="")
    result = one(first(bad), sections, "governing_law: Thailand\nproject_name: PV", changes)
    assert result.findings == [] and any("already agrees" in n and "Governing law discrepancy" in n for n in result.notes)


def test_a_real_difference_in_the_same_clause_stays():
    sections = [Section("misc", "Miscellaneous", "This Agreement shall be governed by the laws of Victoria.")]
    changes = [{"id": "c1", "kind": "wording_change", "clause": "Miscellaneous", "text": "This Agreement shall be governed by the laws of Victoria."}]
    real = finding(clause_key="misc", issue="Governing law differs.", quote="laws of Victoria", term_sheet_says="governing_law: Thailand", fix_type="none", new_text="")
    assert [f.issue for f in one(first(real), sections, "governing_law: Thailand\nproject_name: PV", changes).findings] == ["Governing law differs."]


def two_sections():
    return [Section("a", "Termination", "The Owner may terminate on 30 (thirty) days notice."),
            Section("b", "Notice", "A notice of termination takes effect after 45 (forty-five) days.")]


def contradiction(**over):
    base = dict(kind="contradiction", clause_key="a", term_sheet_says="", quote="terminate on 30 (thirty) days notice", other_clause_key="b",
                other_quote="takes effect after 45 (forty-five) days", fix_type="none", new_text="", issue="Two different notice periods.")
    base.update(over)
    return finding(**base)


def test_a_contradiction_has_two_quotes_and_never_a_fix():
    changes = [{"id": "c1", "kind": "wording_change", "clause": "Termination", "text": "The Owner may terminate on 30 (thirty) days notice."}]
    f = one(first(contradiction(fix_type="modify", new_text="The Owner may terminate on 45 days notice.")), two_sections(), TS_TEXT, changes).findings[0]
    assert (f.kind, f.clause, f.other_clause, f.fix_type, f.new_text) == ("contradiction", "Termination", "Notice", "none", "")


def test_a_contradiction_needs_its_second_quote_in_the_other_section_and_different_words():
    changes = [{"id": "c1", "kind": "wording_change", "clause": "Termination", "text": "The Owner may terminate on 30 (thirty) days notice."}]
    for bad in (contradiction(other_quote="words that are nowhere"), contradiction(other_clause_key=""),
                contradiction(clause_key="a", other_clause_key="a", other_quote="terminate on 30 (thirty)")):
        assert one(first(bad), two_sections(), TS_TEXT, changes).findings == []


def test_an_unknown_clause_a_wrong_kind_or_an_empty_issue_drops_the_finding():
    result = one(first(finding(clause_key="no_such_clause"), finding(kind="style"), finding(issue="  ")))
    assert result.findings == [] and result.notes.count("Dropped a finding that was not valid.") == 6, "each of the two reads dropped three"


def test_a_part_that_is_not_a_clause_has_findings_but_no_fix():
    sections = [Section("header", "Contract header", "Header title")]
    f = one(first(finding(clause_key="header", quote="Header title", new_text="Another title")), sections, TS_TEXT, ()).findings[0]
    assert f.fix_type == "none" and "not a clause" in f.fix_note


def test_a_draft_that_is_only_text_has_no_fixes():
    f = one(first(finding(clause_key="draft")), [Section("draft", "The draft", LD_OLD)], TS_TEXT, ()).findings[0]
    assert f.fix_type == "none"


# ---------------------------------------------------------------- when a call fails
def test_when_one_read_fails_what_the_other_found_is_listed_apart_and_nothing_is_confirmed():
    result = run(SeqClient(first(finding()), first(finding()), refuse_at=1))
    assert result.findings == [] and not result.both_done and len(result.single) == 1
    assert any("could not run" in n and "nothing could be confirmed" in n for n in result.notes)
    result = run(SeqClient(first(finding()), first(finding()), refuse_at=0))
    assert result.findings == [] and len(result.single) == 1


def test_when_both_reads_fail_the_error_is_raised():
    try:
        run(SeqClient(first(), first(), refuse_at=(0, 1)))
    except AIStepError:
        return
    raise AssertionError("the failure should be raised")


# ---------------------------------------------------------------- what the app finds by itself
def test_a_clause_that_still_refers_to_a_clause_taken_out_is_found_without_ai():
    assert dependency_findings(library_for({})) == []
    got = dependency_findings(library_for({"force_majeure": False}))
    assert [(f.kind, f.clause_key, f.source, f.confirmed, f.fix_type) for f in got] == [("removed_clause", "suspension", "app", True, "none"),
                                                                                      ("removed_clause", "termination", "app", True, "none")]
    assert "still refers to \u201cForce Majeure\u201d" in got[0].issue and got[0].quote == "force majeure"


# ---------------------------------------------------------------- what the model reads
def test_the_draft_is_sent_in_sections_header_included_clauses_signature():
    keys = [s.key for s in SECTIONS]
    assert keys[0] == "header" and keys[-1] == "signature" and "completion_deadline" in keys
    assert "completion_deadline" not in [s.key for s in sections_of(library_for({"completion_deadline": False}))]
    assert SECTIONS[0].text == "Header title" and SECTIONS[-1].text == "IN WITNESS\nOwner"


def test_the_model_is_not_shown_the_payment_table():
    price = next(s for s in SECTIONS if s.key == "price_payment")
    table = price.clause.tables[0]
    assert table["rows"] and not any(cell in price.text for row in table["rows"] for cell in row if len(cell) > 25)
    assert not any(" | ".join(table["headers"]) in s.text for s in SECTIONS)


def test_the_schema_allows_the_sections_two_kinds_and_a_second_quote():
    props = build_schema(["a", "b"])["properties"]["findings"]["items"]["properties"]
    assert props["clause_key"]["enum"] == ["a", "b"] and props["other_clause_key"]["enum"] == ["a", "b", ""]
    assert props["kind"]["enum"] == ["term_sheet_mismatch", "contradiction"]


# ---------------------------------------------------------------- the temperature of every call
def test_every_call_is_made_with_temperature_zero_unless_told_otherwise():
    client = SeqClient(first(), first())
    run(client)
    assert [c["temperature"] for c in client.calls] == [0.0, 0.0]
    saved = llm.TEMPERATURE
    try:
        llm.TEMPERATURE = ""
        client = SeqClient(first(), first())
        run(client)
        assert all("temperature" not in c for c in client.calls)
        llm.TEMPERATURE = "0.3"
        client = SeqClient(first(), first())
        run(client)
        assert [c["temperature"] for c in client.calls] == [0.3, 0.3]
    finally:
        llm.TEMPERATURE = saved


def test_a_model_that_does_not_accept_a_temperature_is_called_again_without_one():
    calls = []

    def create(**kwargs):
        calls.append(dict(kwargs))
        if "temperature" in kwargs:
            raise ValueError("Unsupported value: 'temperature' does not support 0.0 with this model.")
        return "ok"
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert chat_create(client, model="m", messages=[]) == "ok" and len(calls) == 2 and "temperature" not in calls[1]

    def other(**kwargs):
        raise ValueError("rate limit")
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=other)))
    try:
        chat_create(client, model="m", messages=[])
    except ValueError:
        return
    raise AssertionError("an error that is not about the temperature must be raised")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} review tests passed.")
