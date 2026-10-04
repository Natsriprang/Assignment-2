"""Figures in a text, written as digits or as words."""
import re

_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen".split())}
_WORDS.update({"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
               "ninety": 90, "hundred": 100})
_TENS = {w for w, v in _WORDS.items() if v in range(20, 100)}


def numbers_in(text):
    """'two-year' -> {2}, 'twenty-five' -> {20, 5, 25}, '7 days' -> {7}."""
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", text.lower())
    values = {float(t) for t in tokens if t[0].isdigit()}
    for i, t in enumerate(tokens):
        if t in _WORDS:
            values.add(float(_WORDS[t]))
            if t in _TENS and i + 1 < len(tokens) and tokens[i + 1] in _WORDS and 0 < _WORDS[tokens[i + 1]] < 10:
                values.add(float(_WORDS[t] + _WORDS[tokens[i + 1]]))
    return values
