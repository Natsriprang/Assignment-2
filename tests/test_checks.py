"""Tests for the exact checks of the term sheet (blanks, price in words, percentages, dates), the page's field names, and the
English-words price reader. Run: python -m tests.test_checks"""
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.field_titles import BLANK_CHECKED, DASH, FIELD_TITLES, label_on_page, title
from core.price_words import words_to_number
from core.term_checks import blank_fields, blank_groups, contradictions, date_warnings, percent_warnings, price_warnings, vat_finding
from core.term_sheet_fields import Installment, TermSheet


def complete(**over):
    ts = TermSheet(project_name="Rooftop PV", project_location="Rayong", capacity="500", contract_no="C-011126", contract_date="1 Nov 2026",
                   signing_place_choice="owner", owner_name="Owner Co.", owner_country="Singapore", owner_reg_no="1020304050601",
                   owner_signatory="Nat Sriprang", owner_address="1 Owner Road", contractor_name="Sun Build", contractor_reg_no="3533555555555",
                   contractor_signatory="Noom Sriprang", contractor_address="2 Builder Road", contract_price_number="100000",
                   contract_price_words="One-hundred Thousand", attachment_no="3", vat_treatment="exclusive", deadline_mode="calendar",
                   start_date="3 October 2026", completion_date="10 October 2026",
                   owner_contact_name="John", owner_contact_position="Director", owner_contact_location="Bangkok",
                   owner_contact_phone="02", owner_contact_email="j@o.example", contractor_contact_name="Jan",
                   contractor_contact_position="Director", contractor_contact_location="Rayong", contractor_contact_phone="03",
                   contractor_contact_email="j@c.example")
    ts.installments = [Installment("1", "60"), Installment("2", "40")]
    for k, v in over.items():
        setattr(ts, k, v)
    return ts


# ---------------------------------------------------------------- the price in words
def test_the_words_are_read_as_a_number():
    cases = {"One-hundred Thousand": 100000, "two-hundred Thousand": 200000, "One hundred thousand baht only": 100000,
             "Two million five hundred thousand baht": 2500000, "Ten thousand": 10000, "One million": 1000000, "fifteen": 15,
             "twenty-five thousand": 25000, "ONE HUNDRED THOUSAND BAHT": 100000, "One Hundred Thousand Thai Baht Only": 100000,
             "one hundred and twenty three thousand four hundred and fifty six baht": 123456,
             "one hundred and twenty three thousand four hundred and fifty six baht and fifty satang": Decimal("123456.5"),
             "one thousand baht and 0 satang": None, "five hundred baht and zero satang": 500, "one billion two hundred million": 1200000000}
    for text, expected in cases.items():
        got = words_to_number(text)
        assert got == (None if expected is None else Decimal(expected)), (text, got)


def test_what_cannot_be_read_completely_is_not_guessed():
    for text in ["", "   ", None, "100,000", "One hundred thousand (THB 100,000)", "lots", "one hundred thousand bahts", "to be confirmed",
                 "one hundred thousand baht and ninety nine thousand satang", "five baht three baht", "one hundred zzz"]:
        assert words_to_number(text) is None, text


def test_the_price_in_words_against_the_digits():
    assert price_warnings(complete()) == [] and price_warnings(complete(contract_price_number="100,000")) == []
    assert price_warnings(complete(contract_price_number="THB 100,000.00")) == []
    assert price_warnings(complete(contract_price_words="One hundred thousand baht only")) == []
    w = price_warnings(complete(contract_price_words="Two-hundred Thousand"))
    assert w == ["Contract price \u2013 Price (in words) \u201cTwo-hundred Thousand\u201d reads as 200,000, but "
                 "Contract price \u2013 Price (THB, number) is 100,000."]
    assert "1,250,000.50" in price_warnings(complete(contract_price_number="1250000.50"))[0]
    for unjudged in (dict(contract_price_words="soon"), dict(contract_price_words=""), dict(contract_price_number=""), dict(contract_price_number="TBC")):
        assert price_warnings(complete(**unjudged)) == [], unjudged


# ---------------------------------------------------------------- percentages and dates
def test_percentages():
    assert percent_warnings(complete()) == []
    ts = complete(); ts.installments = [Installment("1", "60"), Installment("2", "30")]
    assert percent_warnings(ts) == ["Installment percentages add up to 90%, not 100%."]
    ts.installments = [Installment("1", "x"), Installment("2", "100")]
    assert percent_warnings(ts) == ["Installment 1: 'x' is not a number."]


def test_completion_before_start_is_flagged_only_for_calendar_dates():
    assert date_warnings(complete()) == []
    assert date_warnings(complete(start_date="10 October 2026", completion_date="3 October 2026")) == \
        ["Completion date (3 October 2026) is before Start date (10 October 2026)."]
    assert date_warnings(complete(start_date="3 October 2026", completion_date="3 October 2026")) == []        # the same day is allowed
    assert date_warnings(complete(start_date="soon", completion_date="3 October 2026")) == []                  # not dates: not judged
    assert date_warnings(complete(deadline_mode="period", start_date="10 October 2026", completion_date="3 October 2026", completion_days="9")) == []
    assert date_warnings(complete(deadline_mode="")) == []


def test_contradictions_are_all_of_them_together():
    ts = complete(contract_price_words="Two-hundred Thousand", start_date="10 October 2026", completion_date="3 October 2026")
    ts.installments = [Installment("1", "60")]
    assert len(contradictions(ts)) == 3 and contradictions(complete()) == [] and contradictions(None) == []


# ---------------------------------------------------------------- blanks
def test_a_complete_term_sheet_has_no_blanks():
    assert blank_fields(complete()) == [] and blank_fields(None) == []


def test_removing_a_signatory_name_is_reported_by_the_name_the_page_uses():
    assert blank_fields(complete(owner_signatory="")) == ["Owner \u2013 Authorised signatory"]
    assert blank_fields(complete(contractor_signatory="  ")) == ["Contractor \u2013 Authorised signatory"]
    assert blank_fields(complete(owner_signatory="", contractor_signatory="")) == ["Owner \u2013 Authorised signatory", "Contractor \u2013 Authorised signatory"]


def test_blanks_across_the_form():
    got = blank_fields(complete(contract_price_words="", owner_contact_email="", contractor_contact_phone="", project_location="",
                                contract_date="", attachment_no="", owner_country=""))
    assert got == ["Project location", "Contract date", "Owner \u2013 Country of registration", "Contract price \u2013 Price (in words)",
                   "Attachment no. that yields to the Agreement", "Owner contact \u2013 Email", "Contractor contact \u2013 Phone"]


def test_the_place_of_signing_counts_as_blank_when_nothing_is_chosen_or_the_address_is_empty():
    assert blank_fields(complete(signing_place_choice="")) == ["Place of signing"]
    assert blank_fields(complete(owner_address="")) == ["Place of signing", "Owner \u2013 Registered address"]       # in the order of the page
    assert blank_fields(complete(signing_place_choice="other", signing_place_other="Rayong")) == []
    assert blank_fields(complete(signing_place_choice="other", signing_place_other="")) == ["Place of signing"]


def test_installment_blanks():
    ts = complete(); ts.installments = []
    assert blank_fields(ts) == ["Payment installments"]
    ts.installments = [Installment("1", "50"), Installment("2", ""), Installment("", "")]
    assert blank_fields(ts) == ["Installment 2: %", "Installment 3: %"]
    ts.installments = [Installment("1", "100", condition="", required_docs="")]
    assert blank_fields(ts) == []                                           # a blank condition or document list is allowed


def test_fields_with_their_own_notice_or_a_default_or_no_use_are_not_listed():
    ts = TermSheet()
    listed = blank_fields(ts)
    for field in ("roof_owner", "vat_treatment", "deadline_mode", "start_date", "completion_date", "completion_days", "payment_days"):
        assert title(field) not in listed, field
    assert "Contractor \u2013 Country of registration" not in listed        # starts as Thailand
    assert len(listed) == len(BLANK_CHECKED) - 1 + 1                        # every checked field but the Contractor's country, plus the installments


# ---------------------------------------------------------------- one list: the required ones first, nothing named twice
def test_the_required_blanks_and_the_others_are_one_list_without_repeats():
    required, other = blank_groups(TermSheet())
    assert required == ["Project name", "Project location", "Capacity", "Owner \u2013 Company name", "Contractor \u2013 Company name",
                        "Contract price \u2013 Price (THB, number)", "The Works start and finish by"]
    assert not set(required) & set(other), "a field is named once"
    assert "Contract no." in other and "Owner \u2013 Authorised signatory" in other and "Payment installments" in other
    assert sorted(required + other) == sorted(set(required + other))
    assert blank_groups(None) == ([], []) and blank_groups(complete()) == ([], [])


def test_the_required_group_follows_the_deadline_mode():
    assert blank_groups(complete(deadline_mode="calendar", start_date="", completion_date=""))[0] == ["Start date", "Completion date"]
    assert blank_groups(complete(deadline_mode="period", completion_days=""))[0] == ["Complete within (days after signing)"]
    assert blank_groups(complete(deadline_mode=""))[0] == ["The Works start and finish by"]
    required, other = blank_groups(complete(project_name="", owner_signatory=""))
    assert required == ["Project name"] and other == ["Owner \u2013 Authorised signatory"]


def test_an_open_vat_is_one_line_in_the_check():
    assert vat_finding(complete()) is None and vat_finding(complete(vat_treatment="Inclusive of VAT")) is None
    assert vat_finding(complete(vat_treatment="")) == "VAT: not chosen. See the red notice at the VAT field."
    assert vat_finding(complete(vat_treatment="VAT 7%")) == "VAT: not chosen (the term sheet says \u201cVAT 7%\u201d). See the red notice at the VAT field."
    assert vat_finding(None) is not None


# ---------------------------------------------------------------- the page's names
def test_titles_are_the_pages_labels_never_code_names():
    for name, shown in FIELD_TITLES.items():
        assert "_" not in shown and shown[0].isupper(), (name, shown)
    assert title("contract_price_words") == "Contract price \u2013 Price (in words)" and title("completion_date") == "Completion date"
    assert label_on_page("contract_price_words") == "Price (in words)" and label_on_page("project_name") == "Project name"
    assert title("some_unknown_field") == "Some unknown field" and title("installments") == "Payment installments"
    assert len({v for v in FIELD_TITLES.values()}) == len(FIELD_TITLES), "two fields share a title"
    assert all(f in FIELD_TITLES for f in BLANK_CHECKED) and DASH in title("owner_signatory")


def test_every_term_sheet_field_has_a_title():
    missing = [f for f in TermSheet.__dataclass_fields__ if f not in FIELD_TITLES]
    assert missing == [], missing


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"\n{len(tests)} term sheet check tests passed.")
