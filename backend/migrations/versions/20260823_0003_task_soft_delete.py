"""Add reversible task deletion metadata."""

import sqlalchemy as sa
from alembic import op


revision = "20260823_0003"
down_revision = "20260822_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("tasks")}
    if "deleted_at" not in columns:
        op.add_column("tasks", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_tasks_deleted_at", "tasks", ["deleted_at"])
    if "deleted_by_id" not in columns:
        op.add_column("tasks", sa.Column("deleted_by_id", sa.String(length=36), nullable=True))
        op.create_foreign_key("fk_tasks_deleted_by_id_users", "tasks", "users", ["deleted_by_id"], ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("tasks")}
    if "deleted_by_id" in columns:
        op.drop_constraint("fk_tasks_deleted_by_id_users", "tasks", type_="foreignkey")
        op.drop_column("tasks", "deleted_by_id")
    if "deleted_at" in columns:
        op.drop_index("ix_tasks_deleted_at", table_name="tasks")
        op.drop_column("tasks", "deleted_at")
