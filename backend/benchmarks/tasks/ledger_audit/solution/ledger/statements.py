from ledger.money import round_money


def statement(book, account, start, end):
    """Returns (opening balance, [(entry id, amount, running balance)])."""
    entries = [e for e in book.entries if e.account == account]
    opening = round_money(sum(e.amount for e in entries if e.day < start))
    lines, balance = [], opening
    for entry in sorted(entries, key=lambda e: e.day):  # stable, so same-date entries stay in posting order
        if start <= entry.day <= end:
            balance = round_money(balance + entry.amount)
            lines.append((entry.id, entry.amount, balance))
    return opening, lines
