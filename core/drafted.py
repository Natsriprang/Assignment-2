"""Drafted new clauses as real clauses in the contract. A draft's sentences become its numbered items, and
the clause goes directly before the clause the user chose, so numbering, the preview and the Word file all
treat it like any other clause."""
from core.clauses import Clause, Item

FALLBACK_BEFORE = ("force_majeure", "notice")      # used when the chosen clause no longer exists
END = "end"


def make_clause(key, title, sentences):
    return Clause(key=key, title=title, items=[Item(s) for s in sentences], category="drafted")


def insert_drafted(library, drafted):
    """Inserts each draft ({"key", "title", "sentences", "before"}) into `library` in place and returns it.
    `before` is the key of the clause it goes in front of, or "end". Drafts with the same target keep their order."""
    for d in drafted:
        if not d["sentences"]:                  # every sentence cleared: the clause is left out of the contract (the page says so)
            continue
        clause = make_clause(d["key"], d["title"], d["sentences"])
        keys = [c.key for c in library]
        target = d.get("before")
        if target == END:
            library.append(clause)
            continue
        for candidate in (target, *FALLBACK_BEFORE):
            if candidate in keys:
                library.insert(keys.index(candidate), clause)
                break
        else:
            library.append(clause)
    return library
