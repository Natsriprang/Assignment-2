"""Tests for the VAT choice: reading a term sheet's wording, the price clause, and the notice. Run: python -m tests.test_vat"""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from core.clause_data import build_library
from core.draft_state import library_for
from core.fill import fill_template
from core.renumber import renumber_and_render
from core.term_sheet_fields import TermSheet
from core.vat import CLAUSE_PHRASE, normalise_vat, vat_choice, vat_warning
from core.xlsx_parser import parse_xlsx
from tests.xlsx_helper import workbook


def price_sentence(library):
    return next(items[0] for n, c, items in renumber_and_render(library) if c.key == "price_payment")


def test_what_a_term_sheet_may_say_is_read_as_inclusive_or_exclusive():
    inclusive = ["inclusive", "Inclusive", "INCLUSIVE OF VAT", "Inclusive of VAT", "incl. VAT", "including VAT", "VAT included",
                 "VAT-inclusive", "\u0e23\u0e27\u0e21 VAT", "\u0e23\u0e27\u0e21\u0e20\u0e32\u0e29\u0e35\u0e21\u0e39\u0e25\u0e04\u0e48\u0e32\u0e40\u0e1e\u0e34\u0e48\u0e21"]
    exclusive = ["exclusive", "Exclusive", "Exclusive of VAT", "EXCL. VAT", "excluding VAT", "VAT excluded", "not inclusive of VAT",
                 "not including VAT", "price plus VAT", "VAT extra", "before VAT", "\u0e44\u0e21\u0e48\u0e23\u0e27\u0e21 VAT"]
    for text in inclusive:
        assert normalise_vat(text) == "inclusive", text
    for text in exclusive:
        assert normalise_vat(text) == "exclusive", text


def test_anything_unclear_is_not_a_choice():
    for text in ["", "   ", None, "VAT 7%", "TBC", "inclusive / exclusive", "inclusive of VAT and exclusive of WHT", "7%"]:
        assert normalise_vat(text) == "", text


def test_vat_choice_reads_the_term_sheet_and_tolerates_old_objects():
    assert vat_choice(TermSheet(vat_treatment="Exclusive of VAT")) == "exclusive"
    assert vat_choice(TermSheet()) == "" and vat_choice(None) == "" and vat_choice(SimpleNamespace()) == ""


def test_the_price_clause_follows_a_real_choice():
    base = price_sentence(library_for({}))
    assert CLAUSE_PHRASE in base
    for raw, word in (("exclusive", "exclusive"), ("Exclusive of VAT", "exclusive"), ("Inclusive", "inclusive")):
        text = price_sentence(library_for({}, None, None, TermSheet(vat_treatment=raw)))
        assert f"THB [*] ([*]), {word} of VAT, the terms of payment" in text and CLAUSE_PHRASE not in text


def test_without_a_choice_the_template_wording_stays():
    for ts in (None, TermSheet(), TermSheet(vat_treatment="VAT 7%")):
        assert price_sentence(library_for({}, None, None, ts)) == price_sentence(library_for({}))


def test_only_the_price_clause_changes():
    plain = {c.key: [i.text for i in c.items] for c in library_for({})}
    filled = {c.key: [i.text for i in c.items] for c in library_for({}, None, None, TermSheet(vat_treatment="exclusive"))}
    assert [k for k in plain if plain[k] != filled[k]] == ["price_payment"]
    # the price sentence (VAT) and, since payment days now default to 30, the payment sentence; nothing else in that clause
    assert [i for i, (a, b) in enumerate(zip(plain["price_payment"], filled["price_payment"])) if a != b] == [0, 2]
    assert "exclusive of VAT" in filled["price_payment"][0] and "30 (thirty) working days" in filled["price_payment"][2]


def test_fill_template_is_idempotent_and_leaves_drafted_clauses_alone():
    library = fill_template(build_library(), TermSheet(vat_treatment="inclusive"))
    once = price_sentence(library)
    assert price_sentence(fill_template(library, TermSheet(vat_treatment="inclusive"))) == once
    drafted = [{"key": "drafted_1", "title": "Note", "sentences": [f"The price is {CLAUSE_PHRASE}."], "before": "end"}]
    lib = library_for({}, None, drafted, TermSheet(vat_treatment="exclusive"))
    assert any(CLAUSE_PHRASE in i.text for c in lib if c.key == "drafted_1" for i in c.items)


def test_the_notice_says_what_is_wrong_and_what_happens():
    plain = vat_warning(TermSheet())
    assert plain.startswith("VAT is not chosen.") and CLAUSE_PHRASE in plain and "term sheet says" not in plain
    odd = vat_warning(TermSheet(vat_treatment="VAT 7%"))
    assert "\u201cVAT 7%\u201d" in odd and "cannot be read" in odd
    assert vat_warning(TermSheet(vat_treatment="exclusive")) is None and vat_warning(TermSheet(vat_treatment="Inclusive of VAT")) is None


def test_the_xlsx_import_keeps_what_the_cell_said_so_nothing_is_overwritten():
    def sheet(value):
        return parse_xlsx(workbook({"vat_treatment": value}))
    assert vat_choice(sheet("Exclusive of VAT")) == "exclusive" and sheet("Exclusive of VAT").vat_treatment == "Exclusive of VAT"
    assert vat_choice(sheet("inclusive")) == "inclusive"
    odd = sheet("VAT 7%")
    assert vat_choice(odd) == "" and odd.vat_treatment == "VAT 7%"
    assert vat_choice(sheet(None)) == ""


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} VAT tests passed.")
