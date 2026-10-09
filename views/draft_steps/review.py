"""The review round of the draft (step 3). Two kinds of check, side by side:

- The app checks by itself, without AI, which clauses still refer to a clause that was taken out (core.dependencies). This is always
  shown, with no API key and no button.
- The AI reads the final draft, with the sentences this draft changed or added marked, in two independent reads (one goes through the draft
  matter by matter, the other starts from the changed sentences), and keeps only what both reads found: a changed sentence that contradicts
  another sentence of the draft, each with the two sentences quoted. It does not read the term sheet (the term sheet is checked in its own
  step) and it proposes no fix: to change the draft, the user goes back to the Clauses step.

The AI part runs once by itself when the preview is first opened with an API key, and after that only when asked (Review again, which is
off while neither the term sheet nor the draft has changed since the last review), so it never spends a call without the user knowing.
The result is shown as it was when it was made. Nothing here blocks the download."""
import hashlib
import json

import streamlit as st

from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.review import dependency_findings, review_draft, sections_of, term_sheet_for_review
from core.draft_state import library_for
from core.header import build_header
from core.signatures import build_signature_block, signature_texts
from views import clause_sandbox
from views.draft_steps import clauses, drafts, flow, risks, wording_state

RESULT_KEY = "draft_review"                # {"snapshot", "input_snapshot", "run", "findings", "single", "notes", "both_done"} or {..., "error"}
AUTO_KEY = "draft_review_auto"             # the draft the review was last started on by itself
RUN_KEY = "draft_review_run"               # how many reviews were made
FIRST_STEP = "review_by_matter"              # the read that goes through the final draft matter by matter
SECOND_STEP = "review_by_changes"            # the read that starts from the changes


def plain(text):
    return "".join("\\" + ch if ch in "\\`*_{}[]()#+-.!|~$" else ch for ch in str(text))


# ---------------------------------------------------------------------------- what the AI reads
def current_library():
    ts = clause_sandbox.current_term_sheet()
    return library_for(clause_sandbox.ensure_state(clauses.STATE_KEY), clause_sandbox.current_limits(), drafts.drafted_for_library(), ts,
                       wording_state.applied())


def current_changes():
    """What this draft changed or added compared with the template, as the sentences themselves (a clause taken out has none)."""
    return [{"id": it["id"], "kind": it["kind"], "clause": it["clause"], "before": it["before"], "after": it["after"], "text": it["after"],
             "user_words": it["user_words"]} for it in risks.current_items() if it["kind"] in ("wording_change", "new_clause") and (it["before"] or it["after"])]


def current_input():
    """(term sheet text, sections of the draft as it stands now, the changed sentences)."""
    ts = clause_sandbox.current_term_sheet()
    block = build_signature_block(ts)
    return term_sheet_for_review(ts), sections_of(current_library(), build_header(ts), signature_texts(block)[1:]), current_changes()


def snapshot():
    ts_text, sections, changes = current_input()
    return hashlib.sha256(json.dumps([[(s.key, s.text) for s in sections], [(c["before"], c["text"]) for c in changes]], ensure_ascii=False).encode()).hexdigest()


# ---------------------------------------------------------------------------- running it
def run_review(client):
    """Two AI calls now (the two reads); the result is stored with the draft it was made on."""
    ts_text, sections, changes = current_input()
    run = st.session_state.get(RUN_KEY, 0) + 1
    st.session_state[RUN_KEY] = run
    snap = snapshot()
    result = {"snapshot": snap, "input_snapshot": snap, "run": run, "n_changes": len(changes)}
    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    with st.spinner("Reviewing the draft..."):
        try:
            found = review_draft(ts_text, sections, CountingClient(client, calls, FIRST_STEP), MODEL,
                                 second_client=CountingClient(client, calls, SECOND_STEP), changes=changes)
            result.update(findings=found.findings, single=found.single, notes=found.notes, both_done=found.both_done)
        except AIStepError as e:
            result["error"] = str(e)
    st.session_state[RESULT_KEY] = result


# ---------------------------------------------------------------------------- one finding
def fkey(run, f):
    return f"{run}_{f.id}"


def show_finding(run, f):
    """One point to review: what is wrong, with the quotes that show it. A contradiction has no fix to apply; the user changes the draft in the
    Clauses step. A clause that refers to one that was taken out says what to do about it."""
    with st.container(border=True):
        st.markdown(f"**{plain(f.clause)}**")
        st.write(plain(f.issue))
        if f.term_sheet_says:
            st.write(f"**Term sheet:** \u201c{plain(f.term_sheet_says)}\u201d")
        if f.quote:
            st.write(f"**Draft:** \u201c{plain(f.quote)}\u201d")
        if f.other_quote:
            st.write(f"**Also in the draft ({plain(f.other_clause)}):** \u201c{plain(f.other_quote)}\u201d")
        if f.source == "app":                           # what to do about a clause that refers to one that was taken out
            st.write(plain(f.fix_note))


# ---------------------------------------------------------------------------- the section
def show():
    """The review section of the preview."""
    st.subheader("Review of the draft")
    app_findings = dependency_findings(current_library())
    if app_findings:
        st.write(f"{len(app_findings)} clause(s) still refer to a clause that was taken out.")
        for f in app_findings:
            show_finding(0, f)
    client = get_client(st.session_state.get("openai_api_key"))
    result = st.session_state.get(RESULT_KEY)
    snap = None
    if client is not None:
        snap = snapshot()
        if result is None and st.session_state.get(AUTO_KEY) != snap:
            st.session_state[AUTO_KEY] = snap
            run_review(client)
            result = st.session_state.get(RESULT_KEY)
    if result is None:
        st.write("Enter an API key to run the review." if client is None else "The review has not run yet.")
    else:
        if client is not None and result["snapshot"] != snap:
            st.write("The draft changed since this review. Press Review again.")
        if "error" in result:
            st.write(f"The review could not run: {plain(result['error'])}")
        else:
            for note in [n for n in result["notes"] if not n.startswith(("Left out", "Dropped"))]:
                st.write(plain(note))                  # a read that could not run: the user needs to know that nothing was confirmed
            run = result["run"]
            if result["findings"]:
                st.write(f"{len(result['findings'])} point(s) to review.")
                for f in result["findings"]:
                    show_finding(run, f)
            elif result["both_done"]:
                st.write("Checked the final draft for sentences that contradict each other: none found.")
    if client is not None:
        unchanged = result is not None and "error" not in result and result.get("input_snapshot") == snap
        pressed = st.button("Review again" if result is not None else "Review the draft", key="review_again", disabled=unchanged)
        if unchanged:
            st.write("Nothing has changed since the last review.")
        if pressed:
            run_review(client)
            st.rerun()
