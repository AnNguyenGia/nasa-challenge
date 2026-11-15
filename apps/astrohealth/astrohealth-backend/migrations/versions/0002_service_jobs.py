"""Durable inter-process worker jobs."""

from alembic import op

from app.core import jobs

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    jobs.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade disabled")
