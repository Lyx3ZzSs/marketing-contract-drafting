"""Per-template yellow-field editing settings; original bytes remain immutable."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contract_templates", sa.Column("field_bindings", postgresql.JSONB(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("contract_templates", "field_bindings")
