"""Custom-format backup or non-destructive restore to an explicitly named empty DB."""
import argparse
import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import psycopg
from psycopg.conninfo import conninfo_to_dict,make_conninfo

load_dotenv()


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['backup','restore']);p.add_argument('file');p.add_argument('--target-db');p.add_argument('--bin',default='.tools/pgsql/bin');args=p.parse_args()
    params=conninfo_to_dict(os.environ['DATABASE_URL'])
    env=os.environ.copy();env['PGPASSWORD']=params.pop('password','')
    if args.action=='restore':
        if not args.target_db or args.target_db==params['dbname']:
            raise SystemExit('Restore requires a different --target-db, already created and empty')
        params['dbname']=args.target_db
        with psycopg.connect(make_conninfo(**params,password=env['PGPASSWORD'])) as c:
            if c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]:
                raise SystemExit('Target is not empty; no data overwritten')
    common=['--host',params.get('host','localhost'),'--port',params.get('port','5432'),'--username',params['user'],'--dbname',params['dbname']]
    if args.action=='backup':
        if Path(args.file).exists():raise SystemExit('Backup file already exists; choose a new filename')
        cmd=[str(Path(args.bin)/'pg_dump.exe'),*common,'--format=custom','--file',args.file]
    else:cmd=[str(Path(args.bin)/'pg_restore.exe'),*common,'--exit-on-error','--single-transaction','--no-owner',args.file]
    subprocess.run(cmd,env=env,check=True)
    print(args.action,'completed')


if __name__=='__main__':main()
