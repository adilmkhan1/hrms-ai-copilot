"""LangGraph Multi-Agent Orchestration Graph for the HR AI Copilot.

Architecture:
    START
      ↓
    [load_context]         ← stamps user/role/token onto shared state
      ↓
    [route_intent]         ← LLM classifies: POLICY_QA / SQL_QUERY / HR_ACTION / UNKNOWN
      ↓  conditional_edge
      ├─ POLICY_QA  → [policy_rag_node]      → [audit_log_node] → END
      ├─ SQL_QUERY  → [sql_agent_node]       → [audit_log_node] → END
      ├─ HR_ACTION  → [classify_action_node]
      │                  ↓  conditional_edge (needs_confirmation?)
      │                  ├─ YES → [hitl_node]  ←── interrupt() pauses graph here
      │                  │           ↓  (resumed by /chat/actions/confirm)
      │                  │       [execute_action_node] → [audit_log_node] → END
      │                  └─ NO  → [execute_action_node] → [audit_log_node] → END
      └─ UNKNOWN    → [unknown_node]          → [audit_log_node] → END

Key LangGraph concepts used:
    - TypedDict state (HRCopilotState)        — shared memory between nodes
    - StateGraph + compiled app               — the executable graph
    - interrupt()                             — pauses graph for human input
    - MemorySaver checkpointer                — stores state between pause/resume
    - Conditional edges                       — dynamic routing based on state
    - Command(resume=...)                     — resumes an interrupted graph
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Literal
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, END, START
from langgraph.types import interrupt, Command

from app.services.ai.hitl import (
    build_confirmation_message,
    memory_saver,
    needs_confirmation,
)

logger = logging.getLogger(__name__)


# ── Shared Graph State ─────────────────────────────────────────────────────────

class HRCopilotState(TypedDict):
    """Typed state shared across ALL nodes in the graph.

    LangGraph passes this dict through every node. Each node reads what it
    needs and writes its outputs back — just like a pipeline context object.
    """
    # ── Input (set once at the start) ──────────────────
    message: str                       # original user message
    user_id: int                       # authenticated user's DB id
    user_email: str                    # for display in confirmations
    role: str                          # ADMIN / MANAGER / EMPLOYEE
    access_token: str                  # JWT for internal API calls
    thread_id: str                     # unique per conversation turn

    # ── Routing ────────────────────────────────────────
    intent: str                        # POLICY_QA / SQL_QUERY / HR_ACTION / UNKNOWN
    confidence: float
    route_reason: str

    # ── Policy RAG result ──────────────────────────────
    rag_answer: Optional[str]
    rag_sources: Optional[List[Dict]]

    # ── SQL Agent result ───────────────────────────────
    sql_answer: Optional[str]
    sql_query: Optional[str]
    sql_rows: Optional[List[Dict]]

    # ── HR Action state ────────────────────────────────
    action_intent: Optional[str]       # e.g. "approve_leave"
    action_params: Optional[Dict]      # extracted parameters
    action_result: Optional[Dict]      # API response
    action_success: bool

    # ── HITL state ─────────────────────────────────────
    needs_confirmation: bool           # True = graph paused for human
    confirmation_message: Optional[str]
    human_confirmed: Optional[bool]    # None = pending, True = ok, False = cancel

    # ── Final output ───────────────────────────────────
    answer: str                        # the text shown to the user
    error: Optional[str]

    # ── Audit ──────────────────────────────────────────
    tool_name: Optional[str]
    action_status: str                 # SUCCESS / ERROR / PENDING / CANCELLED


# ── Node 1: Load Context ──────────────────────────────────────────────────────

def load_context_node(state: HRCopilotState) -> Dict[str, Any]:
    """Validates and stamps initial state. First node in every graph run."""
    logger.info(
        "LangGraph | load_context | user=%s role=%s",
        state.get("user_id"), state.get("role"),
    )
    return {
        "needs_confirmation": False,
        "human_confirmed": None,
        "action_success": False,
        "action_status": "PENDING",
        "rag_sources": [],
        "sql_rows": [],
    }


# ── Node 2: Route Intent ──────────────────────────────────────────────────────

async def route_intent_node(state: HRCopilotState) -> Dict[str, Any]:
    """Calls the router_agent LLM to classify the user's message."""
    from app.services.ai.router_agent import classify_route

    result = await classify_route(state["message"])
    intent = result.get("intent", "UNKNOWN")
    logger.info("LangGraph | route_intent | intent=%s confidence=%.2f", intent, result.get("confidence", 0))

    return {
        "intent": intent,
        "confidence": result.get("confidence", 0.0),
        "route_reason": result.get("reason", ""),
    }


def _route_after_intent(state: HRCopilotState) -> Literal["policy_rag", "sql_agent", "classify_action", "unknown"]:
    """Conditional edge: maps intent string to the next node name."""
    mapping = {
        "POLICY_QA": "policy_rag",
        "SQL_QUERY": "sql_agent",
        "HR_ACTION": "classify_action",
    }
    return mapping.get(state["intent"], "unknown")


# ── Node 3a: Policy RAG ───────────────────────────────────────────────────────

async def policy_rag_node(state: HRCopilotState) -> Dict[str, Any]:
    """Runs the Policy RAG pipeline and writes answer + sources to state."""
    from app.services.ai.policy_rag import answer_policy_question

    logger.info("LangGraph | policy_rag_node | user=%s", state["user_id"])
    result = await answer_policy_question(state["message"])
    return {
        "rag_answer": result.get("answer", ""),
        "rag_sources": result.get("sources", []),
        "answer": result.get("answer", ""),
        "tool_name": "policy_rag",
        "action_status": "SUCCESS",
    }


# ── Node 3b: SQL Agent ────────────────────────────────────────────────────────

async def sql_agent_node(state: HRCopilotState) -> Dict[str, Any]:
    """Runs the SQL agent — generates + validates + executes a SELECT query."""
    from app.services.ai.sql_agent import run_sql_agent
    from app.models.enums import Role

    logger.info("LangGraph | sql_agent_node | user=%s", state["user_id"])
    role_enum = Role[state["role"]]
    result = await run_sql_agent(
        message=state["message"],
        user_id=state["user_id"],
        role=role_enum,
    )
    return {
        "sql_answer": result.get("answer", ""),
        "sql_query": result.get("sql"),
        "sql_rows": result.get("rows", []),
        "answer": result.get("answer", ""),
        "tool_name": "sql_agent",
        "action_status": "SUCCESS",
    }


# ── Node 3c: Classify Action ──────────────────────────────────────────────────

async def classify_action_node(state: HRCopilotState) -> Dict[str, Any]:
    """Classifies the HR action intent and extracts parameters.

    Does NOT execute yet. The conditional edge after this decides whether
    to pause for HITL or go straight to execution.
    """
    from app.services.ai.action_agent import _classify_intent, _extract_params
    from openai import AsyncOpenAI
    from app.core.config import settings

    logger.info("LangGraph | classify_action_node | user=%s", state["user_id"])
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    intent_result = await _classify_intent(state["message"], client)
    action_intent = intent_result.get("intent", "unknown")

    params = {}
    if action_intent != "unknown":
        params = await _extract_params(state["message"], action_intent, client)

    # Determine if this action needs a confirmation step
    confirmation_needed = needs_confirmation(action_intent)
    confirmation_msg = None
    if confirmation_needed:
        confirmation_msg = build_confirmation_message(action_intent, params)

    return {
        "action_intent": action_intent,
        "action_params": params,
        "needs_confirmation": confirmation_needed,
        "confirmation_message": confirmation_msg,
        "tool_name": action_intent,
    }


def _route_after_classify(state: HRCopilotState) -> Literal["hitl_node", "execute_action"]:
    """Conditional edge: if the action needs confirmation, route to hitl_node."""
    if state.get("needs_confirmation"):
        return "hitl_node"
    return "execute_action"


# ── Node 3d: HITL Node ────────────────────────────────────────────────────────

def hitl_node(state: HRCopilotState) -> Dict[str, Any]:
    """Human-in-the-Loop checkpoint.

    Calls langgraph's `interrupt()` which:
      1. Immediately pauses graph execution here
      2. Saves the full state to MemorySaver under thread_id
      3. Returns the interrupt value to the caller (our API endpoint)

    The graph will resume when /chat/actions/confirm sends:
      Command(resume={"confirmed": True/False})
    """
    logger.info(
        "LangGraph | hitl_node | PAUSING for confirmation | action=%s",
        state.get("action_intent"),
    )

    # interrupt() raises an internal LangGraph exception that suspends the graph.
    # The value passed here is what the API returns as "confirmation_message".
    human_input = interrupt({
        "confirmation_message": state["confirmation_message"],
        "action_intent": state["action_intent"],
        "action_params": state["action_params"],
    })

    # When the graph is RESUMED, execution continues here with human_input
    # containing whatever was passed in Command(resume=...)
    confirmed = human_input.get("confirmed", False) if isinstance(human_input, dict) else False

    logger.info("LangGraph | hitl_node | RESUMED | confirmed=%s", confirmed)
    return {
        "human_confirmed": confirmed,
        "needs_confirmation": False,
    }


def _route_after_hitl(state: HRCopilotState) -> Literal["execute_action", "cancelled"]:
    """After HITL resumes, go to execute if confirmed, or cancelled node."""
    if state.get("human_confirmed"):
        return "execute_action"
    return "cancelled"


# ── Node 3e: Execute Action ───────────────────────────────────────────────────

async def execute_action_node(state: HRCopilotState) -> Dict[str, Any]:
    """Executes the HR action by calling the backend API via api_tools.

    This is the only node that makes mutations — and it does so through
    the existing REST API layer, never directly to the database.
    """
    from app.services.ai.action_agent import _execute_tool
    from app.models.employee import Employee
    from app.models.enums import Role
    from app.db.session import async_session_factory

    logger.info(
        "LangGraph | execute_action_node | action=%s user=%s",
        state.get("action_intent"), state["user_id"],
    )

    try:
        async with async_session_factory() as db:
            user = await db.get(Employee, state["user_id"])
            if not user:
                return {"answer": "User not found.", "action_status": "ERROR", "action_success": False}

        result = await _execute_tool(
            intent=state["action_intent"],
            params=state["action_params"] or {},
            user=user,
            access_token=state["access_token"],
        )

        return {
            "action_result": result,
            "answer": result.get("summary", "Action completed."),
            "action_success": result.get("success", False),
            "action_status": "SUCCESS" if result.get("success") else "ERROR",
        }
    except Exception as e:
        logger.exception("LangGraph | execute_action_node | error: %s", e)
        return {
            "answer": f"Action failed: {str(e)}",
            "action_status": "ERROR",
            "action_success": False,
        }


# ── Node 3f: Cancelled ────────────────────────────────────────────────────────

def cancelled_node(state: HRCopilotState) -> Dict[str, Any]:
    """User declined the HITL confirmation — action is cancelled."""
    logger.info("LangGraph | cancelled_node | action=%s cancelled by user", state.get("action_intent"))
    return {
        "answer": f"Action **{state.get('action_intent', 'request')}** was cancelled.",
        "action_status": "CANCELLED",
        "action_success": False,
    }


# ── Node 3g: Unknown ──────────────────────────────────────────────────────────

def unknown_node(state: HRCopilotState) -> Dict[str, Any]:
    """Handles messages that don't match any supported intent."""
    return {
        "answer": (
            "I'm the HR AI Copilot. I can help you with:\n\n"
            "• **HR Policy questions** — Ask about leave, WFH, benefits\n"
            "• **People & Project data** — Find employees, skills, assignments\n"
            "• **HR Actions** — Apply leave, create tickets, approve requests\n\n"
            "What would you like to know?"
        ),
        "action_status": "SUCCESS",
        "tool_name": "unknown",
    }


# ── Node 4: Audit Log ─────────────────────────────────────────────────────────

async def audit_log_node(state: HRCopilotState) -> Dict[str, Any]:
    """Writes the completed interaction to the ai_audit_logs table."""
    from app.services.ai.audit import log_ai_interaction
    from app.db.session import async_session_factory

    try:
        async with async_session_factory() as db:
            await log_ai_interaction(
                db=db,
                user_id=state["user_id"],
                role=state["role"],
                message=state["message"],
                intent=state.get("intent") or state.get("action_intent"),
                tool_name=state.get("tool_name"),
                action_status=state.get("action_status", "SUCCESS"),
                records_accessed=None,
            )
    except Exception as e:
        logger.warning("LangGraph | audit_log_node | failed to write audit log: %s", e)

    return {}


# ── Build and Compile the Graph ───────────────────────────────────────────────

def _build_graph() -> Any:
    """Construct the StateGraph, wire nodes + edges, and compile with MemorySaver."""

    builder = StateGraph(HRCopilotState)

    # ── Register nodes ──────────────────────────────────────────────────
    builder.add_node("load_context",     load_context_node)
    builder.add_node("route_intent",     route_intent_node)
    builder.add_node("policy_rag",       policy_rag_node)
    builder.add_node("sql_agent",        sql_agent_node)
    builder.add_node("classify_action",  classify_action_node)
    builder.add_node("hitl_node",        hitl_node)
    builder.add_node("execute_action",   execute_action_node)
    builder.add_node("cancelled",        cancelled_node)
    builder.add_node("unknown",          unknown_node)
    builder.add_node("audit_log",        audit_log_node)

    # ── Entry edge ──────────────────────────────────────────────────────
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "route_intent")

    # ── Conditional routing after intent classification ─────────────────
    builder.add_conditional_edges(
        "route_intent",
        _route_after_intent,
        {
            "policy_rag":       "policy_rag",
            "sql_agent":        "sql_agent",
            "classify_action":  "classify_action",
            "unknown":          "unknown",
        },
    )

    # ── Policy RAG → audit → END ────────────────────────────────────────
    builder.add_edge("policy_rag", "audit_log")

    # ── SQL Agent → audit → END ─────────────────────────────────────────
    builder.add_edge("sql_agent", "audit_log")

    # ── HR Action: after classify, route to HITL or direct execution ────
    builder.add_conditional_edges(
        "classify_action",
        _route_after_classify,
        {
            "hitl_node":      "hitl_node",
            "execute_action": "execute_action",
        },
    )

    # ── HITL: after resume, route to execute or cancelled ───────────────
    builder.add_conditional_edges(
        "hitl_node",
        _route_after_hitl,
        {
            "execute_action": "execute_action",
            "cancelled":      "cancelled",
        },
    )

    # ── Execution paths → audit → END ───────────────────────────────────
    builder.add_edge("execute_action", "audit_log")
    builder.add_edge("cancelled",      "audit_log")
    builder.add_edge("unknown",        "audit_log")

    # ── Audit always goes to END ─────────────────────────────────────────
    builder.add_edge("audit_log", END)

    # ── Compile with MemorySaver for HITL checkpointing ─────────────────
    graph = builder.compile(checkpointer=memory_saver)
    logger.info("LangGraph | graph compiled | nodes=%s", list(builder.nodes))
    return graph


# Singleton — compiled once at import time
hr_copilot_graph = _build_graph()


# ── Public API ────────────────────────────────────────────────────────────────

async def run_graph(
    message: str,
    user_id: int,
    user_email: str,
    role: str,
    access_token: str,
    thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the graph from START for a new user message.

    Returns the final state dict. If HITL is triggered, the state will
    contain needs_confirmation=True and a thread_id for resumption.
    """
    if thread_id is None:
        thread_id = str(uuid.uuid4())

    initial_state: HRCopilotState = {
        "message": message,
        "user_id": user_id,
        "user_email": user_email,
        "role": role,
        "access_token": access_token,
        "thread_id": thread_id,
        # Defaults — nodes will overwrite these
        "intent": "",
        "confidence": 0.0,
        "route_reason": "",
        "rag_answer": None,
        "rag_sources": [],
        "sql_answer": None,
        "sql_query": None,
        "sql_rows": [],
        "action_intent": None,
        "action_params": None,
        "action_result": None,
        "action_success": False,
        "needs_confirmation": False,
        "confirmation_message": None,
        "human_confirmed": None,
        "answer": "",
        "error": None,
        "tool_name": None,
        "action_status": "PENDING",
    }

    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = await hr_copilot_graph.ainvoke(initial_state, config=config)
        final_state["thread_id"] = thread_id
        return final_state
    except Exception as e:
        # If interrupt() was called, LangGraph raises GraphInterrupt — catch it
        # and surface the HITL data to the caller
        from langgraph.errors import GraphInterrupt
        if isinstance(e, GraphInterrupt):
            # Extract the interrupt value (what we passed to interrupt())
            interrupt_value = e.args[0][0].value if e.args and e.args[0] else {}
            logger.info("LangGraph | run_graph | GraphInterrupt caught | thread_id=%s", thread_id)
            return {
                "thread_id": thread_id,
                "needs_confirmation": True,
                "confirmation_message": interrupt_value.get("confirmation_message", "Confirm this action?"),
                "action_intent": interrupt_value.get("action_intent"),
                "action_params": interrupt_value.get("action_params", {}),
                "answer": "",
                "action_status": "PENDING_CONFIRMATION",
            }
        logger.exception("LangGraph | run_graph | unhandled error: %s", e)
        return {
            "thread_id": thread_id,
            "answer": f"An error occurred: {str(e)}",
            "action_status": "ERROR",
            "needs_confirmation": False,
        }


async def resume_graph(thread_id: str, confirmed: bool) -> Dict[str, Any]:
    """Resume a paused graph after the user responds to a HITL confirmation.

    Args:
        thread_id: the same thread_id returned from the initial run_graph call.
        confirmed: True if the user clicked "Confirm", False if they clicked "Cancel".
    """
    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = await hr_copilot_graph.ainvoke(
            Command(resume={"confirmed": confirmed}),
            config=config,
        )
        final_state["thread_id"] = thread_id
        final_state["needs_confirmation"] = False
        return final_state
    except Exception as e:
        logger.exception("LangGraph | resume_graph | error: %s", e)
        return {
            "thread_id": thread_id,
            "answer": f"Resume failed: {str(e)}",
            "action_status": "ERROR",
            "needs_confirmation": False,
        }
