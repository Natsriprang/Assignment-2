"""Helpers for the draft's clause selection (clause key -> included flag)."""
from core.clause_data import build_library
from core.clause_params import resolve_clause


def library_for(included, limits=None):
    """A fresh clause library with the selection applied and the parameters (caps) resolved. Keys missing
    from `included` keep their default; limits missing from `limits` keep theirs."""
    library = build_library()
    for clause in library:
        clause.included = included.get(clause.key, clause.included)
        resolve_clause(clause, limits)
    return library
