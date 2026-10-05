"""Tests for the separate phone and email of the notice contacts, and the Excel layouts that hold them.
Run: python -m tests.test_contacts"""
import io
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from core.term_sheet_fields import TermSheet, ensure_fields
from core.xlsx_parser import FIELD_CELLS, parse_xlsx


def workbook(cells):
    wb = openpyxl.Workbook()
    for cell, value in cells.items():
        wb.active[cell] = value
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf


NEW = {"B70": "Owner contact - Name", "C70": "Somchai", "B71": "Owner contact - Position", "C71": "Manager", "B72": "Owner contact - Location",
       "C72": "Bangkok", "B73": "Owner contact - Phone", "C73": "02-111-2222", "B74": "Owner contact - Email", "C74": "somchai@owner.example",
       "B75": "Contractor contact - Name", "C75": "Malee", "B76": "Contractor contact - Position", "C76": "Engineer",
       "B77": "Contractor contact - Location", "C77": "Rayong", "B78": "Contractor contact - Phone", "C78": "03-333-4444",
       "B79": "Contractor contact - E-mail", "C79": "malee@builder.example"}


def test_a_sheet_with_email_rows_is_read_field_by_field():
    ts = parse_xlsx(workbook(NEW))
    assert (ts.owner_contact_name, ts.owner_contact_position, ts.owner_contact_location, ts.owner_contact_phone, ts.owner_contact_email) == \
        ("Somchai", "Manager", "Bangkok", "02-111-2222", "somchai@owner.example")
    assert (ts.contractor_contact_name, ts.contractor_contact_position, ts.contractor_contact_location, ts.contractor_contact_phone,
            ts.contractor_contact_email) == ("Malee", "Engineer", "Rayong", "03-333-4444", "malee@builder.example")


def test_an_email_alone_lands_in_the_email_field_and_a_phone_alone_in_the_phone_field():
    only_email = dict(NEW, C73=None)
    ts = parse_xlsx(workbook(only_email))
    assert ts.owner_contact_phone == "" and ts.owner_contact_email == "somchai@owner.example"
    only_phone = dict(NEW, C79=None, C74=None)
    ts = parse_xlsx(workbook(only_phone))
    assert ts.owner_contact_email == "" and ts.contractor_contact_email == "" and ts.contractor_contact_phone == "03-333-4444"


def test_the_email_label_may_be_in_either_email_row_and_in_thai():
    ts = parse_xlsx(workbook(dict(NEW, B74="Owner contact", B79="อีเมลผู้รับเหมา")))
    assert ts.owner_contact_email == "somchai@owner.example" and ts.contractor_contact_name == "Malee"
    ts = parse_xlsx(workbook(dict(NEW, B74="Owner contact - Fax", B79="Contractor contact - Email")))
    assert ts.contractor_contact_email == "malee@builder.example" and ts.contractor_contact_name == "Malee"


def test_the_layout_before_the_email_rows_is_still_read():
    old = {"B73": "Owner contact - Phone / email", "C70": "Somchai", "C71": "Manager", "C72": "Bangkok", "C73": "somchai@owner.example",
           "C74": "Malee", "C75": "Engineer", "C76": "Rayong", "C77": "03-333-4444"}
    ts = parse_xlsx(workbook(old))
    assert (ts.owner_contact_name, ts.owner_contact_phone, ts.owner_contact_email) == ("Somchai", "somchai@owner.example", "")
    assert (ts.contractor_contact_name, ts.contractor_contact_position, ts.contractor_contact_location, ts.contractor_contact_phone,
            ts.contractor_contact_email) == ("Malee", "Engineer", "Rayong", "03-333-4444", "")


def test_the_cells_above_the_contacts_do_not_move():
    ts = parse_xlsx(workbook(dict(NEW, C3="Rooftop PV", C35="200000", C37="exclusive", C60="03 October 2026", C61="10 October 2026")))
    assert (ts.project_name, ts.contract_price_number, ts.vat_treatment, ts.deadline_mode) == ("Rooftop PV", "200000", "exclusive", "calendar")
    assert FIELD_CELLS["owner_contact_phone"] == "C73" and FIELD_CELLS["owner_contact_email"] == "C74"
    assert FIELD_CELLS["contractor_contact_name"] == "C75" and FIELD_CELLS["contractor_contact_email"] == "C79"


def test_the_new_fields_exist_and_old_objects_get_them():
    ts = TermSheet()
    assert ts.owner_contact_email == "" and ts.contractor_contact_email == "" and not hasattr(ts, "start_days")
    old = ensure_fields(SimpleNamespace(project_name="P"))
    assert old.owner_contact_email == "" and old.contractor_contact_email == ""


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} contact tests passed.")
