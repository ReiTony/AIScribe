"""AI service layer (skeleton).

Will contain business logic: caching, prompt assembly, PII scrubbing, calls to llm_client.
"""
from typing import Any, Dict


def build_cache_key(payload: Dict[str, Any]) -> str:
    # Placeholder; real implementation will hash normalized input + model version
    return "ai:placeholder"


def scrub_pii(text: str) -> str:  # noqa: D401
    """Remove or mask PII (placeholder)."""
    return text