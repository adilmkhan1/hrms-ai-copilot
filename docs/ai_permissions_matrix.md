# AI Permissions Matrix

The AI assistant enforces the same role model as the existing HRMS application.
No AI action can bypass this matrix.

## Roles

| Role | Description |
|---|---|
| `EMPLOYEE` | Regular employee — can only access own data |
| `MANAGER` | Team manager — can access team data and approve requests |
| `ADMIN` | HR/system admin — broad access (forbidden fields still blocked) |

## AI Permissions by Action

| AI Capability | EMPLOYEE | MANAGER | ADMIN |
|---|:---:|:---:|:---:|
| **Policy RAG** | ||||
| Ask HR policy questions | ✅ | ✅ | ✅ |
| **SQL Agent** | ||||
| Query own employee record | ✅ | ✅ | ✅ |
| Query own leave balance | ✅ | ✅ | ✅ |
| Query own project assignments | ✅ | ✅ | ✅ |
| Query team/all employees | ❌ | ✅ | ✅ |
| Query all project assignments | ❌ | ✅ | ✅ |
| Query salary data | ❌ | ❌ | ✅ |
| Query bank/PAN details | ❌ | ❌ | ❌ |
| **HR Action Agent** | ||||
| View own leave balance | ✅ | ✅ | ✅ |
| Create leave request | ✅ | ✅ | ✅ |
| Approve/reject leave | ❌ | ✅ | ✅ |
| View pending leave requests | ❌ | ✅ | ✅ |
| Create ticket | ✅ | ✅ | ✅ |
| Assign/update ticket | ❌ | ✅ | ✅ |
| Create announcement | ❌ | ✅ | ✅ |
| Assign employee to project | ❌ | ✅ | ✅ |
| **Admin Features** | ||||
| Re-index HR policies | ❌ | ❌ | ✅ |
| View AI audit logs | ❌ | ❌ | ✅ |

## Always Forbidden (Regardless of Role)

The following fields are **never** exposed through the AI layer:

- `hashed_password`
- `bank_account_number`, `bank_account_name`, `bank_branch`, `bank_ifsc`
- `pan_number`, `pan_name`, `pan_dob`
- `date_of_birth`
- `current_salary_usd`
- `profile_photo_path`, `profile_photo_mime`

## Enforcement Points

1. **SQL Guardrails** (`sql_guardrails.py`) — blocks forbidden columns at AST level
2. **SQL Agent System Prompt** — role-based WHERE clauses injected
3. **AI Permissions** (`permissions.py`) — `require_permission()` called before every action
4. **Backend APIs** — existing endpoint RBAC remains the final enforcement layer
5. **Result Sanitization** — `strip_forbidden_columns_from_rows()` applied to all SQL results

## Good vs Bad Refusal Examples

**Good refusal (information does not leak):**
> "You do not have permission to view another employee's payroll information."

**Bad refusal (leaks existence of data):**
> ~~"I found the payroll record, but I cannot show it to you."~~
