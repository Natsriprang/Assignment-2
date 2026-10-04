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

    owner_name: str = ""
    owner_reg_no: str = ""
    owner_signatory: str = ""
    owner_address: str = ""

    contractor_name: str = ""
    contractor_reg_no: str = ""
    contractor_signatory: str = ""
    contractor_address: str = ""

    roof_owner: str = ""

    contract_price_number: str = ""
    contract_price_words: str = ""
    vat_treatment: str = ""
    installments: list = field(default_factory=list)  # list[Installment] -- variable length

    start_date: str = ""
    completion_date: str = ""

    owner_contact_name: str = ""
    owner_contact_position: str = ""
    owner_contact_location: str = ""
    owner_contact_phone: str = ""

    contractor_contact_name: str = ""
    contractor_contact_position: str = ""
    contractor_contact_location: str = ""
    contractor_contact_phone: str = ""

    limits: dict = field(default_factory=dict)   # parameter key -> percent, or None for "no cap"



REQUIRED_FIELDS = [
    "project_name", "project_location", "capacity", "owner_name", "contractor_name",
    "contract_price_number", "start_date", "completion_date",
]