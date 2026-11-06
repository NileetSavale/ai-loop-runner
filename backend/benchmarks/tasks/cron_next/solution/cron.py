from datetime import datetime, timedelta

LIMITS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def _number(text, low, high):
    if not text.isdigit() or not low <= int(text) <= high:
        raise ValueError(f"bad value: {text!r}")
    return int(text)


def _item(item, low, high):
    base, slash, step_text = item.partition("/")
    step = 1
    if slash:
        step = _number(step_text, 1, 10 ** 6)
    if base == "*":
        start, end = low, high
    elif "-" in base:
        first, last = base.split("-", 1)
        start, end = _number(first, low, high), _number(last, low, high)
        if start > end:
            raise ValueError(f"backwards range: {item!r}")
    else:
        if slash:
            raise ValueError(f"step needs a range: {item!r}")
        start = end = _number(base, low, high)
    return set(range(start, end + 1, step))


def _field(text, low, high):
    values = set()
    for item in text.split(","):
        values |= _item(item, low, high)
    return values


def next_run(expression, after):
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("expected 5 fields")
    minutes, hours, days, months, weekdays = (_field(f, *limit) for f, limit in zip(fields, LIMITS))
    weekdays = {0 if d == 7 else d for d in weekdays}
    either = not fields[2].startswith("*") and not fields[4].startswith("*")

    def day_matches(day):
        by_month_day = day.day in days
        by_week_day = (day.weekday() + 1) % 7 in weekdays
        return by_month_day or by_week_day if either else by_month_day and by_week_day

    start = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    day = start.replace(hour=0, minute=0)
    limit = after + timedelta(days=5 * 366)
    while day <= limit:
        if day.month in months and day_matches(day):
            for hour in sorted(hours):
                for minute in sorted(minutes):
                    candidate = day.replace(hour=hour, minute=minute)
                    if candidate >= start:
                        return candidate
        day += timedelta(days=1)
    raise ValueError("nothing matches within 5 years")
