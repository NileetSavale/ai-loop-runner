from datetime import date

from ledger.book import Book


def test_posting_the_same_id_twice_counts_once():
    book = Book()
    book.open("cash")
    assert book.post("e1", "cash", date(2025, 1, 1), 10) is True
    assert book.post("e1", "cash", date(2025, 1, 1), 10) is False
    assert book.accounts["cash"].balance == 10
