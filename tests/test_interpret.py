"""Phase 2 tests. `python test_interpret.py` runs offline with a fake client (no API key, no cost).
`python test_interpret.py --live` also sends the sample cases to the real model."""
import json
import sys
from types import SimpleNamespace

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clause_data import build_library
from ai.interpret import (candidate_question, clause_digest, context_summary, interpret_request,
                          resolve_included, result_lines, term_sheet_warnings, validate)
from ai.llm import CountingClient, call_summary
from core.clause_params import limits_of
from core.draft_state import library_for
from core.renumber import renumber_and_render
from core.term_sheet_fields import Installment, TermSheet


def user(*texts):
    return [{"role": "user", "content": t} for t in texts]


def sample_term_sheet(roof_owner="", owner="Solar Owner Co., Ltd."):
    return TermSheet(
        project_name="Rooftop PV Project", project_location="Bangkok", capacity="500",
        owner_name=owner, contractor_name="Sun Build Co., Ltd.", roof_owner=roof_owner,
        contract_price_number="10,000,000", start_date="1 Nov 2026", completion_date="1 Apr 2027",
        installments=[Installment("1", "30"), Installment("2", "30"), Installment("3", "40")])


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
    base = {"clause_actions": [], "deviations": [], "ambiguities": [], "unmapped_requests": [], "suggestions": []}
    base.update(overrides)
    return base


def action(key, act, evidence, basis="comment", reason="r"):
    return {"clause_key": key, "action": act, "reason": reason, "basis": basis, "evidence": evidence}


def test_valid_exclude_applies_and_renumbers():
    ts = sample_term_sheet()
    client = FakeClient(empty(clause_actions=[
        action("completion_deadline", "exclude", "drop the construction timeline")]))
    result = interpret_request(ts, build_library(), client,
                               conversation=user("client wants to drop the construction timeline"))
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


def test_the_roof_owner_rule_gives_a_suggestion_verified_against_the_term_sheet_and_never_an_action():
    ts = sample_term_sheet(roof_owner="Green Land Co., Ltd.")
    client = FakeClient(empty(suggestions=[{"clause_key": "owner_representations", "reason": "The roof owner is a different party from the Owner.",
                                            "evidence": "roof_owner: Green Land Co., Ltd."}]))
    result = interpret_request(ts, build_library(), client, conversation=[])
    assert result.clause_actions == [] and len(result.suggestions) == 1
    s = result.suggestions[0]
    assert (s.clause_key, s.evidence_verified, s.reason) == ("owner_representations", True, "The roof owner is a different party from the Owner.")
    assert resolve_included(build_library(), result.clause_actions)["owner_representations"] is False, "nothing is added: the user ticks it"


def test_a_model_that_still_includes_the_clause_for_the_roof_owner_is_turned_into_a_suggestion():
    ts = sample_term_sheet(roof_owner="Green Land Co., Ltd.")
    client = FakeClient(empty(clause_actions=[action("owner_representations", "include", "roof_owner: Green Land Co., Ltd.", basis="term_sheet", reason="different party")]))
    result = interpret_request(ts, build_library(), client, conversation=[])
    assert result.clause_actions == [] and [s.clause_key for s in result.suggestions] == ["owner_representations"]
    assert result.suggestions[0].reason == "different party" and result.suggestions[0].evidence_verified is True


def dev(key, quote, change_type="modify", change="c", evidence="x", term="liquidated damages",
        match="same_term", relation="", new_text=""):
    return {"clause_key": key, "summary": "s", "requested_change": change,
            "change_type": change_type, "provision_quote": quote, "request_term": term,
            "term_match": match, "relation": relation, "evidence": evidence, "new_text": new_text}


LD_QUOTE = "at the rate of 0.05 (zero point zero five) percent of the Contract Price per day"


def test_deviation_with_real_provision_kept():
    result = validate(empty(deviations=[dev("completion_deadline", LD_QUOTE)]), build_library(), "x")
    assert len(result.deviations) == 1 and not result.unmapped_requests


def test_deviation_on_missing_provision_moved_to_unmapped():
    raw = empty(deviations=[dev("price_payment", "default interest rate",
                                change="reduce the default interest rate")])
    result = validate(raw, build_library(), "x")
    assert not result.deviations
    assert "default interest rate" in result.unmapped_requests[0].request and result.notes


def test_deviation_with_empty_quote_moved_to_unmapped():
    result = validate(empty(deviations=[dev("price_payment", "")]), build_library(), "x")
    assert not result.deviations and len(result.unmapped_requests) == 1


def test_add_deviation_needs_no_quote():
    result = validate(empty(deviations=[dev("price_payment", "", change_type="add")]), build_library(), "x")
    assert len(result.deviations) == 1 and result.deviations[0].change_type == "add"


def test_provision_quote_check_ignores_case_and_whitespace():
    quote = "AT THE RATE of 0.05   (zero point zero five) percent"
    result = validate(empty(deviations=[dev("completion_deadline", quote)]), build_library(), "x")
    assert len(result.deviations) == 1


def test_quote_must_be_in_the_named_clause():
    result = validate(empty(deviations=[dev("price_payment", LD_QUOTE)]), build_library(), "x")
    assert not result.deviations and result.unmapped_requests


def test_unknown_deviation_clause_dropped():
    result = validate(empty(deviations=[dev("nope", "x")]), build_library(), "x")
    assert not result.deviations and len(result.notes) == 1


def unmapped(request="reduce default interest", key="none", quote="", change="", evidence="x"):
    return {"request": request, "evidence": evidence, "candidate_clause_key": key,
            "candidate_provision_quote": quote, "why_related": "both set a charge for lateness",
            "candidate_change": change}


def test_candidate_kept_when_quote_is_in_clause():
    raw = empty(unmapped_requests=[unmapped(key="completion_deadline", quote=LD_QUOTE,
                                            change="Reduce the liquidated damages rate")])
    item = validate(raw, build_library(), "x").unmapped_requests[0]
    assert item.candidate_key == "completion_deadline" and item.candidate_quote == LD_QUOTE
    assert item.candidate_change == "Reduce the liquidated damages rate" and item.why_related


def test_candidate_dropped_when_quote_not_in_clause():
    raw = empty(unmapped_requests=[unmapped(key="price_payment", quote=LD_QUOTE)])
    result = validate(raw, build_library(), "x")
    assert result.unmapped_requests[0].candidate_key == "" and result.notes


def test_candidate_none_and_unknown_key():
    raw = empty(unmapped_requests=[unmapped(), unmapped(key="made_up", quote="x")])
    result = validate(raw, build_library(), "x")
    assert [u.candidate_key for u in result.unmapped_requests] == ["", ""]


def test_empty_unmapped_request_skipped():
    assert not validate(empty(unmapped_requests=[unmapped(request="  ")]), build_library(), "x").unmapped_requests


def test_schema_allows_none_candidate():
    client = FakeClient(empty())
    interpret_request(sample_term_sheet(), build_library(), client)
    schema = client.last_kwargs["response_format"]["json_schema"]["schema"]
    props = schema["properties"]["unmapped_requests"]["items"]["properties"]
    assert "none" in props["candidate_clause_key"]["enum"]
    assert set(schema["properties"]["unmapped_requests"]["items"]["required"]) == set(props)


def test_prompt_includes_full_clause_text():
    client = FakeClient(empty())
    interpret_request(sample_term_sheet(), library_for({}), client)
    user = client.last_kwargs["messages"][1]["content"]
    assert "not more than 5 (five) percent of the Contract Price" in user
    assert "Payable upon completion of installation of the inverter" in user


def test_prompt_asks_for_stable_wording_of_unmapped_requests():
    from ai.interpret import SYSTEM_PROMPT
    assert "reuse exactly the same wording" in SYSTEM_PROMPT and "Not covered by the clause library" in SYSTEM_PROMPT


def test_prompt_follows_the_chosen_caps():
    client = FakeClient(empty())
    ts = sample_term_sheet()
    ts.limits = {"ld_cap": None, "damages_cap": 8}
    interpret_request(ts, library_for({}, limits_of(ts)), client)
    user = client.last_kwargs["messages"][1]["content"]
    assert "not more than" not in user and "shall not exceed 8% (eight percent)" in user
    assert "limits: cap on delay damages none; cap on total damages deducted 8%" in user


def test_schema_enforces_clause_keys():
    client = FakeClient(empty())
    interpret_request(sample_term_sheet(), build_library(), client)
    schema = client.last_kwargs["response_format"]["json_schema"]["schema"]
    enum = schema["properties"]["clause_actions"]["items"]["properties"]["clause_key"]["enum"]
    assert set(enum) == {c.key for c in build_library()}


def test_prompt_contains_conversation_and_library():
    client = FakeClient(empty())
    convo = [{"role": "user", "content": "please drop X"},
             {"role": "assistant", "content": "Question: did you mean Z?"},
             {"role": "user", "content": "yes, Z"}]
    interpret_request(sample_term_sheet(), build_library(), client, conversation=convo)
    content = client.last_kwargs["messages"][1]["content"]
    assert "User: please drop X" in content and "Assistant: Question: did you mean Z?" in content
    assert "User: yes, Z" in content and "key: completion_deadline" in content


def test_empty_conversation_sent_as_no_messages():
    client = FakeClient(empty())
    interpret_request(sample_term_sheet(), build_library(), client)
    assert "(no messages)" in client.last_kwargs["messages"][1]["content"]


def test_evidence_from_assistant_turn_is_not_verified():
    convo = [{"role": "user", "content": "tighten things up"},
             {"role": "assistant", "content": "Proposed: remove clause 'Suspension of Works'."}]
    client = FakeClient(empty(clause_actions=[action("suspension", "exclude", "remove clause 'Suspension")]))
    result = interpret_request(sample_term_sheet(), build_library(), client, conversation=convo)
    assert result.clause_actions[0].evidence_verified is False


def test_evidence_from_later_user_turn_is_verified():
    convo = user("something vague", "I mean drop suspension of works")
    client = FakeClient(empty(clause_actions=[action("suspension", "exclude", "drop suspension of works")]))
    result = interpret_request(sample_term_sheet(), build_library(), client, conversation=convo)
    assert result.clause_actions[0].evidence_verified is True


def asked_convo():
    """User asks, assistant asks whether the user means liquidated damages, user says yes."""
    return [{"role": "user", "content": "client wants to reduce default interest"},
            {"role": "assistant", "content": "Question: The closest provision is 'Completion Deadline'. "
                                             "Is that what you meant?"},
            {"role": "user", "content": "Yes, that is what I meant."}]


def confirmed_dev(**overrides):
    args = dict(change="Reduce the liquidated damages rate", evidence="reduce default interest",
                term="default interest", match="confirmed_by_user")
    args.update(overrides)
    return dev("completion_deadline", LD_QUOTE, **args)


def test_confirmed_candidate_comes_back_as_deviation():
    client = FakeClient(empty(deviations=[confirmed_dev()]))
    result = interpret_request(sample_term_sheet(), build_library(), client, conversation=asked_convo())
    assert len(result.deviations) == 1 and result.deviations[0].evidence_verified


def test_confirmed_by_user_needs_a_prior_question():
    convo = user("client wants to reduce default interest", "yes")
    client = FakeClient(empty(deviations=[confirmed_dev()]))
    result = interpret_request(sample_term_sheet(), build_library(), client, conversation=convo)
    assert not result.deviations and result.unmapped_requests[0].candidate_key == "completion_deadline"


def test_silent_reinterpretation_becomes_a_question():
    raw = empty(deviations=[dev("completion_deadline", LD_QUOTE, term="default interest rate",
                                change="Reduce the default interest rate to 0.01%",
                                evidence="reduce the default interest rate")])
    result = validate(raw, build_library(), "reduce the default interest rate to 0.01%")
    assert not result.deviations
    item = result.unmapped_requests[0]
    assert item.candidate_key == "completion_deadline" and item.candidate_quote == LD_QUOTE
    assert item.candidate_change == "Reduce the default interest rate to 0.01%" and result.notes


def test_model_admitting_a_different_term_becomes_a_question():
    raw = empty(deviations=[dev("completion_deadline", LD_QUOTE, match="different_term",
                                relation="both set a charge for lateness")])
    result = validate(raw, build_library(), "x")
    assert not result.deviations and result.unmapped_requests[0].why_related.startswith("both")


def test_term_check_uses_stems_and_skips_generic_words():
    lib = build_library()
    gov = next(i.text for c in lib if c.key == "miscellaneous" for i in c.items if "governed by" in i.text).rstrip(".")
    kept = validate(empty(deviations=[dev("miscellaneous", gov, term="governing law")]), lib, "x")
    assert len(kept.deviations) == 1
    generic = validate(empty(deviations=[dev("completion_deadline", LD_QUOTE, term="the rate")]), lib, "x")
    assert len(generic.deviations) == 1


def test_add_deviation_skips_term_check():
    raw = empty(deviations=[dev("price_payment", "", change_type="add", term="late payment interest")])
    assert len(validate(raw, build_library(), "x").deviations) == 1


def test_result_lines_and_context_summary():
    lib = build_library()
    raw = empty(
        clause_actions=[action("suspension", "exclude", "x")],
        deviations=[dev("completion_deadline", LD_QUOTE, change="lower the rate")],
        ambiguities=["What does 'it' refer to?"],
        unmapped_requests=[unmapped(key="completion_deadline", quote=LD_QUOTE, evidence="default interest"),
                           unmapped(request="add a warranty clause")])
    result = validate(raw, lib, "x")
    proposals, questions, uncovered = result_lines(result, lib)
    assert len(proposals) == 2 and "Suspension of Works" in proposals[0]
    assert len(questions) == 2 and "Completion Deadline" in questions[1] and "default interest" in questions[1]
    assert uncovered == ["Not covered by the clause library: add a warranty clause"]
    summary = context_summary(result, lib)
    assert summary.count("\n") == 4 and "Is that what you meant?" in summary


def test_ambiguity_that_only_repeats_the_request_is_dropped():
    raw = empty(ambiguities=["I want to increase the interest rate to 1.00%",
                             "Is 1.00% per day or per year?"])
    result = validate(raw, build_library(), "I want to increase the interest rate to 1.00%")
    assert result.ambiguities == ["Is 1.00% per day or per year?"]
    assert any("repeated the request" in n for n in result.notes)


def test_candidate_question_text():
    item = validate(empty(unmapped_requests=[unmapped(key="completion_deadline", quote=LD_QUOTE,
                                                      evidence="default interest")]),
                    build_library(), "default interest").unmapped_requests[0]
    text = candidate_question(item, "Completion Deadline")
    assert text.startswith("You wrote \u201cdefault interest\u201d") and "'Completion Deadline'" in text
    assert text.endswith("Is that what you meant?")


def test_counting_client_records_completed_calls_only():
    log = []
    ok = CountingClient(FakeClient(empty()), log, "interpret")
    interpret_request(sample_term_sheet(), build_library(), ok, model="m1")
    interpret_request(sample_term_sheet(), build_library(), ok, model="m1")
    assert log == [{"step": "interpret", "model": "m1"}] * 2

    class Failing:
        chat = SimpleNamespace(completions=SimpleNamespace(
            create=lambda **k: (_ for _ in ()).throw(RuntimeError("boom"))))
    try:
        interpret_request(sample_term_sheet(), build_library(), CountingClient(Failing(), log, "x"))
    except RuntimeError:
        pass
    assert len(log) == 2          # the failed call was not counted


def test_call_summary():
    assert call_summary([]) == ""
    log = [{"step": "interpret"}, {"step": "review"}, {"step": "interpret"}]
    assert call_summary(log) == "interpret \u00d72, review \u00d71"


def test_library_for_applies_selection():
    lib = library_for({"taxation": False, "owner_representations": True})
    state = {c.key: c.included for c in lib}
    assert state["taxation"] is False and state["owner_representations"] is True
    assert state["suspension"] is True                       # untouched keys keep their default
    assert library_for({}) and all(c.included == d.included for c, d in zip(library_for({}), build_library()))


def test_digest_shows_current_state_not_default():
    digest = clause_digest(library_for({"taxation": False, "owner_representations": True}))
    blocks = {b.split("]")[0]: b for b in digest.split("\n\n[")}
    tax = next(b for k, b in blocks.items() if "key: taxation" in k)
    own = next(b for k, b in blocks.items() if "key: owner_representations" in k)
    assert "currently excluded from the draft" in tax and "standard clause" in tax
    assert "currently included in the draft" in own and "optional clause" in own


def test_noop_filter_uses_current_state():
    lib = library_for({"taxation": False})
    result = validate(empty(clause_actions=[action("taxation", "exclude", "x"),
                                            action("suspension", "exclude", "x")]), lib, "x")
    assert [a.clause_key for a in result.clause_actions] == ["suspension"]
    again = validate(empty(clause_actions=[action("taxation", "include", "x")]), lib, "x")
    assert [a.clause_key for a in again.clause_actions] == ["taxation"]


def test_context_summary_when_nothing_found():
    assert "No changes" in context_summary(validate(empty(), build_library(), "x"), build_library())


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
    ("A. drop timeline", sample_term_sheet(), user("client wants to drop the construction timeline")),
    ("B. third-party roof owner", sample_term_sheet(roof_owner="Green Land Co., Ltd."), []),
    ("C. mixed, Thai", sample_term_sheet(), user(
        "ลูกค้าขอลดค่าปรับล่าช้าเหลือ 0.03% ต่อวัน และไม่ต้องการข้อ confidentiality")),
    ("D. vague + unmappable", sample_term_sheet(), user("make it more balanced and add a 5-year warranty clause")),
    ("E. empty conversation", sample_term_sheet(), []),
    ("F. wrong term (expect liquidated damages as candidate)", sample_term_sheet(),
     user("Client wants to reduce the default interest rate to 0.01%")),
    ("G. garbled request", sample_term_sheet(), user("client wants to drop reduce the default interest rate")),
]


def show(result):
    for a in result.clause_actions:
        print(f"  ACTION   {a.action} {a.clause_key} (verified={a.evidence_verified}) <- {a.evidence!r}")
    for d in result.deviations:
        print(f"  DEVIATE  {d.clause_key} [{d.change_type}]: {d.requested_change} "
              f"(quote={d.provision_quote!r}, verified={d.evidence_verified})")
    for a in result.ambiguities:
        print(f"  AMBIG    {a}")
    for u in result.unmapped_requests:
        print(f"  UNMAPPED {u.request}")
        if u.candidate_key:
            print(f"           candidate: {u.candidate_key} <- {u.candidate_quote!r}")
    for n in result.notes:
        print(f"  NOTE     {n}")


def run_live():
    from ai.llm import get_client
    import os
    client = get_client(os.getenv("OPENAI_API_KEY"))        # the live runs are a developer tool: the key comes from the environment here, not in the app
    if client is None:
        sys.exit("Set OPENAI_API_KEY (or put it in .env) to run live cases.")
    lib = build_library()
    for name, ts, convo in LIVE_CASES:
        print(f"\n=== {name} ===")
        show(interpret_request(ts, lib, client, conversation=convo))

    print("\n=== H. two turns: candidate, then the user confirms ===")
    ts, convo = sample_term_sheet(), user("Client wants to reduce the default interest rate to 0.01%")
    first = interpret_request(ts, lib, client, conversation=convo)
    show(first)
    convo += [{"role": "assistant", "content": context_summary(first, lib)}] + user("Yes, that is what I meant.")
    print("  --- after the user says yes ---")
    show(interpret_request(ts, lib, client, conversation=convo))


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} offline tests passed.")
    if "--live" in sys.argv:
        run_live()
