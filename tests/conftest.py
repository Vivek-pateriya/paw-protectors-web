import os
from pathlib import Path
from uuid import uuid4
import pytest
import psycopg
from psycopg import sql


@pytest.fixture(scope='session')
def isolated_db():
    """Dedicated schema; never truncate the application's data."""
    url=os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL required for real PostgreSQL integration')
    schema='test_'+uuid4().hex
    with psycopg.connect(url,autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        for migration in sorted(Path('database').glob('[0-9][0-9][0-9]_*.sql')):
            conn.execute(migration.read_text())
    from psycopg.conninfo import make_conninfo
    isolated_url=make_conninfo(url,options=f'-c search_path={schema}')
    yield isolated_url
    with psycopg.connect(url,autocommit=True) as conn:
        conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
