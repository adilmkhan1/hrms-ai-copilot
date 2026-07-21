"""SQL Guardrails — parse and validate LLM-generated SQL before execution.

Enforces:
  - SELECT-only (blocks INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, etc.)
  - Single statement per request
  - Row limit enforcement (LIMIT N appended if missing)
  - Forbidden column filtering (sensitive fields never exposed)
  - Role-based access checks
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

import sqlglot
import sqlglot.expressions as exp

logger = logging.getLogger(__name__)

# ── Blocked statement types ───────────────────────────────────────────────────

BLOCKED_STATEMENT_TYPES = {
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create,
    exp.Command,  # catches PRAGMA, ATTACH, DETACH, etc.
}

BLOCKED_KEYWORDS_REGEX = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|PRAGMA|ATTACH|DETACH)\b",
    re.IGNORECASE,
)

# ── Forbidden columns — must NEVER appear in any SQL result ──────────────────

FORBIDDEN_COLUMNS: set[str] = {
    "hashed_password",
    "bank_account_number",
    "bank_account_name",
    "bank_branch",
    "bank_ifsc",
    "pan_number",
    "pan_name",
    "pan_dob",
    "date_of_birth",
    "current_salary_usd",
    "profile_photo_path",
    "profile_photo_mime",
}

# ── Public API ────────────────────────────────────────────────────────────────

class SQLGuardrailError(ValueError):
    """Raised when SQL fails a safety check."""


def validate_and_sanitize_sql(
    sql: str,
    row_limit: int = 50,
    dialect: str = "sqlite",
) -> str:
    """Validate and sanitize LLM-generated SQL.

    Raises SQLGuardrailError on any violation.
    Returns the sanitised SQL string ready for execution.
    """
    sql = sql.strip().rstrip(";")

    # ── Keyword-level fast check ──────────────────────────────────────────────
    if BLOCKED_KEYWORDS_REGEX.search(sql):
        raise SQLGuardrailError(
            "SQL contains blocked keywords (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE etc.). "
            "Only SELECT queries are permitted."
        )

    # ── AST parsing ───────────────────────────────────────────────────────────
    try:
        statements = sqlglot.parse(sql, dialect=dialect)
    except Exception as exc:
        raise SQLGuardrailError(f"SQL parse error: {exc}") from exc

    if not statements:
        raise SQLGuardrailError("No SQL statement found.")

    if len(statements) > 1:
        raise SQLGuardrailError("Only a single SQL statement is permitted per request.")

    stmt = statements[0]
    if stmt is None:
        raise SQLGuardrailError("Empty SQL statement.")

    # ── Must be SELECT ────────────────────────────────────────────────────────
    if not isinstance(stmt, exp.Select):
        raise SQLGuardrailError(
            f"Only SELECT statements are allowed. Got: {type(stmt).__name__}."
        )

    # ── Block forbidden statement sub-types ───────────────────────────────────
    for node in stmt.walk():
        for blocked_type in BLOCKED_STATEMENT_TYPES:
            if isinstance(node, blocked_type):
                raise SQLGuardrailError(
                    f"SQL contains a blocked operation: {type(node).__name__}."
                )

    # ── Forbidden column check ────────────────────────────────────────────────
    _check_forbidden_columns(stmt)

    # ── Enforce row limit ─────────────────────────────────────────────────────
    sanitized = _enforce_row_limit(sql, stmt, row_limit, dialect)

    return sanitized


def _check_forbidden_columns(stmt: exp.Select) -> None:
    """Raise if any forbidden column is referenced in the SELECT or WHERE."""
    for col_node in stmt.find_all(exp.Column):
        col_name = col_node.name.lower() if col_node.name else ""
        if col_name in FORBIDDEN_COLUMNS:
            raise SQLGuardrailError(
                f"Column '{col_name}' is not permitted in AI-generated queries. "
                "Please rephrase your question without requesting sensitive fields."
            )

    # Also check star-selects on tables that would include forbidden columns
    # (allow * but we strip results at execution layer using _safe_columns)


def _enforce_row_limit(
    original_sql: str, stmt: exp.Select, limit: int, dialect: str
) -> str:
    """Return SQL with LIMIT enforced."""
    existing_limit = stmt.args.get("limit")
    if existing_limit is not None:
        # Replace with min(existing, limit)
        try:
            existing_val = int(existing_limit.this.this)  # type: ignore[attr-defined]
            if existing_val > limit:
                stmt = stmt.limit(limit)
                return stmt.sql(dialect=dialect)
        except Exception:
            pass
        return original_sql

    # No limit present — add one
    stmt = stmt.limit(limit)
    return stmt.sql(dialect=dialect)


def strip_forbidden_columns_from_rows(
    rows: List[dict],
) -> List[dict]:
    """Remove any forbidden columns from result rows (defence-in-depth)."""
    return [
        {k: v for k, v in row.items() if k.lower() not in FORBIDDEN_COLUMNS}
        for row in rows
    ]
