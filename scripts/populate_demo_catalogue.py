"""Add the user-requested illustrated demo catalogue through the common admin API."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys

import httpx

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/catalogue-20261103'
OUT.mkdir(exist_ok=True)
CHECKPOINT=OUT/'import.json'
LICENSE='https://unsplash.com/license'


def photo(key,image,page,author='Unsplash contributor'):
    return {'key':key,'url':f'https://images.unsplash.com/{image}?fm=jpg&w=1200&q=85',
            'source':page,'author':author,'license':LICENSE}


PHOTOS=[
 photo('milo','photo-1652990251361-8d4061f6d724','https://unsplash.com/es/fotos/un-primer-plano-de-un-gato-con-ojos-verdes-9j8E3r07t8c','Matteus Silva'),
 photo('luna','photo-1583795128727-6ec3642408f8','https://unsplash.com/photos/brown-and-white-tabby-cat-mBRfYA0dYYE','Lloyd Henneman'),
 photo('tiger','photo-1668036268154-9f3b37adaeb4','https://unsplash.com/photos/a-dog-standing-in-a-field-TEgyQcGneGE','Laura Roberts'),
 photo('bodus','photo-1661815157785-d9d026d0d557','https://unsplash.com/ja/写真/草むらに座っている犬-pY1k0jy8Wr8'),
 photo('juli','photo-1543466835-00a7907e9de1','https://unsplash.com/photos/dogs-face-2l0CWTpcChI','Milli'),
 photo('kiwi','photo-1470662061953-318cd8c6c152','https://unsplash.com/photos/green-and-yellow-bird-standing-on-tree-branch-yWfdhaqSAEo','Dalton Touchberry'),
 photo('sunny','photo-1725075936780-5153e0613074','https://unsplash.com/photos/a-close-up-of-a-bird-on-a-tree-branch-EA0BMEBoWXo','David Clode'),
 photo('peach','photo-1643010838755-b67a96934908','https://unsplash.com/photos/a-yellow-and-orange-bird-sitting-on-a-tree-branch-g3ctJYt-dmo','Anil Sharma'),
 photo('goldie','photo-1654181925544-4b9f45943cc4','https://unsplash.com/s/photos/canary'),
 photo('pip','photo-1618785427266-e7d1bde0c941','https://unsplash.com/es/fotos/pajaro-gris-naranja-y-negro-sobre-hierba-verde-durante-el-dia-M9YOf_w6uiE','Trevor McKinnon'),
 photo('dog-food','photo-1676193866128-03a926df76ef','https://unsplash.com/pt-br/fotografias/uma-tigela-de-comida-de-cachorro-em-um-piso-de-azulejo-xWKBOhVXBQ4',"David D'Angelo"),
 photo('cat-food','photo-1702571076990-0e2390596556','https://unsplash.com/photos/a-blue-bowl-filled-with-food-on-top-of-a-rug-oC-SxJQQ8pY','Linus Belanger'),
 photo('plush-toy','photo-1747052700126-665257bd2e85','https://unsplash.com/photos/a-playful-dog-sniffs-its-many-toys-1lN0U3yA1go','Jing Ma'),
 photo('tug-ring','photo-1701259065786-be8b665a7eb7','https://unsplash.com/photos/a-small-dog-playing-with-a-toy-on-the-floor-qu3twko64Oo'),
 photo('feather-wand','photo-1638826595775-e2eae86cda8e','https://unsplash.com/photos/a-cat-playing-with-a-toy-on-the-floor-RjevsjqTBk8','Piotr Musiol'),
 photo('rainbow-toy','photo-1708979346185-5f3235e1becd','https://unsplash.com/photos/a-cat-playing-with-a-toy-on-the-floor-Oz92sBVFrCo','Nader Saremi'),
 photo('pet-bed','photo-1699309366611-c4cf7748dbec','https://unsplash.com/fr/photos/un-chien-couche-dans-un-lit-pour-chien-sur-le-sol-DLPnU9auOWs','Olivier Leysen'),
]
PHOTO={p['key']:p for p in PHOTOS}
ANIMALS=[
 ('Milo','Cat','Domestic shorthair',12,'male','milo'),
 ('Luna','Cat','Domestic shorthair',10,'female','luna'),
 ('Tiger','Dog','Labrador Retriever',18,'male','tiger'),
 ('Bodus','Dog','Golden Retriever',24,'male','bodus'),
 ('Juli','Dog','Beagle',15,'female','juli'),
 ('Kiwi','Bird','Budgerigar',8,'unknown','kiwi'),
 ('Sunny','Bird','Cockatiel',12,'unknown','sunny'),
 ('Peach','Bird','Lovebird',10,'unknown','peach'),
 ('Goldie','Bird','Canary',9,'unknown','goldie'),
 ('Pip','Bird','Zebra finch',8,'unknown','pip'),
]
PRODUCTS=[
 ('PAW-DF-1000','Adult Dry Dog Food - 1 kg','Dog Food',39900,30,'dog-food','One 1 kg demonstration pack of generic dry dog food. Brand and nutritional specification are not provided.'),
 ('PAW-DF-3000','Adult Dry Dog Food - 3 kg','Dog Food',99900,15,'dog-food','One 3 kg demonstration pack of generic dry dog food. Brand and nutritional specification are not provided.'),
 ('PAW-CF-1000','Dry Cat Food - 1 kg','Cat Food',44900,30,'cat-food','One 1 kg demonstration pack of generic dry cat food. Brand and nutritional specification are not provided.'),
 ('PAW-CF-2000','Dry Cat Food - 2 kg','Cat Food',79900,15,'cat-food','One 2 kg demonstration pack of generic dry cat food. Brand and nutritional specification are not provided.'),
 ('PAW-TOY-PLUSH','Plush Dog Toy','Toys',29900,25,'plush-toy','One assorted plush dog toy. The reference photograph shows an illustrative play scene with several toys.'),
 ('PAW-TOY-RING','Rubber Tug Ring','Toys',19900,25,'tug-ring','One ring-shaped toy for interactive play. Size and colour shown are illustrative.'),
 ('PAW-TOY-WAND','Cat Feather Wand','Toys',12900,35,'feather-wand','One wand-style cat toy with a feather attachment. Reference photo illustrates the type of toy.'),
 ('PAW-TOY-RAINBOW','Rainbow Cat Teaser','Toys',14900,30,'rainbow-toy','One colourful hanging teaser toy for cats. Reference photo illustrates the type of toy.'),
 ('PAW-BOWL-BLUE','Blue Ceramic Pet Bowl','Pet Accessories',24900,20,'dog-food','One blue ceramic feeding bowl. Food in the reference photo is not included.'),
 ('PAW-BED-ROUND','Round Cushion Pet Bed','Pet Accessories',99900,12,'pet-bed','One round cushion-style pet bed. The animal in the reference photograph is not included.'),
]


def download(p):
    path=OUT/(p['key']+'.jpg')
    if not path.exists():
        response=httpx.get(p['url'],timeout=40,follow_redirects=True)
        response.raise_for_status()
        content=response.content
        assert content.startswith(b'\xff\xd8\xff') and len(content)<=5*1024*1024,p['key']
        path.write_bytes(content)
    return {**p,'local_file':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def credit(key):
    p=PHOTO[key]
    return f"Reference photo: {p['author']} / Unsplash. Source: {p['source']} . License: {LICENSE} ."


def run_import():
    state=json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else {'adoption':{},'products':{},'categories':{}}
    def save():CHECKPOINT.write_text(json.dumps(state,indent=2),encoding='utf-8')
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as api:
        login=api.post('/auth/login',json={'email':'admin@paw.local','password':os.environ['PAW_ADMIN_PASSWORD']})
        login.raise_for_status();session=login.json();assert session['user']['role']=='admin'
        api.headers['Authorization']='Bearer '+session['token']
        def call(method,path,**kwargs):
            r=api.request(method,path,**kwargs);r.raise_for_status();return r.json()
        def upload(path,row,key):
            with (OUT/(key+'.jpg')).open('rb') as file:
                return call('POST',path+'/image',params={'version':row['version']},files={'file':(key+'.jpg',file,'image/jpeg')})
        for name,species,breed,age,gender,key in ANIMALS:
            if name not in state['adoption']:
                row=call('POST','/adoption/listings',json={
                    'name':name,'species':species,'breed':breed,'age_months':age,'gender':gender,
                    'location':'Demo Adoption Centre',
                    'description':f'Meet {name}, a {breed.lower()} featured in the Paw Protectors adoption demo. This is an illustrative project listing, not a verified real animal offer. Age, breed and gender are sample profile details. '+credit(key),
                    'health_summary':'Health and vaccination records have not been provided. Demo profile.',
                })
                state['adoption'][name]={'id':row['id'],'photo':key};save()
            row=call('GET',f'/adoption/listings/{state["adoption"][name]["id"]}')
            assert row['creator_id']==session['user']['id'] and row['name']==name
            if not row['image_path']:upload(f'/adoption/listings/{row["id"]}',row,key)
            print('Adoption ready:',name,flush=True)
        categories=call('GET','/shop/categories')
        for category in dict.fromkeys(p[2] for p in PRODUCTS):
            if category not in state['categories']:
                existing=next((c for c in categories if c['name'].casefold()==category.casefold() and c['active']),None)
                row=existing or call('POST','/shop/categories',json={'name':category,'active':True})
                state['categories'][category]=row['id'];save()
        existing=call('GET','/shop/products',params={'scope':'manage','limit':100})['items']
        for sku,name,category,price,stock,key,detail in PRODUCTS:
            if sku not in state['products']:
                assert not any(p['sku']==sku for p in existing),'SKU already exists outside this import'
                row=call('POST','/shop/products',json={
                    'category_id':state['categories'][category],'sku':sku,'name':name,
                    'description':detail+' Sample catalogue price and stock for project demonstration. Photo is illustrative. '+credit(key),
                    'price_paise':price,'initial_stock':stock,'low_stock_threshold':5,'active':True,
                })
                state['products'][sku]={'id':row['id'],'name':name,'photo':key};save()
            row=call('GET',f'/shop/products/{state["products"][sku]["id"]}')
            assert row['sku']==sku and row['active'] and row['category_active']
            if not row['image_path']:upload(f'/shop/products/{row["id"]}',row,key)
            print('Shop ready:',name,flush=True)
        for record in state['adoption'].values():
            row=call('GET',f'/adoption/listings/{record["id"]}')
            assert row['status']=='available' and row['image_path']
            r=api.get(f'/adoption/listings/{row["id"]}/image');r.raise_for_status();assert r.content.startswith(b'\xff\xd8\xff')
        for record in state['products'].values():
            row=call('GET',f'/shop/products/{record["id"]}')
            assert row['active'] and row['category_active'] and row['stock']>0 and row['image_path']
            r=api.get(f'/shop/products/{row["id"]}/image');r.raise_for_status();assert r.content.startswith(b'\xff\xd8\xff')
        state.update({'status':'complete','actor':'admin@paw.local','adoption_count':10,'product_count':10,'sample_data':True})
        save();print('Verified 10 available adoption listings and 10 published products, each with a working photo.')


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if sys.argv[1]=='prepare':
        with ThreadPoolExecutor(max_workers=4) as pool:photos=list(pool.map(download,PHOTOS))
        (OUT/'photo-sources.json').write_text(json.dumps(photos,indent=2,ensure_ascii=False),encoding='utf-8')
        print('Downloaded',len(photos),'reference photos; source/license manifest saved.')
    elif sys.argv[1]=='import':run_import()
