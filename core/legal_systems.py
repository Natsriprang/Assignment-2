"""The elements a draft is checked for before it is signed, for each governing law the app has a list for. Pure code, no AI.

The lists are written from two sources, named in each entry, and have NOT been reviewed by a lawyer; the person who owns the app checks
them against the sources. The sentence under each element ("look_for") is the only thing the AI is told about the law: it is never asked
for the number of a section, an article or a case. `cites` records what the source itself cites, for the reader who checks the list
against the source; it is never shown to the AI or on the page.

A governing law that matches no list gets the general list (GENERIC) and a warning that no list was prepared for it."""
import re
from dataclasses import dataclass

from core.governing_law import law_name


@dataclass(frozen=True)
class Element:
    key: str
    title: str
    look_for: str
    facts: tuple = ()                    # keys of the facts core.readiness checks by code: when one of them fails the element is not complete
    cites: str = ""


@dataclass(frozen=True)
class LegalSystem:
    key: str
    name: str
    aliases: tuple
    source: str
    url: str
    elements: tuple
    note: str = ""


AUSTRALIA = LegalSystem(
    "australia", "Australia",
    ("australia", "australian", "commonwealth of australia", "victoria", "victorian", "new south wales", "nsw", "queensland", "western australia",
     "south australia", "tasmania", "northern territory", "australian capital territory"),
    "The Law Handbook, \u201cElements of a contract\u201d (Fitzroy Legal Service, current as of 1 September 2024)",
    "https://www.thelawhandbook.org.au/71-how-contract-law-works/elements-of-a-contract-2xw6m-lxpbe",
    (
        Element("offer_acceptance", "Offer and acceptance",
                "A contract is formed when a definite offer is accepted without qualification. For a draft that both Parties are to sign, look for the "
                "Parties being identified and the work and the price being stated clearly enough for each of them to accept, with nothing essential left open.",
                ("parties_named", "work_described", "price_stated")),
        Element("intention", "Intention to create legal relations",
                "The Parties must objectively intend a legally binding agreement; between businesses dealing at arm's length this is normally presumed. "
                "Look for wording that shows a binding commercial agreement (obligations, a statement that it is an agreement, a signature block)."),
        Element("consideration", "Consideration",
                "Each Party gives something of value for the other's promise; it need not be money. Look for what the Owner gives (the price and its "
                "payment) and what the Contractor gives (the construction and installation work).",
                ("price_stated", "work_described")),
        Element("capacity", "Legal capacity of the Parties",
                "The Parties must be able to make a contract. A company acts through people who have its authority. Look for the Parties being identified "
                "as companies with their registration details, and for named authorised signatories. Whether a person really has capacity or authority "
                "cannot be seen from the draft alone.",
                ("parties_identified", "signatories_named"),
                "Corporations Act 2001 (Cth) ss 124-126, as cited by the source"),
        Element("consent", "Genuine consent",
                "Each Party's consent must be free of mistake, misrepresentation, duress, undue influence and unconscionable conduct. A draft cannot show how "
                "a Party came to sign. Look only for signs in the draft itself; usually the answer is that it cannot be told from the draft."),
        Element("legality", "Legality",
                "The purpose of the contract and its terms must not be illegal or against public policy. Look at what the Contractor is to do and whether "
                "any term requires or encourages something unlawful.",
                ("work_described",)),
    ),
    "The source is a Victorian handbook; the law of another state or territory may differ.")

THAILAND = LegalSystem(
    "thailand", "Thailand",
    ("thailand", "thai", "kingdom of thailand", "\u0e44\u0e17\u0e22", "\u0e1b\u0e23\u0e30\u0e40\u0e17\u0e28\u0e44\u0e17\u0e22"),
    "ThaiLawWise Legal Blog, \u201cKey principles of contracts and contract auditing\u201d (10 September 2025)",
    "https://www.thailawwise.com/blog/73/key-principles-of-contracts-and-contract-auditing/",
    (
        Element("offer_acceptance", "Offer and acceptance",
                "The contract arises when an offer and an acceptance meet and agree in everything. For a draft that both Parties are to sign, look for the "
                "Parties being identified and the work and the price being stated clearly enough that signing is a full acceptance.",
                ("parties_named", "work_described", "price_stated"),
                "section 361 of the Civil and Commercial Code, as cited by the source"),
        Element("lawful_purpose", "Lawful purpose",
                "The purpose of the contract must not be forbidden by law or be against public order or good morals. Look at what the Contractor is to do "
                "and whether any term requires something unlawful.",
                ("work_described",),
                "section 150, as cited by the source"),
        Element("capacity", "Capacity of the Parties",
                "Each Party must be able to make a contract, and a company acts through its authorised people. Look for the Parties being identified as "
                "companies with their registration details, and for named authorised signatories. Capacity itself cannot be seen from the draft alone.",
                ("parties_identified", "signatories_named"),
                "sections 21, 29 and 32, as cited by the source"),
        Element("genuine_intent", "Genuine expression of intention",
                "Each Party's agreement must be voluntary and free of mistake, threat and fraud. A draft cannot show this. Look only for signs in the draft "
                "itself; usually the answer is that it cannot be told from the draft.",
                (), "sections 156-157, 159 and 164, as cited by the source"),
        Element("reciprocal", "Reciprocal obligations",
                "Each Party owes the other something in return: here the Owner pays the price and the Contractor does the work. Look for the Owner's "
                "obligation to pay (the price and when it is paid) and the Contractor's obligation to do the work. This law's list has no separate "
                "element called consideration.",
                ("price_stated", "work_described")),
        Element("form", "Form of the contract",
                "Some kinds of contract must follow a form the law prescribes (for example in writing and signed, or registered) or they are not complete. "
                "Look at how the draft is to be signed (the signature block and the signatories). Whether the law prescribes a form for this kind of contract "
                "cannot be told from the draft: answer that it cannot be told, unless the draft shows a gap in its own signing.",
                ("signatories_named",)),
    ),
    "The source is a general legal blog, not the Code itself, and has no element for stamp duty.")

GENERIC = LegalSystem(
    "generic", "General list",
    (),
    "No list was prepared for this law: a general list of what any written contract needs",
    "",
    (
        Element("parties", "The Parties are identified",
                "Both Parties are named and identified (companies with registration details and addresses).",
                ("parties_named", "parties_identified")),
        Element("agreement", "What is agreed is clear",
                "The work to be done is described clearly enough that each Party knows what it is agreeing to.", ("work_described",)),
        Element("price", "The price or other return is stated",
                "The price, or what each Party gets in return, is stated.", ("price_stated",)),
        Element("lawful", "Nothing in it is unlawful",
                "Nothing the Contractor is to do, and no term of the draft, requires something unlawful."),
        Element("signing", "The draft is set up to be signed",
                "Each Party has a named authorised signatory and a place to sign.", ("signatories_named",)),
    ),
    "")

SYSTEMS = (AUSTRALIA, THAILAND)


def match_system(governing_law):
    """(system, why) for the governing law as the user typed it. `system` is the LegalSystem whose list applies, or None when the text
    matches no list, or matches two (it is never guessed); `why` says in a sentence what happened."""
    name = law_name(governing_law)
    text = re.sub(r"\s+", " ", name.lower())
    if not text:
        return None, "No governing law is written."
    hits = []
    for system in SYSTEMS:
        for alias in system.aliases:
            found = alias in text if not alias.isascii() else re.search(r"\b" + re.escape(alias) + r"\b", text)
            if found:
                hits.append(system)
                break
    if len(hits) == 1:
        return hits[0], ""
    if len(hits) > 1:
        return None, f"\u201c{name}\u201d names more than one of the laws that have a list, so none was used."
    return None, f"No list of elements was prepared for \u201c{name}\u201d."
