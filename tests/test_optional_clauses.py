"""Tests for the optional clauses taken from the reference library: late-payment interest (an item of the clause on payment), the guarantee,
the performance security and the Owner's rights following termination. Run: python -m tests.test_optional_clauses"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clause_data import build_library
from core.clauses import cross_reference_scan
from core.draft_state import library_for
from core.renumber import renumber_and_render
from core.wording import units
from tests.test_interpret import sample_term_sheet

NEW = ["late_payment_interest", "performance_security", "guarantee", "owner_termination_rights"]
DEFAULTS_BEFORE = ["construction_terms", "attachments", "price_payment", "contractor_representations", "taxation", "completion_deadline",
                   "personnel_responsibility", "confidentiality", "suspension", "inspection", "drawing_discrepancy", "termination",
                   "force_majeure", "notice", "miscellaneous"]


def numbered(included=None):
    return renumber_and_render(library_for(included or {}, None, None, sample_term_sheet(), {}))


def test_the_four_clauses_are_optional_and_out_of_the_draft_by_default():
    by_key = {c.key: c for c in build_library()}
    for key in NEW:
        assert by_key[key].optional and not by_key[key].included, key
    assert [c.key for _, c, _ in numbered()] == DEFAULTS_BEFORE


def test_default_draft_text_and_numbers_are_the_same_as_before():
    rendered = numbered()
    assert [n for n, _, _ in rendered] == [str(i) for i in range(1, 16)]
    price = next(items for _, c, items in rendered if c.key == "price_payment")
    assert [line[:3] for line in price] == ["3.1", "3.2", "3.3", "3.4", "3.5"]


def test_late_payment_interest_is_the_last_item_of_the_payment_clause_and_not_a_clause_of_its_own():
    rendered = numbered({"late_payment_interest": True})
    keys = [c.key for _, c, _ in rendered]
    assert "late_payment_interest" not in keys and len(keys) == 15                    # not a clause of its own
    library = library_for({"late_payment_interest": True}, None, None, sample_term_sheet(), {})
    assert next(c for c in library if c.key == "late_payment_interest").included         # but still ticked, so that the picker keeps showing it
    price = next(items for _, c, items in rendered if c.key == "price_payment")
    assert price[-1].startswith("3.6 In the event that the Owner fails to make the payment") and "0.05 (zero point zero five) percent per day" in price[-1]


def test_the_interest_item_points_at_the_days_to_pay_and_follows_a_renumbering():
    rendered = numbered({"late_payment_interest": True, "attachments": False})
    number, items = next((n, i) for n, c, i in rendered if c.key == "price_payment")
    assert number == "2" and "clause 2.3," in items[-1] and "clause 3.3" not in items[-1]


def test_the_interest_item_is_not_in_the_contract_when_the_payment_clause_is_out():
    keys = [c.key for _, c, _ in numbered({"late_payment_interest": True, "price_payment": False})]
    assert "price_payment" not in keys and "late_payment_interest" not in keys


def test_the_other_three_clauses_come_in_where_the_reference_documents_have_them():
    keys = [c.key for _, c, _ in numbered({k: True for k in NEW})]
    assert len(keys) == 18
    assert keys.index("guarantee") == keys.index("taxation") + 1                       # as the guarantee follows the taxes in the template
    assert keys.index("owner_termination_rights") == keys.index("termination") + 1
    assert keys.index("performance_security") < keys.index("contractor_representations")


def test_a_ticked_optional_clause_is_not_a_change_and_the_cross_reference_check_stays_quiet():
    library = library_for({k: True for k in NEW}, None, None, sample_term_sheet(), {})
    assert cross_reference_scan(library) == []
    assert cross_reference_scan(library_for({}, None, None, sample_term_sheet(), {})) == []


def test_the_merged_item_can_be_reworded_like_any_sentence_of_the_clause():
    library = library_for({"late_payment_interest": True}, None, None, sample_term_sheet(), {})
    price = next(c for c in library if c.key == "price_payment")
    old = next(text for _, text in units(price) if "pay interest" in text)
    edit = {"id": "e1", "clause_key": "price_payment", "change_type": "modify", "old": old, "new": old.replace("0.05 (zero point zero five)", "0.1 (zero point one)"),
            "summary": "interest"}
    failed = []
    library = library_for({"late_payment_interest": True}, None, None, sample_term_sheet(), [edit], failed)
    assert not failed
    assert "0.1 (zero point one) percent per day" in next(c for c in library if c.key == "price_payment").items[-1].text


def test_the_blanks_of_the_new_clauses_stay_visible():
    text = " ".join(line for _, c, items in numbered({"guarantee": True, "performance_security": True}) if c.key in ("guarantee", "performance_security")
                    for line in items)
    assert "[*]" in text


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print("PASS", name)
    print(f"{len(tests)} optional clause tests passed.")
