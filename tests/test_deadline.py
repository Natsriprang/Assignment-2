"""Tests for the calendar-or-period choice of the deadline. Run: python -m tests.test_deadline"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from core.deadline import apply_import, deadline_choice, deadline_warning, is_days, period_days
from core.term_sheet_fields import TermSheet, missing_required
from core.xlsx_parser import parse_xlsx

BASE = dict(project_name="P", project_location="L", capacity="500", owner_name="O", contractor_name="C", contract_price_number="1000")


def test_which_wordings_are_read_as_days_after_signing():
    yes = {"14 days": 14, "within 14 days": 14, "14 days after signing": 14, "14 days from the signing date": 14, "30 Days.": 30,
           "150 days from the date of this Agreement": 150, "within 14 calendar days after signing": 14, "14 days from contract date": 14}
    for text, n in yes.items():
        assert period_days(text) == n, text
    for text in ["150 days from commencement", "30 working days", "3 months", "1000 days", "0 days", "14", "10 October 2026", "", None,
                 "14 days after notice to proceed", "within 14 days of the Owner's payment"]:
        assert period_days(text) is None, text


def test_days_must_be_a_whole_number_from_1_to_999():
    assert all(is_days(x) for x in ("1", "30", " 45 ", "999"))
    assert not any(is_days(x) for x in ("", "0", "1000", "-5", "2.5", "abc", "14 days", None))


def test_only_a_real_mode_counts_as_chosen():
    assert deadline_choice(TermSheet(deadline_mode="calendar")) == "calendar" and deadline_choice(TermSheet(deadline_mode="period")) == "period"
    assert deadline_choice(TermSheet()) == "" and deadline_choice(TermSheet(deadline_mode="weekly")) == ""


def test_the_import_reads_dates_and_periods_and_leaves_the_rest_unchosen():
    def read(start, completion):
        return apply_import(TermSheet(start_date=start, completion_date=completion))
    d = read("03 October 2026", "10 October 2026")
    assert (d.deadline_mode, d.completion_days) == ("calendar", "")
    p = read("14 days after signing", "150 days from the signing date")
    assert (p.deadline_mode, p.completion_days) == ("period", "150")                              # a period only has a completion
    assert read("", "120 days").deadline_mode == "period" and read("", "120 days").completion_days == "120"
    for start, completion in [("03 October 2026", "150 days"), ("14 days", "10 October 2026"), ("14 days", "150 days from commencement"),
                              ("soon", "later"), ("", "10 October 2026"), ("", ""), ("03 October 2026", ""), ("soon", "120 days")]:
        u = read(start, completion)
        assert (u.deadline_mode, u.completion_days) == ("", ""), (start, completion)
        assert (u.start_date, u.completion_date) == (start, completion)                          # what the cells said is kept


def test_the_xlsx_import_sets_the_mode():
    def sheet(start, completion):
        wb = openpyxl.Workbook()
        wb.active["C60"], wb.active["C61"] = start, completion
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
        return parse_xlsx(buf)
    assert sheet("03 October 2026", "10 October 2026").deadline_mode == "calendar"
    assert sheet("14 days after signing", "120 days after signing").completion_days == "120"
    assert sheet("tbc", "tbc").deadline_mode == ""


def test_the_notice_says_what_is_wrong_and_what_happens():
    plain = deadline_warning(TermSheet())
    assert plain.startswith("The completion deadline is not chosen.") and "term sheet says" not in plain and "keeps its blanks" in plain
    odd = deadline_warning(TermSheet(start_date="soon", completion_date="later"))
    assert "start \u201csoon\u201d and completion \u201clater\u201d" in odd and "cannot be read" in odd
    assert "completion \u201clater\u201d" in deadline_warning(TermSheet(completion_date="later")) and "start \u201c" not in deadline_warning(TermSheet(completion_date="later"))
    assert deadline_warning(TermSheet(deadline_mode="calendar")) is None and deadline_warning(TermSheet(deadline_mode="period")) is None


def test_what_is_required_depends_on_the_mode():
    assert missing_required(TermSheet(**BASE)) == ["deadline_mode"]
    assert missing_required(TermSheet(**BASE, deadline_mode="calendar")) == ["start_date", "completion_date"]
    assert missing_required(TermSheet(**BASE, deadline_mode="calendar", start_date="1 Nov 2026", completion_date=" ")) == ["completion_date"]
    assert missing_required(TermSheet(**BASE, deadline_mode="period")) == ["completion_days"]
    assert missing_required(TermSheet(**BASE, deadline_mode="period", completion_days="abc")) == ["completion_days"]
    assert missing_required(TermSheet(**BASE, deadline_mode="period", completion_days="120")) == []
    assert missing_required(TermSheet(**BASE, deadline_mode="calendar", start_date="a", completion_date="b", completion_days="")) == []
    assert "project_name" in missing_required(TermSheet(deadline_mode="period", completion_days="2"))
    assert "deadline_mode" in missing_required(None)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} deadline tests passed.")
