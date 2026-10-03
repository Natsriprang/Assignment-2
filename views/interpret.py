"""Interpret step as a conversation. The user describes changes in chat; the assistant proposes
clause changes and asks when something is unclear. The latest reply carries the proposals as
cards with an "Apply" tick, and nothing reaches the draft until the user presses Confirm."""
import hashlib
import re

import streamlit as st

from clause_data import build_library
from interpret import (InterpretationError, context_summary, interpret_request, resolve_included,
                       result_lines, term_sheet_text, term_sheet_warnings)
from llm import MODEL, get_client
from term_sheet_fields import REQUIRED_FIELDS

st.title("\U0001f50e Interpret Request")
st.caption("Tell the assistant what you want changed from the standard contract. It proposes changes "
           "and asks when something is unclear. Nothing is applied until you confirm.")


def plain(text):
    return re.sub(r"([\\`*_\[\]#>|~$<])", r"\\\1", text)


def widget_key(*parts):
    return "k_" + hashlib.md5("|".join(parts).encode()).hexdigest()[:10]


def show_lines(lines):
    for line in lines:
        st.write(plain(line))


ts = st.session_state.get("term_sheet")
missing = [f for f in REQUIRED_FIELDS if ts is None or not getattr(ts, f)]
if missing:
    st.warning("Complete the required term sheet fields first.")
    st.page_link("page_term_sheet.py", label="Go to Term Sheet", icon="\U0001f4cb")
    st.stop()

# Temporary key input; Phase 8 replaces this with the shared credentials module.
entered = st.sidebar.text_input("OpenAI API key", type="password",
                                value=st.session_state.get("openai_api_key", ""))
if entered:
    st.session_state.openai_api_key = entered
client = get_client(st.session_state.get("openai_api_key"))

if st.sidebar.button("Clear conversation"):
    st.session_state.pop("chat", None)
    st.session_state.pop("confirmed_interpretation", None)
    st.rerun()

library = build_library()
clauses = {c.key: c for c in library}
chat = st.session_state.setdefault("chat", [])


def clause_preview(key, removing):
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


def render_latest(msg):
    """Renders the newest assistant reply with its interactive cards.
    Returns (accepted_actions, accepted_deviations, quick_reply)."""
    result = msg["result"]
    proposals, questions, uncovered = result_lines(result, library)
    accepted_actions, accepted_deviations, quick_reply = [], [], None

    if not (proposals or questions or uncovered):
        st.write("I found no changes to the standard contract.")
    if proposals:
        st.write("Here is what I would change:")

    for a in result.clause_actions:
        with st.container(border=True):
            verb = "Remove" if a.action == "exclude" else "Add"
            st.markdown(f"**{verb} clause: {clauses[a.clause_key].title}**")
            source = "You wrote" if a.basis == "comment" else "From the term sheet"
            st.caption(f"{source}: \u201c{plain(a.evidence)}\u201d")
            if a.reason.strip() and a.reason.strip().lower() != a.evidence.strip().lower():
                st.caption(f"Why: {plain(a.reason)}")
            clause_preview(a.clause_key, removing=a.action == "exclude")
            if not a.evidence_verified:
                st.warning("This quote was not found in your messages. Check it before applying.")
            if st.checkbox("Apply this change", value=a.evidence_verified,
                           key=widget_key("act", a.clause_key, a.action)):
                accepted_actions.append(a)

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
            if st.checkbox("Keep this request", value=d.evidence_verified,
                           key=widget_key("dev", d.clause_key, d.change_type, d.provision_quote, d.summary)):
                accepted_deviations.append(d)

    if uncovered:
        show_lines(uncovered)

    if questions:
        st.markdown("**I need to check something:**")
        show_lines(q.removeprefix("Question: ") for q in questions)
        candidates = [u for u in result.unmapped_requests if u.candidate_key]
        if len(candidates) == 1 and not result.ambiguities:
            c1, c2, _ = st.columns([2, 2, 3])
            if c1.button("Yes, that's what I meant", key=widget_key("yes", str(len(chat)))):
                quick_reply = "Yes, that is what I meant."
            if c2.button("No, something else", key=widget_key("no", str(len(chat)))):
                quick_reply = "No, that is not what I meant."

    if result.notes:
        with st.expander("Automatic checks"):
            st.caption("Proposals the system discarded because they were invalid or changed nothing.")
            show_lines(f"- {n}" for n in result.notes)
    return accepted_actions, accepted_deviations, quick_reply


for w in term_sheet_warnings(ts):
    st.warning(w)

last_idx = max((i for i, m in enumerate(chat) if m["role"] == "assistant"), default=None)
latest = chat[last_idx] if last_idx is not None else None
stale = latest is not None and latest["snapshot"] != term_sheet_text(ts)
if stale:
    st.warning("The term sheet changed after the latest reply. Send a message to analyse again "
               "before confirming.")

skip = False
if not chat:
    with st.chat_message("assistant"):
        st.write("What would you like to change from the standard contract? For example: "
                 "\u201cclient wants to drop the construction timeline\u201d. I also check the term "
                 "sheet itself, for example whether the roof owner is a different party from the Owner.")
        skip = st.button("No special requests \u2014 just check the term sheet", disabled=client is None)

accepted_actions, accepted_deviations, quick_reply = [], [], None
for i, msg in enumerate(chat):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and i == last_idx:
            accepted_actions, accepted_deviations, quick_reply = render_latest(msg)
        else:
            show_lines(msg["content"].split("\n"))

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
                    ts, build_library(), client, MODEL,
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
            chat.append({"role": "assistant", "content": context_summary(result, library),
                         "result": result, "snapshot": term_sheet_text(ts)})
            st.session_state.pop("confirmed_interpretation", None)
            st.rerun()

if latest is not None:
    st.divider()
    _, questions, _ = result_lines(latest["result"], library)
    if questions:
        st.caption("There are open questions above. You can confirm now; requests that are still "
                   "unanswered will not be applied.")
    if st.button("Confirm and apply", type="primary", disabled=stale):
        included = resolve_included(build_library(), accepted_actions)
        st.session_state.included = included
        for key in included:
            st.session_state.pop(f"chk_{key}", None)
        st.session_state.confirmed_interpretation = {
            "clause_actions": accepted_actions, "deviations": accepted_deviations,
            "n_clauses": sum(included.values())}

    confirmed = st.session_state.get("confirmed_interpretation")
    if confirmed:
        st.success(f"Applied. The draft now has {confirmed['n_clauses']} clauses and "
                   f"{len(confirmed['deviations'])} wording change(s) carried forward.")
        st.page_link("page_sandbox.py", label="View the result in Clause Sandbox", icon="\U0001f9f0")