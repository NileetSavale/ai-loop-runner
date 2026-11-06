def daily_rate(plan):
    return plan.price / 30


def upgrade_charge(old_plan, new_plan, days_remaining):
    return (daily_rate(new_plan) - daily_rate(old_plan)) * days_remaining
