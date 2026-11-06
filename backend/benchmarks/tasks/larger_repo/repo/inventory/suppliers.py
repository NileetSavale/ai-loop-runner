from dataclasses import dataclass, field


@dataclass
class Supplier:
    name: str
    lead_time_days: int
    skus: set = field(default_factory=set)


def fastest_supplier(suppliers, sku):
    options = [s for s in suppliers if sku in s.skus]
    return min(options, key=lambda s: s.lead_time_days, default=None)
