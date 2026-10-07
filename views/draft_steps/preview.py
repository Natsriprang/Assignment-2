"""Step 3: numbered preview of the draft as it stands, with the Word download."""
import streamlit as st

from views import clause_sandbox
from views.draft_steps import clauses, readiness, review, risks


def render():
    clause_sandbox.show_vat_notice()
    st.caption("The draft as it stands: the clauses chosen in the previous step, renumbered.")
    risks.show()
    review.show()
    readiness.show()
    clause_sandbox.render_preview(clauses.STATE_KEY, noun="draft", header=True)
