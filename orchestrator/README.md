# Orchestrator

LangGraph-based orchestrator and agent runtime for the Fiverr AI Agency pipeline.

This package contains:
- A typed config layer (`pydantic-settings`)
- An async Supabase wrapper (`db.py`)
- A uniform agent lifecycle (`lifecycle.py`) that handles audit-trail and live-status writes for every agent
- The LangGraph state machine that routes orders through the pipeline (`graph.py`)
- One concrete agent so far: **Brief Clarification** — scores the brief and drafts clarifications when needed
- A CLI entry point (`agency run-once`)

## Layout

```
orchestrator/
├── pyproject.toml
├── README.md
├── src/
│   └── agency/
│       ├── __init__.py            # public re-exports
│       ├── config.py              # pydantic-settings env loader
│       ├── db.py                  # async Supabase wrapper
│       ├── lifecycle.py           # agent run/status context manager
│       ├── state.py               # LangGraph WorkflowState TypedDict
│       ├── graph.py               # state machine builder + routing
│       ├── cli.py                 # `agency` command
│       ├── clients/
│       │   ├── __init__.py
│       │   └── anthropic_client.py
│       └── agents/
│           ├── __init__.py
│           ├── base.py            # abstract Agent base class
│           └── brief_clarification.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_lifecycle.py
    ├── test_brief_clarification.py
    └── test_anthropic_client.py
```

## Install

```powershell
# from orchestrator/
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

The package uses the `src/` layout, so `pip install -e .` is required before
`import agency` works.

## Environment

The orchestrator reads `.env` from `orchestrator/` first, then falls back to
the repository root `.env` (so you can keep one shared `.env`). See
`../.env.example` for the variable list.

Required for the orchestrator to even start:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ANTHROPIC_API_KEY`

Per generation-agent (as they are added):
- `FAL_KEY` for any Flux-based agent
- `REPLICATE_API_TOKEN` for SDXL via Replicate or vectorization
- `OPENAI_API_KEY` for DALL-E 3 fallback

## Running

```powershell
# Process the oldest pending order and exit.
agency run-once
```

`run-loop` is reserved for the next milestone and currently exits with code 2.

## Agent contract

Every agent inherits `agency.agents.base.Agent`, sets a class-level `agent_key`
that matches a row in the `agents` table, and implements `execute(state, run)`:

```python
from agency.agents.base import Agent
from agency.lifecycle import AgentRun
from agency.state import WorkflowState


class MyAgent(Agent):
    agent_key = "my_agent_key"  # validated at import time by __init_subclass__

    async def execute(self, state: WorkflowState, run: AgentRun) -> WorkflowState:
        run.set_input(...)
        # ... do work ...
        run.set_output(...)
        run.log("One-line summary for the dashboard")
        run.add_cost(0.12)
        return {"some_field": some_value}  # partial state — LangGraph merges
```

The base class wraps every call with `agent_lifecycle`, which:
- Inserts the `agent_runs` row at start
- Flips `agent_status.current_status` to `processing`
- Marks the run `completed` on clean exit and `error` on exception
- Re-raises exceptions so the graph can decide whether to retry

The DB trigger `agent_runs_update_counters` maintains `total_runs` / `total_errors`
atomically — application code never touches those.

## Tests

```powershell
pytest                 # full suite
ruff check src tests   # lint
mypy src               # type check
```

All tests use a `MagicMock(spec=Database)` and a `MagicMock(spec=AnthropicClient)` —
no real Supabase or Claude calls. Integration tests against a local Supabase
(`supabase start`) are a future milestone.

## What's wired and what isn't

Wired end-to-end:
- `agency run-once` picks a pending order from Supabase
- Runs it through `START → brief_clarification → (halt | proceed) → END`
- Persists confidence score on `orders`, drafts a `clarification_requests` row if needed
- All status changes flow into `agent_runs` and `agent_status` via the lifecycle wrapper

Not yet wired (next milestone):
- Intake — n8n workflow that inserts `orders` rows from Fiverr emails
- Prompt Engineering — first downstream agent after Brief Clarification proceeds
- Generation agents (Thumbnail, Social Graphics, etc.)
- Editing + QC + Delivery
- Dashboard
