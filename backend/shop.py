"""Single-store shopping. Lock carts/orders first, then products in ID order."""
import hashlib
import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from backend import db
from backend.photos import save_image, delete_image, image_response
from backend.shop_models import Category, CategoryEdit, ProductCreate, ProductEdit, StockAdjustment, CartItem, Checkout, OrderDecision

PRODUCT_FIELDS = ('category_id', 'sku', 'name', 'description', 'price_paise', 'low_stock_threshold', 'active')


def versioned(row, version):
    if row['version'] != version:
        raise HTTPException(409, 'This record changed. Refresh and review before continuing.')


def product_row(conn, pid, lock=False):
    if lock:
        conn.execute('SELECT id FROM shop_products WHERE id=%s FOR UPDATE', (pid,)).fetchone()
    row = conn.execute('''SELECT p.*,c.name AS category_name,c.active AS category_active
        FROM shop_products p JOIN shop_categories c ON c.id=p.category_id WHERE p.id=%s''', (pid,)).fetchone()
    if not row:
        raise HTTPException(404, 'Product not found')
    return row


def published(row):
    return row['active'] and row['category_active']


def category_exists(conn, cid):
    # Share-lock the category through checkout/product updates so an archive
    # cannot race a publication/stock check.
    row = conn.execute('SELECT * FROM shop_categories WHERE id=%s FOR SHARE', (cid,)).fetchone()
    if not row:
        raise HTTPException(422, 'Choose an existing category')
    return row


def cart_lock(conn, uid):
    conn.execute('INSERT INTO shop_carts(user_id) VALUES(%s) ON CONFLICT DO NOTHING', (uid,))
    return conn.execute('SELECT * FROM shop_carts WHERE user_id=%s FOR UPDATE', (uid,)).fetchone()


def cart_view(conn, uid):
    cart = conn.execute('SELECT * FROM shop_carts WHERE user_id=%s', (uid,)).fetchone()
    items = conn.execute('''SELECT p.*,c.name AS category_name,c.active AS category_active,i.quantity,
        p.price_paise*i.quantity AS line_total_paise FROM shop_cart_items i
        JOIN shop_products p ON p.id=i.product_id JOIN shop_categories c ON c.id=p.category_id
        WHERE i.user_id=%s ORDER BY p.id''', (uid,)).fetchall()
    for row in items:
        row['available'] = bool(published(row) and row['stock'] >= row['quantity'])
    return {'version':cart['version'], 'items':items, 'currency':'INR', 'payment_method':'cod',
            'subtotal_paise':sum(r['line_total_paise'] for r in items), 'delivery_paise':0,
            'total_paise':sum(r['line_total_paise'] for r in items),
            'can_checkout':bool(items) and all(r['available'] for r in items)}


def order_view(conn, oid, user, lock=False):
    row = conn.execute('SELECT * FROM shop_orders WHERE id=%s'+(' FOR UPDATE' if lock else ''), (oid,)).fetchone()
    if not row or (user['role'] != 'admin' and row['user_id'] != user['id']):
        raise HTTPException(404, 'Order not found')
    row['items'] = conn.execute('SELECT * FROM shop_order_items WHERE order_id=%s ORDER BY product_id', (oid,)).fetchall()
    row['history'] = conn.execute('SELECT id,from_status,to_status,note,created_at FROM shop_order_history WHERE order_id=%s ORDER BY id', (oid,)).fetchall()
    return row


def movement(conn, pid, actor, delta, resulting, kind, reason, order=None):
    conn.execute('''INSERT INTO shop_stock_movements(product_id,actor_id,delta,resulting_stock,kind,reason,order_id)
        VALUES(%s,%s,%s,%s,%s,%s,%s)''', (pid,actor,delta,resulting,kind,reason,order))


def notify_order(conn, row, event):
    recipients = [row['user_id']] + [r['id'] for r in conn.execute("SELECT id FROM users WHERE role='admin' AND active")]
    for uid in sorted(set(recipients)):
        conn.execute('''INSERT INTO reminders(owner_id,kind,shop_order_id,event_key,due_at,message)
            VALUES(%s,'shop_order',%s,%s,now(),%s)
            ON CONFLICT(owner_id,event_key) WHERE event_key IS NOT NULL DO NOTHING''',
            (uid,row['id'],f'shop:{row["id"]}:{event}',f'Pet Shop order #{row["id"]}: {row["status"]}.'))


def create_router(current_user, roles):
    router = APIRouter(prefix='/shop', tags=['Pet Shop'])

    @router.get('/categories')
    def categories(user=Depends(current_user)):
        with db.connection() as conn:
            return conn.execute('SELECT * FROM shop_categories '+('' if user['role']=='admin' else 'WHERE active ')+'ORDER BY name,id').fetchall()

    @router.post('/categories', status_code=201)
    def add_category(body:Category, user=Depends(roles('admin'))):
        with db.connection(user['id']) as conn:
            return conn.execute('INSERT INTO shop_categories(name,active) VALUES(%s,%s) RETURNING *', (body.name,body.active)).fetchone()

    @router.put('/categories/{cid}')
    def edit_category(cid:int, body:CategoryEdit, user=Depends(roles('admin'))):
        with db.connection(user['id']) as conn:
            row=conn.execute('SELECT * FROM shop_categories WHERE id=%s FOR UPDATE',(cid,)).fetchone()
            if not row:raise HTTPException(404,'Category not found')
            versioned(row,body.version)
            return conn.execute('UPDATE shop_categories SET name=%s,active=%s,version=version+1 WHERE id=%s RETURNING *',(body.name,body.active,cid)).fetchone()

    @router.get('/products')
    def products(q:str=Query('',max_length=100), category_id:int|None=Query(None,gt=0),
                 min_price_paise:int|None=Query(None,ge=0), max_price_paise:int|None=Query(None,ge=0),
                 in_stock:bool=False, low_stock:bool=False, scope:str='browse',
                 offset:int=Query(0,ge=0,le=100000),limit:int=Query(12,ge=1,le=100),user=Depends(current_user)):
        if scope not in ('browse','manage'):raise HTTPException(422,'Choose browse or manage')
        if (scope=='manage' or low_stock) and user['role']!='admin':raise HTTPException(403,'Administrator access required')
        if min_price_paise is not None and max_price_paise is not None and min_price_paise>max_price_paise:raise HTTPException(422,'Minimum price exceeds maximum price')
        terms=[] if scope=='manage' else ['p.active','c.active'];params=[]
        if q:terms.append('(p.name ILIKE %s OR p.sku ILIKE %s OR p.description ILIKE %s)');params.extend(['%'+q+'%']*3)
        if category_id:terms.append('p.category_id=%s');params.append(category_id)
        if min_price_paise is not None:terms.append('p.price_paise>=%s');params.append(min_price_paise)
        if max_price_paise is not None:terms.append('p.price_paise<=%s');params.append(max_price_paise)
        if in_stock:terms.append('p.stock>0')
        if low_stock:terms.append('p.stock<=p.low_stock_threshold')
        base=' FROM shop_products p JOIN shop_categories c ON c.id=p.category_id'+(' WHERE '+' AND '.join(terms) if terms else '')
        with db.connection() as conn:
            total=conn.execute('SELECT count(*) AS n'+base,params).fetchone()['n']
            rows=conn.execute('SELECT p.*,c.name AS category_name,c.active AS category_active'+base+' ORDER BY p.id DESC LIMIT %s OFFSET %s',(*params,limit,offset)).fetchall()
            return {'items':rows,'total':total,'offset':offset,'limit':limit}

    @router.get('/products/{pid}')
    def product(pid:int,user=Depends(current_user)):
        with db.connection() as conn:
            row=product_row(conn,pid)
            if user['role']!='admin' and not published(row):raise HTTPException(404,'Product not found')
            if user['role']=='admin':row['stock_history']=conn.execute('SELECT * FROM shop_stock_movements WHERE product_id=%s ORDER BY id DESC LIMIT 100',(pid,)).fetchall()
            return row

    @router.post('/products',status_code=201)
    def add_product(body:ProductCreate,user=Depends(roles('admin'))):
        values=body.model_dump()
        with db.connection(user['id']) as conn:
            category_exists(conn,body.category_id)
            row=conn.execute('''INSERT INTO shop_products(category_id,sku,name,description,price_paise,low_stock_threshold,active,stock)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',(*[values[k] for k in PRODUCT_FIELDS],body.initial_stock)).fetchone()
            if body.initial_stock:movement(conn,row['id'],user['id'],body.initial_stock,body.initial_stock,'initial','Initial inventory')
            return product_row(conn,row['id'])

    @router.put('/products/{pid}')
    def edit_product(pid:int,body:ProductEdit,user=Depends(roles('admin'))):
        values=body.model_dump()
        with db.connection(user['id']) as conn:
            category_exists(conn,body.category_id)
            row=product_row(conn,pid,True);versioned(row,body.version)
            conn.execute('UPDATE shop_products SET '+','.join(k+'=%s' for k in PRODUCT_FIELDS)+',version=version+1,updated_at=now() WHERE id=%s',(*[values[k] for k in PRODUCT_FIELDS],pid))
            return product_row(conn,pid)

    @router.post('/products/{pid}/stock')
    def stock(pid:int,body:StockAdjustment,user=Depends(roles('admin'))):
        with db.connection(user['id']) as conn:
            row=product_row(conn,pid,True);versioned(row,body.version);result=row['stock']+body.delta
            if result<0 or result>1000000:raise HTTPException(409,'Stock must remain between zero and 1000000')
            conn.execute('UPDATE shop_products SET stock=%s,version=version+1,updated_at=now() WHERE id=%s',(result,pid))
            movement(conn,pid,user['id'],body.delta,result,'adjustment',body.reason)
            return product_row(conn,pid)

    @router.post('/products/{pid}/image')
    def upload(pid:int,version:int=Query(...,gt=0),file:UploadFile=File(...),user=Depends(roles('admin'))):
        content=file.file.read(5*1024*1024+1)
        if len(content)>5*1024*1024:raise HTTPException(413,'Image limit is 5 MB')
        ext='.jpg' if content.startswith(b'\xff\xd8\xff') else '.png' if content.startswith(b'\x89PNG\r\n\x1a\n') else None
        if not ext:raise HTTPException(422,'Select a JPEG or PNG image')
        name=save_image(content,ext)
        try:
            with db.connection(user['id']) as conn:
                row=product_row(conn,pid,True);versioned(row,version)
                conn.execute('UPDATE shop_products SET image_path=%s,version=version+1,updated_at=now() WHERE id=%s',(name,pid))
                return product_row(conn,pid)
        except Exception:
            delete_image(name);raise

    @router.get('/products/{pid}/image')
    def image(pid:int,user=Depends(current_user)):
        with db.connection() as conn:
            row=product_row(conn,pid)
            if user['role']!='admin' and not published(row) and not conn.execute('SELECT 1 FROM shop_order_items i JOIN shop_orders o ON o.id=i.order_id WHERE i.product_id=%s AND o.user_id=%s LIMIT 1',(pid,user['id'])).fetchone():raise HTTPException(404,'Product not found')
        return image_response(row['image_path'])

    @router.get('/cart')
    def cart(user=Depends(roles('owner','vet'))):
        with db.connection() as conn:
            cart_lock(conn,user['id']);return cart_view(conn,user['id'])

    @router.put('/cart/items/{pid}')
    def put_cart(pid:int,body:CartItem,user=Depends(roles('owner','vet'))):
        with db.connection() as conn:
            cart=cart_lock(conn,user['id']);versioned(cart,body.version)
            if body.quantity:
                row=product_row(conn,pid)
                if not published(row):raise HTTPException(409,'Product is unavailable')
                if body.quantity>row['stock']:raise HTTPException(409,'Requested quantity exceeds available stock')
                count=conn.execute('SELECT count(*) AS n FROM shop_cart_items WHERE user_id=%s',(user['id'],)).fetchone()['n']
                exists=conn.execute('SELECT 1 FROM shop_cart_items WHERE user_id=%s AND product_id=%s',(user['id'],pid)).fetchone()
                if count>=50 and not exists:raise HTTPException(409,'A cart can contain at most 50 products')
                conn.execute('INSERT INTO shop_cart_items(user_id,product_id,quantity) VALUES(%s,%s,%s) ON CONFLICT(user_id,product_id) DO UPDATE SET quantity=excluded.quantity',(user['id'],pid,body.quantity))
            else:conn.execute('DELETE FROM shop_cart_items WHERE user_id=%s AND product_id=%s',(user['id'],pid))
            conn.execute('UPDATE shop_carts SET version=version+1,updated_at=now() WHERE user_id=%s',(user['id'],))
            return cart_view(conn,user['id'])

    @router.post('/checkout',status_code=201)
    def checkout(body:Checkout,user=Depends(roles('owner','vet'))):
        fingerprint=hashlib.sha256(json.dumps(body.model_dump(mode='json'),sort_keys=True).encode()).hexdigest()
        with db.connection(user['id']) as conn:
            cart=cart_lock(conn,user['id'])
            existing=conn.execute('SELECT id,request_hash FROM shop_orders WHERE user_id=%s AND checkout_key=%s',(user['id'],body.checkout_key)).fetchone()
            if existing:
                if existing['request_hash']!=fingerprint:raise HTTPException(409,'Checkout key already used for a different request')
                return order_view(conn,existing['id'],user)
            versioned(cart,body.version)
            items=conn.execute('SELECT * FROM shop_cart_items WHERE user_id=%s ORDER BY product_id',(user['id'],)).fetchall()
            if not items:raise HTTPException(409,'Your cart is empty')
            # Lock categories before products, matching admin product updates.
            category_ids=conn.execute('SELECT DISTINCT p.category_id FROM shop_cart_items i JOIN shop_products p ON p.id=i.product_id WHERE i.user_id=%s ORDER BY p.category_id',(user['id'],)).fetchall()
            for c in category_ids:category_exists(conn,c['category_id'])
            products={i['product_id']:product_row(conn,i['product_id'],True) for i in items}
            for cid in sorted({p['category_id'] for p in products.values()}):
                if not category_exists(conn,cid)['active']:
                    raise HTTPException(409,'A category is unavailable. Review your cart.')
            for item in items:
                product=products[item['product_id']]
                if not published(product) or product['stock']<item['quantity']:raise HTTPException(409,f'{product["name"]} is unavailable or has insufficient stock. Review your cart.')
            total=sum(products[i['product_id']]['price_paise']*i['quantity'] for i in items)
            if total!=body.expected_total_paise:raise HTTPException(409,'Prices changed. Refresh your cart and review the new total.')
            row=conn.execute('''INSERT INTO shop_orders(user_id,checkout_key,request_hash,cart_version,customer_name,phone,address,city,state,postal_code,subtotal_paise,total_paise)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',(user['id'],body.checkout_key,fingerprint,body.version,body.customer_name,body.phone,body.address,body.city,body.state,body.postal_code,total,total)).fetchone()
            for item in items:
                p=products[item['product_id']];qty=item['quantity'];remaining=p['stock']-qty
                conn.execute('UPDATE shop_products SET stock=%s,version=version+1,updated_at=now() WHERE id=%s',(remaining,p['id']))
                conn.execute('''INSERT INTO shop_order_items(order_id,product_id,sku,name,unit_price_paise,quantity,line_total_paise)
                    VALUES(%s,%s,%s,%s,%s,%s,%s)''',(row['id'],p['id'],p['sku'],p['name'],p['price_paise'],qty,p['price_paise']*qty))
                movement(conn,p['id'],user['id'],-qty,remaining,'checkout','Stock reserved at checkout',row['id'])
            conn.execute("INSERT INTO shop_order_history(order_id,actor_id,to_status,note) VALUES(%s,%s,'placed','Cash on delivery; free delivery')",(row['id'],user['id']))
            notify_order(conn,row,'placed')
            conn.execute('DELETE FROM shop_cart_items WHERE user_id=%s',(user['id'],))
            conn.execute('UPDATE shop_carts SET version=version+1,updated_at=now() WHERE user_id=%s',(user['id'],))
            return order_view(conn,row['id'],user)

    @router.get('/orders')
    def orders(scope:str='mine',status:str='',offset:int=Query(0,ge=0,le=100000),limit:int=Query(12,ge=1,le=100),user=Depends(current_user)):
        if scope not in ('mine','all'):raise HTTPException(422,'Choose mine or all')
        if scope=='all' and user['role']!='admin':raise HTTPException(403,'Administrator access required')
        if status and status not in ('placed','confirmed','shipped','delivered','cancelled'):raise HTTPException(422,'Unknown order status')
        terms=[];params=[]
        if scope=='mine':terms.append('user_id=%s');params.append(user['id'])
        if status:terms.append('status=%s');params.append(status)
        where=' WHERE '+' AND '.join(terms) if terms else ''
        with db.connection() as conn:
            total=conn.execute('SELECT count(*) AS n FROM shop_orders'+where,params).fetchone()['n']
            # Lists deliberately omit delivery contact/address. Authorized detail contains it.
            rows=conn.execute('SELECT id,user_id,status,total_paise,currency,payment_method,payment_status,version,created_at FROM shop_orders'+where+' ORDER BY id DESC LIMIT %s OFFSET %s',(*params,limit,offset)).fetchall()
            return {'items':rows,'total':total,'offset':offset,'limit':limit}

    @router.get('/orders/{oid}')
    def order(oid:int,user=Depends(current_user)):
        with db.connection() as conn:return order_view(conn,oid,user)

    @router.post('/orders/{oid}/decision')
    def decision(oid:int,body:OrderDecision,user=Depends(current_user)):
        with db.connection(user['id']) as conn:
            row=order_view(conn,oid,user,True);versioned(row,body.version);admin=user['role']=='admin'
            if body.action!='cancel' and not admin:raise HTTPException(403,'Administrator access required')
            old=row['status'];new={'confirm':'confirmed','ship':'shipped','deliver':'delivered','cancel':'cancelled'}[body.action]
            if body.action=='cancel':
                if old not in (('placed','confirmed') if admin else ('placed',)):raise HTTPException(409,'This order can no longer be cancelled')
                if not body.note:raise HTTPException(422,'Cancellation reason is required')
                for item in row['items']:
                    p=product_row(conn,item['product_id'],True);result=p['stock']+item['quantity']
                    if result>1000000:raise HTTPException(409,'Restock would exceed the inventory limit; adjust inventory first')
                    conn.execute('UPDATE shop_products SET stock=%s,version=version+1,updated_at=now() WHERE id=%s',(result,p['id']))
                    movement(conn,p['id'],user['id'],item['quantity'],result,'cancellation',body.note,oid)
            elif old!={'confirm':'placed','ship':'confirmed','deliver':'shipped'}[body.action]:raise HTTPException(409,'Invalid order transition. Refresh the order.')
            conn.execute('''UPDATE shop_orders SET status=%s,payment_status=%s,tracking_reference=%s,version=version+1,updated_at=now() WHERE id=%s''',
                (new,'collected' if new=='delivered' else 'cancelled' if new=='cancelled' else 'pending',body.tracking_reference if body.action=='ship' else row['tracking_reference'],oid))
            conn.execute('INSERT INTO shop_order_history(order_id,actor_id,from_status,to_status,note) VALUES(%s,%s,%s,%s,%s)',(oid,user['id'],old,new,body.note))
            row['status']=new;notify_order(conn,row,new)
            return order_view(conn,oid,user)

    return router
