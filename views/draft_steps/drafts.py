"""Session state for drafted new clauses: which ones the user keeps and where each one goes.

Streamlit drops a widget's state when the widget is not drawn in a run, which happens as soon as the user
moves to another step. The choices are therefore also copied into plain session dicts, which survive. While
the widget exists it is the source of truth (so a change shows up in the same rerun); otherwise the stored
copy is used; otherwise the default."""
import streamlit as st

DRAFTS_KEY = "clause_drafts_v2"          # request id -> DraftedClause
PLACEMENT_STORE = "draft_placements"     # request id -> key of the clause it goes in front of, or "end"
KEEP_STORE = "draft_keeps"               # request id -> bool


def keep_key(entry_id):
    return f"keep_draft_{entry_id}"


def placement_key(entry_id):
    return f"place_draft_{entry_id}"


def is_kept(entry_id):
    if keep_key(entry_id) in st.session_state:
        return bool(st.session_state[keep_key(entry_id)])
    return st.session_state.get(KEEP_STORE, {}).get(entry_id, True)


def placement_of(entry_id, drafted):
    """Key of the clause this draft goes in front of (or "end"): the user's choice, else the AI's suggestion."""
    if placement_key(entry_id) in st.session_state:
        return st.session_state[placement_key(entry_id)]
    return st.session_state.get(PLACEMENT_STORE, {}).get(entry_id, drafted.placement_before)


def remember(entry_id, kept, placement):
    st.session_state.setdefault(KEEP_STORE, {})[entry_id] = bool(kept)
    st.session_state.setdefault(PLACEMENT_STORE, {})[entry_id] = placement


def kept():
    """[(request id, DraftedClause)] for the drafts the user keeps, in the order the requests were first raised."""
    return [(entry_id, drafted) for entry_id, drafted in sorted(st.session_state.get(DRAFTS_KEY, {}).items())
            if is_kept(entry_id)]


def drafted_for_library():
    return [{"key": f"drafted_{entry_id}", "title": drafted.title, "sentences": drafted.sentences,
             "before": placement_of(entry_id, drafted)} for entry_id, drafted in kept()]
