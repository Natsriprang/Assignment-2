"""Helpers for the draft's clause selection (clause key -> included flag)."""
from core.clause_data import build_library


def library_for(included):
    """A fresh clause library with the given selection applied. Keys missing from `included`
    keep their default."""
    library = build_library()
    for clause in library:
        clause.included = included.get(clause.key, clause.included)
    return library
