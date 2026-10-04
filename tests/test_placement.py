"""Tests for placing a drafted clause where its references sit in the author's own contracts.
Run: python -m tests.test_placement"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.drafting import validate_draft
from ai.references import Pick, Selection
from core.clause_data import build_library
from core.placement import placement_from_references
from core.reference_library import load_references

REFS = load_references()
LIBRARY = [(c.key, c.title, c.included) for c in build_library()]


def ref(source, before):
    return SimpleNamespace(source=source, before_clause=before)


# ---------------------------------------------------------------------------- the reference data
def test_each_reference_knows_which_of_our_clauses_follows_it_in_its_own_contract():
    assert REFS["ca-6"].before_clause == "completion_deadline"         # Guarantee, then Completion deadline
    assert REFS["epc-6"].before_clause == "completion_deadline"        # Warranty, then Completion deadline
    assert REFS["gov-8"].before_clause == "contractor_representations"
    assert REFS["ca-16"].before_clause is None                          # the last clause has nothing after it
    assert all(r.before_clause is None or r.before_clause in {k for k, _, _ in LIBRARY} for r in REFS.values())


# ---------------------------------------------------------------------------- the rule
def test_warranty_references_place_the_clause_before_completion_deadline():
    used = [REFS["ca-6"], REFS["epc-6"], REFS["gov-8"]]
    before, reason = placement_from_references(used, LIBRARY)
    assert before == "completion_deadline"                              # two of the three agree, the third is outvoted
    assert reason == "before \u201cCompletion Deadline\u201d."                      # says where, not who suggested it


def test_one_source_gives_the_same_wording():
    before, reason = placement_from_references([REFS["ca-6"]], LIBRARY)
    assert before == "completion_deadline" and reason == "before \u201cCompletion Deadline\u201d."
    assert "CA" not in reason and "AI" not in reason and "contract" not in reason


def test_a_tie_goes_to_the_reference_chosen_first():
    assert placement_from_references([REFS["ca-6"], REFS["gov-8"]], LIBRARY)[0] == "completion_deadline"
    assert placement_from_references([REFS["gov-8"], REFS["ca-6"]], LIBRARY)[0] == "contractor_representations"


def test_references_without_a_position_give_no_suggestion():
    assert placement_from_references([], LIBRARY) is None
    assert placement_from_references([REFS["ca-16"]], LIBRARY) is None
    assert placement_from_references([ref("X", "no_such_clause")], LIBRARY) is None


def test_a_target_that_is_switched_off_moves_the_clause_to_the_next_clause_in_the_draft():
    library = [(k, t, i and k != "completion_deadline") for k, t, i in LIBRARY]
    before, reason = placement_from_references([REFS["ca-6"]], library)
    assert before == "personnel_responsibility" and reason == (
        "before \u201cResponsibility to the Personnel of the Contractor\u201d (\u201cCompletion Deadline\u201d is not in this draft).")
    keys = [k for k, _, _ in LIBRARY]
    after = keys[keys.index("completion_deadline") + 1:]
    library = [(k, t, i and k not in ["completion_deadline", *after]) for k, t, i in LIBRARY]
    before, reason = placement_from_references([REFS["ca-6"]], library)
    assert before == "end" and reason.startswith("at the end (")


# ---------------------------------------------------------------------------- the drafting step uses it
def test_the_hint_replaces_the_models_own_suggestion_without_a_fallback_note():
    raw = {"title": "Warranty", "sentences": ["Text."], "notes": [], "placement": {"before": "made_up", "reason": "x"}}
    sel = Selection("req", [Pick("ca-6", "fits")])
    order = [("completion_deadline", "Completion Deadline"), ("force_majeure", "Force Majeure")]
    d = validate_draft("req", raw, sel, REFS, order, ("completion_deadline", "before \u201cCompletion Deadline\u201d."))
    assert (d.placement_before, d.placement_reason, d.notes) == ("completion_deadline", "before \u201cCompletion Deadline\u201d.", [])
    d = validate_draft("req", raw, sel, REFS, order)                    # no hint: the old fallback still applies
    assert d.placement_before == "force_majeure" and any("position" in n for n in d.notes)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} placement tests passed.")
