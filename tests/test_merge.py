"""Tests for the merge of two proposals that change the same sentence (core/wording.py merge_rewrite). Run: python -m tests.test_merge"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.wording import merge_rewrite

BASE = "The Owner may claim damages at the rate of 0.05 (zero point zero five) percent per day but not more than 5 (five) percent of the Price."
RATE_CHANGED = BASE.replace("0.05 (zero point zero five)", "0.5 (zero point five)")
CAP_REMOVED = BASE.replace(" but not more than 5 (five) percent of the Price", "")
BOTH = CAP_REMOVED.replace("0.05 (zero point zero five)", "0.5 (zero point five)")


def test_two_changes_in_different_places_are_both_made_in_either_order():
    assert merge_rewrite(BASE, RATE_CHANGED, CAP_REMOVED) == BOTH, "the rate was changed first, then the cap was taken out"
    assert merge_rewrite(BASE, CAP_REMOVED, RATE_CHANGED) == BOTH, "the cap was taken out first, then the rate was changed"


def test_a_sentence_nobody_changed_since_gives_the_proposal_as_it_is_and_a_proposal_that_changes_nothing_gives_the_sentence():
    assert merge_rewrite(BASE, BASE, CAP_REMOVED) == CAP_REMOVED
    assert merge_rewrite(BASE, RATE_CHANGED, BASE) == RATE_CHANGED
    assert merge_rewrite(BASE, RATE_CHANGED, RATE_CHANGED) == RATE_CHANGED, "the same change twice is one change"


def test_the_same_change_made_by_both_counts_once_next_to_another_change():
    both_made_it = merge_rewrite(BASE, RATE_CHANGED, BOTH)
    assert both_made_it == BOTH


def test_two_changes_to_the_same_words_are_not_merged():
    week = BASE.replace("per day", "per week")
    month = BASE.replace("per day", "per month")
    assert merge_rewrite(BASE, week, month) is None
    assert merge_rewrite(BASE, RATE_CHANGED, BASE.replace("0.05 (zero point zero five) percent", "0.07 (zero point zero seven) percent")) is None


def test_an_insertion_that_touches_another_change_is_not_merged_but_two_apart_are():
    start = "A B C D E F"
    assert merge_rewrite(start, "A B X C D E F", "A B C D E Y F") == "A B X C D E Y F"
    assert merge_rewrite(start, "A B X C D E F", "A B Y C D E F") is None, "two insertions at the same place: which comes first is not known"
    assert merge_rewrite(start, "A B X C D E F", "A B D E F") is None, "an insertion where the other change takes words out"


def test_case_and_spacing_do_not_matter_when_comparing_but_each_sides_words_are_kept():
    base = "The  Owner shall PAY within 14 days."
    assert merge_rewrite(base, "the owner shall pay within 14 days.", "The Owner shall pay within 21 days.") == "The Owner shall pay within 21 days."
    assert merge_rewrite(base, "The Owner shall pay within 30 days.", "THE OWNER shall PAY within 14 days.") == "The Owner shall pay within 30 days."


def test_without_a_base_nothing_is_merged():
    assert merge_rewrite("", "a b", "a c") is None


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} merge tests passed.")
