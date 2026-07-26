"""AI Permissions Matrix — maps (role, action) → allowed: bool.

This mirrors the authorization model of the existing HRMS application.
AI agents must check these permissions before calling any backend API tool.
"""

from __future__ import annotations

from app.models.enums import Role


class PermissionDeniedError(PermissionError):
    """Raised when an AI action is not permitted for the current user's role."""


# ── Permission matrix ─────────────────────────────────────────────────────────
# Format: {action_name: {Role.X, Role.Y, ...}}  — roles that ARE allowed

_ALLOWED_ROLES: dict[str, set[Role]] = {
    # Policy questions
    "ask_policy": {Role.EMPLOYEE, Role.MANAGER, Role.ADMIN},
    # Leave
    "view_own_leave": {Role.EMPLOYEE, Role.MANAGER, Role.ADMIN},
    "view_team_leave": {Role.MANAGER, Role.ADMIN},
    "view_all_leave": {Role.ADMIN},
    "create_leave_request": {Role.EMPLOYEE, Role.MANAGER, Role.ADMIN},
    "approve_leave": {Role.MANAGER, Role.ADMIN},
    "reject_leave": {Role.MANAGER, Role.ADMIN},
    # Tickets
    "create_ticket": {Role.EMPLOYEE, Role.MANAGER, Role.ADMIN},
    "view_own_tickets": {Role.EMPLOYEE, Role.MANAGER, Role.ADMIN},
    "assign_ticket": {Role.MANAGER, Role.ADMIN},
    "update_ticket_status": {Role.MANAGER, Role.ADMIN},
    # Announcements
    "create_announcement": {Role.MANAGER, Role.ADMIN},
    # Projects
    "view_own_projects": {Role.EMPLOYEE, Role.MANAGER, Role.ADMIN},
    "view_all_projects": {Role.MANAGER, Role.ADMIN},
    "assign_employee_to_project": {Role.MANAGER, Role.ADMIN},
    # SQL / data queries
    "sql_query_own": {Role.EMPLOYEE, Role.MANAGER, Role.ADMIN},
    "sql_query_team": {Role.MANAGER, Role.ADMIN},
    "sql_query_all": {Role.ADMIN},
    # Sensitive data
    "view_salary": {Role.ADMIN},
    "view_bank_details": set(),   # nobody through AI
    "view_pan_details": set(),    # nobody through AI
}


def is_allowed(role: Role, action: str) -> bool:
    """Return True if the role is permitted to perform the action."""
    return role in _ALLOWED_ROLES.get(action, set())


def require_permission(role: Role, action: str) -> None:
    """Raise PermissionDeniedError if the role is not permitted.

    Example:
        require_permission(current_user.role, "approve_leave")
    """
    if not is_allowed(role, action):
        raise PermissionDeniedError(
            f"You do not have permission to perform '{action}'. "
            f"This action requires one of: "
            f"{sorted(r.value for r in _ALLOWED_ROLES.get(action, set()))}."
        )
