"""Local PostgreSQL cluster; no Windows service, registry or firewall changes."""
import os
import secrets
import subprocess
from pathlib import Path
import psycopg
from psycopg import sql

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/'.tools'/'pgsql'/'bin'
DATA=ROOT/'.pgdata'


def run(*args):
    subprocess.run([str(BIN/args[0]),*args[1:]],check=True,cwd=ROOT)


def start():
    if not (BIN/'initdb.exe').is_file():
        raise SystemExit('Run scripts/download_postgres.ps1 first')
    if not (DATA/'PG_VERSION').exists():
        if (ROOT/'.env').exists():
            raise SystemExit('Existing .env preserved. Use scripts.init_db with your configured database, or explicitly configure a separate local cluster.')
        password=secrets.token_urlsafe(32)
        passfile=ROOT/'.pgpass'; passfile.write_text(password,encoding='utf-8')
        try:
            run('initdb.exe','-D',str(DATA),'-U','paw','--auth=scram-sha-256','--pwfile',str(passfile),'--encoding=UTF8','--locale=C')
        finally:
            passfile.unlink(missing_ok=True)
        with (DATA/'postgresql.conf').open('a') as out:
            out.write("\nlisten_addresses = '127.0.0.1'\nport = 55432\nmax_connections = 140\nshared_buffers = '128MB'\n")
        env=ROOT/'.env'
        env.write_text(f'DATABASE_URL=postgresql://paw:{password}@127.0.0.1:55432/paw_protectors\nTOKEN_SECRET={secrets.token_hex(32)}\nUPLOAD_DIR=uploads\n')
    status=subprocess.run([str(BIN/'pg_ctl.exe'),'-D',str(DATA),'status'],capture_output=True)
    if status.returncode:
        run('pg_ctl.exe','-D',str(DATA),'-l',str(ROOT/'artifacts'/'postgres.log'),'-w','start')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    from psycopg.conninfo import conninfo_to_dict,make_conninfo
    params=conninfo_to_dict(os.environ['DATABASE_URL']); params['dbname']='postgres'
    with psycopg.connect(make_conninfo(**params),autocommit=True) as conn:
        for name in ('paw_protectors','paw_test'):
            if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
                conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    print('Local PostgreSQL ready on 127.0.0.1:55432; credentials kept in .env')


if __name__=='__main__':
    (ROOT/'artifacts').mkdir(exist_ok=True)
    start()
