"""create initial metadata and audit tables

Revision ID: 001_initial_metadata_schema
Revises: 
Create Date: 2026-10-15 17:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001_initial_metadata_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=100), nullable=False),
        sa.Column("caller_type", sa.String(length=50), nullable=False, server_default="web_ui"),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "session_contexts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("active_team_id", sa.String(length=100), nullable=True),
        sa.Column("active_service_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_session_contexts_session_id"), "session_contexts", ["session_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_session_contexts_session_id"), table_name="session_contexts")
    op.drop_table("session_contexts")
    op.drop_table("audit_logs")
