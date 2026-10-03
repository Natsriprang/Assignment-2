from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Contract Drafting Assistant", page_icon="\U0001f4c4")

HERE = Path(__file__).resolve().parent

pages = [
    st.Page(HERE / "page_sandbox.py", title="Clause Sandbox", icon="\U0001f9f0", default=True),
]
st.navigation(pages).run()