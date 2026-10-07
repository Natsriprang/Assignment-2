"""Step 2: choose the clauses. The checkboxes are the one place that decides which clauses are in
the draft. The chat proposes changes (add or remove a clause, reword a provision) and asks when
something is unclear; ticked proposals are written into the checkboxes by the Apply button, and
the user can keep adjusting by hand. At least one analysis must run before the user continues."""
import difflib
import hashlib
import re

import streamlit as st

from ai.drafting import draft_clause
from ai.interpret import (InterpretationError, candidate_question, context_summary, forget_unknown_clauses, interpret_request,
                          result_lines, term_sheet_text)
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.references import select_references
from core import wording
from core.clause_data import build_library
from core.conditions import CONDITION_CLAUSES, conditions_of
from core.draft_state import library_for
from core.figures import numbers_in
from core.placement import placement_from_references
from core.reference_library import load_references
from core.term_sheet_fields import missing_required
from views import clause_sandbox
from views.draft_steps import drafts, flow, wording_state

STATE_KEY = "draft_included"
DEVIATIONS_KEY = "draft_deviations"
DRAFTS_KEY = drafts.DRAFTS_KEY       # request id -> DraftedClause
REQUEST_SEQ_KEY = "new_clause_request_seq"   # last request id handed out; ids are never reused
REQUEST_NUMBERS_KEY = "request_numbers"   # [{"n", "kind", "key", "evidence"}]: the number of each request that is not a new clause
REQUESTS_KEY = "new_clause_requests"  # [{"id": int, "text": str}] in the order the requests were first raised
STEP_NAME = "interpret"
DECLINED_KEY = "draft_declined"       # [{"key": clause key, "evidence": the user's words}]: links the user answered No to
UNDO_NOTE_KEY = "draft_undo_note"      # what the last Undo took out besides the change that was pressed (shown once)
APPLIED_KEY = "draft_applied_log"     # [{"id", "entries": [...]}]: what each Apply wrote into the draft, kept for the whole session
AUTO_KEY = "auto_analysis"           # the term sheet the first analysis was started on by itself, so it is not started again on every run
NO_REQUEST_BUTTON = "No special requests \u2014 apply the term sheet's rules"
NO_REQUEST_NOTE = ("This runs one AI analysis. With no request from you it looks only at what the term sheet itself calls for, "
                   "for example suggesting the Owner's Representations clause when the roof owner is a different party from the Owner.")


def plain(text):
    return re.sub(r"([\\`*_\[\]#>|~$<])", r"\\\1", text)


def widget_key(*parts):
    return "k_" + hashlib.md5("|".join(parts).encode()).hexdigest()[:10]


def action_key(a):
    return widget_key("act", a.clause_key, a.action)


def deviation_key(d):
    return widget_key("dev", d.clause_key, d.change_type, d.provision_quote, d.summary)


def newtext_key(d):
    return widget_key("newtext", deviation_key(d))


def applicable(d):
    """A wording change can be written when there is a sentence to change (or, for an addition, a clause to add to)."""
    return d.change_type == "add" or bool(d.old_text)


def default_text(d):
    """The new wording to start with: the AI's sentence; for a change that takes a point out, nothing (it is taken out); else the
    current sentence for the user to change."""
    return d.new_text or (d.old_text if d.change_type != "add" and not d.removes else "")


def current_text(d):
    """The new wording as it stands: what the user saved with Edit, else the AI's sentence (else the current sentence)."""
    return wording.norm(wording_state.saved(deviation_key(d), default_text(d)))


def start_wording_edit(d):
    """Edit opens the wording as one text; for a point that is being taken out it starts with that point (an empty text keeps it
    taken out, a different text replaces it)."""
    wording_state.start_edit(deviation_key(d), current_text(d) or (d.old_text if d.removes else ""))


def save_wording(key, widget):
    wording_state.save_edit(key, widget, wording.norm)


def cancel_wording(key, widget):
    wording_state.cancel_edit(key, widget)


def checked_problem(d, text):
    """What the checks find wrong with `text` as the new wording; "" when nothing. Advice only: it never blocks."""
    if d.removes and not text:
        return ""                                               # taking the whole point out needs no new wording
    if not text:
        return "There is no new wording yet."
    old = d.old_text if d.change_type != "add" else ""
    return wording.check_rewrite(old, text, d.change_type, d.provision_quote, f"{d.requested_change} {d.evidence}")


def default_tick(d):
    """Apply is ticked at the start only when there is wording and the checks have nothing to say."""
    return d.evidence_verified and applicable(d) and bool(d.new_text) and not d.rewrite_problem and not d.removes


def show_lines(lines):
    for line in lines:
        st.write(plain(line))

# The look of the chat of this step: the user's messages on the right, the assistant's on the left, as bubbles, with no avatars, and small
# buttons inside the bubbles. The hooks are the test ids Streamlit puts on its chat elements and a mark placed in each message of the user;
# when a hook is not there the chat simply looks as it did, and nothing stops working.
USER_MARK = '<span class="chat-user-mark"></span>'
CHAT_CSS = """<style>
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"], [data-testid="stChatMessageAvatarCustom"] { display: none; }
[data-testid="stChatMessage"] { background: transparent; padding: 0.2rem 0; }
[data-testid="stChatMessage"]:has(.chat-user-mark) { flex-direction: row-reverse; }
[data-testid="stChatMessageContent"] { border-radius: 16px; padding: 0.55rem 0.9rem; background: rgba(128, 128, 128, 0.08); max-width: 90%; margin-right: auto; }
[data-testid="stChatMessage"]:has(.chat-user-mark) [data-testid="stChatMessageContent"] { background: rgba(70, 130, 220, 0.18); max-width: 100%; margin-left: auto; margin-right: 0;
  border-bottom-right-radius: 4px; }
[data-testid="stChatMessage"] button { font-size: 0.8rem; padding: 0.1rem 0.6rem; min-height: 1.8rem; }
[data-testid="stChatMessage"] button p { font-size: 0.8rem; }
[data-testid="stChatMessage"] h3 { font-size: 1rem; padding: 0.2rem 0; }
</style>"""


def show_user_message(text):
    """The user's message, on the right: in the right-hand column of a row, so that it is on the right whatever the styles do, with the mark that
    gives its bubble the user's colour. (The assistant's reply is not put in a column: it holds boxes that use columns themselves.)"""
    _, right = st.columns([1, 3])
    with right:
        with st.chat_message("user"):
            st.markdown(USER_MARK, unsafe_allow_html=True)
            show_lines(text.split("\n"))



def has_analysis():
    """True once the model has analysed the request at least once in this run."""
    return any(c["step"] == STEP_NAME for c in st.session_state.get(flow.CALLS_KEY, []))


@st.cache_resource
def get_references():
    return load_references()


def wording_same(new, stored):
    """The same request by the user's own words (see ai.interpret): equal, or one inside the other when it is long enough."""
    from ai.interpret import _same_request
    return _same_request(new, stored) or _same_request(stored, new)


def normalize(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def next_request_number():
    """The next number of the one sequence all requests share (new clauses, removed clauses, wording changes)."""
    entries = st.session_state.get(REQUESTS_KEY, [])
    taken = [e["id"] for e in entries] + [b["n"] for b in st.session_state.get(REQUEST_NUMBERS_KEY, [])]
    seq = max([st.session_state.get(REQUEST_SEQ_KEY, 0)] + taken) + 1
    st.session_state[REQUEST_SEQ_KEY] = seq
    return seq


def request_number(kind, key, evidence=""):
    """The number of a request that is not a request for a new clause: the same request (same kind of change to the same clause or
    sentence, for the same words of the user) keeps its number in every later reply, and after an Undo."""
    book = st.session_state.setdefault(REQUEST_NUMBERS_KEY, [])
    for b in book:
        if b["kind"] == kind and b["key"] == key and (not evidence or not b["evidence"] or wording_same(evidence, b["evidence"])):
            if evidence and not b["evidence"]:
                b["evidence"] = evidence
            return b["n"]
    book.append({"n": next_request_number(), "kind": kind, "key": key, "evidence": evidence})
    return book[-1]["n"]


def action_number(a):
    return request_number("act", f"{a.clause_key}|{a.action}", a.evidence)


def deviation_number(d):
    return request_number("dev", f"{d.clause_key}|{d.change_type}|{normalize(d.old_text or d.provision_quote or d.evidence)}", d.evidence)


def request_id(text, evidence=""):
    """A stable id for a request with no matching clause, so it keeps its place and its draft when the model
    words it slightly differently in a later reply, or lists it again for the same words of the user."""
    entries = st.session_state.setdefault(REQUESTS_KEY, [])
    norm = normalize(text)
    for e in entries:
        if normalize(e["text"]) == norm:
            e["text"] = text
            e.setdefault("evidence", evidence)
            return e["id"]
    if evidence:
        for e in entries:
            if e.get("evidence") and wording_same(evidence, e["evidence"]):
                e["text"] = text
                return e["id"]
    for e in entries:
        if (difflib.SequenceMatcher(None, normalize(e["text"]), norm).ratio() >= 0.85
                and numbers_in(e["text"]) == numbers_in(text)):
            e["text"] = text
            return e["id"]
    seq = next_request_number()
    entries.append({"id": seq, "text": text, "evidence": evidence})
    return seq


def request_reject_key(text):
    return f"request:{normalize(text)}"


def reject_request(msg, entry_id, text):
    """Reject button callback for a request: its draft and choices are dropped and the model is told on the next
    analysis. Its number is not reused."""
    key = request_reject_key(text)
    entry = next((e for e in st.session_state.get(REQUESTS_KEY, []) if e["id"] == entry_id), {"id": entry_id, "text": text})
    msg.setdefault("rejected_requests", {})[key] = {"entry": dict(entry), "snapshot": drafts.snapshot(entry_id)}
    msg.setdefault("rejected", {})[key] = f"New clause request: {text}"
    msg.setdefault("rejected_numbers", {})[key] = entry_id
    st.session_state[REQUESTS_KEY] = [e for e in st.session_state.get(REQUESTS_KEY, []) if e["id"] != entry_id]
    drafts.forget(entry_id)


def new_clause_requests(result, rejected=None):
    """[(id, text)] for the new-clause requests to show, in the order they were first raised: the ones in this
    result that match no clause, plus every request that already has a draft, so a draft never disappears when a
    later reply no longer lists its request."""
    found = {}
    for u in result.unmapped_requests:
        if not u.candidate_key and request_reject_key(u.request) not in (rejected or {}):
            found[request_id(u.request, u.evidence)] = u.request
    texts = {e["id"]: e["text"] for e in st.session_state.get(REQUESTS_KEY, [])}
    for entry_id, drafted in st.session_state.get(DRAFTS_KEY, {}).items():
        found.setdefault(entry_id, texts.get(entry_id, drafted.request))
    return sorted((i, t) for i, t in found.items() if not drafts.is_kept(i))        # an applied clause is shown with the applied changes


def kept_drafts():
    """Drafted new clauses the user kept, with the position chosen for each, for the next step."""
    return [{"request": d.request, "title": d.title, "text": " ".join(drafts.sentences_of(entry_id, d)),
             "before": drafts.placement_of(entry_id, d),
             "references": [r.label for r in d.sources.values()]} for entry_id, d in drafts.kept()]


def show_lines_caption(lines):
    for line in lines:
        st.caption(plain(line))


def drafts_default(options):
    for candidate in ("force_majeure", "notice"):
        if candidate in options:
            return candidate
    return "end"


def draft_edit_box(entry_id):
    """The whole clause as one text, one sentence per line, with Save and Cancel (used for a proposed and for an applied clause)."""
    st.caption("Edit anywhere in the text. Each line becomes its own numbered sentence in the contract: press Enter "
               "to start a new one, and clear a line to remove it. The contract changes only when you press Save.")
    ek = drafts.edit_key(entry_id)
    if ek not in st.session_state:                          # drawn for the first time, or again after another step
        st.session_state[ek] = drafts.working_text(entry_id)
    lines = st.session_state[ek].splitlines() or [""]
    height = min(600, max(160, 30 * sum(len(line) // 90 + 1 for line in lines) + 40))
    drafts.set_working(entry_id, st.text_area("Clause wording", key=ek, height=height))       # survives a trip to another step
    c1, c2, _ = st.columns([1, 1, 8])
    c1.button("Save", type="primary", on_click=drafts.save_edit, args=(entry_id,), key=widget_key("save_edit", str(entry_id)))
    c2.button("Cancel", on_click=drafts.cancel_edit, args=(entry_id,), key=widget_key("cancel_edit", str(entry_id)))


def render_draft(entry_id, drafted, clauses, msg, text):
    """The draft, shown inside its request's box. Edit and Reject sit side by side under the wording; while editing,
    Save and Cancel take their place."""
    st.markdown(f"**Proposed new clause: {plain(drafted.title)}**")
    if not drafted.selection.found:
        st.warning("No reference in the library for this request. The AI wrote the clause itself; "
                   "review it carefully.")
    if drafts.is_editing(entry_id):
        draft_edit_box(entry_id)
    else:
        sentences = drafts.sentences_of(entry_id, drafted)
        if sentences:
            st.write("\n\n".join(plain(s) for s in sentences))
        else:
            st.warning("Every sentence is cleared, so this clause is left out of the contract.")
        c0, c1, c2, _ = st.columns([2, 1, 1, 4])
        c0.button("Apply", type="primary", on_click=apply_draft, args=(entry_id, text), disabled=not sentences,
                  key=widget_key("apply_draft", str(entry_id)))
        c1.button("Edit", on_click=drafts.start_edit, args=(entry_id, drafted), key=widget_key("edit_draft", str(entry_id)))
        c2.button("Reject", on_click=reject_request, args=(msg, entry_id, text), key=widget_key("reject_request", str(entry_id)))
    if drafted.references_line():
        st.caption(plain(drafted.references_line()))
    if drafted.selection.picks:
        with st.expander("Why these references"):
            refs = get_references()
            for p in drafted.selection.used:
                st.caption(plain(f"Used: {refs[p.ref_id].label}. {p.reason}"))
            for p in drafted.selection.related:
                st.caption(plain(f"Not used, related but a different subject: {refs[p.ref_id].label}. {p.reason}"))
    if drafted.notes:
        with st.expander("Points to decide or check"):
            show_lines(f"- {n}" for n in drafted.notes)
    titles = {c.key: c.title for c in clauses.values() if c.included}
    options = list(titles) + ["end"]
    pk = drafts.placement_key(entry_id)
    if st.session_state.get(pk) not in options:        # the widget was dropped when the user left this step, or its clause was unticked
        wanted = drafts.placement_of(entry_id, drafted)
        st.session_state[pk] = wanted if wanted in options else drafts_default(options)
    placement = st.selectbox("Place this clause before", options, key=pk,
                             format_func=lambda k: "At the end" if k == "end" else titles[k])
    if drafted.placement_reason:
        st.caption(plain(f"Suggestion: {drafted.placement_reason}"))
    drafts.remember(entry_id, placement)


def display_text(result, latest):
    """The short line shown in the chat for a reply. The details are shown once, in the results panel, so older
    replies do not repeat them."""
    changes = len(result.clause_actions) + len(result.deviations)
    new = len([u for u in result.unmapped_requests if not u.candidate_key])
    questions = len(result.ambiguities) + len([u for u in result.unmapped_requests if u.candidate_key])
    parts = []
    if changes:
        parts.append(f"{changes} proposed change{'s' if changes != 1 else ''}")
    if result.suggestions:
        parts.append(f"{len(result.suggestions)} suggestion{'s' if len(result.suggestions) != 1 else ''}")
    if new:
        parts.append(f"{new} new clause request{'s' if new != 1 else ''}")
    if questions:
        parts.append(f"{questions} question{'s' if questions != 1 else ''} for you")
    if not parts:
        return "I found no changes to the standard contract."
    return ("I found " if latest else "Earlier reply: ") + ", ".join(parts) + (". The details are below." if latest else ".")


def reject_proposal(msg, key, label, number):
    """Reject button callback: the proposal is dismissed (the list says "Request N rejected") and the model is told on the next analysis."""
    msg.setdefault("rejected", {})[key] = label
    msg.setdefault("rejected_numbers", {})[key] = number


def undo_reject(msg, key):
    """Undo button of a rejection: the proposal is back, and the model is no longer told it was rejected. A rejected
    request comes back with its draft, its saved wording, its position and its number."""
    msg.get("rejected", {}).pop(key, None)
    msg.get("rejected_numbers", {}).pop(key, None)
    snap = msg.get("rejected_requests", {}).pop(key, None)
    if snap:
        entries = st.session_state.setdefault(REQUESTS_KEY, [])
        if not any(e["id"] == snap["entry"]["id"] for e in entries):
            entries.append(dict(snap["entry"]))
        drafts.restore(snap["entry"]["id"], snap["snapshot"])


def content_for_model(msg):
    """What the model reads for a message. A reply's rejections and what was applied are added, so that it does not propose them again."""
    lines = [msg["content"]]
    lines += [f"The user rejected: {label}." for label in (msg.get("rejected") or {}).values()]
    for e in [e for e in msg.get("applied_entries") or [] if still_applied(e)]:
        what = (e["heading"] if e["kind"] in ("clause", "new_clause")
                else f"wording change in {e['heading']}: {e['requested_change']}")
        lines.append(f"Applied to the draft: {what} (the user's words: \u201c{e['evidence']}\u201d). This request is done. "
                     "Any other request in the same message is not done by it.")
    return "\n".join(lines)


def applied_clause_notes():
    """The clauses the AI drafted that the user applied, as the lines the model reads: they belong to no reply, so they are given once."""
    return [f"Applied to the draft: {e['heading']} (the user's words: \u201c{e['evidence']}\u201d). This request is done."
            for e in applied_entries_now() if e["kind"] == "new_clause"]


def applied_entries_now():
    """What was applied in this run and is still in the draft (see core.interpret settle)."""
    failed = failed_edit_ids()
    return [e for batch in st.session_state.get(APPLIED_KEY, []) for e in batch["entries"] if still_applied(e, failed)]


def titles_now():
    titles = {c.key: c.title for c in build_library()}
    titles.update({d["key"]: d["title"] for d in drafts.drafted_for_library()})
    return titles


def apply_action(msg, a):
    """Apply button of a clause removal or addition: written into the draft's selection, and listed with what is applied."""
    titles = titles_now()
    previous = clause_sandbox.ensure_state(STATE_KEY).get(a.clause_key)
    clause_sandbox.set_clause(STATE_KEY, a.clause_key, a.action == "include")
    entry = {"kind": "clause", "key": a.clause_key, "action": a.action, "previous": previous, "number": action_number(a),
             "heading": f"{'Remove' if a.action == 'exclude' else 'Add'} clause: {titles[a.clause_key]}",
             "source": "You wrote" if a.basis == "comment" else "From the term sheet", "evidence": a.evidence, "reason": a.reason}
    log_applied([entry])
    msg.setdefault("applied_entries", []).append(entry)


def apply_deviation(msg, d):
    """Apply button of a wording change: the wording as the user left it (saved) is written into the draft. When it cannot be written
    the reason is shown in its box and nothing changes."""
    key = deviation_key(d)
    notes = msg.setdefault("item_notes", {})
    title = titles_now().get(d.clause_key, d.clause_key)
    text = current_text(d)
    removing = d.removes and not text
    drafted_id = int(d.clause_key.split("_", 1)[1]) if d.clause_key.startswith("drafted_") else None
    saved_before = st.session_state.get(drafts.SAVED_STORE, {}).get(drafted_id) if drafted_id is not None else None
    saved_before = list(saved_before) if saved_before is not None else None
    if not applicable(d):
        notes[key] = "I could not tell which sentence it changes."
    elif not removing and (not text or (d.change_type != "add" and text.lower() == wording.norm(d.old_text).lower())):
        notes[key] = "The wording was not changed: press Edit to write the new wording, then Apply."
    elif not write_wording_change(d, text, removing):
        notes[key] = "That sentence is no longer in the clause: it changed after another request was applied."
    else:
        notes.pop(key, None)
        entry = {"kind": "wording", "key": d.clause_key, "heading": f"{title}: {d.summary}", "requested_change": d.requested_change,
                 "number": deviation_number(d), "evidence": d.evidence, "quote": d.provision_quote, "change_type": d.change_type, "old": d.old_text,
                 "new": "" if removing else text, "removed": removing, "drafted_id": drafted_id, "saved_before": saved_before,
                 "edit_id": None if drafted_id is not None else widget_key("edit", d.clause_key, "remove" if removing else d.change_type, d.old_text, text)}
        log_applied([entry])
        msg.setdefault("applied_entries", []).append(entry)
        st.session_state[DEVIATIONS_KEY] = list(st.session_state.get(DEVIATIONS_KEY) or []) + [d]


def apply_all(msg):
    """Apply all button: every open request that needs no care is applied, in the order of its number. A request with a warning, one that
    takes a whole point out, or one whose quote was not found, is left for the user's own Apply."""
    actions, deviations = open_items(msg)
    todo = [(action_number(a), "a", a) for a in actions if a.evidence_verified] + [(deviation_number(d), "d", d) for d in deviations if default_tick(d)]
    for _, kind, item in sorted(todo, key=lambda x: x[0]):
        (apply_action if kind == "a" else apply_deviation)(msg, item)


def log_applied(entries):
    """Records what was applied, each change with its own uid (its Undo button), as one batch of the log."""
    log = st.session_state.setdefault(APPLIED_KEY, [])
    batch = {"id": max((b["id"] for b in log), default=0) + 1, "entries": entries}
    log.append(batch)
    for n, e in enumerate(entries):
        e["uid"] = f"{batch['id']}-{n}"


def apply_draft(entry_id, text):
    """Apply button of a clause the AI drafted: it goes into the contract, at the position chosen, and is listed with the applied changes."""
    drafted = st.session_state.get(DRAFTS_KEY, {}).get(entry_id)
    if drafted is None or not drafts.sentences_of(entry_id, drafted) or drafts.is_kept(entry_id):
        return
    drafts.apply(entry_id)
    request = next((e for e in st.session_state.get(REQUESTS_KEY, []) if e["id"] == entry_id), {})
    log_applied([{"kind": "new_clause", "key": f"drafted_{entry_id}", "drafted_id": entry_id, "number": entry_id,
                  "heading": f"New clause: {drafted.title}", "title": drafted.title, "requested_change": text,
                  "evidence": request.get("evidence") or text}])


def revert_entry(e):
    """Takes one applied change out of the draft again, and nothing else."""
    if e["kind"] == "new_clause":
        drafts.unapply(e["drafted_id"])
    elif e["kind"] == "clause":
        if e["previous"] is not None:
            clause_sandbox.set_clause(STATE_KEY, e["key"], e["previous"])
    elif e["edit_id"]:
        wording_state.remove_edit(e["edit_id"])
    else:                                                          # a clause the AI drafted: its saved wording as it was before
        store = st.session_state.setdefault(drafts.SAVED_STORE, {})
        if e["saved_before"] is None:
            store.pop(e["drafted_id"], None)
        else:
            store[e["drafted_id"]] = list(e["saved_before"])


def undo_entry(uid):
    """Undo button of an applied change: that change is taken out of the draft and its box leaves the list. What was applied before or
    after it, and anything the user did by hand, stays. The request is a proposal again, with its own Apply."""
    log = st.session_state.get(APPLIED_KEY, [])
    chat = st.session_state.get("chat") or []
    st.session_state.pop(UNDO_NOTE_KEY, None)
    for batch in log:
        entry = next((e for e in batch["entries"] if e["uid"] == uid), None)
        if entry is None:
            continue
        failing_before = failed_edit_ids()
        revert_entry(entry)
        batch["entries"].remove(entry)
        # a change that edited the very sentence this one wrote cannot stay without it: it is taken out too, and the user is told
        gone = []
        for other in log:
            for e in list(other["entries"]):
                if e["kind"] == "wording" and e["edit_id"] and e["edit_id"] in failed_edit_ids() - failing_before:
                    revert_entry(e)
                    other["entries"].remove(e)
                    gone.append(e["heading"])
        if gone:
            st.session_state[UNDO_NOTE_KEY] = ("Also taken out, because it changed the same sentence after it: " + "; ".join(gone) + ".")
    st.session_state[APPLIED_KEY] = [b for b in log if b["entries"]]


def write_wording_change(d, text, removing=False):
    """Writes one accepted wording change into the draft: a template clause through the recorded changes, a clause the user
    had drafted through its own saved wording. `text` is the new wording as the user left it. False when the sentence is not
    there any more."""
    if d.clause_key.startswith("drafted_"):
        entry_id = int(d.clause_key.split("_", 1)[1])
        drafted = st.session_state.get(DRAFTS_KEY, {}).get(entry_id)
        if drafted is None:
            return False
        return drafts.reword(entry_id, drafted, "remove" if removing else d.change_type, d.old_text, text)
    kind = "remove" if removing else d.change_type
    wording_state.add_edit({"id": widget_key("edit", d.clause_key, kind, d.old_text, text),
                            "clause_key": d.clause_key, "change_type": kind, "old": d.old_text, "new": "" if removing else text, "summary": d.summary})
    return True


def all_rejections():
    """[(number, label, key, msg)] for every rejected request of every reply, in the order of their numbers."""
    out = []
    for m in st.session_state.get("chat") or []:
        for key, label in (m.get("rejected") or {}).items():
            n = (m.get("rejected_numbers") or {}).get(key)
            if n is not None:
                out.append((n, label, key, m))
    return sorted(out, key=lambda x: x[0])


def open_items(msg, result=None):
    """(clause actions, wording changes) of the reply that are neither rejected nor applied: they are the ones still waiting for the user."""
    result = result or msg["result"]
    rejected = {key for _, _, key, _ in all_rejections()}
    applied = {e["number"] for e in applied_entries_now()}
    return ([a for a in result.clause_actions if action_key(a) not in rejected and action_number(a) not in applied],
            [d for d in result.deviations if deviation_key(d) not in rejected and deviation_number(d) not in applied])


def pending_deviations(chat):
    """The wording changes the latest reply proposed that the user has neither applied nor rejected, so the next analysis
    keeps them (see ai.interpret.settle)."""
    for m in reversed(chat):
        if m["role"] == "assistant" and "result" in m:
            return open_items(m)[1]
    return []


def clause_preview(clauses, key, removing):
    label = "Text that will be removed" if removing else "Text that will be added"
    with st.expander(label):
        c = clauses[key]

        def show(text, caption=False):
            (st.caption if caption else st.markdown)(plain(text))

        for p in c.plain_paragraphs:
            show(p)
        for item in c.items:
            show(item.text)
            for sub in item.lettered:
                show(sub, caption=True)


def render_deviation(d, lookup, msg, stale=False):
    """One wording change in its own box: the current and the new wording, advice from the checks, and Edit and Reject side by
    side (Save and Cancel while the wording is open for editing), like the clauses the AI drafted."""
    key = deviation_key(d)
    title = lookup[d.clause_key].title
    label = f"Wording change: {title}: {d.summary}"
    editing = applicable(d) and wording_state.is_editing(key)
    with st.container(border=True):
        st.markdown(f"#### Request {deviation_number(d)}: {plain(title)}: {plain(d.summary)}")
        if d.carried:
            st.caption("Kept from your earlier message: not applied or rejected yet.")
        st.write(f"Wording change: {plain(d.requested_change)}")
        if not applicable(d):
            st.warning("I could not tell which single sentence this change applies to, so it cannot be written into the "
                       "text. You can change the Word file after downloading.")
            st.caption(f"Current wording: \u201c{plain(d.provision_quote)}\u201d")
        elif editing:
            st.caption("Edit the wording. The contract changes only with what you save and then apply: press Save to keep "
                       "your changes.")
            ek = newtext_key(d)
            if ek not in st.session_state:                  # drawn for the first time, or again after another step
                st.session_state[ek] = wording_state.working(key, current_text(d))
            lines = st.session_state[ek].splitlines() or [""]
            height = min(500, max(120, 30 * sum(len(line) // 90 + 1 for line in lines) + 40))
            wording_state.set_working(key, st.text_area("New wording", key=ek, height=height))
            c1, c2, _ = st.columns([1, 1, 8])
            c1.button("Save", type="primary", on_click=save_wording, args=(key, ek), key=widget_key("save_wording", key))
            c2.button("Cancel", on_click=cancel_wording, args=(key, ek), key=widget_key("cancel_wording", key))
        else:
            text = current_text(d)
            if d.change_type == "add":
                st.caption("A new sentence at the end of this clause")
                st.markdown(plain(text) if text else "_(nothing yet)_")
            elif d.removes and not text:
                before, _ = wording.diff_markup(d.old_text, "")
                st.caption("Current wording")
                st.markdown(before)
                st.caption("New wording")
                st.markdown("_Taken out of the clause._")
            else:
                before, after = wording.diff_markup(d.old_text, text)
                st.caption("Current wording")
                st.markdown(before)
                st.caption("New wording")
                st.markdown(after)
            if d.written_by == "figure":
                st.caption("The AI's wording could not be used, so the new figure was written into the sentence directly, "
                           "with its words made from the number.")
            elif d.written_by == "fragment":
                st.caption("The AI rewrote only part of the sentence; the rest of it is kept exactly as it was.")
            problem = checked_problem(d, text)
            if problem:
                st.warning(f"Check before you apply: {problem} You can still apply it, or press Edit to change the wording first.")
        st.caption(f"You wrote: \u201c{plain(d.evidence)}\u201d")
        if not d.evidence_verified:
            st.warning("This quote was not found in your messages. Check it before applying.")
        note = (msg.get("item_notes") or {}).get(key)
        if note:
            st.warning(note)
        if not editing:
            c0, c1, c2, _ = st.columns([1, 1, 1, 5])
            c0.button("Apply", type="primary", on_click=apply_deviation, args=(msg, d), disabled=stale or not applicable(d),
                      key=widget_key("apply_dev", key))
            c1.button("Edit", on_click=start_wording_edit, args=(d,), disabled=not applicable(d), key=widget_key("edit_wording", key))
            c2.button("Reject", on_click=reject_proposal, args=(msg, key, label, deviation_number(d)), key=widget_key("reject", key))


def failed_edit_ids():
    """The recorded wording changes whose sentence is no longer in their clause: they are not in the draft."""
    failed = []
    library_for(clause_sandbox.ensure_state(STATE_KEY), clause_sandbox.current_limits(), drafts.drafted_for_library(),
                clause_sandbox.current_term_sheet(), wording_state.applied(), failed)
    return {f["id"] for f in failed}


def still_applied(e, failed=None):
    """True while what an Apply wrote is still in the draft (the user may have ticked the clause again by hand, or the sentence
    may have changed since)."""
    if e["kind"] == "new_clause":
        return drafts.is_kept(e["drafted_id"]) and e["drafted_id"] in st.session_state.get(DRAFTS_KEY, {})
    if e["kind"] == "clause":
        return clause_sandbox.ensure_state(STATE_KEY).get(e["key"]) == (e["action"] == "include")
    if e["edit_id"] is None:                                              # a clause the AI drafted: its own saved wording
        entry_id = int(e["key"].split("_", 1)[1])
        drafted = st.session_state.get(DRAFTS_KEY, {}).get(entry_id)
        if drafted is None:
            return False
        sentences = {wording.norm(s).lower() for s in drafts.sentences_of(entry_id, drafted)}
        return (wording.norm(e["old"]).lower() not in sentences) if e["removed"] else (wording.norm(e["new"]).lower() in sentences)
    failed = failed_edit_ids() if failed is None else failed
    return e["edit_id"] not in failed and any(x["id"] == e["edit_id"] for x in wording_state.applied())


def render_applied_body(e):
    """What was applied, as it was proposed, with its Undo: the inside of the dropdown of an applied request."""
    if e["kind"] == "new_clause":
        drafted = st.session_state.get(DRAFTS_KEY, {}).get(e["drafted_id"])
        if drafts.is_editing(e["drafted_id"]):
            draft_edit_box(e["drafted_id"])
            return
        sentences = drafts.sentences_of(e["drafted_id"], drafted)
        if sentences:
            st.write("\n\n".join(plain(x) for x in sentences))
        else:
            st.warning("Every sentence is cleared, so this clause is left out of the contract.")
        where = drafts.placement_of(e["drafted_id"], drafted)
        titles = {c.key: c.title for c in build_library()}
        st.caption("At the end of the contract" if where == "end" else f"Placed before: {titles.get(where, where)}")
        st.caption(f"You wrote: \u201c{plain(e['evidence'])}\u201d")
        c1, c2, _ = st.columns([1, 1, 8])
        c1.button("Edit", on_click=drafts.start_edit, args=(e["drafted_id"], drafted), key=widget_key("edit_draft", str(e["drafted_id"])))
        c2.button("Undo", on_click=undo_entry, args=(e["uid"],), key=widget_key("undo_entry", e["uid"]))
        return
    if e["kind"] == "clause":
        st.caption(f"{e['source']}: \u201c{plain(e['evidence'])}\u201d")
        if e["reason"].strip() and e["reason"].strip().lower() != e["evidence"].strip().lower():
            st.write(plain(e["reason"]))
        st.button("Undo", on_click=undo_entry, args=(e["uid"],), key=widget_key("undo_entry", e["uid"]))
        return
    st.write(f"Wording change: {plain(e['requested_change'])}")
    if e["change_type"] == "add":
        st.caption("A new sentence at the end of this clause")
        st.markdown(plain(e["new"]))
    else:
        before, after = wording.diff_markup(e["old"], e["new"])
        st.caption("Current wording")
        st.markdown(before)
        st.caption("New wording")
        st.markdown("_Taken out of the clause._" if e["removed"] else after)
    st.caption(f"You wrote: \u201c{plain(e['evidence'])}\u201d")
    st.button("Undo", on_click=undo_entry, args=(e["uid"],), key=widget_key("undo_entry", e["uid"]))


def render_action_box(a, lookup, clauses, msg, stale):
    """A proposal to take a clause out or put it back: Apply and Reject (Edit is there too, and cannot be pressed: there is nothing to edit)."""
    with st.container(border=True):
        verb = "Remove" if a.action == "exclude" else "Add"
        label = f"{verb} clause: {lookup[a.clause_key].title}"
        st.markdown(f"#### Request {action_number(a)}: {plain(label)}")
        source = "You wrote" if a.basis == "comment" else "From the term sheet"
        st.caption(f"{source}: \u201c{plain(a.evidence)}\u201d")
        if a.reason.strip() and a.reason.strip().lower() != a.evidence.strip().lower():
            st.caption(f"Why: {plain(a.reason)}")
        clause_preview(clauses, a.clause_key, removing=a.action == "exclude")
        if not a.evidence_verified:
            st.warning("This quote was not found in your messages. Check it before applying.")
        c0, c1, c2, _ = st.columns([1, 1, 1, 5])
        c0.button("Apply", type="primary", on_click=apply_action, args=(msg, a), disabled=stale, key=widget_key("apply_act", action_key(a)))
        c1.button("Edit", disabled=True, key=widget_key("edit_act", action_key(a)))
        c2.button("Reject", on_click=reject_proposal, args=(msg, action_key(a), label, action_number(a)), key=widget_key("reject", action_key(a)))


def render_request_box(entry_id, text, clauses, msg, out):
    """A request for a new clause: first Find references and draft, then the draft with Apply, Edit and Reject."""
    stored = st.session_state.get(DRAFTS_KEY, {})
    with st.container(border=True):
        st.markdown(f"#### Request {entry_id}: {plain(text)}")
        if entry_id in stored:
            render_draft(entry_id, stored[entry_id], clauses, msg, text)
        else:
            st.caption("The library has no matching clause. I can look for references and draft one.")
            find, reject, _ = st.columns([3, 1, 4])
            if find.button("Find references and draft this clause", key=widget_key("draft", str(entry_id))):
                out["draft_request"] = (entry_id, text)
            reject.button("Reject", on_click=reject_request, args=(msg, entry_id, text), key=widget_key("reject_request", str(entry_id)))


def render_results(msg, clauses, turn, stale, all_clauses=None):
    """The one list of requests, in the order of their numbers: a proposal has Apply, Edit and Reject; an applied request is a dropdown
    with its Undo; a rejected request is one line ("Request 2 rejected") that stays where it was, so nothing is renumbered. Then the
    questions and the suggestions. `msg` is the latest reply (None when there is none). Returns (quick_reply, draft_request) when a
    Yes/No or draft button was pressed."""
    lookup = all_clauses or clauses
    out = {"quick_reply": None, "draft_request": None}
    result = forget_unknown_clauses(msg["result"], list(lookup.values())) if msg is not None else None
    proposals, questions, _ = result_lines(result, list(lookup.values())) if result is not None else ([], [], [])
    rejections = all_rejections()
    requests = new_clause_requests(result, {key: label for _, label, key, _ in rejections}) if result is not None else []
    open_actions, open_deviations = open_items(msg, result) if result is not None else ([], [])
    failed = failed_edit_ids()
    applied = [e for batch in st.session_state.get(APPLIED_KEY, []) for e in batch["entries"] if still_applied(e, failed)]
    suggestions = [s for s in (result.suggestions if result is not None else []) if not lookup[s.clause_key].included]   # gone once the clause is ticked

    items = []
    for a in open_actions:
        items.append((action_number(a), lambda a=a: render_action_box(a, lookup, clauses, msg, stale)))
    for d in open_deviations:
        items.append((deviation_number(d), lambda d=d: render_deviation(d, lookup, msg, stale)))
    for entry_id, text in requests:
        items.append((entry_id, lambda i=entry_id, t=text: render_request_box(i, t, clauses, msg, out)))
    for e in applied:
        def show_applied(e=e):
            with st.expander(f"Request {e['number']}: {e['heading']} (applied)"):
                render_applied_body(e)
        items.append((e["number"], show_applied))
    for n, label, key, owner in rejections:
        def show_rejected(n=n, key=key, owner=owner):
            c1, c2 = st.columns([8, 1])
            c1.write(f"Request {n} rejected.")
            c2.button("Undo", on_click=undo_reject, args=(owner, key), key=widget_key("undo_reject", key))
        items.append((n, show_rejected))

    if not (items or questions or suggestions):
        if msg is not None:
            st.subheader("What I found")
            st.write("No changes to the standard contract.")
        return None, None
    st.subheader("What I found")
    note = st.session_state.pop(UNDO_NOTE_KEY, None)
    if note:
        st.info(note)
    for _, show in sorted(items, key=lambda x: x[0]):
        show()
    if open_actions or open_deviations:
        ready = any(a.evidence_verified for a in open_actions) or any(default_tick(d) for d in open_deviations)
        st.button("Apply all", type="primary", on_click=apply_all, args=(msg,), disabled=stale or not ready, key=widget_key("apply_all", str(turn)))
        st.caption("Apply all leaves out a request that has a warning or takes a whole point out: apply those yourself, one by one.")

    if questions:
        st.markdown("**Questions**")
        for q in result.ambiguities:
            with st.container(border=True):
                st.write(plain(q))
        for i, u in enumerate(u for u in result.unmapped_requests if u.candidate_key):
            title = lookup[u.candidate_key].title             # the candidate may be a clause drafted in this session
            said = u.evidence or u.request
            with st.container(border=True):
                st.write(plain(candidate_question(u, title)))
                c1, c2, _ = st.columns([2, 2, 3])
                if c1.button("Yes, that's what I meant", key=widget_key("yes", str(turn), str(i))):
                    out["quick_reply"] = f"Yes, by \u201c{said}\u201d I meant the '{title}' clause."
                    st.session_state[DECLINED_KEY] = [x for x in st.session_state.get(DECLINED_KEY, [])
                                                      if not (x["key"] == u.candidate_key and x["evidence"] == said)]
                if c2.button("No, something else", key=widget_key("no", str(turn), str(i))):
                    out["quick_reply"] = f"No, by \u201c{said}\u201d I did not mean the '{title}' clause."
                    st.session_state.setdefault(DECLINED_KEY, []).append({"key": u.candidate_key, "evidence": said})

    if suggestions:
        st.markdown("**Suggestions**")
        for s_ in suggestions:
            st.info(f"Suggestion: add {plain(lookup[s_.clause_key].title)}. {plain(s_.reason)} "
                    "Tick it under Optional clauses if you want it in the draft.")

    return out["quick_reply"], out["draft_request"]


def render():
    st.markdown(CHAT_CSS, unsafe_allow_html=True)
    st.caption("Choose which clauses are in the draft. Tick them yourself, or tell the assistant what "
               "you want changed and apply what it proposes.")

    ts = st.session_state.get("term_sheet")
    missing = missing_required(ts)
    if missing:
        st.warning("Complete the required term sheet fields first.")
        st.button("Back to term sheet", on_click=flow.go_back)
        return

    clause_sandbox.show_vat_notice()

    client = get_client(st.session_state.get("openai_api_key"))

    if st.sidebar.button("Clear conversation"):
        st.session_state.pop("chat", None)
        st.session_state.pop(AUTO_KEY, None)
        st.session_state.pop(DECLINED_KEY, None)
        st.rerun()

    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    chat = st.session_state.setdefault("chat", [])
    included = clause_sandbox.ensure_state(STATE_KEY)
    limits = clause_sandbox.current_limits()
    edits, failed = wording_state.applied(), []
    clauses = {c.key: c for c in library_for(included, limits, None, ts, edits, failed)}
    interpret_library = library_for(included, limits, drafts.drafted_for_library(), ts, edits)
    all_clauses = {c.key: c for c in interpret_library}
    if failed:
        st.warning("These wording changes could not be applied now, because the sentence they change is no longer in the clause: "
                   + "; ".join(plain(e["summary"]) for e in failed))

    with st.expander("Clauses in the draft", expanded=True):
        clause_sandbox.render_picker(STATE_KEY)

    with st.expander("Clause preview", expanded=True):
        clause_sandbox.render_preview(STATE_KEY, noun="draft", download=False)

    st.subheader("Ask for changes")
    last_idx = max((i for i, m in enumerate(chat) if m["role"] == "assistant"), default=None)
    latest = chat[last_idx] if last_idx is not None else None
    stale = latest is not None and latest["snapshot"] != term_sheet_text(ts)
    if stale:
        st.warning("The term sheet changed after the latest reply. Send a message to analyse again "
                   "before applying.")

    conditions = conditions_of(ts)
    snapshot = term_sheet_text(ts)
    # With additional conditions in the term sheet the first analysis has real work and starts by itself, once for this term sheet.
    auto = bool(conditions) and not chat and not has_analysis() and client is not None and st.session_state.get(AUTO_KEY) != snapshot
    if auto:
        st.session_state[AUTO_KEY] = snapshot
    skip = auto
    if not chat:
        with st.chat_message("assistant"):
            if conditions:
                names = ", ".join(plain(label) for key, label in CONDITION_CLAUSES if key in conditions)
                st.write(f"The term sheet has additional conditions for {len(conditions)} clause"
                         f"{'s' if len(conditions) != 1 else ''} ({names}). I read them as requests: the proposals are below. "
                         "You can ask for more changes in the chat, for example: "
                         "\u201cclient wants to drop the construction timeline\u201d.")
                if client is not None and not auto:
                    skip = st.button("Read the additional conditions again")
            else:
                st.write("What would you like to change from the standard contract? For example: "
                         "\u201cclient wants to drop the construction timeline\u201d. I also check the term "
                         "sheet itself, for example whether the roof owner is a different party from the Owner.")
                skip = st.button(NO_REQUEST_BUTTON, disabled=client is None)
                st.caption(NO_REQUEST_NOTE)

    quick_reply = draft_request = None
    for i, msg in enumerate(chat):
        if msg["role"] == "user":
            show_user_message(msg["content"])
            continue
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and "result" in msg:
                show_lines([display_text(msg["result"], latest=i == last_idx)])
                if i == last_idx:                       # the proposals and their buttons sit under what the assistant wrote
                    quick_reply, draft_request = render_results(latest, clauses, len(chat), stale, all_clauses)
            else:
                show_lines(msg["content"].split("\n"))
    if latest is None:
        quick_reply, draft_request = render_results(latest, clauses, len(chat), stale, all_clauses)

    if client is not None and draft_request:
        entry_id, request_text = draft_request
        with st.chat_message("assistant"):
            with st.spinner("Finding references and drafting..."):
                error = None
                try:
                    refs = get_references()
                    selection = select_references(request_text, refs,
                                                  CountingClient(client, calls, "select_references"), MODEL)
                    order = [(c.key, c.title) for c in clauses.values() if c.included]
                    hint = placement_from_references([refs[i] for i in selection.ids()],
                                                     [(c.key, c.title, c.included) for c in clauses.values()])
                    drafted = draft_clause(request_text, selection, refs,
                                           CountingClient(client, calls, "draft_clause"), MODEL, order, hint)
                except (AIStepError, FileNotFoundError) as e:
                    error = str(e)
                except Exception as e:
                    error = f"The API call failed: {e}"
            if error:
                st.error(error)
            else:
                st.session_state.setdefault(DRAFTS_KEY, {})[entry_id] = drafted
                st.rerun()

    if client is None:
        st.info("Enter an OpenAI API key in the sidebar to start.")
    prompt = st.chat_input("Describe a change, or answer a question above...", disabled=client is None)
    text = (prompt or quick_reply or "").strip()

    if client is not None and (text or skip):
        if text:
            chat.append({"role": "user", "content": text})
            show_user_message(text)
        with st.chat_message("assistant"):
            with st.spinner("Reading the additional conditions..." if auto else "Thinking..."):
                error = None
                try:
                    result = interpret_request(
                        ts, interpret_library, CountingClient(client, calls, STEP_NAME), MODEL,
                        ([{"role": "assistant", "content": "\n".join(applied_clause_notes())}] if applied_clause_notes() else [])
                        + [{"role": m["role"], "content": content_for_model(m)} for m in chat],
                        pending_deviations(chat[:-1] if text else chat), wording_state.applied(), applied_entries_now(),
                        st.session_state.get(DECLINED_KEY, []))
                except InterpretationError as e:
                    error = str(e)
                except Exception as e:
                    error = f"The API call failed: {e}"
            if error:
                if text:
                    chat.pop()
                st.error(f"{error} Your message was not sent; please try again.")
            else:
                chat.append({"role": "assistant", "content": context_summary(result, list(all_clauses.values())),
                             "result": result, "snapshot": term_sheet_text(ts)})
                st.rerun()

    st.divider()
    if latest is not None and any(open_items(latest)):
        st.caption("Some requests above have not been applied yet. Apply them, or continue without them.")
    if not has_analysis():
        st.caption("Run the analysis once to continue: send a message, or press "
                   "\u201cNo special requests\u201d." if not conditions else
                   "The analysis of the additional conditions has not run yet. Enter an API key, or press \u201cRead the additional "
                   "conditions again\u201d.")
    st.button("Continue \u2192", type="primary", on_click=flow.go_next, disabled=not has_analysis())
