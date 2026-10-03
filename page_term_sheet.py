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

ts = st.session_state.term_sheet

uploaded = st.file_uploader("Upload a filled term sheet (.xlsx)", type=["xlsx"])
if uploaded and st.button("Parse and auto-fill the form"):
    parsed = parse_xlsx(uploaded)
    for f in parsed.__dataclass_fields__:
        if f == "installments":
            if parsed.installments:
                st.session_state.term_sheet.installments = parsed.installments
        elif getattr(parsed, f):
            setattr(st.session_state.term_sheet, f, getattr(parsed, f))

    # Widgets below are given explicit `key`s (needed because labels like "Company name" repeat
    # for Owner/Contractor). Once a keyed widget has rendered, Streamlit keeps using whatever is
    # in st.session_state[key] on every later rerun and ignores a new `value=` argument entirely --
    # so the parsed data above would silently never reach the screen unless those stale keys are
    # cleared first, forcing each widget to re-initialise from the freshly updated TermSheet.
    for key in list(st.session_state.keys()):
        if key.startswith(("own_", "con_", "inst_")):
            del st.session_state[key]

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
    ts.owner_name = st.text_input("Company name", ts.owner_name, key="own_name")
    ts.owner_reg_no = st.text_input("Registration no.", ts.owner_reg_no, key="own_reg")
    ts.owner_signatory = st.text_input("Authorised signatory", ts.owner_signatory, key="own_sig")
    ts.owner_address = st.text_input("Registered address", ts.owner_address, key="own_addr")
with c2:
    st.markdown("**Contractor**")
    ts.contractor_name = st.text_input("Company name", ts.contractor_name, key="con_name")
    ts.contractor_reg_no = st.text_input("Registration no.", ts.contractor_reg_no, key="con_reg")
    ts.contractor_signatory = st.text_input("Authorised signatory", ts.contractor_signatory, key="con_sig")
    ts.contractor_address = st.text_input("Registered address", ts.contractor_address, key="con_addr")

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
st.caption("Row count is not fixed -- add or remove rows as the deal needs.")
for i, inst in enumerate(ts.installments):
    cols = st.columns([1, 1, 4, 3, 1])
    inst.number = cols[0].text_input("No.", inst.number, key=f"inst_no_{i}")
    inst.percent = cols[1].text_input("%", inst.percent, key=f"inst_pct_{i}")
    inst.condition = cols[2].text_input("Condition", inst.condition, key=f"inst_cond_{i}")
    inst.required_docs = cols[3].text_input("Required docs", inst.required_docs, key=f"inst_docs_{i}")
    if cols[4].button("\u2715", key=f"inst_del_{i}"):
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
    ts.owner_contact_name = st.text_input("Name", ts.owner_contact_name, key="own_cn")
    ts.owner_contact_position = st.text_input("Position", ts.owner_contact_position, key="own_cp")
    ts.owner_contact_location = st.text_input("Location", ts.owner_contact_location, key="own_cl")
    ts.owner_contact_phone = st.text_input("Phone / email", ts.owner_contact_phone, key="own_cph")
with c2:
    st.markdown("**Contractor**")
    ts.contractor_contact_name = st.text_input("Name", ts.contractor_contact_name, key="con_cn")
    ts.contractor_contact_position = st.text_input("Position", ts.contractor_contact_position, key="con_cp")
    ts.contractor_contact_location = st.text_input("Location", ts.contractor_contact_location, key="con_cl")
    ts.contractor_contact_phone = st.text_input("Phone / email", ts.contractor_contact_phone, key="con_cph")

st.subheader("Comments")
st.caption("For non-legal users: note anything you want changed from the standard draft (e.g. "
           "\"client wants to drop the construction timeline\") -- this is reviewed before drafting.")
ts.comment = st.text_area("Comment", ts.comment, label_visibility="collapsed")

st.divider()
missing = [f for f in REQUIRED_FIELDS if not getattr(ts, f)]
if missing:
    st.warning(f"Required before continuing: {', '.join(missing)}")
st.button("Continue \u2192", disabled=bool(missing), type="primary")