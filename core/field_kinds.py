"""What kind of thing each free-text field should hold, and what to do with an AI's reading of a value.

The AI only LABELS a value (a person's name, a company, an email ...), without seeing the field it sits in. This table, in
code, decides whether that kind fits the field. So the AI can never produce a verdict, only a label, and the same label always
leads to the same decision. "other" is always acceptable: an AI that is unsure never causes a warning."""

KINDS = ["person_name", "company_name", "address", "email", "phone", "registration_number", "date", "number", "other"]

KIND_PHRASE = {
    "person_name": "a person's name",
    "company_name": "a company or organisation name",
    "address": "an address or a place",
    "email": "an email address",
    "phone": "a phone number",
    "registration_number": "a registration number",
    "date": "a date",
    "number": "a number",
    "other": "something else",
}


def _ok(*kinds):
    return frozenset(kinds) | {"other"}


# field -> the kinds that fit it. A generous list on purpose: a kind that is merely unusual for the field is not a mistake.
ACCEPTABLE = {
    "project_location": _ok("address", "company_name"),
    "roof_owner": _ok("person_name", "company_name", "address"),
    "owner_name": _ok("company_name"),
    "owner_signatory": _ok("person_name"),
    "owner_address": _ok("address", "company_name"),
    "owner_reg_no": _ok("registration_number", "number", "phone"),
    "contractor_name": _ok("company_name"),
    "contractor_signatory": _ok("person_name"),
    "contractor_address": _ok("address", "company_name"),
    "contractor_reg_no": _ok("registration_number", "number", "phone"),
    "owner_contact_name": _ok("person_name", "company_name"),
    "owner_contact_location": _ok("address", "company_name"),
    "owner_contact_phone": _ok("phone", "number", "registration_number"),
    "owner_contact_email": _ok("email"),
    "contractor_contact_name": _ok("person_name", "company_name"),
    "contractor_contact_location": _ok("address", "company_name"),
    "contractor_contact_phone": _ok("phone", "number", "registration_number"),
    "contractor_contact_email": _ok("email"),
}


def kind_items(ts):
    """[(id, field, value)] for every field above that has a value, in a fixed order. The value is on one line. The id is all the
    AI sees besides the value: it is not told which field the value is in."""
    items = []
    for field in ACCEPTABLE:
        raw = str(getattr(ts, field, "") or "")
        value = " / ".join(line.strip() for line in raw.replace("\r", "\n").split("\n") if line.strip())
        if value:
            items.append((f"f{len(items) + 1}", field, value))
    return items


def misfits(items, labels):
    """[(field, value, kind)] for each value whose label does not fit its field. `labels` is {id: kind}."""
    return [(field, value, labels[i]) for i, field, value in items if i in labels and labels[i] not in ACCEPTABLE[field]]
