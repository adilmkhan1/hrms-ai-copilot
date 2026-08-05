# AI Architecture — HR Operations Copilot

## Overview

The AI layer is integrated into the existing CB Nest HRMS stack. It adds four major capabilities — Policy RAG, SQL Agent, HR Task Automation, and Role-Based AI Permissions — without modifying any existing business logic.

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        NEXT.JS FRONTEND                          │
│     /ai-copilot — 3-tab AI Copilot page (Policy / SQL / Actions)│
│     chat-panel.tsx | source-list.tsx | sql-result-table.tsx      │
│     action-result-card.tsx                                       │
└──────────────────────────────┬───────────────────────────────────┘
                               │  JWT-authenticated API calls
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND                           │
│  POST /api/v1/chat/policy   → Policy RAG Assistant               │
│  POST /api/v1/chat/sql      → SQL Agent                          │
│  POST /api/v1/chat/actions  → HR Task Automation Agent           │
│  POST /api/v1/chat/router   → Unified intent router              │
│  POST /api/v1/chat/policy/reindex → (Admin) re-index policies    │
│  GET  /api/v1/chat/audit-logs     → (Admin) view audit trail     │
└────────────────────┬──────────────────────┬──────────────────────┘
                     │                      │
         ┌───────────▼──────────┐   ┌───────▼───────────┐
         │  AUTH + PERMISSION   │   │  AI ORCHESTRATION  │
         │  - Decode JWT        │   │  - router_agent.py │
         │  - Role: ADM/MGR/EMP │   │  - policy_rag.py   │
         │  - AI permissions    │   │  - sql_agent.py    │
         └──────────────────────┘   │  - action_agent.py │
                                    └────────┬───────────┘
                          ┌──────────────────┼────────────────┐
                          ▼                  ▼                ▼
              ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐
              │   CHROMA DB     │  │  SQLITE DB   │  │  BACKEND APIs  │
              │  (policy chunks)│  │  (HRMS data) │  │  (tool calls)  │
              └─────────────────┘  └──────────────┘  └────────────────┘
```

## Component Details

### 1. Policy RAG (`services/ai/policy_rag.py`)

- Loads HR policy text from DB (`content` field) and disk (`.txt`, `.md`, `.pdf`)
- Chunks text into ~500-token segments with 50-token overlap
- Embeds chunks using OpenAI `text-embedding-3-small`
- Stores in ChromaDB (persistent, cosine similarity)
- At query time: retrieves top-5 chunks, builds grounded prompt, calls GPT-4o-mini
- **Guardrails**: refuse if context insufficient, never answer from model memory, treat retrieved text as data (prompt injection defence)

### 2. Embeddings (`services/ai/embeddings.py`)

- Wraps OpenAI Embeddings API
- Batch processing (100 texts per request)
- Model: `text-embedding-3-small` (fast, cost-effective)

### 3. Vector Store (`services/ai/vector_store.py`)

- ChromaDB PersistentClient at `./storage/chroma_db/`
- Collection: `hr_policies` (cosine distance space)
- Methods: `upsert_policy_chunks()`, `search(query, k)`
- Singleton instance shared across requests

### 4. SQL Agent (`services/ai/sql_agent.py`)

- Schema description injected into system prompt (with forbidden columns excluded)
- Role-based schema filters: EMPLOYEE sees only own data
- Generates SQL via GPT-4o-mini, validates via `sql_guardrails.py`, executes via `aiosqlite`
- Natural language summary of results

### 5. SQL Guardrails (`services/ai/sql_guardrails.py`)

- Fast keyword regex check: blocks INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/etc.
- AST parsing via `sqlglot`: validates statement type
- Forbidden column check: `hashed_password`, `bank_*`, `pan_*`, `current_salary_usd`, etc.
- Enforces `LIMIT N` if missing
- Defense-in-depth: strips forbidden columns from result rows

### 6. HR Action Agent (`services/ai/action_agent.py`)

- Intent classification → parameter extraction → permission check → API tool dispatch
- All mutations via `api_tools.py` (HTTP calls to existing backend endpoints)
- **Never writes to DB directly**
- Supported actions: create/approve/reject leave, create tickets, create announcements, assign to projects

### 7. API Tools (`services/ai/api_tools.py`)

- `httpx` async wrappers calling existing REST endpoints with the user's Bearer token
- Backend validation, business rules, and authorization remain the source of truth

### 8. Permissions (`services/ai/permissions.py`)

- AI permission matrix mapping `(role, action) → bool`
- Mirrors existing HRMS RBAC
- Raises `PermissionDeniedError` before any tool is called

### 9. AI Audit Log (`services/ai/audit.py` + `models/ai_audit_log.py`)

- Every AI interaction logged: user_id, role, message, intent, tool_name, status, records_accessed
- Never logs secrets, tokens, or sensitive fields

## Models & LLMs Used

| Component | Model |
|---|---|
| Chat / SQL / Actions | `gpt-4o-mini` (OpenAI) |
| Embeddings | `text-embedding-3-small` (OpenAI) |
| Vector DB | ChromaDB (local persistent) |

## Data Flow — Policy RAG

```
User question → POST /api/v1/chat/policy
  → embed question → search ChromaDB (top-5 chunks)
  → filter by distance threshold (< 0.6)
  → build grounded prompt → GPT-4o-mini
  → return {answer, sources} + log to ai_audit_logs
```

## Data Flow — SQL Agent

```
User question → POST /api/v1/chat/sql
  → inject schema + role filter into prompt → GPT-4o-mini generates SQL
  → sql_guardrails.validate_and_sanitize_sql()
  → aiosqlite.execute(safe_sql)
  → strip_forbidden_columns_from_rows()
  → GPT-4o-mini summarises rows
  → return {answer, sql, rows} + log
```

## Data Flow — HR Action Agent

```
User message → POST /api/v1/chat/actions
  → classify_intent() → GPT-4o-mini → intent label
  → require_permission(role, intent) → PermissionDeniedError if blocked
  → extract_params() → GPT-4o-mini → structured params
  → api_tools.xxx() → httpx → existing backend API
  → backend validates → DB write
  → return {intent, result, data, success} + log
```
