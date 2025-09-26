"""External LLM client (skeleton).

Wraps provider SDK/HTTP calls with timeouts, retries, idempotency, and error normalization.
"""
from typing import Any, Dict


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout_ms: int = 10000) -> None:
        self.api_key = api_key
        self.model = model or "gpt-4o"
        self.timeout_ms = timeout_ms

    async def chat(self, messages: list[Dict[str, str]]) -> str:  # placeholder async signature
        raise NotImplementedError("LLM chat not implemented")


client_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global client_singleton
    if client_singleton is None:
        client_singleton = LLMClient()
    return client_singleton