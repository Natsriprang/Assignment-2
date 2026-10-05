"""Draft contract: one continuous workflow. Each step is a function; this page shows the current
step under a header with back/next arrows. To add a step, write its render() and add it to STEPS."""
import streamlit as st

from ai.llm import call_summary
from views.draft_steps import clauses, flow, preview, term_sheet

STEPS = [
    flow.Step("Term sheet", term_sheet.render, term_sheet.is_complete, term_sheet.advance),
    flow.Step("Clauses", clauses.render, clauses.has_analysis),
    flow.Step("Draft preview", preview.render),
]

st.session_state[flow.COUNT_KEY] = len(STEPS)
index = min(flow.current(), len(STEPS) - 1)
step = STEPS[index]

# One key input for the whole workflow (Phase 8 replaces it with the shared credentials module). It runs before the steps
# so a step already sees the key typed in this run.
with st.sidebar:
    entered = st.text_input("OpenAI API key", type="password", value=st.session_state.get("openai_api_key", ""))
    if entered:
        st.session_state.openai_api_key = entered

# The header is created first so it sits on top, but filled after the step runs: the next arrow
# then reflects what the user just typed instead of the previous run's state.
header = st.container()
step.render()

with header:
    st.title("\U0001f4dd Draft contract")
    back, label, forward = st.columns([1, 8, 1])
    back.button("\u2039", key="draft_back", on_click=flow.go_back, disabled=index == 0,
                help="Previous step")
    label.markdown(f"**Step {index + 1} of {len(STEPS)}: {step.title}**")
    forward_disabled = index == len(STEPS) - 1 or not step.ready()
    if step.advance is None:
        forward.button("\u203a", key="draft_forward", on_click=flow.go_next, disabled=forward_disabled, help="Next step")
    elif forward.button("\u203a", key="draft_forward", disabled=forward_disabled, help="Next step"):
        step.advance()                       # a step with work to do on the way out (the term sheet check) does it here
    st.caption(" \u203a ".join(f"**{s.title}**" if i == index else s.title for i, s in enumerate(STEPS)))
    st.divider()

calls = st.session_state.get(flow.CALLS_KEY, [])
with st.sidebar:
    st.divider()
    st.caption(f"AI calls this run: {len(calls)}" + (f" ({call_summary(calls)})" if calls else ""))
