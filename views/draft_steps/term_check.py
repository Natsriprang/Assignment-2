"""The term sheet check, as its own action: the Check / Recheck button runs the exact checks (code) and the AI check, and stores
what they found with the term sheet it was made on. The page shows that result, whatever the term sheet has become since, and
says so when it is out of date. Continue only moves on, and only once the current term sheet has been checked. Nothing here
blocks on what the check found, and nothing changes the term sheet."""
import streamlit as st

from ai.interpret import term_sheet_text
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.termcheck import check_term_sheet
from core.field_rules import rule_warnings, template_notes
from core.field_titles import title
from core.term_checks import blank_fields, contradictions
from views.draft_steps import flow

RESULT_KEY = "term_sheet_check"
NOTES_KEY = "term_sheet_notes"            # the notes (column D) of the last imported Excel


def plain(text):
    return "".join("\\" + ch if ch in "\\`*_{}[]()#+-.!|~$" else ch for ch in str(text))


def current_notes():
    """The notes beside the fields: those of the Excel imported last, or of the template shipped with the app."""
    return st.session_state.get(NOTES_KEY) or template_notes()


def snapshot_of(ts):
    """What a check was made on."""
    return term_sheet_text(ts)


def code_findings(ts):
    """What the exact checks find: the blanks (one sentence), then values that contradict each other or break a note."""
    found = []
    blanks = blank_fields(ts)
    if blanks:
        found.append("Not filled in: " + ", ".join(blanks) + ".")
    return found + contradictions(ts) + rule_warnings(ts, current_notes())


def run_check(ts):
    """Runs both checks now, every time it is asked, and stores the result. A missing key or a failed AI call is recorded as a
    note (the exact checks are still made)."""
    result = {"snapshot": snapshot_of(ts), "code": code_findings(ts)}
    client = get_client(st.session_state.get("openai_api_key"))
    if client is None:
        result["note"] = "The term sheet was not checked by the AI: no API key was set."
    else:
        calls = st.session_state.setdefault(flow.CALLS_KEY, [])
        with st.spinner("Checking the term sheet..."):
            try:
                result["issues"] = check_term_sheet(ts, CountingClient(client, calls, "term_sheet_check"), MODEL).issues
            except AIStepError as e:
                result["note"] = f"The AI term sheet check could not run: {e}"
    st.session_state[RESULT_KEY] = result


def has_result():
    return st.session_state.get(RESULT_KEY) is not None


def is_checked(ts):
    """True when the current term sheet is the one the last check was made on."""
    result = st.session_state.get(RESULT_KEY)
    return result is not None and result["snapshot"] == snapshot_of(ts)


def show_result(ts):
    """The result of the last check, as it was. Before any check there is only the reminder to make one."""
    result = st.session_state.get(RESULT_KEY)
    if result is None:
        st.caption("Check the term sheet before you continue.")
        return
    if result["snapshot"] != snapshot_of(ts):
        st.caption("The term sheet changed since it was last checked. This is what that check found; press Recheck to check it again.")
    for text in result["code"]:
        st.warning(plain(text))
    if not result["code"]:
        st.caption("Exact checks: nothing to flag.")
    flagged = bool(result["code"])
    if "note" in result:
        st.warning(plain(result["note"]))
        flagged = True
    elif result["issues"]:
        st.warning(f"The AI check found {len(result['issues'])} point(s) to look at. Nothing was changed.")
        for i in result["issues"]:
            st.warning(f"**{plain(title(i.field))}**: {plain(i.problem)} The term sheet says \u201c{plain(i.evidence)}\u201d.")
        flagged = True
    else:
        st.caption("AI check: nothing to flag.")
    if flagged:
        st.caption("You can continue with these warnings, or fix them and press Recheck.")
