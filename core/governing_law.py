"""The governing law field: what the user typed, as the name the contract sentence needs ("... in accordance with the laws of [*]").
The sentence already says "the laws of", so a value typed as "the laws of Thailand" or "Laws of Thailand." is cut down to "Thailand"."""
import re

_PREFIX = re.compile(r"^\s*(?:the\s+)?laws?\s+of\s+", re.IGNORECASE)


def law_name(text):
    """The place whose law governs, without a leading "the laws of" or a closing full stop. Empty when nothing is written."""
    name = re.sub(r"\s+", " ", str(text or "")).strip().rstrip(".").strip()
    name = _PREFIX.sub("", name).strip()
    return name
