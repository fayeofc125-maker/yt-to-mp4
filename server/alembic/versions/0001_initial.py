"""create durable jobs"""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "jobrecord",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False, index=True),
        sa.Column("spec_json", sa.String(), nullable=False),
        sa.Column("client", sa.String(), nullable=False, index=True),
        sa.Column("work_dir", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, index=True),
        sa.Column("progress_phase", sa.String(), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("result_url", sa.String(), nullable=True),
        sa.Column("spec_metadata", sa.String(), nullable=False),
        sa.Column("cancellation_requested", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("jobrecord")
