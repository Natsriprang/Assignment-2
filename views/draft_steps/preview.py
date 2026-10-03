"""Step 3: numbered preview of the draft as it stands, with the Word download."""
import streamlit as st

from views import clause_sandbox
from views.draft_steps import clauses


def render():
    st.caption("The draft as it stands: the clauses chosen in the previous step, renumbered.")
    clause_sandbox.render_preview(clauses.STATE_KEY, noun="draft")
