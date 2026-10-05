"""The canonical term-sheet field schema -- what Phase 1 needs to fill the clause placeholders."""
from dataclasses import dataclass, field


@dataclass
class Installment:
    number: str = ""
    percent: str = ""
    condition: str = ""
    required_docs: str = ""


@dataclass
class TermSheet:
    project_name: str = ""
    project_location: str = ""
    capacity: str = ""
    capacity_unit: str = "kWp"      # "kWp" or "MW"
    contract_no: str = ""
    contract_date: str = ""
    signing_place_choice: str = ""     # "owner" | "contractor" | "other" | "" -- the place is read from the address chosen
    signing_place_other: str = ""

    owner_name: str = ""
    owner_country: str = ""
    owner_reg_no: str = ""
    owner_signatory: str = ""
    owner_address: str = ""

    contractor_name: str = ""
    contractor_country: str = "Thailand"
    contractor_reg_no: str = ""
    contractor_signatory: str = ""
    contractor_address: str = ""

    roof_owner: str = ""

    contract_price_number: str = ""
    contract_price_words: str = ""
    vat_treatment: str = ""
    payment_days: str = "30"           # working days the Owner has to pay an installment
    installments: list = field(default_factory=list)  # list[Installment] -- variable length

    attachment_no: str = ""            # the attachment that yields to the Agreement if they differ

    deadline_mode: str = ""            # "calendar" | "period" | "" -- which pair below the contract uses
    start_date: str = ""               # calendar dates ...
    completion_date: str = ""
    completion_days: str = ""          # ... or days after signing (the Works are then only given a completion)

    owner_contact_name: str = ""
    owner_contact_position: str = ""
    owner_contact_location: str = ""
    owner_contact_phone: str = ""
    owner_contact_email: str = ""

    contractor_contact_name: str = ""
    contractor_contact_position: str = ""
    contractor_contact_location: str = ""
    contractor_contact_phone: str = ""
    contractor_contact_email: str = ""

    limits: dict = field(default_factory=dict)   # parameter key -> percent, or None for "no cap"



REQUIRED_FIELDS = [
    "project_name", "project_location", "capacity", "owner_name", "contractor_name",
    "contract_price_number",
]

NEW_FIELD_DEFAULTS = {"owner_country": "", "contractor_country": "Thailand", "signing_place_choice": "",
                      "signing_place_other": "", "payment_days": "30", "attachment_no": "",
                      "deadline_mode": "", "completion_days": "", "owner_contact_email": "", "contractor_contact_email": ""}


def ensure_fields(term_sheet):
    """Gives a term sheet object saved by an older version of the app the fields added since."""
    for name, default in NEW_FIELD_DEFAULTS.items():
        if not hasattr(term_sheet, name):
            setattr(term_sheet, name, default)
    return term_sheet


def signing_place(term_sheet):
    """The place of signing as text: the address of the party chosen, or the place typed. Empty if none."""
    choice = getattr(term_sheet, "signing_place_choice", "")
    source = {"owner": "owner_address", "contractor": "contractor_address", "other": "signing_place_other"}.get(choice)
    return (getattr(term_sheet, source, "") or "").strip() if source else ""


def missing_required(term_sheet):
    """Names of the fields still needed before the draft can start. The deadline needs a mode and the pair it names."""
    from core.deadline import deadline_choice, is_days
    if term_sheet is None:
        return REQUIRED_FIELDS + ["deadline_mode"]
    missing = [f for f in REQUIRED_FIELDS if not getattr(term_sheet, f, "")]
    mode = deadline_choice(term_sheet)
    if not mode:
        return missing + ["deadline_mode"]
    if mode == "calendar":
        return missing + [f for f in ("start_date", "completion_date") if not (getattr(term_sheet, f, "") or "").strip()]
    return missing + ([] if is_days(getattr(term_sheet, "completion_days", "")) else ["completion_days"])
