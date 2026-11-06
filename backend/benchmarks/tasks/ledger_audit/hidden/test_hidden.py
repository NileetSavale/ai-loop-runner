from datetime import date

import pytest
from ledger.book import Book
from ledger.errors import AlreadyReversed, ClosedPeriod, InsufficientFunds, NoRate
from ledger.fees import fee_for
from ledger.fx import convert, rate_on
from ledger.money import round_money
from ledger.statements import statement

D1, D2, D3, D4 = (date(2025, 1, d) for d in (1, 2, 3, 4))


@pytest.fixture
def book():
    book = Book()
    book.open("cash")
    book.open("card", credit_limit=100)
    return book


@pytest.mark.parametrize("value,expected", [(2.675, 2.68), (1.005, 1.01), (0.125, 0.13), (2.5, 2.5), (1.234, 1.23)])
def test_rule_1_rounding(value, expected):
    assert round_money(value) == expected


def test_rule_1_negative_halves_keep_their_size():
    assert round_money(-2.675) == -2.68


def test_rule_2_rate_on_the_day_counts():
    rates = [(D1, 1.1), (D3, 1.2)]
    assert rate_on(rates, D3) == 1.2
    assert rate_on(rates, D2) == 1.1
    assert convert(100, rates, D4) == 120.0


def test_rule_2_no_earlier_rate():
    with pytest.raises(NoRate):
        rate_on([(D2, 1.1)], D1)


def test_rule_3_closing_date_itself_is_closed(book):
    book.post("e1", "cash", D3, 10)
    book.close_period(D2)
    with pytest.raises(ClosedPeriod):
        book.post("e2", "cash", D2, 5)
    with pytest.raises(ClosedPeriod):
        book.post("e3", "cash", D1, 5)
    assert book.post("e4", "cash", D3, 5) is True
    assert book.accounts["cash"].balance == 15


def test_rule_4_repeat_post_changes_nothing(book):
    assert book.post("e1", "cash", D1, 10) is True
    assert book.post("e1", "cash", D1, 99) is False
    assert book.accounts["cash"].balance == 10 and len(book.entries) == 1


def test_rule_5_reversal_is_opposite(book):
    book.post("e1", "cash", D1, 10)
    assert book.reverse("e1") is True
    assert book.accounts["cash"].balance == 0
    reversal = book.entries[-1]
    assert (reversal.id, reversal.account, reversal.day, reversal.amount) == ("R-e1", "cash", D1, -10)


def test_rule_5_cannot_reverse_twice(book):
    book.post("e1", "cash", D1, 10)
    book.reverse("e1")
    with pytest.raises(AlreadyReversed):
        book.reverse("e1")
    assert book.accounts["cash"].balance == 0


def test_rule_6_standard_account_can_reach_zero_not_below(book):
    book.post("e1", "cash", D1, 10)
    assert book.post("e2", "cash", D1, -10) is True
    with pytest.raises(InsufficientFunds):
        book.post("e3", "cash", D1, -0.01)
    assert book.accounts["cash"].balance == 0 and len(book.entries) == 2


def test_rule_6_credit_limit_is_inclusive(book):
    assert book.post("e1", "card", D1, -100) is True
    with pytest.raises(InsufficientFunds):
        book.post("e2", "card", D1, -0.01)
    assert book.accounts["card"].balance == -100


def test_rule_6_a_refused_id_can_be_used_later(book):
    with pytest.raises(InsufficientFunds):
        book.post("e1", "cash", D1, -5)
    book.post("e0", "cash", D1, 10)
    assert book.post("e1", "cash", D1, -5) is True


@pytest.mark.parametrize("amount,fee", [(100, 1.5), (-100, 1.5), (1, 0.3), (10, 0.3), (5000, 25.0), (21, 0.32), (30.5, 0.46)])
def test_rule_7_fees(amount, fee):
    assert fee_for(amount) == fee


def test_rule_8_statement_range_order_and_running_balance(book):
    book.post("z-old", "cash", D1, 5)
    book.post("m", "cash", D3, 2)
    book.post("a", "cash", D2, 1)
    book.post("b", "cash", D2, 4)
    book.post("late", "cash", D4, 100)
    opening, lines = statement(book, "cash", D2, D3)
    assert opening == 5
    assert lines == [("a", 1, 6), ("b", 4, 10), ("m", 2, 12)]


def test_rule_8_other_accounts_stay_out(book):
    book.post("e1", "cash", D1, 5)
    book.post("e2", "card", D1, 5)
    assert statement(book, "card", D1, D1) == (0, [("e2", 5, 5)])


def test_rule_9_failed_transfer_changes_nothing(book):
    book.post("e1", "cash", D1, 10)
    with pytest.raises(InsufficientFunds):
        book.transfer("t1", "cash", "card", D1, 50)
    assert (book.accounts["cash"].balance, book.accounts["card"].balance) == (10, 0)
    assert len(book.entries) == 1


def test_rule_9_transfer_into_a_closed_period_changes_nothing(book):
    book.post("e1", "cash", D3, 10)
    book.close_period(D2)
    with pytest.raises(ClosedPeriod):
        book.transfer("t1", "cash", "card", D1, 5)
    assert (book.accounts["cash"].balance, book.accounts["card"].balance) == (10, 0)


def test_rule_9_good_transfer_moves_money(book):
    book.post("e1", "cash", D1, 10)
    book.transfer("t1", "cash", "card", D1, 4)
    assert (book.accounts["cash"].balance, book.accounts["card"].balance) == (6, 4)
