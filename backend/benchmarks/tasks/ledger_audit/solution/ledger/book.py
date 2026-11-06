from dataclasses import dataclass, field

from ledger.errors import AlreadyReversed, ClosedPeriod, InsufficientFunds
from ledger.money import round_money


@dataclass
class Account:
    name: str
    credit_limit: float | None = None  # None means a standard account
    balance: float = 0.0


@dataclass
class Entry:
    id: str
    account: str
    day: object
    amount: float


@dataclass
class Book:
    accounts: dict = field(default_factory=dict)
    entries: list = field(default_factory=list)
    closed_through: object = None
    reversed_ids: set = field(default_factory=set)

    def open(self, name, credit_limit=None):
        self.accounts[name] = Account(name, credit_limit)

    def close_period(self, day):
        self.closed_through = day

    def _check_post(self, account_name, day, amount, extra=0):
        if self.closed_through is not None and day <= self.closed_through:
            raise ClosedPeriod(day)
        account = self.accounts[account_name]
        floor = 0 if account.credit_limit is None else -account.credit_limit
        new_balance = round_money(account.balance + amount + extra)
        if new_balance < floor:
            raise InsufficientFunds(account.name)
        return new_balance

    def post(self, entry_id, account_name, day, amount):
        if any(e.id == entry_id for e in self.entries):
            return False
        amount = round_money(amount)
        new_balance = self._check_post(account_name, day, amount)
        self.accounts[account_name].balance = new_balance
        self.entries.append(Entry(entry_id, account_name, day, amount))
        return True

    def reverse(self, entry_id):
        if entry_id in self.reversed_ids:
            raise AlreadyReversed(entry_id)
        original = next(e for e in self.entries if e.id == entry_id)
        posted = self.post(f"R-{entry_id}", original.account, original.day, -original.amount)
        self.reversed_ids.add(entry_id)
        return posted

    def transfer(self, entry_id, source, destination, day, amount):
        amount = round_money(amount)
        self._check_post(source, day, -amount)
        self._check_post(destination, day, amount)
        self.post(f"{entry_id}-out", source, day, -amount)
        self.post(f"{entry_id}-in", destination, day, amount)
