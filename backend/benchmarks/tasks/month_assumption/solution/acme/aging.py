def whole_months_between(start, end):
    months = (end.year - start.year) * 12 + end.month - start.month
    return months - 1 if end.day < start.day else months
