"""Template cover configuration and confirmed station names."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contract_templates", sa.Column("cover_config", postgresql.JSONB(), nullable=True)
    )
    # Only the user-confirmed original gets this configuration. Other files remain unconfigured.
    op.execute(
        sa.text("""
        UPDATE contract_templates SET cover_config =
        '{"station_suffix":"风电站","product_line":"风电场功率预测系统V1.0","document_line":"采购合同"}'::jsonb
        WHERE source_sha256 = '094d95c7471ba6295ca7f0d41fe587518c37d584c410eb398846cd17d62463f8'
    """)
    )
    op.create_table(
        "station_aliases",
        sa.Column("station_code", sa.String(255), primary_key=True),
        sa.Column("source_names", postgresql.JSONB(), nullable=False),
        sa.Column("short_name", sa.String(255), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "confirmed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("station_aliases")
    op.drop_column("contract_templates", "cover_config")
