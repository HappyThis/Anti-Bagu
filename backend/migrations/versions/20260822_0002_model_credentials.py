"""Add encrypted per-user model credentials."""

import sqlalchemy as sa
from alembic import op


revision = "20260822_0002"
down_revision = "20260822_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("user_model_credentials"):
        return
    op.create_table(
        "user_model_credentials",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("user_model_credentials"):
        op.drop_table("user_model_credentials")
