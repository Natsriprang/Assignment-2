"""Draft contract: one continuous workflow. Each step is a function; this page shows the current
step under a header with back/next arrows. To add a step, write its render() and add it to STEPS."""
import streamlit as st

from views.draft_steps import flow, interpret, sandbox, term_sheet

STEPS = [
    flow.Step("Term sheet", term_sheet.render, term_sheet.is_complete),
    flow.Step("Interpret request", interpret.render, interpret.is_confirmed),
    flow.Step("Clause sandbox", sandbox.render),
]

st.session_state[flow.COUNT_KEY] = len(STEPS)
index = min(flow.current(), len(STEPS) - 1)
step = STEPS[index]

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
    forward.button("\u203a", key="draft_forward", on_click=flow.go_next,
                   disabled=index == len(STEPS) - 1 or not step.ready(), help="Next step")
    st.caption(" \u203a ".join(f"**{s.title}**" if i == index else s.title for i, s in enumerate(STEPS)))
    st.divider()
