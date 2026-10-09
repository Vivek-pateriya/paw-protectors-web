import os
from contextlib import contextmanager
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

pool = None


def open_pool():
    global pool
    pool = ConnectionPool(os.environ['DATABASE_URL'], min_size=2, max_size=16,
                          timeout=20, kwargs={'row_factory': dict_row}, open=False)
    pool.open()
    pool.wait(timeout=15)


def close_pool():
    if pool:
        pool.close()


@contextmanager
def connection(actor_id=None):
    if pool is None:
        raise RuntimeError('Database pool not started')
    with pool.connection() as conn:
        with conn.transaction():
            conn.execute("SET LOCAL statement_timeout = '15s'")
            if actor_id is not None:
                conn.execute("SELECT set_config('app.actor_id', %s, true)", (str(actor_id),))
            yield conn
