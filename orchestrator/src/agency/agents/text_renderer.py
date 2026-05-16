"""Text Renderer agent.

Composites `state["text_overlay"]` onto every generated deliverable. Each
output is inserted as a new `deliverables` row with `parent_deliverable_id`
pointing back to the original — this preserves both the clean and
text-overlaid versions so the operator can A/B if needed.

If `text_overlay` is absent, the agent is a no-op (lifecycle still records
the run, with `log_summary="no overlay requested"`).
"""

from __future__ import annotations

from uuid import UUID

from agency.agents.base import Agent
from agency.config import Settings
from agency.db import Database
from agency.editing import TextOverlayStyle, render_text_overlay
from agency.lifecycle import AgentRun
from agency.state import WorkflowState
from agency.storage.supabase_storage import SupabaseStorage


class TextRenderer(Agent):
    """Adds styled text overlay to each variant produced by the generator."""

    agent_key = "text_renderer"

    def __init__(
        self,
        db: Database,
        storage: SupabaseStorage,
        settings: Settings,
    ) -> None:
        super().__init__(db)
        self._storage = storage
        self._bucket = settings.storage_bucket_deliverables

    async def execute(self, state: WorkflowState, run: AgentRun) -> WorkflowState:
        text = state.get("text_overlay")
        order_id = state["order_id"]

        if not text:
            run.log("no overlay requested")
            run.set_output(skipped=True)
            return {}  # type: ignore[typeddict-item]

        deliverables = await self.db.list_deliverables(order_id)
        if not deliverables:
            raise RuntimeError("text_renderer found no deliverables to overlay")

        run.set_input(text=text, num_inputs=len(deliverables))

        new_ids: list[str] = []
        for d in deliverables:
            # Skip deliverables that are themselves overlay outputs (have a parent).
            if d.get("parent_deliverable_id"):
                continue

            path = (d.get("metadata") or {}).get("storage_path")
            if not path:
                # Best-effort: skip rows we can't address.
                continue

            blob = await self._storage.download(bucket=self._bucket, path=path)
            composed = render_text_overlay(blob, text, style=TextOverlayStyle())

            new_path = f"{order_id}/text-{d['variant_index']}.jpg"
            stored = await self._storage.upload(
                bucket=self._bucket,
                path=new_path,
                data=composed,
                content_type="image/jpeg",
                upsert=True,
            )
            new_id = await self.db.create_deliverable(
                order_id=order_id,
                parent_deliverable_id=UUID(d["id"]),
                produced_by_agent_id=run.agent_id,
                produced_by_run_id=run.run_id,
                file_url=stored.signed_url,
                file_name=f"text-{d['variant_index']}.jpg",
                file_type="image/jpeg",
                file_size_bytes=len(composed),
                dimensions=d.get("dimensions"),
                variant_index=d["variant_index"],
                metadata={"storage_path": stored.path, "text_overlay": text},
            )
            new_ids.append(str(new_id))

        run.set_output(text=text, new_deliverable_ids=new_ids)
        run.log(f"rendered overlay on {len(new_ids)} variant(s)")
        return {"deliverable_ids": new_ids}  # type: ignore[typeddict-item]
