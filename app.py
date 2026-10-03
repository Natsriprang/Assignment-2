from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Contract Drafting Assistant", page_icon="\U0001f4c4")

HERE = Path(__file__).resolve().parent

pages = [
    st.Page(HERE / "views" / "term_sheet.py", title="Term Sheet", icon="\U0001f4cb", default=True),
    st.Page(HERE / "views" / "interpret.py", title="Interpret", icon="\U0001f50e"),
    st.Page(HERE / "views" / "sandbox.py", title="Clause Sandbox", icon="\U0001f9f0"),
]
st.navigation(pages).run()