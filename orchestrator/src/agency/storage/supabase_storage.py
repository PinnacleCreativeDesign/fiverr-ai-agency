"""Supabase Storage wrapper.

Uploads bytes to a private bucket and returns signed URLs. The bucket itself
must already exist — buckets are managed out-of-band (operator creates them
via the Supabase dashboard; see repo README).

Default TTL for signed URLs is 7 days, configurable per call. For long-lived
deliverable access the dashboard should regenerate signed URLs server-side as
needed rather than relying on the URL stored in `deliverables.file_url`.
"""

from __future__ import annotations

from dataclasses import dataclass

from supabase import AsyncClient

DEFAULT_SIGNED_URL_TTL_SECONDS = 7 * 24 * 3600  # 7 days


@dataclass(frozen=True, slots=True)
class StoredFile:
    """An uploaded object plus its signed URL."""

    bucket: str
    path: str
    signed_url: str
    expires_in_seconds: int


class SupabaseStorage:
    """Async-facing wrapper over `supabase.AsyncClient.storage`."""

    def __init__(self, client: AsyncClient, default_ttl_seconds: int = DEFAULT_SIGNED_URL_TTL_SECONDS) -> None:
        self._client = client
        self._default_ttl = default_ttl_seconds

    async def upload(
        self,
        *,
        bucket: str,
        path: str,
        data: bytes,
        content_type: str,
        upsert: bool = False,
        ttl_seconds: int | None = None,
    ) -> StoredFile:
        """Upload `data` to `bucket/path` and return a signed URL.

        Raises if the path already exists and `upsert=False`.
        """
        storage = self._client.storage.from_(bucket)
        await storage.upload(
            path=path,
            file=data,
            file_options={
                "content-type": content_type,
                "upsert": "true" if upsert else "false",
            },
        )
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        signed = await storage.create_signed_url(path, expires_in=ttl)
        return StoredFile(
            bucket=bucket,
            path=path,
            signed_url=str(signed["signedURL"]),
            expires_in_seconds=ttl,
        )

    async def signed_url(self, *, bucket: str, path: str, ttl_seconds: int | None = None) -> str:
        """Re-issue a signed URL for an existing object (e.g., after expiry)."""
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        signed = await self._client.storage.from_(bucket).create_signed_url(path, expires_in=ttl)
        return str(signed["signedURL"])

    async def download(self, *, bucket: str, path: str) -> bytes:
        """Fetch raw bytes for an object. Uses the service-role channel — no signed URL needed."""
        return await self._client.storage.from_(bucket).download(path)
