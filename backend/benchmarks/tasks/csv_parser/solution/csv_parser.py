def parse_csv(text):
    rows, row, position = [], [], 0
    size = len(text)
    while position < size:
        if text[position] == '"':
            field, position = _quoted(text, position + 1)
        else:
            start = position
            while position < size and text[position] != "," and not _line_end(text, position):
                position += 1
            field = text[start:position]
        row.append(field)
        if position == size:
            rows.append(row)
            return rows
        if text[position] == ",":
            position += 1
            if position == size:
                row.append("")
                rows.append(row)
                return rows
            continue
        length = _line_end(text, position)
        if not length:
            raise ValueError("unexpected text after a closing quote")
        rows.append(row)
        row = []
        position += length
    return rows


def _line_end(text, position):
    if text.startswith("\r\n", position):
        return 2
    return 1 if text[position] == "\n" else 0


def _quoted(text, position):
    parts = []
    while True:
        end = text.find('"', position)
        if end == -1:
            raise ValueError("quoted field never closed")
        parts.append(text[position:end])
        if text.startswith('""', end):
            parts.append('"')
            position = end + 2
        else:
            return "".join(parts), end + 1
