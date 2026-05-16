"""Headshot Generator — professional AI headshots at portrait_4_3 (768x1024).

Photorealistic close-crop headshot format. Client typically wants 3 variations
with different expressions/lighting to choose from.
"""

from __future__ import annotations

from agency.agents._generation_base import GenerationAgentBase
from agency.clients.fal_client import ImageSize
from agency.state import WorkflowState


class HeadshotGenerator(GenerationAgentBase):
    """Generate 3 professional headshot variations."""

    agent_key = "headshot_gen"
    file_prefix = "headshot"

    def image_size(self, state: WorkflowState) -> ImageSize:
        # portrait_4_3 (768x1024) — standard headshot aspect ratio.
        return "portrait_4_3"
