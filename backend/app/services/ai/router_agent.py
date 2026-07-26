"""AI Router Agent — classifies user intent and routes to the right sub-system.

Routes:
  POLICY_QA   → Policy RAG
  SQL_QUERY   → SQL Agent
  HR_ACTION   → HR Task Automation Agent
  UNKNOWN     → Returns a helpful message
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """You are an intent router for the CB Nest HR AI Copilot.

Classify each user message into one of these intents:
- POLICY_QA   : Questions about HR policies, rules, benefits, leave entitlements, work-from-home rules, etc.
- SQL_QUERY   : Requests to look up data about employees, projects, skills, assignments, leave counts, etc.
- HR_ACTION   : Requests to DO something: apply for leave, create a ticket, approve leave, create an announcement, assign someone to a project.
- UNKNOWN     : Greetings, unrelated questions, or anything that doesn't fit.

Respond ONLY with JSON:
{
  "intent": "POLICY_QA" | "SQL_QUERY" | "HR_ACTION" | "UNKNOWN",
  "confidence": 0.95,
  "reason": "brief explanation"
}

Examples:
- "What is the leave policy?" → POLICY_QA
- "Who is assigned to Project X?" → SQL_QUERY
- "Apply casual leave for tomorrow" → HR_ACTION
- "Which employees know Python?" → SQL_QUERY
- "Create a ticket for VPN issue" → HR_ACTION
- "How many sick days do I have left?" → could be SQL_QUERY (balance lookup) or POLICY_QA (policy question) — use SQL_QUERY if it's a personal balance check
- "Hello" → UNKNOWN"""


async def classify_route(message: str) -> Dict[str, Any]:
    """Return {"intent": str, "confidence": float, "reason": str}."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        temperature=0.0,
        max_tokens=100,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(response.choices[0].message.content or "{}")
    except json.JSONDecodeError:
        return {"intent": "UNKNOWN", "confidence": 0.0, "reason": "parse error"}
