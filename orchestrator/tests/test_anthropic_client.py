"""Unit tests for `AnthropicClient` helpers.

The fence-stripping JSON parser is non-trivial — test it explicitly because
every JSON-mode agent depends on it.
"""

from __future__ import annotations

import pytest

from agency.clients.anthropic_client import (
    AnthropicClient,
    _parse_json_with_fence_stripping,
)


def test_parse_json_bare():
    assert _parse_json_with_fence_stripping('{"a": 1}') == {"a": 1}


def test_parse_json_with_json_fence():
    text = '```json\n{"a": 1, "b": [2, 3]}\n```'
    assert _parse_json_with_fence_stripping(text) == {"a": 1, "b": [2, 3]}


def test_parse_json_with_bare_fence():
    text = '```\n{"a": 1}\n```'
    assert _parse_json_with_fence_stripping(text) == {"a": 1}


def test_parse_json_with_leading_prose_is_rejected_unless_fenced():
    """If the model emits prose AND JSON, only fenced JSON is recoverable."""
    text = 'Here is the JSON:\n```json\n{"a": 1}\n```'
    assert _parse_json_with_fence_stripping(text) == {"a": 1}


def test_parse_json_invalid_raises_value_error():
    with pytest.raises(ValueError, match="Could not parse JSON"):
        _parse_json_with_fence_stripping("this is not json")


def test_compute_cost_matches_published_pricing():
    # 1M input tokens at $3 + 1M output tokens at $15 = $18 exactly
    cost = AnthropicClient._compute_cost(1_000_000, 1_000_000)
    assert cost == pytest.approx(18.00)

    # 100k input + 50k output = $0.30 + $0.75 = $1.05
    cost = AnthropicClient._compute_cost(100_000, 50_000)
    assert cost == pytest.approx(1.05)
