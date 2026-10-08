"""Step 3: the draft as it stands, in two tabs: "Contract" (the summary of the contract and the numbered preview) and "Checks" (the risks of the
changes and the review of the draft). The Word download is below the tabs, whichever is open.

The Checks run first in the code so that the line at the top of the Contract tab, which says how many points they found, has this run's results; the
tabs are drawn in their own order. The AI checks run by themselves as before, whichever tab is open."""
import streamlit as st

from views import clause_sandbox
from views.draft_steps import clauses, exsum, review, risks
from ai.review import dependency_findings


def checks_status(risk_result, review_result, app_count):
    """The line that tells, on the Contract tab, how many points the Checks tab holds; "" when no check has run and the app found nothing."""
    parts = []
    risk_n = len(risk_result["findings"]) if risk_result and "findings" in risk_result else 0
    review_n = (len(review_result["findings"]) if review_result and "findings" in review_result else 0) + app_count
    if risk_n:
        parts.append(f"{risk_n} risk point(s)")
    if review_n:
        parts.append(f"{review_n} review point(s)")
    if parts:
        return "Checks: " + ", ".join(parts) + ". Open the Checks tab."
    ran = any(r is not None and "error" not in r for r in (risk_result, review_result))
    return "Checks: nothing to review." if ran else ""


def render():
    clause_sandbox.show_vat_notice()
    st.caption("The draft as it stands: the clauses chosen in the previous step, renumbered.")
    contract_tab, checks_tab = st.tabs(["Contract", "Checks"])
    with checks_tab:                      # first, so that the line on the Contract tab has this run's results
        risks.show()
        review.show()
    with contract_tab:
        line = checks_status(st.session_state.get(risks.RESULT_KEY), st.session_state.get(review.RESULT_KEY), len(dependency_findings(review.current_library())))
        if line:
            st.write(line)
        exsum.show()
        clause_sandbox.render_preview(clauses.STATE_KEY, noun="draft", download=False, header=True)
    st.divider()
    clause_sandbox.download_button(clauses.STATE_KEY, noun="draft", header=True)
