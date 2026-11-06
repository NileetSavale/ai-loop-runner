import pytest
from handlers import HANDLERS

refund = HANDLERS["refund.partial"]


def test_full_refund():
    order = refund({"id": "o", "amount": 100}, {"o": {"balance": 100}})
    assert (order["balance"], order["status"]) == (0, "refunded")


def test_two_partial_refunds_reach_zero():
    store = {"o": {"balance": 100}}
    refund({"id": "o", "amount": 40}, store)
    assert store["o"]["status"] == "partially_refunded"
    refund({"id": "o", "amount": 60}, store)
    assert (store["o"]["balance"], store["o"]["status"]) == (0, "refunded")


@pytest.mark.parametrize("amount", [101, 0, -5])
def test_bad_amounts_change_nothing(amount):
    store = {"o": {"balance": 100}}
    with pytest.raises(ValueError):
        refund({"id": "o", "amount": amount}, store)
    assert store["o"] == {"balance": 100}


def test_every_generated_handler_is_still_registered():
    assert len(HANDLERS) == 257
