"""Permission-scoped activity reports and spreadsheet-safe CSV exports."""
import csv
import io
from datetime import date, timedelta

from fastapi import HTTPException
from fastapi.responses import Response
from backend import db


def activity_report(user, start: date | None, end: date | None, actor_id: int | None = None):
    end = end or date.today()
    start = start or end - timedelta(days=30)
    if end < start or (end-start).days > 366:
        raise HTTPException(422, 'Choose an ordered date range of at most 366 days')
    if user['role'] != 'admin':
        if actor_id is not None and actor_id != user['id']:
            raise HTTPException(403, 'Only administrators can report on another user')
        actor_id = user['id']
    with db.connection() as conn:
        conn.execute("SET LOCAL TIME ZONE 'UTC'")
        people = conn.execute('''SELECT u.id,u.name,u.email,u.role,
            count(a.id) AS activity_count,
            count(a.id) FILTER(WHERE a.action='INSERT') AS created,
            count(a.id) FILTER(WHERE a.action='UPDATE') AS updated,
            count(a.id) FILTER(WHERE a.action='DELETE') AS deleted,
            count(a.id) FILTER(WHERE a.action='LOGIN') AS logins,
            max(a.created_at) AS last_activity
            FROM users u LEFT JOIN audit_logs a ON
            coalesce(a.actor_id,CASE WHEN a.entity='users' AND a.action='INSERT' THEN a.entity_id END)=u.id
            AND a.created_at >= %s::date AND a.created_at < %s::date + interval '1 day'
            WHERE (%s::bigint IS NULL OR u.id=%s) GROUP BY u.id ORDER BY u.id''',
            (start,end,actor_id,actor_id)).fetchall()
        events = conn.execute('''SELECT entity,action,count(*) AS count FROM audit_logs
            WHERE created_at >= %s::date AND created_at < %s::date + interval '1 day'
            AND (%s::bigint IS NULL OR coalesce(actor_id,CASE WHEN entity='users' AND action='INSERT' THEN entity_id END)=%s)
            GROUP BY entity,action ORDER BY entity,action''', (start,end,actor_id,actor_id)).fetchall()
    return {'start': start, 'end': end, 'timezone': 'UTC', 'users': people,
            'events': events, 'total_events': sum(row['count'] for row in events)}


def activity_csv(report):
    output = io.StringIO(newline='')
    columns = ['id','name','email','role','activity_count','created','updated','deleted','logins','last_activity']
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in report['users']:
        values = []
        for key in columns:
            value = '' if row[key] is None else str(row[key])
            if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return Response(output.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="paw-activity.csv"'})
