"""Helpers for the draft's clause selection (clause key -> included flag)."""
from core.clause_data import build_library
from core.clause_params import resolve_clause
from core.drafted import insert_drafted
from core.fill import fill_template
from core.wording import apply_edits


def merge_into_parents(library):
    """An optional clause with a `parent` is written as numbered items at the end of that clause when it is ticked and the parent is in the
    draft: its items move to the parent and it keeps its place in the list, ticked, with no items of its own (it is not a clause of the contract:
    see Clause.in_contract). This way the clause stays in the picker, can be unticked, and the AI sees that it is in the draft."""
    by_key = {c.key: c for c in library}
    for clause in library:
        parent = by_key.get(clause.parent) if clause.parent else None
        if parent is not None and clause.included and parent.included:
            parent.items.extend(clause.items)
            clause.items = []
    return library


def library_for(included, limits=None, drafted=None, term_sheet=None, edits=None, failed=None):
    """A fresh clause library with the selection applied, the parameters (caps) resolved, the term sheet's values
    written in, the accepted wording changes (`edits`, see core.wording) applied, and the drafted new clauses inserted.
    Keys missing from `included` keep their default; limits missing from `limits` keep theirs. An edit whose sentence
    is no longer in the clause is left out and added to `failed`."""
    library = build_library()
    for clause in library:
        clause.included = included.get(clause.key, clause.included)
        resolve_clause(clause, limits)
    library = merge_into_parents(library)
    fill_template(library, term_sheet)
    apply_edits(library, edits, failed)
    return insert_drafted(library, drafted or [])
