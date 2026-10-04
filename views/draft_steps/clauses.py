"""Step 2: choose the clauses. The checkboxes are the one place that decides which clauses are in
the draft. The chat proposes changes (add or remove a clause, reword a provision) and asks when
something is unclear; ticked proposals are written into the checkboxes by the Apply button, and
the user can keep adjusting by hand. At least one analysis must run before the user continues."""
import hashlib
import re

import streamlit as st

from ai.drafting import draft_clause, render_footnoted
from ai.interpret import (InterpretationError, candidate_question, context_summary, interpret_request,
                          result_lines, term_sheet_text, term_sheet_warnings)
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.references import select_references
from core.clause_data import build_library
from core.draft_state import library_for
from core.reference_library import load_references
from core.term_sheet_fields import REQUIRED_FIELDS
from views import clause_sandbox
from views.draft_steps import flow

STATE_KEY = "draft_included"
DEVIATIONS_KEY = "draft_deviations"
DRAFTS_KEY = "clause_drafts"          # request text -> DraftedClause
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


def kept_drafts():
    """Drafted new clauses the user chose to keep, for the next step to merge into the contract."""
    return [d for request, d in st.session_state.get(DRAFTS_KEY, {}).items()
            if st.session_state.get(widget_key("keep", request), True)]


def show_lines_caption(lines):
    for line in lines:
        st.caption(plain(line))


def render_draft(drafted):
    text, footnotes = render_footnoted(drafted)
    with st.container(border=True):
        st.markdown(f"**Proposed new clause: {plain(drafted.title)}**")
        if not drafted.has_references:
            st.warning("No reference in the library for this request. The AI wrote the clause itself; "
                       "review it carefully.")
        elif drafted.needs_review:
            st.info("Some sentences are marked \u2020 or \u2021 and need a closer look.")
        st.write(plain(text))
        show_lines_caption(footnotes)
        if drafted.selection.picks:
            with st.expander("Why these references"):
                for p in drafted.selection.picks:
                    st.caption(plain(f"{p.ref_id}: {p.reason}"))
        if drafted.notes:
            with st.expander("Points to decide or check"):
                show_lines(f"- {n}" for n in drafted.notes)
        st.checkbox("Keep this draft for the next step", value=True, key=widget_key("keep", drafted.request))


def apply_proposals(msg):
    """Apply button callback. Writes the ticked proposals into the draft's selection. Callbacks run
    before the page reruns, which is what allows this to change the checkboxes' state."""
    result = msg["result"]
    titles = {c.key: c.title for c in build_library()}
    applied = []
    for a in result.clause_actions:
        if st.session_state.get(action_key(a), a.evidence_verified):
            clause_sandbox.set_clause(STATE_KEY, a.clause_key, a.action == "include")
            verb = "Removed" if a.action == "exclude" else "Added"
            applied.append(f"{verb} clause: {titles[a.clause_key]}")
    deviations = [d for d in result.deviations
                  if st.session_state.get(deviation_key(d), d.evidence_verified)]
    st.session_state[DEVIATIONS_KEY] = deviations
    applied += [f"Wording change noted for {titles[d.clause_key]}: {d.summary}" for d in deviations]
    msg["applied"] = applied


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


def render_latest(msg, clauses, turn, stale):
    """Renders the newest assistant reply: proposal cards with an Apply button, or the applied
    summary, plus any questions. Returns a quick-reply text if a Yes/No button was pressed."""
    result = msg["result"]
    proposals, questions, uncovered = result_lines(result, list(clauses.values()))
    quick_reply, draft_request = None, None

    if not (proposals or questions or uncovered):
        st.write("I found no changes to the standard contract.")

    if msg.get("applied") is not None:
        st.success("Applied to the draft.")
        show_lines(f"- {line}" for line in msg["applied"])
    elif proposals:
        st.write("Here is what I would change:")
        for a in result.clause_actions:
            with st.container(border=True):
                verb = "Remove" if a.action == "exclude" else "Add"
                st.markdown(f"**{verb} clause: {clauses[a.clause_key].title}**")
                source = "You wrote" if a.basis == "comment" else "From the term sheet"
                st.caption(f"{source}: \u201c{plain(a.evidence)}\u201d")
                if a.reason.strip() and a.reason.strip().lower() != a.evidence.strip().lower():
                    st.caption(f"Why: {plain(a.reason)}")
                clause_preview(clauses, a.clause_key, removing=a.action == "exclude")
                if not a.evidence_verified:
                    st.warning("This quote was not found in your messages. Check it before applying.")
                st.checkbox("Apply this change", value=a.evidence_verified, key=action_key(a))

        for d in result.deviations:
            with st.container(border=True):
                st.markdown(f"**{clauses[d.clause_key].title}: {d.summary}**")
                st.write(f"Wording change: {plain(d.requested_change)}")
                if d.change_type == "add":
                    st.caption("This adds new wording to the clause.")
                else:
                    st.caption(f"Current wording: \u201c{plain(d.provision_quote)}\u201d")
                st.caption(f"You wrote: \u201c{plain(d.evidence)}\u201d")
                if not d.evidence_verified:
                    st.warning("This quote was not found in your messages. Check it before applying.")
                st.checkbox("Keep this request", value=d.evidence_verified, key=deviation_key(d))

        st.button("Apply selected changes", type="primary", on_click=apply_proposals, args=(msg,),
                  disabled=stale, key=widget_key("apply", str(turn)))

    for i, u in enumerate(u for u in result.unmapped_requests if not u.candidate_key):
        show_lines([f"Not covered by the clause library: {u.request}"])
        drafted = st.session_state.get(DRAFTS_KEY, {}).get(u.request)
        if drafted:
            render_draft(drafted)
        elif st.button("Find references and draft this clause", key=widget_key("draft", str(turn), str(i))):
            draft_request = u.request

    if questions:
        st.markdown("**I need to check something:**")
        show_lines(result.ambiguities)
        for i, u in enumerate(u for u in result.unmapped_requests if u.candidate_key):
            title = clauses[u.candidate_key].title
            show_lines([candidate_question(u, title)])
            said = u.evidence or u.request
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
    missing = [f for f in REQUIRED_FIELDS if ts is None or not getattr(ts, f)]
    if missing:
        st.warning("Complete the required term sheet fields first.")
        st.button("Back to term sheet", on_click=flow.go_back)
        return

    # Temporary key input; Phase 8 replaces this with the shared credentials module.
    entered = st.sidebar.text_input("OpenAI API key", type="password",
                                    value=st.session_state.get("openai_api_key", ""))
    if entered:
        st.session_state.openai_api_key = entered
    client = get_client(st.session_state.get("openai_api_key"))

    if st.sidebar.button("Clear conversation"):
        st.session_state.pop("chat", None)
        st.rerun()

    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    chat = st.session_state.setdefault("chat", [])
    included = clause_sandbox.ensure_state(STATE_KEY)
    limits = clause_sandbox.current_limits()
    clauses = {c.key: c for c in library_for(included, limits)}

    for w in term_sheet_warnings(ts):
        st.warning(w)

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

    quick_reply, draft_request = None, None
    for i, msg in enumerate(chat):
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and i == last_idx:
                quick_reply, draft_request = render_latest(msg, clauses, len(chat), stale)
            else:
                show_lines(msg["content"].split("\n"))

    if client is not None and draft_request:
        with st.chat_message("assistant"):
            with st.spinner("Finding references and drafting..."):
                error = None
                try:
                    refs = get_references()
                    selection = select_references(draft_request, refs,
                                                  CountingClient(client, calls, "select_references"), MODEL)
                    drafted = draft_clause(draft_request, selection, refs,
                                           CountingClient(client, calls, "draft_clause"), MODEL)
                except (AIStepError, FileNotFoundError) as e:
                    error = str(e)
                except Exception as e:
                    error = f"The API call failed: {e}"
            if error:
                st.error(error)
            else:
                st.session_state.setdefault(DRAFTS_KEY, {})[draft_request] = drafted
                st.rerun()

    if client is None:
        st.info("Enter an OpenAI API key in the sidebar to start.")
    prompt = st.chat_input("Describe a change, or answer the question above...", disabled=client is None)
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
                        ts, library_for(included, limits), CountingClient(client, calls, STEP_NAME), MODEL,
                        [{"role": m["role"], "content": m["content"]} for m in chat])
                except InterpretationError as e:
                    error = str(e)
                except Exception as e:
                    error = f"The API call failed: {e}"
            if error:
                if text:
                    chat.pop()
                st.error(f"{error} Your message was not sent; please try again.")
            else:
                chat.append({"role": "assistant", "content": context_summary(result, list(clauses.values())),
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
