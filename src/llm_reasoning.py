"""Provider-neutral LLM reasoning with deterministic fallback."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReasoningResponse:
    """LLM or deterministic response metadata."""

    provider: str
    used_llm: bool
    text: str


class LLMReasoner:
    """Small OpenAI/Groq/Ollama-compatible reasoning abstraction.

    The agent always works without external credentials. If a provider cannot
    be called, callers receive the deterministic fallback text instead.
    """

    def __init__(self, provider: str = "mock", model: str | None = None) -> None:
        self.provider = provider.lower().strip()
        self.model = model or self._default_model(self.provider)

    def explain(self, prompt: str, fallback: str) -> ReasoningResponse:
        """Return LLM-enhanced reasoning or deterministic fallback."""

        if self.provider == "mock":
            return ReasoningResponse(provider="mock", used_llm=False, text=fallback)

        try:
            if self.provider == "openai":
                text = self._chat_completion(
                    url="https://api.openai.com/v1/chat/completions",
                    api_key=os.getenv("OPENAI_API_KEY", ""),
                    model=self.model,
                    prompt=prompt,
                )
            elif self.provider == "groq":
                text = self._chat_completion(
                    url="https://api.groq.com/openai/v1/chat/completions",
                    api_key=os.getenv("GROQ_API_KEY", ""),
                    model=self.model,
                    prompt=prompt,
                )
            elif self.provider == "ollama":
                text = self._ollama_completion(prompt)
            else:
                return ReasoningResponse(provider=self.provider, used_llm=False, text=fallback)
        except (OSError, urllib.error.URLError, KeyError, ValueError, TimeoutError):
            return ReasoningResponse(provider=self.provider, used_llm=False, text=fallback)

        return ReasoningResponse(provider=self.provider, used_llm=True, text=text or fallback)

    @staticmethod
    def _default_model(provider: str) -> str:
        return {
            "openai": "gpt-4o-mini",
            "groq": "llama-3.1-70b-versatile",
            "ollama": "llama3.1",
            "mock": "deterministic",
        }.get(provider, "deterministic")

    @staticmethod
    def _chat_completion(url: str, api_key: str, model: str, prompt: str) -> str:
        if not api_key:
            raise ValueError("Missing API key")
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "Write concise executive project-health reasoning in business language.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data["choices"][0]["message"]["content"]).strip()

    def _ollama_completion(self, prompt: str) -> str:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        request = urllib.request.Request(
            f"{base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        return str(data.get("response", "")).strip()
