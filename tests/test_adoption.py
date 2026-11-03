import base64
import os
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(scope='module')
def client(isolated_db):
    os.environ['DATABASE_URL']=isolated_db
    os.environ['TOKEN_SECRET']='adoption-test-secret-'*3
    with TestClient(app) as c:yield c


@pytest.fixture
def people(client,isolated_db):
    import secrets
    users={}
    for label in ('seller','first','second','admin','vet'):
        r=client.post('/auth/register',json={'name':label,'email':label+secrets.token_hex(4)+'@adoption.local','password':'AdoptionTestPass123!'})
        assert r.status_code==201
        data=r.json();users[label]={'id':data['user']['id'],'headers':{'Authorization':'Bearer '+data['token']}}
    with psycopg.connect(isolated_db) as c:
        for label in ('admin','vet'):c.execute('UPDATE users SET role=%s WHERE id=%s',(label,users[label]['id']))
    return users


BODY={'name':'Luna','species':'Cat','breed':'Domestic','age_months':12,'gender':'female','location':'Chennai','description':'Friendly animal seeking a home.','health_summary':'Test health summary','weight_kg':4.125,'allergies':'Recorded allergy'}
APPLICATION={'motivation':'I can provide a safe and caring home.','housing':'apartment','has_other_pets':False,'experience':'Previous pet care','contact_phone':'QA contact'}


def listing(client,people,publish=True):
    r=client.post('/adoption/listings',headers=people['seller']['headers'],json={**BODY,'status':'available'})
    assert r.status_code==201,r.text
    row=r.json();assert row['status']=='pending_review'
    if publish:
        r=client.post(f"/adoption/listings/{row['id']}/review",headers=people['admin']['headers'],json={'version':row['version'],'action':'approve'})
        assert r.status_code==200,r.text
        row=r.json()
    return row


def apply(client,people,row,label='first'):
    r=client.post(f"/adoption/listings/{row['id']}/applications",headers=people[label]['headers'],json=APPLICATION)
    assert r.status_code==201,r.text
    return r.json()


def decide(client,people,application,action,label='admin',reason=''):
    return client.post(f"/adoption/applications/{application['id']}/decision",headers=people[label]['headers'],json={'action':action,'reason':reason})


def test_owner_moderation_and_reapproval(client,people):
    row=listing(client,people,False);path=f"/adoption/listings/{row['id']}"
    assert client.get(path,headers=people['first']['headers']).status_code==404
    assert row['id'] not in [r['id'] for r in client.get('/adoption/listings',headers=people['first']['headers']).json()['items']]
    assert client.get('/adoption/listings?scope=review',headers=people['seller']['headers']).status_code==403
    assert client.post(path+'/review',headers=people['seller']['headers'],json={'version':1,'action':'approve'}).status_code==403
    assert client.post(path+'/review',headers=people['admin']['headers'],json={'version':1,'action':'reject'}).status_code==422
    rejected=client.post(path+'/review',headers=people['admin']['headers'],json={'version':1,'action':'reject','reason':'Add clearer care information'}).json()
    assert rejected['status']=='rejected'
    edited=client.put(path,headers=people['seller']['headers'],json={**BODY,'version':rejected['version'],'description':'Updated animal care information'}).json()
    assert edited['status']=='pending_review' and edited['version']==3
    assert client.post(path+'/review',headers=people['admin']['headers'],json={'version':1,'action':'approve'}).status_code==409
    published=client.post(path+'/review',headers=people['admin']['headers'],json={'version':3,'action':'approve'}).json()
    assert published['status']=='available'
    other=client.get(path,headers=people['first']['headers']).json()
    assert 'moderation_reason' not in other and 'selected_application_id' not in other
    changed=client.put(path,headers=people['seller']['headers'],json={**BODY,'version':published['version']}).json()
    assert changed['status']=='pending_review'
    assert client.get(path,headers=people['first']['headers']).status_code==404


def test_application_privacy_and_validation(client,people):
    row=listing(client,people);path=f"/adoption/listings/{row['id']}"
    assert client.post(path+'/applications',headers=people['seller']['headers'],json=APPLICATION).status_code==409
    assert client.post(path+'/applications',headers=people['vet']['headers'],json=APPLICATION).status_code==403
    assert client.post('/adoption/listings',headers=people['vet']['headers'],json=BODY).status_code==403
    assert client.post(path+'/applications',headers=people['first']['headers'],json={**APPLICATION,'motivation':'          '}).status_code==422
    request=apply(client,people,row)
    assert client.post(path+'/applications',headers=people['first']['headers'],json=APPLICATION).status_code==409
    apppath=f"/adoption/applications/{request['id']}"
    assert client.get(apppath,headers=people['seller']['headers']).status_code==404
    assert client.get(apppath,headers=people['second']['headers']).status_code==404
    assert client.get('/adoption/applications?scope=review',headers=people['seller']['headers']).status_code==403
    assert client.get('/adoption/applications',headers=people['second']['headers']).json()['total']==0
    assert client.get('/adoption/applications',headers=people['first']['headers']).json()['total']==1
    assert decide(client,people,request,'approve','first').status_code==403
    assert decide(client,people,request,'withdraw','admin').status_code==403
    assert client.put(path,headers=people['seller']['headers'],json={**BODY,'version':row['version']}).status_code==409
    assert decide(client,people,request,'withdraw','first').status_code==200
    assert decide(client,people,request,'withdraw','first').status_code==409
    assert apply(client,people,row)['id']!=request['id']


def test_competing_approvals_and_handover(client,people,isolated_db):
    row=listing(client,people);first=apply(client,people,row);second=apply(client,people,row,'second')
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses=list(executor.map(lambda a:decide(client,people,a,'approve').status_code,(first,second)))
    assert sorted(statuses)==[200,409]
    approved=first if statuses[0]==200 else second
    loser=second if statuses[0]==200 else first
    winner_label='first' if approved['id']==first['id'] else 'second'
    before=client.get('/pets',headers=people[winner_label]['headers']).json()
    assert before==[]
    reserved=client.get(f"/adoption/listings/{row['id']}",headers=people['admin']['headers']).json()
    assert reserved['status']=='reserved'
    assert client.post(f"/adoption/listings/{row['id']}/review",headers=people['admin']['headers'],json={'version':reserved['version'],'action':'archive'}).status_code==409
    with ThreadPoolExecutor(max_workers=2) as executor:
        completions=list(executor.map(lambda _:decide(client,people,approved,'complete'),range(2)))
    assert sorted(r.status_code for r in completions)==[200,409]
    completed=next(r for r in completions if r.status_code==200)
    assert completed.status_code==200,completed.text
    result=completed.json();assert result['status']=='completed' and result['adopted_pet_id']
    pet=client.get(f"/pets/{result['adopted_pet_id']}",headers=people[winner_label]['headers']).json()
    assert pet['name']=='Luna' and float(pet['weight_kg'])==4.125 and pet['allergies']==BODY['allergies']
    assert decide(client,people,approved,'complete').status_code==409
    assert client.get(f"/adoption/applications/{loser['id']}",headers=people['admin']['headers']).json()['status']=='rejected'
    assert len(client.get('/pets',headers=people[winner_label]['headers']).json())==1
    with psycopg.connect(isolated_db) as c:
        assert c.execute("SELECT count(*) FROM adoption_applications WHERE listing_id=%s AND status='completed'",(row['id'],)).fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM adoption_history WHERE listing_id=%s',(row['id'],)).fetchone()[0]>=7
    notices=client.get('/notifications',headers=people[winner_label]['headers']).json()
    assert any(n['kind']=='adoption_application' and 'completed' in n['message'] for n in notices)
    report=client.get('/reports/activity',headers=people['admin']['headers']).json()
    assert any(e['entity']=='adoption_applications' for e in report['events'])


def test_reserved_withdrawal_and_archive(client,people):
    row=listing(client,people);first=apply(client,people,row);second=apply(client,people,row,'second')
    assert decide(client,people,first,'complete').status_code==409
    assert decide(client,people,first,'approve').status_code==200
    assert decide(client,people,first,'withdraw','first').status_code==200
    assert decide(client,people,second,'approve').status_code==200
    assert decide(client,people,second,'reject',reason='Applicant declined handover').status_code==200
    reopened=client.get(f"/adoption/listings/{row['id']}",headers=people['seller']['headers']).json()
    assert reopened['status']=='available'
    third=apply(client,people,row)
    archived=client.post(f"/adoption/listings/{row['id']}/review",headers=people['seller']['headers'],json={'version':reopened['version'],'action':'archive'})
    assert archived.status_code==200,archived.text
    assert client.get(f"/adoption/applications/{third['id']}",headers=people['first']['headers']).json()['status']=='rejected'
    assert client.get(f"/adoption/listings/{row['id']}",headers=people['first']['headers']).status_code==200


def test_photos_filters_and_access(client,people,tmp_path,monkeypatch):
    monkeypatch.setenv('UPLOAD_DIR',str(tmp_path))
    row=listing(client,people,False);path=f"/adoption/listings/{row['id']}"
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    files={'file':('qa.png',png,'image/png')}
    assert client.post(path+'/image?version=1',headers=people['first']['headers'],files=files).status_code==403
    uploaded=client.post(path+'/image?version=1',headers=people['seller']['headers'],files=files)
    assert uploaded.status_code==200,uploaded.text
    assert uploaded.json()['version']==2
    assert client.get(path+'/image',headers=people['first']['headers']).status_code==404
    assert client.get(path+'/image',headers=people['seller']['headers']).content==png
    assert client.post(path+'/image?version=1',headers=people['seller']['headers'],files=files).status_code==409
    assert len(list(tmp_path.iterdir()))==1
    assert client.post(path+'/review',headers=people['admin']['headers'],json={'version':2,'action':'approve'}).status_code==200
    assert client.get(path+'/image',headers=people['first']['headers']).content==png
    filtered=client.get('/adoption/listings?q=Luna&species=Cat&location=chennai&max_age_months=12&limit=1',headers=people['first']['headers']).json()
    assert len(filtered['items'])==1 and filtered['total']>=1
    assert client.get('/adoption/listings?status=pending_review',headers=people['first']['headers']).status_code==422
    assert client.get('/adoption/listings?offset=-1',headers=people['first']['headers']).status_code==422
    assert client.get('/adoption/listings').status_code==401
    assert client.post('/adoption/listings',headers=people['seller']['headers'],json={**BODY,'location':'  '}).status_code==422


def test_failed_handover_rolls_back(client,people,isolated_db):
    row=listing(client,people);request=apply(client,people,row)
    assert decide(client,people,request,'approve').status_code==200
    with psycopg.connect(isolated_db) as c:c.execute('UPDATE users SET active=false WHERE id=%s',(people['first']['id'],))
    assert decide(client,people,request,'complete').status_code==409
    with psycopg.connect(isolated_db) as c:
        assert c.execute('SELECT count(*) FROM pets WHERE owner_id=%s',(people['first']['id'],)).fetchone()[0]==0
        assert c.execute('SELECT status FROM adoption_applications WHERE id=%s',(request['id'],)).fetchone()[0]=='approved'


def test_notification_failure_rolls_back_the_entire_handover(client,people,isolated_db,monkeypatch):
    import backend.adoption as module
    row=listing(client,people);request=apply(client,people,row);other=apply(client,people,row,'second')
    assert decide(client,people,request,'approve').status_code==200
    original=module.notify
    def failed_delivery(conn,recipients,listing,event,message,application_id=None):
        if event.endswith(':completed'):raise RuntimeError('simulated transactional notification failure')
        return original(conn,recipients,listing,event,message,application_id)
    with monkeypatch.context() as patch:
        patch.setattr(module,'notify',failed_delivery)
        with pytest.raises(RuntimeError,match='simulated transactional'):
            decide(client,people,request,'complete')
    with psycopg.connect(isolated_db) as c:
        assert c.execute('SELECT count(*) FROM pets WHERE owner_id=%s',(people['first']['id'],)).fetchone()[0]==0
        assert c.execute('SELECT status,adopted_pet_id FROM adoption_listings WHERE id=%s',(row['id'],)).fetchone()==('reserved',None)
        assert c.execute('SELECT status FROM adoption_applications WHERE id=%s',(other['id'],)).fetchone()[0]=='pending'
        assert c.execute("SELECT count(*) FROM adoption_history WHERE listing_id=%s AND to_status IN ('completed','adopted')",(row['id'],)).fetchone()[0]==0
    assert decide(client,people,request,'complete').status_code==200


def test_owner_edit_and_application_are_serialized(client,people,isolated_db):
    row=listing(client,people)
    path=f"/adoption/listings/{row['id']}"
    with ThreadPoolExecutor(max_workers=2) as executor:
        application=executor.submit(lambda:client.post(path+'/applications',headers=people['first']['headers'],json=APPLICATION))
        edit=executor.submit(lambda:client.put(path,headers=people['seller']['headers'],json={**BODY,'version':row['version'],'description':'Changed content must be reviewed again.'}))
        a,e=application.result(),edit.result()
    assert not (a.status_code==201 and e.status_code==200)
    with psycopg.connect(isolated_db) as c:
        status=c.execute('SELECT status FROM adoption_listings WHERE id=%s',(row['id'],)).fetchone()[0]
        count=c.execute("SELECT count(*) FROM adoption_applications WHERE listing_id=%s AND status='pending'",(row['id'],)).fetchone()[0]
    if a.status_code==201:
        assert e.status_code==409 and status=='available' and count==1
    else:
        assert e.status_code==200 and a.status_code in (404,409) and status=='pending_review' and count==0
