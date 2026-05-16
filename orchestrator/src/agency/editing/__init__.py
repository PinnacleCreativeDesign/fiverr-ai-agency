"""Image editing primitives (Pillow-based pure functions).

Each function takes bytes in, returns bytes out. No I/O, no Supabase, no fal.ai.
This keeps editing logic trivially testable and reusable across agents.
"""

from agency.editing.text_overlay import (
    OverlayPosition,
    TextOverlayStyle,
    inspect_image,
    render_text_overlay,
)

__all__ = [
    "OverlayPosition",
    "TextOverlayStyle",
    "inspect_image",
    "render_text_overlay",
]
