"""Step 3: the clause set that came out of the interpret step, shown in the clause sandbox. The
selection is seeded from the confirmed interpretation and can be adjusted by hand before the
draft is previewed and downloaded."""
import streamlit as st

from views import clause_sandbox
from views.draft_steps import flow

STATE_KEY = "draft_included"
VERSION_KEY = "draft_included_version"


def render():
    confirmed = flow.confirmed()
    if confirmed is None:
        st.warning("Confirm the interpretation first.")
        st.button("Back to interpret request", on_click=flow.go_back)
        return

    if st.session_state.get(VERSION_KEY) != confirmed["version"]:
        st.session_state[STATE_KEY] = dict(confirmed["included"])
        for key in list(st.session_state.keys()):
            if key.startswith(f"{STATE_KEY}_chk_"):
                del st.session_state[key]
        st.session_state[VERSION_KEY] = confirmed["version"]

    st.caption("The clauses chosen in the previous step. Adjust them if needed, then preview "
               "and download the draft.")
    clause_sandbox.render(STATE_KEY, noun="draft")