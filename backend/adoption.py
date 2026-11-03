"""Shared adoption workflow. All state changes lock the listing before applications."""
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from backend import db
from backend.adoption_models import Application, Decision, Listing, ListingEdit, Review

PUBLISHED = ('available', 'reserved', 'adopted')
EDITABLE = ('pending_review', 'available', 'rejected')
FIELDS = ('name','species','breed','age_months','gender','location','description','health_summary','weight_kg','allergies')


def fetch_listing(conn, listing_id, uid, lock=False):
    # Acquire the lock before calculating application counts. A projection in
    # the locking SELECT can otherwise use a snapshot taken before a waiter
    # acquired the lock and miss an application just committed by its holder.
    if lock:
        conn.execute('SELECT id FROM adoption_listings WHERE id=%s FOR UPDATE', (listing_id,)).fetchone()
    row = conn.execute('''SELECT l.*,u.active AS creator_active,u.name AS creator_name,
        (SELECT count(*) FROM adoption_applications a WHERE a.listing_id=l.id AND a.status IN ('pending','approved')) AS active_application_count,
        (SELECT a.id FROM adoption_applications a WHERE a.listing_id=l.id AND a.applicant_id=%s AND a.status IN ('pending','approved') LIMIT 1) AS own_active_application_id
        FROM adoption_listings l JOIN users u ON u.id=l.creator_id WHERE l.id=%s''', (uid,listing_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Adoption listing not found')
    return row


def visible(conn, row, user):
    if user['role']=='admin' or row['creator_id']==user['id'] or row['status'] in PUBLISHED:
        return
    if conn.execute('SELECT 1 FROM adoption_applications WHERE listing_id=%s AND applicant_id=%s', (row['id'],user['id'])).fetchone():
        return
    raise HTTPException(404, 'Adoption listing not found')


def present(row, user):
    result = dict(row)
    manager = user['role']=='admin' or (user['role']=='owner' and row['creator_id']==user['id'])
    result['can_manage'] = manager
    result['can_edit'] = manager and row['status'] in EDITABLE and not row['active_application_count']
    result['can_apply'] = user['role']=='owner' and row['creator_id']!=user['id'] and row['status']=='available' and row['creator_active'] and not row['own_active_application_id']
    for key in ('selected_application_id','adopted_pet_id','creator_active'):
        result.pop(key, None)
    if not manager:
        for key in ('moderation_reason','creator_name','active_application_count'):
            result.pop(key, None)
    return result


def history(conn, listing_id, actor_id, old, new, reason='', application_id=None):
    conn.execute('INSERT INTO adoption_history(listing_id,application_id,actor_id,from_status,to_status,reason) VALUES(%s,%s,%s,%s,%s,%s)',
                 (listing_id,application_id,actor_id,old,new,reason))


def administrators(conn):
    return [r['id'] for r in conn.execute("SELECT id FROM users WHERE role='admin' AND active ORDER BY id")]


def notify(conn, recipients, listing, event, message, application_id=None):
    for uid in sorted(set(recipients)):
        conn.execute('''INSERT INTO reminders(owner_id,kind,adoption_listing_id,adoption_application_id,event_key,due_at,message)
            VALUES(%s,%s,%s,%s,%s,now(),%s)
            ON CONFLICT(owner_id,event_key) WHERE event_key IS NOT NULL DO NOTHING''',
            (uid,'adoption_application' if application_id else 'adoption_listing',listing['id'],application_id,
             f'adoption:{listing["id"]}:{event}',f'{listing["name"]}: {message}'))


def editable(row, user, version):
    if user['role']!='admin' and not (user['role']=='owner' and row['creator_id']==user['id']):
        raise HTTPException(403, 'Only the submitter or an administrator can manage this listing')
    if row['version']!=version:
        raise HTTPException(409, 'Listing changed; refresh before continuing')
    if row['status'] not in EDITABLE or row['active_application_count']:
        raise HTTPException(409, 'Resolve active applications before editing; reserved/adopted/archived listings cannot be edited')


def application_view(conn, application_id, user):
    row = conn.execute('''SELECT a.*,l.name AS listing_name,l.status AS listing_status,u.name AS applicant_name,u.email AS applicant_email,
        CASE WHEN a.status='completed' THEN l.adopted_pet_id END AS adopted_pet_id
        FROM adoption_applications a JOIN adoption_listings l ON l.id=a.listing_id JOIN users u ON u.id=a.applicant_id WHERE a.id=%s''', (application_id,)).fetchone()
    if not row or (user['role']!='admin' and row['applicant_id']!=user['id']):
        raise HTTPException(404, 'Adoption application not found')
    row['history'] = conn.execute('SELECT id,from_status,to_status,reason,created_at FROM adoption_history WHERE application_id=%s ORDER BY id', (application_id,)).fetchall()
    return row


def reject_pending(conn, listing, actor_id, reason):
    rows = conn.execute("SELECT * FROM adoption_applications WHERE listing_id=%s AND status='pending' ORDER BY id FOR UPDATE", (listing['id'],)).fetchall()
    for app in rows:
        conn.execute("UPDATE adoption_applications SET status='rejected',decision_reason=%s,updated_at=now() WHERE id=%s", (reason,app['id']))
        history(conn,listing['id'],actor_id,'pending','rejected',reason,app['id'])
        notify(conn,[app['applicant_id']],listing,f'application:{app["id"]}:rejected','application closed: '+reason,app['id'])


def create_router(current_user, roles):
    router = APIRouter(prefix='/adoption', tags=['Adoption'])

    @router.get('/listings')
    def listings(scope: str='browse', status: str | None=None, q: str=Query('',max_length=100),
                 species: str=Query('',max_length=100), location: str=Query('',max_length=200),
                 max_age_months: int | None=Query(None,ge=0,le=1200),
                 offset: int=Query(0,ge=0,le=100000), limit: int=Query(20,ge=1,le=100), user=Depends(current_user)):
        if scope not in ('browse','mine','review'):
            raise HTTPException(422, 'Choose browse, mine or review')
        if scope=='review' and user['role']!='admin':
            raise HTTPException(403, 'Administrator access required')
        if scope=='mine' and user['role'] not in ('owner','admin'):
            raise HTTPException(403, 'Owner access required')
        status = status or ('available' if scope=='browse' else 'pending_review' if scope=='review' else 'all')
        allowed = PUBLISHED if scope=='browse' else (*EDITABLE,'reserved','adopted','archived','all')
        if status not in allowed:
            raise HTTPException(422, 'Invalid listing status for this view')
        where = '''WHERE (%(scope)s!='mine' OR l.creator_id=%(uid)s)
            AND (%(status)s='all' OR l.status=%(status)s)
            AND (%(scope)s!='browse' OR u.active)
            AND (%(q)s='' OR l.name ILIKE %(search)s OR l.breed ILIKE %(search)s OR l.description ILIKE %(search)s)
            AND (%(species)s='' OR lower(l.species)=lower(%(species)s))
            AND (%(location)s='' OR l.location ILIKE %(locsearch)s)
            AND (%(age)s::int IS NULL OR l.age_months<=%(age)s)'''
        params={'scope':scope,'uid':user['id'],'status':status,'q':q,'search':'%'+q+'%', 'species':species,'location':location,'locsearch':'%'+location+'%','age':max_age_months,'offset':offset,'limit':limit}
        with db.connection() as conn:
            total=conn.execute('SELECT count(*) AS n FROM adoption_listings l JOIN users u ON u.id=l.creator_id '+where,params).fetchone()['n']
            ids=conn.execute('SELECT l.id FROM adoption_listings l JOIN users u ON u.id=l.creator_id '+where+' ORDER BY l.id DESC LIMIT %(limit)s OFFSET %(offset)s',params).fetchall()
            items=[present(fetch_listing(conn,r['id'],user['id']),user) for r in ids]
        return {'items':items,'total':total,'offset':offset,'limit':limit}

    @router.post('/listings',status_code=201)
    def create_listing(data:Listing,user=Depends(roles('owner','admin'))):
        with db.connection(user['id']) as conn:
            state='available' if user['role']=='admin' else 'pending_review'
            values=[getattr(data,key) for key in FIELDS]
            row=conn.execute('''INSERT INTO adoption_listings(creator_id,name,species,breed,age_months,gender,location,description,health_summary,weight_kg,allergies,status)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',(user['id'],*values,state)).fetchone()
            history(conn,row['id'],user['id'],None,state,'Listing created')
            if state=='pending_review':
                notify(conn,administrators(conn),row,'submitted:1','new owner listing awaits approval')
            return present(fetch_listing(conn,row['id'],user['id']),user)

    @router.get('/listings/{listing_id}')
    def listing_details(listing_id:int,user=Depends(current_user)):
        with db.connection() as conn:
            row=fetch_listing(conn,listing_id,user['id']);visible(conn,row,user)
            result=present(row,user)
            result['history']=conn.execute('SELECT id,from_status,to_status,reason,created_at FROM adoption_history WHERE listing_id=%s AND application_id IS NULL ORDER BY id',(listing_id,)).fetchall() if result['can_manage'] else []
            return result

    @router.put('/listings/{listing_id}')
    def edit_listing(listing_id:int,data:ListingEdit,user=Depends(roles('owner','admin'))):
        with db.connection(user['id']) as conn:
            row=fetch_listing(conn,listing_id,user['id'],True);editable(row,user,data.version)
            state='pending_review' if user['role']=='owner' else row['status']
            conn.execute('''UPDATE adoption_listings SET name=%s,species=%s,breed=%s,age_months=%s,gender=%s,location=%s,description=%s,health_summary=%s,weight_kg=%s,allergies=%s,
                status=%s,moderation_reason='',version=version+1,updated_at=now() WHERE id=%s''',(*[getattr(data,k) for k in FIELDS],state,listing_id))
            history(conn,listing_id,user['id'],row['status'],state,'Listing details updated')
            if state=='pending_review':
                notify(conn,administrators(conn),row,f'submitted:{row["version"]+1}','listing updated; review required')
            return present(fetch_listing(conn,listing_id,user['id']),user)

    @router.post('/listings/{listing_id}/review')
    def review_listing(listing_id:int,data:Review,user=Depends(current_user)):
        with db.connection(user['id']) as conn:
            row=fetch_listing(conn,listing_id,user['id'],True)
            if user['role']!='admin' and not (data.action=='archive' and user['role']=='owner' and row['creator_id']==user['id']):
                raise HTTPException(403,'Only administrators can approve/reject listings')
            if data.version!=row['version']:
                raise HTTPException(409,'Listing changed; refresh before reviewing')
            if data.action in ('approve','reject') and row['status']!='pending_review':
                raise HTTPException(409,'Only listings awaiting review can be approved/rejected')
            if data.action=='approve' and not row['creator_active']:
                raise HTTPException(409,'Submitter account is inactive')
            if data.action=='reject' and not data.reason.strip():
                raise HTTPException(422,'Explain why this listing was rejected')
            if data.action=='archive' and row['status'] not in EDITABLE:
                raise HTTPException(409,'Resolve reservations first; adopted/archived listings retain their final state')
            state={'approve':'available','reject':'rejected','archive':'archived'}[data.action]
            if state=='archived':reject_pending(conn,row,user['id'],'Listing archived')
            conn.execute('UPDATE adoption_listings SET status=%s,moderation_reason=%s,version=version+1,updated_at=now() WHERE id=%s',(state,data.reason.strip(),listing_id))
            history(conn,listing_id,user['id'],row['status'],state,data.reason.strip())
            notify(conn,[row['creator_id']],row,f'listing:{row["version"]+1}',f'listing {state.replace("_"," ")}')
            return present(fetch_listing(conn,listing_id,user['id']),user)

    @router.post('/listings/{listing_id}/image')
    def upload_image(listing_id:int,version:int=Query(...,gt=0),file:UploadFile=File(...),user=Depends(roles('owner','admin'))):
        with db.connection() as conn:
            row=fetch_listing(conn,listing_id,user['id']);editable(row,user,version)
        content=file.file.read(5*1024*1024+1)
        if len(content)>5*1024*1024:raise HTTPException(413,'Image limit is 5 MB')
        extension='.jpg' if content.startswith(b'\xff\xd8\xff') else '.png' if content.startswith(b'\x89PNG\r\n\x1a\n') else None
        if not extension:raise HTTPException(422,'Select a JPEG or PNG image')
        directory=Path(os.getenv('UPLOAD_DIR','uploads'));directory.mkdir(parents=True,exist_ok=True)
        filename=uuid4().hex+extension;path=directory/filename;path.write_bytes(content)
        try:
            with db.connection(user['id']) as conn:
                row=fetch_listing(conn,listing_id,user['id'],True);editable(row,user,version)
                state='pending_review' if user['role']=='owner' else row['status']
                conn.execute('UPDATE adoption_listings SET image_path=%s,status=%s,moderation_reason=\'\',version=version+1,updated_at=now() WHERE id=%s',(filename,state,listing_id))
                history(conn,listing_id,user['id'],row['status'],state,'Listing photo updated')
                if state=='pending_review':notify(conn,administrators(conn),row,f'submitted:{version+1}','photo changed; review required')
                result=present(fetch_listing(conn,listing_id,user['id']),user)
        except Exception:
            path.unlink(missing_ok=True);raise
        return result

    @router.get('/listings/{listing_id}/image')
    def image(listing_id:int,user=Depends(current_user)):
        with db.connection() as conn:
            row=fetch_listing(conn,listing_id,user['id']);visible(conn,row,user)
        path=Path(os.getenv('UPLOAD_DIR','uploads'))/(row['image_path'] or '_missing')
        if not path.is_file():raise HTTPException(404,'No listing photo')
        return FileResponse(path)

    @router.post('/listings/{listing_id}/applications',status_code=201)
    def apply(listing_id:int,data:Application,user=Depends(roles('owner'))):
        with db.connection(user['id']) as conn:
            row=fetch_listing(conn,listing_id,user['id'],True);visible(conn,row,user)
            if row['creator_id']==user['id']:raise HTTPException(409,'You cannot apply for your own animal')
            if row['status']!='available' or not row['creator_active']:raise HTTPException(409,'This listing is not accepting applications')
            if row['own_active_application_id']:raise HTTPException(409,'You already have an active application for this animal')
            app=conn.execute('''INSERT INTO adoption_applications(listing_id,applicant_id,motivation,housing,has_other_pets,experience,contact_phone)
                VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *''',(listing_id,user['id'],data.motivation,data.housing,data.has_other_pets,data.experience,data.contact_phone)).fetchone()
            history(conn,listing_id,user['id'],None,'pending','Application submitted',app['id'])
            notify(conn,administrators(conn)+[row['creator_id']],row,f'application:{app["id"]}:submitted','new adoption application awaits administrator review',app['id'])
            notify(conn,[user['id']],row,f'application:{app["id"]}:receipt','application submitted',app['id'])
            return application_view(conn,app['id'],user)

    @router.get('/applications')
    def applications(scope:str='mine',listing_id:int | None=None,status:str='all',offset:int=Query(0,ge=0,le=100000),limit:int=Query(20,ge=1,le=100),user=Depends(current_user)):
        if scope not in ('mine','review'):raise HTTPException(422,'Choose mine or review')
        if scope=='review' and user['role']!='admin':raise HTTPException(403,'Administrator access required')
        if status not in ('all','pending','approved','rejected','withdrawn','completed'):raise HTTPException(422,'Invalid application status')
        params=(scope,user['id'],listing_id,listing_id,status,status)
        where="WHERE (%s='review' OR applicant_id=%s) AND (%s::bigint IS NULL OR listing_id=%s) AND (%s='all' OR status=%s)"
        with db.connection() as conn:
            total=conn.execute('SELECT count(*) AS n FROM adoption_applications '+where,params).fetchone()['n']
            ids=conn.execute('SELECT id FROM adoption_applications '+where+' ORDER BY id DESC LIMIT %s OFFSET %s',(*params,limit,offset)).fetchall()
            items=[application_view(conn,r['id'],user) for r in ids]
        return {'items':items,'total':total,'offset':offset,'limit':limit}

    @router.get('/applications/{application_id}')
    def application_details(application_id:int,user=Depends(current_user)):
        with db.connection() as conn:return application_view(conn,application_id,user)

    @router.post('/applications/{application_id}/decision')
    def decide(application_id:int,data:Decision,user=Depends(current_user)):
        with db.connection(user['id']) as conn:
            reference=conn.execute('SELECT listing_id,applicant_id FROM adoption_applications WHERE id=%s',(application_id,)).fetchone()
            if not reference or (user['role']!='admin' and reference['applicant_id']!=user['id']):raise HTTPException(404,'Adoption application not found')
            if data.action!='withdraw' and user['role']!='admin':raise HTTPException(403,'Administrator access required')
            if data.action=='withdraw' and reference['applicant_id']!=user['id']:raise HTTPException(403,'Only the applicant can withdraw')
            row=fetch_listing(conn,reference['listing_id'],user['id'],True)
            app=conn.execute('SELECT * FROM adoption_applications WHERE id=%s FOR UPDATE',(application_id,)).fetchone()
            old=app['status'];reason=data.reason.strip()
            if old not in ('pending','approved'):raise HTTPException(409,'Application is already closed')
            if data.action=='approve':
                if old!='pending' or row['status']!='available':raise HTTPException(409,'Another applicant already holds this animal, or the listing is unavailable')
                applicant=conn.execute('SELECT role,active FROM users WHERE id=%s FOR SHARE',(app['applicant_id'],)).fetchone()
                if not applicant['active'] or applicant['role']!='owner' or not row['creator_active']:raise HTTPException(409,'An involved account is unavailable')
                target='approved';listing_state='reserved'
                conn.execute("UPDATE adoption_listings SET status='reserved',selected_application_id=%s,version=version+1,updated_at=now() WHERE id=%s",(application_id,row['id']))
            elif data.action=='complete':
                if old!='approved' or row['status']!='reserved' or row['selected_application_id']!=application_id:raise HTTPException(409,'Approve and reserve this application before confirming handover')
                applicant=conn.execute('SELECT role,active FROM users WHERE id=%s FOR SHARE',(app['applicant_id'],)).fetchone()
                if not applicant['active'] or applicant['role']!='owner':raise HTTPException(409,'Adopter account is unavailable')
                pet=conn.execute('''INSERT INTO pets(owner_id,name,species,breed,age_months,gender,medical_notes,weight_kg,allergies,image_path)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',(app['applicant_id'],row['name'],row['species'],row['breed'],row['age_months'],row['gender'],row['health_summary'],row['weight_kg'],row['allergies'],row['image_path'])).fetchone()
                target='completed';listing_state='adopted'
                conn.execute("UPDATE adoption_listings SET status='adopted',adopted_pet_id=%s,version=version+1,updated_at=now() WHERE id=%s",(pet['id'],row['id']))
                reject_pending(conn,row,user['id'],'Animal has been adopted')
            else:
                if data.action=='reject' and not reason:raise HTTPException(422,'Explain why this application was rejected')
                target='withdrawn' if data.action=='withdraw' else 'rejected';listing_state=row['status']
                if old=='approved':
                    if row['status']!='reserved' or row['selected_application_id']!=application_id:raise HTTPException(409,'Reservation changed; refresh')
                    listing_state='available'
                    conn.execute("UPDATE adoption_listings SET status='available',selected_application_id=NULL,version=version+1,updated_at=now() WHERE id=%s",(row['id'],))
            conn.execute('UPDATE adoption_applications SET status=%s,decision_reason=%s,updated_at=now() WHERE id=%s',(target,reason,application_id))
            history(conn,row['id'],user['id'],old,target,reason,application_id)
            if listing_state!=row['status']:history(conn,row['id'],user['id'],row['status'],listing_state,'Application #'+str(application_id)+' '+target)
            notify(conn,administrators(conn)+[row['creator_id'],app['applicant_id']],row,f'application:{application_id}:{target}',f'application {target}',application_id)
            return application_view(conn,application_id,user)

    return router
