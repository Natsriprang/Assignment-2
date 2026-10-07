"""The summary of the contract at the top of the preview (step 3): what the contract says, for the person who approves it, also when nothing was
changed from the template.

Code writes what must be right: the table of facts (parties, project, price, time, payment, caps, governing law, signatories) from the term
sheet, what was taken out of the standard contract, what the term sheet still lacks, and the sentences that were changed. These are shown with
no API key. The AI (two calls, steps "exsum_clauses" and "exsum_overview") decides which clauses matter and summarises them, leaving ordinary
boilerplate out and saying which clauses it left out, then writes the overview. A clause that was changed is always shown: when the AI skipped
it, or its summary was taken out by the checks, the changed sentences themselves are shown. It runs once by itself when the preview is first
opened with an API key, and after that only when asked (the button is off while neither the term sheet nor the draft has changed). Advice only:
it never blocks the download."""
import hashlib
import json

import streamlit as st

from ai.exsum import summarise_contract
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.review import sections_of, term_sheet_for_review
from core.exsum import coverage_text, fact_rows, facts_text
from core.readiness import missing_before_sending
from core.renumber import renumber_and_render
from views import clause_sandbox
from views.draft_steps import clauses, flow, review, risks

RESULT_KEY = "draft_exsum"                # {"snapshot", "result": ExSumResult} or {"snapshot", "error"}
AUTO_KEY = "draft_exsum_auto"             # the draft the summary was last started on by itself
CLAUSES_STEP = "exsum_clauses"
OVERVIEW_STEP = "exsum_overview"


def plain(text):
    return review.plain(text)


def current():
    """What the summary is made of, as the draft stands now: (term sheet, term sheet text, sections, table of facts, keys of the changed
    clauses, titles of the clauses taken out, {changed clause key: its changed sentences}, {clause key: number in the draft})."""
    ts = clause_sandbox.current_term_sheet()
    library = clauses.draft_library_now()
    sections = sections_of(library)
    by_title = {c.key: c.title for c in library}
    key_of = {title: key for key, title in by_title.items()}
    items = risks.current_items()
    sentences = {}
    for it in items:
        key = key_of.get(it["clause"])
        if key and it["kind"] in ("wording_change", "new_clause") and it["after"]:
            sentences.setdefault(key, []).append(it["after"])
    taken_out = [it["clause"] for it in items if it["kind"] == "removed_clause"]
    numbers = {c.key: n for n, c, _ in renumber_and_render(library)}
    return ts, term_sheet_for_review(ts), sections, fact_rows(ts), set(sentences), taken_out, sentences, numbers


def snapshot():
    ts, ts_text, sections, rows, changed, taken_out, sentences, _ = current()
    data = [ts_text, facts_text(rows), [(s.key, s.text) for s in sections], sorted(changed), taken_out]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()


def run_summary(client):
    """Two AI calls now; the result is stored with the draft it was made on."""
    ts, ts_text, sections, rows, changed, taken_out, _, _ = current()
    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    outcome = {"snapshot": snapshot()}
    with st.spinner("Summarising the contract..."):
        try:
            outcome["result"] = summarise_contract(ts_text, sections, facts_text(rows), changed, taken_out, CountingClient(client, calls, CLAUSES_STEP), MODEL,
                                                   second_client=CountingClient(client, calls, OVERVIEW_STEP))
        except AIStepError as e:
            outcome["error"] = str(e)
        except Exception as e:
            outcome["error"] = f"The API call failed: {e}"
    st.session_state[RESULT_KEY] = outcome


def show_changed_sentences(title, sentences):
    st.markdown(f"**{plain(title)}**  \u00b7  changed from the template")
    for sentence in sentences:
        st.write(plain(sentence))


def show():
    """The summary section of the preview."""
    st.subheader("Summary of the contract")
    st.caption("What this contract says, for the person who approves it. The table is written from the term sheet by the app; the summaries of the "
               "clauses are written by the AI, which leaves out ordinary standard wording.")
    ts, ts_text, sections, rows, changed, taken_out, sentences, numbers = current()
    with st.container(border=True):
        if rows:
            for label, value in rows:
                st.markdown(f"**{plain(label)}:** {plain(value)}")
        else:
            st.write("The term sheet has no values yet.")
    if taken_out:
        st.write("Taken out of the standard contract: " + plain(", ".join(taken_out)) + ".")
    missing = missing_before_sending(ts)
    if missing:
        st.write("Still missing from the term sheet before the draft is sent: " + plain(", ".join(missing)) + ".")

    client = get_client(st.session_state.get("openai_api_key"))
    outcome = st.session_state.get(RESULT_KEY)
    snap = None
    if client is not None:
        snap = snapshot()
        if outcome is None and st.session_state.get(AUTO_KEY) != snap:
            st.session_state[AUTO_KEY] = snap
            run_summary(client)
            outcome = st.session_state.get(RESULT_KEY)
    titles = {s.key: s.title for s in sections}
    if outcome is None:
        for key in sorted(changed, key=lambda k: float(numbers.get(k, 0) or 0)):
            show_changed_sentences(titles.get(key, key), sentences[key])
        st.write("The clauses were not summarised yet. Enter an API key to summarise them." if client is None else "The clauses were not summarised yet.")
    else:
        if client is not None and outcome["snapshot"] != snap:
            st.write("The draft or the term sheet changed since this summary was made. This is the summary of the draft as it was; press Summarise again.")
        if "error" in outcome:
            st.write(f"The summary could not be made: {plain(outcome['error'])}")
        else:
            result = outcome["result"]
            if result.overview:
                st.write(plain(result.overview))
            for key, text in result.key_points:
                st.write(f"\u2022 {plain(text)}")
            shown = set()
            for d in result.decisions:
                if d.decision == "summarise":
                    tag = "  \u00b7  changed from the template" if d.changed else ""
                    st.markdown(f"**{numbers.get(d.key, '')}. {plain(d.title)}**{tag}")
                    st.write(plain(d.summary))
                    shown.add(d.key)
            for d in result.decisions:
                if d.changed and d.key not in shown and d.key in sentences:
                    show_changed_sentences(d.title, sentences[d.key])
            st.caption(coverage_text(len(result.summarised()), len(result.skipped()), []))
            skipped = result.skipped()
            if skipped:
                with st.expander(f"{len(skipped)} clause(s) left out"):
                    for d in skipped:
                        st.caption(f"{numbers.get(d.key, '')}. {plain(d.title)} \u2014 {plain(d.reason)}")
            if result.notes:
                with st.expander(f"{len(result.notes)} check(s) made on the summary"):
                    for note in result.notes:
                        st.caption(plain(note))
    if client is not None:
        unchanged = outcome is not None and "error" not in outcome and outcome["snapshot"] == snap
        pressed = st.button("Summarise again" if outcome is not None else "Summarise the contract", key="exsum_again", disabled=unchanged)
        if unchanged:
            st.caption("The term sheet and the draft have not changed since this summary was made.")
        if pressed:
            run_summary(client)
            st.rerun()
