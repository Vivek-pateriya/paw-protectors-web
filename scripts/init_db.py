"""Apply schema once and seed real accounts. Passwords are generated, never committed."""
import argparse
import os
import secrets
from pathlib import Path
import psycopg
from dotenv import load_dotenv
from backend.security import hash_password

load_dotenv()


def initialize(seed=True):
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        exists=conn.execute("SELECT to_regclass('public.schema_versions')").fetchone()[0]
        if not exists:
            conn.execute(Path('database/001_schema.sql').read_text(encoding='utf-8'))
        versions={row[0] for row in conn.execute('SELECT version FROM schema_versions')}
        for migration in sorted(Path('database').glob('[0-9][0-9][0-9]_*.sql')):
            version=int(migration.name.split('_')[0])
            if version not in versions:
                conn.execute(migration.read_text(encoding='utf-8'))
        if not seed:
            return
        if conn.execute('SELECT count(*) FROM users').fetchone()[0]:
            print('Existing users preserved; sample seed skipped.')
            return
        password=secrets.token_urlsafe(14)
        ids={}
        for name,email,role in [('Aarav Sharma','owner@paw.local','owner'),('Dr. Meera Rao','vet@paw.local','vet'),('Faculty Admin','admin@paw.local','admin')]:
            ids[role]=conn.execute('INSERT INTO users(name,email,password_hash,role) VALUES(%s,%s,%s,%s) RETURNING id',(name,email,hash_password(password),role)).fetchone()[0]
        vet=conn.execute("INSERT INTO veterinarians(user_id,specialization,clinic) VALUES(%s,'Small animal medicine','Paw Wellness Clinic') RETURNING id",(ids['vet'],)).fetchone()[0]
        pet=conn.execute("INSERT INTO pets(owner_id,name,species,breed,age_months,gender,medical_notes) VALUES(%s,'Bruno','Dog','Labrador',24,'male','Annual wellness check recommended') RETURNING id",(ids['owner'],)).fetchone()[0]
        conn.execute("INSERT INTO pets(owner_id,name,species,breed,age_months,gender) VALUES(%s,'Luna','Cat','Indian domestic',14,'female')",(ids['owner'],))
        conn.execute("INSERT INTO appointment_slots(veterinarian_id,starts_at,ends_at) SELECT %s, date_trunc('day',now()) + (n || ' days')::interval + interval '10 hours', date_trunc('day',now()) + (n || ' days')::interval + interval '10 hours 30 minutes' FROM generate_series(1,14) n",(vet,))
        conn.execute("INSERT INTO vaccination_records(pet_id,vaccine,administered_on,next_due) VALUES(%s,'Rabies',current_date-300,current_date+30)",(pet,))
        conn.execute("INSERT INTO medical_records(pet_id,veterinarian_id,diagnosis,treatment) VALUES(%s,%s,'Healthy at wellness examination','Regular exercise and balanced diet')",(pet,vet))
    print('Seeded owner@paw.local, vet@paw.local, admin@paw.local')
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/demo-credentials.txt').write_text('owner@paw.local\nvet@paw.local\nadmin@paw.local\nSample password: '+password+'\n',encoding='utf-8')
    print('Generated sample password saved in artifacts/demo-credentials.txt (gitignored)')


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--schema-only',action='store_true')
    initialize(not parser.parse_args().schema_only)
