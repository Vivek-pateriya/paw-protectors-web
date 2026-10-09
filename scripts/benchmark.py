"""Isolated 200k-row synthetic clinical dataset; retain actual plans and measurements."""
import argparse
import json
import os
import statistics
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql
from dotenv import load_dotenv

load_dotenv()


def run(rows=200000):
    url=os.environ['DATABASE_URL'];schema='bench_'+uuid4().hex
    with psycopg.connect(url,autocommit=True) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        c.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
        try:
            c.execute('CREATE TABLE records(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,pet_id bigint NOT NULL,recorded_at timestamptz NOT NULL,diagnosis text NOT NULL)')
            c.execute("INSERT INTO records(pet_id,recorded_at,diagnosis) SELECT (n %% 10000)+1, now()-(n || ' minutes')::interval,'Wellness examination ' || n FROM generate_series(1,%s)n",(rows,))
            c.execute('ANALYZE records')
            query='EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM records WHERE pet_id=42 ORDER BY recorded_at DESC LIMIT 20'
            def measure():
                plans=[c.execute(query).fetchone()[0][0] for _ in range(7)]
                return {'median_execution_ms':statistics.median(p['Execution Time'] for p in plans),'execution_ms':[p['Execution Time'] for p in plans],'plans':plans}
            before=measure()
            c.execute('CREATE INDEX benchmark_pet_time ON records(pet_id,recorded_at DESC)');c.execute('ANALYZE records')
            after=measure()
            result={'rows':rows,'repetitions':7,'cache_policy':'Repeated queries; warm cache; same session, before then after','before':before,'after':after}
        finally:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/benchmark.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('before','after')},indent=2))
    print('Median milliseconds: before=',before['median_execution_ms'],'after=',after['median_execution_ms'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--rows',type=int,default=200000)
    run(parser.parse_args().rows)
