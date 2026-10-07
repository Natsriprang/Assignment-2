"""Tests for the summary of the contract: the table of facts and the figure checks (core/exsum.py) and the two AI calls (ai/exsum.py).
Run: python -m tests.test_exsum"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.exsum import (CLAUSES_PROMPT, MAX_KEY_POINTS, OVERVIEW_PROMPT, build_clauses_schema, build_overview_schema, changes_block, clauses_input,
                      evaluate_clauses, summarise_contract, write_overview)
from ai.llm import AIStepError
from ai.review import Section
from core.draft_state import library_for
from core.exsum import allowed_figures, amount, coverage_text, digit_figures, fact_rows, facts_text, unsupported_figures
from core.readiness import missing_before_sending
from core.term_sheet_fields import TermSheet
from tests.test_interpret import sample_term_sheet
from tests.test_review import SeqClient

TS = sample_term_sheet()
TS_TEXT = "Contract price: THB 10,000,000\nPayment due within (working days): 30\nLimits: cap on delay damages 5%"
SECTIONS = [Section("price_payment", "Price", "The Owner shall pay THB 10,000,000. Each installment is due within 30 (thirty) working days."),
            Section("completion_deadline", "Completion Deadline", "The Contractor pays liquidated damages of 0.5 (zero point five) percent per day, not more than 5 (five) percent."),
            Section("notice", "Notice", "Notices must be in writing and delivered to the address of the Party.")]


def decision(key, kind="summarise", summary="", reason=""):
    return {"clause_key": key, "decision": kind, "summary": summary, "reason": reason}


def clauses_answer(*items):
    return {"clauses": list(items)}


GOOD = clauses_answer(decision("price_payment", summary="The Owner pays THB 10,000,000 in installments, each due within 30 working days."),
                      decision("completion_deadline", summary="Late completion costs 0.5% of the price a day, capped at 5%."),
                      decision("notice", "skip", reason="Standard notice wording."))
OVERVIEW = {"overview": "The Owner pays THB 10,000,000 for the works. Delay costs 0.5% a day, capped at 5%.", "key_points": [
    {"clause_key": "completion_deadline", "text": "Delay damages are 0.5% a day up to 5%."}]}


def changes_for(keys):
    """A change for each key, as the view makes them from the risk items."""
    return {k: [{"before": "Old sentence of the template.", "after": "New sentence.", "user_words": ""}] for k in keys}


def run(clauses, overview=None, changed=(), taken_out=(), sections=None, changes=None):
    client = SeqClient(clauses, overview or OVERVIEW)
    changes = changes if changes is not None else changes_for(changed)
    return summarise_contract(TS_TEXT, SECTIONS if sections is None else sections, facts_text(fact_rows(TS)), changes, list(taken_out), client, "m"), client


# ---------------------------------------------------------------- the table of facts, by code
def test_the_facts_come_from_the_term_sheet_in_the_order_a_reader_looks_for_them():
    rows = dict(fact_rows(TS))
    assert rows["Parties"] == "Owner: Solar Owner Co., Ltd.; Contractor: Sun Build Co., Ltd., Thailand"
    assert rows["Project"] == "Rooftop PV Project, Bangkok, capacity 500 kWp" and rows["Contract price"] == "THB 10,000,000"
    assert rows["Time for the Works"] == "1 Nov 2026 to 1 Apr 2027"
    assert rows["Payment"] == "3 installments (30%, 30%, 40%), each due within 30 working days"
    assert rows["Caps on damages"] == "cap on delay damages 5%; cap on total damages deducted 5%"
    assert [label for label, _ in fact_rows(TS)][:3] == ["Parties", "Project", "Contract price"]


def test_a_row_with_no_value_is_left_out_and_a_period_and_a_cap_that_is_off_are_written_as_they_are():
    ts = TermSheet(owner_name="Owner Co", governing_law="the laws of Thailand.", deadline_mode="period", completion_days="150")
    ts.limits = {"ld_cap": None, "damages_cap": 3.0}
    rows = dict(fact_rows(ts))
    assert rows["Parties"] == "Owner: Owner Co", "the default country of the Contractor says nothing without a name"
    assert rows["Time for the Works"] == "150 days" and rows["Governing law"] == "Thailand"
    assert rows["Caps on damages"] == "cap on delay damages none; cap on total damages deducted 3%"
    assert "Contract price" not in rows and "Project" not in rows and "Payment" not in rows, "a unit or a number of days alone is only a default"


def test_the_signatories_and_what_is_missing_before_the_draft_is_sent():
    ts = sample_term_sheet()
    ts.owner_signatory, ts.contractor_signatory = "Nat Sriprang", "Noom Sriprang"
    assert dict(fact_rows(ts))["Signatories"] == "Owner: Nat Sriprang; Contractor: Noom Sriprang"
    assert "the Owner's registration number" in missing_before_sending(TermSheet())
    assert missing_before_sending(TermSheet()).count("the Owner's registration number") == 1


def test_amounts_are_written_with_separators_and_vat_in_full_words():
    assert amount("100000") == "100,000" and amount("1,000,000") == "1,000,000" and amount("1500.5") == "1,500.50" and amount("1500.00") == "1,500"
    assert amount("ten thousand") == "ten thousand" and amount(" 250 ") == "250"
    for vat, shown in (("exclusive", "exclusive of VAT"), ("Not including VAT", "exclusive of VAT"), ("inclusive", "inclusive of VAT"), ("it depends", "it depends")):
        ts = TermSheet(contract_price_number="100000", contract_price_words="One-hundred Thousand", vat_treatment=vat)
        assert dict(fact_rows(ts))["Contract price"] == f"THB 100,000 (One-hundred Thousand), {shown}", vat
    assert dict(fact_rows(TermSheet(contract_price_number="100000")))["Contract price"] == "THB 100,000"


# ---------------------------------------------------------------- the figures
def test_figures_are_read_as_digits_and_an_amount_with_commas_is_one_figure():
    assert digit_figures("THB 1,000,000 within 30 days on 1 Nov 2026, 0.5 percent") == {Decimal(1000000), Decimal(30), Decimal(1), Decimal(2026), Decimal("0.5")}
    assert digit_figures("two weeks and thirty days") == set(), "words are not checked: only digits that the AI could have made up"
    allowed = allowed_figures("THB 10,000,000", "30 (thirty) days")
    assert unsupported_figures("THB 10,000,000 in 30 days", allowed) == []
    assert unsupported_figures("THB 15,000,000 in 30 days", allowed) == [Decimal(15000000)]


def test_the_coverage_line_says_what_was_left_out():
    assert coverage_text(7, 8, []) == "Summarised 7 of 15 clauses; left out 8 that use the template's standard wording with nothing specific to this deal."
    assert coverage_text(3, 0, []) == "Summarised 3 of 3 clauses."


# ---------------------------------------------------------------- the two calls
def test_two_calls_are_made_even_when_every_clause_is_skipped():
    all_skipped = clauses_answer(*[decision(s.key, "skip", reason="Standard.") for s in SECTIONS])
    result, client = run(all_skipped, {"overview": "Nothing differs from the standard contract.", "key_points": []})
    assert len(client.calls) == 2 and result.summarised() == [] and result.overview == "Nothing differs from the standard contract."


def test_every_clause_is_accounted_for_whatever_the_model_returns():
    answer = clauses_answer(decision("price_payment", summary="The Owner pays in installments."), decision("no_such_clause", "skip", reason="x"),
                            {"clause_key": "notice", "decision": "maybe", "summary": "", "reason": ""})
    result, _ = run(answer)
    got = {d.key: d for d in result.decisions}
    assert [d.key for d in result.decisions] == ["price_payment", "completion_deadline", "notice"], "in the order of the draft, nothing unknown"
    assert got["price_payment"].decision == "summarise"
    assert got["completion_deadline"].decision == "skip" and not got["completion_deadline"].assessed and "did not assess" in got["completion_deadline"].reason
    assert not got["notice"].assessed


def test_a_summary_that_is_empty_counts_as_not_assessed():
    result, _ = run(clauses_answer(decision("price_payment", summary="  "), decision("completion_deadline", "skip", reason="x"), decision("notice", "skip", reason="x")))
    assert not result.decisions[0].assessed and result.decisions[0].decision == "skip"


def test_that_a_clause_was_changed_comes_from_the_code_and_a_changed_clause_the_model_skipped_stays_marked():
    answer = clauses_answer(decision("price_payment", "skip", reason="Standard."), decision("completion_deadline", summary="Delay costs 0.5% a day, capped at 5%."),
                            decision("notice", "skip", reason="Standard."))
    result, client = run(answer, changed=["completion_deadline", "price_payment"])
    got = {d.key: d for d in result.decisions}
    assert got["price_payment"].changed and got["price_payment"].decision == "skip" and got["completion_deadline"].changed and not got["notice"].changed
    told = client.calls[0]["messages"][1]["content"]
    assert "CHANGES MADE TO THE TEMPLATE:\n[key: price_payment | title: Price]" in told, "in the order of the draft, not the order the changes were given in"
    assert told.index("[key: price_payment | title: Price]\n- sentence") < told.index("[key: completion_deadline | title: Completion Deadline]\n- sentence")


# ---------------------------------------------------------------- what changed, from what to what
def test_the_model_is_told_what_each_changed_clause_said_in_the_template_what_it_says_now_and_what_the_user_asked():
    block = changes_block({"completion_deadline": [{"before": "Rate 0.05 (zero point zero five) percent.", "after": "Rate 0.5 (zero point five) percent.",
                                                       "user_words": "increase the rate to 0.5%"}],
                           "price_payment": [{"before": "", "after": "A new sentence.", "user_words": ""}],
                           "notice": [{"before": "An old sentence.", "after": "", "user_words": ""}]}, {"completion_deadline": "Completion Deadline"})
    assert "[key: completion_deadline | title: Completion Deadline]\n- sentence in the template: Rate 0.05 (zero point zero five) percent.\n- sentence now: Rate 0.5 (zero point five) percent.\n- the user asked: \u201cincrease the rate to 0.5%\u201d" in block
    assert "- added: A new sentence." in block and "- taken out: An old sentence." in block
    assert changes_block({}, {}) == "(none)"
    told = clauses_input("ts", SECTIONS, {})
    assert "TERM SHEET:\nts" in told and told.endswith("CHANGES MADE TO THE TEMPLATE:\n(none)")


def test_a_changed_clause_may_say_the_figure_it_changed_from_and_the_figure_the_user_asked_for_but_an_unchanged_one_may_not():
    changes = {"completion_deadline": [{"before": "Liquidated damages of 0.05 (zero point zero five) percent a day.", "after": "Liquidated damages of 0.5 (zero point five) percent a day.",
                                         "user_words": "increase the rate to 0.5%"}]}
    answer = clauses_answer(decision("price_payment", summary="The Owner pays THB 10,000,000; the rate was 0.05% once."),
                            decision("completion_deadline", summary="The damages rate rises from 0.05% to 0.5% a day, capped at 5%."), decision("notice", "skip", reason="x"))
    result, _ = run(answer, changes=changes)
    got = {d.key: d for d in result.decisions}
    assert got["completion_deadline"].decision == "summarise" and got["completion_deadline"].changed, "0.05 is in the sentence of the template"
    assert got["price_payment"].removed, "0.05 is not in that clause, the term sheet or the changes of another clause"
    result, _ = run(clauses_answer(decision("price_payment", "skip", reason="x"), decision("completion_deadline", summary="Damages rise from 0.07% to 0.5% a day."),
                                   decision("notice", "skip", reason="x")), changes=changes)
    assert {d.key: d for d in result.decisions}["completion_deadline"].removed, "0.07 is in none of the sources"


# ---------------------------------------------------------------- figures the model wrote that are not in the sources
def test_a_summary_with_a_figure_that_is_in_neither_the_clause_nor_the_term_sheet_is_taken_out():
    answer = clauses_answer(decision("price_payment", summary="The Owner pays THB 15,000,000 within 45 days."),
                            decision("completion_deadline", summary="Late completion costs 0.5% a day, capped at 5%."), decision("notice", "skip", reason="x"))
    result, _ = run(answer)
    got = {d.key: d for d in result.decisions}
    assert got["price_payment"].removed and got["price_payment"].decision == "skip" and got["price_payment"].summary == ""
    assert any("Took out the summary of Price" in n and "15000000" in n and "45" in n for n in result.notes)
    assert got["completion_deadline"].decision == "summarise", "a figure that is in the clause is fine"


def test_a_figure_that_is_only_in_the_term_sheet_or_the_table_of_facts_is_fine_and_a_summary_that_cites_the_law_is_not():
    answer = clauses_answer(decision("price_payment", summary="The price is THB 10,000,000; payment is due within 30 working days."),
                            decision("completion_deadline", summary="Under section 12 of the Act, late completion costs money."), decision("notice", "skip", reason="x"))
    result, _ = run(answer)
    got = {d.key: d for d in result.decisions}
    assert got["price_payment"].decision == "summarise"
    assert got["completion_deadline"].removed and any("cited the law" in n for n in result.notes)


def test_the_overview_loses_a_sentence_with_a_figure_that_is_not_in_the_facts_or_the_summaries_and_a_key_point_about_an_unknown_clause():
    overview = {"overview": "The Owner pays THB 10,000,000. The penalty is 9% a day. Delay is capped at 5%.", "key_points": [
        {"clause_key": "completion_deadline", "text": "Delay is capped at 5%."}, {"clause_key": "notice", "text": "Notices are in writing."},
        {"clause_key": "completion_deadline", "text": "The cap is 12%."}, {"clause_key": "", "text": "General point."}]}
    result, _ = run(GOOD, overview)
    assert result.overview == "The Owner pays THB 10,000,000. Delay is capped at 5%."
    assert result.key_points == [("completion_deadline", "Delay is capped at 5%.")], "notice was skipped, 12% is made up, an empty key is not a clause"
    assert sum("Took a sentence out" in n for n in result.notes) == 1 and sum("Took a key point out" in n for n in result.notes) == 1


def test_at_most_three_key_points():
    overview = {"overview": "Fine.", "key_points": [{"clause_key": "completion_deadline", "text": f"Point {n}."} for n in range(6)]}
    assert len(run(GOOD, overview)[0].key_points) == MAX_KEY_POINTS


def test_the_overview_is_told_the_facts_the_summaries_and_what_was_taken_out():
    result, client = run(GOOD, taken_out=["Force Majeure"], changed={"completion_deadline"})
    told = client.calls[1]["messages"][1]["content"]
    assert "Contract price: THB 10,000,000" in told and "[completion_deadline | Completion Deadline | CHANGED] Late completion costs 0.5% of the price a day" in told
    assert "TAKEN OUT OF THE STANDARD CONTRACT: Force Majeure" in told and "CLAUSES LEFT OUT AS STANDARD WORDING: 1" in told
    assert "[notice" not in told, "a clause that was skipped is not among the clauses that matter"


# ---------------------------------------------------------------- when a call fails
def test_a_failed_overview_keeps_the_clause_summaries_and_says_so():
    client = SeqClient(GOOD, OVERVIEW, refuse_at=1)
    result = summarise_contract(TS_TEXT, SECTIONS, "Contract price: THB 10,000,000", {}, [], client, "m")
    assert len(result.summarised()) == 2 and result.overview == "" and any("overview could not be written" in n for n in result.notes)


def test_a_failed_first_call_raises():
    try:
        summarise_contract(TS_TEXT, SECTIONS, "", {}, [], SeqClient(GOOD, OVERVIEW, refuse_at=0), "m")
    except AIStepError:
        return
    raise AssertionError("the first call's failure should be raised")


# ---------------------------------------------------------------- what the model reads
def test_the_prompts_say_what_to_do_with_a_changed_clause_and_with_one_that_was_not_changed():
    flat = " ".join(CLAUSES_PROMPT.split())
    for phrase in ("A clause that was CHANGED: never skip it", "say what changed, from what to what", "do not only restate the new wording",
                   "skip it when it is only ordinary market boilerplate", "holds a value specific to this deal, one that comes from the TERM SHEET",
                   "summarise ONLY what those values do in the clause, in one sentence", "do not describe the standard wording around them",
                   "Every clause that is not changed has the template's standard wording", "do not calculate, round or add any", "Do not write clause numbers",
                   "Do not cite any statute"):
        assert phrase in flat, phrase
    flat = " ".join(OVERVIEW_PROMPT.split())
    assert "Do not calculate, round or add any figure" in flat and "If nothing differs from the standard contract, say so" in flat
    assert "\\" not in CLAUSES_PROMPT and "\\" not in OVERVIEW_PROMPT


def test_the_schemas_name_every_clause_once_and_the_overview_may_only_point_at_a_clause_that_matters():
    enum = build_clauses_schema(["a", "b"])["properties"]["clauses"]["items"]["properties"]["clause_key"]["enum"]
    assert enum == ["a", "b"]
    assert build_overview_schema(["a"])["properties"]["key_points"]["items"]["properties"]["clause_key"]["enum"] == ["a", ""]


def test_the_model_reads_the_clauses_without_the_payment_table_and_every_call_is_at_temperature_zero():
    from ai.review import sections_of
    sections = sections_of(library_for({}, None, None, TS))
    price = next(s for s in sections if s.key == "price_payment")
    table = price.clause.tables[0]
    assert not any(cell in price.text for row in table["rows"] for cell in row if len(cell) > 25)
    answer = clauses_answer(*[decision(s.key, "skip", reason="Standard.") for s in sections])
    client = SeqClient(answer, OVERVIEW)
    summarise_contract("ts", sections, "facts", {}, [], client, "m")
    assert [c["temperature"] for c in client.calls] == [0.0, 0.0]
    assert "[key: price_payment | title: Contract Price and Terms of Payment]" in client.calls[0]["messages"][1]["content"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} summary tests passed.")
