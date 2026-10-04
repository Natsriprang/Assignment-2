"""Values taken from the term sheet and written into the clause text. Pure code, no AI."""
from core.vat import CLAUSE_PHRASE, vat_choice


def fill_template(library, term_sheet):
    """Writes the term sheet's values into the template clauses of `library`, in place. A value the term sheet does not
    have leaves the template wording untouched."""
    choice = vat_choice(term_sheet)
    if choice:
        for clause in library:
            if clause.key == "price_payment":
                for item in clause.items:
                    item.text = item.text.replace(CLAUSE_PHRASE, f"{choice} of VAT")
    return library
