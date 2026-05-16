"""Text overlay rendering via Pillow.

`render_text_overlay` composites styled text onto an image. Pure function:
takes image bytes + text, returns image bytes. Uses Pillow's built-in
TrueType font (added in Pillow 10) so the package doesn't need to bundle
font files.

Design notes:
  * Stroke width is scaled to font size — readable at any resolution.
  * Font size is proportional to image height — looks consistent across
    1280x720, 1024x1024, etc.
  * Output format mirrors input where possible; falls back to JPEG q=92.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

OverlayPosition = Literal["top", "center", "bottom"]


@dataclass(frozen=True, slots=True)
class TextOverlayStyle:
    """Visual style for the text composite."""

    position: OverlayPosition = "bottom"
    # Font height as a fraction of image height (e.g. 0.12 = 12% of height).
    font_size_ratio: float = 0.12
    # Stroke width as a fraction of font size.
    stroke_ratio: float = 0.06
    # Margin from edges as a fraction of image height.
    margin_ratio: float = 0.06
    fill: tuple[int, int, int, int] = (255, 255, 255, 255)
    stroke: tuple[int, int, int, int] = (0, 0, 0, 255)


@dataclass(frozen=True, slots=True)
class ImageInfo:
    """Result of `inspect_image` — used by Technical QC."""

    width: int
    height: int
    format: str
    mode: str
    size_bytes: int


def inspect_image(data: bytes) -> ImageInfo:
    """Read header-only metadata. Cheaper than full decode."""
    with Image.open(io.BytesIO(data)) as img:
        return ImageInfo(
            width=img.width,
            height=img.height,
            format=(img.format or "UNKNOWN").upper(),
            mode=img.mode,
            size_bytes=len(data),
        )


def render_text_overlay(
    data: bytes,
    text: str,
    *,
    style: TextOverlayStyle | None = None,
) -> bytes:
    """Composite `text` onto the image. Returns JPEG bytes."""
    style = style or TextOverlayStyle()
    src = Image.open(io.BytesIO(data)).convert("RGBA")

    font_size = max(16, int(src.height * style.font_size_ratio))
    font = _load_font(font_size)
    stroke_width = max(1, int(font_size * style.stroke_ratio))

    # Measure with a transient draw context so we know placement.
    measure = ImageDraw.Draw(src)
    bbox = measure.textbbox(
        (0, 0), text, font=font, stroke_width=stroke_width
    )
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    margin = int(src.height * style.margin_ratio)
    x = (src.width - text_w) // 2 - bbox[0]
    y = _y_for_position(src.height, text_h, margin, style.position, bbox[1])

    overlay = Image.new("RGBA", src.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.text(
        (x, y),
        text,
        font=font,
        fill=style.fill,
        stroke_width=stroke_width,
        stroke_fill=style.stroke,
    )

    composite = Image.alpha_composite(src, overlay).convert("RGB")
    buf = io.BytesIO()
    composite.save(buf, format="JPEG", quality=92, optimize=True)
    return buf.getvalue()


# ── helpers ────────────────────────────────────────────────────────────────


def _y_for_position(
    img_h: int, text_h: int, margin: int, position: OverlayPosition, bbox_top: int
) -> int:
    if position == "top":
        return margin - bbox_top
    if position == "center":
        return (img_h - text_h) // 2 - bbox_top
    return img_h - text_h - margin - bbox_top  # bottom


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Use Pillow's built-in TrueType (Aileron, bundled since Pillow 10)."""
    return ImageFont.load_default(size=size)
