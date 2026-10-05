"""The AI term sheet check around the Continue button: run it once per version of the term sheet, keep the result, show it
on the Clauses step. It never blocks and never changes the term sheet."""
import streamlit as st

from ai.interpret import term_sheet_text
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.termcheck import check_term_sheet
from views.draft_steps import flow

RESULT_KEY = "term_sheet_check"


def plain(text):
    return "".join("\\" + ch if ch in "\\`*_{}[]()#+-.!|~$" else ch for ch in str(text))


def run_check(ts):
    """Best effort: a missing key or a failed call is recorded, and the workflow carries on."""
    snapshot = term_sheet_text(ts)
    previous = st.session_state.get(RESULT_KEY)
    if previous and previous["snapshot"] == snapshot and "issues" in previous:
        return                                          # this version of the term sheet was already checked
    client = get_client(st.session_state.get("openai_api_key"))
    if client is None:
        st.session_state[RESULT_KEY] = {"snapshot": snapshot, "note": "The term sheet was not checked: no API key was set."}
        return
    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    with st.spinner("Checking the term sheet..."):
        try:
            result = check_term_sheet(ts, CountingClient(client, calls, "term_sheet_check"), MODEL)
        except AIStepError as e:
            st.session_state[RESULT_KEY] = {"snapshot": snapshot, "note": f"The term sheet check could not run: {e}"}
            return
    st.session_state[RESULT_KEY] = {"snapshot": snapshot, "issues": result.issues}


def show_result(ts):
    result = st.session_state.get(RESULT_KEY)
    if result is None:
        return
    if result["snapshot"] != term_sheet_text(ts):
        st.caption("The term sheet changed after it was checked. Go back and press Continue to check it again.")
    elif "note" in result:
        st.caption(plain(result["note"]))
    elif result["issues"]:
        st.warning(f"The term sheet check found {len(result['issues'])} point(s) to look at. Nothing was changed.")
        for i in result["issues"]:
            st.warning(f"**{plain(i.field)}**: {plain(i.problem)} The term sheet says \u201c{plain(i.evidence)}\u201d.")
        st.button("Back to term sheet", on_click=flow.go_back, key="termcheck_back")
    else:
        st.caption("Term sheet check: nothing to flag.")
