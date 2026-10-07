"""Draft contract: one continuous workflow. Each step is a function; this page shows the current
step under a header with back/next arrows. To add a step, write its render() and add it to STEPS."""
import runpy
from pathlib import Path

import streamlit as st

from ai.llm import call_summary
from views.draft_steps import clauses, flow, preview, term_sheet

STEPS = [
    flow.Step("Term sheet", term_sheet.render, term_sheet.can_continue),
    flow.Step("Clauses", clauses.render, clauses.has_analysis),
    flow.Step("Draft preview", preview.render),
]

st.session_state[flow.COUNT_KEY] = len(STEPS)
index = min(flow.current(), len(STEPS) - 1)
step = STEPS[index]

# One key input for the whole workflow: the shared credentials module from the course (api_key.py at the repo root, not edited).
# It puts the key in st.session_state.openai_api_key when "Update API Key" is pressed, and it runs before the steps so a step
# already sees the key in the same run. run_path runs the file on every rerun (an import would run it only the first time,
# and the sidebar box would disappear on the next rerun).
runpy.run_path(str(Path(__file__).resolve().parent.parent / "api_key.py"))

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

calls = st.session_state.get(flow.CALLS_KEY, [])
with st.sidebar:
    st.divider()
    st.caption(f"AI calls this run: {len(calls)}" + (f" ({call_summary(calls)})" if calls else ""))
