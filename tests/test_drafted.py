"""Tests for drafted new clauses becoming real, numbered clauses. Run: python -m tests.test_drafted"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document

from core.clause_data import build_library
from core.clauses import cross_reference_scan
from core.draft_state import library_for
from core.drafted import insert_drafted, make_clause
from core.render import render_docx
from core.renumber import renumber_and_render

WARRANTY = {"key": "drafted_1", "title": "Warranty", "before": "force_majeure",
            "sentences": ["The Contractor warrants the System for [*].", "The Contractor shall repair any defect promptly."]}


def titles(library):
    return [(n, c.title) for n, c, _ in renumber_and_render(library)]


def position(library, title):
    return [t for _, t in titles(library)].index(title)


def test_a_draft_becomes_a_clause_with_numbered_items():
    c = make_clause("drafted_1", "Warranty", ["First.", "Second."])
    assert c.key == "drafted_1" and c.included and [i.text for i in c.items] == ["First.", "Second."]
    rendered = renumber_and_render([c])
    assert rendered[0][2] == ["1.1 First.", "1.2 Second."]


def test_it_is_inserted_before_the_chosen_clause_and_numbering_follows():
    library = library_for({}, None, [WARRANTY])
    t = titles(library)
    assert position(library, "Warranty") == position(library, "Force Majeure") - 1
    number, title = t[position(library, "Warranty")]
    assert title == "Warranty" and t[position(library, "Force Majeure")][0] == str(int(number) + 1)
    assert [i for i in renumber_and_render(library) if i[1].title == "Warranty"][0][2][0] == f"{number}.1 The Contractor warrants the System for [*]."


def test_any_existing_clause_can_be_the_target():
    for target, title in (("suspension", "Suspension of Works"), ("termination", "Breach and Termination"), ("notice", "Notice")):
        library = library_for({}, None, [{**WARRANTY, "before": target}])
        assert position(library, "Warranty") == position(library, title) - 1


def test_end_puts_it_last():
    library = library_for({}, None, [{**WARRANTY, "before": "end"}])
    assert titles(library)[-1][1] == "Warranty"


def test_a_missing_target_falls_back_to_force_majeure_then_notice_then_the_end():
    library = library_for({}, None, [{**WARRANTY, "before": "no_such_clause"}])
    assert position(library, "Warranty") == position(library, "Force Majeure") - 1
    library = build_library()
    library = [c for c in library if c.key != "force_majeure"]
    insert_drafted(library, [{**WARRANTY, "before": "gone"}])
    assert [c.key for c in library].index("drafted_1") == [c.key for c in library].index("notice") - 1
    library = [c for c in library if c.key not in ("notice", "drafted_1")]
    insert_drafted(library, [{**WARRANTY, "before": "gone"}])
    assert library[-1].key == "drafted_1"


def test_a_target_that_is_switched_off_still_works():
    library = library_for({"force_majeure": False}, None, [WARRANTY])
    assert position(library, "Warranty") == position(library, "Notice") - 1          # next visible clause after it


def test_several_drafts_with_the_same_target_keep_their_order():
    second = {**WARRANTY, "key": "drafted_2", "title": "Indemnity"}
    library = library_for({}, None, [WARRANTY, second])
    assert position(library, "Warranty") + 1 == position(library, "Indemnity") == position(library, "Force Majeure") - 1


def test_inserting_before_an_early_clause_keeps_the_clause_own_cross_references_right():
    plain = renumber_and_render(library_for({}))
    base = {c.key: n for n, c, _ in plain}
    library = library_for({}, None, [{**WARRANTY, "before": "suspension"}])
    shifted = {c.key: (n, items) for n, c, items in renumber_and_render(library)}
    number, items = shifted["termination"]
    assert int(number) == int(base["termination"]) + 1
    assert any(f"clause {number}.1" in line for line in items)                           # "clause 12.1" became "clause 13.1"
    assert not any(f"clause {base['termination']}.1" in line for line in items)


def test_a_reference_to_another_clause_inside_a_draft_is_flagged():
    library = library_for({}, None, [{**WARRANTY, "sentences": ["As set out in clause 3.2 the Contractor shall repair."]}])
    flagged = cross_reference_scan(library)
    assert [(k, m) for k, _, m in flagged] == [("drafted_1", "clause 3.2")]


def test_the_word_file_contains_the_drafted_clause_in_place():
    library = library_for({}, None, [WARRANTY])
    buf = io.BytesIO()
    render_docx(library, buf)
    buf.seek(0)
    lines = [p.text for p in Document(buf).paragraphs if p.text.strip()]
    headings = [l for l in lines if "\t" in l]
    assert any(h.endswith("\tWarranty") for h in headings)
    assert any(l.endswith("The Contractor warrants the System for [*].") for l in lines)
    assert headings.index(next(h for h in headings if h.endswith("\tWarranty"))) + 1 == \
           headings.index(next(h for h in headings if h.endswith("\tForce Majeure")))


def test_without_drafts_the_library_is_unchanged():
    assert [c.key for c in library_for({}, None, [])] == [c.key for c in build_library()]
    assert [c.key for c in library_for({})] == [c.key for c in build_library()]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} drafted clause tests passed.")
