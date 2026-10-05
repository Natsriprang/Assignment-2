"""Parses a term sheet .xlsx matching term_sheet_template_EN.xlsx's layout: column B is the field
label, column C is the value (left blank until filled in -- so any non-empty C cell is real data,
no placeholder matching needed), column D is notes. Installment rows are found by scanning column
B for the pattern 'Installment N', so a term sheet with 5 rows, 7 rows, or any other count parses
correctly -- the row count is never assumed to be fixed."""
import datetime
import re

import openpyxl

from core.capacity import format_number, parse_capacity
from core.deadline import apply_import
from core.term_sheet_fields import Installment, TermSheet

INSTALLMENT_PATTERN = re.compile(r"installment\s*(\d+)", re.IGNORECASE)
PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# Cell positions matching term_sheet_template_EN.xlsx's layout (column B = label, column C = value).
FIELD_CELLS = {
    "project_name": "C3",
    "project_location": "C4",
    "capacity": "C6",
    "contract_no": "C7",
    "contract_date": "C8",
    "owner_name": "C9",
    "owner_reg_no": "C10",
    "owner_signatory": "C11",
    "owner_address": "C13",
    "contractor_name": "C14",
    "contractor_reg_no": "C15",
    "contractor_signatory": "C16",
    "contractor_address": "C18",
    "roof_owner": "C25",
    "contract_price_number": "C35",
    "contract_price_words": "C36",
    "vat_treatment": "C37",
    "start_date": "C60",
    "completion_date": "C61",
    "owner_contact_name": "C70",
    "owner_contact_position": "C71",
    "owner_contact_location": "C72",
    "owner_contact_phone": "C73",
    "owner_contact_email": "C74",          # a row of its own under each phone row
    "contractor_contact_name": "C75",
    "contractor_contact_position": "C76",
    "contractor_contact_location": "C77",
    "contractor_contact_phone": "C78",
    "contractor_contact_email": "C79",
}

# The layout before the email rows were added: phone and email shared one cell, and the Contractor's block started at row 74.
LEGACY_CONTACT_CELLS = {
    "owner_contact_name": "C70", "owner_contact_position": "C71", "owner_contact_location": "C72", "owner_contact_phone": "C73",
    "contractor_contact_name": "C74", "contractor_contact_position": "C75", "contractor_contact_location": "C76",
    "contractor_contact_phone": "C77",
}
EMAIL_LABEL = re.compile(r"e-?\s?mail|\u0e2d\u0e35\u0e40\u0e21\u0e25", re.IGNORECASE)


def field_cells(ws):
    """The cells to read. A sheet whose label column names an email row where one is expected has the email rows; any other
    sheet is read in the layout it had before them (and its phone cell is the phone, with no email)."""
    if any(EMAIL_LABEL.search(str(ws[c].value or "")) for c in ("B74", "B79")):
        return dict(FIELD_CELLS)
    cells = {k: v for k, v in FIELD_CELLS.items() if not k.endswith("_contact_email")}
    cells.update(LEGACY_CONTACT_CELLS)
    return cells


def _clean(value):
    if value in (None, ""):
        return ""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime("%d %B %Y")
    return str(value).strip()


def parse_xlsx(file) -> TermSheet:
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb[wb.sheetnames[0]]

    ts = TermSheet()
    for field_name, cell in field_cells(ws).items():
        value = _clean(ws[cell].value)
        if value:
            setattr(ts, field_name, value)

    value, unit = parse_capacity(ts.capacity, ts.capacity_unit)
    if value is not None:
        ts.capacity, ts.capacity_unit = format_number(value), unit

    installments = {}
    for row in ws.iter_rows():
        for cell in row:
            # column 2 == "B". Checked by number, not `.column_letter`, because a merged cell
            # (other than its top-left anchor) is a MergedCell object that lacks that attribute.
            if cell.column != 2 or not isinstance(cell.value, str):
                continue
            m = INSTALLMENT_PATTERN.search(cell.value)
            if not m:
                continue
            number = m.group(1)
            # The % is written inside this same label cell, e.g. "Installment 1 (10%)", not in its
            # own column -- so it has to be pulled out of cell.value itself, not a separate cell.
            pct_match = PERCENT_PATTERN.search(cell.value)
            condition_cell = ws.cell(row=cell.row, column=3)
            docs_cell = ws.cell(row=cell.row, column=4)
            installments[number] = Installment(
                number=number,
                percent=pct_match.group(1) if pct_match else "",
                condition=_clean(condition_cell.value),
                required_docs=_clean(docs_cell.value),
            )

    ts.installments = [installments[k] for k in sorted(installments, key=int)]
    apply_import(ts)
    return ts