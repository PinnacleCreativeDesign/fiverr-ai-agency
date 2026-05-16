"""External-service clients (LLMs, image generation APIs, storage).

Each client encapsulates the SDK for one provider and adds:
  * Async lifecycle (constructed once per process, shared by all agents)
  * Cost accounting where the provider exposes usage
  * Thin convenience helpers for the patterns the pipeline actually uses

Agents take a client as a constructor dependency — never import an SDK directly.
"""

from agency.clients.anthropic_client import AnthropicClient, CompletionResult
from agency.clients.fal_client import (
    FalClient,
    GeneratedImage,
    GenerationResult,
    ImageSize,
)

__all__ = [
    "AnthropicClient",
    "CompletionResult",
    "FalClient",
    "GeneratedImage",
    "GenerationResult",
    "ImageSize",
]
