# Billing rules

## Daily rate
A plan's daily rate is its price divided by its own period length in days: 30 for monthly plans, 365 for annual plans.

## Upgrades
An upgrade charge is (new plan's daily rate - old plan's daily rate) x days remaining in the period.
Both plans must have the same period length. If they don't, raise ValueError.

## Invoice order
1. Start with the subtotal.
2. Apply the discount percentage.
3. Add tax, calculated on the discounted amount.
4. Round the total to 2 decimal places, with halves rounding up (0.125 becomes 0.13).

Do not round before the last step.

## Regions
Tax rates are looked up by region. An unknown region is an error, never zero tax.
