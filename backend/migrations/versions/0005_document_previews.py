"""Short-lived full-document preview artifacts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_previews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("title", sa.String(2000), nullable=False),
        sa.Column("source_docx", sa.LargeBinary(), nullable=True),
        sa.Column("storage_backend", sa.String(10), nullable=False),
        sa.Column("file_key", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_document_previews_fingerprint", "document_previews", ["fingerprint"])
    op.create_index("ix_document_previews_expires_at", "document_previews", ["expires_at"])


def downgrade() -> None:
    op.drop_table("document_previews")
