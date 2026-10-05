"""Tests for the separate phone and email of the notice contacts. Run: python -m tests.test_contacts"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.term_sheet_fields import TermSheet, ensure_fields
from core.xlsx_parser import parse_xlsx
from tests.xlsx_helper import workbook

CONTACTS = {"owner_contact_name": "Somchai", "owner_contact_position": "Manager", "owner_contact_location": "Bangkok",
            "owner_contact_phone": "02-111-2222", "owner_contact_email": "somchai@owner.example",
            "contractor_contact_name": "Malee", "contractor_contact_position": "Engineer", "contractor_contact_location": "Rayong",
            "contractor_contact_phone": "03-333-4444", "contractor_contact_email": "malee@builder.example"}


def test_each_contact_field_is_read_from_its_own_row():
    ts = parse_xlsx(workbook(CONTACTS))
    for name, value in CONTACTS.items():
        assert getattr(ts, name) == value, name


def test_an_email_alone_lands_in_the_email_field_and_a_phone_alone_in_the_phone_field():
    ts = parse_xlsx(workbook({k: v for k, v in CONTACTS.items() if k != "owner_contact_phone"}))
    assert ts.owner_contact_phone == "" and ts.owner_contact_email == "somchai@owner.example"
    ts = parse_xlsx(workbook({k: v for k, v in CONTACTS.items() if not k.endswith("_email")}))
    assert ts.owner_contact_email == "" and ts.contractor_contact_email == "" and ts.contractor_contact_phone == "03-333-4444"


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
