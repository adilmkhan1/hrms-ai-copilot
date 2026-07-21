"""HR Task Automation Agent — performs HR operations via natural language.

The agent:
  1. Classifies the user's intent from their message
  2. Extracts required parameters
  3. Checks AI permissions for the user's role
  4. Calls the appropriate backend API tool
  5. Returns a human-friendly summary

Critical rule: agents NEVER write to the DB directly.
They call api_tools.py functions which forward to existing REST endpoints.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from openai import AsyncOpenAI

from app.core.config import settings
from app.models.employee import Employee
from app.services.ai import api_tools
from app.services.ai.permissions import PermissionDeniedError, require_permission

logger = logging.getLogger(__name__)

# ── Intent classification ─────────────────────────────────────────────────────

INTENT_SYSTEM_PROMPT = """You are an intent classifier for the CB Nest HR system.

Given a user message, classify it into one of these intents:

- create_leave_request   : user wants to apply/submit/request leave
- get_leave_balance      : user wants to see their leave balance or remaining days
- get_my_leave_requests  : user wants to see their leave history or current status
- approve_leave          : manager/admin wants to approve a pending leave request
- reject_leave           : manager/admin wants to reject a pending leave request
- get_pending_leaves     : manager/admin wants to see pending leave requests to approve
- create_ticket          : user wants to raise/create a support or IT ticket
- get_my_tickets         : user wants to see their tickets
- create_announcement    : manager/admin wants to post an announcement
- assign_to_project      : manager/admin wants to assign an employee to a project
- unknown                : none of the above

Respond ONLY with a JSON object in this exact format:
{
  "intent": "<intent_name>",
  "confidence": 0.95,
  "reason": "brief explanation"
}"""


EXTRACTION_PROMPTS: Dict[str, str] = {
    "create_leave_request": """Extract leave request details from the user message.
Return JSON with keys: leave_type (CASUAL/SICK/EARNED), start_date (YYYY-MM-DD), 
end_date (YYYY-MM-DD), reason, is_half_day (boolean), half_day_period (FIRST_HALF/SECOND_HALF/null).
Today's date for reference: {today}.
If any required field is missing/ambiguous, set it to null.""",

    "approve_leave": """Extract leave request ID to approve. 
Return JSON: {"request_id": <int or null>}
If no specific ID is mentioned, set to null.""",

    "reject_leave": """Extract leave request ID to reject.
Return JSON: {"request_id": <int or null>}
If no specific ID is mentioned, set to null.""",

    "create_ticket": """Extract ticket details.
Return JSON: {"title": str, "description": str, 
"category": "IT"/"HR"/"ONBOARDING", "priority": "LOW"/"MEDIUM"/"HIGH"}
Infer category and priority from context if not explicit.""",

    "create_announcement": """Extract announcement details.
Return JSON: {"title": str, "body": str}""",

    "assign_to_project": """Extract project assignment details.
Return JSON: {"employee_id": <int or null>, "project_id": <int or null>, 
"role_on_project": str}
If IDs are not mentioned, set to null.""",
}


async def _classify_intent(message: str, client: AsyncOpenAI) -> Dict[str, Any]:
    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        temperature=0.0,
        max_tokens=150,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {"intent": "unknown", "confidence": 0.0, "reason": "parse error"}


async def _extract_params(
    message: str,
    intent: str,
    client: AsyncOpenAI,
) -> Dict[str, Any]:
    """Extract structured parameters from the user's message for the given intent."""
    extraction_prompt = EXTRACTION_PROMPTS.get(intent)
    if not extraction_prompt:
        return {}

    from datetime import date
    today = date.today().isoformat()
    extraction_prompt = extraction_prompt.replace("{today}", today)

    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": extraction_prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.0,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {}


# ── Action execution ──────────────────────────────────────────────────────────

async def execute_hr_action(
    message: str,
    current_user: Employee,
    access_token: str,
) -> Dict[str, Any]:
    """
    Classify intent, check permissions, extract params, and call API tool.

    Returns:
        {
            "intent": str,
            "result": str,   # natural language summary
            "data": dict,    # raw API response data (optional)
            "success": bool,
        }
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    role = current_user.role

    # ── Classify intent ───────────────────────────────────────────────────────
    intent_data = await _classify_intent(message, client)
    intent = intent_data.get("intent", "unknown")
    logger.info(
        "Action agent: user=%d role=%s intent=%s",
        current_user.id,
        role.value,
        intent,
    )

    # ── Map intent → permission action ────────────────────────────────────────
    INTENT_TO_PERMISSION: Dict[str, str] = {
        "create_leave_request": "create_leave_request",
        "get_leave_balance": "view_own_leave",
        "get_my_leave_requests": "view_own_leave",
        "approve_leave": "approve_leave",
        "reject_leave": "reject_leave",
        "get_pending_leaves": "approve_leave",
        "create_ticket": "create_ticket",
        "get_my_tickets": "view_own_tickets",
        "create_announcement": "create_announcement",
        "assign_to_project": "assign_employee_to_project",
    }

    perm_action = INTENT_TO_PERMISSION.get(intent)
    if not perm_action:
        return {
            "intent": intent,
            "result": "I'm not sure what you'd like to do. Please describe your HR request more specifically.",
            "data": None,
            "success": False,
        }

    # ── Permission check ──────────────────────────────────────────────────────
    try:
        require_permission(role, perm_action)
    except PermissionDeniedError as exc:
        return {
            "intent": intent,
            "result": str(exc),
            "data": None,
            "success": False,
        }

    # ── Extract parameters ────────────────────────────────────────────────────
    params = await _extract_params(message, intent, client)

    # ── Execute via API tool ──────────────────────────────────────────────────
    try:
        result_str, data = await _dispatch(intent, params, access_token, current_user)
        return {"intent": intent, "result": result_str, "data": data, "success": True}
    except RuntimeError as exc:
        logger.warning("API tool call failed: %s", exc)
        return {
            "intent": intent,
            "result": f"The action could not be completed: {exc}",
            "data": None,
            "success": False,
        }
    except ValueError as exc:
        return {
            "intent": intent,
            "result": str(exc),
            "data": None,
            "success": False,
        }


async def _dispatch(
    intent: str,
    params: Dict[str, Any],
    access_token: str,
    current_user: Employee,
) -> tuple[str, Any]:
    """Call the correct API tool and return (human_summary, raw_data)."""

    if intent == "get_leave_balance":
        resp = await api_tools.get_leave_balances(access_token)
        balances = resp.get("data", [])
        lines = [
            f"{b['leave_type']}: {b['remaining']} days remaining (used {b['used']}/{b['total']})"
            for b in balances
        ]
        return "Your current leave balances:\n" + "\n".join(lines), balances

    if intent == "get_my_leave_requests":
        resp = await api_tools.get_my_leave_requests(access_token)
        items = resp.get("data", {}).get("items", [])
        if not items:
            return "You have no leave requests on record.", []
        lines = [
            f"#{item['id']} {item['leave_type']} ({item['start_date']} – {item['end_date']}): {item['status']}"
            for item in items[:5]
        ]
        return f"Your recent leave requests:\n" + "\n".join(lines), items

    if intent == "get_pending_leaves":
        resp = await api_tools.get_pending_leave_requests(access_token)
        items = resp.get("data", {}).get("items", [])
        if not items:
            return "There are no pending leave requests.", []
        lines = [
            f"#{item['id']} Employee {item['employee_id']} — {item['leave_type']} ({item['start_date']} – {item['end_date']})"
            for item in items[:10]
        ]
        return f"Pending leave requests:\n" + "\n".join(lines), items

    if intent == "create_leave_request":
        lt = params.get("leave_type") or "CASUAL"
        start = params.get("start_date")
        end = params.get("end_date") or start
        reason = params.get("reason") or "Personal"
        half_day = bool(params.get("is_half_day", False))
        half_period = params.get("half_day_period")

        if not start:
            raise ValueError(
                "I need a start date for your leave request. Please specify a date."
            )

        resp = await api_tools.create_leave_request(
            leave_type=lt,
            start_date=start,
            end_date=end,
            reason=reason,
            is_half_day=half_day,
            half_day_period=half_period,
            access_token=access_token,
        )
        data = resp.get("data", {})
        return (
            f"✅ Your {lt.lower()} leave request has been submitted.\n"
            f"Dates: {start} to {end}\n"
            f"Status: {data.get('status', 'PENDING')}\n"
            f"Request ID: #{data.get('id', '—')}",
            data,
        )

    if intent == "approve_leave":
        rid = params.get("request_id")
        if not rid:
            # List pending so the user can choose
            resp = await api_tools.get_pending_leave_requests(access_token)
            items = resp.get("data", {}).get("items", [])
            if not items:
                return "There are no pending leave requests to approve.", []
            lines = [
                f"#{item['id']} Employee {item['employee_id']} — {item['leave_type']} ({item['start_date']} – {item['end_date']})"
                for item in items[:10]
            ]
            return (
                "Please specify which leave request ID to approve:\n" + "\n".join(lines),
                items,
            )
        resp = await api_tools.approve_leave_request(int(rid), access_token)
        data = resp.get("data", {})
        return f"✅ Leave request #{rid} has been approved.", data

    if intent == "reject_leave":
        rid = params.get("request_id")
        if not rid:
            raise ValueError(
                "Please specify the leave request ID to reject."
            )
        resp = await api_tools.reject_leave_request(int(rid), access_token)
        return f"❌ Leave request #{rid} has been rejected.", resp.get("data")

    if intent == "create_ticket":
        title = params.get("title") or "Support Request"
        description = params.get("description") or message
        category = params.get("category") or "IT"
        priority = params.get("priority") or "MEDIUM"
        resp = await api_tools.create_ticket(
            title=title,
            description=description,
            category=category,
            priority=priority,
            access_token=access_token,
        )
        data = resp.get("data", {})
        return (
            f"✅ Ticket #{data.get('id')} created.\n"
            f"Title: {title}\nCategory: {category} | Priority: {priority}\nStatus: OPEN",
            data,
        )

    if intent == "get_my_tickets":
        resp = await api_tools.get_my_tickets(access_token)
        items = resp.get("data", {}).get("items", [])
        if not items:
            return "You have no tickets on record.", []
        lines = [
            f"#{t['id']} [{t['priority']}] {t['title']} — {t['status']}"
            for t in items[:5]
        ]
        return "Your recent tickets:\n" + "\n".join(lines), items

    if intent == "create_announcement":
        title = params.get("title") or "Announcement"
        body = params.get("body") or ""
        if not body:
            raise ValueError("Please provide the announcement content.")
        resp = await api_tools.create_announcement(title, body, access_token)
        data = resp.get("data", {})
        return f"✅ Announcement '{title}' has been posted.", data

    if intent == "assign_to_project":
        emp_id = params.get("employee_id")
        proj_id = params.get("project_id")
        role_on_project = params.get("role_on_project") or "Member"
        if not emp_id or not proj_id:
            raise ValueError(
                "Please specify both the employee and the project to assign them to."
            )
        resp = await api_tools.assign_employee_to_project(
            employee_id=int(emp_id),
            project_id=int(proj_id),
            role_on_project=role_on_project,
            access_token=access_token,
        )
        return (
            f"✅ Employee {emp_id} has been assigned to project {proj_id} as {role_on_project}.",
            resp.get("data"),
        )

    raise ValueError(f"Unknown intent: {intent}")
