"""Tests for the rewritten sentence in the Interpret call (offline, fake client). Run: python -m tests.test_rewrite"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.interpret import SYSTEM_PROMPT, build_schema, clause_digest, interpret_request, validate
from core.draft_state import library_for
from core.wording import find_unit
from tests.test_interpret import FakeClient, action, dev, empty, sample_term_sheet

QUOTE = "at the rate of 0.05 (zero point zero five) percent of the Contract Price per day"
REQUEST = "reduce the delay damages to 0.03% per day"


def lib():
    return library_for({})


def old_ld(library=None):
    return find_unit(next(c for c in (library or lib()) if c.key == "completion_deadline"), QUOTE)[1]


def new_ld(figure="0.03 (zero point zero three)"):
    return old_ld().replace("0.05 (zero point zero five)", figure)


def modify(new_text, **kw):
    return dev("completion_deadline", QUOTE, change="Reduce the rate to 0.03% per day", evidence=REQUEST, new_text=new_text, **kw)


def run(deviations, library=None, **extra):
    return validate(empty(deviations=deviations, **extra), library or lib(), REQUEST)


# ---------------------------------------------------------------- a checked rewrite
def test_a_valid_rewrite_comes_with_the_sentence_it_replaces():
    d = run([modify(new_ld())]).deviations[0]
    assert d.new_text == new_ld() and d.old_text == old_ld() and d.rewrite_problem == ""


SHORT_QUOTE = "at the rate of 0.05 (zero point zero five) percent of the Contract Price per day"
LONG_QUOTE = ("the Owner has the right to claim liquidated damages from the Contractor at the rate of 0.05 (zero point zero five) percent of "
              "the Contract Price per day but not more than 5 (five) percent of the Contract Price.")


def test_the_reported_case_the_ai_gives_back_only_the_quoted_words():
    fragment = LONG_QUOTE.replace("0.05 (zero point zero five)", "0.03 (zero point zero three)")
    raw = dev("completion_deadline", LONG_QUOTE, change="reduce the liquidated damages rate to 0.03%", evidence=REQUEST, new_text=fragment)
    d = validate(empty(deviations=[raw]), lib(), REQUEST).deviations[0]
    assert d.new_text == new_ld() and d.written_by == "fragment" and d.rewrite_problem == ""


def test_a_rewrite_with_a_wrong_figure_or_words_is_replaced_by_the_figure_the_user_gave():
    for wrong in (new_ld("0.03 (zero point zero five)"), new_ld("0.04 (zero point zero four)"), ""):
        d = run([modify(wrong)]).deviations[0]
        assert d.new_text == new_ld() and d.written_by == "figure" and d.rewrite_problem == "", wrong


def test_an_unchanged_sentence_is_also_repaired_by_the_figure():
    d = run([modify(old_ld())]).deviations[0]
    assert d.new_text == new_ld() and d.written_by == "figure"


def test_a_rewrite_that_cannot_be_repaired_is_still_offered_with_the_problem_as_advice():
    text = "The Owner may claim 0.03 (zero point zero three) percent per day."
    long_quote = dev("completion_deadline", LONG_QUOTE, change="Reduce the rate to 0.03% per day", evidence=REQUEST, new_text=text)
    d = validate(empty(deviations=[long_quote]), lib(), REQUEST).deviations[0]             # two figures in the quote: the system will not guess
    assert d.new_text == text and "much more" in d.rewrite_problem and d.written_by == "" and d.old_text
    no_figure = dev("completion_deadline", SHORT_QUOTE, change="Reduce the delay damages", evidence="reduce the delay damages",
                    new_text="The Owner may claim a small amount.")
    d = validate(empty(deviations=[no_figure]), lib(), "reduce the delay damages").deviations[0]
    assert d.new_text == "The Owner may claim a small amount." and d.rewrite_problem


def test_an_invented_figure_is_offered_with_the_problem_when_the_system_cannot_replace_it():
    invented = old_ld().replace("0.05 (zero point zero five)", "0.04 (zero point zero four)")
    d = validate(empty(deviations=[dev("completion_deadline", SHORT_QUOTE, change="reduce the delay damages", evidence="reduce the delay damages",
                                       new_text=invented)]), lib(), "reduce the delay damages").deviations[0]
    assert d.new_text == invented and "figure that you did not give" in d.rewrite_problem


def test_no_wording_at_all_leaves_an_empty_new_text_for_the_user_to_write():
    for raw in (dev("completion_deadline", SHORT_QUOTE, change="reduce the delay damages", evidence="reduce the delay damages", new_text=""),
                dev("completion_deadline", SHORT_QUOTE, change="reduce the delay damages", evidence="reduce the delay damages", new_text=old_ld())):
        d = validate(empty(deviations=[raw]), lib(), "reduce the delay damages").deviations[0]
        assert d.new_text == "" and d.rewrite_problem and d.old_text == old_ld()


def test_the_ais_own_good_sentence_is_used_as_it_is():
    assert run([modify(new_ld())]).deviations[0].written_by == ""


def test_the_system_never_replaces_an_ai_sentence_that_passed():
    good = new_ld().replace("per day", "each day")                                          # a legitimate extra edit inside the quote
    d = run([modify(good)]).deviations[0]
    assert d.new_text == good and d.written_by == ""


def test_a_missing_rewrite_is_repaired_when_the_figure_is_clear_and_a_problem_when_not():
    raw = modify(new_ld())
    del raw["new_text"]
    d = run([raw]).deviations[0]
    assert d.new_text == new_ld() and d.written_by == "figure"
    assert run([modify("")]).deviations[0].new_text == new_ld()


def test_a_remove_part_is_not_rewritten_by_the_figure_repair():
    d = dev("completion_deadline", SHORT_QUOTE, change_type="remove_part", change="remove the rate of 0.05", evidence="remove 0.05", new_text="")
    got = validate(empty(deviations=[d]), lib(), "remove the rate of 0.05").deviations[0]
    assert got.new_text == "" and got.written_by == ""


def test_the_prompt_asks_for_short_quotes_and_whole_sentences():
    assert "Keep it short" in SYSTEM_PROMPT and "never a whole sentence" in SYSTEM_PROMPT
    assert "from its first word to its last word, not only the words of provision_quote" in SYSTEM_PROMPT


def test_a_clause_that_already_says_it_is_not_proposed_again():
    applied = library_for({}, edits=[{"id": "x", "clause_key": "completion_deadline", "change_type": "modify", "old": old_ld(),
                                      "new": new_ld(), "summary": "s"}])
    raw = dev("completion_deadline", "at the rate of 0.03 (zero point zero three) percent of the Contract Price per day",
              change="Reduce the rate to 0.03% per day", evidence=REQUEST, new_text=new_ld())
    result = validate(empty(deviations=[raw]), applied, REQUEST)
    assert result.deviations == [] and any("already has that wording" in n for n in result.notes)


def test_a_sentence_given_back_unchanged_is_a_problem_when_there_is_no_figure_to_write():
    raw = dev("completion_deadline", SHORT_QUOTE if "SHORT_QUOTE" in globals() else QUOTE, change="Reduce the delay damages", evidence="reduce the delay damages",
              new_text=old_ld())
    d = validate(empty(deviations=[raw]), lib(), "reduce the delay damages").deviations[0]
    assert d.rewrite_problem == "The AI gave back the sentence unchanged." and d.new_text == "" and d.written_by == ""


def test_a_quote_that_spans_two_sentences_keeps_the_request_but_cannot_be_rewritten():
    clause = next(c for c in lib() if c.key == "completion_deadline")
    first, second = clause.items[0].text.split(), clause.items[1].text.split()
    across = " ".join(first[-5:] + second[:4])                   # the end of one numbered sentence and the start of the next
    raw = dev("completion_deadline", across, change="Reduce the rate to 0.03% per day", evidence=REQUEST, new_text=new_ld())
    result = run([raw])
    assert len(result.deviations) == 1 and result.deviations[0].new_text == ""
    assert result.deviations[0].rewrite_problem == "I could not tell which single sentence the change applies to."
    inside = run([modify(new_ld())])
    assert inside.deviations[0].new_text                         # a quote inside one sentence is fine


# ---------------------------------------------------------------- adding a sentence
def test_an_added_sentence_is_checked_for_figures_and_repeats():
    ask = "add a 24 months warranty"
    ok = dev("completion_deadline", "", change_type="add", change=ask, evidence=ask, new_text="The warranty period is 24 (twenty-four) months.")
    d = validate(empty(deviations=[ok]), lib(), ask).deviations[0]
    assert d.new_text == "The warranty period is 24 (twenty-four) months." and d.old_text == ""
    bad = dict(ok, new_text="The warranty period is 36 (thirty-six) months.")
    assert "figure that you did not give" in validate(empty(deviations=[bad]), lib(), ask).deviations[0].rewrite_problem
    existing = old_ld()
    again = dict(ok, new_text=existing)
    result = validate(empty(deviations=[again]), lib(), ask)
    assert result.deviations == [] and any("already has that wording" in n for n in result.notes)


# ---------------------------------------------------------------- clauses drafted in the session
def drafted_library():
    return library_for({}, None, [{"key": "drafted_1", "title": "Warranty", "before": "end",
                                   "sentences": ["The Contractor shall repair any defect within 7 (seven) days.", "The warranty lasts two years."]}])


def test_a_drafted_clause_can_be_reworded_but_not_added_or_removed():
    library = drafted_library()
    ask = "change the repair period to 15 days"
    raw = dev("drafted_1", "within 7 (seven) days", change=ask, evidence=ask, term="repair",
              new_text="The Contractor shall repair any defect within 15 (fifteen) days.")
    d = validate(empty(deviations=[raw]), library, ask).deviations[0]
    assert d.clause_key == "drafted_1" and d.old_text == "The Contractor shall repair any defect within 7 (seven) days." and d.new_text
    result = validate(empty(clause_actions=[action("drafted_1", "exclude", ask)]), library, ask)
    assert result.clause_actions == [] and any("unknown clause 'drafted_1'" in n for n in result.notes)


def test_the_library_text_marks_a_drafted_clause_and_the_prompt_says_how_to_treat_it():
    digest = clause_digest(drafted_library())
    block = next(b for b in digest.split("\n\n[") if "key: drafted_1" in b)
    assert "clause drafted in this session (reword only)" in block and "within 7 (seven) days" in block
    assert "drafted in this session" in SYSTEM_PROMPT and '"new_text"' in SYSTEM_PROMPT and "digits followed by the same figure in words" in SYSTEM_PROMPT


# ---------------------------------------------------------------- the call
def test_the_schema_has_the_new_text_and_keeps_drafted_clauses_out_of_actions():
    library = drafted_library()
    keys = [c.key for c in library]
    schema = build_schema(keys, [k for k in keys if k != "drafted_1"])
    deviation = schema["properties"]["deviations"]["items"]
    assert "new_text" in deviation["properties"] and "new_text" in deviation["required"]
    assert "drafted_1" in deviation["properties"]["clause_key"]["enum"]
    assert "drafted_1" not in schema["properties"]["clause_actions"]["items"]["properties"]["clause_key"]["enum"]
    assert build_schema(["a", "b"])["properties"]["clause_actions"]["items"]["properties"]["clause_key"]["enum"] == ["a", "b"]


def test_one_call_does_the_interpretation_and_the_rewriting():
    client = FakeClient(empty(deviations=[modify(new_ld())]))
    library = drafted_library()
    result = interpret_request(sample_term_sheet(), library, client, conversation=[{"role": "user", "content": REQUEST}])
    assert result.deviations[0].new_text and client.last_kwargs is not None
    sent = client.last_kwargs["response_format"]["json_schema"]["schema"]
    assert "drafted_1" not in sent["properties"]["clause_actions"]["items"]["properties"]["clause_key"]["enum"]
    assert "drafted_1" in sent["properties"]["deviations"]["items"]["properties"]["clause_key"]["enum"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} rewrite tests passed.")
