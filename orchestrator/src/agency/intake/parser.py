"""Intake Parser — converts an incoming `FiverrEmail` into an `orders` row.

Flow per email:
  1. Compute idempotency key from the email message-id.
  2. Short-circuit if an order with that key already exists.
  3. Enter the agent lifecycle (no order_id yet — system-agent path).
  4. Ask Claude to extract structured fields → validated as `ParsedOrder`.
  5. Insert the order row.
  6. Attach the new order_id to the run via `run.set_order_id(...)`.
  7. Lifecycle wrapper marks the run completed.

Errors propagate. The lifecycle wrapper records the error on the run row and
re-raises so the runner can decide whether to retry, log, or skip.
"""

from __future__ import annotations

from textwrap import dedent
from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError

from agency.clients.anthropic_client import AnthropicClient, CompletionResult
from agency.db import Database
from agency.intake.email_models import FiverrEmail, ParsedOrder
from agency.lifecycle import agent_lifecycle

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = dedent(
    """\
    You are the intake parser for an AI-driven creative service. Read a single
    Fiverr order notification email and extract a structured order record.

    Output EXACTLY this JSON shape, nothing else, no Markdown, no prose:
    {
      "service_type":   "thumbnail" | "social_graphic" | "headshot"
                       | "background_removal" | "logo" | "business_design",
      "brief":          "<the client's actual request, cleaned up>",
      "fiverr_order_id":"<order id if found in email, else null>",
      "client_username":"<buyer username if found, else null>",
      "deadline":       "<ISO-8601 timestamp if a deadline is stated, else null>",
      "reference_image_urls": ["<url>", ...],   // empty array if none
      "confidence":     <float 0.0-1.0: how confident you are about service_type>,
      "notes":          "<one short sentence flagging anything weird, or null>"
    }

    Rules:
      * Pick the single best matching service_type. Never invent new types.
      * `brief` is the client's verbatim ask, lightly cleaned (drop email
        boilerplate, signature blocks, Fiverr footers). Do NOT paraphrase.
      * If the email is clearly not a real order (spam, account notification,
        marketing), set confidence to 0.0 and notes to "not an order".
    """
)


class IntakeParser:
    """LLM-driven extraction + idempotent order insertion.

    Construct once at process startup and call `process_email(email)` per
    incoming `FiverrEmail`. Concurrent calls on the same parser instance are
    safe — there is no per-instance mutable state.
    """

    agent_key = "intake_parser"

    def __init__(self, db: Database, anthropic: AnthropicClient) -> None:
        self._db = db
        self._anthropic = anthropic

    async def process_email(self, email: FiverrEmail) -> UUID:
        """Parse one email and return the resulting order_id.

        If an order with the same idempotency key already exists, returns its
        id without re-parsing. This is the only correct behavior for an at-
        least-once delivery channel like Gmail polling.
        """
        idempotency_key = self._idempotency_key(email)

        existing = await self._db.find_order_by_idempotency_key(idempotency_key)
        if existing is not None:
            logger.info(
                "intake.duplicate_skipped",
                message_id=email.message_id,
                existing_order_id=existing["id"],
            )
            return UUID(existing["id"])

        async with agent_lifecycle(self._db, self.agent_key, order_id=None) as run:
            run.set_input(
                message_id=email.message_id,
                subject=email.subject,
                sender=email.sender,
                body_length=len(email.body_plain),
                attachment_count=len(email.attachment_urls),
            )

            parsed, completion = await self._extract(email)
            run.add_cost(completion.cost_usd)

            order_id = await self._db.create_order(
                idempotency_key=idempotency_key,
                source="fiverr",
                fiverr_order_id=parsed.fiverr_order_id,
                client_username=parsed.client_username,
                client_email=email.sender,
                service_type=parsed.service_type,
                brief=parsed.brief,
                reference_images=parsed.reference_image_urls or email.attachment_urls,
                deadline=parsed.deadline.isoformat() if parsed.deadline else None,
                raw_payload=email.model_dump(mode="json"),
                metadata={"intake_confidence": parsed.confidence, "intake_notes": parsed.notes},
            )
            run.set_order_id(order_id)
            run.set_output(
                order_id=str(order_id),
                service_type=parsed.service_type,
                fiverr_order_id=parsed.fiverr_order_id,
                confidence=parsed.confidence,
            )
            run.log(
                f"Parsed {parsed.service_type} order"
                + (f" from @{parsed.client_username}" if parsed.client_username else "")
                + f" (confidence={parsed.confidence:.2f})"
            )

        return order_id

    async def _extract(self, email: FiverrEmail) -> tuple[ParsedOrder, CompletionResult]:
        """Run the Claude extraction and validate the JSON against `ParsedOrder`."""
        user_prompt = _build_user_prompt(email)
        data, completion = await self._anthropic.complete_json(
            system=SYSTEM_PROMPT,
            prompt=user_prompt,
            max_tokens=1024,
            temperature=0.0,
        )
        try:
            parsed = ParsedOrder.model_validate(data)
        except ValidationError as exc:
            raise IntakeExtractionError(
                f"Claude returned invalid intake JSON: {exc.errors()[:3]}"
            ) from exc
        return parsed, completion

    @staticmethod
    def _idempotency_key(email: FiverrEmail) -> str:
        return f"gmail:{email.message_id}"


def _build_user_prompt(email: FiverrEmail) -> str:
    """Compose the user-message payload Claude sees. Plain-text body only."""
    parts: list[Any] = [
        f"Subject: {email.subject}",
        f"From: {email.sender}",
        f"Received: {email.received_at.isoformat()}",
    ]
    if email.attachment_urls:
        parts.append("Attachments: " + ", ".join(email.attachment_urls))
    parts.append("")
    parts.append("--- BODY ---")
    parts.append(email.body_plain.strip())
    return "\n".join(parts)


class IntakeExtractionError(RuntimeError):
    """Raised when Claude's extraction output cannot be parsed as a `ParsedOrder`."""
