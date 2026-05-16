"""Brief Clarification agent.

The first decision point in the pipeline. Scores the client brief's clarity
on [0.0, 1.0]. If the score is below the configured threshold, the agent
generates a clarification message draft and creates a `clarification_requests`
row for the operator to send. Otherwise the order advances to `processing`.

Routing in the LangGraph state machine reads `state["clarification_needed"]`.
"""

from __future__ import annotations

from textwrap import dedent

from agency.agents.base import Agent
from agency.clients.anthropic_client import AnthropicClient
from agency.config import Settings
from agency.db import Database
from agency.lifecycle import AgentRun
from agency.state import WorkflowState

SYSTEM_PROMPT = dedent(
    """\
    You are an expert creative director evaluating a client brief for an
    AI-driven creative service (Fiverr). Score the brief's clarity and identify
    any ambiguities that would block high-quality first-pass generation.

    Output EXACTLY this JSON shape, no other text, no prose, no Markdown:
    {
      "confidence_score": <float in [0.0, 1.0]>,
      "rationale": "<one sentence justifying the score>",
      "needs_clarification": <true | false>,
      "questions": ["<question 1>", "<question 2>", ...]
    }

    Rubric:
      * 0.85 - 1.00: Specifies subject, style/mood, intent, dimensions or
        platform, and any text overlays. Proceed without questions.
      * 0.65 - 0.84: Minor ambiguities but inferable from context. Proceed,
        no clarification needed.
      * 0.00 - 0.64: Critical info missing (subject, target use, key
        constraints). MUST request clarification.

    The `questions` array MUST be empty when `needs_clarification` is false,
    and MUST contain 1-4 concrete, answerable questions when true.
    """
)


class BriefClarification(Agent):
    """Scores brief clarity and drafts clarifications when needed."""

    agent_key = "brief_clarification"

    def __init__(
        self,
        db: Database,
        anthropic: AnthropicClient,
        settings: Settings,
    ) -> None:
        super().__init__(db)
        self._anthropic = anthropic
        self._threshold = settings.brief_confidence_threshold

    async def execute(self, state: WorkflowState, run: AgentRun) -> WorkflowState:
        run.set_input(
            service_type=state["service_type"],
            brief=state["brief"],
            has_references=bool(state.get("reference_image_urls")),
            threshold=self._threshold,
        )

        user_prompt = (
            f"Service type: {state['service_type']}\n"
            f"Reference images attached: {bool(state.get('reference_image_urls'))}\n\n"
            f"Brief:\n{state['brief']}"
        )

        result, completion = await self._anthropic.complete_json(
            system=SYSTEM_PROMPT,
            prompt=user_prompt,
            max_tokens=512,
            temperature=0.0,
        )
        run.add_cost(completion.cost_usd)

        score = float(result["confidence_score"])
        questions = list(result.get("questions", []))
        # Trust the score, not the model's `needs_clarification` self-report —
        # the threshold is operator-configurable and is the source of truth.
        needs_clarification = score < self._threshold

        run.set_output(
            confidence_score=score,
            rationale=result.get("rationale"),
            questions=questions,
            decision="clarify" if needs_clarification else "proceed",
        )

        await self.db.update_order_status(
            order_id=state["order_id"],
            status="clarification_needed" if needs_clarification else "processing",
            confidence_score=score,
        )

        partial: WorkflowState = {  # type: ignore[typeddict-item]
            "confidence_score": score,
            "clarification_needed": needs_clarification,
        }

        if needs_clarification:
            if not questions:
                # Model said high confidence but score is low — defensive
                # fallback so the operator still has something to send.
                questions = ["Could you provide more detail about what you're looking for?"]
            draft = _draft_clarification_message(questions)
            request_id = await self.db.create_clarification_request(
                order_id=state["order_id"],
                questions=questions,
                draft_message=draft,
            )
            partial["clarification_request_id"] = request_id
            run.log(
                f"Brief unclear (score={score:.2f} < {self._threshold:.2f}); "
                f"drafted {len(questions)} questions"
            )
        else:
            run.log(f"Brief clear (score={score:.2f}); routing to prompt engineering")

        return partial


def _draft_clarification_message(questions: list[str]) -> str:
    """Compose a friendly, professional clarification message for the operator."""
    lines = [
        "Hi! Thanks so much for your order — really excited to work on this.",
        "",
        "Before I dive in, I just want to make sure I nail it on the first pass. "
        "A few quick questions:",
        "",
    ]
    lines.extend(f"  {i}. {question}" for i, question in enumerate(questions, start=1))
    lines.extend(
        [
            "",
            "As soon as you reply I'll get to work. Aiming to have your first "
            "drafts back within the delivery window.",
            "",
            "Thanks!",
        ]
    )
    return "\n".join(lines)
