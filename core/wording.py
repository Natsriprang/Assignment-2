"""Wording changes written into clause text. Pure code, no AI.

A change the user asked for is made on ONE unit of text: a numbered sentence, a lettered point, a paragraph or a table cell
(or a new sentence added at the end of a clause). The AI proposes the new text of that unit; this module finds the unit, checks the
proposal against the request, applies accepted changes to a clause library, and marks up before and after for the page.
Nothing here trusts the proposal: it must keep the rest of the sentence, change it only around the quoted words, bring in the
figures the user gave and no others, and write each figure the way the contract does (digits, then the same figure in words)."""
import difflib
import re
from decimal import Decimal, InvalidOperation

from core.clause_params import format_number, int_words, number_words
from core.clauses import Item
from core.figures import numbers_in, target_figures

KEEP_MODIFY = 0.6          # share of the old sentence's words that must survive a modify
KEEP_REMOVE = 0.3          # ... and a remove_part (which removes some of them on purpose)
MARGIN_WORDS = 2           # words around the quoted text that a rewrite may also touch (a/an, plural, a joining word)
MAX_LENGTH = 700           # characters in a new sentence
MOSTLY_NEW = 0.7           # above this share of changed words the new wording is shown plain

_FIGURE_WITH_WORDS = re.compile(r"(\d+(?:\.\d+)?)\s*%?\s*\(([A-Za-z][A-Za-z \-]*)\)")
_PAIR = re.compile(r"(\d+(?:\.\d+)?)(\s*%?\s*)\(([A-Za-z][A-Za-z \-]*)\)")        # "0.05 (zero point zero five)", "5% (five percent)"


def norm(text):
    return " ".join((text or "").split())


# ---------------------------------------------------------------------------------------- finding the unit
def units(clause):
    """[(location, text)] for every piece of text a change can apply to. A location says where the text lives."""
    out = [(("paragraph", i), p) for i, p in enumerate(clause.plain_paragraphs)]
    for i, item in enumerate(clause.items):
        out.append((("item", i), item.text))
        out += [(("lettered", i, j), sub) for j, sub in enumerate(item.lettered)]
    for t, table in enumerate(clause.tables):
        for r, row in enumerate(table["rows"]):
            out += [(("cell", t, r, c), cell) for c, cell in enumerate(row)]
    return out


_EDGE = " \t\n.,;:\u201c\u201d\"'\u2018\u2019"
_SPECIFIC = {"lettered": 0, "cell": 0, "item": 1, "paragraph": 1}          # a lettered point is more specific than the sentence it is part of


def find_unit(clause, quote):
    """(location, text) of the unit that `quote` points at. Punctuation at the ends of the quote does not matter. When more than one
    unit contains it, the most specific kind wins (a lettered point rather than the sentence it belongs to); when several of that kind
    contain it, or none does, None: it is never guessed between two similar sentences or table cells."""
    wanted = norm(quote).strip(_EDGE).lower()
    if not wanted:
        return None
    found = [(loc, text) for loc, text in units(clause) if wanted in norm(text).lower()]
    if len(found) <= 1:
        return found[0] if found else None
    best = min(_SPECIFIC[loc[0]] for loc, _ in found)
    pool = [(loc, text) for loc, text in found if _SPECIFIC[loc[0]] == best]
    return pool[0] if len(pool) == 1 else None


def unit_hits(clause, quote):
    """How many units contain the quote (0, 1 or more): why find_unit found nothing."""
    wanted = norm(quote).strip(_EDGE).lower()
    return sum(1 for _, text in units(clause) if wanted and wanted in norm(text).lower())


# ---------------------------------------------------------------------------------------- checking a proposal
def _closure(values):
    """The figures a request brings in, with the numbers its words are made of: "0.03" is spelled "zero point zero three",
    "24" is "twenty-four" (20 and 4), "120" is "one hundred and twenty" (1, 100 and 20)."""
    out = set()
    for v in values:
        out.add(v)
        out |= {float(ch) for ch in repr(v) if ch.isdigit()}
        if v == int(v) and 0 < v < 1000:
            hundreds, rest = divmod(int(v), 100)
            if hundreds:
                out |= {float(hundreds), 100.0}
            out.add(float(rest))
            if rest >= 20:
                out |= {float(rest // 10 * 10), float(rest % 10)}
    return out


def _expected_words(figure):
    try:
        value = Decimal(figure)
    except InvalidOperation:
        return None
    if value == value.to_integral():
        return int_words(int(value)) if 0 < value < 1000 else None
    return number_words(float(value)) if 0 < value <= 100 else None


def figure_mismatches(text, known=""):
    """'15 (fourteen) days' -> ['15 (fourteen)']: a figure whose words in brackets say another number. Pairs already in
    `known` (the old sentence) are not looked at again."""
    already = {m.group(0).lower() for m in _FIGURE_WITH_WORDS.finditer(known)}
    bad = []
    for m in _FIGURE_WITH_WORDS.finditer(text):
        if m.group(0).lower() in already:
            continue
        words = re.sub(r"\s+percent$", "", norm(m.group(2)).lower())
        expected = _expected_words(m.group(1))
        if expected is not None and words != expected:
            bad.append(m.group(0))
    return bad


def _word_spans(text):
    return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


def _quote_range(old, quote):
    """(first word, last word) of the quoted text in `old`, in words; None when it cannot be located."""
    at = old.lower().find(norm(quote).lower())
    if at < 0:
        return None
    end = at + len(norm(quote))
    spans = _word_spans(old)
    inside = [n for n, (s, e) in enumerate(spans) if e > at and s < end]
    return (inside[0], inside[-1]) if inside else None


def without_existing(clause, new):
    """The AI was asked for only the new sentence, but it may write the clause's own sentences again before it. Those are taken
    out, so that the clause does not get its own text twice. Only whole existing sentences, points or paragraphs are removed."""
    text = norm(new)
    for _, unit in sorted(units(clause), key=lambda u: -len(norm(u[1]))):
        u = norm(unit)
        if len(u) >= 20:
            text = re.sub(re.escape(u), " ", text, flags=re.IGNORECASE)
    return norm(text).strip()


def check_rewrite(old, new, change_type, quote, request_text):
    """"" when the new text may be written into the contract, else the reason, as a sentence for the user.
    `old` is the unit being changed ("" for an added sentence); `request_text` is what the user asked for."""
    new_n, old_n = norm(new), norm(old)
    if not new_n:
        return "The AI did not write the new wording."
    if len(new_n) > MAX_LENGTH:
        return "The new wording is too long to check."
    asked = _closure(numbers_in(request_text))
    brought_in = numbers_in(new_n) - numbers_in(old_n)
    if brought_in - asked:
        return "The new wording has a figure that you did not give."
    bad = figure_mismatches(new_n, old_n)
    if bad:
        return f"A figure and its words do not agree ({bad[0]})."
    if change_type == "add":
        return ""
    if new_n.lower() == old_n.lower():
        return "The wording would not change."
    new_numbers = numbers_in(request_text) - numbers_in(old_n)
    if new_numbers and not (new_numbers & numbers_in(new_n)):
        return "The new wording does not contain the figure you asked for."
    old_w, new_w = old_n.split(), new_n.split()
    matcher = difflib.SequenceMatcher(None, [w.lower() for w in old_w], [w.lower() for w in new_w], autojunk=False)
    kept = sum(size for _, _, size in matcher.get_matching_blocks()) / max(1, len(old_w))
    if kept < (KEEP_REMOVE if change_type == "remove_part" else KEEP_MODIFY):
        return "The new wording changes much more of the sentence than you asked for."
    quoted = _quote_range(old_n, quote)
    if quoted:
        low, high = quoted[0] - MARGIN_WORDS, quoted[1] + MARGIN_WORDS
        for tag, i1, i2, _, _ in matcher.get_opcodes():
            if tag == "equal":
                continue
            if (i1 < low or i2 - 1 > high) if i2 > i1 else (i1 < low or i1 > high + 1):
                return "The new wording changes parts of the sentence you did not ask about."
    if change_type == "remove_part" and norm(quote).lower() in new_n.lower():
        return "The part to remove is still in the new wording."
    return ""


# ---------------------------------------------------------------------------------------- taking a point or sentence out
def removal_of(unit_text, quote):
    """True when taking `quote` out of `unit_text` leaves no words (only a list label such as "7)" and punctuation): the change
    removes the whole point or sentence, and the unit itself is taken out."""
    span = _quote_span(unit_text, quote)
    if span is None:
        return False
    rest = norm(unit_text)[:span[0]] + " " + norm(unit_text)[span[1]:]
    rest = re.sub(r"[;,]?\s*\b(?:or|and)\b\s*[.;,]?\s*$", " ", rest, flags=re.IGNORECASE)      # the "; or" that joins a point to the next is not wording
    return not re.search(r"[A-Za-z]{2,}", rest)


def removable(loc):
    """A table cell cannot be taken out; a numbered sentence, a lettered point and a paragraph can."""
    return loc[0] in ("paragraph", "item", "lettered")


_LABEL = re.compile(r"^\s*(?:\((\d+)\)|(\d+)\)|\(([a-z])\)|([a-z])\))\s+")
_ENDING = re.compile(r"\s*(?:;\s*(?:or|and)|[;.,])\s*$", re.IGNORECASE)


def _ending(text):
    m = _ENDING.search(text)
    return m.group(0).strip() if m else None


def _relabel(points):
    """The labels of a list after a point was taken out: "1)", "(1)", "a)" or "(a)" counted again from the start. A list whose
    labels are not all of one of these kinds is left as it is."""
    matches = [_LABEL.match(p) for p in points]
    if not points or not all(matches):
        return points
    kinds = {next(i for i, g in enumerate(m.groups()) if g is not None) for m in matches}
    if len(kinds) != 1:
        return points
    kind = kinds.pop()
    out = []
    for n, (p, m) in enumerate(zip(points, matches)):
        mark = str(n + 1) if kind in (0, 1) else chr(ord("a") + n)
        label = {0: f"({mark})", 1: f"{mark})", 2: f"({mark})", 3: f"{mark})"}[kind]
        out.append(label + " " + p[m.end():])
    return out


def _with_ending(point, ending):
    return _ENDING.sub("", point) + ending


def _fix_endings(points, endings, removed):
    """The punctuation of a list after the point at index `removed` was taken out. Each point keeps its own ending, except that
    a last point taken out hands its ending (the full stop) to the new last one, and a second-to-last point taken out hands its
    "; or" / "; and" to the one before it. Left as it is when any point of the original list ended in something else."""
    if not points or any(e is None for e in endings):
        return points
    n, out = len(endings), list(points)
    if removed == n - 1:
        out[-1] = _with_ending(out[-1], endings[-1])
    elif removed == n - 2 and len(out) >= 2 and re.search(r"(or|and)$", endings[removed], re.IGNORECASE):
        out[-2] = _with_ending(out[-2], endings[removed])
    return out


def _delete(clause, loc):
    """Takes the unit at `loc` out of the clause. Numbers of sentences follow by themselves; the labels and the punctuation of a
    list are put right. False when it cannot be done (the only point of a list)."""
    kind = loc[0]
    if kind == "paragraph":
        del clause.plain_paragraphs[loc[1]]
        return True
    if kind == "item":
        del clause.items[loc[1]]
        return True
    if kind == "lettered":
        item = clause.items[loc[1]]
        if len(item.lettered) < 2:
            return False
        endings = [_ending(p) for p in item.lettered]
        points = item.lettered[:loc[2]] + item.lettered[loc[2] + 1:]
        item.lettered = _relabel(_fix_endings(points, endings, loc[2]))
        return True
    return False


# ---------------------------------------------------------------------------------------- repairing a proposal
def _quote_span(old, quote):
    wanted = norm(quote).strip(_EDGE)
    at = norm(old).lower().find(wanted.lower())
    return (at, at + len(wanted)) if wanted and at >= 0 else None


def splice_fragment(old, quote, new):
    """When the AI gave back only the quoted words, rewritten, instead of the whole sentence: the sentence with the quoted words
    replaced by `new`. "" when `new` is not such a fragment (it already holds the rest of the sentence, or is not a light edit
    of the quote). The result still has to pass check_rewrite."""
    span = _quote_span(old, quote)
    if span is None:
        return ""
    old_n, new_n, quote_n = norm(old), norm(new), norm(quote)
    prefix, suffix = old_n[:span[0]], old_n[span[1]:]
    new_l = new_n.lower()
    before = [w for w in prefix.split() if any(ch.isalnum() for ch in w)]        # a lone full stop is not the rest of the sentence
    after = [w for w in suffix.split() if any(ch.isalnum() for ch in w)]
    if (before and " ".join(before[:3]).lower() in new_l) or (after and " ".join(after[-3:]).lower() in new_l):
        return ""                                                    # it holds the rest of the sentence: not a fragment
    quote_w, new_w = [w.lower().strip(".,;:") for w in quote_n.split()], [w.lower().strip(".,;:") for w in new_n.split()]
    if not new_w or difflib.SequenceMatcher(None, quote_w, new_w, autojunk=False).ratio() < 0.5:     # a figure and its words change two of five
        return ""
    if suffix[:1] in ".,;:" and new_n[-1:] == suffix[:1]:
        suffix = suffix[1:]
    return norm(prefix + new_n + suffix)


def figure_swap(old, quote, request_text):
    """The sentence with the one figure in the quoted words replaced by the one new figure the user gave, written the way the
    contract writes it: digits, then the same figure in words ("0.03 (zero point zero three)"). The words come from the number,
    so they cannot disagree with it. "" unless the quote holds exactly one such figure and the request brings exactly one new one."""
    span = _quote_span(old, quote)
    if span is None:
        return ""
    old_n = norm(old)
    pairs = [m for m in _PAIR.finditer(old_n) if m.start() >= span[0] and m.end() <= span[1]]
    new_figures = target_figures(request_text) - numbers_in(old_n)
    if len(pairs) != 1 or len(new_figures) != 1:
        return ""
    value = next(iter(new_figures))
    digits = format_number(value)
    try:
        if value == int(value) and 0 < value < 1000:
            words = int_words(int(value))
        else:
            words = number_words(value)
    except ValueError:
        return ""
    if value <= 0 or len(digits.partition(".")[2]) > 2:
        return ""
    m = pairs[0]
    old_words = m.group(3)
    suffix = " percent" if old_words.lower().endswith(" percent") else ""
    return norm(old_n[:m.start()] + f"{digits}{m.group(2)}({words}{suffix})" + old_n[m.end():])


# ---------------------------------------------------------------------------------------- applying changes
_LABEL_ANY = re.compile(r"^\s*(?:\(\d+\)|\d+\)|\([a-z]\)|[a-z]\))\s+", re.IGNORECASE)
_TAIL = re.compile(r"\s*(?:;\s*(?:or|and)|[;.,])\s*$", re.IGNORECASE)


def split_point(text):
    """(label, body, ending) of a list point: "6) any change in law; or" -> ("6)", "any change in law", "; or"). A text with no label or
    no ending has "" for it."""
    t = norm(text)
    m = _LABEL_ANY.match(t)
    label, body = (t[:m.end()].strip(), t[m.end():]) if m else ("", t)
    m2 = _TAIL.search(body)
    ending = m2.group(0).strip() if m2 else ""
    return label, (body[:m2.start()] if m2 else body).strip(), ending


def core_text(text):
    """What a list point says, whatever its number or the punctuation at its end: those move when a neighbouring point is taken out."""
    return split_point(text)[1].lower()


def _find_for_edit(clause, old):
    """The unit a recorded change is about. The text as it was recorded; or, for a lettered point, the point that says the same whatever its
    number and ending are now, so that changes to neighbouring points of one list do not depend on the order they are applied in."""
    wanted = norm(old)
    exact = [(loc, text) for loc, text in units(clause) if norm(text) == wanted]
    if exact:
        return exact[0]
    core = core_text(old)
    like = [(loc, text) for loc, text in units(clause) if loc[0] == "lettered" and core and core_text(text) == core]
    return like[0] if len(like) == 1 else None


def apply_edits(library, edits, failed=None):
    """Writes each accepted change into `library` in place. An edit is {"id", "clause_key", "change_type", "old", "new",
    "summary"}. One whose sentence is no longer there (the clause text changed since) is not applied; it is added to `failed`."""
    by_key = {c.key: c for c in library}
    for edit in edits or []:
        clause = by_key.get(edit["clause_key"])
        ok = False
        if clause is not None and edit["change_type"] == "add":
            if clause.items:
                clause.items.append(Item(edit["new"]))
            else:
                clause.plain_paragraphs.append(edit["new"])
            ok = True
        elif clause is not None:
            found = _find_for_edit(clause, edit["old"])
            if found is not None:
                loc = found[0]
                ok = _delete(clause, loc) if edit["change_type"] == "remove" else (_write(clause, loc, edit["new"]) or True)
        if not ok and failed is not None:
            failed.append(edit)
    return library


def _write(clause, loc, text):
    kind = loc[0]
    if kind == "paragraph":
        clause.plain_paragraphs[loc[1]] = text
    elif kind == "item":
        clause.items[loc[1]].text = text
    elif kind == "lettered":                                      # the point keeps the number and the ending it has now
        label, _, ending = split_point(clause.items[loc[1]].lettered[loc[2]])
        clause.items[loc[1]].lettered[loc[2]] = (label + " " if label else "") + split_point(text)[1] + ending
    else:
        _, t, r, c = loc
        clause.tables[t]["rows"][r][c] = text
        if t == 0 and clause.table_rows:
            clause.table_rows = [tuple(row) for row in clause.tables[0]["rows"]]


# ---------------------------------------------------------------------------------------- two proposals for the same sentence
def merge_rewrite(base, mine, theirs):
    """A three-way merge of one sentence, word by word. `base` is the sentence a proposal was written against, `mine` the sentence as the draft
    has it now (another proposal changed it), `theirs` the new wording of the proposal. The result is the sentence with both changes, or None
    when the two changes touch the same words (or an insertion touches another change): it is never guessed. The same change made by both
    counts once."""
    b, m, t = norm(base).split(), norm(mine).split(), norm(theirs).split()
    if not b:
        return None
    low = lambda words: [w.lower() for w in words]
    if low(m) == low(b) or low(m) == low(t):
        return " ".join(t)
    if low(t) == low(b):
        return " ".join(m)

    def changes(other):
        matcher = difflib.SequenceMatcher(None, low(b), low(other), autojunk=False)
        return [(i1, i2, other[j1:j2]) for tag, i1, i2, j1, j2 in matcher.get_opcodes() if tag != "equal"]

    mine_changes, their_changes = changes(m), changes(t)
    their_changes = [c for c in their_changes if not any(c[:2] == x[:2] and low(c[2]) == low(x[2]) for x in mine_changes)]
    for a1, a2, _ in mine_changes:
        for b1, b2, _ in their_changes:
            if a1 < b2 and b1 < a2:                                  # the same words
                return None
            if (a1 == a2 or b1 == b2) and a1 <= b2 and b1 <= a2:    # an insertion that touches the other change
                return None
    out, at = [], 0
    for i1, i2, words in sorted(mine_changes + their_changes, key=lambda c: (c[0], c[1])):
        out += b[at:i1] + list(words)
        at = i2
    return " ".join(out + b[at:])


# ---------------------------------------------------------------------------------------- before and after for the page
def _escape(word):
    return re.sub(r"([\\`*_\[\]#>|~$<])", r"\\\1", word)


def diff_markup(old, new):
    """(old, new) as markdown for the page: the whole of both texts, with the words that are changed in bold on both sides (the words
    to be changed in the current wording, the words they become in the new wording)."""
    old_w, new_w = norm(old).split(), norm(new).split()
    matcher = difflib.SequenceMatcher(None, [w.lower() for w in old_w], [w.lower() for w in new_w], autojunk=False)
    before, after, changed = [], [], 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        gone, put = [_escape(w) for w in old_w[i1:i2]], [_escape(w) for w in new_w[j1:j2]]
        if tag == "equal":
            before += gone
            after += put
            continue
        if gone:
            before.append("**" + " ".join(gone) + "**")
        if put:
            after.append("**" + " ".join(put) + "**")
            changed += len(put)
    if new_w and changed / len(new_w) > MOSTLY_NEW:
        after = [_escape(w) for w in new_w]                 # a text that is mostly new is not marked word by word: bold says nothing there
    return " ".join(before), " ".join(after)
