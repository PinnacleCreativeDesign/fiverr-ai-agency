"""Business Design Concept Generator — brand mood boards at landscape_16_9.

Produces 3 mood-board-style concept variations for brand identity exploration.
Wider format (1280x720) suits the mood board / presentation layout aesthetic.
"""

from __future__ import annotations

from agency.agents._generation_base import GenerationAgentBase
from agency.clients.fal_client import ImageSize
from agency.state import WorkflowState


class BusinessDesignGenerator(GenerationAgentBase):
    """Generate 3 brand identity concept variations."""

    agent_key = "business_design"
    file_prefix = "brand-concept"

    def image_size(self, state: WorkflowState) -> ImageSize:
        return "landscape_16_9"
