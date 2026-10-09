"""Real HTTP booking race. Supply an unused future slot; one booking will persist."""
import argparse
import asyncio
import getpass
import json
from collections import Counter
from pathlib import Path
import httpx


async def race(base,email,password,pet,slot):
    async with httpx.AsyncClient(base_url=base,timeout=60,limits=httpx.Limits(max_connections=100,max_keepalive_connections=100)) as client:
        login=await client.post('/auth/login',json={'email':email,'password':password});login.raise_for_status()
        headers={'Authorization':'Bearer '+login.json()['token']}
        gate=asyncio.Event()
        async def attempt():
            await gate.wait()
            return (await client.post('/appointments',headers=headers,json={'pet_id':pet,'slot_id':slot,'reason':'Faculty concurrency demonstration'})).status_code
        tasks=[asyncio.create_task(attempt()) for _ in range(100)];gate.set()
        outcomes=Counter(await asyncio.gather(*tasks))
        result={'attempts':100,'statuses':dict(outcomes)}
        Path('artifacts').mkdir(exist_ok=True);Path('artifacts/http-race.json').write_text(json.dumps(result,indent=2))
        print(result)
        assert outcomes==Counter({409:99,201:1}),result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='http://127.0.0.1:8000');p.add_argument('--email',required=True);p.add_argument('--pet',type=int,required=True);p.add_argument('--slot',type=int,required=True);args=p.parse_args()
    asyncio.run(race(args.base,args.email,getpass.getpass('Password: '),args.pet,args.slot))
