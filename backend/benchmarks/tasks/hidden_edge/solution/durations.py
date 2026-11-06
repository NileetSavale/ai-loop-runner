import re

_DURATION = re.compile(r"\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?\s*")


def parse_duration(text):
    match = _DURATION.fullmatch(text)
    if not match or not any(match.groups()):
        raise ValueError(f"not a duration: {text!r}")
    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds
