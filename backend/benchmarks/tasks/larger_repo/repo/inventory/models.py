from dataclasses import dataclass


@dataclass
class Product:
    sku: str
    name: str
    price: float
    on_hand: int = 0
    reserved: int = 0
