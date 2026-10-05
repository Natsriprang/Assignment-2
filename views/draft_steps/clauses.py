"""Step 2: choose the clauses. The checkboxes are the one place that decides which clauses are in
the draft. The chat proposes changes (add or remove a clause, reword a provision) and asks when
something is unclear; ticked proposals are written into the checkboxes by the Apply button, and
the user can keep adjusting by hand. At least one analysis must run before the user continues."""
import difflib
import hashlib
import re

import streamlit as st

from ai.drafting import draft_clause
from ai.interpret import (InterpretationError, candidate_question, context_summary, interpret_request,
                          result_lines, term_sheet_text)
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.references import select_references
from core import wording
from core.clause_data import build_library
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
REQUESTS_KEY = "new_clause_requests"  # [{"id": int, "text": str}] in the order the requests were first raised
STEP_NAME = "interpret"


def plain(text):
    return re.sub(r"([\\`*_\[\]#>|~$<])", r"\\\1", text)


def widget_key(*parts):
    return "k_" + hashlib.md5("|".join(parts).encode()).hexdigest()[:10]


def action_key(a):
    return widget_key("act", a.clause_key, a.action)


def deviation_key(d):
    return widget_key("dev", d.clause_key, d.change_type, d.provision_quote, d.summary)


def show_lines(lines):
    for line in lines:
        st.write(plain(line))


def has_analysis():
    """True once the model has analysed the request at least once in this run."""
    return any(c["step"] == STEP_NAME for c in st.session_state.get(flow.CALLS_KEY, []))


@st.cache_resource
def get_references():
    return load_references()


def normalize(text):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def request_id(text):
    """A stable id for a request with no matching clause, so it keeps its place and its draft when the model
    words it slightly differently in a later reply."""
    entries = st.session_state.setdefault(REQUESTS_KEY, [])
    norm = normalize(text)
    for e in entries:
        if normalize(e["text"]) == norm:
            e["text"] = text
            return e["id"]
    for e in entries:
        if (difflib.SequenceMatcher(None, normalize(e["text"]), norm).ratio() >= 0.85
                and numbers_in(e["text"]) == numbers_in(text)):
            e["text"] = text
            return e["id"]
    seq = max([st.session_state.get(REQUEST_SEQ_KEY, 0)] + [e["id"] for e in entries]) + 1
    st.session_state[REQUEST_SEQ_KEY] = seq
    entries.append({"id": seq, "text": text})
    return seq


def request_reject_key(text):
    return f"request:{normalize(text)}"


def reject_request(msg, entry_id, text):
    """Reject button callback for a request: its draft and choices are dropped and the model is told on the next
    analysis. Its number is not reused."""
    msg.setdefault("rejected", {})[request_reject_key(text)] = f"New clause request: {text}"
    st.session_state[REQUESTS_KEY] = [e for e in st.session_state.get(REQUESTS_KEY, []) if e["id"] != entry_id]
    drafts.forget(entry_id)


def new_clause_requests(result, rejected=None):
    """[(id, text)] for the new-clause requests to show, in the order they were first raised: the ones in this
    result that match no clause, plus every request that already has a draft, so a draft never disappears when a
    later reply no longer lists its request."""
    found = {}
    for u in result.unmapped_requests:
        if not u.candidate_key and request_reject_key(u.request) not in (rejected or {}):
            found[request_id(u.request)] = u.request
    texts = {e["id"]: e["text"] for e in st.session_state.get(REQUESTS_KEY, [])}
    for entry_id, drafted in st.session_state.get(DRAFTS_KEY, {}).items():
        found.setdefault(entry_id, texts.get(entry_id, drafted.request))
    return sorted(found.items())


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


def render_draft(entry_id, drafted, clauses, msg, text):
    """The draft, shown inside its request's box. Edit and Reject sit side by side under the wording; while editing,
    Save and Cancel take their place."""
    st.markdown(f"**Proposed new clause: {plain(drafted.title)}**")
    if not drafted.selection.found:
        st.warning("No reference in the library for this request. The AI wrote the clause itself; "
                   "review it carefully.")
    if drafts.is_editing(entry_id):
        st.caption("Edit anywhere in the text. Each line becomes its own numbered sentence in the contract: press Enter "
                   "to start a new one, and clear a line to remove it. The contract changes only when you press Save.")
        ek = drafts.edit_key(entry_id)
        if ek not in st.session_state:                      # drawn for the first time, or again after another step
            st.session_state[ek] = drafts.working_text(entry_id)
        lines = st.session_state[ek].splitlines() or [""]
        height = min(600, max(160, 30 * sum(len(line) // 90 + 1 for line in lines) + 40))
        drafts.set_working(entry_id, st.text_area("Clause wording", key=ek, height=height))   # survives a trip to another step
        c1, c2, _ = st.columns([1, 1, 8])
        c1.button("Save", type="primary", on_click=drafts.save_edit, args=(entry_id,), key=widget_key("save_edit", str(entry_id)))
        c2.button("Cancel", on_click=drafts.cancel_edit, args=(entry_id,), key=widget_key("cancel_edit", str(entry_id)))
    else:
        sentences = drafts.sentences_of(entry_id, drafted)
        if sentences:
            st.write("\n\n".join(plain(s) for s in sentences))
        else:
            st.warning("Every sentence is cleared, so this clause is left out of the contract.")
        c1, c2, _ = st.columns([1, 1, 6])
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
    kept = st.checkbox("Keep this draft for the next step", value=drafts.is_kept(entry_id), key=drafts.keep_key(entry_id))
    drafts.remember(entry_id, kept, placement)


def display_text(result, latest):
    """The short line shown in the chat for a reply. The details are shown once, in the results panel, so older
    replies do not repeat them."""
    changes = len(result.clause_actions) + len(result.deviations)
    new = len([u for u in result.unmapped_requests if not u.candidate_key])
    questions = len(result.ambiguities) + len([u for u in result.unmapped_requests if u.candidate_key])
    parts = []
    if changes:
        parts.append(f"{changes} proposed change{'s' if changes != 1 else ''}")
    if new:
        parts.append(f"{new} new clause request{'s' if new != 1 else ''}")
    if questions:
        parts.append(f"{questions} question{'s' if questions != 1 else ''} for you")
    if not parts:
        return "I found no changes to the standard contract."
    return ("I found " if latest else "Earlier reply: ") + ", ".join(parts) + (". The details are below." if latest else ".")


def reject_proposal(msg, key, label):
    """Reject button callback: the proposal is dismissed for this reply and the model is told on the next analysis."""
    msg.setdefault("rejected", {})[key] = label


def content_for_model(msg):
    """What the model reads for a message. A reply's rejections are added so that it does not propose them again."""
    rejected = msg.get("rejected") or {}
    if not rejected:
        return msg["content"]
    return msg["content"] + "\n" + "\n".join(f"The user rejected: {label}." for label in rejected.values())


def apply_proposals(msg):
    """Apply button callback. Writes the ticked proposals into the draft's selection. Callbacks run
    before the page reruns, which is what allows this to change the checkboxes' state."""
    result = msg["result"]
    rejected = msg.get("rejected") or {}
    titles = {c.key: c.title for c in build_library()}
    titles.update({d["key"]: d["title"] for d in drafts.drafted_for_library()})
    applied = []
    for a in result.clause_actions:
        if action_key(a) not in rejected and st.session_state.get(action_key(a), a.evidence_verified):
            clause_sandbox.set_clause(STATE_KEY, a.clause_key, a.action == "include")
            verb = "Removed" if a.action == "exclude" else "Added"
            applied.append(f"{verb} clause: {titles[a.clause_key]}")
    deviations = [d for d in result.deviations if deviation_key(d) not in rejected]
    chosen = [d for d in deviations if d.new_text and st.session_state.get(deviation_key(d), d.evidence_verified)]
    st.session_state[DEVIATIONS_KEY] = chosen
    for d in deviations:
        title = titles.get(d.clause_key, d.clause_key)
        if not d.new_text:
            applied.append(f"Not applied: {title}: {d.summary} ({d.rewrite_problem})")
        elif d in chosen and write_wording_change(d):
            applied.append(f"Wording changed in {title}: {d.summary}")
        elif d in chosen:
            applied.append(f"Not applied: {title}: {d.summary} (that sentence is no longer in the clause)")
    msg["applied"] = applied


def write_wording_change(d):
    """Writes one accepted wording change into the draft: a template clause through the recorded changes, a clause the user
    had drafted through its own saved wording. False when the sentence is not there any more."""
    if d.clause_key.startswith("drafted_"):
        entry_id = int(d.clause_key.split("_", 1)[1])
        drafted = st.session_state.get(DRAFTS_KEY, {}).get(entry_id)
        return drafted is not None and drafts.reword(entry_id, drafted, d.change_type, d.old_text, d.new_text)
    wording_state.add_edit({"id": widget_key("edit", d.clause_key, d.change_type, d.old_text, d.new_text),
                            "clause_key": d.clause_key, "change_type": d.change_type, "old": d.old_text,
                            "new": d.new_text, "summary": d.summary})
    return True


def pending_deviations(chat):
    """The wording changes the latest reply proposed that the user has neither applied nor rejected, so the next analysis
    keeps them (see ai.interpret.settle)."""
    for m in reversed(chat):
        if m["role"] == "assistant" and "result" in m:
            if m.get("applied") is not None:
                return []
            rejected = m.get("rejected") or {}
            return [d for d in m["result"].deviations if deviation_key(d) not in rejected]
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


def render_results(msg, clauses, turn, stale, all_clauses=None):
    """The results for the latest reply. Every item sits in its own box; the new-clause requests are numbered
    in the order they were first raised. `all_clauses` also has the clauses drafted in this session, which a wording
    change may name. Returns (quick_reply, draft_request) when a Yes/No or draft button was pressed."""
    result = msg["result"]
    lookup = all_clauses or clauses
    proposals, questions, _ = result_lines(result, list(lookup.values()))
    rejected = msg.get("rejected") or {}
    requests = new_clause_requests(result, rejected)
    quick_reply, draft_request = None, None

    st.subheader("What I found")
    if not (proposals or questions or requests or rejected):
        st.write("No changes to the standard contract.")

    open_actions = [a for a in result.clause_actions if action_key(a) not in rejected]
    open_deviations = [d for d in result.deviations if deviation_key(d) not in rejected]

    if msg.get("applied") is not None:
        st.success("Applied to the draft.")
        show_lines(f"- {line}" for line in msg["applied"])
    elif open_actions or open_deviations:
        st.markdown("**Proposed changes**")
        for a in open_actions:
            with st.container(border=True):
                verb = "Remove" if a.action == "exclude" else "Add"
                label = f"{verb} clause: {clauses[a.clause_key].title}"
                st.markdown(f"#### {plain(label)}")
                source = "You wrote" if a.basis == "comment" else "From the term sheet"
                st.caption(f"{source}: \u201c{plain(a.evidence)}\u201d")
                if a.reason.strip() and a.reason.strip().lower() != a.evidence.strip().lower():
                    st.caption(f"Why: {plain(a.reason)}")
                clause_preview(clauses, a.clause_key, removing=a.action == "exclude")
                if not a.evidence_verified:
                    st.warning("This quote was not found in your messages. Check it before applying.")
                st.checkbox("Apply this change", value=a.evidence_verified, key=action_key(a))
                st.button("Reject", on_click=reject_proposal, args=(msg, action_key(a), label),
                          key=widget_key("reject", action_key(a)))

        for d in open_deviations:
            with st.container(border=True):
                title = lookup[d.clause_key].title
                label = f"Wording change: {title}: {d.summary}"
                st.markdown(f"#### {plain(title)}: {plain(d.summary)}")
                if d.carried:
                    st.caption("Kept from your earlier message: not applied or rejected yet.")
                st.write(f"Wording change: {plain(d.requested_change)}")
                if d.new_text and d.change_type == "add":
                    st.caption("A new sentence at the end of this clause:")
                    st.markdown(f"**{plain(d.new_text)}**")
                elif d.new_text:
                    before, after = wording.diff_markup(d.old_text, d.new_text)
                    st.caption("Current wording (struck through: taken out)")
                    st.markdown(before)
                    st.caption("New wording (bold: put in)")
                    st.markdown(after)
                else:
                    st.warning(f"I could not write this change into the text: {d.rewrite_problem} It will not be applied. "
                               "Rephrase the request, or change the Word file after downloading.")
                    if d.change_type != "add":
                        st.caption(f"Current wording: \u201c{plain(d.provision_quote)}\u201d")
                st.caption(f"You wrote: \u201c{plain(d.evidence)}\u201d")
                if not d.evidence_verified:
                    st.warning("This quote was not found in your messages. Check it before applying.")
                st.checkbox("Apply this change", value=d.evidence_verified and bool(d.new_text), key=deviation_key(d),
                            disabled=not d.new_text)
                st.button("Reject", on_click=reject_proposal, args=(msg, deviation_key(d), label),
                          key=widget_key("reject", deviation_key(d)))

        st.button("Apply selected changes", type="primary", on_click=apply_proposals, args=(msg,),
                  disabled=stale, key=widget_key("apply", str(turn)))
    if rejected:
        show_lines(f"Rejected: {label}" for label in rejected.values())

    stored = st.session_state.get(DRAFTS_KEY, {})
    for entry_id, text in requests:
        with st.container(border=True):
            st.markdown(f"#### Request {entry_id}: {plain(text)}")
            if entry_id in stored:
                render_draft(entry_id, stored[entry_id], clauses, msg, text)
            else:
                st.caption("The library has no matching clause. I can look for references and draft one.")
                find, reject, _ = st.columns([3, 1, 4])
                if find.button("Find references and draft this clause", key=widget_key("draft", str(entry_id))):
                    draft_request = (entry_id, text)
                reject.button("Reject", on_click=reject_request, args=(msg, entry_id, text),
                              key=widget_key("reject_request", str(entry_id)))

    if questions:
        st.markdown("**Questions**")
        for q in result.ambiguities:
            with st.container(border=True):
                st.write(plain(q))
        for i, u in enumerate(u for u in result.unmapped_requests if u.candidate_key):
            title = clauses[u.candidate_key].title
            said = u.evidence or u.request
            with st.container(border=True):
                st.write(plain(candidate_question(u, title)))
                c1, c2, _ = st.columns([2, 2, 3])
                if c1.button("Yes, that's what I meant", key=widget_key("yes", str(turn), str(i))):
                    quick_reply = f"Yes, by \u201c{said}\u201d I meant the '{title}' clause."
                if c2.button("No, something else", key=widget_key("no", str(turn), str(i))):
                    quick_reply = f"No, by \u201c{said}\u201d I did not mean the '{title}' clause."

    if result.notes:
        with st.expander("Automatic checks"):
            st.caption("Proposals the system discarded because they were invalid or changed nothing.")
            show_lines(f"- {n}" for n in result.notes)
    return quick_reply, draft_request


def render():
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

    skip = False
    if not chat:
        with st.chat_message("assistant"):
            st.write("What would you like to change from the standard contract? For example: "
                     "\u201cclient wants to drop the construction timeline\u201d. I also check the term "
                     "sheet itself, for example whether the roof owner is a different party from the Owner.")
            skip = st.button("No special requests \u2014 just check the term sheet", disabled=client is None)

    for i, msg in enumerate(chat):
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and "result" in msg:
                show_lines([display_text(msg["result"], latest=i == last_idx)])
            else:
                show_lines(msg["content"].split("\n"))

    quick_reply, draft_request = None, None
    if latest is not None:
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
            with st.chat_message("user"):
                show_lines(text.split("\n"))
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                error = None
                try:
                    result = interpret_request(
                        ts, interpret_library, CountingClient(client, calls, STEP_NAME), MODEL,
                        [{"role": m["role"], "content": content_for_model(m)} for m in chat],
                        pending_deviations(chat[:-1] if text else chat), wording_state.applied())
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
    if (latest is not None and latest.get("applied") is None
            and (latest["result"].clause_actions or latest["result"].deviations)):
        st.caption("Some proposals above have not been applied yet. Press \u201cApply selected "
                   "changes\u201d first, or continue without them.")
    if not has_analysis():
        st.caption("Run the analysis once to continue: send a message, or press "
                   "\u201cNo special requests\u201d.")
    st.button("Continue \u2192", type="primary", on_click=flow.go_next, disabled=not has_analysis())
