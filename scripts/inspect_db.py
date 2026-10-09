import json
import os
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()
if __name__=='__main__':
    with psycopg.connect(os.environ['DATABASE_URL'],row_factory=dict_row) as c:
        data={'version':c.execute('SELECT version() AS version').fetchone()['version']}
        data['migrations']=c.execute('SELECT version FROM schema_versions ORDER BY version').fetchall()
        data['duplicate_active_slots']=c.execute("SELECT slot_id,count(*) AS n FROM appointments WHERE status IN ('booked','completed') GROUP BY slot_id HAVING count(*)>1").fetchall()
        data['indexes']=c.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' ORDER BY indexname").fetchall()
        data['triggers']=c.execute("SELECT trigger_name FROM information_schema.triggers WHERE trigger_schema='public' ORDER BY trigger_name").fetchall()
        data['routines']=c.execute("SELECT routine_name,routine_type FROM information_schema.routines WHERE routine_schema='public' ORDER BY routine_name").fetchall()
        data['counts']=c.execute("SELECT (SELECT count(*) FROM users) AS users,(SELECT count(*) FROM pets) AS pets,(SELECT count(*) FROM appointment_slots) AS slots,(SELECT count(*) FROM audit_logs) AS audit_events").fetchone()
    assert not data['duplicate_active_slots']
    Path('artifacts/database-verification.json').write_text(json.dumps(data,indent=2))
    print(data['version']);print('Migrations:',data['migrations']);print('No duplicate active slots; database objects recorded.')
