"""Copy an explicit private backup into an EMPTY Render database and Cloudinary.

Credentials are read from a private env file, never command arguments or output.
Existing local data is never changed. Restore refuses any occupied destination.
"""
import argparse
import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from dotenv import dotenv_values


def run(args):
    backup = args.backup_dir.resolve()
    manifest = json.loads((backup / 'manifest.json').read_text())
    credentials = dotenv_values(args.credentials)
    if args.action == 'photos':
        if not credentials.get('CLOUDINARY_URL'):
            raise RuntimeError('Fill CLOUDINARY_URL in the private credentials file first')
        os.environ.update(PHOTO_STORAGE='cloudinary', CLOUDINARY_URL=credentials['CLOUDINARY_URL'])
        from backend.photos import save_image, cloud_image_bytes
        checkpoint = backup / 'cloudinary-migration.json'
        done = json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
        with tarfile.open(backup / 'photos.tar.gz', 'r:gz') as archive:
            for filename, expected in manifest['photos'].items():
                if done.get(filename) == expected:
                    continue
                member = archive.getmember(filename)
                if not member.isfile() or member.size > 5 * 1024 * 1024:
                    raise RuntimeError('Invalid photo backup member')
                content = archive.extractfile(member).read()
                if hashlib.sha256(content).hexdigest() != expected:
                    raise RuntimeError('Photo backup integrity check failed')
                save_image(content, Path(filename).suffix, filename=filename)
                if hashlib.sha256(cloud_image_bytes(filename)).hexdigest() != expected:
                    raise RuntimeError('Cloud photo verification failed; database was not changed')
                done[filename] = expected
                checkpoint.write_text(json.dumps(done, indent=2))
                print(f'Verified cloud photo {len(done)}/{len(manifest["photos"])}', flush=True)
        print('Photo copy complete; database filenames remain unchanged.')
        return
    target = credentials.get('DEST_DATABASE_URL')
    if not target:
        raise RuntimeError('Fill DEST_DATABASE_URL in the private credentials file first')
    params = conninfo_to_dict(target)
    if not params.get('host', '').endswith('.render.com'):
        raise RuntimeError('Destination must be an external Render PostgreSQL host')
    params['sslmode'] = 'require'
    params['connect_timeout'] = '15'
    target = make_conninfo(**params)
    def verify():
        with psycopg.connect(target) as conn:
            actual = {r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
            if actual != set(manifest['tables']):
                raise RuntimeError('Restored table inventory differs from backup')
            for table, expected in manifest['tables'].items():
                count = conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0]
                if count != expected:
                    raise RuntimeError('Restored row count differs for ' + table)
        print(f'Verified {len(manifest["tables"])} tables and {sum(manifest["tables"].values())} restored rows.')
    if args.action == 'verify':
        verify()
        return
    with psycopg.connect(target) as conn:
        count = conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]
        if count:
            raise RuntimeError('Destination is not empty. No existing records will be overwritten. Use verify for a completed restore.')
    checkpoint = backup / 'cloudinary-migration.json'
    if not checkpoint.exists() or json.loads(checkpoint.read_text()) != manifest['photos']:
        raise RuntimeError('Copy and verify all photos before restoring the database')
    env = {**os.environ, 'PGHOST': params['host'], 'PGPORT': params.get('port', '5432'),
           'PGDATABASE': params['dbname'], 'PGUSER': params['user'], 'PGPASSWORD': params.get('password', ''),
           'PGSSLMODE': 'require', 'PGCONNECT_TIMEOUT': '15'}
    binary = args.postgres_bin / ('pg_restore.exe' if os.name == 'nt' else 'pg_restore')
    restored = subprocess.run([str(binary), '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges', '--dbname', params['dbname'], str(backup / 'database.dump')], env=env, capture_output=True)
    if restored.returncode:
        raise RuntimeError('Database restore failed and was rolled back. Check connectivity and PostgreSQL tool compatibility; credentials have not been logged.')
    verify()
    (backup / 'render-restore.json').write_text(json.dumps({'status': 'verified', 'host': params['host'], 'database': params['dbname'], 'tables': manifest['tables']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['photos', 'database', 'verify'])
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--credentials', type=Path, required=True)
    parser.add_argument('--postgres-bin', type=Path, default=Path('.tools/pgsql/bin'))
    args = parser.parse_args()
    try:
        run(args)
    except Exception as error:
        # Provider and database exceptions may contain passwords or signed URLs.
        if isinstance(error, RuntimeError):
            raise SystemExit(str(error)) from None
        raise SystemExit('Migration could not complete. Local data is unchanged; no private provider or database error details were printed.') from None
