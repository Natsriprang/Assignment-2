"""Parses a term sheet .xlsx like term_sheet_template_EN.xlsx: column B is the field label, column C the value (left blank
until filled in, so any non-empty C cell is real data), column D notes.

Values are found by their LABEL in column B, never by row number, so rows may be inserted, deleted or reordered. A label
that cannot be found is reported, not guessed; a label that appears more than once is reported when its copies differ.
Installment rows are found by the pattern 'Installment N' in column B, so any number of them reads correctly. A value may
run over several lines inside its cell; the lines are kept."""
import datetime
import re
from dataclasses import dataclass, field

import openpyxl

from core.capacity import format_number, parse_capacity
from core.deadline import apply_import
from core.term_sheet_fields import Installment, TermSheet

INSTALLMENT_PATTERN = re.compile(r"installment\s*(\d+)", re.IGNORECASE)
PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%")

# term sheet field -> the label written in column B of the template
FIELD_LABELS = {
    "project_name": "Project name",
    "project_location": "Project location",
    "capacity": "Capacity (kWp or MW)",
    "contract_no": "Contract no.",
    "contract_date": "Contract date",
    "owner_name": "Owner",
    "owner_reg_no": "Owner registration no.",
    "owner_signatory": "Owner authorised signatory(ies)",
    "owner_address": "Owner registered office",
    "contractor_name": "Contractor",
    "contractor_reg_no": "Contractor registration no.",
    "contractor_signatory": "Contractor authorised signatory(ies)",
    "contractor_address": "Contractor registered office",
    "roof_owner": "Roof / site owner",
    "contract_price_number": "Contract Price (number)",
    "contract_price_words": "Contract Price (in words)",
    "vat_treatment": "VAT treatment",
    "start_date": "Start date",
    "completion_date": "Completion date",
    "owner_contact_name": "Owner contact name",
    "owner_contact_position": "Owner contact position",
    "owner_contact_location": "Owner contact location",
    "owner_contact_phone": "Owner contact phone",
    "owner_contact_email": "Owner contact email",
    "contractor_contact_name": "Contractor contact name",
    "contractor_contact_position": "Contractor contact position",
    "contractor_contact_location": "Contractor contact location",
    "contractor_contact_phone": "Contractor contact phone",
    "contractor_contact_email": "Contractor contact email",
}


@dataclass
class ImportReport:
    missing: list = field(default_factory=list)      # labels not found in column B
    conflicts: list = field(default_factory=list)    # sentences about repeated labels whose copies differ
    notes: dict = field(default_factory=dict)        # term sheet field -> the note beside its label (column D), when there is one

    @property
    def nothing_found(self):
        return len(self.missing) == len(FIELD_LABELS)


def _label_key(text):
    """A label compared without case, extra spaces or a trailing colon."""
    return " ".join(str(text).replace("\xa0", " ").split()).rstrip(":").strip().lower()


def _clean(value):
    if value in (None, ""):
        return ""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime("%d %B %Y")
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.strip() for line in text.strip().split("\n"))


def _same(a, b):
    """Copies that differ only in case or spacing ("100MW", "100 mw") are the same value."""
    return "".join(a.split()).lower() == "".join(b.split()).lower()


def parse_xlsx_report(file):
    """The term sheet read from the file, and a report of what could not be read."""
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb[wb.sheetnames[0]]

    rows_by_label = {}
    for row in ws.iter_rows():
        for cell in row:
            # column 2 == "B". Checked by number, not `.column_letter`, because a merged cell (other than its top-left
            # anchor) is a MergedCell object that lacks that attribute.
            if cell.column == 2 and isinstance(cell.value, str) and cell.value.strip():
                rows_by_label.setdefault(_label_key(cell.value), []).append(cell.row)

    ts, report = TermSheet(), ImportReport()
    for field_name, label in FIELD_LABELS.items():
        rows = rows_by_label.get(_label_key(label))
        if not rows:
            report.missing.append(label)
            continue
        note = next((n for n in (_clean(ws.cell(row=r, column=4).value) for r in rows) if n), "")
        if note:
            report.notes[field_name] = note
        found = [(r, _clean(ws.cell(row=r, column=3).value)) for r in rows]
        filled = [(r, v) for r, v in found if v]
        if filled:
            setattr(ts, field_name, filled[0][1])
            if any(not _same(v, filled[0][1]) for _, v in filled[1:]):
                report.conflicts.append(
                    f"\u201c{label}\u201d appears {len(rows)} times (rows {', '.join(str(r) for r in rows)}) with different "
                    f"values; the first filled one (row {filled[0][0]}) was used.")

    value, unit = parse_capacity(ts.capacity, ts.capacity_unit)
    if value is not None:
        ts.capacity, ts.capacity_unit = format_number(value), unit

    installments = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.column != 2 or not isinstance(cell.value, str):
                continue
            m = INSTALLMENT_PATTERN.search(cell.value)
            if not m:
                continue
            number = m.group(1)
            # The % is written inside this same label cell, e.g. "Installment 1 (10%)", not in its own column -- so it has
            # to be pulled out of cell.value itself, not a separate cell.
            pct_match = PERCENT_PATTERN.search(cell.value)
            installments[number] = Installment(
                number=number,
                percent=pct_match.group(1) if pct_match else "",
                condition=_clean(ws.cell(row=cell.row, column=3).value),
                required_docs=_clean(ws.cell(row=cell.row, column=4).value),
            )

    ts.installments = [installments[k] for k in sorted(installments, key=int)]
    apply_import(ts)
    return ts, report


def parse_xlsx(file) -> TermSheet:
    return parse_xlsx_report(file)[0]
