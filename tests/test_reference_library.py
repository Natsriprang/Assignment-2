"""Checks the reference library files under data/reference/. Run: python -m tests.test_reference_library"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clause_data import build_library

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"
REQUIRED = {"id", "article", "title", "category", "our_clause", "gap", "quality_notes", "text"}
CONFIDENTIAL = re.compile(
    r"Tharong|Surat Thani|1,582,500|Cement Plant|TP&T|Vibhavadi|Chatuchak|\bHQ2\b|\bASO\b|"
    r"3,650,000|2,000,000|1,650,000|\b\d{3},\d{3}\b|30 August 2023|2 July 2024|@", re.I)


def load_all():
    files = sorted(REFERENCE_DIR.glob("*.json"))
    assert files, "no reference files found"
    return [(f.name, json.loads(f.read_text(encoding="utf-8"))) for f in files]


def test_files_have_source_metadata():
    for name, doc in load_all():
        for key in ("id", "title", "provenance", "rights_note", "language", "governing_law",
                    "differences_from_target", "clauses"):
            assert doc.get(key), f"{name}: missing {key}"


def test_every_clause_has_the_required_fields():
    for name, doc in load_all():
        for c in doc["clauses"]:
            assert REQUIRED <= set(c), f"{name}/{c.get('id')}: missing {REQUIRED - set(c)}"
            assert c["text"].strip(), f"{name}/{c['id']}: empty text"
            assert isinstance(c["gap"], bool) and isinstance(c["quality_notes"], list)


def test_ids_are_unique_across_the_library():
    ids = [c["id"] for _, doc in load_all() for c in doc["clauses"]]
    assert len(ids) == len(set(ids))


def test_our_clause_points_to_a_real_clause_or_none():
    keys = {c.key for c in build_library()}
    for name, doc in load_all():
        for c in doc["clauses"]:
            assert c["our_clause"] is None or c["our_clause"] in keys, f"{name}/{c['id']}: {c['our_clause']}"


def test_no_confidential_strings_or_markup_left():
    for name, doc in load_all():
        for c in doc["clauses"]:
            assert not CONFIDENTIAL.search(c["text"]), f"{name}/{c['id']}: confidential string"
            assert not re.search(r"(?<!\[)\*(?!\])", c["text"]), f"{name}/{c['id']}: markdown residue"


def test_similarity_scores_are_fractions():
    for name, doc in load_all():
        for c in doc["clauses"]:
            if "similarity_to_ours" in c:
                assert c["our_clause"] and 0 <= c["similarity_to_ours"] <= 1, f"{name}/{c['id']}"


def test_thai_government_form():
    doc = dict(load_all())["th_gov_construction_contract.json"]
    by = {c["id"]: c for c in doc["clauses"]}
    assert len(doc["clauses"]) == 27 and doc["version_note"]
    assert doc["translation"]["reviewed_by_a_lawyer"] is False and "GPT" in doc["provenance"]
    assert any("penalty" in n for n in by["gov-17"]["quality_notes"])
    for cid in ("gov-3", "gov-5", "gov-6", "gov-8", "gov-9", "gov-11", "gov-16", "gov-19", "gov-20"):
        assert by[cid]["gap"] is True, cid                                             # topics the app's template lacks
    assert "0.10%" in by["gov-notes"]["text"] and "two years" in by["gov-notes"]["text"]
    assert "Force Majeure" in by["gov-11"]["text"]
    assert by["gov-22"]["category"] == "public_procurement" and by["gov-23"]["category"] == "public_procurement"
    assert "4A" in {c["article"] for c in doc["clauses"]} and "7B" in {c["article"] for c in doc["clauses"]}


def test_ca_long_version():
    doc = dict(load_all())["ca_long_version.json"]
    by = {c["id"]: c for c in doc["clauses"]}
    assert len(doc["clauses"]) == 17 and sum(s["count"] for s in doc["scrubs"]) == 2
    assert "[ADDRESS]" in by["ca-preamble"]["text"]
    assert by["ca-6"]["gap"] is True and "2 (Two) years" in by["ca-6"]["text"]
    assert "0.05 percent per day" in by["ca-3"]["text"]
    assert "zero point one" in by["ca-7"]["text"] and "0.01" in by["ca-7"]["text"]      # figure and words disagree in the source
    assert by["ca-4"]["similarity_to_ours"] > 0.9                                    # same wording as the app's clause


def test_epc_subcontract():
    doc = dict(load_all())["epc_subcontract_agreement.json"]
    by = {c["id"]: c for c in doc["clauses"]}
    assert len(doc["clauses"]) == 19 and sum(s["count"] for s in doc["scrubs"]) == 17
    assert "[AMOUNT]" in by["epc-3"]["text"] and "five percent (5%)" in by["epc-3"]["text"]
    assert "[BUILDING A]" in by["epc-3"]["text"] and "[BUILDING B]" in by["epc-3"]["text"]
    assert by["epc-3"]["text"].count("| Installment |") == 1 and doc["edits"]
    assert "[START DATE]" in by["epc-7"]["text"] and "[COMPLETION DATE]" in by["epc-7"]["text"]
    assert by["epc-6"]["gap"] is True and "two (2) years" in by["epc-6"]["text"]


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} reference library tests passed.")
