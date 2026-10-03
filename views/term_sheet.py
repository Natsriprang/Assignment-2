"""Term sheet ingestion: upload a filled .xlsx to auto-fill the form, or fill it by hand. Every
field stays editable after auto-fill. The installment table has no fixed row count -- rows come
from whatever the term sheet actually contains, with add/remove controls for manual adjustment.
The Continue button is disabled until every required field is filled (validation gate, no AI)."""
import streamlit as st

from term_sheet_fields import TermSheet, Installment, REQUIRED_FIELDS
from xlsx_parser import parse_xlsx

st.title("\U0001f4cb Term Sheet")

if "term_sheet" not in st.session_state:
    st.session_state.term_sheet = TermSheet()
    st.session_state.term_sheet.installments = [Installment(number=str(i)) for i in range(1, 6)]
if "form_version" not in st.session_state:
    st.session_state.form_version = 0

ts = st.session_state.term_sheet
v = st.session_state.form_version  # bump this whenever ts is updated programmatically (parsing) so
# every keyed widget below gets a brand-new key and re-initialises from ts, instead of Streamlit
# reusing whatever is already stored under the old key and ignoring the new `value=` argument.

uploaded = st.file_uploader("Upload a filled term sheet (.xlsx)", type=["xlsx"])
if uploaded and st.button("Auto-fill the form"):
    parsed = parse_xlsx(uploaded)
    for f in parsed.__dataclass_fields__:
        if f == "installments":
            if parsed.installments:
                st.session_state.term_sheet.installments = parsed.installments
        elif getattr(parsed, f):
            setattr(st.session_state.term_sheet, f, getattr(parsed, f))

    st.session_state.form_version += 1  # see the note on `v` above
    st.success(f"Auto-filled from {uploaded.name}. Every field below is still editable.")
    st.rerun()

st.caption("All fields are editable, whether auto-filled or entered by hand.")

st.subheader("Project")
c1, c2 = st.columns(2)
ts.project_name = c1.text_input("Project name", ts.project_name)
ts.project_location = c2.text_input("Project location", ts.project_location)
c1, c2 = st.columns(2)
ts.capacity = c1.text_input("Capacity (kWp / MW)", ts.capacity)
ts.roof_owner = c2.text_input("Roof owner", ts.roof_owner)
c1, c2 = st.columns(2)
ts.contract_no = c1.text_input("Contract no.", ts.contract_no)
ts.contract_date = c2.text_input("Contract date", ts.contract_date)

st.subheader("Parties")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Owner**")
    ts.owner_name = st.text_input("Company name", ts.owner_name, key=f"own_name_{v}")
    ts.owner_reg_no = st.text_input("Registration no.", ts.owner_reg_no, key=f"own_reg_{v}")
    ts.owner_signatory = st.text_input("Authorised signatory", ts.owner_signatory, key=f"own_sig_{v}")
    ts.owner_address = st.text_input("Registered address", ts.owner_address, key=f"own_addr_{v}")
with c2:
    st.markdown("**Contractor**")
    ts.contractor_name = st.text_input("Company name", ts.contractor_name, key=f"con_name_{v}")
    ts.contractor_reg_no = st.text_input("Registration no.", ts.contractor_reg_no, key=f"con_reg_{v}")
    ts.contractor_signatory = st.text_input("Authorised signatory", ts.contractor_signatory, key=f"con_sig_{v}")
    ts.contractor_address = st.text_input("Registered address", ts.contractor_address, key=f"con_addr_{v}")

st.subheader("Contract price")
c1, c2, c3 = st.columns(3)
ts.contract_price_number = c1.text_input("Price (THB, number)", ts.contract_price_number)
ts.contract_price_words = c2.text_input("Price (in words)", ts.contract_price_words)
ts.vat_treatment = c3.selectbox(
    "VAT",
    ["inclusive", "exclusive"],
    index=0 if ts.vat_treatment != "exclusive" else 1,
)

st.subheader("Payment installments")
st.caption("Add or remove installments.")
for i, inst in enumerate(ts.installments):
    cols = st.columns([1, 1, 4, 3, 1])
    inst.number = cols[0].text_input("No.", inst.number, key=f"inst_no_{v}_{i}")
    inst.percent = cols[1].text_input("%", inst.percent, key=f"inst_pct_{v}_{i}")
    inst.condition = cols[2].text_input("Condition", inst.condition, key=f"inst_cond_{v}_{i}")
    inst.required_docs = cols[3].text_input("Required docs", inst.required_docs, key=f"inst_docs_{v}_{i}")
    if cols[4].button("\u2715", key=f"inst_del_{v}_{i}"):
        ts.installments.pop(i)
        st.rerun()

if st.button("+ Add installment"):
    ts.installments.append(Installment(number=str(len(ts.installments) + 1)))
    st.rerun()

st.subheader("Completion deadline")
c1, c2 = st.columns(2)
ts.start_date = c1.text_input("Start date", ts.start_date)
ts.completion_date = c2.text_input("Completion date", ts.completion_date)

st.subheader("Notice contacts")
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Owner**")
    ts.owner_contact_name = st.text_input("Name", ts.owner_contact_name, key=f"own_cn_{v}")
    ts.owner_contact_position = st.text_input("Position", ts.owner_contact_position, key=f"own_cp_{v}")
    ts.owner_contact_location = st.text_input("Location", ts.owner_contact_location, key=f"own_cl_{v}")
    ts.owner_contact_phone = st.text_input("Phone / email", ts.owner_contact_phone, key=f"own_cph_{v}")
with c2:
    st.markdown("**Contractor**")
    ts.contractor_contact_name = st.text_input("Name", ts.contractor_contact_name, key=f"con_cn_{v}")
    ts.contractor_contact_position = st.text_input("Position", ts.contractor_contact_position, key=f"con_cp_{v}")
    ts.contractor_contact_location = st.text_input("Location", ts.contractor_contact_location, key=f"con_cl_{v}")
    ts.contractor_contact_phone = st.text_input("Phone / email", ts.contractor_contact_phone, key=f"con_cph_{v}")

st.divider()
missing = [f for f in REQUIRED_FIELDS if not getattr(ts, f)]
if missing:
    st.warning(f"Required before continuing: {', '.join(missing)}")
if st.button("Continue \u2192", disabled=bool(missing), type="primary"):
    st.switch_page("page_interpret.py")