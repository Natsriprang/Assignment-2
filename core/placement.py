"""Where a drafted new clause goes. If the references it was drafted from sit in a particular place in the author's
own contracts, the new clause goes in the same place: directly before the clause that follows them there. Pure code."""
from collections import Counter


def placement_from_references(refs, clauses):
    """`refs` are the references the clause was drafted from, in the order they were chosen. `clauses` is
    [(key, title, included)] for the template clauses in contract order. Returns (before_key, reason), or None
    when the references say nothing about position. A target clause that is switched off is skipped: the new clause
    goes before the next one that is in the draft, or at the end."""
    votes = Counter(r.before_clause for r in refs if r.before_clause)
    if not votes:
        return None
    best = max(votes.values())
    target = next(r.before_clause for r in refs if r.before_clause and votes[r.before_clause] == best)   # a tie goes to the first chosen
    keys = [k for k, _, _ in clauses]
    if target not in keys:
        return None
    titles = {k: t for k, t, _ in clauses}
    before = next((k for k, _, included in clauses[keys.index(target):] if included), "end")
    if before == target:
        return before, f"before \u201c{titles[target]}\u201d."
    if before == "end":
        return before, f"at the end (\u201c{titles[target]}\u201d and what follows it are not in this draft)."
    return before, f"before \u201c{titles[before]}\u201d (\u201c{titles[target]}\u201d is not in this draft)."
