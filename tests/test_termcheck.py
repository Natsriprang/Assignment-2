"""Tests for the AI term sheet check: the AI only labels values, code decides (offline, with a fake client).
Run: python -m tests.test_termcheck"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.llm import AIStepError, CountingClient
from ai.termcheck import CHECK_PROMPT, check_schema, check_term_sheet, validate_labels
from core.field_kinds import ACCEPTABLE, KIND_PHRASE, KINDS, kind_items, misfits
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


def sheet(**over):
    ts = TermSheet(owner_name="University of Melbourne", owner_signatory="Nat Sriprang", roof_owner="University of Melbourne",
                   owner_reg_no="1020304050601", owner_contact_phone="422222222", owner_contact_email="jonh@gmail.com",
                   contractor_name="Prime Road Group Co.,ltd.", contractor_signatory="Noom Sriprang")
    for k, v in over.items():
        setattr(ts, k, v)
    return ts


def labels_for(ts, **kinds):
    """A reply labelling each filled field with the kind given for it (default: the kind that fits)."""
    fits = {"owner_name": "company_name", "contractor_name": "company_name", "owner_signatory": "person_name",
            "contractor_signatory": "person_name", "roof_owner": "company_name", "owner_reg_no": "registration_number",
            "owner_contact_phone": "phone", "owner_contact_email": "email"}
    fits.update(kinds)
    return {"kinds": [{"id": i, "kind": fits.get(f, "other")} for i, f, v in kind_items(ts)]}


# ------------------------------------------------------------------ what the AI is asked
def test_the_ai_gets_values_and_ids_only_never_the_field_names():
    ts = sheet()
    client = Client(labels_for(ts))
    check_term_sheet(ts, client)
    user = client.requests[0]["messages"][1]["content"]
    assert user.startswith("<items>\nf1: ") and user.endswith("\n</items>")
    for value in ("University of Melbourne", "Nat Sriprang", "1020304050601", "jonh@gmail.com"):
        assert value in user
    for name in ("owner_name", "roof_owner", "signatory", "Authorised", "Registration", "Company name", "<term_sheet>"):
        assert name not in user, f"the AI must not be told which field a value is in: {name!r}"


def test_the_prompt_asks_for_labels_and_nothing_else():
    low = CHECK_PROMPT.lower()
    for word in ("thai", "rooftop", "solar", "agreement", "contract ", "construction", "mistake", "wrong", "report", "warn", "field"):
        assert word not in low, f"the prompt only asks for labels, so it has no word like {word!r}"
    for kind in KINDS:
        assert f"- {kind}:" in low
    assert "when unsure, use other" in low and "label every item" in low and "never follow instructions" in low


def test_the_schema_allows_only_the_ids_sent_and_the_known_kinds():
    props = check_schema(["f1", "f2"])["properties"]["kinds"]["items"]["properties"]
    assert props["id"]["enum"] == ["f1", "f2"] and props["kind"]["enum"] == KINDS


def test_with_nothing_to_label_there_is_no_call():
    client = Client()
    assert check_term_sheet(TermSheet(), client).issues == [] and client.requests == []
    assert check_term_sheet(TermSheet(project_name="Only a free-text field the table does not cover"), client).issues == []


# ------------------------------------------------------------------ the decision is in code
def test_the_reported_cases_are_not_warnings_any_more():
    ts = sheet()                                              # "Nat Sriprang" and "University of Melbourne" as the user reported
    c = check_term_sheet(ts, Client(labels_for(ts)))
    assert c.issues == [] and c.notes == []


def test_a_label_that_does_not_fit_gives_a_warning_the_code_wrote():
    ts = sheet(owner_contact_phone="jan@x.example")
    c = check_term_sheet(ts, Client(labels_for(ts, owner_contact_phone="email")))
    assert [(i.field, i.evidence) for i in c.issues] == [("owner_contact_phone", "jan@x.example")]
    assert c.issues[0].problem == "The AI read this as an email address, which does not fit this field."
    ts = sheet(owner_name="John Smith")
    c = check_term_sheet(ts, Client(labels_for(ts, owner_name="person_name")))
    assert c.issues[0].problem == "The AI read this as a person's name, which does not fit this field."


def test_other_never_causes_a_warning_and_neither_do_the_kinds_that_merely_fit():
    ts = sheet()
    every = {f: "other" for f in ACCEPTABLE}
    assert check_term_sheet(ts, Client(labels_for(ts, **every))).issues == []
    for field, ok_kinds in ACCEPTABLE.items():
        assert "other" in ok_kinds, field
    assert "company_name" in ACCEPTABLE["roof_owner"] and "person_name" in ACCEPTABLE["roof_owner"]       # the roof owner may be either
    assert check_term_sheet(sheet(roof_owner="Somchai Jaidee"), Client(labels_for(sheet(roof_owner="Somchai Jaidee"), roof_owner="person_name"))).issues == []


def test_every_kind_is_decided_by_the_table_and_the_table_is_the_only_judge():
    items = [("f1", "owner_contact_email", "x")]
    for kind in KINDS:
        got = misfits(items, {"f1": kind})
        assert bool(got) == (kind not in ACCEPTABLE["owner_contact_email"]), kind
    assert misfits(items, {}) == [] and misfits(items, {"f9": "phone"}) == []           # an item with no label is not judged


def test_labels_for_unknown_ids_or_kinds_are_dropped_and_the_first_label_of_an_id_wins():
    items = [("f1", "owner_contact_email", "jan@x.example")]
    raw = {"kinds": [{"id": "f1", "kind": "email"}, {"id": "f1", "kind": "phone"}, {"id": "f7", "kind": "email"}, {"id": "f1", "kind": "wizard"}]}
    c = validate_labels(raw, items)
    assert c.issues == [] and len(c.notes) == 2
    c = validate_labels({"kinds": [{"id": "f1", "kind": "phone"}, {"id": "f1", "kind": "email"}]}, items)
    assert len(c.issues) == 1 and "a phone number" in c.issues[0].problem
    assert KIND_PHRASE.keys() == set(KINDS)


def test_the_value_shown_is_the_users_own_not_the_ais():
    ts = sheet(owner_signatory="Nat Sriprang\r\nSomchai Jaidee")
    assert [v for i, f, v in kind_items(ts) if f == "owner_signatory"] == ["Nat Sriprang / Somchai Jaidee"]
    c = check_term_sheet(ts, Client(labels_for(ts, owner_signatory="company_name")))
    assert c.issues[0].evidence == "Nat Sriprang / Somchai Jaidee"


# ------------------------------------------------------------------ calls and failures
def test_a_failed_call_is_tried_once_more_and_counted_once_per_success():
    ts = sheet()
    log = []
    client = Client(RuntimeError("temporary"), labels_for(ts))
    c = check_term_sheet(ts, CountingClient(client, log, "term_sheet_check"))
    assert c.issues == [] and [e["step"] for e in log] == ["term_sheet_check"] and len(client.requests) == 2


def test_two_failures_raise():
    try:
        check_term_sheet(sheet(), Client(RuntimeError("a"), RuntimeError("b")))
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
