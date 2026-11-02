"""Dispatch jobs from PostgreSQL instead of a Redis stream.

A job row becomes its own queue entry: it is dispatchable while it is queued and its
available_at has passed. Reserving pushes available_at forward, which reproduces the
visibility timeout that Redis consumer-group pending entries provided.

Revision ID: 0023_postgres_job_queue
Revises: 0022_annotation_title
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_postgres_job_queue"
down_revision = "0022_annotation_title"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # Jobs queued before this migration keep their original dispatch order.
    op.execute("UPDATE jobs SET available_at = created_at WHERE status = 'queued'")
    # Partial index: dispatch stays cheap however large the finished-job history grows.
    op.create_index(
        "ix_jobs_dispatch",
        "jobs",
        ["available_at", "created_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_dispatch", table_name="jobs")
    op.drop_column("jobs", "available_at")
