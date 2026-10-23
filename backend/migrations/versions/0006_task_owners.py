"""Associate tasks and their preview artifacts with the authenticated OIDC subject."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("owner_sub", sa.String(255), nullable=True))
    op.create_index("ix_tasks_owner_sub", "tasks", ["owner_sub"])


def downgrade() -> None:
    op.drop_index("ix_tasks_owner_sub", table_name="tasks")
    op.drop_column("tasks", "owner_sub")
