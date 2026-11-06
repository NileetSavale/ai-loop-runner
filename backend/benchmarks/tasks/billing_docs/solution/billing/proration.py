def daily_rate(plan):
    return plan.price / plan.period_days


def upgrade_charge(old_plan, new_plan, days_remaining):
    if old_plan.period_days != new_plan.period_days:
        raise ValueError("plans must have the same period length")
    return (daily_rate(new_plan) - daily_rate(old_plan)) * days_remaining
