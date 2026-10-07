"""Readiness of the draft to become a contract if it is signed, under the governing law the user typed on the term sheet (step 3).

The governing law is matched by code to a list of elements (core.legal_systems: Australia, Thailand); a law with no list gets a general list
and a warning that says so. What the term sheet lacks for an element is found by code and shown with no key and no AI call. The AI (one call,
step "readiness") judges the rest: each element is complete, not complete, or cannot be told from the draft, with words of the draft as
evidence. It runs once by itself when the preview is first opened with an API key, so every run that reaches the preview with a key makes this
call, and after that only when asked (the button is off while neither the term sheet nor the draft has changed). Advice only: it does not decide
that a contract exists and it never blocks the download."""
import hashlib
import json

import streamlit as st

from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.readiness import check_readiness
from ai.review import sections_of
from core.header import build_header
from core.legal_systems import GENERIC, match_system
from core.readiness import facts, failed_for
from core.signatures import build_signature_block, signature_texts
from views import clause_sandbox
from views.draft_steps import flow, review

RESULT_KEY = "draft_readiness"            # {"snapshot", "result": ReadinessResult} or {"snapshot", "error"}
AUTO_KEY = "draft_readiness_auto"         # the draft the check was last started on by itself
STEP_NAME = "readiness"
LABEL = {"complete": "Complete", "not_complete": "Not complete", "cannot_tell": "Cannot be told from the draft"}


def plain(text):
    return review.plain(text)


def current():
    """(governing law as typed, the matching system or None, why not, the facts of the term sheet, sections of the draft)."""
    ts = clause_sandbox.current_term_sheet()
    law = str(getattr(ts, "governing_law", "") or "")
    system, why = match_system(law)
    sections = sections_of(review.current_library(), build_header(ts), signature_texts(build_signature_block(ts))[1:])
    return law, system, why, facts(ts), sections


def snapshot():
    law, system, why, found, sections = current()
    return hashlib.sha256(json.dumps([law, [(k, f.ok) for k, f in found.items()], [(s.key, s.text) for s in sections]], ensure_ascii=False).encode()).hexdigest()


def run_check(client):
    """One AI call now; the result is stored with the draft it was made on."""
    law, system, why, found, sections = current()
    outcome = {"snapshot": snapshot()}
    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    with st.spinner("Checking whether the draft has what the governing law needs..."):
        try:
            outcome["result"] = check_readiness(system, why, found, sections, CountingClient(client, calls, STEP_NAME), MODEL)
        except AIStepError as e:
            outcome["error"] = str(e)
    st.session_state[RESULT_KEY] = outcome


def show_element(r):
    with st.container(border=True):
        st.markdown(f"**{plain(r.title)}**  \u00b7  {LABEL[r.status]}" + ("  \u00b7  checked by the app, no AI" if r.by == "app" else ""))
        if r.reason:
            st.write(plain(r.reason))
        if r.quote:
            st.caption(f"In the draft: \u201c{plain(r.quote)}\u201d")


def show_governing_law(law, system, why, source, url, note):
    if system is None:
        st.warning(f"{plain(why)} A general list of what any written contract needs was used, which does not follow that law. "
                   f"Governing law written on the term sheet: \u201c{plain(law or '(nothing)')}\u201d.")
    else:
        st.caption(f"Governing law on the term sheet: \u201c{plain(law)}\u201d. List of elements used: {plain(system.name)}. Source: {plain(source)}. "
                   f"{plain(note)} The list was not reviewed by a lawyer.")


def show():
    """The readiness section of the preview."""
    st.subheader("Readiness to form a contract")
    st.caption("If the Parties sign this draft, does it have what the governing law they chose needs for a contract to come into existence and be "
               "enforceable? This is advice before signing. It does not decide that a contract exists.")
    law, system, why, found, sections = current()
    chosen = system or GENERIC
    show_governing_law(law, system, why, chosen.source, chosen.url, chosen.note)
    client = get_client(st.session_state.get("openai_api_key"))
    outcome = st.session_state.get(RESULT_KEY)
    snap = None
    if client is not None:
        snap = snapshot()
        if outcome is None and st.session_state.get(AUTO_KEY) != snap:
            st.session_state[AUTO_KEY] = snap
            run_check(client)
            outcome = st.session_state.get(RESULT_KEY)
    if outcome is None:
        gaps = [(e.title, failed_for(e, found)) for e in chosen.elements if failed_for(e, found)]
        if gaps:
            st.warning("Found by the app, without AI: " + "; ".join(f"{plain(t)} (not in the term sheet: {plain(', '.join(m))})" for t, m in gaps) + ".")
        st.caption("The elements were not checked against the draft yet. Enter an API key to check them." if client is None
                   else "The elements were not checked against the draft yet.")
    else:
        if client is not None and outcome["snapshot"] != snap:
            st.caption("The draft or the term sheet changed since this check was made. This is what that check found; press Check readiness again to check again.")
        if "error" in outcome:
            st.warning(f"The readiness check could not run: {plain(outcome['error'])}")
        else:
            result = outcome["result"]
            n = result.counts()
            if n["not_complete"]:
                st.warning(f"{n['not_complete']} element(s) not complete, {n['complete']} complete, {n['cannot_tell']} that cannot be told from the draft. "
                           "Nothing was changed, and you can still download the draft.")
            else:
                st.caption(f"No element was found missing: {n['complete']} complete, {n['cannot_tell']} that cannot be told from the draft. "
                           "That does not mean a contract will exist.")
            for note in result.notes:
                st.caption(plain(note))
            for r in result.results:
                show_element(r)
    if client is not None:
        unchanged = outcome is not None and "error" not in outcome and outcome["snapshot"] == snap
        pressed = st.button("Check readiness again" if outcome is not None else "Check readiness", key="readiness_again", disabled=unchanged)
        if unchanged:
            st.caption("The term sheet and the draft have not changed since the last check.")
        if pressed:
            run_check(client)
            st.rerun()
