"""Frozen initial V1 schema; independent from future application models."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    def key():
        return sa.Column("id", sa.String(36), primary_key=True)
    def user():
        return sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True)
    def col(name, kind, nullable=False):
        return sa.Column(name, kind, nullable=nullable)
    # Timestamps are stored as UTC without an SQL timezone modifier, matching UTCDateTime.
    op.create_table("users", key(), col("username", sa.String(80)), col("password_hash", sa.Text()), col("timezone", sa.String(64)), sa.UniqueConstraint("username"))
    op.create_table("connectors", key(), user(), col("base_url", sa.Text()), col("encrypted_token", sa.Text()), col("enabled", sa.Boolean()), col("last_synced_at", sa.DateTime(), True), col("error", sa.Text(), True))
    op.create_table("courses", key(), user(), col("connector_id", sa.String(36)), col("external_id", sa.String(100)), col("name", sa.String(512)),
                    sa.ForeignKeyConstraint(["connector_id"], ["connectors.id"]), sa.UniqueConstraint("user_id", "connector_id", "external_id"))
    op.create_table("raw_information", key(), user(), col("platform", sa.String(32)), col("source_type", sa.String(32)), col("external_id", sa.String(512), True),
                    col("channel_name", sa.String(512)), col("title", sa.Text()), col("content", sa.Text()), col("structured_data", sa.JSON()), col("fingerprint", sa.String(64)),
                    col("source_updated_at", sa.DateTime(), True), col("received_at", sa.DateTime(), True), col("status", sa.String(32)), col("error", sa.Text(), True), sa.UniqueConstraint("fingerprint"))
    op.create_table("extraction_results", key(), col("raw_id", sa.String(36)), col("decision", sa.JSON()), col("engine", sa.String(40)), col("status", sa.String(32)),
                    sa.ForeignKeyConstraint(["raw_id"], ["raw_information.id"]), sa.UniqueConstraint("raw_id"))
    op.create_table("tasks", key(), user(), col("title", sa.String(512)), col("course", sa.String(512)), col("description", sa.Text()), col("deadline", sa.DateTime(), True),
                    col("estimated_duration", sa.Integer()), col("remaining_duration", sa.Integer()), col("priority", sa.Integer()), col("splittable", sa.Boolean()), col("status", sa.String(32)),
                    col("deadline_locked", sa.Boolean()), col("duration_locked", sa.Boolean()), col("created_at", sa.DateTime(), True), col("updated_at", sa.DateTime(), True))
    op.create_table("task_sources", key(), col("task_id", sa.String(36)), col("raw_information_id", sa.String(36)), col("relation", sa.String(32)),
                    sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]), sa.ForeignKeyConstraint(["raw_information_id"], ["raw_information.id"]), sa.UniqueConstraint("task_id", "raw_information_id"))
    op.create_index("ix_task_sources_task_id", "task_sources", ["task_id"])
    op.create_table("events", key(), user(), col("title", sa.String(512)), col("start_at", sa.DateTime(), True), col("end_at", sa.DateTime(), True), col("event_type", sa.String(32)), col("status", sa.String(32)),
                    col("source_raw_id", sa.String(36), True), sa.ForeignKeyConstraint(["source_raw_id"], ["raw_information.id"]))
    op.create_table("schedule_blocks", key(), user(), col("task_id", sa.String(36)), col("start_at", sa.DateTime(), True), col("end_at", sa.DateTime(), True), col("locked", sa.Boolean()), col("version", sa.Integer()),
                    sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]))
    op.create_table("schedule_versions", key(), user(), col("version", sa.Integer()), col("trigger", sa.String(100)), col("status", sa.String(32)), col("risks", sa.JSON()), col("snapshot", sa.JSON()), col("created_at", sa.DateTime(), True), sa.UniqueConstraint("user_id", "version"))


def downgrade():
    for table in ("schedule_versions", "schedule_blocks", "events", "task_sources", "tasks", "extraction_results", "raw_information", "courses", "connectors", "users"):
        op.drop_table(table)
