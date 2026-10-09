# Advanced DBMS evaluation

Run from the Windows project root with the local server running:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify
```

This runs real PostgreSQL tests in an isolated random schema on `paw_test`, asserts 100 concurrent API attempts yield exactly one HTTP 201 and 99 HTTP 409 responses, checks one active booking and one successful booking audit, runs transaction schedules, and benchmarks 200,000 rows. Application records are preserved. Evidence: `artifacts/pytest.xml`, `artifacts/dbms-demo.json`, `artifacts/benchmark.json`.

For a live socket-based race against the running API, choose a fresh available slot and a pet owned by the supplied account:

```powershell
.\.venv\Scripts\python.exe -m scripts.load_test --email owner@paw.local --pet 1 --slot 1
```

The password is requested without echo. This creates one real appointment and saves HTTP results. Reusing a booked slot should produce 100 conflicts; it is not a valid first-booking demonstration. Cancel the winning visit to release it. API docs at `http://127.0.0.1:8000/docs` show IDs and requests.

Connect to SQL without placing the password on the command line:

```powershell
.\.tools\pgsql\bin\psql.exe -h 127.0.0.1 -p 55432 -U paw -d paw_protectors
```

Enter the cluster password from the private `.env`, not the application login password.

## Schema, functions, triggers, indexes and views

```sql
\dt
\df book_appointment
\df acknowledge_reminder
\d appointments
\d vaccination_records
SELECT * FROM available_slots LIMIT 5;
SELECT * FROM appointment_details ORDER BY id DESC LIMIT 5;
SELECT entity,action,actor_id,transaction_id,created_at FROM audit_logs ORDER BY id DESC LIMIT 10;
SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public';
```

`book_appointment` uses `SELECT ... FOR UPDATE` on the slot; the partial unique index `one_active_booking_per_slot` prevents duplicate booked/completed visits. API booking and audit are in one ACID transaction. The composite foreign key requires the appointment owner to match the pet owner. Vaccination inserts/updates trigger reminder creation. Functions and triggers are in `database/001_schema.sql`.

## Commit and rollback

```sql
BEGIN;
UPDATE pets SET medical_notes='Rollback demonstration' WHERE id=1;
SELECT medical_notes FROM pets WHERE id=1;
ROLLBACK;
SELECT medical_notes FROM pets WHERE id=1;
BEGIN;
UPDATE pets SET medical_notes=medical_notes WHERE id=1;
COMMIT;
```

The first change and its audit insert disappear together; the second transaction commits. Sequences can have gaps after rollback, which is expected.

## READ COMMITTED (two psql sessions)

Session A:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT medical_notes FROM pets WHERE id=1;
```

Session B:

```sql
BEGIN;
UPDATE pets SET medical_notes='Committed by session B' WHERE id=1;
COMMIT;
```

Session A repeats the SELECT and sees B's committed value, then `ROLLBACK`. The automated schedule uses a disposable balance table and asserts 100→101.

## SERIALIZABLE, row lock contention, deadlock recovery

```powershell
.\.venv\Scripts\python.exe -m scripts.dbms_demo
```

The script controls two independent PostgreSQL connections using barriers/events:

1. Rollback leaves the original balance 100.
2. READ COMMITTED allows successive statement snapshots to see 100 then 101.
3. Two SERIALIZABLE transactions read the same predicate and update different rows. Exactly one commits; the other receives SQLSTATE 40001.
4. One connection holds a row lock; another waits at least 0.3 seconds until commit. Actual wait duration is recorded.
5. Opposite row acquisition creates an actual deadlock. PostgreSQL aborts one with 40P01; the victim is rolled back and retries after locking both rows in ascending ID order. Both logical operations eventually commit once, yielding balances `(1,103),(2,102)`.

To inspect locks during a manual test, hold `BEGIN; SELECT * FROM appointment_slots WHERE id=1 FOR UPDATE;` in one psql session and issue the same query in a second. A third session can run:

```sql
SELECT pid,wait_event_type,wait_event,pg_blocking_pids(pid),query
FROM pg_stat_activity WHERE datname=current_database();
```

Commit the first session and observe the second resume, then roll back the second.

## Optimization and actual EXPLAIN plans

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark --rows 200000
```

The script creates a disposable schema, generates synthetic clinical records, runs ANALYZE and seven repetitions of:

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT * FROM records WHERE pet_id=42 ORDER BY recorded_at DESC LIMIT 20;
CREATE INDEX benchmark_pet_time ON records(pet_id,recorded_at DESC);
ANALYZE records;
-- Repeat EXPLAIN after the index.
```

Both plans, all execution times and medians are saved. Compare sequential scan/sort to index access and buffer counts. These are warm-cache measurements in the same session, not cold-disk or general system throughput results. Do not replace measured numbers with estimates.

## Backup and restore

```powershell
.\.venv\Scripts\python.exe -m scripts.backup backup artifacts/faculty.dump
.\.tools\pgsql\bin\createdb.exe -h 127.0.0.1 -p 55432 -U paw paw_restore
.\.venv\Scripts\python.exe -m scripts.backup restore artifacts/faculty.dump --target-db paw_restore
.\.tools\pgsql\bin\psql.exe -h 127.0.0.1 -p 55432 -U paw -d paw_restore -c "SELECT count(*) FROM pets;"
```

The backup uses custom format; restore is a single transaction into a different empty database. Existing targets and existing backup files are refused. Uploads live outside PostgreSQL: back up `uploads/` separately if pet photos are needed. PostgreSQL credentials are passed through a subprocess environment, not command arguments.
