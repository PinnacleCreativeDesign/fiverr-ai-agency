#!/usr/bin/env python
"""End-to-end smoke test for the Fiverr AI Agency pipeline.

Runs from the repo root with the venv active:

    python scripts/smoke_test.py              # connectivity + brief-clarification only
    python scripts/smoke_test.py --full       # full pipeline including image generation

The --full flag makes real calls to fal.ai (costs ~$0.12) and requires FAL_KEY.
Without it the test stops after Brief Clarification to verify the DB + LLM layer.
"""

from __future__ import annotations

import asyncio
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

# Ensure the orchestrator package is importable even when run from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "orchestrator" / "src"))

OK = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m·\033[0m"


def step(label: str, ok: bool, detail: str = "") -> None:
    icon = OK if ok else FAIL
    suffix = f"  {detail}" if detail else ""
    print(f"  {icon} {label}{suffix}")
    if not ok:
        sys.exit(1)


async def main(full: bool) -> None:
    print("\n═══ Fiverr AI Agency smoke test ═══\n")

    # ── 1. Env vars ──────────────────────────────────────────────────────────
    print("1. Environment")
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "ANTHROPIC_API_KEY"]
    if full:
        required += ["FAL_KEY"]
    for var in required:
        step(var, bool(os.environ.get(var)), "(set)" if os.environ.get(var) else "MISSING")

    from agency.config import get_settings
    settings = get_settings()

    # ── 2. Supabase connectivity + schema ────────────────────────────────────
    print("\n2. Supabase")
    from agency.db import Database
    db = await Database.connect(settings)
    step("connect", True)

    agent_count = (await db.raw.table("agents").select("id", count="exact").execute()).count
    step("agents seeded", (agent_count or 0) == 19, f"found {agent_count}/19")

    # ── 3. Insert synthetic order ────────────────────────────────────────────
    print("\n3. Synthetic order")
    idempotency_key = f"smoke-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    order_id: UUID = await db.create_order(
        idempotency_key=idempotency_key,
        source="manual",
        service_type="thumbnail",
        brief=(
            "MrBeast-style YouTube thumbnail for a gaming speedrun video. "
            "Big shocked face on the left, pixel art explosion behind, title 'WORLD RECORD' "
            "in bold yellow. 1280x720, high contrast, neon."
        ),
        metadata={"smoke_test": True},
    )
    step("order inserted", True, str(order_id))

    # ── 4. Verify order status ────────────────────────────────────────────────
    order = await db.get_order(order_id)
    step("order status=pending", order is not None and order["status"] == "pending")

    # ── 5. Run Brief Clarification via graph ──────────────────────────────────
    print("\n4. Brief Clarification agent")
    from agency.agents.brief_clarification import BriefClarification
    from agency.clients.anthropic_client import AnthropicClient
    from agency.state import WorkflowState

    anthropic = AnthropicClient.from_settings(settings)
    agent = BriefClarification(db=db, anthropic=anthropic, settings=settings)
    state = WorkflowState(  # type: ignore[typeddict-item]
        order_id=order_id,
        service_type="thumbnail",
        brief=order["brief"],
        reference_image_urls=[],
    )
    result = await agent(state)

    score = result.get("confidence_score", 0)
    step("confidence scored", score > 0, f"{score:.2f}")
    step("decision made", "clarification_needed" in result)

    # Check agent_runs row was created
    runs = (
        await db.raw.table("agent_runs")
        .select("*")
        .eq("order_id", str(order_id))
        .eq("status", "completed")
        .execute()
    ).data
    step("agent_runs row created", len(runs) == 1)

    if result.get("clarification_needed"):
        clarifications = (
            await db.raw.table("clarification_requests")
            .select("*")
            .eq("order_id", str(order_id))
            .execute()
        ).data
        step("clarification drafted", len(clarifications) == 1)
        print(f"\n  {INFO} Brief scored below threshold — clarification drafted.")
        print(f"    (The test brief is intentionally verbose, so this path is expected.)\n")

    if not full:
        print("\n5. Skipped (--full not set: no image generation)")
        _print_summary(order_id)
        await anthropic.aclose()
        return

    # ── 6. Prompt Engineering ─────────────────────────────────────────────────
    print("\n5. Prompt Engineering")
    from agency.agents.prompt_engineering import PromptEngineering
    pe = PromptEngineering(db=db, anthropic=anthropic)
    # Force proceed even if clarification was flagged (smoke test override)
    result["clarification_needed"] = False
    result = await pe({**state, **result})  # type: ignore[typeddict-item]
    step("refined_prompt set", bool(result.get("refined_prompt")))
    print(f"    Prompt: {textwrap.shorten(result.get('refined_prompt',''), 80)!r}")

    # ── 7. Thumbnail Generation ────────────────────────────────────────────────
    print("\n6. Thumbnail Generator (real fal.ai call — costs ~$0.12)")
    from agency.clients.fal_client import FalClient
    from agency.agents.thumbnail_generator import ThumbnailGenerator
    from agency.storage.supabase_storage import SupabaseStorage

    fal = FalClient.from_settings(settings)
    storage = SupabaseStorage(client=db.raw)
    tgen = ThumbnailGenerator(db=db, fal=fal, storage=storage, settings=settings)

    result = await tgen({**state, **result})  # type: ignore[typeddict-item]
    deliverable_ids = result.get("deliverable_ids", [])
    step("deliverables created", len(deliverable_ids) == 3, f"{len(deliverable_ids)} variants")

    deliverables = await db.list_deliverables(order_id)
    step("deliverables in DB", len(deliverables) == 3)

    await fal.aclose()
    await anthropic.aclose()
    _print_summary(order_id)


def _print_summary(order_id: UUID) -> None:
    print(f"\n{'─'*40}")
    print(f"  {OK} Smoke test passed")
    print(f"  Order ID: {order_id}")
    print(f"  Check Supabase dashboard → orders, agent_runs, agent_status")
    print(f"{'─'*40}\n")


if __name__ == "__main__":
    full_mode = "--full" in sys.argv
    asyncio.run(main(full=full_mode))
