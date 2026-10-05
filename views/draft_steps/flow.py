"""Shared step state for the Draft contract workflow. Steps move the workflow forward or back
through these callbacks, so a step never needs to know which step comes next."""
from dataclasses import dataclass
from typing import Callable

import streamlit as st

STEP_KEY = "draft_step"
COUNT_KEY = "draft_step_count"
CALLS_KEY = "ai_calls"   # log of completed AI calls in this run, one entry per call


@dataclass
class Step:
    title: str
    render: Callable
    ready: Callable = lambda: True   # whether the user may move past this step
    advance: Callable = None         # how the next arrow leaves this step, if it needs more than moving on (see term_sheet.advance)


def current():
    return st.session_state.get(STEP_KEY, 0)


def go_next():
    st.session_state[STEP_KEY] = min(current() + 1, st.session_state.get(COUNT_KEY, 1) - 1)


def go_back():
    st.session_state[STEP_KEY] = max(current() - 1, 0)
