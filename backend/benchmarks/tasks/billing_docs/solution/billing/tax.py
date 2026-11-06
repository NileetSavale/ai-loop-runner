RATES = {"us-ny": 0.08875, "de": 0.19, "uk": 0.2}


def tax_rate(region):
    if region not in RATES:
        raise ValueError(f"unknown region: {region}")
    return RATES[region]
