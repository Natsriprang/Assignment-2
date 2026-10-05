"""Tests for wording changes: finding the sentence, checking a rewrite, applying accepted changes, before/after markup.
Run: python -m tests.test_wording"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document

from core.clause_data import build_library
from core.draft_state import library_for
from core.header import build_header
from core.render import render_docx
from core.renumber import renumber_and_render
from core.wording import (apply_edits, check_rewrite, diff_markup, figure_mismatches, figure_swap, find_unit, norm, splice_fragment,
                          units)

LD_QUOTE = "at the rate of 0.05 (zero point zero five) percent of the Contract Price per day"
REQ = "Reduce the delay damages rate to 0.03% per day. reduce delay damages to 0.03% per day"


def clause(key, library=None):
    return next(c for c in (library or library_for({})) if c.key == key)


def old_ld():
    return find_unit(clause("completion_deadline"), LD_QUOTE)[1]


def new_ld(figure="0.03 (zero point zero three)"):
    return old_ld().replace("0.05 (zero point zero five)", figure)


# ---------------------------------------------------------------- finding the sentence
def test_the_sentence_containing_a_quote_is_found_whatever_kind_of_text_it_is():
    loc, text = find_unit(clause("completion_deadline"), LD_QUOTE)
    assert loc[0] == "item" and text.startswith("Unless otherwise agreed by the Parties") and "0.05 (zero point zero five)" in text
    assert find_unit(clause("price_payment"), "mounting system")[0][0] == "cell"
    assert find_unit(clause("notice"), "Any communication with the addressee")[0][0] == "paragraph"
    assert find_unit(clause("completion_deadline"), "  AT THE RATE of 0.05   (zero point zero five) PERCENT ")[0] == loc


def test_a_quote_in_no_sentence_or_in_several_finds_nothing():
    assert find_unit(clause("completion_deadline"), "a provision that is not there") is None
    assert find_unit(clause("completion_deadline"), "") is None
    assert find_unit(clause("price_payment"), "Payable upon completion of installation") is None          # in more than one table cell


def test_every_piece_of_text_of_a_clause_is_a_unit():
    c = clause("price_payment")
    kinds = {loc[0] for loc, _ in units(c)}
    assert kinds == {"item", "cell"} and len([1 for loc, _ in units(c) if loc[0] == "cell"]) == 5 * 4


# ---------------------------------------------------------------- checking a rewrite
def test_a_change_of_the_figure_and_its_words_is_accepted():
    assert check_rewrite(old_ld(), new_ld(), "modify", LD_QUOTE, REQ) == ""


def test_a_figure_and_its_words_must_agree():
    assert "do not agree" in check_rewrite(old_ld(), new_ld("0.03 (zero point zero five)"), "modify", LD_QUOTE, REQ)
    assert figure_mismatches("pay within 15 (fifteen) days and 7 (eight) days") == ["7 (eight)"]
    assert figure_mismatches("5% (five percent) and 0.03 (zero point zero three) percent and 120 (one hundred and twenty) days") == []
    assert figure_mismatches("15 (fourteen) days", known="15 (fourteen) days") == []            # an old mismatch is not this change's


def test_only_figures_the_user_gave_may_come_in():
    assert "figure that you did not give" in check_rewrite(old_ld(), new_ld("0.04 (zero point zero four)"), "modify", LD_QUOTE, REQ)
    assert "figure that you did not give" in check_rewrite("", "The warranty period is 36 (thirty-six) months.", "add", "", "add a 24 months warranty")
    assert check_rewrite("", "The warranty period is 24 (twenty-four) months.", "add", "", "add a 24 months warranty") == ""
    assert check_rewrite("", "Repair within 120 (one hundred and twenty) days.", "add", "", "repair within 120 days") == ""


def test_the_figure_asked_for_must_be_in_the_new_wording():
    assert "does not contain the figure" in check_rewrite("Pay within 30 (thirty) days.", "Pay within 30 (thirty) days promptly.", "modify", "30 (thirty) days", "make it 15 days")


def test_nothing_changing_or_everything_changing_is_refused():
    assert check_rewrite(old_ld(), old_ld(), "modify", LD_QUOTE, REQ) == "The wording would not change."
    rewritten = "The Owner may claim 0.03 (zero point zero three) percent of the Contract Price per day."
    assert "much more of the sentence" in check_rewrite(old_ld(), rewritten, "modify", LD_QUOTE, REQ)
    assert check_rewrite(old_ld(), "", "modify", LD_QUOTE, REQ) == "The AI did not write the new wording."
    assert "too long" in check_rewrite("A b.", "word " * 200, "add", "", "")


def test_a_change_outside_the_quoted_words_is_refused():
    elsewhere = new_ld().replace("Unless otherwise agreed by the Parties", "Unless otherwise agreed in writing by the Parties")
    assert "parts of the sentence you did not ask about" in check_rewrite(old_ld(), elsewhere, "modify", LD_QUOTE, REQ)
    near = new_ld().replace("per day", "each day")                            # inside the quote
    assert check_rewrite(old_ld(), near, "modify", LD_QUOTE, REQ) == ""


def test_removing_part_of_a_sentence():
    old = "The Contractor shall provide the Owner with weekly progress reports and photographs of the Works."
    quote = "and photographs of the Works"
    assert check_rewrite(old, "The Contractor shall provide the Owner with weekly progress reports.", "remove_part", quote, "remove the photographs") == ""
    assert "still in the new wording" in check_rewrite(old, old.replace("progress", "interim progress"), "remove_part", quote, "remove the photographs")
    assert "much more" in check_rewrite(old, "The Contractor shall provide.", "remove_part", quote, "remove the photographs")


# ---------------------------------------------------------------- repairing a proposal
LONG_QUOTE = ("the Owner has the right to claim liquidated damages from the Contractor at the rate of 0.05 (zero point zero five) percent of "
              "the Contract Price per day but not more than 5 (five) percent of the Contract Price.")
REQUEST_2 = "Reduce the liquidated damages rate to 0.03% reduce the delay damage to 0.03%"


def test_only_the_quoted_words_given_back_are_put_into_the_sentence():
    old = find_unit(clause("completion_deadline"), LD_QUOTE)[1]
    fragment = LONG_QUOTE.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)")
    assert "much more of the sentence" in check_rewrite(old, fragment, "modify", LONG_QUOTE, REQUEST_2)           # the reported refusal
    whole = splice_fragment(old, LONG_QUOTE, fragment)
    assert whole == old.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)")
    assert check_rewrite(old, whole, "modify", LONG_QUOTE, REQUEST_2) == ""


def test_a_fragment_in_the_middle_keeps_the_words_on_both_sides():
    old = "The Owner shall pay the Contractor within 30 (thirty) working days after receipt of the invoice, without any deduction."
    got = splice_fragment(old, "within 30 (thirty) working days", "within 15 (fifteen) working days")
    assert got == "The Owner shall pay the Contractor within 15 (fifteen) working days after receipt of the invoice, without any deduction."
    ended = splice_fragment("Pay within 30 (thirty) days.", "within 30 (thirty) days", "within 15 (fifteen) days.")
    assert ended == "Pay within 15 (fifteen) days."                                           # a full stop is not doubled


def test_a_whole_sentence_or_an_unrelated_text_is_not_treated_as_a_fragment():
    old = find_unit(clause("completion_deadline"), LD_QUOTE)[1]
    assert splice_fragment(old, LD_QUOTE, old.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)")) == ""
    assert splice_fragment(old, LD_QUOTE, "The Contractor shall do something entirely different.") == ""
    assert splice_fragment(old, "a quote that is not there", "x") == "" and splice_fragment(old, LD_QUOTE, "") == ""


def test_the_system_writes_one_figure_and_its_words_itself():
    old = find_unit(clause("completion_deadline"), LD_QUOTE)[1]
    got = figure_swap(old, LD_QUOTE, "reduce the rate to 0.03% per day")
    assert got == old.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)")        # one figure in the quote: replaced
    one = "at the rate of 0.05 (zero point zero five) percent of the Contract Price per day"
    got = figure_swap(old, one, "reduce the rate to 0.03% per day")
    assert got == old.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)")
    assert check_rewrite(old, got, "modify", one, "reduce the rate to 0.03% per day") == ""
    pay = "The Owner shall pay within 30 (thirty) working days."
    assert figure_swap(pay, "within 30 (thirty) working days", "make it 45 working days") == "The Owner shall pay within 45 (forty-five) working days."
    assert figure_swap(pay, "within 30 (thirty) working days", "make it 120 working days") == "The Owner shall pay within 120 (one hundred and twenty) working days."
    pct = "not more than 5% (five percent) of the Contract Price"
    assert figure_swap(pct, "5% (five percent)", "cap it at 8%") == "not more than 8% (eight percent) of the Contract Price"
    assert figure_swap(pct, "5% (five percent)", "cap it at 2.5%") == "not more than 2.5% (two point five percent) of the Contract Price"


def test_the_system_does_not_guess_which_figure_or_what_the_new_one_is():
    old = find_unit(clause("completion_deadline"), LD_QUOTE)[1]
    assert figure_swap(old, LONG_QUOTE, "reduce the rate to 0.03% per day") == ""                    # two figures in the quote: which one?
    one = "at the rate of 0.05 (zero point zero five) percent of the Contract Price per day"
    assert figure_swap(old, one, "reduce the rate") == ""                                            # no new figure
    assert figure_swap(old, one, "reduce the rate to 0.03% per day or 0.02%") == ""                 # two new figures
    assert figure_swap(old, one, "reduce the rate to 0.0123% per day") == ""                         # more than two decimals
    assert figure_swap(old, "a quote that is not there", "to 0.03%") == ""
    assert figure_swap("Pay within thirty days.", "within thirty days", "make it 15 days") == ""      # no digits-and-words pair to replace


# ---------------------------------------------------------------- applying
def edit(change_type, old, new, key="completion_deadline"):
    return {"id": f"{key}-{change_type}-{len(new)}", "clause_key": key, "change_type": change_type, "old": old, "new": new, "summary": "s"}


def test_a_modify_replaces_the_sentence_in_place():
    lib = library_for({}, edits=[edit("modify", old_ld(), new_ld())])
    c = clause("completion_deadline", lib)
    assert [loc[0] for loc, t in units(c) if "0.03 (zero point zero three)" in t] == ["item"]
    assert not any("0.05 (zero point zero five)" in t for _, t in units(c))
    assert len(c.items) == len(clause("completion_deadline").items)


def test_the_caps_and_the_term_sheet_are_written_in_before_a_change_is_applied():
    lib = library_for({}, {"ld_cap": 3.0}, edits=[edit("modify", old_ld().replace("5 (five) percent", "3 (three) percent"), "X rewritten sentence.")])
    assert any(t == "X rewritten sentence." for _, t in units(clause("completion_deadline", lib)))     # the change matched the capped text


def test_a_table_cell_and_a_paragraph_can_be_changed():
    cell = "Payable upon completion of installation of the mounting system."
    lib = library_for({}, edits=[edit("modify", cell, "Payable upon completion of the mounting system.", "price_payment")])
    price = clause("price_payment", lib)
    assert price.tables[0]["rows"][1][3] == "Payable upon completion of the mounting system."
    assert price.table_rows[1][3] == "Payable upon completion of the mounting system."
    para = clause("notice").plain_paragraphs[1]
    lib = library_for({}, edits=[edit("modify", para, "Changed paragraph.", "notice")])
    assert clause("notice", lib).plain_paragraphs[1] == "Changed paragraph."


def test_an_added_sentence_goes_at_the_end_and_is_numbered():
    sentence = "The warranty period is 24 (twenty-four) months."
    lib = library_for({}, edits=[edit("add", "", sentence)])
    c = clause("completion_deadline", lib)
    assert c.items[-1].text == sentence and len(c.items) == len(clause("completion_deadline").items) + 1
    lines = next(items for n, cl, items in renumber_and_render(lib) if cl.key == "completion_deadline")
    assert lines[-1].endswith(sentence) and lines[-1].split(" ", 1)[0].startswith("6.")
    lib = library_for({}, edits=[edit("add", "", "A new last paragraph.", "notice")])
    assert clause("notice", lib).plain_paragraphs[-1] == "A new last paragraph."


def test_a_change_whose_sentence_is_gone_is_not_applied_and_is_reported():
    failed = []
    stale = edit("modify", "A sentence that is not in the clause.", "Whatever.")
    lib = library_for({}, edits=[stale, edit("modify", old_ld(), new_ld()), edit("add", "", "x y.", "no_such_clause")], failed=failed)
    assert [e["id"] for e in failed] == [stale["id"], failed[1]["id"]] and len(failed) == 2
    assert any("0.03" in t for _, t in units(clause("completion_deadline", lib)))                       # the good one still went in


def test_changes_are_applied_in_order_and_a_second_change_builds_on_the_first():
    first = edit("modify", old_ld(), new_ld())
    second = edit("modify", new_ld(), new_ld().replace("per day", "each day"))
    lib = library_for({}, edits=[first, second])
    assert any("each day" in t for _, t in units(clause("completion_deadline", lib)))
    failed = []
    library_for({}, edits=[second, first], failed=failed)                    # the other way round, the second has nothing to change yet
    assert len(failed) == 1


def test_a_fresh_library_has_none_of_the_changes():
    library_for({}, edits=[edit("modify", old_ld(), new_ld())])
    assert any("0.05 (zero point zero five)" in t for _, t in units(clause("completion_deadline")))


def test_the_changed_sentence_reaches_the_word_file():
    lib = library_for({}, edits=[edit("modify", old_ld(), new_ld()), edit("add", "", "The warranty period is 24 (twenty-four) months.")])
    buf = io.BytesIO()
    render_docx(lib, buf, header=build_header(None))
    buf.seek(0)
    text = "\n".join(p.text for p in Document(buf).paragraphs)
    assert "0.03 (zero point zero three) percent of the Contract Price per day" in text and "0.05 (zero point zero five)" not in text
    assert "The warranty period is 24 (twenty-four) months." in text


# ---------------------------------------------------------------- before and after
def test_the_markup_strikes_what_goes_and_bolds_what_comes():
    old = "The Owner may claim damages at the rate of 0.05 (zero point zero five) percent per day."
    before, after = diff_markup(old, old.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)"))
    assert "~~0.05~~" in before and "(zero point zero ~~five)~~" in before and "**0.03**" in after and "**three)**" in after
    assert before.replace("~~", "").replace("\\", "") == old and after.replace("**", "") == old.replace("0.05", "0.03").replace("five", "three")
    assert diff_markup("same words", "same words") == ("same words", "same words")
    assert diff_markup("a [b] *c*", "a [b] *d*")[0] == "a \\[b\\] ~~\\*c\\*~~"                       # markdown characters are escaped


def test_norm_is_one_line_with_single_spaces():
    assert norm("  a \n b\t c ") == "a b c" and norm(None) == ""


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} wording tests passed.")
