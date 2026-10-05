"""Session state for the wording changes in the Clauses step.

The accepted changes (EDITS_KEY) are kept as plain data and applied to a fresh clause library each time it is built
(core.wording.apply_edits), so the preview, the Word file and the next analysis all see the same text, and a change that no
longer fits the clause is reported instead of applied wrongly.

The new wording of a proposal can be edited like the wording of a clause the AI drafted: Edit opens it as one text, Save keeps
it, Cancel throws the typing away, and only the saved wording is ever applied. The stores are plain dicts because Streamlit
drops a widget's state when the widget is not drawn (as soon as the user is on another step)."""
import streamlit as st

EDITS_KEY = "draft_wording_edits"        # [{"id", "clause_key", "change_type", "old", "new", "summary"}] in the order accepted
SAVED_TEXT = "draft_wording_saved"       # proposal key -> the new wording the user saved
WORKING_TEXT = "draft_wording_working"   # proposal key -> the text being edited (only while editing)
EDITING = "draft_wording_editing"        # set of proposal keys open for editing


# ---------------------------------------------------------------------------- the accepted changes
def applied():
    return list(st.session_state.get(EDITS_KEY, []))


def add_edit(edit):
    """Records an accepted change; the same change accepted twice is recorded once. True when it was added."""
    edits = st.session_state.setdefault(EDITS_KEY, [])
    if any(e["id"] == edit["id"] for e in edits):
        return False
    edits.append(edit)
    return True


def remove_edit(edit_id):
    st.session_state[EDITS_KEY] = [e for e in st.session_state.get(EDITS_KEY, []) if e["id"] != edit_id]


def clear():
    st.session_state.pop(EDITS_KEY, None)


# ---------------------------------------------------------------------------- the new wording of a proposal
def saved(key, default):
    """The new wording as the user last saved it, else `default` (the AI's sentence)."""
    return st.session_state.get(SAVED_TEXT, {}).get(key, default)


def is_editing(key):
    return key in st.session_state.get(EDITING, set())


def working(key, default=""):
    return st.session_state.get(WORKING_TEXT, {}).get(key, default)


def set_working(key, text):
    st.session_state.setdefault(WORKING_TEXT, {})[key] = text


def _close(key, widget_key=None):
    st.session_state.get(EDITING, set()).discard(key)
    st.session_state.get(WORKING_TEXT, {}).pop(key, None)
    if widget_key:
        st.session_state.pop(widget_key, None)


def start_edit(key, text):
    """Edit button: the new wording opens as one text."""
    _close(key)
    st.session_state.setdefault(EDITING, set()).add(key)
    set_working(key, text)


def save_edit(key, widget_key, tidy):
    """Save button: what is in the text becomes the new wording (`tidy` makes it one line)."""
    text = st.session_state.get(widget_key, working(key))
    st.session_state.setdefault(SAVED_TEXT, {})[key] = tidy(text)
    _close(key, widget_key)


def cancel_edit(key, widget_key):
    """Cancel button: the typing is thrown away and the saved wording stays as it was."""
    _close(key, widget_key)
