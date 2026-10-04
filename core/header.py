"""The contract header (title, parties, recitals), filled from the term sheet. Wording is the template's own.
A value the term sheet does not have is written as [*] so it stays visible. Pure code, no AI."""
from core.capacity import capacity_in

PLACEHOLDER = "[*]"
TITLE = "Construction and Installation Service Agreement"

# (style, text). Styles: title, centre, para, bullet, indent.
Line = tuple


def _v(value):
    value = (value or "").strip()
    return value if value else PLACEHOLDER


def build_header(ts):
    """The header as a list of (style, text) lines. `ts` may be None or an older term sheet object."""
    g = lambda name: _v(getattr(ts, name, ""))
    capacity_mw = capacity_in(ts, "MW") or PLACEHOLDER
    return [
        ("title", TITLE),
        ("centre", "for the Photovoltaic Solar Power Rooftop Facility"),
        ("centre", f"{g('project_name')} with {capacity_mw} MW"),
        ("centre", f"Contract no.: {g('contract_no')}"),
        ("para", "This construction and installation service agreement (the \u201cAgreement\u201d) is made on "
                 f"{g('contract_date')} (the \u201cdate of this Agreement\u201d) at {PLACEHOLDER}."),
        ("para", "Between:"),
        ("bullet", f"{g('owner_name')}, a company incorporated under the laws of {PLACEHOLDER} having the company "
                   f"registration number {g('owner_reg_no')}, whose registered head office is at {g('owner_address')}, "
                   "hereinafter referred to as the \u201cOwner\u201d and;"),
        ("bullet", f"{g('contractor_name')}, a company incorporated under the laws of Thailand having the company "
                   f"registration number {g('contractor_reg_no')}, whose registered head office is at "
                   f"{g('contractor_address')}, hereinafter referred to as the \u201cContractor\u201d"),
        ("para", "The Owner and the Contractor are hereinafter referred to as the \u201cParties\u201d"),
        ("para", "WHEREAS"),
        ("indent", "The Owner wishes to install the photovoltaic solar power system on the rooftop (the "
                   f"\u201cSystem\u201d) located at {g('project_location')} (the \u201cProject\u201d). The Contractor is an "
                   "expert in providing services on design, construct and installation of the System."),
        ("indent", "The Parties wish to enter into the subcontracting services on construction and installation "
                   "agreement for the photovoltaic solar power rooftop in accordance with the terms and conditions "
                   "set out in this Agreement."),
    ]
