"""The review round of the draft (step 3). The AI reads the whole draft against the term sheet in two calls (a review, then a second look
at its own findings) and reports what is missing, does not agree with the term sheet, contradicts itself or is too vague. A finding
may come with a proposed fix: one sentence rewritten, or one sentence added at the end of a clause. Each fix has Apply, Edit and Reject
like the requests in the Clauses step, and only Apply writes anything into the draft.

It runs once by itself when the preview is first opened with an API key, and after that only when asked (Review again), so it never spends
a call without the user knowing. The result is shown as it was when it was made. Nothing here blocks the download."""
import hashlib
import json
from types import SimpleNamespace

import streamlit as st

from ai.interpret import term_sheet_text
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.review import review_draft, sections_of
from core import wording
from core.draft_state import library_for
from core.header import build_header
from core.signatures import build_signature_block, signature_texts
from views import clause_sandbox
from views.draft_steps import clauses, drafts, flow, wording_state

RESULT_KEY = "draft_review"                # {"snapshot", "run", "findings", "dropped", "notes", "second_look_done"} or {"snapshot", "error"}
AUTO_KEY = "draft_review_auto"             # the draft the review was last started on by itself
RUN_KEY = "draft_review_run"               # how many reviews were made: keeps the widgets of one review apart from the next
STATUS_KEY = "draft_review_status"         # finding key -> {"state": "applied" | "rejected", "entry": {...}} for the current review
NOTE_KEY = "draft_review_notes"            # finding key -> a sentence about why an Apply did not write anything
FIRST_STEP = "review"
SECOND_STEP = "review_second_look"


def plain(text):
    return "".join("\\" + ch if ch in "\\`*_{}[]()#+-.!|~$" else ch for ch in str(text))


# ---------------------------------------------------------------------------- what the AI reads
def current_library():
    ts = clause_sandbox.current_term_sheet()
    return library_for(clause_sandbox.ensure_state(clauses.STATE_KEY), clause_sandbox.current_limits(), drafts.drafted_for_library(), ts,
                       wording_state.applied())


def current_input():
    """(term sheet text, sections of the draft as it stands now)."""
    ts = clause_sandbox.current_term_sheet()
    block = build_signature_block(ts)
    return term_sheet_text(ts), sections_of(current_library(), build_header(ts), signature_texts(block)[1:])


def snapshot():
    ts_text, sections = current_input()
    return hashlib.sha256(json.dumps([ts_text, [(s.key, s.text) for s in sections]], ensure_ascii=False).encode()).hexdigest()


# ---------------------------------------------------------------------------- running it
def run_review(client):
    """Two AI calls now (the review and the second look); the result is stored with the draft it was made on."""
    ts_text, sections = current_input()
    run = st.session_state.get(RUN_KEY, 0) + 1
    st.session_state[RUN_KEY] = run
    st.session_state[STATUS_KEY] = {}
    st.session_state[NOTE_KEY] = {}
    result = {"snapshot": snapshot(), "run": run}
    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    with st.spinner("Reviewing the draft against the term sheet..."):
        try:
            found = review_draft(ts_text, sections, CountingClient(client, calls, FIRST_STEP), MODEL,
                                 second_client=CountingClient(client, calls, SECOND_STEP))
            result.update(findings=found.findings, dropped=found.dropped, notes=found.notes, second_look_done=found.second_look_done)
        except AIStepError as e:
            result["error"] = str(e)
    st.session_state[RESULT_KEY] = result


# ---------------------------------------------------------------------------- one finding
def fkey(run, f):
    return f"{run}_{f.id}"


def text_key(run, f):
    return clauses.widget_key("review_text", fkey(run, f))


def current_text(run, f):
    """The new wording as it stands: what the user saved with Edit, else the AI's."""
    return wording.norm(wording_state.saved(fkey(run, f), f.new_text))


def problem_with(f, text):
    if not text:
        return "There is no new wording yet."
    problem = wording.check_rewrite(f.old_text if f.fix_type == "modify" else "", text, f.fix_type, f.quote, term_sheet_text(clause_sandbox.current_term_sheet()))
    return "" if problem in ("The new wording does not contain the figure you asked for.",) else problem


def _refresh_snapshot(result):
    """What the user did through a finding is not 'the draft changed since the review': the review keeps its place."""
    result["snapshot"] = snapshot()


def apply_fix(run, f):
    """Apply button: the wording as the user left it is written into the draft the way the Clauses step writes a wording change."""
    key = fkey(run, f)
    notes = st.session_state.setdefault(NOTE_KEY, {})
    text = current_text(run, f)
    if f.fix_type == "modify" and text.lower() == wording.norm(f.old_text).lower():
        notes[key] = "The wording was not changed: press Edit to write the new wording, then Apply."
        return
    if not text:
        notes[key] = "There is no new wording yet: press Edit to write it, then Apply."
        return
    drafted_id = int(f.clause_key.split("_", 1)[1]) if f.clause_key.startswith("drafted_") else None
    saved_before = st.session_state.get(drafts.SAVED_STORE, {}).get(drafted_id) if drafted_id is not None else None
    saved_before = list(saved_before) if saved_before is not None else None
    d = SimpleNamespace(clause_key=f.clause_key, change_type=f.fix_type, old_text=f.old_text, summary=f.issue[:80])
    if not clauses.write_wording_change(d, text):
        notes[key] = "That clause is no longer in the draft."
        return
    edit_id = None if drafted_id is not None else clauses.widget_key("edit", f.clause_key, f.fix_type, f.old_text, text)
    entry = {"kind": "wording", "edit_id": edit_id, "drafted_id": drafted_id, "saved_before": saved_before}
    if edit_id is not None and edit_id in clauses.failed_edit_ids():          # the sentence is not there any more
        clauses.revert_entry(entry)
        notes[key] = "That sentence is no longer in the clause: it changed after the review was made."
        return
    notes.pop(key, None)
    st.session_state.setdefault(STATUS_KEY, {})[key] = {"state": "applied", "entry": entry, "text": text}
    _refresh_snapshot(st.session_state.get(RESULT_KEY, {}))


def undo_fix(run, f):
    key = fkey(run, f)
    status = st.session_state.get(STATUS_KEY, {}).pop(key, None)
    if status and status["state"] == "applied":
        clauses.revert_entry(status["entry"])
        _refresh_snapshot(st.session_state.get(RESULT_KEY, {}))


def reject_fix(run, f):
    st.session_state.setdefault(STATUS_KEY, {})[fkey(run, f)] = {"state": "rejected"}


def start_edit(run, f):
    wording_state.start_edit(fkey(run, f), current_text(run, f) or f.old_text)


def save_edit(run, f):
    wording_state.save_edit(fkey(run, f), text_key(run, f), wording.norm)


def cancel_edit(run, f):
    wording_state.cancel_edit(fkey(run, f), text_key(run, f))


def show_fix(run, f, status):
    key = fkey(run, f)
    text = status["text"] if status and status["state"] == "applied" else current_text(run, f)
    if f.fix_type == "add":
        st.caption("A new sentence at the end of this clause")
        st.markdown(plain(text) if text else "_(nothing yet)_")
    else:
        before, after = wording.diff_markup(f.old_text, text)
        st.caption("Current wording")
        st.markdown(before)
        st.caption("Proposed wording")
        st.markdown(after)
    if not status:
        problem = problem_with(f, text)
        if problem:
            st.warning(f"Check before you apply: {problem} You can still apply it, or press Edit to change the wording first.")
    note = st.session_state.get(NOTE_KEY, {}).get(key)
    if note:
        st.warning(note)


def show_finding(run, f):
    key = fkey(run, f)
    status = st.session_state.get(STATUS_KEY, {}).get(key)
    with st.container(border=True):
        st.markdown(f"**{plain(f.clause)}**" + (" \u00b7 found by the second look" if f.round == 2 else ""))
        st.write(plain(f.issue))
        if f.why:
            st.caption(f"Why: {plain(f.why)}")
        if f.quote_verified:
            st.caption(f"In the draft: \u201c{plain(f.quote)}\u201d")
        if f.fix_type == "none":
            st.caption(plain(f.fix_note) if f.fix_note else "No automatic fix. Change the draft in the Clauses step, or in the Word file after downloading.")
            return
        if status and status["state"] == "rejected":
            st.caption("Rejected.")
            st.button("Undo", on_click=undo_fix, args=(run, f), key=clauses.widget_key("review_undo_reject", key))
            return
        editing = not status and wording_state.is_editing(key)
        if editing:
            st.caption("Edit the wording. The contract changes only with what you save and then apply: press Save to keep your changes.")
            tk = text_key(run, f)
            if tk not in st.session_state:
                st.session_state[tk] = wording_state.working(key, current_text(run, f))
            lines = st.session_state[tk].splitlines() or [""]
            height = min(500, max(120, 30 * sum(len(line) // 90 + 1 for line in lines) + 40))
            wording_state.set_working(key, st.text_area("New wording", key=tk, height=height))
            c1, c2, _ = st.columns([1, 1, 8])
            c1.button("Save", type="primary", on_click=save_edit, args=(run, f), key=clauses.widget_key("review_save", key))
            c2.button("Cancel", on_click=cancel_edit, args=(run, f), key=clauses.widget_key("review_cancel", key))
            return
        show_fix(run, f, status)
        if status and status["state"] == "applied":
            st.success("Applied to the draft.")
            st.button("Undo", on_click=undo_fix, args=(run, f), key=clauses.widget_key("review_undo", key))
            return
        c0, c1, c2, _ = st.columns([1, 1, 1, 5])
        c0.button("Apply", type="primary", on_click=apply_fix, args=(run, f), key=clauses.widget_key("review_apply", key))
        c1.button("Edit", on_click=start_edit, args=(run, f), key=clauses.widget_key("review_edit", key))
        c2.button("Reject", on_click=reject_fix, args=(run, f), key=clauses.widget_key("review_reject", key))


# ---------------------------------------------------------------------------- the section
def show():
    """The review section of the preview."""
    st.subheader("Review of the draft")
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
        st.caption("The draft was not reviewed against the term sheet yet. Enter an API key to review it." if client is None
                   else "The draft was not reviewed against the term sheet yet.")
    else:
        if client is not None and result["snapshot"] != snap:
            st.caption("The draft or the term sheet changed since the review was made. This is what that review found; press Review again to review it again.")
        if "error" in result:
            st.warning(f"The review could not run: {plain(result['error'])}")
        else:
            for note in result["notes"]:
                st.caption(plain(note))
            run = result["run"]
            if result["findings"]:
                st.warning(f"{len(result['findings'])} point(s) to review. Nothing was changed: a fix is written into the draft only when you press Apply, "
                           "and you can still download the draft.")
                for f in result["findings"]:
                    show_finding(run, f)
            else:
                st.caption("The review found nothing in the draft that disagrees with the term sheet.")
            if result["dropped"]:
                with st.expander(f"{len(result['dropped'])} finding(s) dropped by the second look"):
                    for _, issue, reason in result["dropped"]:
                        st.caption(f"{plain(issue)} \u2014 {plain(reason)}")
    if client is not None and st.button("Review again" if result is not None else "Review the draft", key="review_again"):
        run_review(client)
        st.rerun()
