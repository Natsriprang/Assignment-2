"""Shared step state for the Draft contract workflow. Steps move the workflow forward or back
through these callbacks, so a step never needs to know which step comes next."""
from dataclasses import dataclass
from typing import Callable

import streamlit as st

STEP_KEY = "draft_step"
COUNT_KEY = "draft_step_count"
CONFIRMED_KEY = "confirmed_interpretation"
CONFIRMED_FIELDS = {"clause_actions", "deviations", "included", "version"}


@dataclass
class Step:
    title: str
    render: Callable
    ready: Callable = lambda: True   # whether the user may move past this step


def current():
    return st.session_state.get(STEP_KEY, 0)


def go_next():
    st.session_state[STEP_KEY] = min(current() + 1, st.session_state.get(COUNT_KEY, 1) - 1)


def go_back():
    st.session_state[STEP_KEY] = max(current() - 1, 0)


def confirmed():
    """The confirmed interpretation, or None. An entry left in the session by an older version of
    the app (missing fields) is discarded instead of being read."""
    data = st.session_state.get(CONFIRMED_KEY)
    if data is not None and not CONFIRMED_FIELDS <= set(data):
        del st.session_state[CONFIRMED_KEY]
        return None
    return data