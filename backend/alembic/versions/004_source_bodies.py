"""add the source body pointer table

The graph holds the address of a file body; object storage holds the body. This
table is the link between them, and it is the only place that link exists.

Content is addressed by digest, so the unique key is on ``(repository_id,
path, commit_sha)``: re-ingesting the same commit at the same path updates one
row rather than accumulating history. A *different* commit that happens to hold
identical bytes points at the same ``content_sha256``, so an unchanged file
across many commits costs one stored object and a few rows.

The relationship to the graph is deliberately one-directional. This table knows
nothing about nodes or edges, and nothing in the graph knows whether a body is
present -- a retrieval tool resolves the graph address first and consults this
table second, which is why a missing blob is a reportable fact rather than a
dangling edge.

Revision ID: 004_source_bodies
Revises: 003_document_ingestion_models
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_source_bodies"
down_revision: Union[str, None] = "003_document_ingestion_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_bodies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # The graph node id of the file, i.e. "{repository_id}::{path}".
        sa.Column("file_id", sa.String(length=1000), nullable=False),
        sa.Column("repository_id", sa.String(length=200), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        # The commit the bytes were read at. Pins retrieval to the revision the
        # graph describes, so a description cannot be read against later code.
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=300), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stored_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "repository_id", "path", "commit_sha", name="uq_source_bodies_revision"
        ),
    )
    # Retrieval resolves by file id, which is how a graph address is turned
    # into bytes.
    op.create_index("ix_source_bodies_file_id", "source_bodies", ["file_id"])
    # Re-ingest skips content it already holds.
    op.create_index(
        "ix_source_bodies_content_sha256", "source_bodies", ["content_sha256"]
    )


def downgrade() -> None:
    op.drop_index("ix_source_bodies_content_sha256", table_name="source_bodies")
    op.drop_index("ix_source_bodies_file_id", table_name="source_bodies")
    op.drop_table("source_bodies")