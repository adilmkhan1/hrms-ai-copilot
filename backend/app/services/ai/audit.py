"""AI Audit Logging — records every AI interaction for compliance."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_audit_log import AIAuditLog

logger = logging.getLogger(__name__)


async def log_ai_interaction(
    db: AsyncSession,
    user_id: int,
    role: str,
    message: str,
    intent: Optional[str] = None,
    tool_name: Optional[str] = None,
    action_status: Optional[str] = None,
    records_accessed: Optional[Any] = None,
) -> None:
    """Persist an AI interaction to the audit log table.

    Sensitive data (tokens, passwords, bank details) must NEVER be passed here.
    """
    records_str: Optional[str] = None
    if records_accessed is not None:
        try:
            records_str = json.dumps(records_accessed, default=str)[:2000]
        except Exception:
            records_str = str(records_accessed)[:2000]

    log_entry = AIAuditLog(
        user_id=user_id,
        role=role,
        message=message[:1000],  # cap at 1000 chars
        intent=intent,
        tool_name=tool_name,
        action_status=action_status,
        records_accessed=records_str,
    )
    db.add(log_entry)
    try:
        await db.commit()
    except Exception as exc:
        logger.warning("AI audit log commit failed (non-fatal): %s", exc)
        await db.rollback()
