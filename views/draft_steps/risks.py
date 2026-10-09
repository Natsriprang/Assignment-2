"""The risk check of the draft (step 3). The AI reads the changes the draft makes to the standard template and says which of them
create a real risk, for whom, and why. It runs once by itself when the preview is first opened with changes in the draft, and after
that only when asked (Recheck risks), so it never spends a call without the user knowing. The result is shown as it was when it was
made, whatever the draft has become since, and says so when it is out of date. Nothing here blocks the download or changes the draft."""
import streamlit as st

from ai.interpret import clause_text
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.risk import flag_risks
from core.clause_data import build_library
from core.draft_state import library_for
from core.risk_items import build_items, snapshot
from views import clause_sandbox
from views.draft_steps import clauses, drafts, flow, wording_state

RESULT_KEY = "risk_check"                # {"snapshot", "findings", "notes"} or {"snapshot", "error"}
AUTO_KEY = "risk_check_auto"             # the changes the check was last started on by itself
STEP_NAME = "risk_flagging"
LABEL = {"high": "High", "medium": "Medium", "low": "Low"}
COLOUR = {"high": "220, 38, 38", "medium": "249, 115, 22", "low": "234, 179, 8"}      # red, orange, yellow (RGB, used with some transparency)


def plain(text):
    return "".join("\\" + ch if ch in "\\`*_{}[]()#+-.!|~$" else ch for ch in str(text))


def current_items():
    """The changes the draft makes to the standard template, as the draft stands now."""
    ts = clause_sandbox.current_term_sheet()
    limits = clause_sandbox.current_limits()
    standard = library_for({}, limits, None, ts)
    template_text = {c.key: (c.title, clause_text(c)) for c in standard}
    template = build_library()
    included = clause_sandbox.ensure_state(clauses.STATE_KEY)
    edits, failed = wording_state.applied(), []
    library_for(included, limits, drafts.drafted_for_library(), ts, edits, failed)
    applied = clauses.applied_entries_now()
    words_by_edit = {e["edit_id"]: e["evidence"] for e in applied if e["kind"] == "wording" and e["edit_id"]}
    words_by_clause = {e["key"]: e["evidence"] for e in applied if e["kind"] == "clause" and e["action"] == "exclude"}
    requests = {f"drafted_{entry_id}": drafted.request for entry_id, drafted in drafts.kept()}
    return build_items(template_text, {c.key: c.included for c in template}, {c.key for c in template if c.optional}, included, edits,
                       {f["id"] for f in failed}, drafts.drafted_for_library(), requests, words_by_edit, words_by_clause)


def run_check(items, client):
    """One AI call now; the result is stored with the changes it was made on."""
    result = {"snapshot": snapshot(items)}
    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    with st.spinner("Checking the risks of the changes..."):
        try:
            found = flag_risks(items, CountingClient(client, calls, STEP_NAME), MODEL)
            result["findings"], result["notes"] = found.findings, found.notes
        except AIStepError as e:
            result["error"] = str(e)
    st.session_state[RESULT_KEY] = result


def colour_css():
    """The style of the risk boxes: a tinted background and a coloured edge by severity, light enough to read in a light or a dark theme."""
    rules = "".join(f"[class*='st-key-risk_box_{sev}_'] {{ background-color: rgba({rgb}, 0.14); border: 1px solid rgba({rgb}, 0.65); border-radius: 0.5rem; "
                    f"padding: 0.75rem 1rem; }}\n" for sev, rgb in COLOUR.items())
    return f"<style>{rules}</style>"


def show_findings(findings):
    st.markdown(colour_css(), unsafe_allow_html=True)
    for n, f in enumerate(findings):
        with st.container(key=f"risk_box_{f.severity}_{n}"):
            st.markdown(f"**{LABEL[f.severity]} \u00b7 {plain(f.clause)}**")
            st.write(plain(f.issue))
            st.write(f"**Risk to:** {plain(f.party)}")
            st.write(f"**Why:** {plain(f.why)}")
            if f.suggestion:
                st.write(f"**Consider:** {plain(f.suggestion)}")
            if f.quote_verified:
                st.write(f"**In the draft:** \u201c{plain(f.quote)}\u201d")


def show():
    """The risk section at the top of the preview."""
    items = current_items()
    result = st.session_state.get(RESULT_KEY)
    st.subheader("Risks to review")
    if not items:
        st.write("No changes from the standard template to assess.")
        return
    client = get_client(st.session_state.get("openai_api_key"))
    snap = snapshot(items)
    if client is not None and result is None and st.session_state.get(AUTO_KEY) != snap:
        st.session_state[AUTO_KEY] = snap
        run_check(items, client)
        result = st.session_state.get(RESULT_KEY)
    if result is None:
        st.write("The risks of the changes were not checked yet. Enter an API key to check them." if client is None
                   else "The risks of the changes were not checked yet.")
    else:
        if result["snapshot"] != snap:
            st.write("The draft changed since the risks were last checked. This is what that check found; press Recheck risks to check again.")
        if "error" in result:
            st.write(f"The risk check could not run: {plain(result['error'])}")
        elif result["findings"]:
            st.write(f"{len(result['findings'])} point(s) to review.")
            show_findings(result["findings"])
        else:
            st.write("No significant risks were found in the changes to the standard template.")
    if client is not None and st.button("Recheck risks" if result is not None else "Check risks", key="risk_recheck"):
        run_check(items, client)
        st.rerun()
