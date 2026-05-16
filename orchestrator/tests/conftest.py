"""Shared pytest fixtures.

The mock database fixture returns a `MagicMock(spec=Database)` so any method
*not* explicitly stubbed raises `AttributeError` if accessed — that's the
behavior we want; unexpected calls become test failures.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from agency.clients.anthropic_client import AnthropicClient, CompletionResult
from agency.config import Settings
from agency.db import Database

# Deterministic UUIDs so test assertions are stable.
AGENT_ID = UUID("00000000-0000-0000-0000-0000000000aa")
ORDER_ID = UUID("00000000-0000-0000-0000-0000000000b0")
RUN_ID = UUID("00000000-0000-0000-0000-0000000000c0")
CLARIFICATION_REQUEST_ID = UUID("00000000-0000-0000-0000-0000000000d0")


@pytest.fixture
def mock_db() -> MagicMock:
    """A `Database` test double with the lifecycle-critical methods stubbed.

    Tests that exercise additional methods should add stubs in the test body.
    """
    db = MagicMock(spec=Database)

    db.get_agent_by_key = AsyncMock(
        return_value={
            "id": str(AGENT_ID),
            "agent_key": "brief_clarification",
            "display_name": "Brief Clarification",
            "layer": "coordination",
        }
    )
    db.start_agent_run = AsyncMock(return_value=RUN_ID)
    db.finish_agent_run = AsyncMock()
    db.set_agent_status = AsyncMock()
    db.update_order_status = AsyncMock()
    db.create_clarification_request = AsyncMock(return_value=CLARIFICATION_REQUEST_ID)

    return db


@pytest.fixture
def mock_anthropic() -> MagicMock:
    """A `AnthropicClient` test double. Override `complete_json` per test."""
    client = MagicMock(spec=AnthropicClient)
    client.complete_json = AsyncMock()
    client.complete = AsyncMock()
    return client


@pytest.fixture
def settings() -> Settings:
    """Minimal Settings instance for tests. Doesn't touch real env or network."""
    return Settings.model_construct(
        supabase_url="https://test.supabase.co",
        supabase_service_role_key=_FakeSecret("test"),
        supabase_anon_key=None,
        supabase_db_url=None,
        anthropic_api_key=_FakeSecret("test"),
        anthropic_model="claude-sonnet-4-6",
        openai_api_key=None,
        openai_model="gpt-4o",
        fal_key=None,
        fal_flux_pro_endpoint="fal-ai/flux-pro/v1.1",
        replicate_api_token=None,
        comfyui_url="http://localhost:8188",
        storage_bucket_references="client-references",
        storage_bucket_deliverables="deliverables",
        storage_bucket_packages="delivery-packages",
        log_level="warning",
        brief_confidence_threshold=0.65,
        brand_consistency_threshold=0.75,
        visual_qc_threshold=0.70,
        max_generation_retries=2,
    )


@pytest.fixture
def completion_result_factory():
    """Build `CompletionResult` instances with sensible defaults."""

    def _build(
        text: str = "",
        input_tokens: int = 100,
        output_tokens: int = 50,
        cost_usd: float = 0.001,
    ) -> CompletionResult:
        return CompletionResult(
            text=text, input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost_usd
        )

    return _build


class _FakeSecret:
    """Minimal stand-in for `pydantic.SecretStr` in unit tests."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value

    def __repr__(self) -> str:  # pragma: no cover
        return "FakeSecret(...)"


def make_state(**overrides: Any):
    """Build a minimal `WorkflowState` for tests; overrides win over defaults."""
    base = {
        "order_id": ORDER_ID,
        "service_type": "thumbnail",
        "brief": "Test brief",
        "reference_image_urls": [],
    }
    base.update(overrides)
    return base
