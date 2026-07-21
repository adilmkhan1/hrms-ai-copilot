"""API Tools — async wrappers that call existing HRMS backend REST endpoints.

The HR Action Agent must NEVER write to the database directly.
Instead, every mutation flows through these wrappers, which call the same
REST API endpoints the frontend uses — preserving all existing validation,
business rules, and authorization logic.

Pattern:
    Agent → api_tools.create_leave_request() → POST /api/v1/leaves/requests
                                                  → Service Layer → DB
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

BASE = settings.internal_api_base_url.rstrip("/")
TIMEOUT = 15.0  # seconds


def _auth_headers(access_token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


async def _call(
    method: str,
    path: str,
    access_token: str,
    json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generic async HTTP caller with structured error handling."""
    url = f"{BASE}{path}"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=_auth_headers(access_token),
            json=json,
        )
    data = response.json()
    if response.status_code >= 400:
        error_detail = data.get("detail") or data.get("error") or str(data)
        raise RuntimeError(f"API error {response.status_code}: {error_detail}")
    return data


# ── Leave Tools ───────────────────────────────────────────────────────────────

async def get_leave_balances(access_token: str) -> Dict[str, Any]:
    """GET /api/v1/leaves/balances/me — fetch current user's leave balances."""
    return await _call("GET", "/api/v1/leaves/balances/me", access_token)


async def get_my_leave_requests(access_token: str) -> Dict[str, Any]:
    """GET /api/v1/leaves/requests/me — fetch current user's leave history."""
    return await _call("GET", "/api/v1/leaves/requests/me", access_token)


async def get_pending_leave_requests(access_token: str) -> Dict[str, Any]:
    """GET /api/v1/leaves/requests/pending — list all pending leave requests (MANAGER/ADMIN)."""
    return await _call("GET", "/api/v1/leaves/requests/pending", access_token)


async def create_leave_request(
    leave_type: str,
    start_date: str,
    end_date: str,
    reason: str,
    is_half_day: bool = False,
    half_day_period: Optional[str] = None,
    access_token: str = "",
) -> Dict[str, Any]:
    """POST /api/v1/leaves/requests — submit a leave request on behalf of the user."""
    payload: Dict[str, Any] = {
        "leave_type": leave_type.upper(),
        "start_date": start_date,
        "end_date": end_date,
        "reason": reason,
        "is_half_day": is_half_day,
        "half_day_period": half_day_period,
    }
    return await _call("POST", "/api/v1/leaves/requests", access_token, json=payload)


async def approve_leave_request(request_id: int, access_token: str) -> Dict[str, Any]:
    """POST /api/v1/leaves/requests/{id}/approve — approve a pending leave."""
    return await _call(
        "POST", f"/api/v1/leaves/requests/{request_id}/approve", access_token
    )


async def reject_leave_request(request_id: int, access_token: str) -> Dict[str, Any]:
    """POST /api/v1/leaves/requests/{id}/reject — reject a pending leave."""
    return await _call(
        "POST", f"/api/v1/leaves/requests/{request_id}/reject", access_token
    )


# ── Ticket Tools ──────────────────────────────────────────────────────────────

async def create_ticket(
    title: str,
    description: str,
    category: str,
    priority: str,
    access_token: str,
) -> Dict[str, Any]:
    """POST /api/v1/tickets — create a support ticket."""
    payload = {
        "title": title,
        "description": description,
        "category": category.upper(),
        "priority": priority.upper(),
    }
    return await _call("POST", "/api/v1/tickets", access_token, json=payload)


async def get_my_tickets(access_token: str) -> Dict[str, Any]:
    """GET /api/v1/tickets?mine=true — fetch tickets for the current user."""
    return await _call("GET", "/api/v1/tickets?mine=true", access_token)


async def update_ticket_status(
    ticket_id: int, new_status: str, access_token: str
) -> Dict[str, Any]:
    """POST /api/v1/tickets/{id}/status — update ticket status (MANAGER/ADMIN)."""
    return await _call(
        "POST",
        f"/api/v1/tickets/{ticket_id}/status",
        access_token,
        json={"status": new_status.upper()},
    )


# ── Announcement Tools ────────────────────────────────────────────────────────

async def create_announcement(
    title: str, body: str, access_token: str
) -> Dict[str, Any]:
    """POST /api/v1/announcements — create an announcement (MANAGER/ADMIN)."""
    return await _call(
        "POST", "/api/v1/announcements", access_token, json={"title": title, "body": body}
    )


async def get_announcements(access_token: str) -> Dict[str, Any]:
    """GET /api/v1/announcements — list recent announcements."""
    return await _call("GET", "/api/v1/announcements", access_token)


# ── Project Tools ─────────────────────────────────────────────────────────────

async def assign_employee_to_project(
    employee_id: int,
    project_id: int,
    role_on_project: str,
    access_token: str,
) -> Dict[str, Any]:
    """POST /api/v1/employees/{id}/projects — assign employee to project (MANAGER/ADMIN)."""
    payload = {
        "project_id": project_id,
        "role_on_project": role_on_project,
    }
    return await _call(
        "POST", f"/api/v1/employees/{employee_id}/projects", access_token, json=payload
    )
