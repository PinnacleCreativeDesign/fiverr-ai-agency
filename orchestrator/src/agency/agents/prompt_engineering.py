"""Prompt Engineering agent.

Converts the client brief into a precise image-generation prompt. Operates
per-service-type — each service has its own system prompt encoding the
domain-specific best practices the generation model needs.

Design notes:
  * System prompts are constants in this file, NOT pulled from the
    `prompt_templates` table. The table stays in the schema for future
    fine-tuning, but a code-as-config approach is faster to iterate on while
    we're still learning what prompts work in production.
  * Text overlays are extracted to state but NOT inlined into the generation
    prompt — Flux is unreliable at rendering exact text. The Text Renderer
    agent (later) adds clean overlays via Pillow.
"""

from __future__ import annotations

from textwrap import dedent
from typing import Literal

from agency.agents.base import Agent
from agency.clients.anthropic_client import AnthropicClient
from agency.db import Database
from agency.lifecycle import AgentRun
from agency.state import ServiceType, WorkflowState

ROUTE = Literal["generate", "halt"]

# ── Per-service system prompts ───────────────────────────────────────────────

_THUMBNAIL_PROMPT = dedent(
    """\
    You are an expert YouTube thumbnail prompt engineer for diffusion image
    models (Flux Pro 1.1). Convert the client brief into a single,
    model-ready generation prompt.

    Rules of thumb that perform on YouTube CTR:
      * Lead with subject and composition; layer style, lighting, mood.
      * Camera + lens vocabulary helps: "low-angle", "85mm", "shallow DOF".
      * Lighting cues: "rim-lit", "neon underglow", "dramatic key light".
      * High contrast + saturated colors > washed-out.
      * Tight crops on faces with intense expression.
      * 16:9 framing (1280x720).

    Do NOT instruct the model to render literal text. Surface any required
    title/caption text in the `text_overlay` field — a downstream agent
    composites it cleanly in post.

    Output EXACTLY this JSON shape:
    {
      "refined_prompt":  "<the full generation prompt, 1-3 sentences>",
      "negative_prompt": "<comma-separated things to avoid>",
      "text_overlay":    "<the title/caption text the client asked for, or null>",
      "rationale":       "<one sentence on the choices made>"
    }
    """
)

_SOCIAL_GRAPHIC_PROMPT = dedent(
    """\
    You are an expert social-media graphic prompt engineer. The deliverable is
    a single-image post for Instagram, Facebook, or X. Convert the client
    brief into a model-ready prompt.

    Key constraints:
      * Aspect ratio is platform-dependent — surface it in the prompt
        ("square 1:1" for IG feed, "vertical 4:5" for IG portrait).
      * Brand-safe by default — no copyrighted characters unless the client
        explicitly owns the IP.
      * Leave space for headline text (top-third or bottom-third).
      * Avoid: literal rendered text (handled by Text Renderer agent later).

    Output EXACTLY this JSON shape:
    {
      "refined_prompt":  "<full generation prompt>",
      "negative_prompt": "<comma-separated things to avoid>",
      "text_overlay":    "<headline text, or null>",
      "rationale":       "<one sentence>"
    }
    """
)

_HEADSHOT_PROMPT = dedent(
    """\
    You are an expert AI-headshot prompt engineer. The deliverable is a
    photorealistic professional headshot. Convert the client brief into a
    model-ready prompt.

    Quality cues that matter:
      * Specify clothing register (business / business-casual / casual).
      * Lighting: "softbox key light + fill", "natural window light".
      * Camera: "85mm portrait lens, f/1.8, shallow DOF".
      * Background: "neutral grey studio backdrop" unless the client specifies.
      * Skin: "natural skin texture, no airbrushing" (avoids the plastic look).

    No text overlay for headshots.

    Output EXACTLY this JSON shape:
    {
      "refined_prompt":  "<full generation prompt>",
      "negative_prompt": "<comma-separated things to avoid>",
      "text_overlay":    null,
      "rationale":       "<one sentence>"
    }
    """
)

_LOGO_PROMPT = dedent(
    """\
    You are an expert logo prompt engineer. The deliverable is a raster
    concept that the Logo Generator pipeline will later vectorize to SVG.

    Constraints:
      * Flat, simple shapes — avoid photographic detail and gradients.
      * High contrast on solid background (white or transparent).
      * Single subject; no scene composition.
      * No literal text — type lockup is added separately.
      * Generate AT THE LOGO LEVEL — describe the mark, not a scene.

    Output EXACTLY this JSON shape:
    {
      "refined_prompt":  "<full generation prompt>",
      "negative_prompt": "<comma-separated things to avoid>",
      "text_overlay":    "<brand name if mentioned, or null>",
      "rationale":       "<one sentence>"
    }
    """
)

_BUSINESS_DESIGN_PROMPT = dedent(
    """\
    You are an expert brand-identity concept prompt engineer. The deliverable
    is a mood-board-style image conveying brand direction (color, typography
    feel, visual texture).

    Output EXACTLY this JSON shape:
    {
      "refined_prompt":  "<full generation prompt>",
      "negative_prompt": "<comma-separated things to avoid>",
      "text_overlay":    null,
      "rationale":       "<one sentence>"
    }
    """
)

_BACKGROUND_REMOVAL_PROMPT = dedent(
    """\
    Background removal does NOT use a generation prompt — the Background
    Removal agent calls rembg directly on the client's input image. This
    prompt should not be reached at runtime; if it is, surface that as an
    error.

    Output EXACTLY this JSON shape:
    {
      "refined_prompt":  "ERROR: background_removal does not use generation",
      "negative_prompt": "",
      "text_overlay":    null,
      "rationale":       "Background removal is rule-based, not generative."
    }
    """
)

_SYSTEM_PROMPTS: dict[ServiceType, str] = {
    "thumbnail": _THUMBNAIL_PROMPT,
    "social_graphic": _SOCIAL_GRAPHIC_PROMPT,
    "headshot": _HEADSHOT_PROMPT,
    "logo": _LOGO_PROMPT,
    "business_design": _BUSINESS_DESIGN_PROMPT,
    "background_removal": _BACKGROUND_REMOVAL_PROMPT,
}


class PromptEngineering(Agent):
    """Converts the client brief into a precise generation prompt."""

    agent_key = "prompt_engineering"

    def __init__(self, db: Database, anthropic: AnthropicClient) -> None:
        super().__init__(db)
        self._anthropic = anthropic

    async def execute(self, state: WorkflowState, run: AgentRun) -> WorkflowState:
        service_type = state["service_type"]
        system_prompt = _SYSTEM_PROMPTS.get(service_type)
        if system_prompt is None:
            raise ValueError(f"No system prompt registered for service_type={service_type}")

        style = state.get("style_attributes")
        user_prompt = _build_user_prompt(state["brief"], service_type, style)

        run.set_input(
            service_type=service_type,
            brief=state["brief"],
            has_style_attributes=bool(style),
        )

        data, completion = await self._anthropic.complete_json(
            system=system_prompt,
            prompt=user_prompt,
            max_tokens=600,
            temperature=0.3,  # mild creativity, but consistent
        )
        run.add_cost(completion.cost_usd)

        refined_prompt = str(data.get("refined_prompt") or "").strip()
        if not refined_prompt:
            raise ValueError("Prompt Engineering returned an empty refined_prompt")

        negative_prompt = (data.get("negative_prompt") or "").strip() or None
        text_overlay = data.get("text_overlay") or None
        rationale = data.get("rationale") or None

        run.set_output(
            refined_prompt=refined_prompt,
            negative_prompt=negative_prompt,
            text_overlay=text_overlay,
            rationale=rationale,
        )
        run.log(f"Engineered {service_type} prompt ({len(refined_prompt)} chars)")

        partial: WorkflowState = {  # type: ignore[typeddict-item]
            "refined_prompt": refined_prompt,
        }
        if negative_prompt:
            partial["negative_prompt"] = negative_prompt
        if text_overlay:
            partial["text_overlay"] = text_overlay
        return partial


def _build_user_prompt(
    brief: str,
    service_type: ServiceType,
    style: dict | None,
) -> str:
    parts = [f"Service type: {service_type}", "", "Brief:", brief]
    if style:
        parts.append("")
        parts.append("Style reference (extracted from client images):")
        for key, value in style.items():
            parts.append(f"  - {key}: {value}")
    return "\n".join(parts)
