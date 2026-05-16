"""Shared base class for fal.ai-backed generation agents.

Subclasses provide:
  * `agent_key`         — class var matching the DB row
  * `image_size(state)` — fal preset to render at (may be state-dependent)
  * `file_prefix`       — naming prefix for the storage path / file_name

The base implements the full generate → download → upload → record loop
(uniform across every generation agent). Adding a new generator is one new
file with ~30 lines of body.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import ClassVar

from agency.agents.base import Agent
from agency.clients.fal_client import FalClient, GenerationResult, ImageSize
from agency.config import Settings
from agency.db import Database
from agency.lifecycle import AgentRun
from agency.state import WorkflowState
from agency.storage.supabase_storage import SupabaseStorage

_EXT_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class GenerationAgentBase(Agent):
    """Abstract base for fal.ai-backed generation agents."""

    num_variations: ClassVar[int] = 3
    file_prefix: ClassVar[str] = "image"

    def __init__(
        self,
        db: Database,
        fal: FalClient,
        storage: SupabaseStorage,
        settings: Settings,
    ) -> None:
        super().__init__(db)
        self._fal = fal
        self._storage = storage
        self._bucket = settings.storage_bucket_deliverables

    @abstractmethod
    def image_size(self, state: WorkflowState) -> ImageSize:
        """Pick the fal preset for this order. May read state to choose."""

    async def execute(self, state: WorkflowState, run: AgentRun) -> WorkflowState:
        prompt = state.get("refined_prompt")
        if not prompt:
            raise ValueError(
                f"{type(self).__name__} requires state['refined_prompt'] — "
                f"Prompt Engineering must run first."
            )
        order_id = state["order_id"]
        negative = state.get("negative_prompt")
        size = self.image_size(state)

        run.set_input(
            prompt=prompt,
            negative_prompt=negative,
            num_variations=self.num_variations,
            image_size=size,
        )

        generation: GenerationResult = await self._fal.generate(
            prompt=prompt,
            negative_prompt=negative,
            num_images=self.num_variations,
            image_size=size,
        )
        run.add_cost(generation.cost_usd)

        if not generation.images:
            raise RuntimeError("fal.ai returned zero images — likely safety filter triggered")

        deliverable_ids: list[str] = []
        for index, image in enumerate(generation.images):
            blob = await self._fal.download(image.url)
            ext = _EXT_BY_MIME.get(image.content_type, ".jpg")
            name = f"{self.file_prefix}-{index + 1}{ext}"
            storage_path = f"{order_id}/{name}"

            stored = await self._storage.upload(
                bucket=self._bucket,
                path=storage_path,
                data=blob,
                content_type=image.content_type,
                upsert=True,
            )
            deliverable_id = await self.db.create_deliverable(
                order_id=order_id,
                produced_by_agent_id=run.agent_id,
                produced_by_run_id=run.run_id,
                file_url=stored.signed_url,
                file_name=name,
                file_type=image.content_type,
                file_size_bytes=len(blob),
                dimensions={"width": image.width, "height": image.height, "dpi": 72},
                variant_index=index,
                metadata={
                    "storage_path": stored.path,
                    "signed_url_expires_in": stored.expires_in_seconds,
                    "fal_seed": generation.seed,
                    "fal_endpoint": self._fal.endpoint,
                    "image_size_preset": size,
                },
            )
            deliverable_ids.append(str(deliverable_id))

        run.set_output(
            deliverable_ids=deliverable_ids,
            cost_usd=generation.cost_usd,
            seed=generation.seed,
            image_size=size,
        )
        run.log(
            f"Generated {len(deliverable_ids)} {self.file_prefix} variant(s) "
            f"at {size} (${generation.cost_usd:.2f})"
        )
        return {"deliverable_ids": deliverable_ids}  # type: ignore[typeddict-item]
