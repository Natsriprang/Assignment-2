"""Clause sandbox component: toggle which clauses are included, preview the renumbered result,
download it as a Word file. Used by the Draft contract workflow (step 3) and by the standalone
Generate contract template page. Each use passes its own `state_key`, so their selections and
checkbox states never overlap."""
import io
import re

import streamlit as st

from core.clause_data import build_library
from core.clauses import cross_reference_scan
from core.render import render_docx
from core.renumber import renumber_and_render


def plain(text):
    """Escape markdown so placeholders like '[*]' render as literal text, not italic/link syntax."""
    return re.sub(r"([\\`*_\[\]#>|~$<])", r"\\\1", text)


def render(state_key, noun="draft"):
    """`state_key` names the session_state dict (clause key -> included) this instance edits."""
    st.markdown(
        "<style>[data-testid='stCheckbox'] p { white-space: normal !important; "
        "overflow-wrap: break-word !important; }</style>",
        unsafe_allow_html=True,
    )

    if state_key not in st.session_state:
        st.session_state[state_key] = {c.key: c.included for c in build_library()}
    included = st.session_state[state_key]

    library = build_library()
    for c in library:
        c.included = included.get(c.key, c.included)

    default_clauses = [c for c in library if not c.optional]
    optional_clauses = [c for c in library if c.optional]

    def checkbox_grid(clause_list, cols_per_row=3):
        for i in range(0, len(clause_list), cols_per_row):
            row = clause_list[i:i + cols_per_row]
            cols = st.columns(cols_per_row)
            for col, c in zip(cols, row):
                with col:
                    checked = st.checkbox(c.title, value=c.included, key=f"{state_key}_chk_{c.key}")
                    included[c.key] = checked

    st.subheader("Standard clauses")
    st.caption(f"Included by default. Untick to remove one from this {noun}.")
    checkbox_grid(default_clauses)

    if optional_clauses:
        st.subheader("Optional clauses")
        st.caption(f"Not included by default. Tick to add one to this {noun}.")
        checkbox_grid(optional_clauses)

    for c in library:
        c.included = included[c.key]

    st.divider()

    rendered = renumber_and_render(library)
    st.subheader(f"Preview ({len(rendered)} clauses)")

    flagged = cross_reference_scan(library)
    if flagged:
        st.warning(f"{len(flagged)} reference(s) may point to a different clause than intended -- "
                   f"review before using this {noun}.")
        with st.expander("Show flagged references"):
            for key, text, mention in flagged:
                st.markdown(f"**{key}**: `{mention}` in \u201c{plain(text[:80])}...\u201d")

    numbers_line = "  \u2192  ".join(f"{num}. {c.title}" for num, c, _ in rendered)
    st.caption(numbers_line)

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

    st.divider()
    buf = io.BytesIO()
    render_docx(library, buf)
    buf.seek(0)
    st.download_button(
        f"Download {noun} as Word file",
        buf.getvalue(),
        file_name=f"contract_{noun}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{state_key}_download",
    )
