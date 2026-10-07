"""Clauses of the template that point at another clause by what it is about, so that taking the other clause out leaves them
pointing at nothing. Pure code, no AI. The table is short on purpose: it was made by reading the template (only these references are
real; the other mentions of a topic, such as "notice" or "payment", are ordinary words), and tests/test_dependencies.py fails when a
phrase is no longer in its clause, so the table cannot go stale unnoticed. The template's numbered references ("clause 3.2") all
point at the clause they are in, which renumbering already keeps right."""
from core import wording

# (clause that refers, clause it refers to, words of the clause that refers to it)
DEPENDENCIES = [
    ("suspension", "force_majeure", "force majeure"),
    ("termination", "suspension", "the Works are suspended"),
    ("termination", "force_majeure", "force majeure"),
]


def _sentence_with(clause, phrase):
    wanted = phrase.lower()
    return next((text for _, text in wording.units(clause) if wanted in wording.norm(text).lower()), None)


def broken_references(library):
    """[{"clause_key", "clause", "target_key", "target", "phrase", "sentence"}] for every clause that is in the draft, refers to a clause
    that is not, and still has the words that refer to it."""
    by_key = {c.key: c for c in library}
    found = []
    for source, target, phrase in DEPENDENCIES:
        src, tgt = by_key.get(source), by_key.get(target)
        if src is None or tgt is None or not src.included or tgt.included:
            continue
        sentence = _sentence_with(src, phrase)
        if sentence is not None:
            found.append({"clause_key": source, "clause": src.title, "target_key": target, "target": tgt.title, "phrase": phrase,
                          "sentence": wording.norm(sentence)})
    return found
