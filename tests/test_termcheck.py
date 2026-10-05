"""Tests for the AI term sheet check (offline, with a fake client). Run: python -m tests.test_termcheck"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.interpret import term_sheet_text
from ai.llm import AIStepError, CountingClient
from ai.termcheck import CHECK_PROMPT, FIELDS, MAX_ISSUES, check_schema, check_term_sheet, validate_check
from core.term_sheet_fields import TermSheet


class Client:
    """Queued replies: a dict is returned as JSON, an Exception is raised."""
    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.requests.append(kw)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        msg = SimpleNamespace(content=json.dumps(reply), refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")])


TS = TermSheet(project_name="Rooftop PV", contract_price_number="10,000,000", contract_price_words="five million baht",
               start_date="1 Nov 2026", completion_date="150 days")


def issue(field, problem, evidence):
    return {"field": field, "problem": problem, "evidence": evidence}


def test_a_point_with_a_real_field_and_a_real_quote_is_kept():
    c = check_term_sheet(TS, Client({"issues": [issue("contract_price_words", "The words do not match the number.", "five million baht")]}))
    assert [(i.field, i.evidence) for i in c.issues] == [("contract_price_words", "five million baht")] and c.notes == []


def test_a_quote_that_is_not_in_the_term_sheet_is_dropped():
    text = term_sheet_text(TS)
    raw = {"issues": [issue("start_date", "Looks like a date.", "1 November 2026"), issue("start_date", "Looks like a date.", "1 Nov 2026")]}
    c = validate_check(raw, text)
    assert len(c.issues) == 1 and c.issues[0].evidence == "1 Nov 2026" and len(c.notes) == 1


def test_whitespace_and_case_do_not_hide_a_real_quote():
    assert len(validate_check({"issues": [issue("project_name", "x", "  ROOFTOP   pv ")]}, term_sheet_text(TS)).issues) == 1


def test_unknown_fields_and_empty_points_are_dropped():
    raw = {"issues": [issue("made_up_field", "p", "Rooftop PV"), issue("project_name", "", "Rooftop PV"), issue("project_name", "p", "")]}
    c = validate_check(raw, term_sheet_text(TS))
    assert c.issues == [] and len(c.notes) == 3


def test_duplicates_are_merged_and_the_list_is_capped():
    same = issue("project_name", "Same point.", "Rooftop PV")
    assert len(validate_check({"issues": [same, same]}, term_sheet_text(TS)).issues) == 1
    many = {"issues": [issue("project_name", f"Point {i}.", "Rooftop PV") for i in range(MAX_ISSUES + 3)]}
    c = validate_check(many, term_sheet_text(TS))
    assert len(c.issues) == MAX_ISSUES and any("kept the first" in n for n in c.notes)


def test_nothing_wrong_is_an_empty_list():
    c = check_term_sheet(TS, Client({"issues": []}))
    assert c.issues == [] and c.notes == []


def test_the_prompt_and_schema():
    low = CHECK_PROMPT.lower()
    for word in ("thai", "rooftop", "solar", "agreement", "contract ", "draft the", "construction", "deadline_mode", "start_days"):
        assert word not in low, f"the check prompt must be about the term sheet only, not about {word!r}"
    assert "wrong kind for its field" in low and "never report" in low and "plausible" in low
    assert "<notes>" in low and "breaks, in meaning, the note" in low
    assert "never count characters or digits yourself" in low and "code checks counts, lengths, digits" in low   # counting is code's job
    assert "country in the place field" not in low and "contradict each other" not in low
    enum = check_schema()["properties"]["issues"]["items"]["properties"]["field"]["enum"]
    assert enum == FIELDS and "limits" not in FIELDS and "installments" in FIELDS and "payment_days" in FIELDS
    assert "start_days" not in FIELDS and "owner_contact_email" in FIELDS and "contractor_contact_email" in FIELDS
    client = Client({"issues": []})
    check_term_sheet(TS, client)
    sent = client.requests[0]["messages"]
    assert "<term_sheet>" in sent[1]["content"] and "start_date: 1 Nov 2026" in sent[1]["content"]
    assert "<notes>" not in sent[1]["content"], "no notes to give, no notes block"
    props = check_schema()["properties"]["issues"]["items"]
    assert "rule" in props["properties"] and "rule" in props["required"]


def test_notes_are_given_to_the_ai_only_when_they_are_about_meaning_and_not_already_checked():
    from ai.termcheck import notes_text
    ts = TermSheet(owner_signatory="Nat", owner_reg_no="1020304050601", contract_no="UM123426", contract_date="3 October 2026",
                   roof_owner="", contract_price_words="One-hundred Thousand", start_date="3 October 2026")
    notes = {"owner_signatory": "Full name(s), matching the company's signing authority", "owner_reg_no": "13 digits",
             "contract_no": "8 digits: first 2 start from 01", "contract_date": "Must be consistent with the last 6 digits of the contract no.",
             "roof_owner": "Name of the roof owner", "contract_price_words": "2 decimal places", "start_date": "DD Month YYYY",
             "vat_treatment": "inclusive / exclusive", "contractor_signatory": "Full name(s)"}
    assert notes_text(ts, notes) == "owner_signatory: Full name(s), matching the company's signing authority"
    client = Client({"issues": []})
    check_term_sheet(ts, client, notes=notes)
    sent = client.requests[0]["messages"][1]["content"]
    assert sent.endswith("<notes>\nowner_signatory: Full name(s), matching the company's signing authority\n</notes>")
    assert "13 digits" not in sent and "2 decimal places" not in sent


def test_a_point_that_quotes_a_note_must_quote_a_real_one():
    ts = TermSheet(owner_signatory="Nat")
    notes = {"owner_signatory": "Full name(s), matching the company's signing authority"}
    given = "owner_signatory: Full name(s), matching the company's signing authority"
    good = {"issues": [issue("owner_signatory", "Looks like a first name only.", "Nat")]}
    good["issues"][0]["rule"] = "Full name(s), matching the company's signing authority"
    c = validate_check(good, term_sheet_text(ts), given)
    assert [(i.field, i.rule) for i in c.issues] == [("owner_signatory", "Full name(s), matching the company's signing authority")]
    bad = {"issues": [dict(good["issues"][0], rule="Must be exactly two words")]}
    c = validate_check(bad, term_sheet_text(ts), given)
    assert c.issues == [] and any("note it quotes is not one of the notes" in n for n in c.notes)
    plain = {"issues": [dict(good["issues"][0], rule="")]}                           # a wrong-kind point has no note
    assert len(validate_check(plain, term_sheet_text(ts), given).issues) == 1
    assert check_term_sheet(ts, Client({"issues": good["issues"]}), notes=notes).issues[0].rule.startswith("Full name")


def test_a_failed_call_is_tried_once_more_and_counted_once_per_success():
    log = []
    client = Client(RuntimeError("temporary"), {"issues": []})
    c = check_term_sheet(TS, CountingClient(client, log, "term_sheet_check"))
    assert c.issues == [] and [e["step"] for e in log] == ["term_sheet_check"] and len(client.requests) == 2


def test_two_failures_raise():
    try:
        check_term_sheet(TS, Client(RuntimeError("a"), RuntimeError("b")))
    except AIStepError as e:
        assert "API call failed" in str(e)
        return
    raise AssertionError("expected AIStepError")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} term sheet check tests passed.")
