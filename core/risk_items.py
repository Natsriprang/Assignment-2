"""The changes the draft makes to the standard template, as plain data for the risk check (no streamlit, no AI).

One item per change: a standard clause taken out, a sentence or point whose wording was changed (or taken out, or added), or a
clause drafted for this contract. Optional clauses ticked from the template and everything the template says by itself are not
changes. The same changes always give the same items, so a risk check can say whether the draft has changed since it was made."""
import json

from core.wording import norm

MAX_TEXT = 1500                                   # characters of one text sent to the model


def _clip(text):
    text = norm(text)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT].rstrip() + " ..."


def build_items(template_text, default_included, optional, included, edits, failed_ids=(), drafted=(), requests=None,
                words_by_edit=None, words_by_clause=None):
    """The items, in this order: clauses taken out, wording changes, clauses drafted.
    template_text: {clause key: (title, standard text)}; default_included / included: {clause key: bool}; optional: the keys of the
    optional clauses; edits: the accepted wording changes [{"id", "clause_key", "change_type", "old", "new"}], of which `failed_ids`
    no longer fit their clause and are not in the draft; drafted: the kept drafted clauses [{"key", "title", "sentences"}];
    requests / words_by_edit / words_by_clause: what the user wrote for them, when known."""
    requests, words_by_edit, words_by_clause = requests or {}, words_by_edit or {}, words_by_clause or {}
    items = []

    def add(kind, clause, before, after, words, change=""):
        items.append({"id": f"i{len(items) + 1}", "kind": kind, "clause": clause, "change": change, "before": _clip(before),
                      "after": _clip(after), "user_words": norm(words)})

    for key, (title, text) in template_text.items():
        if key not in optional and default_included.get(key, True) and not included.get(key, True):
            add("removed_clause", title, text, "", words_by_clause.get(key, ""))
    for e in edits:
        if e["id"] in failed_ids or e["clause_key"] not in template_text:
            continue
        add("wording_change", template_text[e["clause_key"]][0], e["old"] if e["change_type"] != "add" else "",
            "" if e["change_type"] == "remove" else e["new"], words_by_edit.get(e["id"], ""), e["change_type"])
    for d in drafted:
        add("new_clause", d["title"], "", " ".join(norm(s) for s in d["sentences"]), requests.get(d["key"], ""))
    return items


def snapshot(items):
    """What a risk check was made on."""
    return json.dumps(items, sort_keys=True, ensure_ascii=False)
