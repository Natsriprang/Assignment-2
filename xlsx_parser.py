"""Parses a term sheet .xlsx matching the admin-defined layout (column B = field label, column C =
value). Installment rows are found by scanning column B for the pattern 'installment N' / 'งวดที่
N', so a term sheet with 5 rows, 7 rows, or any other count parses correctly -- the row count is
never assumed to be fixed."""
import re

import openpyxl

from term_sheet_fields import Installment, TermSheet

INSTALLMENT_PATTERN = re.compile(r"(?:installment|งวดที่)\s*(\d+)", re.IGNORECASE)

# Cell positions matching the admin-defined term sheet layout (B column = label, C column =
# value), paired with the EXACT instructional placeholder text that cell shows when still unfilled
# -- a generic "starts with 'specify'" heuristic missed placeholders like "ตัวเลข" (a number) or
# "วัน เดือน ปี" (day month year), so an exact match against the known placeholder is used instead.
FIELD_CELLS = {
    "project_name": ("C3", "ระบุชื่อโครงการ"),
    "project_location": ("C4", "ที่อยู่สถานที่ตั้งโครงการ"),
    "capacity": ("C6", "ระบุุขนาดกำลังการผลิต"),
    "contract_no": ("C7", "เลขที่สัญญาทั้งหมด 8 หลัก สองหลักแรก เริ่มตั้งแต่ 01 หลักที่สี่ถึงหลักที่หกหกคือเลขย่อตามวันที่ เดือน และปีพ.ศ. (อย่างละ 2 หลัก)"),
    "contract_date": ("C8", "วันที่ทำสัญญา  และต้องสอดคล้องกับเลขที่สัญญาหกหลักท้าย"),
    "owner_name": ("C9", "ชื่อบริษัทผู้ว่าจ้าง"),
    "owner_reg_no": ("C10", "เลขที่นิติบุคคลผู้ว่าจ้าง 13 หลัก"),
    "owner_signatory": ("C11", "ระบุชื่อกรรมการผู้มีอำนาจให้ครบตามอำนาจลงนามของบริษัท"),
    "owner_address": ("C13", "ระบุที่ตั้งสำนักงานห่งใหญ่ผู้ว่าจ้าง"),
    "contractor_name": ("C14", "ชื่อบริษัทผู้รับจ้าง"),
    "contractor_reg_no": ("C15", "เลขที่นิติบุคคลผู้รับจ้าง 13 หลัก"),
    "contractor_signatory": ("C16", "ระบุชื่อกรรมการผู้มีอำนาจให้ครบตามอำนาจลงนามของบริษัท"),
    "contractor_address": ("C18", "ระบุที่ตั้งสำนักงานห่งใหญ่ผู้รับจ้าง"),
    "roof_owner": ("C25", "ระบุชื่อเจ้าของหลังคา (ชื่อบริษัทผู้ว่าจ้าง) หรือบริษัทที่ผู้ว่าจ้างให้ดำเนินการติดตั้ง CA"),
    "contract_price_number": ("C35", "ตัวเลข"),
    "contract_price_words": ("C36", "ตัวอักษร (มีทศนิยม 2 ตำแหน่ง)"),
    "vat_treatment": ("C37", "รวมภาษีมูลค่าเพิ่ม/ไม่รวมภาษีมูลค่าเพิ่ม (กดเลือกได้)"),
    "start_date": ("C60", "วัน เดือน ปี"),
    "completion_date": ("C61", "วัน เดือน ปี"),
    "owner_contact_name": ("C70", "ชื่อบุคคลผู้ติดต่อฝั่งผู้ว่าจ้าง"),
    "owner_contact_position": ("C71", "ตำแหน่ง"),
    "owner_contact_location": ("C72", "สถานที่"),
    "owner_contact_phone": ("C73", "เบอร์โทรศัพท์ หรืออีเมล"),
    "contractor_contact_name": ("C74", "ชื่อบุคคลผู้ติดต่อฝั่งผู้ว่าจ้าง"),
    "contractor_contact_position": ("C75", "ตำแหน่ง"),
    "contractor_contact_location": ("C76", "สถานที่"),
    "contractor_contact_phone": ("C77", "เบอร์โทรศัพท์ หรืออีเมล"),
}


def _clean(value):
    return str(value).strip() if value not in (None, "") else ""


def parse_xlsx(file) -> TermSheet:
    wb = openpyxl.load_workbook(file, data_only=True)
    ws = wb[wb.sheetnames[0]]

    ts = TermSheet()
    for field_name, (cell, placeholder) in FIELD_CELLS.items():
        value = _clean(ws[cell].value)
        is_placeholder = placeholder is not None and value == placeholder
        if value and not is_placeholder:
            setattr(ts, field_name, value)

    installments = {}
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str):
                continue
            m = INSTALLMENT_PATTERN.search(cell.value)
            if not m or cell.column_letter != "B":
                continue
            number = m.group(1)
            condition_cell = ws.cell(row=cell.row, column=3)
            docs_cell = ws.cell(row=cell.row, column=4)
            installments[number] = Installment(
                number=number,
                percent="",
                condition=_clean(condition_cell.value),
                required_docs=_clean(docs_cell.value),
            )

    ts.installments = [installments[k] for k in sorted(installments, key=int)]
    return ts