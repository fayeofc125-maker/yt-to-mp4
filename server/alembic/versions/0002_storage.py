"""Add durable result object metadata.

Revision ID: 0002_storage
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_storage"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobrecord", sa.Column("object_key", sa.String(), nullable=True))
    op.add_column("jobrecord", sa.Column("result_size", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobrecord", "result_size")
    op.drop_column("jobrecord", "object_key")
