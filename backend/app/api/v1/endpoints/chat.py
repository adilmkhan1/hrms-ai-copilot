"""AI Chat endpoints — Policy RAG, SQL Agent, HR Action Agent, Router.

All endpoints:
  - Require JWT authentication (get_current_user)
  - Respect role-based access control via AI permissions layer
  - Log every interaction to ai_audit_logs
  - Never write to business tables directly (action agent calls backend APIs)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import error_response, success_response
from app.db.session import get_db
from app.models.employee import Employee
from app.schemas.ai_chat import (
    ActionChatRequest,
    PolicyChatRequest,
    RouterChatRequest,
    SQLChatRequest,
)
from app.services.ai.audit import log_ai_interaction
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def _extract_token(request: Request) -> str:
    """Pull the raw Bearer token from the request for tool forwarding."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return ""


# ── Policy RAG ────────────────────────────────────────────────────────────────

@router.post("/policy")
async def chat_policy(
    payload: PolicyChatRequest,
    request: Request,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Answer an HR policy question using vector-search RAG.

    Grounded in retrieved policy documents — never from model memory.
    """
    from app.services.ai.policy_rag import answer_policy_question

    try:
        result = await answer_policy_question(payload.message)
    except Exception as exc:
        logger.error("Policy RAG error: %s", exc, exc_info=True)
        await log_ai_interaction(
            db,
            user_id=current_user.id,
            role=current_user.role.value,
            message=payload.message,
            intent="POLICY_QA",
            tool_name="policy_rag",
            action_status="ERROR",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("AI_ERROR", "Policy assistant encountered an error."),
        ) from exc

    await log_ai_interaction(
        db,
        user_id=current_user.id,
        role=current_user.role.value,
        message=payload.message,
        intent="POLICY_QA",
        tool_name="policy_rag",
        action_status="SUCCESS",
        records_accessed=[s["title"] for s in result["sources"]],
    )

    return success_response(
        {"answer": result["answer"], "sources": result["sources"]}
    )


# ── SQL Agent ─────────────────────────────────────────────────────────────────

@router.post("/sql")
async def chat_sql(
    payload: SQLChatRequest,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Answer a data question using safe read-only SQL.

    Generates and validates SQL before executing against the HRMS database.
    Sensitive columns are always blocked.
    """
    from app.services.ai.sql_agent import answer_sql_question

    try:
        result = await answer_sql_question(payload.message, current_user)
    except Exception as exc:
        logger.error("SQL agent error: %s", exc, exc_info=True)
        await log_ai_interaction(
            db,
            user_id=current_user.id,
            role=current_user.role.value,
            message=payload.message,
            intent="SQL_QUERY",
            tool_name="sql_agent",
            action_status="ERROR",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("AI_ERROR", "SQL assistant encountered an error."),
        ) from exc

    await log_ai_interaction(
        db,
        user_id=current_user.id,
        role=current_user.role.value,
        message=payload.message,
        intent="SQL_QUERY",
        tool_name="sql_agent",
        action_status="SUCCESS",
        records_accessed={"row_count": len(result["rows"])},
    )

    return success_response(
        {
            "answer": result["answer"],
            "sql": result["sql"],
            "rows": result["rows"],
        }
    )


# ── HR Action Agent ───────────────────────────────────────────────────────────

@router.post("/actions")
async def chat_actions(
    payload: ActionChatRequest,
    request: Request,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Perform an HR action via natural language.

    The agent calls existing backend REST APIs — never writes to the DB directly.
    """
    from app.services.ai.action_agent import execute_hr_action

    access_token = _extract_token(request)

    try:
        result = await execute_hr_action(payload.message, current_user, access_token)
    except Exception as exc:
        logger.error("Action agent error: %s", exc, exc_info=True)
        await log_ai_interaction(
            db,
            user_id=current_user.id,
            role=current_user.role.value,
            message=payload.message,
            intent="HR_ACTION",
            tool_name="action_agent",
            action_status="ERROR",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("AI_ERROR", "HR action agent encountered an error."),
        ) from exc

    await log_ai_interaction(
        db,
        user_id=current_user.id,
        role=current_user.role.value,
        message=payload.message,
        intent=result.get("intent", "HR_ACTION"),
        tool_name="action_agent",
        action_status="SUCCESS" if result.get("success") else "PERMISSION_DENIED",
    )

    return success_response(
        {
            "intent": result["intent"],
            "result": result["result"],
            "data": result.get("data"),
            "success": result["success"],
        }
    )


# ── Unified Router ────────────────────────────────────────────────────────────

@router.post("/router")
async def chat_router(
    payload: RouterChatRequest,
    current_user: Employee = Depends(get_current_user),
):
    """Classify the intent of a user message and return the suggested route.

    Useful for the frontend to decide which tab/endpoint to call.
    """
    from app.services.ai.router_agent import classify_route

    try:
        classification = await classify_route(payload.message)
    except Exception as exc:
        logger.error("Router error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("AI_ERROR", "Router encountered an error."),
        ) from exc

    return success_response(classification)


# ── Policy indexing trigger (Admin only) ──────────────────────────────────────

@router.post("/policy/reindex")
async def reindex_policies(
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-index all HR policies into ChromaDB. Admin only."""
    from app.models.enums import Role

    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("FORBIDDEN", "Only admins can trigger policy re-indexing."),
        )

    from app.services.ai.policy_rag import index_all_policies

    total_chunks = await index_all_policies(db)
    return success_response({"indexed_chunks": total_chunks})


# ── AI Audit Logs (Admin only) ────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_ai_audit_logs(
    limit: int = 50,
    offset: int = 0,
    current_user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """View AI audit logs. Admin only."""
    from app.models.enums import Role

    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("FORBIDDEN", "Only admins can view audit logs."),
        )

    from sqlalchemy import func, select
    from app.models.ai_audit_log import AIAuditLog

    total = (await db.execute(select(func.count(AIAuditLog.id)))).scalar_one()
    rows = (
        await db.execute(
            select(AIAuditLog)
            .order_by(AIAuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return success_response(
        {
            "items": [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "role": r.role,
                    "message": r.message,
                    "intent": r.intent,
                    "tool_name": r.tool_name,
                    "action_status": r.action_status,
                    "records_accessed": r.records_accessed,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
            "meta": {"total": total, "limit": limit, "offset": offset},
        }
    )
