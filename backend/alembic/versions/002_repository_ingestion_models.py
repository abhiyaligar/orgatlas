"""add schema version and ingest job tables

Revision ID: 002_repository_ingestion_models
Revises: 001_initial_metadata_schema

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_repository_ingestion_models"
down_revision: Union[str, None] = "001_initial_metadata_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("repository_url", sa.String(length=500), nullable=False),
        sa.Column("repository_id", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("stage_detail", sa.String(length=500), nullable=True),
        sa.Column("commits_ingested", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("files_indexed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("identities_resolved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sandbox_id", sa.String(length=200), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingest_jobs_status"), "ingest_jobs", ["status"], unique=False)
    op.create_table(
        "schema_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("component", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("schema_versions")
    op.drop_index(op.f("ix_ingest_jobs_status"), table_name="ingest_jobs")
    op.drop_table("ingest_jobs")