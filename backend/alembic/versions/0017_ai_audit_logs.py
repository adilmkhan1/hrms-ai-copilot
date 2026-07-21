"""Alembic migration: add ai_audit_logs table (Phase-4 AI)."""

from alembic import op
import sqlalchemy as sa


revision = "0017_ai_audit_logs"
down_revision = "0016_employee_documents_uploaded_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=50), nullable=True),
        sa.Column("tool_name", sa.String(length=100), nullable=True),
        sa.Column("action_status", sa.String(length=30), nullable=True),
        sa.Column("records_accessed", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_audit_logs_id"), "ai_audit_logs", ["id"], unique=False)
    op.create_index(op.f("ix_ai_audit_logs_user_id"), "ai_audit_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_audit_logs_user_id"), table_name="ai_audit_logs")
    op.drop_index(op.f("ix_ai_audit_logs_id"), table_name="ai_audit_logs")
    op.drop_table("ai_audit_logs")
