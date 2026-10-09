"""Deterministic real PostgreSQL transaction schedules, using a disposable schema."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from dotenv import load_dotenv

load_dotenv()


def run():
    url=os.environ['DATABASE_URL']; schema='demo_'+uuid4().hex
    result={}
    with psycopg.connect(url,autocommit=True) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        c.execute(sql.SQL('CREATE TABLE {}.balances(id int PRIMARY KEY,value int NOT NULL)').format(sql.Identifier(schema)))
        c.execute(sql.SQL('INSERT INTO {}.balances VALUES(1,100),(2,100)').format(sql.Identifier(schema)))
    scoped=make_conninfo(url,options=f'-c search_path={schema}')
    try:
        with psycopg.connect(scoped) as c:
            c.execute('UPDATE balances SET value=0 WHERE id=1'); c.rollback()
            value=c.execute('SELECT value FROM balances WHERE id=1').fetchone()[0]
            assert value==100; result['rollback']={'expected':100,'actual':value}
        with psycopg.connect(scoped) as a,psycopg.connect(scoped) as b:
            a.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
            first=a.execute('SELECT value FROM balances WHERE id=1').fetchone()[0]
            b.execute('UPDATE balances SET value=value+1 WHERE id=1');b.commit()
            second=a.execute('SELECT value FROM balances WHERE id=1').fetchone()[0]
            assert second==first+1;result['read_committed']={'first_read':first,'second_read':second}
        # Write skew: each sees two positive balances, then changes a different row.
        gate=Barrier(2)
        def serializable(row):
            try:
                with psycopg.connect(scoped) as c:
                    c.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE')
                    assert c.execute('SELECT count(*) FROM balances WHERE value>0').fetchone()[0]==2
                    gate.wait(timeout=10)
                    c.execute('UPDATE balances SET value=0 WHERE id=%s',(row,))
                return 'committed'
            except psycopg.errors.SerializationFailure:
                return '40001'
        with ThreadPoolExecutor(2) as workers:
            outcomes=list(workers.map(serializable,[1,2]))
        assert sorted(outcomes)==['40001','committed']; result['serializable']=outcomes
        with psycopg.connect(scoped) as c:
            c.execute('UPDATE balances SET value=100')
        # Hold one row lock and measure the wait in a second connection.
        started=Event()
        with psycopg.connect(scoped) as holder:
            holder.execute('SELECT * FROM balances WHERE id=1 FOR UPDATE')
            def contend():
                with psycopg.connect(scoped) as waiter:
                    started.set(); begin=time.perf_counter()
                    waiter.execute('UPDATE balances SET value=value+1 WHERE id=1')
                    return time.perf_counter()-begin
            with ThreadPoolExecutor(1) as workers:
                future=workers.submit(contend);assert started.wait(10)
                time.sleep(0.35);assert not future.done()
                holder.commit();elapsed=future.result(timeout=10)
        assert elapsed>=0.3;result['lock_wait_seconds']=elapsed
        # Opposite row order creates an actual cycle in PostgreSQL's lock graph.
        gate=Barrier(2)
        def deadlock(order):
            try:
                with psycopg.connect(scoped) as c:
                    c.execute("SET LOCAL lock_timeout='8s'")
                    c.execute('UPDATE balances SET value=value+1 WHERE id=%s',(order[0],))
                    gate.wait(timeout=10)
                    c.execute('UPDATE balances SET value=value+1 WHERE id=%s',(order[1],))
                return 'committed'
            except psycopg.errors.DeadlockDetected:
                # Context rolled back the entire victim transaction. Retry in consistent order.
                with psycopg.connect(scoped) as c:
                    c.execute('SELECT * FROM balances ORDER BY id FOR UPDATE')
                    c.execute('UPDATE balances SET value=value+1')
                return '40P01 recovered'
        with ThreadPoolExecutor(2) as workers:
            outcomes=list(workers.map(deadlock,[(1,2),(2,1)]))
        assert sorted(outcomes)==['40P01 recovered','committed']
        with psycopg.connect(scoped) as c:
            final=c.execute('SELECT id,value FROM balances ORDER BY id').fetchall()
        assert final==[(1,103),(2,102)],final
        result['deadlock']={'outcomes':outcomes,'final_balances':final}
    finally:
        with psycopg.connect(url,autocommit=True) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/dbms-demo.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2));return result


if __name__=='__main__':run()
