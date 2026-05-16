"""Storage clients — Supabase Storage wrapper for deliverables and references.

Buckets are created out-of-band (see repo README). This package provides a
thin async wrapper that uploads bytes, returns signed URLs with a configurable
TTL, and centralizes the bucket-name convention.
"""

from agency.storage.supabase_storage import StoredFile, SupabaseStorage

__all__ = ["StoredFile", "SupabaseStorage"]
