RATES = {"standard": 5.0, "express": 15.0}


def shipping_cost(method, order_total, free_over=100):
    if order_total >= free_over:
        return 0.0
    return RATES[method]
