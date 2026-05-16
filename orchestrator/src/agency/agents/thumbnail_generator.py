"""Thumbnail Generator — YouTube thumbnails at 1280x720 via Flux Pro 1.1.

Subclasses `GenerationAgentBase`; the loop (generate → download → upload →
record) lives there. This file only declares the agent identity and the
output dimensions.
"""

from __future__ import annotations

from agency.agents._generation_base import GenerationAgentBase
from agency.clients.fal_client import ImageSize
from agency.state import WorkflowState


class ThumbnailGenerator(GenerationAgentBase):
    """Generate 3 thumbnail variations at 1280x720."""

    agent_key = "thumbnail_gen"
    file_prefix = "thumbnail"

    def image_size(self, state: WorkflowState) -> ImageSize:
        # YouTube thumbnail spec is fixed 1280x720 → landscape_16_9 preset.
        return "landscape_16_9"
