"""The AI term sheet check around the Continue button: run it once per version of the term sheet, keep the result, show it on
the Term sheet page itself. It never blocks and never changes the term sheet."""
import streamlit as st

from ai.interpret import term_sheet_text
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.termcheck import check_term_sheet
from core.field_rules import template_notes
from core.field_titles import title
from views.draft_steps import flow

RESULT_KEY = "term_sheet_check"
NOTES_KEY = "term_sheet_notes"            # the notes (column D) of the last imported Excel


def current_notes():
    """The notes beside the fields: those of the Excel imported last, or of the template shipped with the app."""
    return st.session_state.get(NOTES_KEY) or template_notes()


def snapshot_of(ts):
    """What the check was made on: the term sheet and the notes it was given."""
    from ai.termcheck import notes_text
    return term_sheet_text(ts) + "\n--notes--\n" + notes_text(ts, current_notes())


def plain(text):
    return "".join("\\" + ch if ch in "\\`*_{}[]()#+-.!|~$" else ch for ch in str(text))


def run_check(ts):
    """Best effort: a missing key or a failed call is recorded, and the workflow carries on.
    Returns "ran" when this call did the check, "kept" when this version of the term sheet was already checked (or its
    result already shown)."""
    snapshot = snapshot_of(ts)
    previous = st.session_state.get(RESULT_KEY)
    if previous and previous["snapshot"] == snapshot and ("issues" in previous or previous.get("shown")):
        return "kept"
    client = get_client(st.session_state.get("openai_api_key"))
    if client is None:
        st.session_state[RESULT_KEY] = {"snapshot": snapshot, "note": "The term sheet was not checked by the AI: no API key was set."}
        return "ran"
    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    with st.spinner("Checking the term sheet..."):
        try:
            result = check_term_sheet(ts, CountingClient(client, calls, "term_sheet_check"), MODEL, notes=current_notes())
        except AIStepError as e:
            st.session_state[RESULT_KEY] = {"snapshot": snapshot, "note": f"The AI term sheet check could not run: {e}"}
            return "ran"
    st.session_state[RESULT_KEY] = {"snapshot": snapshot, "issues": result.issues}
    return "ran"


def needs_a_look():
    """True when the check that just ran has something to show the user: points to look at, or a note that it did not run."""
    result = st.session_state.get(RESULT_KEY) or {}
    return bool(result.get("issues") or result.get("note"))


def hold(ts):
    """Marks the current result as shown, so the next Continue goes on instead of checking again."""
    st.session_state[RESULT_KEY]["shown"] = True


def show_result(ts):
    """Shows what the AI check found. True when it showed something the user must decide on (the page then says how to go on)."""
    result = st.session_state.get(RESULT_KEY)
    if result is None:
        return False
    if result["snapshot"] != snapshot_of(ts):
        st.caption("The term sheet changed after the AI checked it. Press Continue to check it again.")
        return False
    if "note" in result:
        st.warning(plain(result["note"]))
        return True
    if result["issues"]:
        st.warning(f"The AI check found {len(result['issues'])} point(s) to look at. Nothing was changed.")
        for i in result["issues"]:
            rule = f" Its note says \u201c{plain(i.rule)}\u201d." if i.rule else ""
            st.warning(f"**{plain(title(i.field))}**: {plain(i.problem)} The term sheet says \u201c{plain(i.evidence)}\u201d.{rule}")
        return True
    st.caption("AI check: nothing to flag.")
    return False
