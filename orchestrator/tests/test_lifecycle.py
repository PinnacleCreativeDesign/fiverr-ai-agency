"""Unit tests for `agent_lifecycle`.

These tests use a `MagicMock(spec=Database)` — no real Supabase. They verify
the contract every agent depends on: clean exit → completed run + idle status;
exception → errored run + errored status + re-raise.
"""

from __future__ import annotations

import pytest

from agency.lifecycle import AgentRun, agent_lifecycle
from tests.conftest import AGENT_ID, ORDER_ID, RUN_ID


async def test_lifecycle_clean_exit_marks_run_completed(mock_db):
    async with agent_lifecycle(mock_db, "brief_clarification", ORDER_ID) as run:
        assert isinstance(run, AgentRun)
        assert run.run_id == RUN_ID
        assert run.agent_id == AGENT_ID
        assert run.order_id == ORDER_ID

        run.set_input(brief="hello")
        run.set_output(score=0.9)
        run.log("Did the thing")
        run.add_cost(0.05)

    # start + finish were both called exactly once
    mock_db.start_agent_run.assert_awaited_once()
    mock_db.finish_agent_run.assert_awaited_once()

    finish_kwargs = mock_db.finish_agent_run.await_args.kwargs
    assert finish_kwargs["status"] == "completed"
    assert finish_kwargs["log_summary"] == "Did the thing"
    assert finish_kwargs["cost_usd"] == 0.05
    assert finish_kwargs["input_data"] == {"brief": "hello"}
    assert finish_kwargs["output_data"] == {"score": 0.9}

    # Status was set to processing first, then idle
    assert mock_db.set_agent_status.await_count == 2
    first_call, second_call = mock_db.set_agent_status.await_args_list
    assert first_call.kwargs["current_status"] == "processing"
    assert second_call.kwargs["current_status"] == "idle"
    assert second_call.kwargs["current_order_id"] is None


async def test_lifecycle_exception_marks_run_errored_and_reraises(mock_db):
    with pytest.raises(ValueError, match="boom"):
        async with agent_lifecycle(mock_db, "brief_clarification", ORDER_ID) as run:
            run.log("about to fail")
            raise ValueError("boom")

    mock_db.finish_agent_run.assert_awaited_once()
    finish_kwargs = mock_db.finish_agent_run.await_args.kwargs
    assert finish_kwargs["status"] == "error"
    assert "ValueError" in finish_kwargs["error_message"]
    assert "boom" in finish_kwargs["error_message"]

    # Status was set to processing first, then error
    assert mock_db.set_agent_status.await_count == 2
    last_call = mock_db.set_agent_status.await_args_list[-1]
    assert last_call.kwargs["current_status"] == "error"
    # Error status preserves order/run context for debugging
    assert last_call.kwargs["current_order_id"] == ORDER_ID
    assert last_call.kwargs["current_run_id"] == RUN_ID


async def test_lifecycle_accumulates_cost(mock_db):
    async with agent_lifecycle(mock_db, "brief_clarification", ORDER_ID) as run:
        run.add_cost(0.01)
        run.add_cost(0.02)
        run.add_cost(0.03)

    finish_kwargs = mock_db.finish_agent_run.await_args.kwargs
    assert finish_kwargs["cost_usd"] == pytest.approx(0.06)


async def test_lifecycle_set_input_merges_keys(mock_db):
    async with agent_lifecycle(mock_db, "brief_clarification", ORDER_ID) as run:
        run.set_input(a=1)
        run.set_input(b=2)

    finish_kwargs = mock_db.finish_agent_run.await_args.kwargs
    assert finish_kwargs["input_data"] == {"a": 1, "b": 2}


# ── System-agent path (order_id starts None, set during execution) ──────────


async def test_lifecycle_accepts_none_order_id_for_system_agents(mock_db):
    """Intake Parser starts with no order_id — schema permits this for system agents."""
    async with agent_lifecycle(mock_db, "brief_clarification", order_id=None) as run:
        assert run.order_id is None
        run.log("just inspecting")

    # start_agent_run was called with order_id=None
    start_kwargs = mock_db.start_agent_run.await_args.kwargs
    assert start_kwargs["order_id"] is None

    # set_agent_status processing call had current_order_id=None
    first_status_call = mock_db.set_agent_status.await_args_list[0]
    assert first_status_call.kwargs["current_order_id"] is None


async def test_lifecycle_attaches_order_id_when_set_during_execution(mock_db):
    """When run.set_order_id(...) is called, the order_id propagates to finish_agent_run."""
    async with agent_lifecycle(mock_db, "brief_clarification", order_id=None) as run:
        # Simulates Intake creating the order mid-execution.
        run.set_order_id(ORDER_ID)
        run.log("created order")

    finish_kwargs = mock_db.finish_agent_run.await_args.kwargs
    assert finish_kwargs["status"] == "completed"
    assert finish_kwargs["order_id"] == ORDER_ID


async def test_lifecycle_error_after_set_order_id_preserves_order_context(mock_db):
    """If a system agent creates the order and then errors, the failure is still
    attributed to that order so the operator can find it."""
    with pytest.raises(RuntimeError, match="downstream"):
        async with agent_lifecycle(mock_db, "brief_clarification", order_id=None) as run:
            run.set_order_id(ORDER_ID)
            raise RuntimeError("downstream")

    finish_kwargs = mock_db.finish_agent_run.await_args.kwargs
    assert finish_kwargs["status"] == "error"
    assert finish_kwargs["order_id"] == ORDER_ID

    # set_agent_status error call carried the order_id forward for operator visibility
    last_status_call = mock_db.set_agent_status.await_args_list[-1]
    assert last_status_call.kwargs["current_order_id"] == ORDER_ID
