"""Intake — converts incoming order notifications into `orders` rows.

The Intake Parser is a "system" agent: it runs *before* an order exists in
the database, so it follows the same lifecycle pattern as graph agents but
starts with `order_id = None` and attaches the order_id via
`run.set_order_id(...)` once the row is inserted.

Modules:
  * `email_models` — typed `FiverrEmail` input and `ParsedOrder` Claude output
  * `parser`       — `IntakeParser` class (LLM-driven extraction + insert)
  * `gmail_client` — `GmailClient` wrapper around the official Gmail SDK
  * `runner`       — `IntakeRunner` (single-cycle + continuous-loop driver)
"""

from agency.intake.email_models import FiverrEmail, ParsedOrder
from agency.intake.gmail_client import GmailClient, message_to_email
from agency.intake.parser import IntakeExtractionError, IntakeParser
from agency.intake.runner import IntakeRunner, IntakeRunResult

__all__ = [
    "FiverrEmail",
    "GmailClient",
    "IntakeExtractionError",
    "IntakeParser",
    "IntakeRunResult",
    "IntakeRunner",
    "ParsedOrder",
    "message_to_email",
]
