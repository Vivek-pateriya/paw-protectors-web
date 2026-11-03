import React, { useEffect, useId, useRef, useState } from 'react';
import { request } from './api';

const money = n => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(n / 100);
const label = s => String(s ?? '').replaceAll('_', ' ');
const statuses = ['placed', 'confirmed', 'shipped', 'delivered', 'cancelled'];
function paise(raw) {
  if (!/^\d+(\.\d{1,2})?$/.test(raw)) throw new Error('Enter an INR amount with at most two decimal places.');
  const [whole, cents = ''] = raw.split('.'); const value = Number(whole) * 100 + Number(cents.padEnd(2, '0'));
  if (!Number.isSafeInteger(value) || value < 1 || value > 100000000) throw new Error('Price must be between ₹0.01 and ₹10,00,000.');
  return value;
}
const F = (name, title, type = 'text', value = '', options) => ({ name, title, type, value, options });

function Editor({ spec, save, cancel, busy }) {
  const id = useId(), [error, setError] = useState('');
  return <article className="card"><h2>{spec.title}</h2>{spec.note && <p>{spec.note}</p>}
    <form onSubmit={async e => {
      e.preventDefault(); setError('');
      const values = Object.fromEntries(new FormData(e.currentTarget));
      try { await save(values); } catch (err) { setError(err.message); }
    }}>
      {spec.fields.map(f => <label key={f.name} htmlFor={`${id}-${f.name}`}>{f.title}
        {f.type === 'select' ? <select id={`${id}-${f.name}`} name={f.name} defaultValue={f.value} disabled={busy}>{f.options.map(o => <option key={o.value ?? o} value={o.value ?? o}>{o.label ?? label(o)}</option>)}</select>
          : f.type === 'textarea' ? <textarea id={`${id}-${f.name}`} name={f.name} defaultValue={f.value} disabled={busy} maxLength={5000} />
            : <input id={`${id}-${f.name}`} name={f.name} type={f.type} defaultValue={f.value} disabled={busy} min={f.type === 'number' ? 0 : undefined} maxLength={f.type === 'text' ? 500 : undefined} />}
      </label>)}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions"><button className="btn primary" disabled={busy}>{spec.submit || 'Save'}</button><button className="btn" type="button" disabled={busy} onClick={cancel}>Cancel</button></div>
    </form></article>;
}

function ProductPhoto({ product, token, detail = false }) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    const c = new AbortController(); let url, active = true; setSrc('');
    if (product.image_path) fetch(`/shop/products/${product.id}/image?v=${product.version}`, { headers: { Authorization: `Bearer ${token}` }, signal: c.signal })
      .then(r => { if (!r.ok) throw new Error(); return r.blob(); }).then(b => { if (active) { url = URL.createObjectURL(b); setSrc(url); } }).catch(() => {});
    return () => { active = false; c.abort(); if (url) URL.revokeObjectURL(url); };
  }, [product.id, product.version, product.image_path, token]);
  return <div className={`pet-face shop-photo${detail ? ' photo-detail' : ''}`}>{src ? <img src={src} alt={product.name} /> : <span aria-label="No product photo">🛍</span>}</div>;
}

export function ShopPage({ user, token, onExpired }) {
  const admin = user.role === 'admin';
  const [view, setView] = useState('browse'), [selected, setSelected] = useState(null), [data, setData] = useState(null);
  const [categories, setCategories] = useState([]), [filters, setFilters] = useState({}), [offset, setOffset] = useState(0);
  const [revision, refresh] = useState(0), [form, setForm] = useState(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const checkoutKey = useRef(null), lock = useRef(false);
  const api = (path, method = 'GET', body, signal) => request(path, token, method, body, signal).catch(e => { if (e.status === 401) onExpired(); throw e; });
  function choose(next, selection = null) { setView(next); setSelected(selection); setData(null); setForm(null); setOffset(0); setFilters({}); setError(''); setNotice(''); }
  useEffect(() => {
    const c = new AbortController(); let active = true; setLoading(true); setData(null); setError('');
    const params = new URLSearchParams({ offset: String(offset), limit: '12' });
    Object.entries(filters).forEach(([k, v]) => { if (v !== '') params.set(k, String(v)); });
    let path = '/shop/products?';
    if (selected) path = `/shop/${selected.type === 'order' ? 'orders' : 'products'}/${selected.id}`;
    else if (view === 'cart') path = '/shop/cart';
    else if (view === 'categories') path = '/shop/categories';
    else if (view === 'orders') { path = '/shop/orders?'; params.set('scope', admin ? 'all' : 'mine'); }
    else params.set('scope', view === 'manage' ? 'manage' : 'browse');
    if (path.endsWith('?')) path += params.toString();
    Promise.all([api(path, 'GET', undefined, c.signal), api('/shop/categories', 'GET', undefined, c.signal)])
      .then(([value, cats]) => { if (active) { setData(value); setCategories(cats); } }).catch(e => { if (active && e.name !== 'AbortError') setError(e.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; c.abort(); };
  }, [view, selected, offset, filters, revision, token]);
  async function act(fn, success) {
    if (lock.current) return; lock.current = true; setBusy(true); setError(''); setNotice('');
    try { const result = await fn(); if (success) setNotice(success); setForm(null); refresh(x => x + 1); return result; }
    catch (e) { setError(e.message); throw e; } finally { lock.current = false; setBusy(false); }
  }
  const run = (fn, msg) => { void act(fn, msg).catch(() => {}); };
  const productFields = (p = {}) => [F('category_id', 'Category', 'select', p.category_id || categories[0]?.id || '', categories.map(c => ({ value: c.id, label: c.name + (c.active ? '' : ' (archived)') }))), F('sku', 'SKU', 'text', p.sku), F('name', 'Product name', 'text', p.name), F('description', 'Description', 'textarea', p.description), F('price', 'Price in INR', 'text', p.price_paise ? (p.price_paise / 100).toFixed(2) : ''), F('low_stock_threshold', 'Low stock threshold', 'number', p.low_stock_threshold ?? 5), F('active', 'Publication', 'select', String(p.active ?? false), [{ value: 'false', label: 'Draft / archived' }, { value: 'true', label: 'Published (category must be active)' }]), ...(!p.id ? [F('initial_stock', 'Initial stock', 'number', 0)] : [])];
  function editProduct(p = {}) {
    if (!categories.length) { setError('Create a category before adding a product.'); return; }
    setForm({ title: p.id ? 'Edit product' : 'Add product', note: 'INR prices. Stock changes have a separate recorded reason. Add a photo after saving.', fields: productFields(p), save: v => act(async () => {
      const { price, ...body } = v; body.price_paise = paise(price); body.category_id = Number(v.category_id); body.low_stock_threshold = Number(v.low_stock_threshold); body.active = v.active === 'true';
      if (p.id) body.version = p.version; else body.initial_stock = Number(v.initial_stock);
      const row = await api('/shop/products' + (p.id ? `/${p.id}` : ''), p.id ? 'PUT' : 'POST', body); setSelected({ type: 'product', id: row.id }); setData(null);
    }, 'Product saved.') });
  }
  function editCategory(c = {}) { setForm({ title: c.id ? 'Edit category' : 'Add category', fields: [F('name', 'Category name', 'text', c.name), F('active', 'Availability', 'select', String(c.active ?? true), ['true', 'false'])], save: v => act(() => api('/shop/categories' + (c.id ? `/${c.id}` : ''), c.id ? 'PUT' : 'POST', { name: v.name, active: v.active === 'true', ...(c.id ? { version: c.version } : {}) }), 'Category saved.') }); }
  function add(p) { run(async () => { const c = await api('/shop/cart'); const item = c.items.find(x => x.id === p.id); await api(`/shop/cart/items/${p.id}`, 'PUT', { version: c.version, quantity: (item?.quantity || 0) + 1 }); choose('cart'); }, 'Added to cart.'); }
  function checkout() {
    const quote = data;
    setForm({ title: 'Checkout', submit: `Place COD order · ${money(quote.total_paise)}`, note: `Cash on delivery. Free delivery. Total ${money(quote.total_paise)}. Pay when delivery is confirmed.`, fields: [F('customer_name', 'Recipient name', 'text', user.name), F('phone', 'Contact phone'), F('address', 'Delivery address', 'textarea'), F('city', 'City'), F('state', 'State'), F('postal_code', 'Six-digit PIN code')], save: v => act(async () => {
      const body = { ...v, version: quote.version, expected_total_paise: quote.total_paise }; const fingerprint = JSON.stringify(body);
      if (checkoutKey.current?.fingerprint !== fingerprint) checkoutKey.current = { fingerprint, key: crypto.randomUUID() };
      const order = await api('/shop/checkout', 'POST', { ...body, checkout_key: checkoutKey.current.key }); checkoutKey.current = null; setData(null); setView('orders'); setSelected({ type: 'order', id: order.id });
    }, 'Order placed. Cash on delivery; delivery is free.') });
  }
  function orderDecision(o, action) {
    setForm({ title: `${label(action)} order #${o.id}`, submit: action === 'deliver' ? 'Confirm delivery and cash collected' : 'Confirm decision', note: action === 'cancel' ? 'Cancelling restores reserved stock once.' : action === 'deliver' ? 'Confirm only after delivery and cash collection.' : 'The customer will receive an order update.', fields: [F('note', action === 'cancel' ? 'Cancellation reason (required)' : 'Note (optional)', 'textarea'), ...(action === 'ship' ? [F('tracking_reference', 'Tracking reference (optional)')] : [])], save: v => act(() => api(`/shop/orders/${o.id}/decision`, 'POST', { version: o.version, action, note: v.note, tracking_reference: v.tracking_reference || '' }), 'Order updated.') });
  }
  const page = !selected && !['cart', 'categories'].includes(view) && data;
  return <>
    <h1>Pet Shop</h1><p>Pet essentials. INR prices, cash on delivery and free delivery.</p>
    <div className="actions">{[['browse', 'Browse products'], ...(!admin ? [['cart', 'Cart']] : []), ['orders', admin ? 'Manage orders' : 'My orders'], ...(admin ? [['manage', 'Inventory'], ['categories', 'Categories']] : [])].map(([v, title]) => <button className={`btn ${view === v ? 'primary' : ''}`} key={v} disabled={busy} onClick={() => choose(v)}>{title}</button>)}<button className="btn" disabled={busy} onClick={() => refresh(x => x + 1)}>Refresh</button></div>
    {notice && <p className="notice" role="status">{notice}</p>}{error && <p className="error" role="alert">{error}</p>}
    {form ? <Editor key={form.title} spec={form} save={form.save} cancel={() => setForm(null)} busy={busy} /> : <>
      {loading && <p role="status">Loading shop…</p>}
      {selected && <button className="btn" disabled={busy} onClick={() => { setSelected(null); setData(null); }}>Back to results</button>}
      {selected?.type === 'product' && data && <article className="card"><ProductPhoto product={data} token={token} detail /><h2>{data.name}</h2><p>{data.category_name} · {data.sku}</p><p>{data.description}</p><h3>{money(data.price_paise)}</h3><p>{data.stock} available {(!data.active || !data.category_active) && '· Not published'}</p>
        {!admin && <button className="btn primary" disabled={busy || !data.stock} onClick={() => add(data)}>Add to cart</button>}
        {admin && <><div className="actions"><button className="btn" disabled={busy} onClick={() => editProduct(data)}>Edit product</button><button className="btn" disabled={busy} onClick={() => setForm({ title: 'Adjust stock', fields: [F('delta', 'Quantity change (negative removes stock)'), F('reason', 'Reason (required)', 'textarea')], save: v => act(() => { if (!/^-?\d+$/.test(v.delta)) throw new Error('Enter a whole quantity change.'); return api(`/shop/products/${data.id}/stock`, 'POST', { version: data.version, delta: Number(v.delta), reason: v.reason }); }, 'Stock adjusted.') })}>Adjust stock</button></div>
          <label>Product photo (JPEG or PNG, up to 5 MB)<input type="file" accept="image/jpeg,image/png" disabled={busy} onChange={e => { const file = e.target.files[0]; e.target.value = ''; if (file) run(async () => { if (file.size > 5 * 1024 * 1024) throw new Error('Select a photo smaller than 5 MB.'); const body = new FormData(); body.append('file', file); await api(`/shop/products/${data.id}/image?version=${data.version}`, 'POST', body); }, 'Product photo saved.'); }} /></label>
          <h3>Stock history</h3>{data.stock_history?.map(x => <p key={x.id}>{new Date(x.created_at).toLocaleString()} · {x.kind} · {x.delta > 0 ? '+' : ''}{x.delta} · remaining {x.resulting_stock}<br />{x.reason}</p>)}</>}
      </article>}
      {selected?.type === 'order' && data && <article className="card"><h2>Order #{data.id} · {label(data.status)}</h2><p>{new Date(data.created_at).toLocaleString()} · Cash on delivery · Payment {data.payment_status}</p><p><strong>Deliver to {data.customer_name}</strong><br />{data.phone}<br />{data.address}<br />{data.city}, {data.state} {data.postal_code}</p>
        {data.items.map(x => <p key={x.id}>{x.name} · {x.sku}<br />{x.quantity} × {money(x.unit_price_paise)} = {money(x.line_total_paise)}</p>)}<p>Delivery: Free</p><h3>Total {money(data.total_paise)}</h3>{data.tracking_reference && <p>Tracking: {data.tracking_reference}</p>}
        <div className="actions">{admin && ({ placed: ['confirm'], confirmed: ['ship'], shipped: ['deliver'] }[data.status] || []).map(a => <button className="btn primary" disabled={busy} key={a} onClick={() => orderDecision(data, a)}>{a === 'deliver' ? 'Confirm delivery and cash collection' : label(a)}</button>)}{(data.status === 'placed' || admin && data.status === 'confirmed') && <button className="btn danger" disabled={busy} onClick={() => orderDecision(data, 'cancel')}>Cancel order</button>}</div>
        <h3>Order history</h3>{data.history.map(x => <p key={x.id}>{new Date(x.created_at).toLocaleString()} · {label(x.to_status)}<br />{x.note}</p>)}
      </article>}
      {!selected && view === 'categories' && <><button className="btn primary" disabled={busy} onClick={() => editCategory()}>Add category</button>{Array.isArray(data) && data.map(c => <article className="row-card" key={c.id}><strong>{c.name} · {c.active ? 'Active' : 'Archived'}</strong><button className="btn" disabled={busy} onClick={() => editCategory(c)}>Edit category</button></article>)}</>}
      {!selected && view === 'cart' && data && <article className="card"><h2>Your shared cart</h2><p>Stock is reserved only when the order is placed. Review current prices before checkout.</p>{!data.items.length && <p>Your cart is empty.</p>}{data.items.map(p => <article className="row-card" key={p.id}><div><strong>{p.name}</strong><p>{money(p.price_paise)} each · {p.quantity} in cart · {money(p.line_total_paise)}</p>{!p.available && <p className="error">Unavailable or insufficient stock. Change the quantity or remove it.</p>}</div><div className="actions"><button className="btn" disabled={busy || p.quantity <= 1} onClick={() => run(() => api(`/shop/cart/items/${p.id}`, 'PUT', { version: data.version, quantity: p.quantity - 1 }))}>Decrease {p.name}</button><button className="btn" disabled={busy || p.quantity >= 99 || p.quantity >= p.stock} onClick={() => run(() => api(`/shop/cart/items/${p.id}`, 'PUT', { version: data.version, quantity: p.quantity + 1 }))}>Increase {p.name}</button><button className="btn" disabled={busy} onClick={() => run(() => api(`/shop/cart/items/${p.id}`, 'PUT', { version: data.version, quantity: 0 }))}>Remove {p.name}</button></div></article>)}<p>Delivery: Free</p><h3>Total {money(data.total_paise)}</h3><button className="btn primary" disabled={busy || !data.can_checkout} onClick={checkout}>Checkout with cash on delivery</button></article>}
      {page && <>
        {view === 'manage' && <button className="btn primary" disabled={busy} onClick={() => editProduct()}>Add product</button>}
        <form className="shop-filters" key={view} onSubmit={e => { e.preventDefault(); const v = Object.fromEntries(new FormData(e.currentTarget)); try { if (v.min_price) v.min_price_paise = paise(v.min_price); if (v.max_price) v.max_price_paise = paise(v.max_price); delete v.min_price; delete v.max_price; setOffset(0); setFilters(v); } catch (err) { setError(err.message); } }}>
          {view === 'orders' ? <label>Status<select name="status" defaultValue={filters.status || ''}><option value="">All statuses</option>{statuses.map(s => <option key={s}>{s}</option>)}</select></label> : <><label>Search products<input name="q" maxLength={100} defaultValue={filters.q || ''} /></label><label>Category<select name="category_id" defaultValue={filters.category_id || ''}><option value="">All categories</option>{categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Minimum price INR<input name="min_price" defaultValue={filters.min_price_paise ? (Number(filters.min_price_paise) / 100).toFixed(2) : ''} /></label><label>Maximum price INR<input name="max_price" defaultValue={filters.max_price_paise ? (Number(filters.max_price_paise) / 100).toFixed(2) : ''} /></label><label>Availability<select name="in_stock" defaultValue={filters.in_stock || ''}><option value="">All stock levels</option><option value="true">In stock</option></select></label>{admin && <label>Low stock<select name="low_stock" defaultValue={filters.low_stock || ''}><option value="">All</option><option value="true">At or below threshold</option></select></label>}</>}
          <button className="btn" disabled={busy}>Apply filters</button>
        </form><p>{data.total} results</p>
        {data.items.map(row => view === 'orders' ? <article className="row-card" key={row.id}><strong>Order #{row.id} · {row.status}</strong><span>{money(row.total_paise)} · payment {row.payment_status}</span><button className="btn" disabled={busy} onClick={() => { setData(null); setSelected({ type: 'order', id: row.id }); }}>View order</button></article>
          : <article className="row-card" key={row.id}><ProductPhoto product={row} token={token} /><div><strong>{row.name}</strong><p>{row.category_name} · {money(row.price_paise)} · {row.stock} available {(!row.active || !row.category_active) && '· Draft / archived'}</p></div><button className="btn" disabled={busy} onClick={() => { setData(null); setSelected({ type: 'product', id: row.id }); }}>View product</button></article>)}
        {!data.items.length && <p>No matching records.</p>}<div className="actions">{offset > 0 && <button className="btn" disabled={busy} onClick={() => setOffset(x => Math.max(0, x - 12))}>Previous</button>}{offset + 12 < data.total && <button className="btn" disabled={busy} onClick={() => setOffset(x => x + 12)}>Next</button>}</div>
      </>}
    </>}
  </>;
}
