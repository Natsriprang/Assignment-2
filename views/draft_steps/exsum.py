"""The summary of the contract at the top of the preview (step 3): what the contract says, for the person who approves it, also when nothing was
changed from the template.

Code writes everything that must be right, and shows it with no API key: the table of facts from the term sheet (parties, project, price, time,
payment, the caps as the draft has them, governing law, signatories), what the term sheet still lacks, and "Changes made to the contract": the
clauses taken out of the standard contract and, for every sentence that was changed, only what changed, in plain words ("changed from 0.05 to 0.5").
The AI (one call, step "exsum_overview") writes the overview above the changes (what the deal is, what matters in it and how it differs from the
standard contract, leaving ordinary standard wording alone) and, in the same call, one sentence in ordinary language for each change ("Liquidated
damages changed from 0.05% to 0.5% a day"); code checks their figures and symbols, and writes the plain version itself for a change that has no
sentence that passed. It runs once by itself when the preview is first opened with an API key, and after that only when asked (the button is off
while neither the term sheet nor the draft has changed). Advice only: it never blocks the download."""
import hashlib
import json

import streamlit as st

from ai.exsum import summarise_contract
from ai.llm import MODEL, AIStepError, CountingClient, get_client
from ai.review import sections_of, term_sheet_for_review
from core.exsum import fact_rows, facts_text, plain_change, word_changes
from core.readiness import missing_before_sending
from core.renumber import renumber_and_render
from views import clause_sandbox
from views.draft_steps import clauses, flow, review, risks

RESULT_KEY = "draft_exsum"                # {"snapshot", "result": ExSumResult} or {"snapshot", "error"}
AUTO_KEY = "draft_exsum_auto"             # the draft the summary was last started on by itself
OVERVIEW_STEP = "exsum_overview"


def plain(text):
    return review.plain(text)


def current():
    """What the summary is made of, as the draft stands now: (term sheet text, sections of the clauses, table of facts, {clause key: [{"kind",
    "before", "after", "user_words"}]} for the clauses that were changed, titles of the clauses taken out, {clause key: its number}, {clause
    key: its title})."""
    ts = clause_sandbox.current_term_sheet()
    library = clauses.draft_library_now()
    sections = sections_of(library)
    titles = {c.key: c.title for c in library}
    key_of = {title: key for key, title in titles.items()}
    items = risks.current_items()
    changes = {}
    for it in items:
        key = key_of.get(it["clause"])
        if key and it["kind"] in ("wording_change", "new_clause"):
            changes.setdefault(key, []).append({"kind": it["kind"], "before": it["before"], "after": it["after"], "user_words": it["user_words"]})
    taken_out = [it["clause"] for it in items if it["kind"] == "removed_clause"]
    numbers = {c.key: n for n, c, _ in renumber_and_render(library)}
    return term_sheet_for_review(ts), sections, fact_rows(ts, library), changes, taken_out, numbers, titles


def snapshot():
    ts_text, sections, rows, changes, taken_out, _, _ = current()
    data = [ts_text, facts_text(rows), [(s.key, s.text) for s in sections], changes, taken_out]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def run_summary(client):
    """The AI call now; the overview is stored with the draft it was made on."""
    ts_text, sections, rows, changes, taken_out, _, _ = current()
    calls = st.session_state.setdefault(flow.CALLS_KEY, [])
    outcome = {"snapshot": snapshot()}
    with st.spinner("Writing the overview..."):
        try:
            outcome["result"] = summarise_contract(ts_text, sections, facts_text(rows), changes, taken_out, CountingClient(client, calls, OVERVIEW_STEP), MODEL)
        except AIStepError as e:
            outcome["error"] = str(e)
        except Exception as e:
            outcome["error"] = f"The API call failed: {e}"
    st.session_state[RESULT_KEY] = outcome


def change_lines(entry):
    """The changes of one sentence as plain lines that the app writes itself."""
    kind, before, after = entry["kind"], entry["before"], entry["after"]
    if kind == "new_clause":
        return ["new clause"]
    if before and after:
        return [plain_change(removed, added) for removed, added in word_changes(before, after)]
    return [plain_change("", after)] if after else [plain_change(before, "")]


def show_changes(changes, taken_out, numbers, titles, plain_by_clause=None):
    """The list of changes: for each changed clause the AI's plain sentences when they passed the checks, otherwise the app's own plain version."""
    st.markdown("#### Changes made to the contract")
    if not changes and not taken_out:
        st.write("No change from the standard contract.")
        return
    if taken_out:
        st.write("Clauses taken out: " + plain(", ".join(taken_out)) + ".")
    for key in sorted(changes, key=lambda k: float(numbers.get(k, 0) or 0)):
        st.markdown(f"**{numbers.get(key, '')}. {plain(titles.get(key, key))}**")
        lines = (plain_by_clause or {}).get(key) or [line for entry in changes[key] for line in change_lines(entry)]
        for line in lines:
            st.write("\u2022 " + plain(line))


def show():
    """The summary section of the preview."""
    st.subheader("Summary of the contract")
    st.caption("What this contract says, for the person who approves it. The table and the changes are written by the app from the term sheet and the "
               "draft; the overview is written by the AI, which leaves ordinary standard wording alone.")
    ts_text, sections, rows, changes, taken_out, numbers, titles = current()
    with st.container(border=True):
        if rows:
            for label, value in rows:
                st.markdown(f"**{plain(label)}:** {plain(value)}")
        else:
            st.write("The term sheet has no values yet.")
    missing = missing_before_sending(clause_sandbox.current_term_sheet())
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
    if outcome is None:
        st.write("The overview was not written yet. Enter an API key to write it." if client is None else "The overview was not written yet.")
    else:
        if client is not None and outcome["snapshot"] != snap:
            st.write("The draft or the term sheet changed since this overview was written. This is the overview of the draft as it was; press Write the overview again.")
        if "error" in outcome:
            st.write(f"The overview could not be written: {plain(outcome['error'])}")
        else:
            result = outcome["result"]
            if result.overview:
                st.write(plain(result.overview))
            else:
                st.write("The AI wrote no overview that passed the checks.")
            if result.notes:
                with st.expander(f"{len(result.notes)} check(s) made on the overview"):
                    for note in result.notes:
                        st.caption(plain(note))
    ok = outcome is not None and "error" not in outcome
    show_changes(changes, taken_out, numbers, titles, outcome["result"].plain_changes if ok else None)
    if client is not None:
        unchanged = outcome is not None and "error" not in outcome and outcome["snapshot"] == snap
        pressed = st.button("Write the overview again" if outcome is not None else "Write the overview", key="exsum_again", disabled=unchanged)
        if unchanged:
            st.caption("The term sheet and the draft have not changed since this overview was written.")
        if pressed:
            run_summary(client)
            st.rerun()
