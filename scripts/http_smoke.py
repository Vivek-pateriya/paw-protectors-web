"""Socket-based end-to-end race using seed admin credentials kept outside Git."""
import asyncio
import json
import secrets
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
from scripts.load_test import race


def run():
    base='http://127.0.0.1:8000'
    password=Path('artifacts/demo-credentials.txt').read_text().split('password: ')[-1].strip()
    with httpx.Client(base_url=base,timeout=30) as c:
        assert c.get('/health').status_code==200
        admin=c.post('/auth/login',json={'email':'admin@paw.local','password':password});admin.raise_for_status()
        headers={'Authorization':'Bearer '+admin.json()['token']}
        vets=c.get('/veterinarians',headers=headers).json();vid=vets[0]['id']
        start=datetime.now(timezone.utc)+timedelta(days=20)
        slot=c.post('/slots',headers=headers,json={'veterinarian_id':vid,'starts_at':start.isoformat(),'ends_at':(start+timedelta(minutes=30)).isoformat()});slot.raise_for_status();sid=slot.json()['id']
        owner_email='faculty-'+secrets.token_hex(4)+'@demo.local';owner_pass=secrets.token_urlsafe(16)
        user=c.post('/auth/register',json={'name':'Faculty race owner','email':owner_email,'password':owner_pass});user.raise_for_status()
        oh={'Authorization':'Bearer '+user.json()['token']}
        pet=c.post('/pets',headers=oh,json={'name':'Concurrency demo pet','species':'Dog','breed':'Indian pariah'});pet.raise_for_status();pid=pet.json()['id']
    asyncio.run(race(base,owner_email,owner_pass,pid,sid))
    with httpx.Client(base_url=base,timeout=30) as c:
        history=c.get('/appointments',headers=oh).json()
        assert len(history)==1 and history[0]['slot_id']==sid
        assert c.post(f"/appointments/{history[0]['id']}/cancel",headers=oh).status_code==200
        assert c.post('/auth/logout',headers=oh).status_code==204
    print('PASS: real HTTP health, registration, pet creation, 100-way booking race, history, cancellation and logout')


if __name__=='__main__':run()
