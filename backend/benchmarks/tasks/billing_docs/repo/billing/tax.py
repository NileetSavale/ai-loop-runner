RATES = {"us-ny": 0.08875, "de": 0.19, "uk": 0.2}


def tax_rate(region):
    return RATES.get(region, 0.0)
