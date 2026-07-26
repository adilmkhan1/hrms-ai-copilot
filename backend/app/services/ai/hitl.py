"""HITL (Human-in-the-Loop) configuration for the HR AI Copilot.

Defines:
  - Which HR actions require human confirmation before execution
  - Confirmation message templates
  - MemorySaver reference (shared across requests for graph checkpointing)
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

# ── Shared in-memory checkpointer ─────────────────────────────────────────────
# MemorySaver stores graph state between the "pause" and "resume" calls.
# Fine for development; swap for SqliteSaver / RedisSaver in production.
memory_saver = MemorySaver()


# ── Actions that require human confirmation ────────────────────────────────────
# Low-risk actions (create_leave_request, create_ticket, get_*) execute immediately.
# High-impact actions pause the graph and ask the user to confirm.

HITL_REQUIRED_ACTIONS = {
    "approve_leave",
    "reject_leave",
    "create_announcement",
    "assign_to_project",
}


def needs_confirmation(intent: str) -> bool:
    """Return True if this action requires a human confirmation step."""
    return intent in HITL_REQUIRED_ACTIONS


def build_confirmation_message(intent: str, params: dict) -> str:
    """Build a human-readable confirmation prompt for the given action + params."""
    if intent == "approve_leave":
        req_id = params.get("request_id", "?")
        return (
            f"✅ You're about to **approve** leave request **#{req_id}**.\n\n"
            "Please confirm this action."
        )

    if intent == "reject_leave":
        req_id = params.get("request_id", "?")
        return (
            f"❌ You're about to **reject** leave request **#{req_id}**.\n\n"
            "This action cannot be undone. Please confirm."
        )

    if intent == "create_announcement":
        title = params.get("title", "Untitled")
        body = params.get("body", "")
        preview = body[:120] + "..." if len(body) > 120 else body
        return (
            f"📢 You're about to post an announcement:\n\n"
            f"**{title}**\n{preview}\n\n"
            "Confirm posting to all employees?"
        )

    if intent == "assign_to_project":
        emp_id = params.get("employee_id", "?")
        proj_id = params.get("project_id", "?")
        role = params.get("role_on_project", "Team Member")
        return (
            f"👤 You're about to assign **Employee #{emp_id}** to "
            f"**Project #{proj_id}** as **{role}**.\n\n"
            "Confirm this assignment?"
        )

    return f"You're about to perform: **{intent}**. Confirm?"
