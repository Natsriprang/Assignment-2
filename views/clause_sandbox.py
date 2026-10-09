"""Clause sandbox components for the Draft contract workflow. The selection (clause key ->
included flag) lives in one session_state dict under `state_key`; the picker edits it and the
preview reads it, so they never disagree."""
import io
import re

import html

import streamlit as st

from core.clause_data import build_library
from core.clauses import cross_reference_scan
from core.clause_params import limits_of
from core.draft_state import library_for
from core.blanks import find_blanks
from core.fill import fill_warnings
from core.emphasis import party_names, segments
from core.header import build_header
from core.signatures import build_signature_block
from core.vat import vat_warning
from core.memo import build_memo
from core.memo_render import render_memo_docx
from core.render import render_docx
from core.renumber import renumber_and_render
from views.draft_steps import drafts, wording_state


def plain(text):
    """Escape markdown so placeholders like '[*]' render as literal text, not italic/link syntax."""
    return re.sub(r"([\\`*_\[\]#>|~$<])", r"\\\1", text)


def aligned(text, align, bold=False, names=()):
    """A paragraph with its alignment ("center", "right" or "justify"). The text is escaped as HTML, so a placeholder like [*] is shown as typed;
    defined terms in quotation marks and `names` are in bold."""
    body = "".join(f"<b>{html.escape(piece)}</b>" if strong or bold else html.escape(piece) for piece, strong in segments(text, names))
    st.markdown(f"<div style='text-align:{align}'>{body}</div>", unsafe_allow_html=True)


def current_limits():
    """The caps chosen on the term sheet (defaults if none were chosen)."""
    return limits_of(st.session_state.get("term_sheet"))


def show_table(table_data):
    """A table of a clause. A cell that runs over several lines needs a real HTML table to show them; the others keep st.table."""
    rows = table_data["rows"]
    if not any("\n" in cell for row in rows for cell in row):
        st.table([dict(zip(table_data["headers"], row)) for row in rows])
        return
    cell = ("border:1px solid rgba(128,128,128,0.35);padding:0.35rem 0.6rem;vertical-align:top;text-align:left;"
            "line-height:1.45")
    def td(tag, text):
        return f'<{tag} style="{cell}">{html.escape(text).replace(chr(10), "<br>")}</{tag}>'
    head = "<tr>" + "".join(td("th", h) for h in table_data["headers"]) + "</tr>"
    body = "".join("<tr>" + "".join(td("td", c) for c in row) + "</tr>" for row in rows)
    st.markdown(f'<table style="border-collapse:collapse;width:100%;font-size:0.9rem">{head}{body}</table>', unsafe_allow_html=True)


def current_term_sheet():
    return st.session_state.get("term_sheet")


def show_vat_notice():
    """The red notice that VAT is not chosen. Nothing is shown once it is."""
    ts = current_term_sheet()
    if ts is not None and vat_warning(ts):
        st.error("\u2757 " + vat_warning(ts))


def show_signature_block(block):
    """The closing sentence and one column per party, each line on its own line."""
    with st.container(border=True):
        st.markdown("**Signature block**")
        st.write(plain(block["closing"]))
        for column, party in zip(st.columns(len(block["parties"])), block["parties"]):
            with column:
                st.markdown("  \n".join((f"**{plain(line)}**" if n < 2 else plain(line)) if line else "\u00a0" for n, line in enumerate(party["lines"])))


def show_blanks(header_lines, rendered, ts, signature=None):
    """What is still blank in the draft and what the term sheet holds that the text could not show."""
    for w in fill_warnings(ts):
        st.warning(plain(w))
    blanks = find_blanks(header_lines, rendered, signature)
    if not blanks:
        st.success("No blanks left in the draft.")
        return
    st.warning(f"{len(blanks)} blank{'s' if len(blanks) != 1 else ''} ([*]) left in the draft. They appear as [*] in the "
               "Word file until they are filled.")
    with st.expander(f"Where the {len(blanks)} blank{'s are' if len(blanks) != 1 else ' is'}", expanded=True):
        for b in blanks:
            st.caption(plain(f"{b.where}: {b.context}"))


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
        now = library_for(included)                     # after the checkboxes above, so that it follows the ticks of this run
        numbered = {c.key: (n, c, items) for n, c, items in renumber_and_render(now)}
        for c in now:
            if c.parent and included.get(c.key):        # only while it is ticked: say where this optional clause is written
                host = numbered.get(c.parent)
                st.caption(f"{c.title}: " + (f"written as item {host[0]}.{len(host[2])} at the end of clause {host[0]}, {host[1].title}." if host
                                             else "not written, because the clause it belongs to is not in the draft."))
    st.caption(f"{sum(included.values())} of {len(included)} clauses included.")


def render_preview(state_key, noun="draft", download=True, header=False):
    """Numbered preview of the selected clauses, with a Word download unless `download` is False. With `header` the
    contract header from the term sheet is shown above the clauses."""
    library = library_for(ensure_state(state_key), current_limits(), drafts.drafted_for_library(), current_term_sheet(),
                          wording_state.applied())
    header_lines = build_header(st.session_state.get("term_sheet"))
    rendered = renumber_and_render(library)
    signature = build_signature_block(st.session_state.get("term_sheet")) if header else None
    st.subheader(f"Preview ({len(rendered)} clauses)")
    if header:
        show_blanks(header_lines, rendered, current_term_sheet(), signature)
        with st.container(border=True):
            recital = 0
            names = party_names(current_term_sheet())
            for style, text in header_lines:
                if style == "title":
                    aligned(text, "center", bold=True)
                elif style == "centre":
                    aligned(text, "center")
                elif style == "right":
                    aligned(text, "right")
                elif style == "numbered":
                    recital += 1
                    aligned(f"{recital}. {text}", "justify")
                else:
                    aligned(("\u2022 " if style == "bullet" else "") + text, "justify", names=names if style == "bullet" else ())

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
        for n, p in enumerate(clause.plain_paragraphs):
            aligned(p, "justify")
            if n == 0 and not items:                       # a clause without numbered items: its table follows its first paragraph
                for table_data in clause.tables:
                    show_table(table_data)
        for i, line in enumerate(items):
            if line.startswith("    "):
                st.caption(plain(line.strip()))
            else:
                aligned(line, "justify")
            if i == 0:
                for table_data in clause.tables:
                    show_table(table_data)
        if not items and not clause.plain_paragraphs:
            for table_data in clause.tables:
                show_table(table_data)

    if signature:
        show_signature_block(signature)

    if not download:
        return
    st.divider()
    download_button(state_key, noun, header)


def download_button(state_key, noun="draft", header=False):
    """The Word download of the draft as it stands (with its header and signature block when `header`)."""
    library = library_for(ensure_state(state_key), current_limits(), drafts.drafted_for_library(), current_term_sheet(),
                          wording_state.applied())
    header_lines = build_header(st.session_state.get("term_sheet"))
    signature = build_signature_block(st.session_state.get("term_sheet")) if header else None
    buf = io.BytesIO()
    render_docx(library, buf, header=header_lines, signature=signature, bold_names=party_names(st.session_state.get("term_sheet")))
    buf.seek(0)
    st.download_button(
        f"Download {noun} as Word file",
        buf.getvalue(),
        file_name=f"contract_{noun}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{state_key}_download",
    )


def memo_download_button(state_key):
    """The Word download of the internal approval memo that goes with the draft (core.memo); it is not part of the contract."""
    library = library_for(ensure_state(state_key), current_limits(), drafts.drafted_for_library(), current_term_sheet(),
                          wording_state.applied())
    buf = io.BytesIO()
    render_memo_docx(build_memo(st.session_state.get("term_sheet"), library), buf)
    buf.seek(0)
    st.download_button(
        "Download approval memo as Word file",
        buf.getvalue(),
        file_name="approval_memo.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        key=f"{state_key}_memo_download",
    )
