"""LangGraph state definition.

`WorkflowState` is the typed dict that flows through every node in the agent
graph. Fields are populated incrementally as the order moves through the
pipeline. `NotRequired` marks fields that are populated by downstream nodes.

Convention: nodes are pure with respect to state — they read what they need
and return a partial dict that LangGraph merges into the running state.
"""

from __future__ import annotations

from typing import Literal, NotRequired, TypedDict
from uuid import UUID

ServiceType = Literal[
    "thumbnail",
    "social_graphic",
    "headshot",
    "background_removal",
    "logo",
    "business_design",
]


class StyleAttributes(TypedDict, total=False):
    """Output of the Style Reference Analyzer."""

    palette: list[str]            # hex codes
    mood: list[str]               # e.g. ["minimalist", "warm"]
    composition: str | None
    typography: str | None
    notes: str | None


class WorkflowState(TypedDict):
    """State that flows through the LangGraph state machine."""

    # ── Set on intake (always present) ──────────────────────────────────
    order_id: UUID
    service_type: ServiceType
    brief: str
    reference_image_urls: list[str]

    # ── Set after Brief Clarification ───────────────────────────────────
    confidence_score: NotRequired[float]
    clarification_needed: NotRequired[bool]
    clarification_request_id: NotRequired[UUID]

    # ── Set after Prompt Engineering ────────────────────────────────────
    refined_prompt: NotRequired[str]
    template_id: NotRequired[UUID]
    negative_prompt: NotRequired[str]
    # Title / caption text the client asked for. Not inlined into the
    # generation prompt (Flux is unreliable at text) — the Text Renderer
    # agent composites it cleanly in post-processing.
    text_overlay: NotRequired[str]

    # ── Set after Style Reference Analyzer ──────────────────────────────
    style_attributes: NotRequired[StyleAttributes]

    # ── Set after Generation ────────────────────────────────────────────
    deliverable_ids: NotRequired[list[UUID]]

    # ── Set after Editing ───────────────────────────────────────────────
    edited_deliverable_ids: NotRequired[list[UUID]]

    # ── Set after QC ────────────────────────────────────────────────────
    qc_passed: NotRequired[bool]
    qc_failure_reason: NotRequired[str]
    retry_count: NotRequired[int]

    # ── Set after Delivery Packager / Upsell ────────────────────────────
    package_id: NotRequired[UUID]
    delivery_message: NotRequired[str]
    upsell_suggestion: NotRequired[str]

    # ── Cross-cutting ───────────────────────────────────────────────────
    total_cost_usd: NotRequired[float]
    error_message: NotRequired[str]
