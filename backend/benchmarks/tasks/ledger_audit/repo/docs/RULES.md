# Ledger rules

1. **Rounding.** Money is rounded to 2 decimal places, with halves rounding away from zero: 2.675 becomes 2.68 and -2.675 becomes -2.68.
2. **Exchange rates.** Conversion uses the most recent rate on or before the transaction date. No such rate raises NoRate.
3. **Closed periods.** Closing a period on date D closes D and everything before it. Posting into a closed period raises ClosedPeriod.
4. **Idempotency.** Posting an entry id that was already posted changes nothing and returns False. A new entry returns True.
5. **Reversals.** A reversal posts the opposite amount on the same account and date, with the id `R-<original id>`. Reversing an entry twice raises AlreadyReversed.
6. **Limits.** A standard account can't go below 0. A credit account can reach exactly minus its credit limit but not beyond. Breaking a limit raises InsufficientFunds and changes nothing.
7. **Fees.** A fee is 1.5% of the absolute amount, at least 0.30 and at most 25.00, then rounded. Reversals have no fee.
8. **Statements.** A statement covers start to end, both included, in date order, with same-date entries in posting order. The opening balance is everything before start, and each line carries the running balance.
9. **Transfers.** A transfer posts to both accounts or neither. If either side fails, neither balance changes.
