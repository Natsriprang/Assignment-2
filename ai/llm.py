"""Shared OpenAI client setup. Every AI step imports MODEL and get_client from here."""
import os

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


def get_client(api_key=None):
    """Returns an OpenAI client, or None when no key is available."""
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    from openai import OpenAI  # imported lazily so offline tests don't need the package
    return OpenAI(api_key=key)