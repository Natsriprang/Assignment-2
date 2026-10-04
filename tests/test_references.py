"""Tests for the reference library, reference selection (with the fit field) and drafting.
`python -m tests.test_references` runs offline with a fake client (no key, no cost).
`python -m tests.test_references --live` also runs three cases against the real model:
a request the library covers, a request it does not, and one that shares a word with the wrong clauses."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.drafting import DRAFT_PROMPT, build_prompt, draft_clause, draft_schema, validate_draft
from ai.llm import AIStepError, CountingClient
from ai.references import (MAX_PICKS, MAX_RELATED, SELECT_PROMPT, Pick, Selection, select_references,
                           selection_schema, validate_selection)
from core.figures import numbers_in
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


def picks(*ids, related=()):
    """A selection payload: `ids` fit the request, `related` ids are related but a different subject."""
    items = [{"ref_id": i, "fit": "same_subject", "reason": f"fits: {i}"} for i in ids]
    items += [{"ref_id": i, "fit": "related", "reason": f"related only: {i}"} for i in related]
    return {"picks": items}


def draft_payload(*sentences, title="Warranty", notes=()):
    return {"title": title, "sentences": list(sentences), "notes": list(notes)}


def selection_of(*ids, related=()):
    return Selection("request", [Pick(i, "why") for i in ids] + [Pick(i, "why", "related") for i in related])


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


# ----------------------------------------------------------------------------- selection and fit
def test_selection_keeps_valid_ids_drops_unknown_and_duplicates():
    raw = picks("ca-6", "made-up", "ca-6", "epc-6")
    sel = validate_selection("req", raw, REFS)
    assert sel.ids() == ["ca-6", "epc-6"] and sel.found and any("made-up" in n for n in sel.notes)


def test_fitting_and_related_references_are_kept_apart():
    sel = validate_selection("req", picks("epc-6", related=["ca-11", "epc-12"]), REFS)
    assert sel.ids() == ["epc-6"] and [p.ref_id for p in sel.related] == ["ca-11", "epc-12"]
    assert sel.found and len(sel.picks) == 3


def test_only_related_references_means_nothing_to_draft_from():
    sel = validate_selection("req", picks(related=["ca-11", "epc-12"]), REFS)
    assert not sel.found and sel.ids() == [] and len(sel.related) == 2


def test_an_unclear_fit_is_treated_as_related():
    raw = {"picks": [{"ref_id": "ca-6", "fit": "maybe", "reason": "x"}, {"ref_id": "epc-6", "reason": "y"}]}
    sel = validate_selection("req", raw, REFS)
    assert not sel.found and [p.fit for p in sel.picks] == ["related", "related"]


def test_both_lists_are_capped_separately():
    raw = picks("ca-1", "ca-2", "ca-3", "ca-4", "ca-5", related=["ca-6", "ca-7", "ca-8", "ca-9"])
    sel = validate_selection("req", raw, REFS)
    assert len(sel.used) == MAX_PICKS and len(sel.related) == MAX_RELATED and len(sel.notes) == 2


def test_select_references_sends_catalogue_and_request_and_enforces_ids_and_fit():
    client = SequenceClient(picks("ca-6"))
    sel = select_references("add a two year warranty", REFS, client)
    sent = client.requests[0]
    assert "- ca-6 | CA (long version) | Guarantee" in sent["messages"][1]["content"]
    assert "add a two year warranty" in sent["messages"][1]["content"]
    props = sent["response_format"]["json_schema"]["schema"]["properties"]["picks"]["items"]["properties"]
    assert set(props["ref_id"]["enum"]) == set(REFS) and props["fit"]["enum"] == ["same_subject", "related"]
    assert sel.ids() == ["ca-6"]


def test_selection_prompt_explains_fit_and_does_not_discourage_short_requests():
    assert '"same_subject"' in SELECT_PROMPT and '"related"' in SELECT_PROMPT and "not used to draft" in SELECT_PROMPT
    assert "typos" in SELECT_PROMPT and "different word for the same subject" in SELECT_PROMPT
    assert "only when no entry is even related to the subject" in SELECT_PROMPT and "Do not stretch" not in SELECT_PROMPT


# ----------------------------------------------------------------------------- drafting
def test_draft_shows_plain_sentences_and_one_references_line_without_flags():
    raw = draft_payload("The Contractor warrants the Works for two (2) years.",
                        "The Contractor shall repair any defect within seven (7) days.")
    d = validate_draft("add a warranty", raw, selection_of("epc-6", "ca-6", "gov-8"), REFS)
    assert d.text == "The Contractor warrants the Works for two (2) years. The Contractor shall repair any defect within seven (7) days."
    assert d.references_line() == ("References used: EPC subcontract, clause 6: Warranty; "
                                   "CA (long version), clause 6: Guarantee; Thai government form, clause 8: Liability for defects")
    assert "[" not in d.references_line() and not any(ch in d.text for ch in "\u00b9\u00b2\u00b3\u2020\u2021")


def test_related_references_are_not_used_in_the_draft_or_the_references_line():
    sel = selection_of("epc-6", related=["ca-11"])
    d = validate_draft("add a warranty", draft_payload("Text."), sel, REFS)
    assert list(d.sources) == ["epc-6"] and "Inspection" not in d.references_line()
    prompt = build_prompt("add a warranty", sel, REFS)
    assert "Warranty" in prompt and "Inspection of works" not in prompt           # ca-11 is not sent to the drafting step


def test_no_reference_in_the_library_is_drafted_by_the_ai_and_has_no_references_line():
    """The fallback path, and a README test case: nothing in the library covers drone inspections."""
    request = "add a clause requiring a drone inspection of the roof before handover"
    client = SequenceClient(
        picks(related=["ca-11", "epc-12"]),                         # only same-word clauses, none fit
        draft_payload("Before handover the Contractor shall carry out a drone inspection of the roof.",
                      "The Contractor shall give the Owner the inspection images within [*] days.",
                      title="Drone inspection", notes=["Decide who pays for the inspection."]))
    sel = select_references(request, REFS, client)
    drafted = draft_clause(request, sel, REFS, client)
    assert not sel.found and drafted.sources == {} and drafted.references_line() == ""
    assert "(none: the library has nothing on this subject)" in client.requests[1]["messages"][1]["content"]
    assert [p.ref_id for p in drafted.selection.related] == ["ca-11", "epc-12"]


def test_draft_prompt_contains_only_fitting_references_with_issues_and_caveats():
    prompt = build_prompt("add a warranty", selection_of("ca-6"), REFS)
    assert "2 (Two) years" in prompt and "Known issues:" in prompt and "<source_caveats>" in prompt
    assert "- CA (long version):" in prompt and "Two-year warranty from the Project Owner" not in prompt   # epc-6 not selected


def test_draft_prompt_keeps_the_roles_in_the_request():
    assert "Keep the roles in the request" in DRAFT_PROMPT and "even if a reference gives that right to the Owner" in DRAFT_PROMPT


def test_draft_schema_is_plain_sentences():
    props = draft_schema()["properties"]
    assert props["sentences"]["items"] == {"type": "string"} and set(props) == {"title", "sentences", "notes"}


def test_empty_clause_raises():
    try:
        validate_draft("req", draft_payload("  ", ""), selection_of(), REFS)
    except AIStepError:
        return
    raise AssertionError("expected AIStepError")


# ----------------------------------------------------------------------------- counting and figures
def test_both_steps_are_counted_by_name():
    log = []
    client = SequenceClient(picks("ca-6"), draft_payload("Text."))
    sel = select_references("req", REFS, CountingClient(client, log, "select_references"))
    draft_clause("req", sel, REFS, CountingClient(client, log, "draft_clause"))
    assert [e["step"] for e in log] == ["select_references", "draft_clause"]


def test_figures_in_words_and_digits():
    assert numbers_in("a two-year warranty") == {2.0}
    assert numbers_in("a twenty-five day period") >= {20.0, 5.0, 25.0}
    assert numbers_in("within 7 (seven) days") == {7.0}
    assert numbers_in("no figures here") == set()


def test_schema_enums():
    assert set(selection_schema(REFS)["properties"]["picks"]["items"]["properties"]["ref_id"]["enum"]) == set(REFS)


# ----------------------------------------------------------------------------- live
LIVE_CASES = [
    ("A. the library covers it", "add warranty clause"),
    ("B. nothing in the library covers it", "add a clause requiring a drone inspection of the roof before handover"),
    ("C. shares a word with the wrong clauses (Owner's right to inspect)", "add a drone clause to observe the site. The contractor is responsible for the cost of this observation."),
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
            print(f"    {p.fit:<13} {p.ref_id}: {p.reason}")
        for n in sel.notes:
            print(f"    note: {n}")
        drafted = draft_clause(request, sel, REFS, client)
        print(f"    title: {drafted.title}\n    {drafted.text}")
        print(f"    {drafted.references_line() or '(no reference used)'}")
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
