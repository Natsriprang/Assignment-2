"""Session state for the wording changes the user accepted in the Clauses step. They are kept as plain data and applied to a fresh
clause library each time it is built (core.wording.apply_edits), so the preview, the Word file and the next analysis all see
the same text, and a change that no longer fits the clause is reported instead of applied wrongly."""
import streamlit as st

EDITS_KEY = "draft_wording_edits"       # [{"id", "clause_key", "change_type", "old", "new", "summary"}] in the order accepted


def applied():
    return list(st.session_state.get(EDITS_KEY, []))


def add_edit(edit):
    """Records an accepted change; the same change accepted twice is recorded once."""
    edits = st.session_state.setdefault(EDITS_KEY, [])
    if not any(e["id"] == edit["id"] for e in edits):
        edits.append(edit)


def clear():
    st.session_state.pop(EDITS_KEY, None)
