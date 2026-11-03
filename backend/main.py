import logging
import hashlib
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from backend.photos import save_image, delete_image, image_response
from datetime import date

import psycopg
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from psycopg_pool import PoolTimeout

from backend import db
from backend.models import Booking, Login, Medical, Pet, Registration, Slot, UserUpdate, Vaccination, Vet
from backend.security import decode_token, hash_password, issue_token, secret, verify_password
from backend.security import token_claims
from backend.models import RecoveryRequest, ProfileUpdate, PasswordChange, PasswordReset
from backend.models import Medication
from backend.mail import deliver_reset
from backend.reports import activity_report, activity_csv
from backend.adoption import create_router
from backend.shop import create_router as create_shop_router

load_dotenv()
log = logging.getLogger('paw')
bearer = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(app):
    secret()
    db.open_pool()
    try:
        yield
    finally:
        db.close_pool()


app = FastAPI(title='Paw Protectors', version='1.0.0', lifespan=lifespan)
project_root = Path(__file__).resolve().parents[1]
website_dir = project_root / 'website'
react_checkout = (website_dir / 'package.json').is_file()
react_dir = (website_dir / 'dist' if react_checkout else
             project_root / 'github-ready' / 'paw-protectors-web' / 'website' / 'dist')
if not react_checkout:
    app.mount('/website', StaticFiles(directory=website_dir, html=True), name='website')


@app.get('/', include_in_schema=False)
def website_home():
    if react_checkout:
        return react_home()
    return FileResponse(website_dir / 'index.html')


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    code = exc.sqlstate
    status, message = {
        '23505': (409, 'Resource already exists or slot already booked'),
        '23503': (409, 'Referenced resource missing or still in use'),
        '23514': (422, 'Database constraint failed'),
        '42501': (403, 'Operation forbidden'),
        'P0002': (404, 'Resource not found'),
        'P0001': (409, 'Slot is unavailable'),
        '40001': (409, 'Concurrent transaction: retry the operation'),
        '40P01': (409, 'Deadlock recovered: retry the operation'),
        '57014': (503, 'Database operation timed out'),
    }.get(code, (503, 'Database unavailable'))
    if status == 503:
        log.exception('Database operation failed')
    return JSONResponse(status_code=status, content={'detail': message})


@app.exception_handler(PoolTimeout)
async def pool_timeout(request, exc):
    return JSONResponse(status_code=503, content={'detail': 'Server busy; retry shortly'})


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials:
        raise HTTPException(401, 'Login required')
    try:
        claims = token_claims(credentials.credentials)
        uid = claims['sub']
    except ValueError:
        raise HTTPException(401, 'Invalid or expired session')
    with db.connection() as conn:
        if conn.execute('SELECT 1 FROM revoked_sessions WHERE token_hash=%s',(hashlib.sha256(credentials.credentials.encode()).hexdigest(),)).fetchone():
            raise HTTPException(401, 'Session logged out')
        user = conn.execute('SELECT id,name,email,role,active,session_version FROM users WHERE id=%s', (uid,)).fetchone()
    if not user or not user['active'] or user['session_version'] != claims['ver']:
        raise HTTPException(401, 'Account unavailable')
    user.pop('session_version')
    return user


def roles(*allowed):
    def check(user=Depends(current_user)):
        if user['role'] not in allowed:
            raise HTTPException(403, 'Role not authorized')
        return user
    return check


def pet_access(conn, pet_id, user, clinical=False):
    query = ('SELECT p.*,u.name AS owner_name FROM pets p JOIN users u ON u.id=p.owner_id WHERE p.id=%s'
             if user['role']=='admin' else 'SELECT * FROM pets WHERE id=%s')
    pet = conn.execute(query, (pet_id,)).fetchone()
    if not pet:
        raise HTTPException(404, 'Pet not found')
    if user['role'] == 'admin' or pet['owner_id'] == user['id']:
        return pet
    if clinical and user['role'] == 'vet':
        linked = conn.execute('SELECT 1 FROM appointments a JOIN appointment_slots s ON s.id=a.slot_id JOIN veterinarians v ON v.id=s.veterinarian_id WHERE a.pet_id=%s AND v.user_id=%s AND a.status IN (\'booked\',\'completed\')', (pet_id,user['id'])).fetchone()
        if linked:
            return pet
    raise HTTPException(403, 'Pet access denied')


app.include_router(create_router(current_user, roles))
app.include_router(create_shop_router(current_user, roles))

# Both clients use this service. Serve the built React client at /app.
if (react_dir / 'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=react_dir / 'assets'), name='react-assets')


@app.get('/app', include_in_schema=False)
def react_home():
    if not (react_dir / 'index.html').is_file():
        raise HTTPException(503, 'Build the React JS client first with npm ci and npm run build in the React website directory, then restart the backend.')
    return FileResponse(react_dir / 'index.html')


@app.get('/health')
def health():
    with db.connection() as conn:
        conn.execute('SELECT 1').fetchone()
    return {'status': 'ok', 'database': 'postgresql'}


@app.post('/auth/register', status_code=201)
def register(data: Registration):
    with db.connection() as conn:
        user = conn.execute('INSERT INTO users(name,email,password_hash) VALUES(%s,%s,%s) RETURNING id,name,email,role', (data.name,data.email,hash_password(data.password))).fetchone()
    return {'token': issue_token(user['id']), 'user': user}


@app.post('/auth/login')
def login(data: Login):
    with db.connection() as conn:
        user = conn.execute('SELECT * FROM users WHERE email=%s FOR UPDATE', (data.email.strip().lower(),)).fetchone()
        if not user or not user['active'] or not verify_password(data.password,user['password_hash']):
            raise HTTPException(401, 'Invalid credentials')
        conn.execute("INSERT INTO audit_logs(actor_id,entity,entity_id,action) VALUES(%s,'users',%s,'LOGIN')", (user['id'],user['id']))
    return {'token': issue_token(user['id'], user['session_version']), 'user': {k:user[k] for k in ('id','name','email','role')}}


def auth_result(user):
    return {'token': issue_token(user['id'], user['session_version']),
            'user': {k: user[k] for k in ('id', 'name', 'email', 'role', 'active')}}


def locked_account(conn, user, credentials):
    account = conn.execute('SELECT * FROM users WHERE id=%s FOR UPDATE', (user['id'],)).fetchone()
    if not account['active'] or account['session_version'] != token_claims(credentials.credentials)['ver']:
        raise HTTPException(401, 'Session expired; log in again')
    return account


@app.put('/auth/profile')
def edit_profile(data: ProfileUpdate, user=Depends(current_user), credentials=Depends(bearer)):
    with db.connection(user['id']) as conn:
        account = locked_account(conn, user, credentials)
        if not verify_password(data.current_password, account['password_hash']):
            raise HTTPException(403, 'Current password is incorrect')
        # Changing the login address invalidates other sessions and outstanding recovery codes.
        changed = data.email != account['email']
        account = conn.execute('UPDATE users SET name=%s,email=%s,session_version=session_version+%s WHERE id=%s RETURNING *',
                               (data.name, data.email, int(changed), user['id'])).fetchone()
        if changed:
            conn.execute('DELETE FROM password_resets WHERE user_id=%s', (user['id'],))
    return auth_result(account)


@app.post('/auth/change-password')
def change_password(data: PasswordChange, user=Depends(current_user), credentials=Depends(bearer)):
    with db.connection(user['id']) as conn:
        account = locked_account(conn, user, credentials)
        if not verify_password(data.current_password, account['password_hash']):
            raise HTTPException(403, 'Current password is incorrect')
        account = conn.execute('UPDATE users SET password_hash=%s,session_version=session_version+1 WHERE id=%s RETURNING *',
                               (hash_password(data.new_password), user['id'])).fetchone()
        conn.execute('DELETE FROM password_resets WHERE user_id=%s', (user['id'],))
    return auth_result(account)


@app.post('/auth/forgot-password', status_code=202)
def forgot_password(data: RecoveryRequest, request: Request):
    response = {'message': 'If this account is eligible, a recovery code has been sent. It expires in 15 minutes.'}
    # Hash rate-limit keys so the table stores neither addresses nor IPs.
    key = hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
    with db.connection() as conn:
        conn.execute("DELETE FROM recovery_rate_limits WHERE window_at < now()-interval '1 day'")
        limit = conn.execute("""INSERT INTO recovery_rate_limits(key_hash) VALUES(%s)
            ON CONFLICT(key_hash) DO UPDATE SET
            attempts=CASE WHEN recovery_rate_limits.window_at < now()-interval '1 hour' THEN 1 ELSE recovery_rate_limits.attempts+1 END,
            window_at=CASE WHEN recovery_rate_limits.window_at < now()-interval '1 hour' THEN now() ELSE recovery_rate_limits.window_at END
            RETURNING attempts""", (key,)).fetchone()
        if limit['attempts'] > 10:
            return response
        account = conn.execute('SELECT id FROM users WHERE email=%s AND active FOR UPDATE', (data.email,)).fetchone()
        if not account:
            return response
        previous = conn.execute("SELECT 1 FROM password_resets WHERE user_id=%s AND requested_at > now()-interval '1 minute'", (account['id'],)).fetchone()
        if previous:
            return response
        token = secrets.token_urlsafe(32)
        conn.execute("""INSERT INTO password_resets(user_id,token_hash,expires_at) VALUES(%s,%s,now()+interval '15 minutes')
            ON CONFLICT(user_id) DO UPDATE SET token_hash=EXCLUDED.token_hash,expires_at=EXCLUDED.expires_at,requested_at=now()""",
                     (account['id'], hashlib.sha256(token.encode()).hexdigest()))
        try:
            deliver_reset(data.email, token)
        except Exception:
            # Do not log tokens, addresses, SMTP credentials, or reveal account existence.
            log.error('Password recovery delivery failed; check mailbox configuration')
            conn.execute('DELETE FROM password_resets WHERE user_id=%s', (account['id'],))
    return response


@app.post('/auth/reset-password')
def reset_password(data: PasswordReset):
    digest = hashlib.sha256(data.token.encode()).hexdigest()
    with db.connection() as conn:
        # All credential-changing paths lock the account before locking/deleting its reset row.
        account = conn.execute('SELECT u.* FROM users u JOIN password_resets r ON r.user_id=u.id WHERE r.token_hash=%s FOR UPDATE OF u', (digest,)).fetchone()
        if not account or not account['active']:
            raise HTTPException(400, 'Invalid or expired recovery code')
        consumed = conn.execute('DELETE FROM password_resets WHERE user_id=%s AND token_hash=%s AND expires_at>now() RETURNING user_id', (account['id'], digest)).fetchone()
        if not consumed:
            raise HTTPException(400, 'Invalid or expired recovery code')
        conn.execute("SELECT set_config('app.actor_id', %s, true)", (str(account['id']),))
        conn.execute('UPDATE users SET password_hash=%s,session_version=session_version+1 WHERE id=%s', (hash_password(data.new_password), account['id']))
    return {'message': 'Password reset. Log in with your new password.'}


@app.get('/auth/me')
def me(user=Depends(current_user)):
    return user


@app.post('/auth/logout',status_code=204)
def logout(user=Depends(current_user),credentials:HTTPAuthorizationCredentials=Depends(bearer)):
    with db.connection(user['id']) as conn:
        conn.execute('INSERT INTO revoked_sessions(token_hash,user_id) VALUES(%s,%s) ON CONFLICT DO NOTHING',(hashlib.sha256(credentials.credentials.encode()).hexdigest(),user['id']))
        conn.execute("INSERT INTO audit_logs(actor_id,entity,entity_id,action) VALUES(%s,'users',%s,'LOGOUT')", (user['id'],user['id']))


@app.get('/pets')
def pets(user=Depends(current_user)):
    with db.connection() as conn:
        if user['role']=='admin':
            return conn.execute('SELECT p.*,u.name AS owner_name FROM pets p JOIN users u ON u.id=p.owner_id ORDER BY p.id DESC LIMIT 500').fetchall()
        if user['role']=='vet':
            return conn.execute('SELECT DISTINCT p.* FROM pets p JOIN appointments a ON a.pet_id=p.id JOIN appointment_slots s ON s.id=a.slot_id JOIN veterinarians v ON v.id=s.veterinarian_id WHERE v.user_id=%s AND a.status IN (\'booked\',\'completed\') LIMIT 500', (user['id'],)).fetchall()
        return conn.execute('SELECT * FROM pets WHERE owner_id=%s ORDER BY id DESC', (user['id'],)).fetchall()


@app.post('/pets', status_code=201)
def create_pet(data: Pet, user=Depends(roles('owner','admin'))):
    with db.connection(user['id']) as conn:
        row = conn.execute('INSERT INTO pets(owner_id,name,species,breed,age_months,gender,medical_notes,weight_kg,allergies) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *', (user['id'],data.name,data.species,data.breed,data.age_months,data.gender,data.medical_notes,data.weight_kg,data.allergies)).fetchone()
        return pet_access(conn,row['id'],user) if user['role']=='admin' else row


@app.get('/pets/{pet_id}')
def pet(pet_id:int,user=Depends(current_user)):
    with db.connection() as conn:
        return pet_access(conn,pet_id,user,True)


@app.put('/pets/{pet_id}')
def edit_pet(pet_id:int,data:Pet,user=Depends(current_user)):
    with db.connection(user['id']) as conn:
        pet_access(conn,pet_id,user)
        row = conn.execute('UPDATE pets SET name=%s,species=%s,breed=%s,age_months=%s,gender=%s,medical_notes=%s,weight_kg=CASE WHEN %s THEN %s ELSE weight_kg END,allergies=CASE WHEN %s THEN %s ELSE allergies END WHERE id=%s RETURNING *', (data.name,data.species,data.breed,data.age_months,data.gender,data.medical_notes,'weight_kg' in data.model_fields_set,data.weight_kg,'allergies' in data.model_fields_set,data.allergies,pet_id)).fetchone()
        return pet_access(conn,pet_id,user) if user['role']=='admin' else row


@app.delete('/pets/{pet_id}', status_code=204)
def delete_pet(pet_id:int,user=Depends(current_user)):
    with db.connection(user['id']) as conn:
        pet_access(conn,pet_id,user)
        conn.execute('DELETE FROM pets WHERE id=%s',(pet_id,))


@app.post('/pets/{pet_id}/image')
def upload_image(pet_id:int,file:UploadFile=File(...),user=Depends(current_user)):
    with db.connection() as conn:
        pet_access(conn,pet_id,user)
    content=file.file.read(5*1024*1024+1)
    if len(content)>5*1024*1024:
        raise HTTPException(413,'Image limit is 5 MB')
    extension = '.jpg' if content.startswith(b'\xff\xd8\xff') else '.png' if content.startswith(b'\x89PNG\r\n\x1a\n') else None
    if not extension:
        raise HTTPException(422,'Select a JPEG or PNG image')
    filename=save_image(content,extension)
    try:
        with db.connection(user['id']) as conn:
            pet_access(conn,pet_id,user)
            conn.execute('UPDATE pets SET image_path=%s WHERE id=%s',(filename,pet_id))
    except Exception:
        delete_image(filename)
        raise
    return {'image_path':filename}


@app.get('/pets/{pet_id}/image')
def get_image(pet_id:int,user=Depends(current_user)):
    with db.connection() as conn:
        data=pet_access(conn,pet_id,user,True)
    return image_response(data['image_path'])


@app.get('/veterinarians')
def veterinarians(user=Depends(current_user)):
    with db.connection() as conn:
        return conn.execute('SELECT v.*,u.name,u.email FROM veterinarians v JOIN users u ON u.id=v.user_id WHERE u.active ORDER BY u.name').fetchall()


def vet_access(conn,vid,user):
    vet=conn.execute('SELECT * FROM veterinarians WHERE id=%s',(vid,)).fetchone()
    if not vet:
        raise HTTPException(404,'Veterinarian not found')
    if user['role']!='admin' and vet['user_id']!=user['id']:
        raise HTTPException(403,'Veterinarian access denied')
    return vet


@app.post('/veterinarians',status_code=201)
def create_vet(data:Vet,user=Depends(roles('admin'))):
    with db.connection(user['id']) as conn:
        account=conn.execute('SELECT role FROM users WHERE id=%s FOR UPDATE',(data.user_id,)).fetchone()
        if not account or account['role']!='vet':
            raise HTTPException(422,'Assign vet role to the user first')
        return conn.execute('INSERT INTO veterinarians(user_id,specialization,clinic,available) VALUES(%s,%s,%s,%s) RETURNING *',(data.user_id,data.specialization,data.clinic,data.available)).fetchone()


@app.put('/veterinarians/{vet_id}')
def edit_vet(vet_id:int,data:Vet,user=Depends(roles('vet','admin'))):
    with db.connection(user['id']) as conn:
        vet=vet_access(conn,vet_id,user)
        if data.user_id!=vet['user_id']:
            raise HTTPException(422,'Veterinarian account cannot be reassigned')
        return conn.execute('UPDATE veterinarians SET specialization=%s,clinic=%s,available=%s WHERE id=%s RETURNING *',(data.specialization,data.clinic,data.available,vet_id)).fetchone()


@app.get('/slots')
def slots(veterinarian_id:int|None=None,user=Depends(current_user)):
    with db.connection() as conn:
        return conn.execute('SELECT * FROM available_slots WHERE (%s::bigint IS NULL OR veterinarian_id=%s) ORDER BY starts_at LIMIT 500',(veterinarian_id,veterinarian_id)).fetchall()


@app.post('/slots',status_code=201)
def create_slot(data:Slot,user=Depends(roles('vet','admin'))):
    with db.connection(user['id']) as conn:
        vet_access(conn,data.veterinarian_id,user)
        return conn.execute('INSERT INTO appointment_slots(veterinarian_id,starts_at,ends_at) VALUES(%s,%s,%s) RETURNING *',(data.veterinarian_id,data.starts_at,data.ends_at)).fetchone()


@app.delete('/slots/{slot_id}',status_code=204)
def delete_slot(slot_id:int,user=Depends(roles('vet','admin'))):
    with db.connection(user['id']) as conn:
        slot=conn.execute('SELECT * FROM appointment_slots WHERE id=%s FOR UPDATE',(slot_id,)).fetchone()
        if not slot:
            raise HTTPException(404,'Slot not found')
        vet_access(conn,slot['veterinarian_id'],user)
        conn.execute('DELETE FROM appointment_slots WHERE id=%s',(slot_id,))


@app.post('/appointments',status_code=201)
def book(data:Booking,user=Depends(roles('owner','admin'))):
    with db.connection(user['id']) as conn:
        row=conn.execute('SELECT book_appointment(%s,%s,%s,%s) AS id',(data.slot_id,data.pet_id,user['id'],data.reason)).fetchone()
        return conn.execute('SELECT * FROM appointment_details WHERE id=%s',(row['id'],)).fetchone()


@app.get('/appointments')
def appointments(user=Depends(current_user)):
    with db.connection() as conn:
        if user['role']=='admin':
            return conn.execute('SELECT * FROM appointment_details ORDER BY starts_at DESC LIMIT 500').fetchall()
        if user['role']=='vet':
            return conn.execute('SELECT a.* FROM appointment_details a JOIN veterinarians v ON v.id=a.veterinarian_id WHERE v.user_id=%s ORDER BY starts_at DESC LIMIT 500',(user['id'],)).fetchall()
        return conn.execute('SELECT * FROM appointment_details WHERE owner_id=%s ORDER BY starts_at DESC',(user['id'],)).fetchall()


def appointment_action(aid,user,target):
    with db.connection(user['id']) as conn:
        a=conn.execute('SELECT a.*,v.user_id AS vet_user FROM appointments a JOIN appointment_slots s ON s.id=a.slot_id JOIN veterinarians v ON v.id=s.veterinarian_id WHERE a.id=%s FOR UPDATE OF a',(aid,)).fetchone()
        if not a:
            raise HTTPException(404,'Appointment not found')
        authorized=user['role']=='admin' or a['vet_user']==user['id'] or (target=='cancelled' and a['owner_id']==user['id'])
        if not authorized:
            raise HTTPException(403,'Appointment access denied')
        if a['status']!='booked':
            raise HTTPException(409,'Appointment is no longer booked')
        return conn.execute('UPDATE appointments SET status=%s WHERE id=%s RETURNING *',(target,aid)).fetchone()


@app.post('/appointments/{appointment_id}/cancel')
def cancel(appointment_id:int,user=Depends(current_user)):
    return appointment_action(appointment_id,user,'cancelled')


@app.post('/appointments/{appointment_id}/complete')
def complete(appointment_id:int,user=Depends(roles('vet','admin'))):
    return appointment_action(appointment_id,user,'completed')


@app.get('/pets/{pet_id}/vaccinations')
def vaccinations(pet_id:int,user=Depends(current_user)):
    with db.connection() as conn:
        pet_access(conn,pet_id,user,True)
        return conn.execute('SELECT * FROM vaccination_records WHERE pet_id=%s ORDER BY administered_on DESC',(pet_id,)).fetchall()


@app.post('/pets/{pet_id}/vaccinations',status_code=201)
def add_vaccination(pet_id:int,data:Vaccination,user=Depends(current_user)):
    with db.connection(user['id']) as conn:
        pet_access(conn,pet_id,user,True)
        return conn.execute('INSERT INTO vaccination_records(pet_id,vaccine,administered_on,next_due) VALUES(%s,%s,%s,%s) RETURNING *',(pet_id,data.vaccine,data.administered_on,data.next_due)).fetchone()


@app.get('/pets/{pet_id}/medical-records')
def medical_records(pet_id:int,user=Depends(current_user)):
    with db.connection() as conn:
        pet_access(conn,pet_id,user,True)
        return conn.execute('SELECT m.*,u.name AS veterinarian_name FROM medical_records m JOIN veterinarians v ON v.id=m.veterinarian_id JOIN users u ON u.id=v.user_id WHERE pet_id=%s ORDER BY recorded_at DESC',(pet_id,)).fetchall()


@app.post('/pets/{pet_id}/medical-records',status_code=201)
def add_medical(pet_id:int,data:Medical,user=Depends(roles('vet'))):
    with db.connection(user['id']) as conn:
        pet_access(conn,pet_id,user,True)
        vet=conn.execute('SELECT id FROM veterinarians WHERE user_id=%s',(user['id'],)).fetchone()
        if not vet:
            raise HTTPException(409,'Veterinarian profile missing')
        return conn.execute('INSERT INTO medical_records(pet_id,veterinarian_id,diagnosis,treatment) VALUES(%s,%s,%s,%s) RETURNING *',(pet_id,vet['id'],data.diagnosis,data.treatment)).fetchone()


@app.get('/reminders')
def reminders(user=Depends(current_user)):
    with db.connection() as conn:
        return conn.execute('SELECT * FROM reminders WHERE owner_id=%s AND NOT acknowledged AND NOT cancelled ORDER BY due_at,id',(user['id'],)).fetchall()


@app.get('/pets/{pet_id}/medications')
def medications(pet_id: int, user=Depends(current_user)):
    with db.connection() as conn:
        pet_access(conn, pet_id, user, True)
        return conn.execute('SELECT * FROM medication_schedules WHERE pet_id=%s ORDER BY starts_at DESC LIMIT 500', (pet_id,)).fetchall()


@app.post('/pets/{pet_id}/medications', status_code=201)
def add_medication(pet_id: int, data: Medication, user=Depends(current_user)):
    with db.connection(user['id']) as conn:
        pet_access(conn, pet_id, user, True)
        return conn.execute('INSERT INTO medication_schedules(pet_id,name,dosage,instructions,starts_at,ends_at,interval_hours) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                            (pet_id,data.name,data.dosage,data.instructions,data.starts_at,data.ends_at,data.interval_hours)).fetchone()


@app.post('/pets/{pet_id}/medications/{medication_id}/stop')
def stop_medication(pet_id: int, medication_id: int, user=Depends(current_user)):
    with db.connection(user['id']) as conn:
        pet_access(conn, pet_id, user, True)
        row = conn.execute('UPDATE medication_schedules SET active=false WHERE id=%s AND pet_id=%s RETURNING *', (medication_id, pet_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Medication schedule not found')
        return row


@app.get('/notifications')
def notifications(read: bool | None = None, offset: int = 0, user=Depends(current_user)):
    if offset < 0:
        raise HTTPException(422, 'Offset must be non-negative')
    with db.connection() as conn:
        return conn.execute('SELECT * FROM reminders WHERE owner_id=%s AND NOT cancelled AND (%s::boolean IS NULL OR (read_at IS NOT NULL)=%s) ORDER BY due_at DESC,id DESC LIMIT 100 OFFSET %s',
                            (user['id'],read,read,offset)).fetchall()


@app.post('/notifications/{notification_id}/read')
def read_notification(notification_id: int, user=Depends(current_user)):
    with db.connection() as conn:
        row = conn.execute('UPDATE reminders SET read_at=coalesce(read_at,now()) WHERE id=%s AND owner_id=%s AND NOT cancelled RETURNING *', (notification_id,user['id'])).fetchone()
        if not row:
            raise HTTPException(404, 'Notification not found')
        return row


@app.post('/reminders/{reminder_id}/acknowledge')
def acknowledge(reminder_id:int,user=Depends(current_user)):
    with db.connection(user['id']) as conn:
        conn.execute('CALL acknowledge_reminder(%s,%s)',(reminder_id,user['id']))
        return conn.execute('SELECT * FROM reminders WHERE id=%s',(reminder_id,)).fetchone()


@app.get('/admin/users')
def users(user=Depends(roles('admin'))):
    with db.connection() as conn:
        return conn.execute('SELECT id,name,email,role,active FROM users ORDER BY id LIMIT 500').fetchall()


@app.get('/reports/activity')
def report_activity(start: date | None = None, end: date | None = None, actor_id: int | None = None,
                    format: str = 'json', user=Depends(current_user)):
    if format not in ('json', 'csv'):
        raise HTTPException(422, 'Choose json or csv format')
    report = activity_report(user, start, end, actor_id)
    return activity_csv(report) if format == 'csv' else report


@app.put('/admin/users/{user_id}')
def update_user(user_id:int,data:UserUpdate,user=Depends(roles('admin'))):
    if user_id==user['id'] and (not data.active or data.role!='admin'):
        raise HTTPException(409,'Cannot disable your own admin access')
    with db.connection(user['id']) as conn:
        if data.role!='vet' and conn.execute('SELECT 1 FROM veterinarians WHERE user_id=%s',(user_id,)).fetchone():
            raise HTTPException(409,'Veterinarian role is required by its profile')
        row=conn.execute('UPDATE users SET role=%s,active=%s WHERE id=%s RETURNING id,name,email,role,active',(data.role,data.active,user_id)).fetchone()
        if not row:
            raise HTTPException(404,'User not found')
        return row


@app.get('/admin/analytics')
def analytics(user=Depends(roles('admin'))):
    with db.connection() as conn:
        return conn.execute("SELECT (SELECT count(*) FROM users) AS users,(SELECT count(*) FROM pets) AS pets,(SELECT count(*) FROM veterinarians) AS veterinarians,(SELECT count(*) FROM appointments WHERE status='booked') AS booked,(SELECT count(*) FROM appointments WHERE status='cancelled') AS cancelled,(SELECT count(*) FROM audit_logs) AS audit_events,(SELECT count(*) FROM adoption_listings WHERE status='pending_review') AS adoption_pending_review,(SELECT count(*) FROM adoption_listings WHERE status='available') AS adoption_available,(SELECT count(*) FROM adoption_applications WHERE status='pending') AS adoption_pending_applications,(SELECT count(*) FROM adoption_listings WHERE status='adopted') AS adoption_completed,(SELECT count(*) FROM shop_products WHERE active) AS shop_published_products,(SELECT count(*) FROM shop_orders WHERE status='placed') AS shop_new_orders,(SELECT count(*) FROM shop_products WHERE stock<=low_stock_threshold) AS shop_low_stock").fetchone()


@app.get('/admin/audit')
def audit(user=Depends(roles('admin'))):
    with db.connection() as conn:
        return conn.execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT 200').fetchall()
