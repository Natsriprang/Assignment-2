"""Clause sandbox components for the Draft contract workflow. The selection (clause key ->
included flag) lives in one session_state dict under `state_key`; the picker edits it and the
preview reads it, so they never disagree."""
import io
import re

import streamlit as st

from core.clause_data import build_library
from core.clauses import cross_reference_scan
from core.clause_params import limits_of
from core.draft_state import library_for
from core.header import build_header
from core.render import render_docx
from core.renumber import renumber_and_render
from views.draft_steps import drafts


def plain(text):
    """Escape markdown so placeholders like '[*]' render as literal text, not italic/link syntax."""
    return re.sub(r"([\\`*_\[\]#>|~$<])", r"\\\1", text)


def current_limits():
    """The caps chosen on the term sheet (defaults if none were chosen)."""
    return limits_of(st.session_state.get("term_sheet"))


def checkbox_key(state_key, clause_key):
    return f"{state_key}_chk_{clause_key}"


def ensure_state(state_key):
    if state_key not in st.session_state:
        st.session_state[state_key] = {c.key: c.included for c in build_library()}
    return st.session_state[state_key]


def set_clause(state_key, clause_key, included):
    """Sets one clause, including its checkbox. Safe to call from a widget callback."""
    ensure_state(state_key)[clause_key] = included
    st.session_state[checkbox_key(state_key, clause_key)] = included


def render_picker(state_key, noun="draft"):
    """Tick or untick clauses. Checkbox widgets have no `value=`: their state is seeded from the
    selection dict instead, so changing a clause from code never clashes with the widget."""
    st.markdown(
        "<style>[data-testid='stCheckbox'] p { white-space: normal !important; "
        "overflow-wrap: break-word !important; }</style>",
        unsafe_allow_html=True,
    )
    included = ensure_state(state_key)
    library = library_for(included)

    def grid(clauses, cols_per_row=3):
        for i in range(0, len(clauses), cols_per_row):
            cols = st.columns(cols_per_row)
            for col, c in zip(cols, clauses[i:i + cols_per_row]):
                with col:
                    key = checkbox_key(state_key, c.key)
                    st.session_state.setdefault(key, included[c.key])
                    included[c.key] = st.checkbox(c.title, key=key)

    standard = [c for c in library if not c.optional]
    optional = [c for c in library if c.optional]
    st.markdown("**Standard clauses**")
    st.caption(f"Included by default. Untick to remove one from this {noun}.")
    grid(standard)
    if optional:
        st.markdown("**Optional clauses**")
        st.caption(f"Not included by default. Tick to add one to this {noun}.")
        grid(optional)
    st.caption(f"{sum(included.values())} of {len(included)} clauses included.")


def render_preview(state_key, noun="draft", download=True, header=False):
    """Numbered preview of the selected clauses, with a Word download unless `download` is False. With `header` the
    contract header from the term sheet is shown above the clauses."""
    library = library_for(ensure_state(state_key), current_limits(), drafts.drafted_for_library())
    header_lines = build_header(st.session_state.get("term_sheet"))
    if header:
        with st.container(border=True):
            for style, text in header_lines:
                if style == "title":
                    st.markdown(f"**{plain(text)}**")
                elif style in ("centre", "para"):
                    st.write(plain(text))
                else:
                    st.write(plain(("\u2022 " if style == "bullet" else "") + text))
    rendered = renumber_and_render(library)
    st.subheader(f"Preview ({len(rendered)} clauses)")

    flagged = cross_reference_scan(library)
    if flagged:
        st.warning(f"{len(flagged)} reference(s) may point to a different clause than intended -- "
                   f"review before using this {noun}.")
        for key, text, mention in flagged:
            st.caption(f"{key}: `{mention}` in \u201c{plain(text[:80])}...\u201d")

    st.caption("  \u2192  ".join(f"{num}. {c.title}" for num, c, _ in rendered))

    selected_title = st.selectbox("View a clause", [c.title for _, c, _ in rendered],
                                  key=f"{state_key}_view")
    number, clause, items = next((n, c, i) for n, c, i in rendered if c.title == selected_title)
    with st.container(border=True):
        st.markdown(f"**{number}. {clause.title}**")
        for p in clause.plain_paragraphs:
            st.write(plain(p))
        for i, line in enumerate(items):
            if line.startswith("    "):
                st.caption(plain(line.strip()))
            else:
                st.write(plain(line))
            if i == 0:
                for table_data in clause.tables:
                    st.table([dict(zip(table_data["headers"], row)) for row in table_data["rows"]])
        if not items:
            for table_data in clause.tables:
                st.table([dict(zip(table_data["headers"], row)) for row in table_data["rows"]])

    if not download:
        return
    st.divider()
    buf = io.BytesIO()
    render_docx(library, buf, header=header_lines)
    buf.seek(0)
    st.download_button(
        f"Download {noun} as Word file",
        buf.getvalue(),
        file_name=f"contract_{noun}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{state_key}_download",
    )
