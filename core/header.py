"""The contract header (title, parties, recitals), filled from the term sheet. Wording is the template's own.
A value the term sheet does not have is written as [*] so it stays visible. Pure code, no AI."""
from core.capacity import capacity_parts
from core.term_sheet_fields import signing_place

PLACEHOLDER = "[*]"
TITLE = "Construction and Installation Service Agreement"

# (style, text). Styles: title, centre, right, para, bullet, numbered (the recitals; the renderers put 1., 2. ... in front).
Line = tuple


def _v(value):
    value = (value or "").strip()
    return value if value else PLACEHOLDER


def build_header(ts):
    """The header as a list of (style, text) lines. `ts` may be None or an older term sheet object."""
    g = lambda name: _v(getattr(ts, name, ""))
    capacity, unit = capacity_parts(ts)
    owner_country = _v(getattr(ts, "owner_country", ""))
    contractor_country = _v(getattr(ts, "contractor_country", "Thailand"))      # the template's own wording for older term sheets
    place = signing_place(ts) or PLACEHOLDER
    return [
        ("title", TITLE),
        ("centre", "for the Photovoltaic Solar Power Rooftop Facility"),
        ("centre", f"{g('project_name')} with {capacity or PLACEHOLDER} {unit}"),
        ("right", f"Contract no.: {g('contract_no')}"),
        ("para", "This construction and installation service agreement (the \u201cAgreement\u201d) is made on "
                 f"{g('contract_date')} (the \u201cdate of this Agreement\u201d) at {place}."),
        ("para", "Between:"),
        ("bullet", f"{g('owner_name')}, a company incorporated under the laws of {owner_country} having the company "
                   f"registration number {g('owner_reg_no')}, whose registered head office is at {g('owner_address')}, "
                   "hereinafter referred to as the \u201cOwner\u201d and;"),
        ("bullet", f"{g('contractor_name')}, a company incorporated under the laws of {contractor_country} having the company "
                   f"registration number {g('contractor_reg_no')}, whose registered head office is at "
                   f"{g('contractor_address')}, hereinafter referred to as the \u201cContractor\u201d"),
        ("para", "The Owner and the Contractor are hereinafter referred to as the \u201cParties\u201d"),
        ("para", "WHEREAS"),
        ("numbered", "The Owner wishes to install the photovoltaic solar power system on the rooftop (the "
                   f"\u201cSystem\u201d) located at {g('project_location')} (the \u201cProject\u201d). The Contractor is an "
                   "expert in providing services on design, construct and installation of the System."),
        ("numbered", "The Parties wish to enter into the subcontracting services on construction and installation "
                   "agreement for the photovoltaic solar power rooftop in accordance with the terms and conditions "
                   "set out in this Agreement."),
    ]
