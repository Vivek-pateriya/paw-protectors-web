"""Prove the new migrations preserve a populated version-2 database."""
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg import sql


def test_upgrade_existing_accounts_pets_and_bookings(isolated_db):
    schema = 'upgrade_' + uuid4().hex
    with psycopg.connect(isolated_db, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            for version in (1,2):
                conn.execute(next(Path('database').glob(f'{version:03}_*.sql')).read_text(encoding='utf-8'))
            owner = conn.execute("INSERT INTO users(name,email,password_hash) VALUES('Existing owner','upgrade-owner@paw.local','preserved-hash') RETURNING id").fetchone()[0]
            vetuser = conn.execute("INSERT INTO users(name,email,password_hash,role) VALUES('Existing vet','upgrade-vet@paw.local','preserved-vet-hash','vet') RETURNING id").fetchone()[0]
            pet = conn.execute("INSERT INTO pets(owner_id,name,species,gender,medical_notes) VALUES(%s,'Existing Luna','Cat','female','Preserve these notes') RETURNING id",(owner,)).fetchone()[0]
            vet = conn.execute('INSERT INTO veterinarians(user_id) VALUES(%s) RETURNING id',(vetuser,)).fetchone()[0]
            slot = conn.execute("INSERT INTO appointment_slots(veterinarian_id,starts_at,ends_at) VALUES(%s,now()+interval '2 days',now()+interval '2 days 30 minutes') RETURNING id",(vet,)).fetchone()[0]
            booking = conn.execute("SELECT book_appointment(%s,%s,%s,'Existing booking')",(slot,pet,owner)).fetchone()[0]
            conn.execute("INSERT INTO vaccination_records(pet_id,vaccine,administered_on,next_due) VALUES(%s,'Rabies',current_date,current_date+30)",(pet,))
            before = conn.execute('SELECT id,name,email,password_hash,role FROM users ORDER BY id').fetchall()
            for version in (3,4,5,6):
                conn.execute(next(Path('database').glob(f'{version:03}_*.sql')).read_text(encoding='utf-8'))
            assert conn.execute('SELECT id,name,email,password_hash,role FROM users ORDER BY id').fetchall() == before
            assert conn.execute('SELECT medical_notes,weight_kg,allergies FROM pets WHERE id=%s',(pet,)).fetchone() == ('Preserve these notes',None,'')
            assert conn.execute('SELECT reason,status FROM appointments WHERE id=%s',(booking,)).fetchone() == ('Existing booking','booked')
            assert conn.execute('SELECT kind FROM reminders ORDER BY kind').fetchall() == [('appointment_reminder',),('vaccination',)]
            assert conn.execute('SELECT version FROM schema_versions ORDER BY version').fetchall() == [(1,),(2,),(3,),(4,),(5,),(6,)]
        finally:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
