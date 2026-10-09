"""Round-trip verification into a newly created disposable database."""
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from dotenv import load_dotenv

load_dotenv()
if __name__=='__main__':
    url=os.environ['DATABASE_URL'];name='paw_restore_test_'+uuid4().hex
    archive=Path('artifacts')/(name+'.dump')
    admin=make_conninfo(url,dbname='postgres')
    with psycopg.connect(admin,autocommit=True) as c:
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    try:
        subprocess.run([sys.executable,'-m','scripts.backup','backup',str(archive)],check=True)
        subprocess.run([sys.executable,'-m','scripts.backup','restore',str(archive),'--target-db',name],check=True)
        counts={}
        with psycopg.connect(url) as source,psycopg.connect(make_conninfo(url,dbname=name)) as target:
            for table in ['users','pets','veterinarians','appointment_slots','appointments','medical_records','vaccination_records','reminders','audit_logs','schema_versions','revoked_sessions']:
                query=sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))
                a,b=source.execute(query).fetchone()[0],target.execute(query).fetchone()[0]
                assert a==b,(table,a,b);counts[table]={'source':a,'restored':b}
        Path('artifacts/backup-restore.json').write_text(json.dumps({'status':'passed','counts':counts},indent=2))
        print('PASS: backup and restore row counts match for all',len(counts),'tables')
    finally:
        with psycopg.connect(admin,autocommit=True) as c:
            c.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
