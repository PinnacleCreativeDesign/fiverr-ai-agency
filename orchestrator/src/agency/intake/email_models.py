"""Typed models for the intake pipeline.

`FiverrEmail` is the canonical input shape — whatever produces it (Gmail
polling, n8n webhook, manual upload) must populate exactly these fields.
`ParsedOrder` is the canonical output of the Claude extraction step and is
validated before the order is inserted.

Keeping these models in one place means the LLM prompt, the database schema,
and the test fixtures all reference a single source of truth.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Mirror of the `service_type` enum in the database. Keep in sync with the
# schema migration and `agency.state.ServiceType`.
ServiceType = Literal[
    "thumbnail",
    "social_graphic",
    "headshot",
    "background_removal",
    "logo",
    "business_design",
]


class FiverrEmail(BaseModel):
    """A normalized incoming order email, regardless of upstream source.

    `message_id` is the idempotency anchor. For Gmail this is the RFC-2822
    `Message-ID` header (stable across re-fetches of the same email).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str = Field(..., min_length=1)
    received_at: datetime
    subject: str
    sender: str
    body_plain: str
    body_html: str | None = None
    attachment_urls: list[str] = Field(default_factory=list)


class ParsedOrder(BaseModel):
    """Structured output of the LLM intake extraction. Validated before insert."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    service_type: ServiceType
    brief: str = Field(..., min_length=10)
    fiverr_order_id: str | None = None
    client_username: str | None = None
    deadline: datetime | None = None
    reference_image_urls: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: str | None = None

    @field_validator("brief")
    @classmethod
    def _brief_is_substantive(cls, value: str) -> str:
        """Reject briefs that are obviously not a real request."""
        if len(value.strip().split()) < 3:
            raise ValueError("brief must contain at least 3 words")
        return value
