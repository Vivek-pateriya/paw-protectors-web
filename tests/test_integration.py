import os
from datetime import date,timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import psycopg
import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(scope='module')
def client(isolated_db):
    from backend import db
    os.environ['DATABASE_URL']=isolated_db
    os.environ['TOKEN_SECRET']='integration-test-secret-'*3
    with TestClient(app) as client:
        yield client


def register(client,email):
    r=client.post('/auth/register',json={'name':'Test owner','email':email,'password':'TestPassword123!'})
    assert r.status_code==201,r.text
    data=r.json()
    return {'Authorization':'Bearer '+data['token']},data['user']['id']


def setup_booking(client,url,email):
    headers,owner=register(client,email)
    pet=client.post('/pets',headers=headers,json={'name':'Bruno','species':'Dog'}).json()['id']
    with psycopg.connect(url) as conn:
        vet_user=conn.execute("INSERT INTO users(name,email,password_hash,role) VALUES('Vet',%s,'unused','vet') RETURNING id",('vet-'+email,)).fetchone()[0]
        vet=conn.execute("INSERT INTO veterinarians(user_id) VALUES(%s) RETURNING id",(vet_user,)).fetchone()[0]
        slot=conn.execute("INSERT INTO appointment_slots(veterinarian_id,starts_at,ends_at) VALUES(%s,now()+interval '1 day',now()+interval '1 day 30 minutes') RETURNING id",(vet,)).fetchone()[0]
    return headers,pet,slot


def test_health_and_auth(client):
    assert client.get('/health').json()['database']=='postgresql'
    assert client.get('/pets').status_code==401
    headers,uid=register(client,'first@test.local')
    assert client.get('/auth/me',headers=headers).json()['id']==uid
    assert client.get('/admin/users',headers=headers).status_code==403
    assert client.post('/auth/login',json={'email':'first@test.local','password':'wrong'}).status_code==401
    assert client.post('/auth/register',json={'name':'x','email':'first@test.local','password':'TestPassword123!'}).status_code==409


def test_api_documentation(client):
    assert client.get('/docs').status_code == 200
    assert client.get('/openapi.json').json()['info']['title'] == 'Paw Protectors'


def test_pet_crud_and_authorization(client):
    a,_=register(client,'a@test.local'); b,_=register(client,'b@test.local')
    body={'name':'Luna','species':'Cat','gender':'female'}
    r=client.post('/pets',headers=a,json=body); assert r.status_code==201
    pid=r.json()['id']
    assert client.get(f'/pets/{pid}',headers=b).status_code==403
    assert client.put(f'/pets/{pid}',headers=a,json={**body,'age_months':18}).json()['age_months']==18
    assert client.post('/pets',headers=a,json={**body,'age_months':-1}).status_code==422
    assert client.delete(f'/pets/{pid}',headers=a).status_code==204


def test_vaccination_trigger_and_medical_permissions(client):
    a,_=register(client,'vacc@test.local')
    pid=client.post('/pets',headers=a,json={'name':'Luna','species':'Cat'}).json()['id']
    today=date.today()
    r=client.post(f'/pets/{pid}/vaccinations',headers=a,json={'vaccine':'Rabies','administered_on':str(today),'next_due':str(today+timedelta(days=30))})
    assert r.status_code==201
    reminders=client.get('/reminders',headers=a).json(); assert len(reminders)==1
    assert client.post(f"/reminders/{reminders[0]['id']}/acknowledge",headers=a).status_code==200
    assert client.get('/reminders',headers=a).json()==[]
    assert client.post(f'/pets/{pid}/medical-records',headers=a,json={'diagnosis':'x'}).status_code==403


def test_100_simultaneous_booking_attempts(client,isolated_db):
    headers,pet,slot=setup_booking(client,isolated_db,'race@test.local')
    barrier=Barrier(100)
    def attempt(_):
        barrier.wait(timeout=30)
        return client.post('/appointments',headers=headers,json={'slot_id':slot,'pet_id':pet}).status_code
    with ThreadPoolExecutor(max_workers=100) as executor:
        results=list(executor.map(attempt,range(100)))
    assert results.count(201)==1,results
    assert results.count(409)==99,results
    with psycopg.connect(isolated_db) as conn:
        assert conn.execute("SELECT count(*) FROM appointments WHERE slot_id=%s AND status IN ('booked','completed')",(slot,)).fetchone()[0]==1
        assert conn.execute("SELECT count(*) FROM audit_logs WHERE entity='appointments' AND action='INSERT' AND entity_id IN (SELECT id FROM appointments WHERE slot_id=%s)",(slot,)).fetchone()[0]==1


def test_cancel_reopens_slot(client,isolated_db):
    headers,pet,slot=setup_booking(client,isolated_db,'cancel@test.local')
    first=client.post('/appointments',headers=headers,json={'slot_id':slot,'pet_id':pet})
    assert first.status_code==201
    assert client.post(f"/appointments/{first.json()['id']}/cancel",headers=headers).status_code==200
    assert client.post('/appointments',headers=headers,json={'slot_id':slot,'pet_id':pet}).status_code==201


def test_rollback_removes_audit(isolated_db):
    with psycopg.connect(isolated_db) as conn:
        before=conn.execute('SELECT count(*) FROM audit_logs').fetchone()[0]
        with pytest.raises(RuntimeError):
            with conn.transaction():
                conn.execute("INSERT INTO users(name,email,password_hash) VALUES('Rollback','rollback@test.local','unused')")
                raise RuntimeError('force rollback')
        assert conn.execute("SELECT count(*) FROM users WHERE email='rollback@test.local'").fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM audit_logs').fetchone()[0]==before


def test_logout_revokes_session(client):
    headers,_=register(client,'logout@test.local')
    assert client.post('/auth/logout',headers=headers).status_code==204
    assert client.get('/auth/me',headers=headers).status_code==401


def test_images(client,tmp_path,monkeypatch):
    monkeypatch.setenv('UPLOAD_DIR',str(tmp_path))
    owner,_=register(client,'image@test.local')
    stranger,_=register(client,'image-other@test.local')
    pet=client.post('/pets',headers=owner,json={'name':'Image pet','species':'Cat'}).json()['id']
    assert client.post(f'/pets/{pet}/image',headers=owner,files={'file':('x.txt',b'not image','text/plain')}).status_code==422
    # Minimal PNG fixture generated from standard library: a valid 1x1 image.
    import base64
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    assert client.post(f'/pets/{pet}/image',headers=owner,files={'file':('x.png',png,'image/png')}).status_code==200
    assert client.get(f'/pets/{pet}/image',headers=owner).content==png
    assert client.get(f'/pets/{pet}/image',headers=stranger).status_code==403


def test_vet_admin_and_clinical_flow(client,isolated_db):
    admin,aid=register(client,'admin@test.local')
    vet,vid=register(client,'clinical@test.local')
    owner,oid=register(client,'clinical-owner@test.local')
    with psycopg.connect(isolated_db) as conn:
        conn.execute("UPDATE users SET role='admin' WHERE id=%s",(aid,))
    assert client.put(f'/admin/users/{vid}',headers=admin,json={'role':'vet','active':True}).status_code==200
    v=client.post('/veterinarians',headers=admin,json={'user_id':vid,'clinic':'Test clinic'})
    assert v.status_code==201;v=v.json()
    start=date.today()+timedelta(days=4)
    s=client.post('/slots',headers=vet,json={'veterinarian_id':v['id'],'starts_at':str(start)+'T10:00:00+05:30','ends_at':str(start)+'T10:30:00+05:30'})
    assert s.status_code==201;s=s.json()
    pid=client.post('/pets',headers=owner,json={'name':'Clinical pet','species':'Dog'}).json()['id']
    assert client.get(f'/pets/{pid}',headers=vet).status_code==403
    booking=client.post('/appointments',headers=owner,json={'slot_id':s['id'],'pet_id':pid})
    assert booking.status_code==201
    assert client.get(f'/pets/{pid}',headers=vet).status_code==200
    assert client.post(f'/pets/{pid}/medical-records',headers=vet,json={'diagnosis':'Well','treatment':'Exercise'}).status_code==201
    assert len(client.get(f'/pets/{pid}/medical-records',headers=owner).json())==1
    assert client.post(f"/appointments/{booking.json()['id']}/complete",headers=owner).status_code==403
    assert client.post(f"/appointments/{booking.json()['id']}/complete",headers=vet).status_code==200
    assert client.post('/appointments',headers=owner,json={'slot_id':s['id'],'pet_id':pid}).status_code==409
    assert client.get('/admin/analytics',headers=admin).json()['veterinarians']>=1
    audits=client.get('/admin/audit',headers=admin).json()
    assert any(a['actor_id']==oid and a['entity']=='appointments' for a in audits)
    assert all('password_hash' not in a['details'] for a in audits)
    assert client.put(f'/admin/users/{aid}',headers=admin,json={'role':'owner','active':True}).status_code==409
    assert client.put(f"/veterinarians/{v['id']}",headers=vet,json={'user_id':vid,'available':False,'clinic':'Test clinic'}).status_code==200


def test_database_constraints(isolated_db):
    with psycopg.connect(isolated_db) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            with conn.transaction():
                conn.execute("INSERT INTO users(name,email,password_hash,role) VALUES('Bad','bad@test.local','unused','superuser')")
        # Cross-owner booking is rejected even by a direct SQL INSERT.
        a=conn.execute('SELECT id,owner_id FROM pets LIMIT 1').fetchone()
        other=conn.execute('SELECT id FROM users WHERE id<>%s LIMIT 1',(a[1],)).fetchone()[0]
        slot=conn.execute('SELECT id FROM appointment_slots LIMIT 1').fetchone()[0]
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            with conn.transaction():
                conn.execute('INSERT INTO appointments(slot_id,pet_id,owner_id,status) VALUES(%s,%s,%s,\'cancelled\')',(slot,a[0],other))
