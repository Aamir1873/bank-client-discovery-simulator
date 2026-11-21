"""One small wrapper around any OpenAI-compatible chat endpoint, configured from .env."""
from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, OpenAI

load_dotenv()


class AIError(Exception):
    """The model could not be reached or gave an unusable answer."""


def setting(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _client() -> OpenAI:
    base = setting("AI_BASE_URL")
    if not base:
        raise AIError("AI_BASE_URL is not set. Copy .env.example to .env and fill it in.")
    return OpenAI(base_url=base, api_key=setting("AI_API_KEY", "none"), timeout=60, max_retries=0)


def _extra_body() -> dict | None:
    raw = setting("AI_EXTRA_BODY")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise AIError("AI_EXTRA_BODY in .env is not valid JSON")


def chat(messages: list[dict], *, model: str | None = None, temperature: float = 0.5, max_tokens: int = 800, json_mode: bool = False) -> str:
    """Send messages, return the reply text. Retries once on a timeout or dropped connection."""
    model = model or setting("AI_MODEL")
    if not model:
        raise AIError("AI_MODEL is not set in .env")
    extra = {}
    # Thinking models (Qwen 3.5) spend the whole answer budget on hidden reasoning unless it is turned off.
    if setting("AI_REASONING_EFFORT"):
        extra["reasoning_effort"] = setting("AI_REASONING_EFFORT")
    if json_mode:
        extra["response_format"] = {"type": "json_object"}
    last = None
    for _ in range(2):
        try:
            r = _client().chat.completions.create(
                model=model, messages=messages, temperature=temperature, max_tokens=max_tokens, extra_body=_extra_body(), **extra
            )
            text = (r.choices[0].message.content or "").strip()
            # Some reasoning models wrap their thinking in <think> tags; never show it.
            text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S).strip()
            if not text:
                raise AIError("The model sent back an empty reply")
            return text
        except AIError:
            raise
        except (APITimeoutError, APIConnectionError) as e:
            last = e
        except Exception as e:  # wrong model name, bad key, server error
            # Some servers (Ollama's MLX runner) refuse JSON mode; ask again without it.
            if "response_format" in extra and any(w in str(e).lower() for w in ("structured", "response_format", "json")):
                extra.pop("response_format")
                continue
            raise AIError(f"The model call failed: {e}") from e
    raise AIError(f"The model did not answer. Check AI_BASE_URL and that the model is running. ({last})")


def coach_model() -> str:
    return setting("COACH_MODEL") or setting("AI_MODEL")


def parse_json(text: str) -> dict:
    """Read the first JSON object in a reply, ignoring code fences or stray words around it."""
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise AIError("The reply had no JSON in it")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise AIError(f"The reply's JSON is broken: {e}") from e
