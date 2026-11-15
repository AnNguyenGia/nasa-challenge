"""Mark demonstration crew without deleting existing records."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(crew_members)")}
    if "is_demo" not in columns:
        conn.exec_driver_sql("ALTER TABLE crew_members ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
    for name, callsign in [
        ("Nguyễn Minh Quân", "CDR"),
        ("Linh Nguyễn", "PLT"),
        ("Minh Trần", "MED"),
        ("An Phạm", "ENG"),
        ("Hà Lê", "SCI"),
        ("Duy Hoàng", "MSP"),
    ]:
        conn.exec_driver_sql(
            "UPDATE crew_members SET is_demo=1 WHERE mission_id=? AND name=? AND callsign=?",
            ("ORBITAL-03", name, callsign),
        )
    conn.exec_driver_sql("UPDATE crew_members SET is_demo=1 WHERE mission_id='LOCAL-DEMO'")


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade disabled")
