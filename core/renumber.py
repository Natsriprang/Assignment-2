"""Recompute clause and item numbers from the current included/order state."""


def renumber_and_render(clauses):
    """Returns [(display_number, clause, [rendered_item_strings]), ...]."""
    included = [c for c in clauses if c.included]
    result = []
    for i, clause in enumerate(included):
        new_number = str(i + 1)
        old_number = clause.authored_number or new_number
        rendered_items = []
        for pos, item in enumerate(clause.items, start=1):
            def fix_refs(s):
                return s.replace(f"clause {old_number}.", f"clause {new_number}.") if old_number != new_number else s

            rendered_items.append(f"{new_number}.{pos} {fix_refs(item.text)}")
            for sub in item.lettered:
                rendered_items.append(f"    {fix_refs(sub)}")
        result.append((new_number, clause, rendered_items))
    return result