"""Session state for drafted new clauses: which ones the user keeps, where each one goes, and the wording of
the sentences after the user's edits.

Streamlit drops a widget's state when the widget is not drawn in a run, which happens as soon as the user
moves to another step. The choices are therefore also copied into plain session dicts, which survive. While
the widget exists it is the source of truth (so a change shows up in the same rerun); otherwise the stored
copy is used; otherwise the default.

Editing works like editing a message: Edit opens the whole clause as one text (one sentence per line) that can
be changed anywhere, Save replaces the clause's wording with it, Cancel throws it away. The contract only ever
sees the saved wording."""
import streamlit as st

DRAFTS_KEY = "clause_drafts_v2"          # request id -> DraftedClause
PLACEMENT_STORE = "draft_placements"     # request id -> key of the clause it goes in front of, or "end"
KEEP_STORE = "draft_keeps"               # request id -> bool
SAVED_STORE = "draft_saved_sentences"    # request id -> [sentence] after the user pressed Save
WORKING_STORE = "draft_working_text"     # request id -> the text being edited (only while editing)
EDITING_KEY = "draft_editing"            # set of request ids that are open for editing


def keep_key(entry_id):
    return f"keep_draft_{entry_id}"


def placement_key(entry_id):
    return f"place_draft_{entry_id}"


def edit_key(entry_id):
    return f"edit_draft_{entry_id}"


def tidy(text):
    """One line with single spaces."""
    return " ".join((text or "").split())


# ---------------------------------------------------------------------------- the wording
def sentences_of(entry_id, drafted):
    """The clause's sentences as they stand in the contract: the saved wording, else the drafted one."""
    saved = st.session_state.get(SAVED_STORE, {}).get(entry_id)
    sentences = drafted.sentences if saved is None else saved
    return [t for t in (tidy(s) for s in sentences) if t]


def is_editing(entry_id):
    return entry_id in st.session_state.get(EDITING_KEY, set())


def working_text(entry_id):
    return st.session_state.get(WORKING_STORE, {}).get(entry_id, "")


def set_working(entry_id, text):
    st.session_state.setdefault(WORKING_STORE, {})[entry_id] = text


def _close(entry_id):
    st.session_state.get(EDITING_KEY, set()).discard(entry_id)
    st.session_state.get(WORKING_STORE, {}).pop(entry_id, None)
    st.session_state.pop(edit_key(entry_id), None)


def start_edit(entry_id, drafted):
    """Edit button: open the clause as one text, one sentence per line, to be changed anywhere."""
    _close(entry_id)
    st.session_state.setdefault(EDITING_KEY, set()).add(entry_id)
    set_working(entry_id, "\n".join(sentences_of(entry_id, drafted)))


def save_edit(entry_id):
    """Save button: each non-empty line of the text becomes a sentence of the clause (a numbered item in the contract)."""
    text = st.session_state.get(edit_key(entry_id), working_text(entry_id))
    st.session_state.setdefault(SAVED_STORE, {})[entry_id] = [t for t in (tidy(line) for line in text.splitlines()) if t]
    _close(entry_id)


def cancel_edit(entry_id):
    """Cancel button: the text being edited is thrown away and the saved wording stays as it was."""
    _close(entry_id)


# ---------------------------------------------------------------------------- keep and position
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
    return [{"key": f"drafted_{entry_id}", "title": drafted.title, "sentences": sentences_of(entry_id, drafted),
             "before": placement_of(entry_id, drafted)} for entry_id, drafted in kept()]


def reword(entry_id, drafted, change_type, old, new):
    """Writes an accepted wording change into a drafted clause: the sentence `old` becomes `new` (or `new` is added as a last
    sentence). The result is saved like the user's own Save. False when the sentence is not there any more."""
    sentences = sentences_of(entry_id, drafted)
    if change_type == "add":
        sentences.append(tidy(new))
    elif change_type == "remove":
        at = next((i for i, s in enumerate(sentences) if tidy(s).lower() == tidy(old).lower()), None)
        if at is None:
            return False
        del sentences[at]
    else:
        at = next((i for i, s in enumerate(sentences) if tidy(s).lower() == tidy(old).lower()), None)
        if at is None:
            return False
        sentences[at] = tidy(new)
    st.session_state.setdefault(SAVED_STORE, {})[entry_id] = sentences
    return True


def snapshot(entry_id):
    """Everything about a request's draft, so that Undo can bring a rejected request back. None when it has no draft."""
    drafted = st.session_state.get(DRAFTS_KEY, {}).get(entry_id)
    if drafted is None:
        return None

    def copy(store):
        value = st.session_state.get(store, {}).get(entry_id)
        return list(value) if isinstance(value, list) else value

    return {"drafted": drafted, "saved": copy(SAVED_STORE), "placement": copy(PLACEMENT_STORE), "keep": copy(KEEP_STORE),
            "keep_widget": st.session_state.get(keep_key(entry_id)), "placement_widget": st.session_state.get(placement_key(entry_id))}


def restore(entry_id, snap):
    """Puts a draft back as snapshot() found it."""
    if not snap:
        return
    st.session_state.setdefault(DRAFTS_KEY, {})[entry_id] = snap["drafted"]
    for store, name in ((SAVED_STORE, "saved"), (PLACEMENT_STORE, "placement"), (KEEP_STORE, "keep")):
        if snap[name] is not None:
            st.session_state.setdefault(store, {})[entry_id] = snap[name]


def forget(entry_id):
    """Drops a rejected request's draft and every choice made about it."""
    st.session_state.get(DRAFTS_KEY, {}).pop(entry_id, None)
    for store in (PLACEMENT_STORE, KEEP_STORE, SAVED_STORE):
        st.session_state.get(store, {}).pop(entry_id, None)
    _close(entry_id)
    st.session_state.pop(keep_key(entry_id), None)
    st.session_state.pop(placement_key(entry_id), None)
