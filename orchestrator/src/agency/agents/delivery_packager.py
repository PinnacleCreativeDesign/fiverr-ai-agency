"""Delivery Packager agent.

Selects the QC-passed deliverables, builds a ZIP archive, uploads it to the
delivery-packages bucket, drafts a delivery message, and inserts a
`delivery_packages` row with `status='pending_approval'` for the operator
to review and send.

Message drafting is template-based at this milestone — keeps cost at zero
and the output is consistent enough that the operator can edit if needed.
A future Upsell agent will append a service-specific suggestion.
"""

from __future__ import annotations

import io
import zipfile
from textwrap import dedent
from typing import Any
from uuid import UUID

from agency.agents.base import Agent
from agency.config import Settings
from agency.db import Database
from agency.lifecycle import AgentRun
from agency.state import ServiceType, WorkflowState
from agency.storage.supabase_storage import SupabaseStorage

_SERVICE_LABELS: dict[ServiceType, str] = {
    "thumbnail": "YouTube thumbnail",
    "social_graphic": "social media graphic",
    "headshot": "AI headshot",
    "logo": "logo",
    "business_design": "brand identity concept",
    "background_removal": "background-removed image",
}


class DeliveryPackager(Agent):
    """Bundle QC-passed deliverables into a single ZIP + drafted message."""

    agent_key = "delivery_packager"

    def __init__(
        self,
        db: Database,
        storage: SupabaseStorage,
        settings: Settings,
    ) -> None:
        super().__init__(db)
        self._storage = storage
        self._deliverables_bucket = settings.storage_bucket_deliverables
        self._packages_bucket = settings.storage_bucket_packages
        self._visual_qc_threshold = settings.visual_qc_threshold

    async def execute(self, state: WorkflowState, run: AgentRun) -> WorkflowState:
        order_id = state["order_id"]
        service_type = state["service_type"]

        all_deliverables = await self.db.list_deliverables(order_id)
        # Prefer text-overlay outputs (have parent) when present; otherwise originals.
        with_text = [d for d in all_deliverables if d.get("parent_deliverable_id")]
        candidates = with_text or [d for d in all_deliverables if not d.get("parent_deliverable_id")]

        # Pass filter: must have passed technical QC AND (no visual_qc score OR
        # score above threshold). `None` quality_score is treated as pass so
        # the pipeline still works if Visual QC is disabled or skipped.
        passing = [
            d for d in candidates
            if d.get("technical_qc_passed")
            and (
                d.get("quality_score") is None
                or float(d.get("quality_score") or 0.0) >= self._visual_qc_threshold
            )
        ]

        if not passing:
            raise RuntimeError(
                f"delivery_packager: no QC-passed deliverables for order {order_id}"
            )

        run.set_input(
            service_type=service_type,
            total_deliverables=len(all_deliverables),
            packaging=len(passing),
        )

        # Mark the chosen variants approved.
        for d in passing:
            await self.db.update_deliverable_qc(UUID(d["id"]), is_approved=True)

        zip_bytes = await self._build_zip(passing)
        zip_path = f"{order_id}/delivery.zip"
        stored = await self._storage.upload(
            bucket=self._packages_bucket,
            path=zip_path,
            data=zip_bytes,
            content_type="application/zip",
            upsert=True,
        )

        message = _draft_message(service_type=service_type, variant_count=len(passing))
        package_id = await self.db.create_delivery_package(
            order_id=order_id,
            delivery_message=message,
            zip_url=stored.signed_url,
        )

        await self.db.update_order_status(order_id, status="ready_for_delivery")

        run.set_output(
            package_id=str(package_id),
            zip_url=stored.signed_url,
            variants_packaged=len(passing),
        )
        run.log(f"packaged {len(passing)} variant(s) — awaiting operator approval")

        return {  # type: ignore[typeddict-item]
            "package_id": package_id,
            "delivery_message": message,
        }

    async def _build_zip(self, deliverables: list[dict[str, Any]]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for d in deliverables:
                path = (d.get("metadata") or {}).get("storage_path")
                if not path:
                    continue
                blob = await self._storage.download(
                    bucket=self._deliverables_bucket, path=path
                )
                zf.writestr(d["file_name"], blob)
        return buf.getvalue()


# ── Pure helpers ────────────────────────────────────────────────────────────


def _draft_message(*, service_type: ServiceType, variant_count: int) -> str:
    """Operator-friendly delivery message. They can edit before clicking deliver."""
    label = _SERVICE_LABELS.get(service_type, service_type)
    return dedent(
        f"""\
        Hey! Your {label} order is ready — I've included {variant_count} variation{'s' if variant_count != 1 else ''} in the ZIP.

        Pick your favorite and let me know if you'd like any tweaks. You get up to 2 free revisions, so don't be shy.

        Thanks for choosing me — really enjoyed this one. If you're happy with the result, a 5-star review would mean a lot.

        Cheers!
        """
    ).strip()
