"""Phase 2 tests. `python test_interpret.py` runs offline with a fake client (no API key, no cost).
`python test_interpret.py --live` also sends the sample cases to the real model."""
import json
import sys
from types import SimpleNamespace

from clause_data import build_library
from interpret import (Interpretation, interpret_request, resolve_included, term_sheet_warnings,
                       validate)
from renumber import renumber_and_render
from term_sheet_fields import Installment, TermSheet


def sample_term_sheet(comment="", roof_owner="", owner="Solar Owner Co., Ltd."):
    return TermSheet(
        project_name="Rooftop PV Project", project_location="Bangkok", capacity="500",
        owner_name=owner, contractor_name="Sun Build Co., Ltd.", roof_owner=roof_owner,
        contract_price_number="10,000,000", start_date="1 Nov 2026", completion_date="1 Apr 2027",
        installments=[Installment("1", "30"), Installment("2", "30"), Installment("3", "40")],
        comment=comment)


class FakeClient:
    """Mimics client.chat.completions.create and returns a canned JSON payload."""
    def __init__(self, payload, finish_reason="stop", refusal=None):
        self.payload, self.finish_reason, self.refusal = payload, finish_reason, refusal
        self.last_kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.last_kwargs = kwargs
        msg = SimpleNamespace(content=json.dumps(self.payload), refusal=self.refusal)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=self.finish_reason)])


def empty(**overrides):
    base = {"clause_actions": [], "deviations": [], "ambiguities": [], "unmapped_requests": []}
    base.update(overrides)
    return base


def action(key, act, evidence, basis="comment", reason="r"):
    return {"clause_key": key, "action": act, "reason": reason, "basis": basis, "evidence": evidence}


def test_valid_exclude_applies_and_renumbers():
    comment = "client wants to drop the construction timeline"
    ts = sample_term_sheet(comment)
    client = FakeClient(empty(clause_actions=[
        action("completion_deadline", "exclude", "drop the construction timeline")]))
    result = interpret_request(ts, build_library(), client)
    assert len(result.clause_actions) == 1 and result.clause_actions[0].evidence_verified

    lib = build_library()
    for c in lib:
        c.included = resolve_included(lib, result.clause_actions)[c.key]
    titles = [c.title for _, c, _ in renumber_and_render(lib)]
    assert "Completion Deadline" not in titles and len(titles) == 14


def test_unknown_key_rejected():
    lib = build_library()
    result = validate(empty(clause_actions=[action("made_up_clause", "exclude", "x")]), lib, "x")
    assert not result.clause_actions and result.notes


def test_noop_actions_dropped():
    lib = build_library()
    raw = empty(clause_actions=[action("taxation", "include", "x"),
                                action("owner_representations", "exclude", "x")])
    result = validate(raw, lib, "x")
    assert not result.clause_actions and len(result.notes) == 2


def test_conflicting_actions_become_ambiguity():
    lib = build_library()
    raw = empty(clause_actions=[action("taxation", "exclude", "x"), action("taxation", "include", "x")])
    result = validate(raw, lib, "x")
    assert not result.clause_actions and "includes and excludes" in result.ambiguities[0]


def test_conflict_include_then_exclude_on_optional():
    lib = build_library()
    raw = empty(clause_actions=[action("owner_representations", "include", "x"),
                                action("owner_representations", "exclude", "x")])
    result = validate(raw, lib, "x")
    assert not result.clause_actions and len(result.ambiguities) == 1


def test_fabricated_evidence_flagged():
    lib = build_library()
    raw = empty(clause_actions=[action("suspension", "exclude", "the client said to drop suspension")])
    result = validate(raw, lib, "some unrelated comment")
    assert result.clause_actions[0].evidence_verified is False


def test_evidence_check_ignores_case_and_whitespace():
    lib = build_library()
    raw = empty(clause_actions=[action("suspension", "exclude", "Drop   the  suspension clause")])
    result = validate(raw, lib, "please drop the suspension\nclause")
    assert result.clause_actions[0].evidence_verified is True


def test_thai_evidence_verified():
    lib = build_library()
    comment = "ลูกค้าอยากตัดข้อกำหนดระยะเวลาก่อสร้างออก"
    raw = empty(clause_actions=[action("completion_deadline", "exclude", "ตัดข้อกำหนดระยะเวลาก่อสร้าง")])
    assert validate(raw, lib, comment).clause_actions[0].evidence_verified is True


def test_term_sheet_rule_action_verified_against_term_sheet():
    ts = sample_term_sheet(roof_owner="Green Land Co., Ltd.")
    client = FakeClient(empty(clause_actions=[
        action("owner_representations", "include", "Green Land Co., Ltd.", basis="term_sheet")]))
    result = interpret_request(ts, build_library(), client)
    assert result.clause_actions[0].evidence_verified is True
    included = resolve_included(build_library(), result.clause_actions)
    assert included["owner_representations"] is True


def test_deviation_kept_and_unknown_deviation_dropped():
    lib = build_library()
    raw = empty(deviations=[
        {"clause_key": "completion_deadline", "summary": "LD rate", "requested_change": "0.03%/day",
         "evidence": "x"},
        {"clause_key": "nope", "summary": "s", "requested_change": "c", "evidence": "x"}])
    result = validate(raw, lib, "x")
    assert len(result.deviations) == 1 and len(result.notes) == 1


def test_schema_enforces_clause_keys():
    client = FakeClient(empty())
    interpret_request(sample_term_sheet(), build_library(), client)
    schema = client.last_kwargs["response_format"]["json_schema"]["schema"]
    enum = schema["properties"]["clause_actions"]["items"]["properties"]["clause_key"]["enum"]
    assert set(enum) == {c.key for c in build_library()}


def test_prompt_contains_comment_and_library():
    client = FakeClient(empty())
    interpret_request(sample_term_sheet("please drop X"), build_library(), client, clarification="by X I mean Y")
    user = client.last_kwargs["messages"][1]["content"]
    assert "please drop X" in user and "key: completion_deadline" in user and "by X I mean Y" in user


def test_empty_comment_sent_as_none():
    client = FakeClient(empty())
    interpret_request(sample_term_sheet(""), build_library(), client)
    assert "(none)" in client.last_kwargs["messages"][1]["content"]


def test_refusal_and_truncation_raise():
    for kwargs in ({"refusal": "no"}, {"finish_reason": "length"}):
        try:
            interpret_request(sample_term_sheet(), build_library(), FakeClient(empty(), **kwargs))
        except Exception as e:
            assert type(e).__name__ == "InterpretationError"
        else:
            raise AssertionError("expected InterpretationError")


def test_installment_sum_warning():
    ts = sample_term_sheet()
    assert term_sheet_warnings(ts) == []
    ts.installments[2].percent = "30"
    assert "90%" in term_sheet_warnings(ts)[0]
    ts.installments[2].percent = "abc"
    assert "not a number" in term_sheet_warnings(ts)[0]


def test_resolve_included_defaults():
    lib = build_library()
    included = resolve_included(lib, [])
    assert included["owner_representations"] is False and included["taxation"] is True


LIVE_CASES = [
    ("A. drop timeline", sample_term_sheet("client wants to drop the construction timeline")),
    ("B. third-party roof owner", sample_term_sheet(roof_owner="Green Land Co., Ltd.")),
    ("C. mixed, Thai", sample_term_sheet(
        "ลูกค้าขอลดค่าปรับล่าช้าเหลือ 0.03% ต่อวัน และไม่ต้องการข้อ confidentiality")),
    ("D. vague + unmappable", sample_term_sheet("make it more balanced and add a 5-year warranty clause")),
    ("E. empty comment", sample_term_sheet("")),
]


def run_live():
    from llm import get_client
    client = get_client()
    if client is None:
        sys.exit("Set OPENAI_API_KEY (or put it in .env) to run live cases.")
    for name, ts in LIVE_CASES:
        print(f"\n=== {name} ===")
        result = interpret_request(ts, build_library(), client)
        for a in result.clause_actions:
            print(f"  ACTION   {a.action} {a.clause_key} (verified={a.evidence_verified}) <- {a.evidence!r}")
        for d in result.deviations:
            print(f"  DEVIATE  {d.clause_key}: {d.requested_change} (verified={d.evidence_verified})")
        for a in result.ambiguities:
            print(f"  AMBIG    {a}")
        for u in result.unmapped_requests:
            print(f"  UNMAPPED {u}")
        for n in result.notes:
            print(f"  NOTE     {n}")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} offline tests passed.")
    if "--live" in sys.argv:
        run_live()