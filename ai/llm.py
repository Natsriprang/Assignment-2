"""Shared OpenAI client setup. Every AI step imports MODEL and get_client from here."""
import os
from types import SimpleNamespace

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


class CountingClient:
    """Wraps an OpenAI client and records each completed chat completion in `log`, so the app can
    show how many AI calls a run made and which step made them."""

    def __init__(self, client, log, step):
        self._client, self._log, self._step = client, log, step
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        response = self._client.chat.completions.create(**kwargs)
        self._log.append({"step": self._step, "model": kwargs.get("model")})
        return response


def call_summary(log):
    """'interpret x2, review x1' style summary of a call log."""
    counts = {}
    for entry in log:
        counts[entry["step"]] = counts.get(entry["step"], 0) + 1
    return ", ".join(f"{step} \u00d7{n}" for step, n in counts.items())


class AIStepError(Exception):
    """An AI step could not produce a usable result (refusal, cut-off or invalid output)."""


def structured_call(client, model, system, user, name, schema):
    """One chat completion that must return JSON matching `schema`. Returns the parsed dict."""
    import json

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    )
    choice = response.choices[0]
    if getattr(choice.message, "refusal", None):
        raise AIStepError(f"The model declined: {choice.message.refusal}")
    if choice.finish_reason == "length":
        raise AIStepError("The response was cut off; try again.")
    try:
        return json.loads(choice.message.content)
    except (TypeError, json.JSONDecodeError) as e:
        raise AIStepError(f"The model returned invalid JSON: {e}")
