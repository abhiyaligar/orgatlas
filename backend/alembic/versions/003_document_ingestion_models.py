"""add document, extraction, slack message and document ingest job tables

Revision ID: 003_document_ingestion_models
Revises: 002_repository_ingestion_models

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_document_ingestion_models"
down_revision: Union[str, None] = "002_repository_ingestion_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("uri", sa.String(length=1000), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("source_at", sa.DateTime(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_kind", "documents", ["kind"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])

    op.create_table(
        "document_extractions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("input_sha", sa.String(length=64), nullable=True),
        sa.Column("trigger", sa.String(length=50), nullable=True),
        sa.Column("usage", sa.Text(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_extractions_document_id", "document_extractions", ["document_id"]
    )

    op.create_table(
        "slack_messages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("channel_id", sa.String(length=64), nullable=False),
        sa.Column("channel_name", sa.String(length=200), nullable=True),
        sa.Column("slack_user_id", sa.String(length=64), nullable=True),
        sa.Column("author", sa.String(length=200), nullable=True),
        sa.Column("posted_at", sa.DateTime(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("permalink", sa.String(length=1000), nullable=True),
        sa.Column("thread_ts", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_slack_messages_channel_id", "slack_messages", ["channel_id"])
    op.create_index("ix_slack_messages_slack_user_id", "slack_messages", ["slack_user_id"])

    op.create_table(
        "document_ingest_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("stage_detail", sa.String(length=500), nullable=True),
        sa.Column("documents_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decisions_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("entities_linked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_ingest_jobs_status", "document_ingest_jobs", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_document_ingest_jobs_status", table_name="document_ingest_jobs")
    op.drop_table("document_ingest_jobs")

    op.drop_index("ix_slack_messages_slack_user_id", table_name="slack_messages")
    op.drop_index("ix_slack_messages_channel_id", table_name="slack_messages")
    op.drop_table("slack_messages")

    op.drop_index("ix_document_extractions_document_id", table_name="document_extractions")
    op.drop_table("document_extractions")

    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_index("ix_documents_kind", table_name="documents")
    op.drop_table("documents")