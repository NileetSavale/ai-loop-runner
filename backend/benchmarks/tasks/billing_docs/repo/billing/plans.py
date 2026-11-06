from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    name: str
    price: float
    period_days: int


PLANS = {
    "monthly_basic": Plan("monthly_basic", 30.0, 30),
    "monthly_pro": Plan("monthly_pro", 60.0, 30),
    "annual_basic": Plan("annual_basic", 300.0, 365),
    "annual_pro": Plan("annual_pro", 600.0, 365),
}
