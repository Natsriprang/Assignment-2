"""Tests for the rules written as notes beside the fields (column D), checked by code. Run: python -m tests.test_field_rules"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.field_rules import rule_warnings, template_notes
from core.term_sheet_fields import TermSheet
from core.xlsx_parser import parse_xlsx_report
from tests.xlsx_helper import workbook

NOTES = {"owner_reg_no": "13 digits", "contractor_reg_no": "13 digits",
         "contract_date": "Must be consistent with the last 6 digits of the contract no.",
         "contract_no": "8 digits: first 2 start from 01; digits 4-6 are day/month/year (2 digits each)"}


def test_a_value_with_the_right_number_of_digits_passes():
    for value in ("1020304050601", "1-0203-04050-60-1", " 1020304050601 ", "1 0203 04050 60 1"):
        assert rule_warnings(TermSheet(owner_reg_no=value), NOTES) == [], value


def test_the_wrong_number_of_digits_or_other_characters_is_reported_with_the_page_name():
    w = rule_warnings(TermSheet(owner_reg_no="102030405060"), NOTES)
    assert w == ["Owner \u2013 Registration no. \u201c102030405060\u201d has 12 digits, but the term sheet's note says \u201c13 digits\u201d."]
    assert "has 14 digits" in rule_warnings(TermSheet(contractor_reg_no="10203040506012"), NOTES)[0]
    assert rule_warnings(TermSheet(owner_reg_no="10203040506AB"), NOTES)[0].startswith(
        "Owner \u2013 Registration no. \u201c10203040506AB\u201d contains characters other than digits")


def test_an_empty_value_is_not_judged_here_that_is_the_blanks_check():
    assert rule_warnings(TermSheet(), NOTES) == [] and rule_warnings(None, NOTES) == [] and rule_warnings(TermSheet(owner_reg_no="1"), {}) == []


def test_the_contract_date_must_match_the_last_six_digits_of_the_contract_no():
    ok = TermSheet(contract_no="UM031026", contract_date="03 October 2026")
    assert rule_warnings(ok, NOTES) == [] and rule_warnings(TermSheet(contract_no="01-031026", contract_date="2026-10-03"), NOTES) == []
    bad = rule_warnings(TermSheet(contract_no="UM123426", contract_date="03 October 2026"), NOTES)
    assert len(bad) == 1 and "Contract date \u201c03 October 2026\u201d does not match the last 6 digits of Contract no. \u201cUM123426\u201d" in bad[0]
    assert "would end in 031026" in bad[0]
    assert rule_warnings(TermSheet(contract_no="UM12", contract_date="03 October 2026"), NOTES)[0].count("would end in 031026") == 1
    assert rule_warnings(TermSheet(contract_no="UM031026", contract_date="soon"), NOTES) == []      # not a date: not judged
    assert rule_warnings(TermSheet(contract_no="", contract_date="03 October 2026"), NOTES) == []


def test_only_notes_that_say_something_exact_are_checked_by_code():
    ts = TermSheet(contract_no="UM123426")                          # the contract no.'s own note is too loose to check exactly
    assert rule_warnings(ts, NOTES) == []


def test_full_names_need_at_least_two_words_each():
    note = {"owner_signatory": "Full name(s), matching the company's signing authority"}
    for ok in ("Nat Sriprang", "Nat Sriprang\nSomchai Jaidee", "Nat Sriprang and Somchai Jaidee", "Nat Sriprang; Somchai Jaidee", "Nat Sriprang, Somchai Jaidee",
               "Somchai  Jaidee", " Nat Sriprang "):
        assert rule_warnings(TermSheet(owner_signatory=ok), note) == [], ok
    w = rule_warnings(TermSheet(owner_signatory="Nat"), note)
    assert w == ["Owner \u2013 Authorised signatory \u201cNat\u201d looks like a first name only, but the term sheet's note says "
                 "\u201cFull name(s), matching the company's signing authority\u201d."]
    w = rule_warnings(TermSheet(owner_signatory="Nat Sriprang\nSomchai"), note)
    assert w == ["Owner \u2013 Authorised signatory \u201cNat Sriprang / Somchai\u201d: \u201cSomchai\u201d looks like a first name only, but the term sheet's "
                 "note says \u201cFull name(s), matching the company's signing authority\u201d."]
    w = rule_warnings(TermSheet(owner_signatory="Nat\nSomchai"), note)
    assert len(w) == 1 and "\u201cNat\u201d, \u201cSomchai\u201d look like first names only" in w[0]
    assert rule_warnings(TermSheet(owner_signatory=""), note) == []                       # empty: the blanks check's business
    assert rule_warnings(TermSheet(contractor_signatory="Noom"), {"contractor_signatory": "Full name(s)"})[0].startswith("Contractor \u2013 Authorised signatory")
    assert rule_warnings(TermSheet(owner_signatory="Nat"), {"owner_signatory": "The person who signs"}) == []   # only a note that asks for full names


def test_the_import_reads_each_note_and_the_template_ships_with_its_notes():
    ts, rep = parse_xlsx_report(workbook({"owner_reg_no": "1"}, extra_rows=[]))
    assert rep.notes == {}                                               # a sheet without notes has none
    import io, openpyxl
    wb = openpyxl.load_workbook(workbook({"owner_reg_no": "1"})); ws = wb.active
    for row in ws.iter_rows(min_col=2, max_col=2):
        if row[0].value == "Owner registration no.":
            ws.cell(row=row[0].row, column=4, value="  13 digits  ")
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    assert parse_xlsx_report(buf)[1].notes == {"owner_reg_no": "13 digits"}
    notes = template_notes()
    assert notes["owner_reg_no"] == "13 digits" and notes["contractor_reg_no"] == "13 digits" and "last 6 digits" in notes["contract_date"]
    assert "full name" in notes["owner_signatory"].lower()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} field rule tests passed.")
