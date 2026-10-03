"""Clause sandbox: toggle which clauses are included, preview the renumbered draft, download it."""
import io
import re

import streamlit as st

from clause_data import build_library
from clauses import cross_reference_scan
from renumber import renumber_and_render
from render import render_docx


def plain(text):
    """Escape markdown so placeholders like '[*]' render as literal text, not italic/link syntax."""
    return re.sub(r"([\\`*_\[\]#>|~$<])", r"\\\1", text)


st.markdown(
    "<style>[data-testid='stCheckbox'] p { white-space: normal !important; "
    "overflow-wrap: break-word !important; }</style>",
    unsafe_allow_html=True,
)

st.title("\U0001f9f0 Clause Sandbox")
st.caption("Choose which clauses to include in the draft.")

if "included" not in st.session_state:
    st.session_state.included = {c.key: c.included for c in build_library()}

library = build_library()
for c in library:
    c.included = st.session_state.included.get(c.key, c.included)

default_clauses = [c for c in library if not c.optional]
optional_clauses = [c for c in library if c.optional]


def checkbox_grid(clause_list, cols_per_row=3):
    for i in range(0, len(clause_list), cols_per_row):
        row = clause_list[i:i + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, c in zip(cols, row):
            with col:
                checked = st.checkbox(c.title, value=c.included, key=f"chk_{c.key}")
                st.session_state.included[c.key] = checked


st.subheader("Standard clauses")
st.caption("Included by default. Untick to remove one from this draft.")
checkbox_grid(default_clauses)

if optional_clauses:
    st.subheader("Optional clauses")
    st.caption("Not included by default. Tick to add one to this draft.")
    checkbox_grid(optional_clauses)

for c in library:
    c.included = st.session_state.included[c.key]

st.divider()

rendered = renumber_and_render(library)
st.subheader(f"Preview ({len(rendered)} clauses)")

flagged = cross_reference_scan(library)
if flagged:
    st.warning(f"{len(flagged)} reference(s) may point to a different clause than intended -- "
               "review before using this draft.")
    with st.expander("Show flagged references"):
        for key, text, mention in flagged:
            st.markdown(f"**{key}**: `{mention}` in \u201c{plain(text[:80])}...\u201d")

numbers_line = "  \u2192  ".join(f"{num}. {c.title}" for num, c, _ in rendered)
st.caption(numbers_line)

selected_title = st.selectbox("View a clause", [c.title for _, c, _ in rendered])
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

st.divider()
buf = io.BytesIO()
render_docx(library, buf)
buf.seek(0)
st.download_button(
    "Download draft as Word file",
    buf.getvalue(),
    file_name="contract_draft.docx",
    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)