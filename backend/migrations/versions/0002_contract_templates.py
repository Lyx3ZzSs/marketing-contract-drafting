"""Persist uploaded Word originals and parsed template sections."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contract_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_file", sa.String(255), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("original", sa.LargeBinary(), nullable=False),
        sa.Column("sections", postgresql.JSONB(), nullable=False),
        sa.Column("section_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("contract_templates")
