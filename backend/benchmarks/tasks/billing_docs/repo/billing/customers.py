from dataclasses import dataclass


@dataclass
class Customer:
    email: str
    plan_name: str
    region: str
