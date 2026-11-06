from handlers import HANDLERS


def test_partial_refund_keeps_the_remaining_balance():
    store = {"o1": {"balance": 100}}
    order = HANDLERS["refund.partial"]({"id": "o1", "amount": 30}, store)
    assert (order["balance"], order["status"]) == (70, "partially_refunded")


def test_other_handlers_still_work():
    store = {}
    assert HANDLERS["order.created"]({"id": "o2", "at": 1}, store)["status"] == "created"
