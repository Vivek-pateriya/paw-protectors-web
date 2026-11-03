import React, { useEffect, useId, useState } from 'react';
import { request } from './api';

const day = () => new Date().toISOString().slice(0,10);
const stamp = value => new Date(value).toLocaleString();
const password = name => ({ name, label: name === 'current_password' ? 'Current password' : name === 'confirm_password' ? 'Confirm new password' : 'New password (at least 10 characters)', type: 'password', minLength: name === 'new_password' ? 10 : 1, maxLength:128 });

function DataForm({ fields, submit, label }) {
  const formId=useId();
  const [error,setError] = useState(''), [busy,setBusy] = useState(false);
  return <form onSubmit={async event => {
    event.preventDefault();setBusy(true);setError('');
    const element=event.currentTarget;
    try {
      const values=Object.fromEntries(new FormData(element));
      for(const f of fields) {
        if(f.type==='number') values[f.name]=values[f.name]===''?null:Number(values[f.name]);
        if(f.type==='datetime-local') values[f.name]=new Date(values[f.name]).toISOString();
      }
      if(values.confirm_password!==undefined&&values.confirm_password!==values.new_password)throw new Error('Passwords do not match');
      delete values.confirm_password;
      await submit(values);element.reset();
    } catch(e){setError(e.message);}finally{setBusy(false);}
  }}>{fields.map(f=><React.Fragment key={f.name}><label htmlFor={`${formId}-${f.name}`}>{f.label}</label><input id={`${formId}-${f.name}`} name={f.name} type={f.type||'text'} defaultValue={f.value??''} required={f.required!==false} min={f.min} max={f.max} step={f.step} minLength={f.minLength} maxLength={f.maxLength} autoComplete={f.type==='password'?'off':undefined} disabled={busy}/></React.Fragment>)}{error&&<p role="alert" className="inline-error">{error}</p>}<div className="actions"><button className="btn" disabled={busy} type="submit">{busy?'Saving…':label}</button></div></form>;
}

export function Recovery() {
  const [notice,setNotice]=useState('');
  return <section><details><summary>Forgot password</summary><DataForm fields={[{name:'email',label:'Account email',type:'email'}]} label="Send recovery code" submit={async data=>{const result=await request('/auth/forgot-password','','POST',data);setNotice(result.message+' Local demo: ask the laptop operator for the private mailbox message.');}}/></details><details><summary>Enter recovery code</summary><DataForm fields={[{name:'token',label:'Recovery code',maxLength:128},password('new_password'),password('confirm_password')]} label="Reset password" submit={async data=>{const result=await request('/auth/reset-password','','POST',data);setNotice(result.message);}}/></details>{notice&&<p role="status">{notice}</p>}</section>;
}

export function CarePage({page,id,user,token,onSession}) {
  const [data,setData]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[revision,setRevision]=useState(0);
  const [offset,setOffset]=useState(0),[unread,setUnread]=useState(false);
  const [range,setRange]=useState({start:new Date(Date.now()-30*86400000).toISOString().slice(0,10),end:day()});
  const api=(path,method='GET',body)=>request(path,token,method,body);
  const reload=()=>setRevision(x=>x+1);
  async function act(fn){setError('');try{await fn();reload();}catch(e){setError(e.message);}}
  useEffect(()=>{
    const controller=new AbortController();setData(null);setError('');
    let path=page==='notifications'?`/notifications?offset=${offset}${unread?'&read=false':''}`:page==='reports'?`/reports/activity?start=${range.start}&end=${range.end}`:page==='medications'?`/pets/${id}/medications`:'/auth/me';
    request(path,token,'GET',undefined,controller.signal).then(setData).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return()=>controller.abort();
  },[page,id,token,revision,offset,unread,range]);
  return <><div className="page-header"><h1>{{account:'My account',notifications:'Notification centre',reports:'Activity report',medications:'Medication schedules'}[page]}</h1></div>{error&&<p role="alert" className="inline-error">{error}</p>}{notice&&<p role="status">{notice}</p>}{!data&&!error?<p>Loading…</p>:data&&<>
    {page==='account'&&<div className="two-col"><article className="card"><h2>Edit my profile</h2><DataForm key={user.email+user.name} fields={[{name:'name',label:'Full name',value:user.name,maxLength:120},{name:'email',label:'Email',value:user.email,type:'email'},password('current_password')]} label="Save profile" submit={async values=>{onSession(await api('/auth/profile','PUT',values));setNotice('Profile updated.');}}/></article><article className="card"><h2>Change password</h2><DataForm fields={[password('current_password'),password('new_password'),password('confirm_password')]} label="Change password" submit={async values=>{onSession(await api('/auth/change-password','POST',values));setNotice('Password changed. Other sessions have been signed out.');}}/></article></div>}
    {page==='medications'&&<><details className="card"><summary>Add medication schedule</summary><DataForm fields={[{name:'name',label:'Medication name',maxLength:200},{name:'dosage',label:'Prescribed dose',maxLength:500},{name:'instructions',label:'Instructions',required:false,maxLength:2000},{name:'starts_at',label:'First dose (local time)',type:'datetime-local'},{name:'ends_at',label:'Last dose (local time)',type:'datetime-local'},{name:'interval_hours',label:'Hours between doses',type:'number',value:24,min:1,max:720}]} label="Create schedule" submit={async values=>{await api(`/pets/${id}/medications`,'POST',values);reload();setNotice('Schedule created.');}}/></details>{data.map(m=><article className="row-card" key={m.id}><div><h3>{m.name} · {m.active?'Active':'Stopped'}</h3><p>{m.dosage} · every {m.interval_hours} hours</p><p>{stamp(m.starts_at)} – {stamp(m.ends_at)}</p><p>{m.instructions}</p></div>{m.active&&<button className="btn danger" onClick={()=>{if(confirm('Stop this schedule and cancel remaining reminders?'))void act(()=>api(`/pets/${id}/medications/${m.id}/stop`,'POST'));}}>Stop reminders</button>}</article>)}</>}
    {page==='notifications'&&<><button className="btn secondary" onClick={()=>{setUnread(!unread);setOffset(0);}}>{unread?'Show all':'Unread only'}</button>{data.map(n=><article className="row-card" key={n.id}><div><h3>{n.message}</h3><p>{stamp(n.due_at)} · {n.acknowledged?'Done':n.read_at?'Read':'Unread'}</p></div><div className="actions">{!n.read_at&&<button className="btn secondary" onClick={()=>void act(()=>api(`/notifications/${n.id}/read`,'POST'))}>Mark read</button>}{!n.acknowledged&&<button className="btn ghost" onClick={()=>void act(()=>api(`/reminders/${n.id}/acknowledge`,'POST'))}>Mark done</button>}</div></article>)}<div className="actions">{offset>0&&<button className="btn secondary" onClick={()=>setOffset(x=>x-100)}>Previous page</button>}{data.length===100&&<button className="btn secondary" onClick={()=>setOffset(x=>x+100)}>Next page</button>}</div></>}
    {page==='reports'&&<><p>{data.start} to {data.end} · {data.total_events} committed events. Historical activity appears only where auditing existed.</p><details><summary>Choose dates</summary><DataForm fields={[{name:'start',label:'From',type:'date',value:range.start},{name:'end',label:'Through',type:'date',value:range.end}]} label="Apply dates" submit={async values=>{if(values.end<values.start||(Date.parse(values.end)-Date.parse(values.start)>366*86400000))throw new Error('Choose an ordered range of at most 366 days');setRange(values);}}/></details><button className="btn" onClick={()=>void act(async()=>{const response=await fetch(`/reports/activity?start=${data.start}&end=${data.end}&format=csv`,{headers:{Authorization:`Bearer ${token}`}});if(!response.ok)throw new Error('Report download failed');const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download='paw-activity.csv';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);})}>Download CSV</button><div className="table-wrap"><table><thead><tr><th>User</th><th>Events</th><th>Created / Updated / Deleted</th><th>Logins</th></tr></thead><tbody>{data.users.map(u=><tr key={u.id}><td>{u.name}<br/>{u.email}</td><td>{u.activity_count}</td><td>{u.created} / {u.updated} / {u.deleted}</td><td>{u.logins}</td></tr>)}</tbody></table></div><h2>Activity by module</h2>{data.events.map(e=><article className="row-card" key={`${e.entity}-${e.action}`}><strong>{e.entity} · {e.action}</strong><span>{e.count}</span></article>)}</>}
    {Array.isArray(data)&&!data.length&&<p>No records in this view.</p>}
  </>}</>;
}
