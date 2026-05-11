"""Helpers para parseo de JSON proveniente de outputs LLM."""
from __future__ import annotations

import re

_FENCE_OPEN = re.compile(r"^```(?:json)?\s*")
_FENCE_CLOSE = re.compile(r"\s*```$")


def strip_fences(content: str) -> str:
    """Elimina markdown fences ```json ... ``` del output LLM."""
    content = content.strip()
    if content.startswith("```"):
        content = _FENCE_OPEN.sub("", content)
        content = _FENCE_CLOSE.sub("", content)
    return content.strip()
