"""Visual QC agent — Claude Vision review for anatomical and compositional defects.

Runs after Technical QC. Only inspects deliverables that already passed the
technical checks (no point spending vision tokens on a corrupted file). Scores
each variant 0.0-1.0 and persists to `deliverables.quality_score`. The
Delivery Packager picks variants where `quality_score >= visual_qc_threshold`.

Cost: ~$0.004 per image at 1280x720 (image tokens roll into input_tokens at
$3/MTok). 3-variant order ≈ $0.012.

Behavior on zero passing variants: raises — operator triages in the dashboard.
"""

from __future__ import annotations

from textwrap import dedent
from typing import Any
from uuid import UUID

from agency.agents.base import Agent
from agency.clients.anthropic_client import AnthropicClient
from agency.config import Settings
from agency.db import Database
from agency.lifecycle import AgentRun
from agency.state import WorkflowState
from agency.storage.supabase_storage import SupabaseStorage

SYSTEM_PROMPT = dedent(
    """\
    You are a quality-control reviewer for AI-generated creative assets bound
    for paying clients on Fiverr. Score the attached image and identify
    defects that would cause a refund or bad review.

    Output EXACTLY this JSON shape, nothing else:
    {
      "quality_score": <float in [0.0, 1.0]>,
      "issues":        ["<specific issue>", ...],
      "publishable":   <true | false>,
      "rationale":     "<one sentence>"
    }

    Score rubric:
      * 0.90 - 1.00: Publishable as-is. No anatomical, compositional, or
        rendering defects that a typical client would notice.
      * 0.70 - 0.89: Minor issues but defensible. (Slight artifacts, mild
        framing awkwardness.)
      * 0.40 - 0.69: Noticeable defects (e.g. distorted hand, asymmetric
        face). Refund risk.
      * 0.00 - 0.39: Egregious — extra fingers, malformed faces, illegible
        composition, broken anatomy. Do NOT ship.

    Specific failure modes to look for:
      * Hands: count fingers, check joint anatomy, look for fusing
      * Faces: pupil/iris asymmetry, malformed teeth, ear placement
      * Text: garbled lettering (only matters if it was supposed to render text)
      * Composition: subject cut off, awkward crops, dead negative space
      * Artifacts: noise grids, JPEG-style blocking, color banding

    Be honest. Bad scores are the whole point of running this check.
    """
)


class VisualQC(Agent):
    """Vision-model review for each technically-passing deliverable."""

    agent_key = "visual_qc"

    def __init__(
        self,
        db: Database,
        anthropic: AnthropicClient,
        storage: SupabaseStorage,
        settings: Settings,
    ) -> None:
        super().__init__(db)
        self._anthropic = anthropic
        self._storage = storage
        self._bucket = settings.storage_bucket_deliverables
        self._threshold = settings.visual_qc_threshold

    async def execute(self, state: WorkflowState, run: AgentRun) -> WorkflowState:
        order_id = state["order_id"]
        deliverables = await self.db.list_deliverables(order_id)
        # Skip ones that already failed Technical QC — don't waste vision tokens.
        candidates = [d for d in deliverables if d.get("technical_qc_passed")]
        if not candidates:
            raise RuntimeError("visual_qc found no technically-passing deliverables")

        run.set_input(
            num_candidates=len(candidates),
            threshold=self._threshold,
            brief=state["brief"],
        )

        per_variant: list[dict[str, Any]] = []
        pass_count = 0
        for d in candidates:
            path = (d.get("metadata") or {}).get("storage_path")
            if not path:
                per_variant.append(
                    {"deliverable_id": d["id"], "skipped": "no storage_path"}
                )
                continue

            blob = await self._storage.download(bucket=self._bucket, path=path)
            review = await self._review(image=blob, brief=state["brief"], run=run)

            await self.db.update_deliverable_qc(
                UUID(d["id"]),
                quality_score=review["quality_score"],
            )
            per_variant.append(
                {
                    "deliverable_id": d["id"],
                    "quality_score": review["quality_score"],
                    "publishable": review["publishable"],
                    "issues": review.get("issues", []),
                }
            )
            if review["quality_score"] >= self._threshold:
                pass_count += 1

        run.set_output(checked=len(candidates), passing=pass_count, results=per_variant)
        run.log(
            f"{pass_count}/{len(candidates)} variants scored "
            f">= {self._threshold:.2f}"
        )

        if pass_count == 0:
            raise RuntimeError(
                "visual_qc: no variants reached threshold — manual review required"
            )

        return {"qc_passed": True}  # type: ignore[typeddict-item]

    async def _review(
        self, *, image: bytes, brief: str, run: AgentRun
    ) -> dict[str, Any]:
        prompt = f"Client brief (for context, not strict comparison):\n{brief}"
        data, completion = await self._anthropic.complete_json_with_image(
            system=SYSTEM_PROMPT,
            text_prompt=prompt,
            image_bytes=image,
            image_media_type="image/jpeg",
            max_tokens=400,
            temperature=0.0,
        )
        run.add_cost(completion.cost_usd)

        # Clamp the score and coerce types defensively — Claude can drift.
        score = float(data.get("quality_score") or 0.0)
        score = max(0.0, min(1.0, score))
        data["quality_score"] = score
        data["publishable"] = bool(data.get("publishable", score >= self._threshold))
        return data
