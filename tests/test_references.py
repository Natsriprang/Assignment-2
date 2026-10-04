"""Tests for the reference library, reference selection and footnoted drafting.
`python -m tests.test_references` runs offline with a fake client (no key, no cost).
`python -m tests.test_references --live` also runs two cases against the real model:
one where the library has references and one where it has none."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.drafting import (AI_NOTE, NO_SOURCE, build_prompt, draft_clause, draft_schema, figures_not_in, numbers_in,
                         render_footnoted, superscript, unsupported_numbers, validate_draft)
from ai.llm import AIStepError, CountingClient
from ai.references import MAX_PICKS, Selection, Pick, select_references, selection_schema, validate_selection
from core.reference_library import catalogue_lines, load_references

REFS = load_references()


class SequenceClient:
    """Returns the queued payloads in order, one per call, and records every request."""
    def __init__(self, *payloads):
        self.payloads, self.requests = list(payloads), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.requests.append(kwargs)
        msg = SimpleNamespace(content=json.dumps(self.payloads.pop(0)), refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


def picks(*ids):
    return {"picks": [{"ref_id": i, "reason": f"relevant: {i}"} for i in ids]}


def sentence(text, ids, basis="adapted"):
    return {"text": text, "source_ids": ids, "basis": basis}


def draft_payload(*sentences, title="Warranty", notes=()):
    return {"title": title, "sentences": list(sentences), "notes": list(notes)}


def selection_of(*ids):
    return Selection("request", [Pick(i, "why") for i in ids])


# ----------------------------------------------------------------------------- library
def test_library_loads_all_documents_without_preambles():
    assert len(REFS) == 60 and len({r.doc_id for r in REFS.values()}) == 3
    assert not [r for r in REFS.values() if r.category == "preamble"]
    assert REFS["ca-6"].label == "CA (long version), clause 6: Guarantee"
    assert REFS["gov-notes"].label == "Thai government form, notes on the form: Notes on the use of the form"
    assert REFS["ca-6"].flags == ["not public"] and REFS["gov-8"].flags == ["machine translation"]


def test_catalogue_has_one_short_line_per_entry():
    lines = catalogue_lines(REFS).split("\n")
    assert len(lines) == 60 and all(l.startswith("- ") for l in lines)
    assert len(catalogue_lines(REFS)) < 25000                      # well inside one prompt
    assert "seven (7) days" not in catalogue_lines(REFS)            # the full text of epc-6 is not in the index


# ----------------------------------------------------------------------------- selection
def test_selection_keeps_valid_ids_drops_unknown_and_duplicates():
    raw = picks("ca-6", "made-up", "ca-6", "epc-6")
    sel = validate_selection("req", raw, REFS)
    assert sel.ids() == ["ca-6", "epc-6"] and sel.found and any("made-up" in n for n in sel.notes)


def test_selection_is_capped():
    raw = picks("ca-1", "ca-2", "ca-3", "ca-4", "ca-5", "ca-6")
    sel = validate_selection("req", raw, REFS)
    assert len(sel.picks) == MAX_PICKS and sel.notes


def test_selection_prompt_does_not_discourage_short_requests_or_other_wording():
    from ai.references import SELECT_PROMPT
    assert "typos" in SELECT_PROMPT and "different word for the same subject" in SELECT_PROMPT
    assert "only when no entry is about the subject at all" in SELECT_PROMPT
    assert "Do not stretch" not in SELECT_PROMPT


def test_empty_selection_is_not_found():
    assert not validate_selection("req", {"picks": []}, REFS).found


def test_select_references_sends_catalogue_and_request_and_enforces_ids():
    client = SequenceClient(picks("ca-6"))
    sel = select_references("add a two year warranty", REFS, client)
    sent = client.requests[0]
    assert "- ca-6 | CA (long version) | Guarantee" in sent["messages"][1]["content"]
    assert "add a two year warranty" in sent["messages"][1]["content"]
    enum = sent["response_format"]["json_schema"]["schema"]["properties"]["picks"]["items"]["properties"]["ref_id"]["enum"]
    assert set(enum) == set(REFS) and sel.ids() == ["ca-6"]


# ----------------------------------------------------------------------------- drafting with references
def test_footnotes_are_numbers_only_numbered_by_first_use_and_reused():
    raw = draft_payload(
        sentence("The Contractor warrants the Works for two (2) years.", ["epc-6"]),
        sentence("The Contractor shall keep the roof clean.", ["ca-6", "epc-6"]),
        sentence("The Contractor shall return the keys.", ["ca-6"]))
    d = validate_draft("add a two-year warranty and keep the roof clean and return the keys", raw, selection_of("ca-6", "epc-6"), REFS)
    text, lines = render_footnoted(d)
    assert text == ("The Contractor warrants the Works for two (2) years.\u00b9 "
                    "The Contractor shall keep the roof clean.\u00b2,\u00b9 "
                    "The Contractor shall return the keys.\u00b2")
    assert [l[:1] for l in lines] == ["\u00b9", "\u00b2"]
    assert lines[0].startswith("\u00b9 EPC subcontract, clause 6: Warranty") and "[not public]" in lines[0]
    assert lines[1].startswith("\u00b2 CA (long version), clause 6: Guarantee")
    assert not any(ch in text + " ".join(lines) for ch in ("\u2020", "\u2021"))          # no dagger or double-dagger


def test_a_sentence_without_a_reference_gets_a_numbered_note_saying_the_ai_wrote_it():
    raw = draft_payload(sentence("The Contractor warrants the Works.", ["epc-6"]),
                        sentence("The Contractor shall indemnify the Owner.", [NO_SOURCE], "ai_written"),
                        sentence("The Contractor shall insure the Works.", [NO_SOURCE], "ai_written"))
    d = validate_draft("add a warranty, an indemnity and insurance", raw, selection_of("epc-6"), REFS)
    text, lines = render_footnoted(d)
    assert text.endswith("insure the Works.\u00b2") and "indemnify the Owner.\u00b2" in text       # the AI note is shared
    assert lines[1] == "\u00b2 " + AI_NOTE


def test_unknown_citation_is_dropped_and_sentence_gets_the_ai_note():
    raw = draft_payload(sentence("The Contractor shall indemnify the Owner.", ["gov-11"]))
    d = validate_draft("add an indemnity", raw, selection_of("ca-6"), REFS)
    s = d.sentences[0]
    assert s.source_ids == [] and s.basis == "ai_written" and not d.has_references
    assert any("gov-11" in n for n in d.notes)
    assert render_footnoted(d)[0].endswith("\u00b9") and render_footnoted(d)[1] == ["\u00b9 " + AI_NOTE]


def test_basis_ai_written_with_a_valid_citation_is_treated_as_adapted():
    d = validate_draft("req", draft_payload(sentence("Text.", ["ca-6"], "ai_written")), selection_of("ca-6"), REFS)
    assert d.sentences[0].basis == "adapted"


# ----------------------------------------------------------------------------- figures written in words
def test_a_figure_written_in_words_in_the_request_counts_as_given():
    raw = draft_payload(sentence("The Contractor warrants the System for two (2) years.", [NO_SOURCE], "ai_written"))
    d = validate_draft("add a two-year warranty", raw, selection_of(), REFS)
    assert d.sentences[0].unsupported_numbers == [] and render_footnoted(d)[1] == ["\u00b9 " + AI_NOTE]
    assert numbers_in("a twenty-five day period") >= {20.0, 5.0, 25.0}
    assert figures_not_in("within 30 (thirty) days", ["add thirty days"]) == []
    assert figures_not_in("within 30 (thirty) days", ["add a warranty"]) == ["30"]


# ----------------------------------------------------------------------------- no reference in the library
def test_no_reference_in_the_library_is_drafted_by_the_ai_and_noted():
    """The fallback path, and a README test case: nothing in the library covers drone inspections."""
    request = "add a clause requiring a drone inspection of the roof before handover"
    client = SequenceClient(
        picks(),                                                                                   # selection finds nothing
        draft_payload(sentence("Before handover the Contractor shall carry out a drone inspection of the roof.", [NO_SOURCE], "ai_written"),
                      sentence("The Contractor shall give the Owner the inspection images within [*] days.", [NO_SOURCE], "ai_written"),
                      title="Drone inspection", notes=["Decide who pays for the inspection."]))
    sel = select_references(request, REFS, client)
    drafted = draft_clause(request, sel, REFS, client)
    assert not sel.found and not drafted.has_references and drafted.sources == {}
    assert all(s.basis == "ai_written" for s in drafted.sentences)
    schema = client.requests[1]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["sentences"]["items"]["properties"]["source_ids"]["items"]["enum"] == [NO_SOURCE]
    assert "(none: the library has nothing on this subject)" in client.requests[1]["messages"][1]["content"]
    text, lines = render_footnoted(drafted)
    assert text.count("\u00b9") == 2 and lines == ["\u00b9 " + AI_NOTE]


def test_draft_prompt_contains_only_selected_references_with_issues_and_caveats():
    prompt = build_prompt("add a warranty", selection_of("ca-6"), REFS)
    assert '<reference id="ca-6"' in prompt and "2 (Two) years" in prompt
    assert "Known issues:" in prompt and "<source_caveats>" in prompt and "- CA (long version):" in prompt
    assert 'id="epc-6"' not in prompt


# ----------------------------------------------------------------------------- figures written in words
def test_a_figure_written_in_words_in_the_request_counts_as_given():
    raw = draft_payload(sentence("The Contractor warrants the System for two (2) years.", [NO_SOURCE], "ai_written"))
    d = validate_draft("add a two-year warranty", raw, selection_of(), REFS)
    assert d.sentences[0].unsupported_numbers == [] and render_footnoted(d)[1] == ["\u00b9 " + AI_NOTE]
    assert numbers_in("a twenty-five day period") >= {20.0, 5.0, 25.0}
    assert figures_not_in("within 30 (thirty) days", ["add thirty days"]) == []
    assert figures_not_in("within 30 (thirty) days", ["add a warranty"]) == ["30"]


# ----------------------------------------------------------------------------- no reference in the library
def test_no_reference_in_the_library_is_drafted_by_the_ai_and_noted():
    """The fallback path, and a README test case: nothing in the library covers drone inspections."""
    request = "add a clause requiring a drone inspection of the roof before handover"
    client = SequenceClient(
        picks(),                                                                                   # selection finds nothing
        draft_payload(sentence("Before handover the Contractor shall carry out a drone inspection of the roof.", [NO_SOURCE], "ai_written"),
                      sentence("The Contractor shall give the Owner the inspection images within [*] days.", [NO_SOURCE], "ai_written"),
                      title="Drone inspection", notes=["Decide who pays for the inspection."]))
    sel = select_references(request, REFS, client)
    drafted = draft_clause(request, sel, REFS, client)
    assert not sel.found and not drafted.has_references and drafted.sources == {}
    assert all(s.basis == "ai_written" for s in drafted.sentences)
    schema = client.requests[1]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["sentences"]["items"]["properties"]["source_ids"]["items"]["enum"] == [NO_SOURCE]
    assert "(none: the library has nothing on this subject)" in client.requests[1]["messages"][1]["content"]
    text, lines = render_footnoted(drafted)
    assert text.count("\u00b9") == 2 and lines == ["\u00b9 " + AI_NOTE]


def test_draft_prompt_contains_only_selected_references_with_issues_and_caveats():
    prompt = build_prompt("add a warranty", selection_of("ca-6"), REFS)
    assert '<reference id="ca-6"' in prompt and "2 (Two) years" in prompt
    assert "Known issues:" in prompt and "<source_caveats>" in prompt and "- CA (long version):" in prompt
    assert 'id="epc-6"' not in prompt


# ----------------------------------------------------------------------------- figures
def test_unsupported_figures_are_flagged_with_a_numbered_note():
    assert unsupported_numbers("Repair within 7 days.", "add warranty", [REFS["ca-6"].text]) == []        # 7 is in ca-6
    assert unsupported_numbers("Repair within 10 days.", "add warranty", [REFS["ca-6"].text]) == ["10"]
    assert unsupported_numbers("Interest of 1.5 percent.", "interest of 1.50 percent", []) == []          # 1.5 == 1.50
    assert unsupported_numbers("Pay within 30 days.", "any request", []) == ["30"]
    raw = draft_payload(sentence("The Contractor shall repair defects within 10 days.", ["ca-6"]))
    d = validate_draft("add a warranty", raw, selection_of("ca-6"), REFS)
    text, lines = render_footnoted(d)
    assert d.sentences[0].unsupported_numbers == ["10"] and "\u00b9,\u00b2" in text
    assert lines[1] == "\u00b2 Contains the figure 10, which is not in your request or in the cited references."


def test_superscript_numbers():
    assert superscript(1) == "\u00b9" and superscript(12) == "\u00b9\u00b2" and superscript(30) == "\u00b3\u2070"


# ----------------------------------------------------------------------------- errors and counting
def test_empty_clause_raises():
    try:
        validate_draft("req", draft_payload(sentence("  ", [NO_SOURCE], "ai_written")), selection_of(), REFS)
    except AIStepError:
        return
    raise AssertionError("expected AIStepError")


def test_both_steps_are_counted_by_name():
    log = []
    client = SequenceClient(picks("ca-6"), draft_payload(sentence("Text.", ["ca-6"])))
    sel = select_references("req", REFS, CountingClient(client, log, "select_references"))
    draft_clause("req", sel, REFS, CountingClient(client, log, "draft_clause"))
    assert [e["step"] for e in log] == ["select_references", "draft_clause"]


def test_schema_enums():
    assert set(selection_schema(REFS)["properties"]["picks"]["items"]["properties"]["ref_id"]["enum"]) == set(REFS)
    props = draft_schema(["ca-6", "epc-6"])["properties"]["sentences"]["items"]["properties"]
    assert props["source_ids"]["items"]["enum"] == ["ca-6", "epc-6"] and "origin" not in props


# ----------------------------------------------------------------------------- live
LIVE_CASES = [
    ("A. library has references", "add a two-year warranty on the installation and late-payment interest on overdue instalments"),
    ("B. no reference in the library", "add a clause requiring a drone inspection of the roof before handover"),
]


def run_live():
    from ai.llm import get_client
    client = get_client()
    if client is None:
        sys.exit("Set OPENAI_API_KEY (or put it in .env) to run live cases.")
    for name, request in LIVE_CASES:
        print(f"\n=== {name}\n    request: {request}")
        sel = select_references(request, REFS, client)
        for p in sel.picks:
            print(f"    picked {p.ref_id}: {p.reason}")
        if not sel.found:
            print("    no reference selected")
        drafted = draft_clause(request, sel, REFS, client)
        text, lines = render_footnoted(drafted)
        print(f"    title: {drafted.title}\n    {text}")
        for line in lines:
            print(f"    {line}")
        for n in drafted.notes:
            print(f"    note: {n}")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} reference and drafting tests passed.")
    if "--live" in sys.argv:
        run_live()
