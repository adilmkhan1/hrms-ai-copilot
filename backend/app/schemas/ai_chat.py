"""Pydantic schemas for AI chat endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Shared ────────────────────────────────────────────────────────────────────

class PolicySource(BaseModel):
    title: str
    category: str
    filename: Optional[str] = None


# ── Policy RAG ───────────────────────────────────────────────────────────────

class PolicyChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class PolicyChatResponse(BaseModel):
    answer: str
    sources: List[PolicySource]


# ── SQL Agent ─────────────────────────────────────────────────────────────────

class SQLChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class SQLChatResponse(BaseModel):
    answer: str
    sql: Optional[str] = None
    rows: List[Dict[str, Any]] = []


# ── HR Action Agent ───────────────────────────────────────────────────────────

class ActionChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class ActionChatResponse(BaseModel):
    intent: str
    result: str
    data: Optional[Any] = None
    success: bool


# ── Router ────────────────────────────────────────────────────────────────────

class RouterChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class RouterChatResponse(BaseModel):
    intent: str
    confidence: float
    reason: str


# ── AI Audit Log ──────────────────────────────────────────────────────────────

class AIAuditLogResponse(BaseModel):
    id: int
    user_id: int
    role: str
    message: str
    intent: Optional[str]
    tool_name: Optional[str]
    action_status: Optional[str]
    records_accessed: Optional[str]
    created_at: str
