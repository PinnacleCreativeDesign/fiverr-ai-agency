"""Typed environment configuration via pydantic-settings.

All env vars are read once at startup and cached. See `.env.example` at the
repository root for the canonical list of variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),  # works from orchestrator/ or repo root
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Supabase ────────────────────────────────────────────────────────────
    supabase_url: str = Field(..., description="Project URL, e.g. https://abc.supabase.co")
    supabase_service_role_key: SecretStr = Field(..., description="Backend writes use this key")
    supabase_anon_key: SecretStr | None = Field(default=None)
    supabase_db_url: SecretStr | None = Field(default=None)

    # ── Anthropic (orchestration, prompt engineering, vision QC) ───────────
    anthropic_api_key: SecretStr = Field(..., description="Required for all Claude calls")
    anthropic_model: str = Field(default="claude-sonnet-4-6")

    # ── OpenAI (DALL-E 3, optional GPT-4o vision fallback) ─────────────────
    openai_api_key: SecretStr | None = Field(default=None)
    openai_model: str = Field(default="gpt-4o")

    # ── fal.ai (Flux 1.1 Pro generation) ───────────────────────────────────
    fal_key: SecretStr | None = Field(default=None)
    fal_flux_pro_endpoint: str = Field(default="fal-ai/flux-pro/v1.1")

    # ── Replicate (SDXL on-demand, vectorization, optional Real-ESRGAN) ────
    replicate_api_token: SecretStr | None = Field(default=None)

    # ── ComfyUI (local or RunPod-hosted SDXL workflows) ────────────────────
    comfyui_url: str = Field(default="http://localhost:8188")

    # ── Storage buckets (must exist in Supabase Storage before runtime) ────
    storage_bucket_references: str = Field(default="client-references")
    storage_bucket_deliverables: str = Field(default="deliverables")
    storage_bucket_packages: str = Field(default="delivery-packages")

    # ── Gmail intake ───────────────────────────────────────────────────────
    # File paths for the OAuth client secret and the issued refresh token.
    # See docs/intake-setup.md for how to obtain `credentials.json` and bootstrap
    # `token.json` via `agency auth-gmail`.
    gmail_credentials_file: str = Field(default="credentials.json")
    gmail_token_file: str = Field(default="token.json")
    # Label names as they appear in Gmail. Nested labels use `/` as separator.
    gmail_label_pending: str = Field(default="Fiverr/Orders")
    gmail_label_processed: str = Field(default="FiverrAgency/Processed")
    gmail_label_failed: str = Field(default="FiverrAgency/Failed")
    # Polling cadence and batch size for `agency intake-loop`.
    intake_poll_interval_seconds: float = Field(default=60.0, gt=0.0)
    intake_max_per_cycle: int = Field(default=10, ge=1, le=100)

    # ── Operations ─────────────────────────────────────────────────────────
    log_level: str = Field(default="info")
    brief_confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    brand_consistency_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    visual_qc_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    max_generation_retries: int = Field(default=2, ge=0, le=5)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor. Call once per process."""
    return Settings()  # type: ignore[call-arg]
