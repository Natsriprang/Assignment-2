"""How each term sheet field is named on the Term sheet page. Every warning uses these names, never the code's field names.
Where the form's own label would be unclear on its own (the same label appears for the Owner and the Contractor, or the label
lacks its section) the title is "Section \u2013 label". The part after the dash is exactly the label of the input on the page."""

DASH = " \u2013 "


def _party(prefix, section):
    return {
        f"{prefix}_name": f"{section}{DASH}Company name",
        f"{prefix}_country": f"{section}{DASH}Country of registration",
        f"{prefix}_reg_no": f"{section}{DASH}Registration no.",
        f"{prefix}_signatory": f"{section}{DASH}Authorised signatory",
        f"{prefix}_address": f"{section}{DASH}Registered address",
    }


def _contact(prefix, section):
    return {f"{prefix}_contact_{k}": f"{section}{DASH}{label}"
            for k, label in (("name", "Name"), ("position", "Position"), ("location", "Location"), ("phone", "Phone"), ("email", "Email"))}


FIELD_TITLES = {
    "project_name": "Project name",
    "project_location": "Project location",
    "capacity": "Capacity",
    "capacity_unit": "Unit",
    "roof_owner": "Roof owner",
    "contract_no": "Contract no.",
    "contract_date": "Contract date",
    "signing_place_choice": "Place of signing",
    "signing_place_other": "Other place",
    **_party("owner", "Owner"),
    **_party("contractor", "Contractor"),
    "contract_price_number": f"Contract price{DASH}Price (THB, number)",
    "contract_price_words": f"Contract price{DASH}Price (in words)",
    "vat_treatment": "VAT",
    "payment_days": "Payment due within (working days)",
    "installments": "Payment installments",
    "deadline_mode": "The Works start and finish by",
    "start_date": "Start date",
    "completion_date": "Completion date",
    "completion_days": "Complete within (days after signing)",
    "attachment_no": "Attachment no. that yields to the Agreement",
    "additional_conditions": "Additional conditions",
    "limits": "Limits",
    **_contact("owner", "Owner contact"),
    **_contact("contractor", "Contractor contact"),
}

# Fields a blank in which is worth a warning: the ones the contract or the notice and signature blocks use, and have no
# default and no notice of their own. (The roof owner is optional; VAT and the deadline have their own red notices.)
BLANK_CHECKED = [
    "project_name", "project_location", "capacity", "contract_no", "contract_date", "signing_place_choice",
    "owner_name", "owner_country", "owner_reg_no", "owner_signatory", "owner_address",
    "contractor_name", "contractor_country", "contractor_reg_no", "contractor_signatory", "contractor_address",
    "contract_price_number", "contract_price_words", "attachment_no",
    "owner_contact_name", "owner_contact_position", "owner_contact_location", "owner_contact_phone", "owner_contact_email",
    "contractor_contact_name", "contractor_contact_position", "contractor_contact_location", "contractor_contact_phone",
    "contractor_contact_email",
]


def title(field_name):
    """The page's name for a field; a field with no entry gets its code name made readable."""
    return FIELD_TITLES.get(field_name) or field_name.replace("_", " ").capitalize()


def label_on_page(field_name):
    """The label of the input itself (the title without its section)."""
    return title(field_name).split(DASH)[-1]
