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

    def _check_limit(self, account, new_balance):
        floor = 0 if account.credit_limit is None else -account.credit_limit
        if new_balance <= floor and new_balance != 0:
            raise InsufficientFunds(account.name)

    def post(self, entry_id, account_name, day, amount):
        if self.closed_through is not None and day < self.closed_through:
            raise ClosedPeriod(day)
        account = self.accounts[account_name]
        amount = round_money(amount)
        new_balance = round_money(account.balance + amount)
        self._check_limit(account, new_balance)
        account.balance = new_balance
        self.entries.append(Entry(entry_id, account_name, day, amount))
        return True

    def reverse(self, entry_id):
        original = next(e for e in self.entries if e.id == entry_id)
        self.reversed_ids.add(entry_id)
        return self.post(f"R-{entry_id}", original.account, original.day, original.amount)

    def transfer(self, entry_id, source, destination, day, amount):
        self.post(f"{entry_id}-in", destination, day, amount)
        self.post(f"{entry_id}-out", source, day, -amount)
