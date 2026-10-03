"""Interpret step: the model reads the comment and term sheet and proposes changes to the standard
contract. Nothing is applied until the user reviews each proposal and confirms. Proposals whose
quoted evidence was not found in the input start unticked."""
import re

import streamlit as st

from clause_data import build_library
from interpret import InterpretationError, interpret_request, resolve_included, term_sheet_text, term_sheet_warnings
from llm import MODEL, get_client
from term_sheet_fields import REQUIRED_FIELDS

st.title("\U0001f50e Interpret Request")
st.caption("The system reads your comment and the term sheet, then proposes changes to the standard "
           "contract. Review each proposal below. Nothing changes until you confirm.")


def plain(text):
    return re.sub(r"([\\`*_\[\]#>|~$<])", r"\\\1", text)


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

clauses = {c.key: c for c in build_library()}


def run_interpretation(clarification):
    with st.spinner("Analysing your request..."):
        try:
            st.session_state.interpretation = interpret_request(
                ts, build_library(), client, MODEL, clarification)
        except InterpretationError as e:
            st.error(str(e))
            return False
        except Exception as e:
            st.error(f"The API call failed: {e}")
            return False
    st.session_state.interpretation_inputs = (term_sheet_text(ts), ts.comment)
    st.session_state.clarification_used = clarification
    st.session_state.interpretation_run = st.session_state.get("interpretation_run", 0) + 1
    st.session_state.clar_n = st.session_state.get("clar_n", 0) + 1
    st.session_state.pop("confirmed_interpretation", None)
    return True


def clause_preview(key, removing):
    label = "Text that will be removed" if removing else "Text that will be added"
    with st.expander(label):
        c = clauses[key]

        def show(text, caption=False):
            body = plain(text)
            if removing:
                body = f"~~{body}~~"
            (st.caption if caption else st.markdown)(body)

        for p in c.plain_paragraphs:
            show(p)
        for item in c.items:
            show(item.text)
            for sub in item.lettered:
                show(sub, caption=True)


for w in term_sheet_warnings(ts):
    st.warning(w)

st.subheader("Your request")
if ts.comment.strip():
    st.info(plain(ts.comment))
else:
    st.caption("No comment was entered. The system will still check the term sheet itself, "
               "for example whether the roof owner is a different party from the Owner.")
st.page_link("page_term_sheet.py", label="Edit on the Term Sheet page", icon="\U0001f4cb")

if client is None:
    st.info("Enter an OpenAI API key in the sidebar to continue.")

if st.button("Analyse my request", type="primary", disabled=client is None):
    run_interpretation("")

result = st.session_state.get("interpretation")
if result is None:
    st.stop()

run = st.session_state.interpretation_run
stale = st.session_state.interpretation_inputs != (term_sheet_text(ts), ts.comment)
if stale:
    st.warning("The term sheet or comment changed after this analysis. Analyse again before confirming.")

st.divider()
st.subheader("Proposed changes")
st.caption(f"{len(result.clause_actions)} clause change(s) \u00b7 {len(result.deviations)} wording "
           f"change(s) \u00b7 {len(result.ambiguities)} question(s) for you")

accepted_actions = []
for i, a in enumerate(result.clause_actions):
    with st.container(border=True):
        verb = "Remove" if a.action == "exclude" else "Add"
        st.markdown(f"**{verb} clause: {clauses[a.clause_key].title}**")
        source = "You wrote" if a.basis == "comment" else "From the term sheet"
        st.caption(f"{source}: \u201c{plain(a.evidence)}\u201d")
        if a.reason.strip() and a.reason.strip().lower() != a.evidence.strip().lower():
            st.caption(f"Why: {plain(a.reason)}")
        clause_preview(a.clause_key, removing=a.action == "exclude")
        if not a.evidence_verified:
            st.warning("This quote was not found in your input. Check it before applying.")
        if st.checkbox("Apply this change", value=a.evidence_verified, key=f"act_{run}_{i}"):
            accepted_actions.append(a)

accepted_deviations = []
if result.deviations:
    st.markdown("**Wording changes requested**")
    st.caption("The clause stays in the contract, but its wording will need to change. "
               "A later step drafts these.")
for i, d in enumerate(result.deviations):
    with st.container(border=True):
        st.markdown(f"**{clauses[d.clause_key].title}: {d.summary}**")
        st.write(f"You asked for: {plain(d.requested_change)}")
        st.caption(f"You wrote: \u201c{plain(d.evidence)}\u201d")
        if not d.evidence_verified:
            st.warning("This quote was not found in your input. Check it before applying.")
        if st.checkbox("Keep this request", value=d.evidence_verified, key=f"dev_{run}_{i}"):
            accepted_deviations.append(d)

if not result.clause_actions and not result.deviations:
    st.caption("No changes to the standard contract were found.")

if result.unmapped_requests:
    st.markdown("**Not covered by the clause library**")
    st.caption("The system has no clause for these, so they will not be applied.")
    for u in result.unmapped_requests:
        st.write(f"- {plain(u)}")

if result.ambiguities:
    st.subheader("Questions for you")
    for q in result.ambiguities:
        st.info(plain(q))
    used = st.session_state.get("clarification_used", "")
    if used:
        st.caption(f"Your earlier answer: {plain(used)}")
    answer = st.text_area("Your answer", key=f"clar_{st.session_state.get('clar_n', 0)}",
                          placeholder="Answer the questions above in your own words.")
    if st.button("Analyse again with my answer", disabled=not answer.strip()):
        if run_interpretation((used + "\n" + answer).strip()):
            st.rerun()

if result.notes:
    with st.expander("Automatic checks"):
        st.caption("Proposals the system discarded because they were invalid or changed nothing.")
        for n in result.notes:
            st.write(f"- {plain(n)}")

st.divider()
if st.button("Confirm and apply", type="primary", disabled=stale):
    included = resolve_included(build_library(), accepted_actions)
    st.session_state.included = included
    for key in included:
        st.session_state.pop(f"chk_{key}", None)
    st.session_state.confirmed_interpretation = {
        "clause_actions": accepted_actions, "deviations": accepted_deviations}
    st.success(f"Applied. The draft now has {sum(included.values())} clauses and "
               f"{len(accepted_deviations)} wording change(s) carried forward.")
    st.page_link("page_sandbox.py", label="View the result in Clause Sandbox", icon="\U0001f9f0")