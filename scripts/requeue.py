"""Run inside edge container after fixing cloud config/schema; retain same event ID."""
import sys
from app.core.db import connect
if len(sys.argv) != 2:
    raise SystemExit('Usage: python scripts/requeue.py EVENT_UUID')
with connect() as db:
    result=db.execute('UPDATE events SET dead_letter=0,retry_at=0,attempts=0,last_error=NULL WHERE id=? AND synced=0',(sys.argv[1],))
    print('Requeued',result.rowcount)
