"""Tests for the named clause parameters (caps on damages). Run: python -m tests.test_clause_params"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.interpret import clause_digest, term_sheet_text
from core.clause_data import build_library
from core.clause_params import (MARK_CLOSE, MARK_OPEN, PARAMS, effective, limits_of, number_words,
                                percent_phrase, percent_phrase_symbol, resolve_text)
from core.clauses import cross_reference_scan
from core.draft_state import library_for
from core.renumber import renumber_and_render
from core.term_sheet_fields import TermSheet

# The two sentences exactly as they were written before they were parametrised.
ORIGINAL_LD = ("Unless otherwise agreed by the Parties, if the Contractor fails to complete the Works within the "
               "stipulated deadline as specified in clause 6.1, the Owner has the right to claim liquidated damages "
               "from the Contractor at the rate of 0.05 (zero point zero five) percent of the Contract Price per day "
               "but not more than 5 (five) percent of the Contract Price.")
ORIGINAL_DAMAGES = ("In any case where the Contractor breaches this Agreement or causes damage to the Owner, the "
                    "Contractor agrees that the Owner may deduct the amount of such damages or expenses from the "
                    "performance bond (contract security) or from the remaining Contract Price, provided that the "
                    "total damages shall not exceed 5% (five percent) of the Contract Price, within 15 (fifteen) "
                    "days of the Owner\u2019s written notice to the Contractor.")


def item_texts(library, key):
    return [i.text for c in library if c.key == key for i in c.items]


# ---------------------------------------------------------------------------- wording
def test_number_words():
    assert [number_words(v) for v in (5, 12, 25, 100, 0.05, 2.5, 7.25)] == [
        "five", "twelve", "twenty-five", "one hundred", "zero point zero five", "two point five",
        "seven point two five"]


def test_percent_phrases():
    assert percent_phrase(5) == "5 (five) percent" and percent_phrase(5.0) == "5 (five) percent"
    assert percent_phrase(0.05) == "0.05 (zero point zero five) percent"
    assert percent_phrase_symbol(5) == "5% (five percent)" and percent_phrase_symbol(12.5) == "12.5% (twelve point five percent)"


def test_invalid_percentages_are_rejected():
    for bad in (0, -1, 100.5, float("nan"), float("inf"), "5", True, 1.234):
        try:
            percent_phrase(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should have been rejected")


# ---------------------------------------------------------------------------- resolution
def test_default_values_reproduce_the_original_sentences_exactly():
    library = library_for({})
    assert ORIGINAL_LD in item_texts(library, "completion_deadline")
    assert ORIGINAL_DAMAGES in item_texts(library, "termination")


def test_a_custom_cap_changes_figure_and_words_together():
    library = library_for({}, {"ld_cap": 7.5, "damages_cap": 10})
    assert "per day but not more than 7.5 (seven point five) percent of the Contract Price." in " ".join(item_texts(library, "completion_deadline"))
    assert "shall not exceed 10% (ten percent) of the Contract Price, within 15" in " ".join(item_texts(library, "termination"))


def test_no_cap_removes_the_fragment_and_keeps_the_sentence_correct():
    library = library_for({}, {"ld_cap": None, "damages_cap": None})
    ld = [t for t in item_texts(library, "completion_deadline") if "liquidated damages" in t][0]
    damages = [t for t in item_texts(library, "termination") if "performance bond" in t][0]
    assert ld.endswith("at the rate of 0.05 (zero point zero five) percent of the Contract Price per day.")
    assert "from the remaining Contract Price, within 15 (fifteen) days of the Owner\u2019s written notice" in damages
    assert "not more than" not in ld and "shall not exceed" not in damages


def test_one_cap_can_be_removed_without_touching_the_other():
    library = library_for({}, {"damages_cap": None})
    assert ORIGINAL_LD in item_texts(library, "completion_deadline")
    assert "shall not exceed" not in " ".join(item_texts(library, "termination"))


def test_resolve_text_edge_cases():
    assert resolve_text("No markers here.") == "No markers here."
    marked = f"A{MARK_OPEN}ld_cap| capped at {{pct}}{MARK_CLOSE}, B{MARK_OPEN}damages_cap| and {{pct_sym}}{MARK_CLOSE}."
    assert resolve_text(marked) == "A capped at 5 (five) percent, B and 5% (five percent)."
    assert resolve_text(marked, {"ld_cap": None, "damages_cap": None}) == "A, B."
    try:
        resolve_text(f"x{MARK_OPEN}unknown| y{MARK_CLOSE}")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown parameter must raise")


def test_effective_rejects_bad_input():
    assert effective({"ld_cap": None})["damages_cap"] == 5.0
    for bad in ({"made_up": 5}, {"ld_cap": 0}, {"ld_cap": 150}):
        try:
            effective(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} should have been rejected")


# ---------------------------------------------------------------------------- library, preview, AI text
def test_no_marker_survives_anywhere_in_a_resolved_library():
    for limits in (None, {"ld_cap": None, "damages_cap": None}, {"ld_cap": 3, "damages_cap": 12.5}):
        library = library_for({c.key: True for c in build_library()}, limits)
        for c in library:
            texts = list(c.plain_paragraphs) + [t for i in c.items for t in [i.text] + i.lettered]
            texts += [cell for t in c.tables for row in t["rows"] for cell in row] + [cell for row in c.table_rows for cell in row]
            assert not [t for t in texts if MARK_OPEN in t or MARK_CLOSE in t], c.key


def test_numbering_and_cross_references_are_unaffected():
    with_caps = renumber_and_render(library_for({}))
    without = renumber_and_render(library_for({}, {"ld_cap": None, "damages_cap": None}))
    assert [(n, c.key) for n, c, _ in with_caps] == [(n, c.key) for n, c, _ in without]
    assert [len(i) for _, _, i in with_caps] == [len(i) for _, _, i in without]       # same number of items
    assert len(cross_reference_scan(library_for({}))) == len(cross_reference_scan(library_for({}, {"ld_cap": None})))


def test_the_model_sees_the_resolved_text():
    digest = clause_digest(library_for({}, {"damages_cap": None, "ld_cap": 7}))
    assert "7 (seven) percent" in digest and "shall not exceed" not in digest and MARK_OPEN not in digest


# ---------------------------------------------------------------------------- term sheet
def test_limits_of_defaults_and_old_term_sheet_objects():
    assert limits_of(None) == {"ld_cap": 5.0, "damages_cap": 5.0}
    assert limits_of(SimpleNamespace()) == {"ld_cap": 5.0, "damages_cap": 5.0}          # an object from an older app version
    ts = TermSheet()
    ts.limits = {"damages_cap": None, "stray_key": 9}
    assert limits_of(ts) == {"ld_cap": 5.0, "damages_cap": None}


def test_term_sheet_text_includes_the_caps_so_a_change_is_noticed():
    ts = TermSheet(project_name="P")
    base = term_sheet_text(ts)
    assert "limits: cap on delay damages 5%; cap on total damages deducted 5%" in base
    ts.limits = {"damages_cap": None}
    assert term_sheet_text(ts) != base and "cap on total damages deducted none" in term_sheet_text(ts)


def test_registry_is_consistent_with_the_template():
    raw = " ".join(i.text for c in build_library() for i in c.items)
    for key in PARAMS:
        assert f"{MARK_OPEN}{key}|" in raw, f"{key} is declared but not used in any clause"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} clause parameter tests passed.")
