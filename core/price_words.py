"""Reads the contract price written in English words ("One-hundred Thousand", "two million five hundred thousand baht") as a
number, so it can be compared with the price in digits. Pure code. Anything it cannot read completely is None: it never
guesses."""
import re
from decimal import Decimal

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen".split())}
_TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}
_SCALES = {"thousand": 10**3, "million": 10**6, "billion": 10**9}
_FILLER = {"and", "only", "exactly", "thai", "thb", "just", "the", "a", "of"}


def _integer(tokens):
    """tokens like ['one', 'hundred', 'twenty', 'three', 'thousand'] -> 123000, or None."""
    total = current = 0
    seen = False
    for t in tokens:
        if t in _FILLER:
            continue
        if t in _UNITS:
            current += _UNITS[t]
        elif t in _TENS:
            current += _TENS[t]
        elif t == "hundred":
            current = (current or 1) * 100
        elif t in _SCALES:
            total += (current or 1) * _SCALES[t]
            current = 0
        else:
            return None
        seen = True
    return total + current if seen else None


def words_to_number(text):
    """A Decimal, or None if the words are not a complete English number (optionally 'baht' and 'N satang')."""
    t = re.sub(r"[-\u2010-\u2015]", " ", (text or "").lower())
    t = re.sub(r"[,.;:()]", " ", t).replace("\u00a0", " ")
    tokens = t.split()
    if not tokens or any(ch.isdigit() for ch in t):
        return None
    if "baht" in tokens:
        i = tokens.index("baht")
        whole, rest = _integer(tokens[:i]), [x for x in tokens[i + 1:] if x not in _FILLER]
        if whole is None or "baht" in rest:
            return None
        if not rest:
            return Decimal(whole)
        if rest[-1] != "satang":
            return None
        satang = _integer(rest[:-1])
        return Decimal(whole) + Decimal(satang) / 100 if satang is not None and satang < 100 else None
    whole = _integer(tokens)
    return Decimal(whole) if whole is not None else None
