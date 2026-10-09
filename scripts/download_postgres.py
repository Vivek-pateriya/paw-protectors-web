from pathlib import Path
import urllib.request
import zipfile

root=Path(__file__).resolve().parents[1]/'.tools'
root.mkdir(exist_ok=True)
archive=root/'postgres-archive.zip'
if not (root/'pgsql/share/postgres.bki').exists():
    print('Downloading project-local PostgreSQL',flush=True)
    existing=root/'postgresql.zip'
    if existing.exists() and zipfile.is_zipfile(existing):
        archive=existing
    else:
        with urllib.request.urlopen('https://get.enterprisedb.com/postgresql/postgresql-17.11-3-windows-x64-binaries.zip',timeout=60) as source,archive.open('wb') as output:
            while chunk:=source.read(1024*1024):output.write(chunk)
    with zipfile.ZipFile(archive) as package:
        bad=package.testzip()
        if bad:raise RuntimeError('Archive CRC verification failed: '+bad)
        for member in package.infolist():
            if member.filename.startswith(('pgsql/bin/','pgsql/lib/','pgsql/share/')):package.extract(member,root)
    print('PostgreSQL binaries ready',flush=True)
