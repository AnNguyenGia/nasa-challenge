"""Initial durable schema; monthly measurement partitions are created by ingestion."""

from alembic import op

from app.core import metadata, now, partition

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())
    partition(op.get_bind(), now())


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade disabled; restore an approved backup instead")
