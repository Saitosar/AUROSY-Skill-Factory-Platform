"""Request dependencies (Phase 5 identity)."""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.config import get_settings
from app.platform_paths import sanitize_user_id


def get_user_id(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> str:
    s = get_settings()
    raw = x_user_id if x_user_id is not None and x_user_id.strip() else s.dev_user_id
    try:
        return sanitize_user_id(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
