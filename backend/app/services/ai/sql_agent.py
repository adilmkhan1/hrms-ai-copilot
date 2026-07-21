"""SQL Agent — natural language → safe SQL → execution → natural language summary.

Flow:
  1. Build schema context (table/column descriptions, forbidden columns excluded)
  2. Apply role-based schema filtering (e.g., EMPLOYEE sees only own data)
  3. Call LLM to generate a SELECT query
  4. Validate via sql_guardrails
  5. Execute against the HRMS SQLite database
  6. Generate a natural language summary of results
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiosqlite
from openai import AsyncOpenAI

from app.core.config import settings
from app.models.employee import Employee
from app.models.enums import Role
from app.services.ai.sql_guardrails import (
    SQLGuardrailError,
    strip_forbidden_columns_from_rows,
    validate_and_sanitize_sql,
)

logger = logging.getLogger(__name__)

# ── Schema description (hand-crafted to avoid exposing forbidden columns) ──────

SCHEMA_DESCRIPTION = """
You have access to the following SQLite tables. Use ONLY these tables and columns.

TABLE: employees
  ALLOWED COLUMNS: id, name, email, department_id, manager_id, role, status,
                   joining_date, phone, address, blood_type, occupancy
  (NOTE: hashed_password, bank_*, pan_*, date_of_birth, current_salary_usd,
         profile_photo_path, profile_photo_mime are FORBIDDEN — never select them)

TABLE: departments
  COLUMNS: id, name

TABLE: projects
  COLUMNS: id, name, description, status

TABLE: employee_projects
  COLUMNS: id, employee_id, project_id, role_on_project, assigned_date

TABLE: skills
  COLUMNS: id, name

TABLE: employee_skills
  COLUMNS: id, employee_id, skill_id, level

TABLE: job_history
  COLUMNS: id, employee_id, title, department_id, start_date, end_date, change_reason

TABLE: leave_balances
  COLUMNS: id, employee_id, leave_type, total, used, remaining

TABLE: leave_requests
  COLUMNS: id, employee_id, leave_type, start_date, end_date, is_half_day,
           half_day_period, reason, status, approver_id

TABLE: tickets
  COLUMNS: id, employee_id, assignee_id, title, description, category,
           priority, status, created_at

Common join patterns:
  employees JOIN departments ON employees.department_id = departments.id
  employees JOIN employee_projects ON employees.id = employee_projects.employee_id
  employee_projects JOIN projects ON employee_projects.project_id = projects.id
  employees JOIN employee_skills ON employees.id = employee_skills.employee_id
  employee_skills JOIN skills ON employee_skills.skill_id = skills.id
""".strip()

ROLE_FILTERS: Dict[str, str] = {
    "EMPLOYEE": (
        "IMPORTANT: This user is an EMPLOYEE. Their employee_id is {user_id}. "
        "They can ONLY see:\n"
        "  - Their own employee record (WHERE employees.id = {user_id})\n"
        "  - Their own leave requests and balances\n"
        "  - Their own ticket submissions\n"
        "  - Their own project assignments\n"
        "  - General project catalog (name, description, status — no assignments of others)\n"
        "  - General skill catalog\n"
        "Do NOT generate SQL that returns other employees' personal data."
    ),
    "MANAGER": (
        "IMPORTANT: This user is a MANAGER. Their employee_id is {user_id}. "
        "They can see:\n"
        "  - All employees in their team (department)\n"
        "  - All project assignments\n"
        "  - All skills\n"
        "  - Team leave requests and balances\n"
        "  - All tickets\n"
        "Do NOT expose salary, bank, or PAN data."
    ),
    "ADMIN": (
        "This user is an ADMIN (employee_id={user_id}). "
        "They can query all non-forbidden columns across all tables."
    ),
}

SQL_SYSTEM_PROMPT = """You are a SQL generator for the CB Nest HRMS database (SQLite).

RULES:
1. Generate ONLY a single SELECT statement.
2. NEVER use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, PRAGMA, ATTACH, DETACH.
3. NEVER select forbidden columns: hashed_password, bank_account_number, bank_account_name,
   bank_branch, bank_ifsc, pan_number, pan_name, pan_dob, date_of_birth,
   current_salary_usd, profile_photo_path, profile_photo_mime.
4. Always add LIMIT {row_limit} unless the user explicitly asks for all rows.
5. Return ONLY the SQL query. No explanation. No markdown fences. No comments.
6. If the question cannot be answered with a safe SELECT query, respond with exactly:
   CANNOT_ANSWER

{schema}

{role_filter}"""

SUMMARY_SYSTEM_PROMPT = """You are a helpful HR data assistant. 
Given a SQL query, the question it answered, and the resulting rows, 
write a concise 1-3 sentence natural language summary.
Do NOT mention SQL. Be direct and factual."""


async def answer_sql_question(
    question: str,
    current_user: Employee,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Translate a natural language question to SQL, execute it, and summarise results.

    Returns:
        {
            "answer": str,
            "sql": str | None,
            "rows": list[dict],
        }
    """
    if db_path is None:
        db_path = _db_path_from_url(settings.database_url)

    role_str = current_user.role.value
    role_filter = ROLE_FILTERS.get(role_str, ROLE_FILTERS["EMPLOYEE"]).format(
        user_id=current_user.id
    )

    system_prompt = SQL_SYSTEM_PROMPT.format(
        schema=SCHEMA_DESCRIPTION,
        role_filter=role_filter,
        row_limit=settings.ai_sql_row_limit,
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # ── Step 1: Generate SQL ──────────────────────────────────────────────────
    gen_response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.0,
        max_tokens=500,
    )

    raw_sql = (gen_response.choices[0].message.content or "").strip()
    # Strip markdown fences if LLM adds them
    raw_sql = raw_sql.removeprefix("```sql").removeprefix("```").removesuffix("```").strip()

    if raw_sql == "CANNOT_ANSWER" or not raw_sql:
        return {
            "answer": "I cannot generate a safe SQL query to answer this question.",
            "sql": None,
            "rows": [],
        }

    # ── Step 2: Validate ──────────────────────────────────────────────────────
    try:
        safe_sql = validate_and_sanitize_sql(
            raw_sql, row_limit=settings.ai_sql_row_limit
        )
    except SQLGuardrailError as exc:
        logger.warning("SQL guardrail blocked query: %s | SQL: %s", exc, raw_sql)
        return {
            "answer": f"I cannot execute that query: {exc}",
            "sql": None,
            "rows": [],
        }

    # ── Step 3: Execute ───────────────────────────────────────────────────────
    try:
        rows = await _execute_sql(safe_sql, db_path)
    except Exception as exc:
        logger.error("SQL execution error: %s | SQL: %s", exc, safe_sql)
        return {
            "answer": "The query ran into an error. Please rephrase your question.",
            "sql": safe_sql,
            "rows": [],
        }

    # Strip any forbidden columns from result rows (defence-in-depth)
    rows = strip_forbidden_columns_from_rows(rows)

    # ── Step 4: Summarise ─────────────────────────────────────────────────────
    summary = await _summarise_results(question, safe_sql, rows, client)

    return {
        "answer": summary,
        "sql": safe_sql,
        "rows": rows,
    }


async def _execute_sql(sql: str, db_path: str) -> List[Dict[str, Any]]:
    """Execute a validated SQL query against the SQLite database."""
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(sql) as cursor:
            raw_rows = await cursor.fetchall()
            return [dict(row) for row in raw_rows]


async def _summarise_results(
    question: str,
    sql: str,
    rows: List[Dict[str, Any]],
    client: AsyncOpenAI,
) -> str:
    """Generate a natural language summary of the query results."""
    if not rows:
        return "No results were found for your query."

    sample = rows[:10]  # limit to 10 rows for summary context
    rows_preview = "\n".join(str(r) for r in sample)
    if len(rows) > 10:
        rows_preview += f"\n... and {len(rows) - 10} more rows."

    user_content = (
        f"Question: {question}\n\n"
        f"SQL used: {sql}\n\n"
        f"Results ({len(rows)} rows):\n{rows_preview}"
    )

    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.0,
        max_tokens=250,
    )
    return response.choices[0].message.content or f"Found {len(rows)} result(s)."


def _db_path_from_url(database_url: str) -> str:
    """Extract the file path from a SQLite URL like sqlite+aiosqlite:///./storage/hrms.db."""
    # Remove the driver prefix
    url = database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    return url
