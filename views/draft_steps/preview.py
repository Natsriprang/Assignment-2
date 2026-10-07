"""Step 3: numbered preview of the draft as it stands, with the Word download."""
import streamlit as st

from views import clause_sandbox
from views.draft_steps import clauses, exsum, review, risks


def render():
    clause_sandbox.show_vat_notice()
    st.caption("The draft as it stands: the clauses chosen in the previous step, renumbered.")
    exsum.show()
    risks.show()
    review.show()
    clause_sandbox.render_preview(clauses.STATE_KEY, noun="draft", header=True)
