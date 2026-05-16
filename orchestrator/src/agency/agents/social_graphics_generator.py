"""Social Graphics Generator — multi-platform social media graphics.

Picks the fal `image_size` preset by inferring the platform from the refined
prompt and the original brief:

  * Stories / reels (9:16)              → `portrait_16_9`  (720x1280)
  * Twitter / banners (16:9)            → `landscape_16_9` (1280x720)
  * Default: Instagram feed (1:1)       → `square_hd`       (1024x1024)

The Prompt Engineering social_graphic system prompt requires Claude to surface
the aspect ratio in the prompt text, which is the signal we read here. If
nothing matches we default to square — by far the most common Fiverr ask.
"""

from __future__ import annotations

from agency.agents._generation_base import GenerationAgentBase
from agency.clients.fal_client import ImageSize
from agency.state import WorkflowState

# Keyword hints scanned against `refined_prompt + brief` (case-insensitive).
_PORTRAIT_HINTS = (
    "9:16", "story", "stories", "reel", "reels", "tiktok",
    "vertical", "portrait", "1080x1920", "1920", "ig story",
)
_LANDSCAPE_HINTS = (
    "16:9", "twitter", "x post", "header", "banner",
    "cover photo", "youtube", "landscape", "1200x630", "facebook cover",
)


class SocialGraphicsGenerator(GenerationAgentBase):
    """Generate 3 social media graphic variations at platform-appropriate dims."""

    agent_key = "social_graphics_gen"
    file_prefix = "social"

    def image_size(self, state: WorkflowState) -> ImageSize:
        return _infer_image_size(state)


def _infer_image_size(state: WorkflowState) -> ImageSize:
    """Heuristic platform → image_size mapping. See module docstring."""
    text = (
        (state.get("refined_prompt") or "")
        + " "
        + (state.get("brief") or "")
    ).lower()

    if any(hint in text for hint in _PORTRAIT_HINTS):
        return "portrait_16_9"
    if any(hint in text for hint in _LANDSCAPE_HINTS):
        return "landscape_16_9"
    return "square_hd"
