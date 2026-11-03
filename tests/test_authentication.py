"""Credential security against isolated real PostgreSQL, including token races."""
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(scope='module')
def client(isolated_db):
    os.environ['DATABASE_URL'] = isolated_db
    os.environ['TOKEN_SECRET'] = 'authentication-tests-secret-' * 3
    with TestClient(app) as client:
        yield client


def account(client, email):
    result = client.post('/auth/register', json={'name': 'Owner', 'email': email, 'password': 'OriginalPassword123!'} )
    assert result.status_code == 201, result.text
    return result.json(), {'Authorization': 'Bearer ' + result.json()['token']}


def recovery(client, monkeypatch, email):
    sent = []
    monkeypatch.setattr('backend.main.deliver_reset', lambda address, token: sent.append((address, token)))
    response = client.post('/auth/forgot-password', json={'email': email})
    assert response.status_code == 202
    assert len(sent) == 1
    assert sent[0][1] not in response.text
    return sent[0][1]


def test_profile_and_password_change(client):
    session, headers = account(client, 'profile@auth.local')
    body = {'name': '  Updated owner  ', 'email': 'UPDATED@auth.local', 'current_password': 'wrong'}
    assert client.put('/auth/profile', headers=headers, json=body).status_code == 403
    body['current_password'] = 'OriginalPassword123!'
    response = client.put('/auth/profile', headers=headers, json={**body, 'role': 'admin'})
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated['user']['name'] == 'Updated owner'
    assert updated['user']['email'] == 'updated@auth.local'
    assert updated['user']['role'] == 'owner'
    assert client.get('/auth/me', headers=headers).status_code == 401
    headers = {'Authorization': 'Bearer ' + updated['token']}
    change = {'current_password': body['current_password'], 'new_password': 'ChangedPassword123!'}
    assert client.post('/auth/change-password', headers=headers, json={**change, 'current_password': 'wrong'}).status_code == 403
    result = client.post('/auth/change-password', headers=headers, json=change)
    assert result.status_code == 200
    assert client.get('/auth/me', headers=headers).status_code == 401
    assert client.get('/auth/me', headers={'Authorization': 'Bearer ' + result.json()['token']}).status_code == 200
    assert client.post('/auth/login', json={'email': body['email'], 'password': body['current_password']}).status_code == 401
    assert client.post('/auth/login', json={'email': body['email'], 'password': change['new_password']}).status_code == 200


def test_profile_conflicts_validation_and_access(client):
    _, headers = account(client, 'conflict@auth.local')
    body = {'name': 'Name', 'email': 'updated@auth.local', 'current_password': 'OriginalPassword123!'}
    assert client.put('/auth/profile', headers=headers, json=body).status_code == 409
    assert client.put('/auth/profile', json=body).status_code == 401
    assert client.put('/auth/profile', headers=headers, json={**body, 'name': '   '}).status_code == 422
    assert client.put('/auth/profile', headers=headers, json={**body, 'email': 'invalid'}).status_code == 422
    assert client.post('/auth/change-password', headers=headers, json={'current_password': body['current_password'], 'new_password': 'short'}).status_code == 422


def test_reset_single_use_and_revocation(client, isolated_db, monkeypatch):
    session, headers = account(client, 'reset@auth.local')
    token = recovery(client, monkeypatch, 'reset@auth.local')
    with psycopg.connect(isolated_db) as conn:
        stored = conn.execute('SELECT token_hash FROM password_resets WHERE user_id=%s', (session['user']['id'],)).fetchone()[0]
        assert stored == hashlib.sha256(token.encode()).hexdigest()
    body = {'token': token, 'new_password': 'RecoveredPassword123!'}
    with ThreadPoolExecutor(max_workers=2) as workers:
        statuses = list(workers.map(lambda _: client.post('/auth/reset-password', json=body).status_code, range(2)))
    assert sorted(statuses) == [200, 400]
    assert client.get('/auth/me', headers=headers).status_code == 401
    assert client.post('/auth/login', json={'email': 'reset@auth.local', 'password': 'OriginalPassword123!'}).status_code == 401
    assert client.post('/auth/login', json={'email': 'reset@auth.local', 'password': body['new_password']}).status_code == 200


def test_expired_disabled_unknown_and_throttle(client, isolated_db, monkeypatch):
    session, _ = account(client, 'expired@auth.local')
    token = recovery(client, monkeypatch, 'expired@auth.local')
    with psycopg.connect(isolated_db) as conn:
        conn.execute("UPDATE password_resets SET expires_at=now()-interval '1 second' WHERE user_id=%s", (session['user']['id'],))
    assert client.post('/auth/reset-password', json={'token': token, 'new_password': 'RecoveredPassword123!'}).status_code == 400
    sent = []
    monkeypatch.setattr('backend.main.deliver_reset', lambda *args: sent.append(args))
    known = client.post('/auth/forgot-password', json={'email': 'expired@auth.local'})
    unknown = client.post('/auth/forgot-password', json={'email': 'missing@auth.local'})
    assert known.json() == unknown.json()
    assert not sent
    with psycopg.connect(isolated_db) as conn:
        conn.execute('UPDATE users SET active=false WHERE id=%s', (session['user']['id'],))
        conn.execute("UPDATE password_resets SET expires_at=now()+interval '1 hour' WHERE user_id=%s", (session['user']['id'],))
    assert client.post('/auth/reset-password', json={'token': token, 'new_password': 'RecoveredPassword123!'}).status_code == 400
    for _ in range(11):
        assert client.post('/auth/forgot-password', json={'email': 'missing@auth.local'}).status_code == 202
    assert not sent


def test_delivery_failure_does_not_expose_account(client, isolated_db, monkeypatch):
    session, _ = account(client, 'failed-delivery@auth.local')
    with psycopg.connect(isolated_db) as conn:
        conn.execute('DELETE FROM recovery_rate_limits')
    def fail(*args):
        raise RuntimeError('private delivery details')
    monkeypatch.setattr('backend.main.deliver_reset', fail)
    known = client.post('/auth/forgot-password', json={'email':'failed-delivery@auth.local'})
    unknown = client.post('/auth/forgot-password', json={'email':'missing2@auth.local'})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    with psycopg.connect(isolated_db) as conn:
        assert conn.execute('SELECT count(*) FROM password_resets WHERE user_id=%s', (session['user']['id'],)).fetchone()[0] == 0
    assert client.post('/auth/forgot-password', json={'email':'x@demo.local\r\nBcc:someone@else.local'}).status_code == 422


def test_recovery_mail_private_local_delivery(tmp_path, monkeypatch):
    from backend.mail import deliver_reset
    monkeypatch.setenv('RECOVERY_DELIVERY', 'local')
    monkeypatch.setenv('RECOVERY_MAILBOX_DIR', str(tmp_path))
    deliver_reset('owner@auth.local', 'test-recovery-code')
    message = next(tmp_path.glob('*.eml')).read_text()
    assert 'test-recovery-code' in message and 'owner@auth.local' in message
