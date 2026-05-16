"""Anthropic client wrapper with cost accounting and JSON-mode helper.

Encapsulates `AsyncAnthropic` so agents never import the SDK directly. Adds:
  * Per-call cost computation from `response.usage` (input + output tokens)
  * `complete_json` helper that strips Markdown code fences before parsing
  * Single source of truth for the model id used across the pipeline
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from agency.config import Settings


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Result of a single Claude completion. `cost_usd` is in absolute dollars."""

    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class AnthropicClient:
    """Async wrapper around `AsyncAnthropic` with cost accounting."""

    # Public pricing for `claude-sonnet-4-6` as of May 2026.
    # Source: https://platform.claude.com/docs/en/about-claude/pricing
    INPUT_USD_PER_MTOK: float = 3.00
    OUTPUT_USD_PER_MTOK: float = 15.00

    def __init__(self, client: AsyncAnthropic, model: str) -> None:
        self._client = client
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> AnthropicClient:
        return cls(
            client=AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value()),
            model=settings.anthropic_model,
        )

    async def aclose(self) -> None:
        """Release underlying HTTP resources. Call once at process shutdown."""
        await self._client.close()

    @property
    def model(self) -> str:
        return self._model

    # ── Completions ─────────────────────────────────────────────────────

    async def complete(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> CompletionResult:
        """Single-turn user prompt with a system message. Returns text + cost."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "system": system,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = await self._client.messages.create(**kwargs)

        text = "".join(block.text for block in response.content if block.type == "text")
        cost = self._compute_cost(response.usage.input_tokens, response.usage.output_tokens)
        return CompletionResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=cost,
        )

    async def complete_json(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> tuple[dict[str, Any], CompletionResult]:
        """Complete and parse the response as JSON.

        Strips Markdown code fences (```json ... ```) before parsing. The system
        prompt is responsible for instructing Claude to emit valid JSON.
        Raises `ValueError` if the response can't be parsed.
        """
        result = await self.complete(
            system=system, prompt=prompt, max_tokens=max_tokens, temperature=temperature
        )
        data = _parse_json_with_fence_stripping(result.text)
        return data, result

    async def complete_json_with_image(
        self,
        *,
        system: str,
        text_prompt: str,
        image_bytes: bytes,
        image_media_type: str = "image/jpeg",
        max_tokens: int = 1024,
        temperature: float | None = None,
    ) -> tuple[dict[str, Any], CompletionResult]:
        """Vision completion: send one image + text, parse JSON response.

        Cost is computed from the SDK-reported `input_tokens` which already
        include the image's token equivalent (Anthropic rolls image tokens
        into input_tokens), so the existing pricing formula stays correct.
        """
        encoded = base64.standard_b64encode(image_bytes).decode("ascii")
        kwargs: dict[str, Any] = {
            "model": self._model,
            "system": system,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": image_media_type,
                                "data": encoded,
                            },
                        },
                        {"type": "text", "text": text_prompt},
                    ],
                }
            ],
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        response = await self._client.messages.create(**kwargs)
        text = "".join(block.text for block in response.content if block.type == "text")
        cost = self._compute_cost(response.usage.input_tokens, response.usage.output_tokens)
        result = CompletionResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=cost,
        )
        data = _parse_json_with_fence_stripping(text)
        return data, result

    # ── Cost computation ────────────────────────────────────────────────

    @classmethod
    def _compute_cost(cls, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * cls.INPUT_USD_PER_MTOK / 1_000_000
            + output_tokens * cls.OUTPUT_USD_PER_MTOK / 1_000_000
        )


def _parse_json_with_fence_stripping(text: str) -> dict[str, Any]:
    """Parse JSON, tolerant of Markdown code-fence wrapping."""
    stripped = text.strip()

    # Fast path: already valid JSON.
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Strip Markdown fences if present.
    if "```" in stripped:
        # Split on triple backticks; odd-indexed parts are inside fences.
        parts = stripped.split("```")
        for i in range(1, len(parts), 2):
            candidate = parts[i]
            # Drop optional language tag on the first line.
            if "\n" in candidate:
                first_line, rest = candidate.split("\n", 1)
                if first_line.strip().lower() in {"json", ""}:
                    candidate = rest
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                continue

    snippet = text[:200].replace("\n", " ")
    raise ValueError(f"Could not parse JSON from Claude response: {snippet!r}")
