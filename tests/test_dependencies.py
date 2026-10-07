"""Tests for the clauses that point at another clause by topic (core/dependencies.py). Run: python -m tests.test_dependencies"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clause_data import build_library
from core.dependencies import DEPENDENCIES, broken_references
from core.draft_state import library_for
from core.wording import norm, units


def test_every_phrase_of_the_table_is_still_in_its_clause():
    library = {c.key: c for c in build_library()}
    for source, target, phrase in DEPENDENCIES:
        assert source in library and target in library, (source, target)
        assert any(phrase.lower() in norm(text).lower() for _, text in units(library[source])), f"{source}: {phrase!r}"


def test_the_standard_draft_has_no_broken_reference():
    assert broken_references(library_for({})) == []


def test_taking_out_force_majeure_breaks_two_clauses():
    got = broken_references(library_for({"force_majeure": False}))
    assert [(g["clause_key"], g["target_key"]) for g in got] == [("suspension", "force_majeure"), ("termination", "force_majeure")]
    assert "force majeure" in got[0]["sentence"].lower() and got[0]["target"] == "Force Majeure"


def test_taking_out_suspension_breaks_termination_only():
    got = broken_references(library_for({"suspension": False}))
    assert [(g["clause_key"], g["target_key"]) for g in got] == [("termination", "suspension")]
    assert got[0]["sentence"].startswith("(c) the Works are suspended")


def test_a_clause_that_is_out_does_not_refer_to_anything():
    got = broken_references(library_for({"force_majeure": False, "suspension": False, "termination": False}))
    assert got == []


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} dependency tests passed.")
