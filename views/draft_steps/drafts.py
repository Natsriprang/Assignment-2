"""Session state for drafted new clauses: which ones the user keeps and where each one goes."""
import streamlit as st

DRAFTS_KEY = "clause_drafts_v2"      # request id -> DraftedClause


def keep_key(entry_id):
    return f"keep_draft_{entry_id}"


def placement_key(entry_id):
    return f"place_draft_{entry_id}"


def kept():
    """[(request id, DraftedClause)] for the drafts the user keeps, in the order the requests were first raised."""
    return [(entry_id, drafted) for entry_id, drafted in sorted(st.session_state.get(DRAFTS_KEY, {}).items())
            if st.session_state.get(keep_key(entry_id), True)]


def placement_of(entry_id, drafted):
    """Key of the clause this draft goes in front of (or "end"): the user's choice, else the AI's suggestion."""
    return st.session_state.get(placement_key(entry_id), drafted.placement_before)


def drafted_for_library():
    return [{"key": f"drafted_{entry_id}", "title": drafted.title, "sentences": drafted.sentences,
             "before": placement_of(entry_id, drafted)} for entry_id, drafted in kept()]
