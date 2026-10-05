"""Term sheet ingestion: upload a filled .xlsx to auto-fill the form, or fill it by hand. Every
field stays editable after auto-fill. The installment table has no fixed row count -- rows come
from whatever the term sheet actually contains, with add/remove controls for manual adjustment.
The Check / Recheck button runs the exact checks and the AI check and shows what they found; Continue only moves on, and is
disabled until every required field is filled and the current term sheet has been checked."""
import streamlit as st

from core.capacity import UNITS, parse_capacity
from core.clause_params import PARAMS
from core.deadline import deadline_choice, deadline_warning, is_days
from core.field_titles import title
from core.term_sheet_fields import TermSheet, Installment, ensure_fields, missing_required, signing_place
from core.vat import vat_choice, vat_warning
from core.xlsx_parser import FIELD_LABELS, parse_xlsx_report
from views.draft_steps import flow, term_check


PLACE_LABELS = {"": "\u2014 not chosen \u2014", "owner": "Owner's registered address",
               "contractor": "Contractor's registered address", "other": "Other place"}
IMPORTED_FIELDS = set(FIELD_LABELS) | {"capacity_unit"}
IMPORT_REPORT_KEY = "term_sheet_import_report"
DEADLINE_FIELDS = ("deadline_mode", "completion_days")       # read together from the start/completion cells
DEADLINE_LABELS = {"": "\u2014 not chosen \u2014", "calendar": "Calendar dates", "period": "A period from signing"}
VAT_LABELS = {"": "\u2014 not chosen \u2014", "inclusive": "Inclusive of VAT", "exclusive": "Exclusive of VAT"}


def can_continue():
    """The next arrow's condition, the same as Continue's: the required fields are filled and this term sheet has been checked."""
    ts = st.session_state.get("term_sheet")
    return ts is not None and not missing_required(ts) and term_check.is_checked(ensure_fields(ts))


def show_import_report():
    """What the last Excel import could not read, kept on the page until the next import."""
    rep = st.session_state.get(IMPORT_REPORT_KEY)
    if not rep:
        return
    if rep["nothing"]:
        st.error(f"None of the expected labels were found in column B of the first sheet of {rep['name']}. "
                 "Is it the term sheet template? Nothing was filled in.")
        return
    if rep["missing"]:
        st.warning(f"Not found in {rep['name']} (the label is missing or was renamed), so these were left as they are: "
                   + ", ".join(rep["missing"]) + ".")
    for note in rep["conflicts"]:
        st.warning(note)


def render():
    if "term_sheet" not in st.session_state:
        st.session_state.term_sheet = TermSheet()
        st.session_state.term_sheet.installments = [Installment(number=str(i)) for i in range(1, 6)]
    if "form_version" not in st.session_state:
        st.session_state.form_version = 0

    ts = ensure_fields(st.session_state.term_sheet)       # an object saved by an older version gets the newer fields
    v = st.session_state.form_version  # bump this whenever ts is updated programmatically (parsing) so
    # every keyed widget below gets a brand-new key and re-initialises from ts, instead of Streamlit
    # reusing whatever is already stored under the old key and ignoring the new `value=` argument.

    uploaded = st.file_uploader("Upload a filled term sheet (.xlsx)", type=["xlsx"])
    show_import_report()
    if uploaded and st.button("Auto-fill the form"):
        parsed, report = parse_xlsx_report(uploaded)
        st.session_state[IMPORT_REPORT_KEY] = {"name": uploaded.name, "missing": report.missing, "conflicts": report.conflicts,
                                               "nothing": report.nothing_found}
        st.session_state.pop(term_check.RESULT_KEY, None)          # a fresh import has not been checked
        if not report.nothing_found:
            st.session_state[term_check.NOTES_KEY] = report.notes
        for f in parsed.__dataclass_fields__:
            if f != "installments" and f not in IMPORTED_FIELDS or f in DEADLINE_FIELDS:
                continue                       # fields the Excel does not hold keep what the user has
            if f == "installments":
                if parsed.installments:
                    st.session_state.term_sheet.installments = parsed.installments
            elif getattr(parsed, f):
                setattr(st.session_state.term_sheet, f, getattr(parsed, f))

        if parsed.start_date or parsed.completion_date:                 # the mode and the days go with the two cells they come from
            for f in DEADLINE_FIELDS:
                setattr(st.session_state.term_sheet, f, getattr(parsed, f))

        st.session_state.form_version += 1  # see the note on `v` above
        if not report.nothing_found:
            st.success(f"Auto-filled from {uploaded.name}. Every field below is still editable.")
        st.rerun()

    st.caption("All fields are editable, whether auto-filled or entered by hand.")

    st.subheader("Project")
    c1, c2 = st.columns(2)
    ts.project_name = c1.text_input("Project name", ts.project_name)
    ts.project_location = c2.text_input("Project location", ts.project_location)
    c1, c2 = st.columns(2)
    with c1:
        cap_value, cap_unit = st.columns([3, 1])
        ts.capacity = cap_value.text_input("Capacity", ts.capacity)
        _, shown_unit = parse_capacity(ts.capacity, getattr(ts, "capacity_unit", "kWp"))
        ts.capacity_unit = cap_unit.selectbox("Unit", UNITS, index=UNITS.index(shown_unit), key=f"cap_unit_{v}")
    ts.roof_owner = c2.text_input("Roof owner", ts.roof_owner)
    c1, c2 = st.columns(2)
    ts.contract_no = c1.text_input("Contract no.", ts.contract_no)
    ts.contract_date = c2.text_input("Contract date", ts.contract_date)
    c1, c2 = st.columns(2)
    place_choice = ts.signing_place_choice if ts.signing_place_choice in PLACE_LABELS else ""
    ts.signing_place_choice = c1.selectbox("Place of signing", list(PLACE_LABELS), index=list(PLACE_LABELS).index(place_choice),
                                           format_func=PLACE_LABELS.get, key=f"place_choice_{v}")
    ts.signing_place_other = c2.text_input("Other place", ts.signing_place_other, disabled=ts.signing_place_choice != "other",
                                           key=f"place_other_{v}")
    if ts.signing_place_choice in ("owner", "contractor"):
        st.caption("Will be written as: " + (signing_place(ts) or "(that address is empty)"))

    st.subheader("Parties")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Owner**")
        ts.owner_name = st.text_input("Company name", ts.owner_name, key=f"own_name_{v}")
        ts.owner_country = st.text_input("Country of registration", ts.owner_country, key=f"own_country_{v}")
        ts.owner_reg_no = st.text_input("Registration no.", ts.owner_reg_no, key=f"own_reg_{v}")
        ts.owner_signatory = st.text_input("Authorised signatory", ts.owner_signatory, key=f"own_sig_{v}")
        ts.owner_address = st.text_input("Registered address", ts.owner_address, key=f"own_addr_{v}")
    with c2:
        st.markdown("**Contractor**")
        ts.contractor_name = st.text_input("Company name", ts.contractor_name, key=f"con_name_{v}")
        ts.contractor_country = st.text_input("Country of registration", ts.contractor_country, key=f"con_country_{v}")
        ts.contractor_reg_no = st.text_input("Registration no.", ts.contractor_reg_no, key=f"con_reg_{v}")
        ts.contractor_signatory = st.text_input("Authorised signatory", ts.contractor_signatory, key=f"con_sig_{v}")
        ts.contractor_address = st.text_input("Registered address", ts.contractor_address, key=f"con_addr_{v}")

    st.subheader("Contract price")
    c1, c2, c3 = st.columns(3)
    ts.contract_price_number = c1.text_input("Price (THB, number)", ts.contract_price_number)
    ts.contract_price_words = c2.text_input("Price (in words)", ts.contract_price_words)
    current_vat = vat_choice(ts)
    chosen_vat = c3.selectbox("VAT", list(VAT_LABELS), index=list(VAT_LABELS).index(current_vat), format_func=VAT_LABELS.get)
    if chosen_vat != current_vat:                  # only a real change by the user overwrites what the term sheet said
        ts.vat_treatment = chosen_vat
    if vat_warning(ts):
        st.error("\u2757 " + vat_warning(ts))
    days = ts.payment_days
    shown_days = int(days) if str(days).isdigit() and 1 <= int(days) <= 365 else 30
    ts.payment_days = str(int(st.number_input("Payment due within (working days)", min_value=1, max_value=365, step=1,
                                              value=shown_days, key=f"pay_days_{v}")))

    st.subheader("Payment installments")
    st.caption("Add or remove installments.")
    for i, inst in enumerate(ts.installments):
        cols = st.columns([1, 1, 4, 3, 1])
        inst.number = cols[0].text_input("No.", inst.number, key=f"inst_no_{v}_{i}")
        inst.percent = cols[1].text_input("%", inst.percent, key=f"inst_pct_{v}_{i}")
        inst.condition = cols[2].text_area("Condition", inst.condition, key=f"inst_cond_{v}_{i}", height=110)
        inst.required_docs = cols[3].text_area("Required docs", inst.required_docs, key=f"inst_docs_{v}_{i}", height=110)
        if cols[4].button("\u2715", key=f"inst_del_{v}_{i}"):
            ts.installments.pop(i)
            st.rerun()

    if st.button("+ Add installment"):
        ts.installments.append(Installment(number=str(len(ts.installments) + 1)))
        st.rerun()

    st.subheader("Completion deadline")
    mode = deadline_choice(ts)
    ts.deadline_mode = st.selectbox("The Works start and finish by", list(DEADLINE_LABELS), index=list(DEADLINE_LABELS).index(mode),
                                    format_func=DEADLINE_LABELS.get, key=f"deadline_mode_{v}")
    c1, c2 = st.columns(2)
    if ts.deadline_mode == "calendar":
        ts.start_date = c1.text_input("Start date", ts.start_date)
        ts.completion_date = c2.text_input("Completion date", ts.completion_date)
    elif ts.deadline_mode == "period":
        ts.completion_days = c1.text_input("Complete within (days after signing)", ts.completion_days, key=f"completion_days_{v}")
        if ts.completion_days.strip() and not is_days(ts.completion_days):
            st.error("Completion: enter a whole number of days from 1 to 999.")
    if deadline_warning(ts):
        st.error("\u2757 " + deadline_warning(ts))

    st.subheader("Contract documents")
    ts.attachment_no = st.text_input("Attachment no. that yields to the Agreement", ts.attachment_no, key=f"attach_{v}",
                                     help="The attachments clause says that if the Agreement and this attachment differ, "
                                          "the Agreement prevails.")

    st.subheader("Limits")
    st.caption("Caps written into the contract. Tick \"No cap\" to take a cap out of the wording.")
    if not hasattr(ts, "limits"):
        ts.limits = {}
    for p in PARAMS.values():
        current = ts.limits.get(p.key, p.default)
        c1, c2 = st.columns([3, 2])
        no_cap = c2.checkbox("No cap", value=current is None, key=f"limit_none_{p.key}_{v}") if p.allow_none else False
        percent = c1.number_input(p.label, min_value=0.01, max_value=100.0, step=0.5, disabled=no_cap,
                                  value=float(current if current is not None else p.default),
                                  key=f"limit_pct_{p.key}_{v}")
        ts.limits[p.key] = None if no_cap else percent

    st.subheader("Notice contacts")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Owner**")
        ts.owner_contact_name = st.text_input("Name", ts.owner_contact_name, key=f"own_cn_{v}")
        ts.owner_contact_position = st.text_input("Position", ts.owner_contact_position, key=f"own_cp_{v}")
        ts.owner_contact_location = st.text_input("Location", ts.owner_contact_location, key=f"own_cl_{v}")
        ts.owner_contact_phone = st.text_input("Phone", ts.owner_contact_phone, key=f"own_cph_{v}")
        ts.owner_contact_email = st.text_input("Email", ts.owner_contact_email, key=f"own_cem_{v}")
    with c2:
        st.markdown("**Contractor**")
        ts.contractor_contact_name = st.text_input("Name", ts.contractor_contact_name, key=f"con_cn_{v}")
        ts.contractor_contact_position = st.text_input("Position", ts.contractor_contact_position, key=f"con_cp_{v}")
        ts.contractor_contact_location = st.text_input("Location", ts.contractor_contact_location, key=f"con_cl_{v}")
        ts.contractor_contact_phone = st.text_input("Phone", ts.contractor_contact_phone, key=f"con_cph_{v}")
        ts.contractor_contact_email = st.text_input("Email", ts.contractor_contact_email, key=f"con_cem_{v}")

    st.divider()
    term_check.show_result(ts)
    missing = missing_required(ts)
    if missing:
        st.warning(f"Required before continuing: {', '.join(title(f) for f in missing)}")
    if st.button("Recheck" if term_check.has_result() else "Check term sheet", key="term_check_button"):
        term_check.run_check(ts)
        st.rerun()
    if st.button("Continue \u2192", disabled=bool(missing) or not term_check.is_checked(ts), type="primary", key="term_continue"):
        flow.go_next()
        st.rerun()
