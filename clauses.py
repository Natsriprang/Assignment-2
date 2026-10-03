"""Clause data model: a Clause holds an ordered list of Items. Item text is stored WITHOUT its
number prefix -- the "{clause_number}.{position}" prefix is generated on render, so it can never
go stale when clauses are added, removed, or reordered."""
import re
from dataclasses import dataclass, field


@dataclass
class Item:
    text: str
    lettered: list = field(default_factory=list)   # (a)/(b)/(c) sub-points, never numbered
    refs: list = field(default_factory=list)        # positions of other items in this clause that `text` mentions by number


@dataclass
class Clause:
    key: str
    title: str
    items: list = field(default_factory=list)              # list[Item]; empty for un-numbered clauses
    plain_paragraphs: list = field(default_factory=list)    # used instead of items for un-numbered clauses
    optional: bool = False
    included: bool = True
    category: str = ""
    authored_number: str = ""  # the clause number this Item text is actually phrased against;
    # fixed once in build_library() and never recomputed from the current included/order state.


REF_PATTERN = re.compile(r"clause (\d+[A-Za-z]?)(?:\.(\d+))?", re.IGNORECASE)


def cross_reference_scan(clauses):
    """Flags any 'clause N[.N]' mention whose N is not this clause's own authored_number -- i.e. a
    reference to a DIFFERENT clause, which renumbering does not rewrite automatically."""
    flagged = []
    for clause in clauses:
        for item in clause.items:
            for text in [item.text] + item.lettered:
                for m in REF_PATTERN.finditer(text):
                    if m.group(1) != clause.authored_number:
                        flagged.append((clause.key, text, m.group(0)))
    return flagged