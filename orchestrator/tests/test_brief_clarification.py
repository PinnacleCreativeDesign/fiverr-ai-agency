"""Unit tests for the Brief Clarification agent.

Mocks the Anthropic client to return fixed JSON payloads and verifies the
agent's decision routing, threshold handling, and database side effects.
"""

from __future__ import annotations

import pytest

from agency.agents.brief_clarification import BriefClarification
from tests.conftest import CLARIFICATION_REQUEST_ID, ORDER_ID, make_state


async def test_high_confidence_proceeds_without_clarification(
    mock_db, mock_anthropic, settings, completion_result_factory
):
    mock_anthropic.complete_json.return_value = (
        {
            "confidence_score": 0.92,
            "rationale": "Brief is specific and actionable.",
            "needs_clarification": False,
            "questions": [],
        },
        completion_result_factory(cost_usd=0.002),
    )

    agent = BriefClarification(db=mock_db, anthropic=mock_anthropic, settings=settings)
    state = make_state(
        service_type="thumbnail",
        brief=(
            "MrBeast-style YouTube thumbnail for my gaming channel 'PixelRush'. "
            "Big shocked face on left, neon explosion behind, title text 'INSANE WIN' in "
            "bold yellow. 1280x720, cinematic."
        ),
    )

    result = await agent(state)

    assert result["confidence_score"] == 0.92
    assert result["clarification_needed"] is False
    assert "clarification_request_id" not in result

    mock_db.update_order_status.assert_awaited_once()
    update_kwargs = mock_db.update_order_status.await_args.kwargs
    assert update_kwargs["status"] == "processing"
    assert update_kwargs["confidence_score"] == 0.92
    assert update_kwargs["order_id"] == ORDER_ID

    mock_db.create_clarification_request.assert_not_called()


async def test_low_confidence_creates_clarification_request(
    mock_db, mock_anthropic, settings, completion_result_factory
):
    mock_anthropic.complete_json.return_value = (
        {
            "confidence_score": 0.30,
            "rationale": "Brief omits subject, platform, and any styling cues.",
            "needs_clarification": True,
            "questions": [
                "What is the subject of the thumbnail?",
                "Which YouTube channel is this for?",
                "Do you want any text on the thumbnail?",
            ],
        },
        completion_result_factory(cost_usd=0.003),
    )

    agent = BriefClarification(db=mock_db, anthropic=mock_anthropic, settings=settings)
    state = make_state(brief="make me a cool thumbnail")

    result = await agent(state)

    assert result["confidence_score"] == 0.30
    assert result["clarification_needed"] is True
    assert result["clarification_request_id"] == CLARIFICATION_REQUEST_ID

    update_kwargs = mock_db.update_order_status.await_args.kwargs
    assert update_kwargs["status"] == "clarification_needed"

    mock_db.create_clarification_request.assert_awaited_once()
    create_kwargs = mock_db.create_clarification_request.await_args.kwargs
    assert create_kwargs["order_id"] == ORDER_ID
    assert len(create_kwargs["questions"]) == 3
    # Draft message should be operator-friendly and include each question
    for q in create_kwargs["questions"]:
        assert q in create_kwargs["draft_message"]


async def test_threshold_is_source_of_truth_overrides_model_decision(
    mock_db, mock_anthropic, settings, completion_result_factory
):
    """If the model says `needs_clarification=False` but score is below threshold,
    the agent must still treat it as a clarification case (threshold wins)."""
    mock_anthropic.complete_json.return_value = (
        {
            "confidence_score": 0.40,  # below the default 0.65 threshold
            "rationale": "Model thinks it's fine but it's not.",
            "needs_clarification": False,  # model is wrong here
            "questions": [],  # empty — exercises the fallback path
        },
        completion_result_factory(),
    )

    agent = BriefClarification(db=mock_db, anthropic=mock_anthropic, settings=settings)
    state = make_state()

    result = await agent(state)

    assert result["clarification_needed"] is True
    mock_db.create_clarification_request.assert_awaited_once()
    # Fallback question is used when the model returns an empty list
    create_kwargs = mock_db.create_clarification_request.await_args.kwargs
    assert len(create_kwargs["questions"]) >= 1


async def test_cost_is_recorded_on_the_run(
    mock_db, mock_anthropic, settings, completion_result_factory
):
    mock_anthropic.complete_json.return_value = (
        {
            "confidence_score": 0.90,
            "rationale": "fine",
            "needs_clarification": False,
            "questions": [],
        },
        completion_result_factory(cost_usd=0.0042),
    )

    agent = BriefClarification(db=mock_db, anthropic=mock_anthropic, settings=settings)
    await agent(make_state())

    finish_kwargs = mock_db.finish_agent_run.await_args.kwargs
    assert finish_kwargs["cost_usd"] == pytest.approx(0.0042)
    assert finish_kwargs["status"] == "completed"
