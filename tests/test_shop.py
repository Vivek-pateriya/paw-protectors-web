import base64
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from backend.main import app


@pytest.fixture(scope='module')
def client(isolated_db):
    os.environ['DATABASE_URL']=isolated_db
    os.environ['TOKEN_SECRET']='shop-test-secret-'*4
    with TestClient(app) as c:yield c


@pytest.fixture
def people(client,isolated_db):
    result={}
    for role in ('owner','other','admin','vet'):
        r=client.post('/auth/register',json={'name':'Shop '+role,'email':role+secrets.token_hex(6)+'@shop.local','password':'ShopTestPassword123!'})
        assert r.status_code==201,r.text
        result[role]={'id':r.json()['user']['id'],'headers':{'Authorization':'Bearer '+r.json()['token']}}
    with psycopg.connect(isolated_db) as conn:
        for role in ('admin','vet'):conn.execute('UPDATE users SET role=%s WHERE id=%s',(role,result[role]['id']))
    return result


def product(client,people,stock=5,active=True):
    h=people['admin']['headers']
    cat=client.post('/shop/categories',headers=h,json={'name':'Food '+uuid4().hex,'active':True})
    assert cat.status_code==201,cat.text
    body={'category_id':cat.json()['id'],'sku':uuid4().hex,'name':'QA pet food','description':'Synthetic shop item','price_paise':12345,'active':active,'initial_stock':stock}
    r=client.post('/shop/products',headers=h,json=body);assert r.status_code==201,r.text
    return r.json()


def cart(client,people,p,who='owner',qty=1):
    h=people[who]['headers'];v=client.get('/shop/cart',headers=h).json()['version']
    r=client.put(f'/shop/cart/items/{p["id"]}',headers=h,json={'version':v,'quantity':qty})
    assert r.status_code==200,r.text
    return r.json()


def address(c):
    return {'version':c['version'],'checkout_key':str(uuid4()),'expected_total_paise':c['total_paise'],'customer_name':'QA Buyer','phone':'0000000000','address':'Synthetic test address only','city':'QA City','state':'QA State','postal_code':'600001'}


def buy(client,people,p,who='owner',qty=1):
    c=cart(client,people,p,who,qty);body=address(c)
    r=client.post('/shop/checkout',headers=people[who]['headers'],json=body)
    assert r.status_code==201,r.text
    return r.json(),body


def decision(client,people,o,action,who='admin',note='QA decision'):
    return client.post(f'/shop/orders/{o["id"]}/decision',headers=people[who]['headers'],json={'version':o['version'],'action':action,'note':note,'tracking_reference':'QA tracking' if action=='ship' else ''})


def test_catalogue_permissions_categories_and_photos(client,people,tmp_path,monkeypatch):
    monkeypatch.setenv('UPLOAD_DIR',str(tmp_path))
    p=product(client,people,active=False);path=f'/shop/products/{p["id"]}'
    assert client.get('/shop/products').status_code==401
    assert client.get(path,headers=people['owner']['headers']).status_code==404
    assert client.post('/shop/products',headers=people['owner']['headers'],json={}).status_code==403
    assert client.get('/shop/products?scope=manage',headers=people['vet']['headers']).status_code==403
    png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j4ZkAAAAASUVORK5CYII=')
    h=people['admin']['headers']
    r=client.post(path+'/image',params={'version':p['version']},headers=h,files={'file':('qa.png',png,'image/png')})
    assert r.status_code==200,r.text;p=r.json()
    assert client.get(path+'/image',headers=people['owner']['headers']).status_code==404
    assert client.post(path+'/image',params={'version':p['version']},headers=h,files={'file':('qa.txt',b'not image','image/png')}).status_code==422
    body={k:p[k] for k in ('category_id','sku','name','description','price_paise','low_stock_threshold')};body.update(active=True,version=p['version'])
    r=client.put(path,headers=h,json=body);assert r.status_code==200,r.text
    assert client.put(path,headers=h,json=body).status_code==409
    assert client.get(path+'/image',headers=people['owner']['headers']).content==png
    found=client.get('/shop/products',params={'q':p['sku'],'in_stock':True},headers=people['owner']['headers']).json()
    assert found['total']==1
    cat=client.get('/shop/categories',headers=h).json();cat=next(x for x in cat if x['id']==p['category_id'])
    assert client.put('/shop/categories/'+str(cat['id']),headers=h,json={'name':cat['name'],'active':False,'version':cat['version']}).status_code==200
    assert client.get(path,headers=people['owner']['headers']).status_code==404


def test_cart_shared_version_and_checkout_price_change(client,people):
    p=product(client,people);c=cart(client,people,p,qty=2);h=people['owner']['headers']
    assert client.get('/shop/cart',headers=h).json()['items'][0]['quantity']==2
    assert client.put(f'/shop/cart/items/{p["id"]}',headers=h,json={'version':c['version']-1,'quantity':1}).status_code==409
    assert client.get('/shop/cart',headers=people['admin']['headers']).status_code==403
    body={k:p[k] for k in ('category_id','sku','name','description','price_paise','low_stock_threshold','active')};body.update(version=p['version'],price_paise=13000)
    assert client.put('/shop/products/'+str(p['id']),headers=people['admin']['headers'],json=body).status_code==200
    assert client.post('/shop/checkout',headers=h,json=address(c)).status_code==409
    fresh=client.get('/shop/cart',headers=h).json();assert fresh['total_paise']==26000
    assert client.put(f'/shop/cart/items/{p["id"]}',headers=h,json={'version':fresh['version'],'quantity':0}).json()['items']==[]


def test_checkout_snapshots_privacy_and_idempotent_retry(client,people):
    p=product(client,people);o,body=buy(client,people,p,'vet',2);h=people['vet']['headers']
    assert o['total_paise']==24690 and o['delivery_paise']==0 and o['payment_method']=='cod'
    assert o['items'][0]['unit_price_paise']==12345 and o['payment_status']=='pending'
    retry=client.post('/shop/checkout',headers=h,json=body);assert retry.status_code==201 and retry.json()['id']==o['id']
    assert client.post('/shop/checkout',headers=h,json={**body,'city':'Different'}).status_code==409
    assert client.get('/shop/orders/'+str(o['id']),headers=people['other']['headers']).status_code==404
    assert client.get('/shop/orders?scope=all',headers=people['other']['headers']).status_code==403
    assert 'address' not in client.get('/shop/orders',headers=h).json()['items'][0]
    assert client.get('/shop/cart',headers=h).json()['items']==[]
    assert client.get('/shop/products/'+str(p['id']),headers=people['admin']['headers']).json()['stock']==3
    assert decision(client,people,o,'confirm','vet').status_code==403
    assert any('Pet Shop order' in x['message'] for x in client.get('/notifications',headers=h).json())


def test_competing_checkouts_never_oversell(client,people,isolated_db):
    p=product(client,people,stock=1);a=address(cart(client,people,p));b=address(cart(client,people,p,'other'))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda x:client.post('/shop/checkout',headers=people[x[0]]['headers'],json=x[1]),[('owner',a),('other',b)]))
    assert sorted(x.status_code for x in results)==[201,409]
    with psycopg.connect(isolated_db) as conn:
        assert conn.execute('SELECT stock FROM shop_products WHERE id=%s',(p['id'],)).fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM shop_stock_movements WHERE product_id=%s AND kind='checkout'",(p['id'],)).fetchone()[0]==1


def test_concurrent_retry_and_cancel_restock_once(client,people,isolated_db):
    p=product(client,people,stock=2);body=address(cart(client,people,p))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:client.post('/shop/checkout',headers=people['owner']['headers'],json=body),range(2)))
    assert [x.status_code for x in results]==[201,201]
    assert results[0].json()['id']==results[1].json()['id'];o=results[0].json()
    assert decision(client,people,o,'cancel','owner','').status_code==422
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:decision(client,people,o,'cancel','owner'),range(2)))
    assert sorted(x.status_code for x in results)==[200,409]
    with psycopg.connect(isolated_db) as conn:
        assert conn.execute('SELECT stock FROM shop_products WHERE id=%s',(p['id'],)).fetchone()[0]==2
        assert conn.execute("SELECT count(*) FROM shop_stock_movements WHERE order_id=%s AND kind='cancellation'",(o['id'],)).fetchone()[0]==1


def test_order_status_machine_and_cash_collection(client,people):
    p=product(client,people);o,_=buy(client,people,p)
    assert decision(client,people,o,'deliver').status_code==409
    r=decision(client,people,o,'confirm');assert r.status_code==200;o=r.json()
    assert decision(client,people,o,'cancel','owner').status_code==409
    r=decision(client,people,o,'ship');assert r.status_code==200;o=r.json()
    assert o['tracking_reference']=='QA tracking'
    assert decision(client,people,o,'cancel').status_code==409
    r=decision(client,people,o,'deliver');assert r.status_code==200;o=r.json()
    assert o['payment_status']=='collected' and len(o['history'])==4
    assert decision(client,people,o,'deliver').status_code==409


def test_archived_cart_and_stock_audit(client,people):
    p=product(client,people);c=cart(client,people,p);path='/shop/products/'+str(p['id']);h=people['admin']['headers']
    assert client.post(path+'/stock',headers=h,json={'version':p['version'],'delta':-99,'reason':'QA'}).status_code==409
    r=client.post(path+'/stock',headers=h,json={'version':p['version'],'delta':-4,'reason':'QA stock correction'});assert r.status_code==200;p=r.json()
    detail=client.get(path,headers=h).json();assert detail['stock_history'][0]['reason']=='QA stock correction'
    assert client.get('/shop/products?scope=manage&low_stock=true',headers=h).json()['total']>=1
    body={k:p[k] for k in ('category_id','sku','name','description','price_paise','low_stock_threshold')};body.update(version=p['version'],active=False)
    assert client.put(path,headers=h,json=body).status_code==200
    assert not client.get('/shop/cart',headers=people['owner']['headers']).json()['can_checkout']
    assert client.post('/shop/checkout',headers=people['owner']['headers'],json=address(c)).status_code==409


def test_checkout_failure_rolls_back_stock_order_cart_and_notifications(client,people,isolated_db,monkeypatch):
    from backend import shop
    p=product(client,people);c=cart(client,people,p);body=address(c)
    original=shop.notify_order
    def fail(*args):raise RuntimeError('Simulated notification failure')
    monkeypatch.setattr(shop,'notify_order',fail)
    with pytest.raises(RuntimeError,match='Simulated'):client.post('/shop/checkout',headers=people['owner']['headers'],json=body)
    with psycopg.connect(isolated_db) as conn:
        assert conn.execute('SELECT stock FROM shop_products WHERE id=%s',(p['id'],)).fetchone()[0]==5
        assert conn.execute('SELECT count(*) FROM shop_orders WHERE user_id=%s',(people['owner']['id'],)).fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM shop_cart_items WHERE user_id=%s',(people['owner']['id'],)).fetchone()[0]==1
    monkeypatch.setattr(shop,'notify_order',original)
    assert client.post('/shop/checkout',headers=people['owner']['headers'],json=body).status_code==201
