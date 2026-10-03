"""Entry point. Run: streamlit run app.py"""
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Contract Drafting Assistant", page_icon="\U0001f4c4")

HERE = Path(__file__).resolve().parent

draft = st.Page(HERE / "views" / "draft_contract.py", title="Draft contract",
                icon="\U0001f4dd", default=True)

st.navigation([draft]).run()
