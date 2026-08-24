"""Add the task event query index."""

import sqlalchemy as sa
from alembic import op


revision = "20260824_0004"
down_revision = "20260823_0003"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_task_events_task_type_created"


def upgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("task_events")}
    if INDEX_NAME not in indexes:
        op.create_index(
            INDEX_NAME,
            "task_events",
            ["task_id", "event_type", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("task_events")}
    if INDEX_NAME in indexes:
        op.drop_index(INDEX_NAME, table_name="task_events")
