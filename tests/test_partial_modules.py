import csv
import io
import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(scope='module')
def client(isolated_db):
    os.environ['DATABASE_URL'] = isolated_db
    os.environ['TOKEN_SECRET'] = 'partial-module-test-secret-' * 3
    with TestClient(app) as client:
        yield client


def owner(client, email):
    result = client.post('/auth/register', json={'name':'Owner','email':email,'password':'TestPassword123!'}).json()
    return {'Authorization':'Bearer '+result['token']}, result['user']['id']


def test_structured_pet_fields(client):
    headers, _ = owner(client, 'fields@partial.local')
    body = {'name':'Luna','species':'Cat','weight_kg':4.125,'allergies':'Penicillin'}
    result = client.post('/pets', headers=headers, json=body)
    assert result.status_code == 201, result.text
    pet = result.json()
    assert float(pet['weight_kg']) == 4.125 and pet['allergies'] == 'Penicillin'
    legacy_edit = client.put(f"/pets/{pet['id']}", headers=headers, json={'name':'Luna','species':'Cat'}).json()
    assert float(legacy_edit['weight_kg']) == 4.125 and legacy_edit['allergies'] == 'Penicillin'
    assert client.post('/pets', headers=headers, json={**body,'weight_kg':0}).status_code == 422
    assert client.post('/pets', headers=headers, json={**body,'weight_kg':2001}).status_code == 422
    updated = client.put(f"/pets/{pet['id']}", headers=headers, json={**body,'weight_kg':None,'allergies':''}).json()
    assert updated['weight_kg'] is None and updated['allergies'] == ''


def test_medication_schedule_doses_and_stop(client, isolated_db):
    headers, _ = owner(client, 'medication@partial.local')
    stranger, _ = owner(client, 'stranger@partial.local')
    pet = client.post('/pets', headers=headers, json={'name':'Bruno','species':'Dog'}).json()['id']
    start = datetime.now(timezone.utc)+timedelta(minutes=10)
    body = {'name':'Prescribed medicine','dosage':'1 tablet','instructions':'With food',
            'starts_at':start.isoformat(),'ends_at':(start+timedelta(days=2)).isoformat(),'interval_hours':12}
    path = f'/pets/{pet}/medications'
    assert client.post(path, headers=stranger, json=body).status_code == 403
    response = client.post(path, headers=headers, json=body)
    assert response.status_code == 201, response.text
    mid = response.json()['id']
    doses = client.get('/reminders', headers=headers).json()
    assert len(doses) == 5 and all(d['kind']=='medication' for d in doses)
    assert doses[0]['due_at'] != doses[-1]['due_at']
    assert client.get(path, headers=stranger).status_code == 403
    assert client.get(path, headers=headers).json()[0]['id'] == mid
    assert client.post(path, headers=headers, json={**body,'interval_hours':0}).status_code == 422
    assert client.post(path, headers=headers, json={**body,'ends_at':(start+timedelta(days=367)).isoformat()}).status_code == 422
    assert client.post(path, headers=headers, json={**body,'starts_at':start.replace(tzinfo=None).isoformat()}).status_code == 422
    assert client.post(f"/reminders/{doses[0]['id']}/acknowledge", headers=headers).status_code == 200
    assert client.post(f'{path}/{mid}/stop', headers=stranger).status_code == 403
    assert client.post(f'{path}/{mid}/stop', headers=headers).status_code == 200
    assert client.get('/reminders', headers=headers).json() == []
    with psycopg.connect(isolated_db) as conn:
        assert conn.execute('SELECT count(*) FROM reminders WHERE medication_id=%s AND cancelled', (mid,)).fetchone()[0] == 4
    history = client.get('/notifications', headers=headers).json()
    assert len(history) == 1 and history[0]['acknowledged']
    assert client.delete(f'/pets/{pet}', headers=headers).status_code == 409


def test_appointment_notifications_and_ownership(client, isolated_db):
    headers, uid = owner(client, 'visit@partial.local')
    stranger, _ = owner(client, 'visit-stranger@partial.local')
    pet = client.post('/pets', headers=headers, json={'name':'Luna','species':'Cat'}).json()['id']
    with psycopg.connect(isolated_db) as conn:
        vetuser = conn.execute("INSERT INTO users(name,email,password_hash,role) VALUES('Vet','partial-vet@test.local','unused','vet') RETURNING id").fetchone()[0]
        vet = conn.execute('INSERT INTO veterinarians(user_id) VALUES(%s) RETURNING id',(vetuser,)).fetchone()[0]
        slot = conn.execute("INSERT INTO appointment_slots(veterinarian_id,starts_at,ends_at) VALUES(%s,now()+interval '2 days',now()+interval '2 days 30 minutes') RETURNING id",(vet,)).fetchone()[0]
    response = client.post('/appointments', headers=headers, json={'pet_id':pet,'slot_id':slot})
    assert response.status_code == 201, response.text
    aid = response.json()['id']
    reminders = client.get('/reminders', headers=headers).json()
    assert {r['kind'] for r in reminders} == {'appointment_booked','appointment_reminder'}
    reminder = next(r for r in reminders if r['kind']=='appointment_reminder')
    assert datetime.fromisoformat(reminder['due_at']) > datetime.now(timezone.utc)
    nid = reminders[0]['id']
    assert client.post(f'/notifications/{nid}/read', headers=stranger).status_code == 404
    assert client.post(f'/reminders/{nid}/acknowledge', headers=stranger).status_code == 404
    assert client.post(f'/notifications/{nid}/read', headers=headers).status_code == 200
    assert len(client.get('/notifications?read=false', headers=headers).json()) == 1
    assert client.post(f'/appointments/{aid}/cancel', headers=headers).status_code == 200
    history = client.get('/notifications', headers=headers).json()
    assert {r['kind'] for r in history} == {'appointment_booked','appointment_cancelled'}
    assert client.post(f"/notifications/{reminder['id']}/read", headers=headers).status_code == 404
    assert client.get('/notifications?offset=-1', headers=headers).status_code == 422


def test_reports_role_scope_and_safe_csv(client, isolated_db):
    headers, uid = owner(client, 'report-owner@partial.local')
    other, otherid = owner(client, 'report-other@partial.local')
    admin, adminid = owner(client, 'report-admin@partial.local')
    with psycopg.connect(isolated_db) as conn:
        conn.execute("UPDATE users SET role='admin' WHERE id=%s", (adminid,))
        conn.execute("UPDATE users SET name='=HYPERLINK(1)' WHERE id=%s", (uid,))
    client.post('/auth/login', json={'email':'report-owner@partial.local','password':'TestPassword123!'})
    report = client.get('/reports/activity', headers=headers).json()
    assert len(report['users']) == 1 and report['users'][0]['id'] == uid
    assert report['users'][0]['logins'] == 1
    assert report['total_events'] >= 2
    assert client.get(f'/reports/activity?actor_id={otherid}', headers=headers).status_code == 403
    assert client.get('/reports/activity?start=2026-10-31&end=2026-01-01', headers=headers).status_code == 422
    assert client.get('/reports/activity?start=2020-01-01&end=2026-10-31', headers=headers).status_code == 422
    assert client.get('/reports/activity?format=pdf', headers=headers).status_code == 422
    assert len(client.get('/reports/activity', headers=admin).json()['users']) > 1
    csv_response = client.get('/reports/activity?format=csv', headers=headers)
    assert csv_response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    assert len(rows) == 1 and rows[0]['name'] == "'=HYPERLINK(1)"
    assert 'password_hash' not in csv_response.text
    assert client.get('/reports/activity').status_code == 401
