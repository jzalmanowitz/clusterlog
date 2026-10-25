/* ClusterLog front end — plain JS, no build step.
   Views are rendered from the URL hash (#/cycle/3, #/attack/12, ...).
   Times are local wall-clock strings "YYYY-MM-DDTHH:MM", as stored. */
'use strict';

const app = document.getElementById('app');
const bar = document.getElementById('bar');

const PHASES = [['shadow', 'Shadows'], ['onset', 'Onset'], ['build', 'Building'], ['peak', 'Peak'], ['subside', 'Subsiding']];
const PHASE_LABEL = Object.fromEntries(PHASES);
const CATS = [['abortive', 'Abortive'], ['preventive', 'Preventive'], ['emergent', 'Emergent / transitional'],
  ['supplement', 'Supplement'], ['other', 'Other']];
const CAT_LABEL = Object.fromEntries(CATS);
const SIDES = ['Left', 'Right', 'Both', 'Alternating'];
const TAGS = { pain: 'PAIN', treatment: 'MED', note: 'NOTE', event: 'EVENT', supplement: 'D3' };
const D3_SCHEDULES = [['maintenance', 'Maintenance only'], ['two_week', 'Two-week loading'], ['four_week', 'Four-week loading']];
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const S = {
  treatments: [], settings: {}, entries: {}, attacks: {}, supps: {},
  attack: null,          // attack shown on the attack screen
  tab: 'journal',        // cycle screen tab
  meds: 'key',           // chart medication filter
  justEnded: null,       // id of an attack just ended (shows the summary card)
};

/* ---------------------------------------------------------------- utils */

const $ = (sel, el = document) => el.querySelector(sel);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pad = n => String(n).padStart(2, '0');
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const fmtAmt = v => (v == null || v === '' ? '' : Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }));

async function api(path, opts = {}) {
  const o = { method: 'GET', headers: {}, ...opts };
  if (o.body !== undefined && typeof o.body !== 'string') {
    o.body = JSON.stringify(o.body);
    o.headers['Content-Type'] = 'application/json';
  }
  let r;
  try { r = await fetch('/api' + path, o); } catch { throw new Error("Can't reach the ClusterLog server"); }
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      if (typeof j.detail === 'string') msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map(d => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join('; ');
    } catch { /* not json */ }
    throw new Error(msg);
  }
  const ct = r.headers.get('content-type') || '';
  return ct.includes('json') ? r.json() : r.text();
}

/* ---------------------------------------------------------------- time */

const localStr = (d = new Date()) =>
  `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const nowLocal = () => localStr();
const today = () => nowLocal().slice(0, 10);
function toDate(s) {
  const [y, m, d] = s.slice(0, 10).split('-').map(Number);
  return new Date(y, m - 1, d, +s.slice(11, 13) || 0, +s.slice(14, 16) || 0);
}
const addMin = (s, m) => localStr(new Date(toDate(s).getTime() + m * 60000));
function addDays(d, n) { const x = toDate(d); return localStr(new Date(x.getFullYear(), x.getMonth(), x.getDate() + n)).slice(0, 10); }
const minsBetween = (a, b) => Math.round((toDate(b) - toDate(a)) / 60000);
const minsSince = s => Math.max(0, Math.floor((Date.now() - toDate(s)) / 60000));
const dayDiff = (a, b) => Math.round((toDate(b.slice(0, 10)) - toDate(a.slice(0, 10))) / 86400000);
const hhmm = s => s.slice(11, 13) + s.slice(14, 16);
function fmtDur(m) {
  if (m == null || isNaN(m)) return '–';
  m = Math.max(0, Math.round(m));
  const h = Math.floor(m / 60);
  if (h >= 48) return `${Math.floor(h / 24)}d`;
  return h ? `${h}h${pad(m % 60)}m` : `${m}m`;
}
function dayLabel(d) {
  const x = toDate(d);
  const y = x.getFullYear() !== new Date().getFullYear() ? ' ' + x.getFullYear() : '';
  return `${DOW[x.getDay()]} ${x.getDate()} ${MON[x.getMonth()]}${y}`;
}
const shortDate = d => { const x = toDate(d); return `${x.getDate()} ${MON[x.getMonth()]}`; };
const fmtDate = d => { const x = toDate(d); return `${x.getDate()} ${MON[x.getMonth()]} ${x.getFullYear()}`; };
const cycleDay = (c, d) => dayDiff(c.started_on, d) + 1;

/** Week group for a date: weeks inside a cycle (days 1–7 = week 1), else Monday-based calendar weeks. */
function weekOf(cycle, d) {
  if (cycle) {
    const n = Math.floor(dayDiff(cycle.started_on, d) / 7) + 1;
    if (n >= 1) {
      const ws = addDays(cycle.started_on, (n - 1) * 7);
      return { key: ws, label: `Week ${n}`, sub: `${shortDate(ws)} – ${shortDate(addDays(ws, 6))}` };
    }
  }
  const ws = addDays(d, -((toDate(d).getDay() + 6) % 7));
  return { key: ws, label: `Week of ${shortDate(ws)}`, sub: `${shortDate(ws)} – ${shortDate(addDays(ws, 6))}` };
}

/* ---------------------------------------------------------------- ui helpers */

function pageHead(title, back, right = '') {
  return `<header class="top">${back ? `<a class="back" href="${back}" aria-label="Back">‹</a>` : ''}
    <h1>${title}</h1>${right}</header>`;
}

function setBar(html) {
  bar.innerHTML = html ? `<div class="inner">${html}</div>` : '';
  bar.hidden = !html;
  document.body.classList.toggle('has-bar', !!html);
}

let toastTimer;
function toast(msg, actions = []) {
  const t = $('#toast');
  t.innerHTML = `<span>${esc(msg)}</span>` + actions.map((a, i) => `<button type="button" data-i="${i}">${esc(a.label)}</button>`).join('');
  t.hidden = false;
  t.onclick = async ev => {
    const b = ev.target.closest('button');
    if (!b) return;
    t.hidden = true;
    try { await actions[+b.dataset.i].fn(); } catch (e) { toast(e.message); }
  };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, actions.length ? 8000 : 3500);
}

const opt = (type, name, value, label, checked) =>
  `<label class="opt"><input type="${type}" name="${name}" value="${esc(value)}"${checked ? ' checked' : ''}><span class="chip">${esc(label)}</span></label>`;
const radios = (name, opts, val) => opts.map(([v, l]) => opt('radio', name, v, l, String(v) === String(val ?? ''))).join('');
const checks = (name, opts, vals) => opts.map(v => opt('checkbox', name, v, v, (vals || []).includes(v))).join('');
const kipRadios = (val) => `<div class="kip-grid">${[...Array(11).keys()].map(i =>
  `<label class="opt" style="display:block"><input type="radio" name="kip" value="${i}"${String(val) === String(i) ? ' checked' : ''}><span class="chip" style="width:100%;justify-content:center;min-height:56px;border-radius:12px;font-size:var(--s-lg)">${i}</span></label>`).join('')}</div>`;

function union(base, extra) {
  const out = [...(base || [])];
  for (const x of extra || []) if (!out.some(y => y.toLowerCase() === x.toLowerCase())) out.push(x);
  return out;
}

function formValues(form, submitter) {
  const out = {};
  for (const el of form.elements) {
    if (!el.name || el.disabled) continue;
    if (el.type === 'checkbox') {
      if (el.dataset.bool !== undefined) out[el.name] = el.checked;
      else { out[el.name] = out[el.name] || []; if (el.checked) out[el.name].push(el.value); }
    } else if (el.type === 'radio') { if (el.checked) out[el.name] = el.value; else if (!(el.name in out)) out[el.name] = null; }
    else if (el.tagName !== 'BUTTON') out[el.name] = el.value;
  }
  if (submitter && submitter.name) out[submitter.name] = submitter.value;
  return out;
}

/** Bottom sheet with a form. onSubmit(values, form) may throw to keep it open. */
function openSheet(title, body, { onSubmit, submitLabel = 'Save', extra = '', onOpen } = {}) {
  closeSheet();
  const wrap = document.createElement('div');
  wrap.className = 'sheet-wrap';
  wrap.innerHTML = `<div class="sheet-bg" data-act="closeSheet"></div>
    <form class="sheet" novalidate>
      <div class="sheet-head"><h1>${esc(title)}</h1><button type="button" class="x" data-act="closeSheet" aria-label="Close">✕</button></div>
      <button type="submit" disabled hidden aria-hidden="true"></button>
      <div class="sheet-body">${body}</div>
      ${(onSubmit && submitLabel) || extra ? `<div class="sheet-foot">${extra}${onSubmit && submitLabel ? `<button class="btn primary" type="submit">${esc(submitLabel)}</button>` : ''}</div>` : ''}
    </form>`;
  document.body.appendChild(wrap);
  document.body.classList.add('noscroll');
  const form = $('form', wrap);
  form.addEventListener('submit', async ev => {
    ev.preventDefault();
    if (!onSubmit || form.dataset.busy) return;
    form.dataset.busy = '1';
    const hash = location.hash;
    try {
      const keepOpen = await onSubmit(formValues(form, ev.submitter), form);
      if (keepOpen === true) return;
      closeSheet();
      if (location.hash === hash) await refresh();
    } catch (e) { toast(e.message); }
    finally { delete form.dataset.busy; }
  });
  if (onOpen) onOpen(form);
  return form;
}
function closeSheet() {
  document.querySelectorAll('.sheet-wrap').forEach(w => w.remove());
  document.body.classList.remove('noscroll');
}

async function copyText(t) {
  try { await navigator.clipboard.writeText(t); return true; } catch { /* http: fall back */ }
  const ta = document.createElement('textarea');
  ta.value = t; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;top:0;opacity:0';
  document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0, t.length);
  let ok = false; try { ok = document.execCommand('copy'); } catch { /* ignore */ }
  ta.remove(); return ok;
}

/* ---------------------------------------------------------------- data helpers */

async function loadTreatments() { S.treatments = await api('/treatments?include_archived=true'); }
async function loadSettings() { S.settings = await api('/settings'); applyFontScale(S.settings.font_scale); applyTheme(S.settings.theme); }

const FONT_SCALES = [['0.8', 'Small'], ['0.9', 'Medium'], ['1', 'Large'], ['1.15', 'Extra large']];
/** Text size lives in settings (survives reinstalls) and localStorage (applied before the first fetch). */
function applyFontScale(v) {
  if (!v) return;
  document.documentElement.style.setProperty('--fs', v);
  try { localStorage.setItem('fontScale', v); } catch { /* private mode */ }
}
try { applyFontScale(localStorage.getItem('fontScale')); } catch { /* private mode */ }

const THEMES = [['normal', 'Normal'], ['dim', 'Dim'], ['auto', 'Auto (dim 22:00–07:00)']];
let themeSetting = 'normal';
const isDim = () => themeSetting === 'dim' || (themeSetting === 'auto' && (new Date().getHours() >= 22 || new Date().getHours() < 7));
/** Display mode, stored like the text size. Auto is re-checked every tick so it switches at 22:00 / 07:00. */
function applyTheme(v) {
  if (v) {
    themeSetting = v;
    try { localStorage.setItem('theme', v); } catch { /* private mode */ }
  }
  const dim = isDim();
  if ((document.documentElement.dataset.theme === 'dim') !== dim) {
    if (dim) document.documentElement.dataset.theme = 'dim'; else delete document.documentElement.dataset.theme;
  }
}
try { applyTheme(localStorage.getItem('theme')); } catch { /* private mode */ }
const activeTreatments = () => S.treatments.filter(t => !t.archived);
const treatment = id => S.treatments.find(t => t.id === +id);
const recentSince = () => api('/recent?since=' + encodeURIComponent(addMin(nowLocal(), -24 * 60)));
/** Duration treatments (oxygen, cold compress…) started in the past 24h and not stopped yet. */
const runningNow = () => api('/running?since=' + encodeURIComponent(addMin(nowLocal(), -24 * 60)));
const isRunning = e => e.mode === 'duration' && !e.ended_at && minsSince(e.at) < 24 * 60;
function doseLabel(t, amount) {
  amount = (amount ?? '').trim(); const uom = (t.uom || '').trim();
  if (!amount) return t.name;
  if (!uom) return `${t.name}, ${amount}`;
  return t.uom_prefix ? `${t.name}, ${uom} ${amount}` : `${t.name}, ${amount} ${uom}`;
}
function weatherBits(w, prev) {
  if (!w) return '';
  const arrow = k => { if (!prev || prev[k] == null) return ''; const d = w[k] - prev[k]; return d > 0.005 ? ' ↑' : d < -0.005 ? ' ↓' : ' →'; };
  return `${w.temp_c.toFixed(1)}°C${arrow('temp_c')} · ${w.humidity}%${arrow('humidity')} · ${w.pressure_cmhg.toFixed(2)} cmHg${arrow('pressure_cmhg')}`;
}

/* ---------------------------------------------------------------- journal */

/** ' · until 0101 (19m)' / ' · running 12m' / ' · no stop time' for a duration treatment. */
function sessionBit(e) {
  if (e.mode !== 'duration') return '';
  if (e.ended_at) return ` · until ${hhmm(e.ended_at)} (${fmtDur(minsBetween(e.at, e.ended_at))})`;
  return isRunning(e) ? ` · running <span class="ago" data-since="${e.at}">${fmtDur(minsSince(e.at))}</span>` : ' · no stop time';
}
function entryText(e) {
  const note = e.note ? esc(e.note) : '';
  if (e.kind === 'pain') return `<b>KIP ${e.kip}</b>${e.phase ? ' · ' + PHASE_LABEL[e.phase] : ''}${note ? ' — ' + note : ''}`;
  if (e.kind === 'treatment' || e.kind === 'event') return `<b>${esc(e.title)}</b>${sessionBit(e)}${note ? ' — ' + note : ''}`;
  return note;
}
const entryRow = e => `<div class="jrow${e.attack_id ? ' in' : ''}" data-act="editEntry" data-id="${e.id}" role="button" tabindex="0">
  <span class="t">${hhmm(e.at)}</span><span class="tag">${TAGS[e.kind]}</span><span class="txt">${entryText(e)}</span></div>`;

/** One "Track D3 Regimen" log: every supplement taken at that time. */
function suppRow(l) {
  const items = l.items.map(i => `${esc(i.name)} ${fmtAmt(i.amount)}${i.uom && i.amount != null ? ' ' + esc(i.uom) : ''}${i.loading ? ' (weekly loading dose)' : ''}${i.source === 'food' ? ' (food)' : ''}`);
  return `<div class="jrow" data-act="editSupp" data-id="${l.id}" role="button" tabindex="0">
  <span class="t">${hhmm(l.at)}</span><span class="tag">${TAGS.supplement}</span><span class="txt"><b>D3 regimen</b> · ${items.join(' · ')}${l.note ? ' — ' + esc(l.note) : ''}</span></div>`;
}

function attackRow(a, which, link = true) {
  const tagName = link ? 'a' : 'div';
  const href = link ? ` href="#/attack/${a.id}"` : ` data-act="editAttack" data-id="${a.id}" role="button" tabindex="0"`;
  const dur = a.ended_at ? minsBetween(a.started_at, a.ended_at) : null;
  if (which === 'start') {
    const detail = [a.side && `${a.side} side`, (a.locations || []).join(', '), (a.pain_types || []).join(', ')].filter(Boolean).join(' · ');
    const w = a.weather ? weatherBits(a.weather) : '';
    return `<${tagName} class="jrow attack in"${href}><span class="t">${hhmm(a.started_at)}</span><span class="tag">▶</span>
      <span class="txt">HEADACHE #${a.number}${a.ended_at ? ` · ${fmtDur(dur)}${a.peak_kip != null ? ' · peak ' + a.peak_kip : ''}` : ' · in progress'}
      ${detail ? `<span class="sub">${esc(detail)}</span>` : ''}${w ? `<span class="sub">${esc(w)}</span>` : ''}</span></${tagName}>`;
  }
  return `<${tagName} class="jrow attack in"${href}><span class="t">${hhmm(a.ended_at)}</span><span class="tag">■</span>
    <span class="txt">END #${a.number} <span class="muted">· lasted ${fmtDur(dur)}</span></span></${tagName}>`;
}

/** Entries + attack start/end rows, grouped by (cycle) week and day. */
function journalHTML(attacks, entries, cycle, { asc = false, weeks = true, links = true, supps = [] } = {}) {
  attacks.forEach(a => { S.attacks[a.id] = a; });
  entries.forEach(e => { S.entries[e.id] = e; });
  supps.forEach(l => { S.supps[l.id] = l; });
  const items = [];
  for (const a of attacks) {
    items.push({ at: a.started_at, o: 0, id: a.id, html: attackRow(a, 'start', links) });
    if (a.ended_at) items.push({ at: a.ended_at, o: 2, id: a.id, html: attackRow(a, 'end', links) });
  }
  for (const e of entries) items.push({ at: e.at, o: 1, id: e.id, html: entryRow(e) });
  for (const l of supps) items.push({ at: l.at, o: 1, id: l.id, html: suppRow(l) });
  items.sort((x, y) => (x.at < y.at ? -1 : x.at > y.at ? 1 : (x.o - y.o) || (x.id - y.id)));
  const byDay = new Map();
  for (const it of items) {
    const d = it.at.slice(0, 10);
    if (!byDay.has(d)) byDay.set(d, []);
    byDay.get(d).push(it);
  }
  const days = [...byDay.keys()].sort();
  if (!asc) days.reverse();
  let out = '', week = null;
  for (const d of days) {
    if (weeks) {
      const w = weekOf(cycle, d);
      if (w.key !== week) { week = w.key; out += `<h2 class="week">${w.label} <span class="muted">· ${w.sub}</span></h2>`; }
    }
    const n = attacks.filter(a => a.started_at.slice(0, 10) === d).length;
    out += `<h3 class="day">${dayLabel(d)}${cycle ? ` <span class="muted">· day ${cycleDay(cycle, d)}</span>` : ''}${n ? ` <span class="muted">· ${plural(n, 'headache')}</span>` : ''}</h3>`;
    out += byDay.get(d).map(i => i.html).join('');
  }
  return out;
}

function runningHTML(list) {
  if (!list.length) return '';
  return `<section><h2>Running now</h2>${list.map(e => `<div class="list-row running"><div><b>● ${esc(e.title)}</b>
      <div class="small muted">started ${hhmm(e.at)}${dayDiff(e.at, nowLocal()) ? ' ' + dayLabel(e.at) : ''}</div></div>
    <div><b><span class="ago" data-since="${e.at}">${fmtDur(minsSince(e.at))}</span></b>
      <button class="btn sm" data-act="stopEntry" data-id="${e.id}">Stop</button></div></div>`).join('')}</section>`;
}

function recentHTML(list, attack) {
  if (!list.length) return '';
  const hints = attack?.hints?.treatments || {};
  const inAttack = new Set((attack?.entries || []).filter(e => e.kind === 'treatment').map(e => String(e.treatment_id)));
  return `<section><h2>Since last dose · past 24h</h2>${list.map(r => {
    const h = hints[r.treatment_id];
    const hint = attack && !attack.ended_at && inAttack.has(String(r.treatment_id)) && h && h.n >= 2
      ? `<div class="small muted">headaches usually end ~${fmtDur(h.median)} after this${h.p25 != null ? ` (${fmtDur(h.p25)}–${fmtDur(h.p75)})` : ''} · n=${h.n}</div>` : '';
    const limit = r.max_per_day ? `<div class="small${r.count >= r.max_per_day ? '' : ' muted'}">${r.count >= r.max_per_day ? '<b>Daily limit reached</b> · ' : ''}${r.count} of ${r.max_per_day} in 24h</div>` : '';
    return `<div class="list-row"><div><b>${esc(r.title)}</b>${r.count > 1 && !r.max_per_day ? ` <span class="muted">×${r.count}</span>` : ''}${limit}${hint}</div>
      <div><b><span class="ago" data-since="${r.last_at}">${fmtDur(minsSince(r.last_at))}</span></b> <span class="muted">ago</span></div></div>`;
  }).join('')}</section>`;
}

/* ---------------------------------------------------------------- views: home */

async function viewHome() {
  const [cycles, active, learn, running] = await Promise.all([api('/cycles?today=' + today()), api('/attacks/active'),
    api('/learnings'), runningNow()]);
  running.forEach(e => { S.entries[e.id] = e; });
  const openCycle = cycles.find(c => !c.ended_on);
  let h = pageHead('ClusterLog', null, `<a class="btn sm ghost" href="#/settings">Settings</a>`);
  if (active) h += activeBanner(active);
  h += runningHTML(running);
  h += `<section><div class="sec-head"><h2>Cycles</h2>${cycles.length ? `<button class="btn sm" data-act="newCycle">+ New cycle</button>` : ''}</div>`;
  if (!cycles.length) {
    h += `<div class="empty"><h1>No cycles yet</h1>
      <p>A cycle is a container for one cluster period. Start one when a new cycle begins — every headache, dose and note goes inside it.</p>
      <button class="btn primary wide" data-act="newCycle">Start a new cycle</button></div>`;
  }
  h += cycles.map(cycleCard).join('') + `</section>
    <section><h2>More</h2>
      <a class="card" href="#/loose"><b>Outside a cycle</b><div class="small muted">Injections, appointments &amp; notes between cycles</div></a>
      <a class="card" href="#/learnings"><b>Cycle learnings</b><div class="small muted">${learn.length ? `${plural(learn.length, 'note')} from past you` : 'What past you wants future you to remember'}</div></a>
      <a class="card" href="#/export"><b>Report for neurologist</b><div class="small muted">Pick dates · email · print · CSV</div></a>
      <a class="card" href="#/treatments"><b>Meds &amp; treatments</b><div class="small muted">${activeTreatments().length} defined</div></a>
      <a class="card" href="#/supplements"><b>D3 regimen supplements</b><div class="small muted">Vitamin D3, cofactors &amp; daily targets</div></a>
    </section>`;
  app.innerHTML = h;
  if (active) setBar(`<a class="btn primary big" href="#/attack/${active.id}">● Open headache · <span class="ago" data-since="${active.started_at}">${fmtDur(minsSince(active.started_at))}</span></a>`);
  else if (openCycle) setBar(`<button class="btn primary big" data-act="startAttack" data-cycle="${openCycle.id}">Start headache</button>`);
}

function cycleCard(c) {
  const ended = !!c.ended_on;
  const len = cycleDay(c, ended ? c.ended_on : today());
  return `<a class="card${ended ? '' : ' solid'}" href="#/cycle/${c.id}">
    <div class="card-title"><span>${esc(c.name)}</span>${ended ? '' : '<span class="pill">ACTIVE</span>'}</div>
    <div class="small muted">${ended ? `${fmtDate(c.started_on)} – ${fmtDate(c.ended_on)} · ${len} days` : `Day ${len} · week ${Math.floor((len - 1) / 7) + 1} · since ${fmtDate(c.started_on)}`}
      · ${plural(c.attack_count, 'headache')}${ended ? '' : ` · ${c.today_count} today`}</div></a>`;
}

function activeBanner(a) {
  return `<a class="banner" href="#/attack/${a.id}">
    <div class="small"><b>● HEADACHE IN PROGRESS</b>${a.cycle_name ? ' · ' + esc(a.cycle_name) : ''}</div>
    <div class="num"><span class="ago" data-since="${a.started_at}">${fmtDur(minsSince(a.started_at))}</span></div>
    <div class="small muted">started ${hhmm(a.started_at)}${a.last_kip != null ? ` · KIP ${a.last_kip}` : ''} · tap to open</div></a>`;
}

/* ---------------------------------------------------------------- views: cycle / loose log */

async function viewCycle(id) { await viewLog(await api('/cycles/' + id)); }
async function viewLoose() { await viewLog(null); }

async function viewLog(cycle) {
  const cid = cycle ? cycle.id : 'none';
  const [j, active, recent, running] = await Promise.all([api('/journal?cycle_id=' + cid), api('/attacks/active'),
    recentSince(), runningNow()]);
  running.forEach(e => { S.entries[e.id] = e; });
  const here = active && (cycle ? active.cycle_id === cycle.id : active.cycle_id == null);
  let h = pageHead(cycle ? esc(cycle.name) : 'Outside a cycle', '#/',
    cycle ? `<button class="btn sm ghost" data-act="editCycle" data-id="${cycle.id}">Edit</button>` : '');
  if (cycle) {
    const len = cycleDay(cycle, cycle.ended_on || today());
    h += `<p class="muted">${cycle.ended_on ? `Ended ${fmtDate(cycle.ended_on)} · lasted ${len} days` : `Day ${len} · week ${Math.floor((len - 1) / 7) + 1} · started ${fmtDate(cycle.started_on)}`}</p>`;
  } else {
    h += `<p class="muted">For things between cycles — e.g. an Emgality injection, a nerve block, or an appointment.</p>`;
  }
  if (active && !here) h += activeBanner(active);
  const t = today();
  const todayAtt = j.attacks.filter(a => a.started_at.slice(0, 10) === t);
  const lastEnded = j.attacks.filter(a => a.ended_at).sort((a, b) => (a.ended_at < b.ended_at ? -1 : 1)).pop();
  if (j.attacks.length || cycle) {
    h += `<div class="tiles">
      <div class="tile"><div class="num">${todayAtt.length}</div><div class="small">headaches today</div></div>
      ${cycle?.ended_on ? '' : `<div class="tile"><div class="num">${lastEnded ? `<span class="ago" data-since="${lastEnded.ended_at}">${fmtDur(minsSince(lastEnded.ended_at))}</span>` : '–'}</div><div class="small">since last headache ended</div></div>`}
      <div class="tile"><div class="num">${j.attacks.length}</div><div class="small">headaches ${cycle ? 'this cycle' : 'logged'}</div></div>
    </div>`;
  }
  h += runningHTML(running);
  h += recentHTML(recent);
  if (cycle && cycle.ended_on) {
    h += `<section><div class="sec-head"><h2>Cycle learnings</h2><button class="btn sm ghost" data-act="editLearnings" data-id="${cycle.id}">${cycle.learnings ? 'Edit' : 'Write'}</button></div>
      ${cycle.learnings ? `<div class="card"><div class="txt" style="white-space:pre-wrap">${esc(cycle.learnings)}</div></div>`
        : `<div class="empty"><p>What should future you remember from this cycle?</p><button class="btn primary" data-act="editLearnings" data-id="${cycle.id}">Write learnings</button></div>`}</section>`;
  }
  h += `<div class="tabs" role="tablist">${[['journal', 'Journal'], ['chart', 'Chart'], ['stats', 'Stats']].map(([k, l]) =>
    `<button role="tab" class="${S.tab === k ? 'on' : ''}" data-act="tab" data-v="${k}">${l}</button>`).join('')}</div>
    <div id="tabbody"></div>`;
  app.innerHTML = h;

  const body = $('#tabbody');
  if (S.tab === 'journal') {
    body.innerHTML = (j.attacks.length || j.entries.length || j.supplement_logs.length)
      ? journalHTML(j.attacks, j.entries, cycle, { supps: j.supplement_logs })
      : `<div class="empty"><p>Nothing logged yet.</p><p class="small">Tap <b>Start headache</b> when shadows begin, or log a med or note below.</p></div>`;
  } else if (S.tab === 'chart') {
    renderChart(body, cid);
  } else {
    renderStats(body, cid);
  }

  const c = cycle ? cycle.id : '';
  setBar(`${here ? `<a class="btn primary sm" href="#/attack/${active.id}">● Headache · <span class="ago" data-since="${active.started_at}">${fmtDur(minsSince(active.started_at))}</span></a>`
    : `<button class="btn primary sm" data-act="startAttack" data-cycle="${c}">Start headache</button>`}
    <button class="btn sm" data-act="addEvent" ${here ? `data-attack="${active.id}"` : `data-cycle="${c}"`}>+ Add event</button>
    <button class="btn sm" data-act="trackD3" data-cycle="${c}">Track D3 Regimen</button>`);
}

async function renderChart(el, cid) {
  el.innerHTML = `<div class="chips" style="margin-top:16px">${[['key', 'Key meds'], ['all', 'All meds'], ['none', 'No meds']].map(([k, l]) =>
    `<button class="chip ${S.meds === k ? 'on' : ''}" data-act="meds" data-v="${k}">${l}</button>`).join('')}</div>
    <div class="chart-scroll" id="chartbox"><p class="muted">Loading chart…</p></div>
    <p class="help">Each column is a day; top is midnight, bottom is midnight. ● headache start (bigger = higher peak KIP), bar = duration,
    ◇ abortive dose, ◆ preventive / emergent dose. Bottom strip: headaches per day. Week lines are cycle weeks. Scroll sideways for older days.</p>`;
  const svg = await api(`/chart/daily.svg?cycle_id=${cid}&meds=${S.meds}&today=${today()}&theme=${isDim() ? 'dim' : 'dark'}`);
  const box = $('#chartbox');
  if (!box) return;
  box.innerHTML = svg;
  box.scrollLeft = box.scrollWidth;
}

async function renderStats(el, cid) {
  el.innerHTML = `<p class="muted">Loading…</p>`;
  const s = await api(`/stats?cycle_id=${cid}&today=${today()}`);
  const du = s.duration;
  let h = `<div class="tiles" style="margin-top:16px">
    <div class="tile"><div class="num">${s.attacks}</div><div class="small">headaches · ${s.per_day_avg}/day</div></div>
    <div class="tile"><div class="num">${fmtDur(du.median)}</div><div class="small">median length${du.n ? ` · n=${du.n}` : ''}</div></div>
    <div class="tile"><div class="num">${s.peak.mean ?? '–'}</div><div class="small">avg peak KIP · max ${s.peak.max ?? '–'}</div></div>
    <div class="tile"><div class="num">${fmtDur(du.max)}</div><div class="small">longest</div></div>
    <div class="tile"><div class="num">${s.free_days}</div><div class="small">headache-free days of ${s.days}</div></div>
    <div class="tile"><div class="num">${du.p25 != null ? `${fmtDur(du.p25)}` : '–'}</div><div class="small">${du.p25 != null ? `to ${fmtDur(du.p75)} · middle half` : 'middle half (needs 4+)'}</div></div>
  </div>`;
  h += `<section><h2>Headache start time</h2>${hourSVG(s.by_hour)}</section>`;
  if (s.weeks.length) {
    h += `<section><h2>By week</h2><div class="tbl-scroll"><table class="t"><tr><th>Week</th><th>Headaches</th><th>Doses</th><th>Median</th><th>Max KIP</th></tr>
      ${s.weeks.slice().reverse().map(w => `<tr><td>${esc(w.label)}</td><td>${w.attacks}</td><td>${w.meds}</td><td>${fmtDur(w.median_duration)}</td><td>${w.max_kip ?? '–'}</td></tr>`).join('')}
      </table></div></section>`;
  }
  if (s.treatments.length) {
    h += `<section><h2>Treatments</h2>${s.treatments.map(t => {
      const tag = t.treatment_id ? 'a' : 'div';
      return `<${tag} class="list-row"${t.treatment_id ? ` href="#/med/${t.treatment_id}/${cid}"` : ''}><div><b>${esc(t.name)}</b>${t.treatment_id ? ' ›' : ''}
      <div class="small muted">${t.uses} uses${t.in_attacks ? ` · ${t.in_attacks} during attacks` : ''}</div>
      ${t.mode === 'duration' && t.session.n ? `<div class="small muted">median session ${fmtDur(t.session.median)} · total ${fmtDur(t.total_min)}</div>` : ''}</div>
      <div>${t.to_end.n ? `<b>${fmtDur(t.to_end.median)}</b><div class="small muted">to headache end · n=${t.to_end.n}</div>` : '<span class="muted">–</span>'}</div></${tag}>`;
    }).join('')}
      <p class="help">Tap a treatment to see every time it was used. "To headache end" = median time from the first dose of that treatment to the end of the headache.</p></section>`;
  }
  h += regimenStatsHTML(s.regimen);
  el.innerHTML = h;
}

function d3StatusText(st) {
  if (!st) return '';
  if (st.schedule === 'maintenance') return `Maintenance · ${fmtAmt(st.target)} IU a day`;
  if (!st.day) return `${D3_SCHEDULES.find(x => x[0] === st.schedule)[1]} · starts with your first D3 dose`;
  return `${st.phase} · day ${st.day} · ${st.until_maintenance ? `${plural(st.until_maintenance, 'day')} until maintenance · ` : ''}D3 ${fmtAmt(st.target)} IU a day`
    + (st.weekly_loading ? ' + 50,000 IU once this week' : '');
}

function regimenStatsHTML(g) {
  if (!g || (!g.days && (!g.schedule || g.schedule === 'maintenance'))) return '';
  let h = `<section><h2>D3 regimen</h2>`;
  if (g.schedule) h += `<p><b>${esc(g.schedule_label)}</b><span class="small muted" style="display:block">${esc(d3StatusText(g.status))}</span></p>`;
  if (!g.days) return h + `<p class="muted">Nothing tracked yet. Tap <b>Track D3 Regimen</b> below.</p></section>`;
  h += `<div class="tiles">
    <div class="tile"><div class="num">${g.complete_days}</div><div class="small">days all targets met · of ${g.days}</div></div>
    ${g.loading_doses ? `<div class="tile"><div class="num">${g.loading_doses.taken}/${g.loading_doses.expected}</div><div class="small">weekly 50,000 IU loading doses</div></div>` : ''}
  </div>`;
  h += g.supplements.map(p => `<div class="list-row"><div><b>${esc(p.name)}</b>
    <div class="small muted">${p.days_taken ? `total ${fmtAmt(p.total)} ${esc(p.uom)}${p.food ? ` · ${fmtAmt(p.food)} from food` : ''}` : 'not taken'}${p.target ? ` · target ${esc(p.target)}` : ''}</div></div>
    <div>${p.days_expected ? `<b>${p.days_met}/${p.days_expected}</b><div class="small muted">days at target</div>` : '<span class="muted">–</span>'}</div></div>`).join('');
  return h + `<p class="help">Each day's doses are added up and compared with the daily target; Vitamin D3's target follows the cycle's loading schedule. Counted from the first tracked day.</p></section>`;
}

function hourSVG(hours) {
  const W = 336, H = 132, bw = W / 24, top = 16, ph = 90, mx = Math.max(1, ...hours);
  let s = `<svg class="fit" viewBox="0 0 ${W} ${H}" role="img" aria-label="Headaches by hour of day">`;
  hours.forEach((c, i) => {
    const h = c / mx * ph;
    s += `<rect x="${i * bw + 1}" y="${top + ph - h}" width="${bw - 2}" height="${Math.max(h, c ? 2 : 0)}" fill="currentColor"><title>${pad(i)}:00 · ${c}</title></rect>`;
    if (c) s += `<text x="${i * bw + bw / 2}" y="${top + ph - h - 4}" fill="currentColor" font-size="9" text-anchor="middle">${c}</text>`;
  });
  s += `<line x1="0" x2="${W}" y1="${top + ph}" y2="${top + ph}" stroke="#555"/>`;
  for (const i of [0, 6, 12, 18]) s += `<text x="${i * bw + 1}" y="${top + ph + 16}" fill="currentColor" fill-opacity=".68" font-size="11">${pad(i)}h</text>`;
  return s + '</svg>';
}

/* ---------------------------------------------------------------- views: attack */

async function viewAttack(id) {
  const [a, recent, sessions] = await Promise.all([api('/attacks/' + id), recentSince(), runningNow()]);
  sessions.forEach(e => { S.entries[e.id] = e; });
  S.attack = a;
  S.attacks[a.id] = a;
  a.entries.forEach(e => { S.entries[e.id] = e; });
  const running = !a.ended_at;
  const pains = a.entries.filter(e => e.kind === 'pain');
  const last = pains[pains.length - 1];
  const peak = pains.length ? Math.max(...pains.map(e => e.kip)) : null;
  const back = a.cycle_id ? '#/cycle/' + a.cycle_id : '#/loose';
  const hd = a.hints.duration;
  let h = pageHead(`Headache #${a.number}`, back, `<button class="btn sm ghost" data-act="editAttack" data-id="${a.id}">Edit</button>`);

  if (!running && S.justEnded === a.id) {
    h += endSummaryCard(a, peak);
    S.justEnded = null;
  }
  h += `<div class="hero">`;
  if (running) {
    h += `<div class="small muted">IN PROGRESS · ${a.cycle_name ? esc(a.cycle_name) + ' · ' : ''}started ${hhmm(a.started_at)}</div>
      <div class="num"><span class="ago" data-since="${a.started_at}">${fmtDur(minsSince(a.started_at))}</span></div>
      ${hd.n >= 3 ? `<div class="small muted">your headaches usually last ~${fmtDur(hd.median)}${hd.p25 != null ? ` (${fmtDur(hd.p25)}–${fmtDur(hd.p75)})` : ''}</div>` : ''}`;
  } else {
    const span = dayDiff(a.started_at, a.ended_at);
    h += `<div class="small muted">${dayLabel(a.started_at)} · ${hhmm(a.started_at)}–${hhmm(a.ended_at)}${span ? ` (+${span}d)` : ''}${a.cycle_name ? ' · ' + esc(a.cycle_name) : ''}</div>
      <div class="num">${fmtDur(minsBetween(a.started_at, a.ended_at))}</div>`;
  }
  h += `<div class="stats"><div><span class="num">${last ? last.kip : '–'}</span><span class="small muted">KIP ${running ? 'now' : 'last'}</span></div>
    <div><span class="num">${peak ?? '–'}</span><span class="small muted">peak</span></div></div></div>`;

  const detail = [a.side && `${a.side} side`, a.locations.join(', '), a.pain_types.join(', ')].filter(Boolean).join(' · ');
  h += `<button class="list-row" data-act="editAttack" data-id="${a.id}">
    <span>${detail ? esc(detail) : '<span class="muted">Add side, location, pain type…</span>'}</span><span class="muted">Edit ›</span></button>`;
  h += runningHTML(sessions);
  h += recentHTML(recent, a);
  h += chartSVG(a, pains);
  h += `<section><h2>Weather at start</h2>${a.weather
    ? `<div><b>${esc(weatherBits(a.weather, a.prev_weather))}</b><div class="small muted">${a.weather.pressure_kpa != null ? `${a.weather.pressure_kpa.toFixed(2)} kPa · ` : ''}sea-level pressure${a.weather.pressure_change_6h_cmhg != null ? ` · ${a.weather.pressure_change_6h_cmhg > 0 ? '+' : ''}${a.weather.pressure_change_6h_cmhg.toFixed(2)} cmHg over the 6 h before` : ''}${a.prev_weather ? ' · arrows vs. previous headache' : ''}<br>${esc(a.weather.place || '')} · ${a.weather.hour.slice(11)} · ${esc(a.weather.source)}</div></div>`
    : `<p class="small muted">${S.settings.lat ? 'Fetching… (retried hourly if the server is offline)' : 'Set your location in Settings to record weather automatically.'}</p>`}</section>`;
  h += `<section><h2>Timeline</h2>${journalHTML([a], a.entries, null, { asc: true, weeks: false, links: false })}</section>`;
  app.innerHTML = h;

  setBar(`<button class="btn primary grow" data-act="addEvent" data-attack="${a.id}">+ Add event</button>`
    + (running ? `<button class="btn" data-act="endAttack" data-id="${a.id}">End headache</button>` : ''));
}

function endSummaryCard(a, peak) {
  const firsts = {};
  for (const e of a.entries) if (e.kind === 'treatment' && !(e.treatment_id in firsts)) firsts[e.treatment_id] = e;
  const lines = Object.values(firsts).map(e => `${esc(e.title)} → over ${fmtDur(minsBetween(e.at, a.ended_at))} after first dose`);
  return `<div class="card solid" style="margin-top:16px"><div class="card-title">Headache over</div>
    <div class="num" style="margin:8px 0">${fmtDur(minsBetween(a.started_at, a.ended_at))}</div>
    <div class="small">${peak != null ? `peak KIP ${peak}` : ''}${lines.length ? '<br>' + lines.join('<br>') : ''}</div>
    <p class="small muted">Saved. Details can be edited any time.</p></div>`;
}

/** Side / location / pain-type fields, shared by the start and edit sheets. */
function headacheDetailFields(a) {
  return `<label class="f">Side</label><div class="chips">${radios('side', [['', '—'], ...SIDES.map(s => [s, s])], a.side || '')}</div>
    <label class="f">Location <span class="muted">(pick any)</span></label>
    <div class="chips">${checks('locations', union(S.settings.pain_locations, a.locations), a.locations)}</div>
    <label class="f">Pain type <span class="muted">(pick any)</span></label>
    <div class="chips">${checks('pain_types', union(S.settings.pain_types, a.pain_types), a.pain_types)}</div>
    <input name="custom_type" placeholder="+ add your own pain type" autocomplete="off">`;
}

/** Selected pain types plus a typed-in one (which is also saved to the option list). */
async function painTypesWithCustom(f) {
  const v = (f.custom_type || '').trim();
  if (!v) return f.pain_types || [];
  S.settings = await api('/settings', { method: 'PUT', body: { pain_types: union(S.settings.pain_types, [v]) } });
  return union(f.pain_types, [v]);
}

/** Pain curve for one attack: step line of KIP over time, dashed lines at doses. */
function chartSVG(a, pains) {
  if (!pains.length) return '';
  const W = 336, H = 156, L = 24, R = 8, T = 12, B = 28, pw = W - L - R, ph = H - T - B;
  const end = a.ended_at || nowLocal();
  const total = Math.max(10, minsBetween(a.started_at, end > pains[pains.length - 1].at ? end : pains[pains.length - 1].at));
  const x = at => L + Math.min(1, Math.max(0, minsBetween(a.started_at, at) / total)) * pw;
  const y = k => T + ph - k / 10 * ph;
  let s = `<section><h2>Pain curve</h2><svg class="fit" viewBox="0 0 ${W} ${H}" role="img" aria-label="Pain over time">`;
  for (const k of [0, 5, 10]) s += `<line x1="${L}" x2="${W - R}" y1="${y(k)}" y2="${y(k)}" stroke="#333"/><text x="${L - 6}" y="${y(k) + 4}" fill="currentColor" fill-opacity=".68" font-size="11" text-anchor="end">${k}</text>`;
  for (const e of a.entries.filter(e => e.kind === 'treatment')) {
    if (e.mode === 'duration') {  // shaded band for the session (to now while running)
      const stop = e.ended_at || (isRunning(e) ? nowLocal() : null);
      if (stop) s += `<rect x="${x(e.at)}" y="${T}" width="${Math.max(1, x(stop) - x(e.at))}" height="${ph}" fill="currentColor" opacity=".1"><title>${esc(e.title)} ${hhmm(e.at)}–${e.ended_at ? hhmm(e.ended_at) : 'now'}</title></rect>`;
    }
    s += `<line x1="${x(e.at)}" x2="${x(e.at)}" y1="${T}" y2="${T + ph}" stroke="currentColor" stroke-dasharray="3 3" opacity=".6"><title>${esc(e.title)} ${hhmm(e.at)}</title></line>`;
    s += `<path d="M${x(e.at)} ${T + ph - 5}l5 5-5 5-5-5z" fill="#000" stroke="currentColor"/>`;
  }
  let d = `M${x(pains[0].at)} ${y(pains[0].kip)}`;
  for (const p of pains.slice(1)) d += ` H${x(p.at)} V${y(p.kip)}`;
  d += ` H${x(end)}`;
  s += `<path d="${d}" fill="none" stroke="currentColor" stroke-width="2.5"/>`;
  for (const p of pains) s += `<circle cx="${x(p.at)}" cy="${y(p.kip)}" r="4" fill="currentColor"><title>${hhmm(p.at)} KIP ${p.kip}</title></circle>`;
  s += `<text x="${L}" y="${H - 8}" fill="currentColor" fill-opacity=".68" font-size="11">${hhmm(a.started_at)}</text>
    <text x="${W - R}" y="${H - 8}" fill="currentColor" fill-opacity=".68" font-size="11" text-anchor="end">${a.ended_at ? hhmm(a.ended_at) : 'now'} · ${fmtDur(total)}</text>`;
  return s + '</svg></section>';
}

/** Phase for a KIP logged with "Auto" selected. */
function autoPhase(a, kip) {
  const pains = a.entries.filter(e => e.kind === 'pain');
  const last = pains[pains.length - 1];
  if (!last) return kip >= 4 || a.start_phase === 'onset' ? 'onset' : 'shadow';
  if (kip > last.kip) return last.phase === 'shadow' ? 'onset' : 'build';
  if (kip < last.kip) return 'subside';
  return last.phase || 'build';
}

/* ---------------------------------------------------------------- views: learnings */

async function viewLearnings() {
  const list = await api('/learnings');
  let h = pageHead('Cycle learnings', '#/');
  h += `<p class="muted">One note per cycle, written at the end — what past you wants future you to remember.</p>`;
  h += list.length ? list.map(learningCard).join('')
    : `<div class="empty"><p>No learnings yet. When you end a cycle, you'll be asked for one.</p></div>`;
  app.innerHTML = h;
}
const learningCard = c => `<div class="card"><div class="card-title"><a href="#/cycle/${c.id}">${esc(c.name)}</a>
  <span class="small muted">${fmtDate(c.started_on)}${c.ended_on ? ' – ' + fmtDate(c.ended_on) : ''}</span></div>
  <div style="white-space:pre-wrap;margin-top:8px">${esc(c.learnings)}</div></div>`;

/* ---------------------------------------------------------------- views: treatments */

async function viewTreatments() {
  await loadTreatments();
  let h = pageHead('Meds & treatments', '#/', `<button class="btn sm" data-act="editTreatment">+ Add</button>`);
  h += `<p class="muted">Define each med or treatment once with its unit of measure. <b>Quick</b> ones are listed first under Add event → Medication, where one tap logs them.</p>`;
  for (const [cat, label] of CATS) {
    const list = S.treatments.filter(t => t.category === cat && !t.archived);
    if (!list.length) continue;
    h += `<section><h2>${label}</h2>${list.map(treatmentRow).join('')}</section>`;
  }
  const arch = S.treatments.filter(t => t.archived);
  if (arch.length) h += `<section><h2>Archived</h2>${arch.map(treatmentRow).join('')}</section>`;
  app.innerHTML = h;
  setBar(`<button class="btn primary" data-act="editTreatment">+ Add treatment</button>`);
}
const treatmentRow = t => `<button class="list-row" data-act="editTreatment" data-id="${t.id}">
  <span><b>${esc(t.name)}</b><span class="small muted" style="display:block">${t.mode === 'duration' ? 'start / stop · ' : ''}${t.uom ? 'unit: ' + esc(t.uom) : 'no unit'}${t.default_amount ? ' · default ' + esc(doseLabel(t, t.default_amount)) : ''}</span></span>
  <span class="small">${t.quick ? '<span class="pill">QUICK</span>' : ''}</span></button>`;

/* ---------------------------------------------------------------- views: supplements */

async function viewSupplements() {
  const list = await api('/supplements?include_archived=true');
  let h = pageHead('D3 regimen supplements', '#/', `<button class="btn sm" data-act="editSupplement">+ Add</button>`);
  h += `<p class="muted">The supplements listed under <b>Track D3 Regimen</b>, with the amount per dose and the daily target. Vitamin D3's target follows the loading schedule chosen for each cycle. Discuss the regimen with your healthcare provider.</p>`;
  const row = s => `<button class="list-row" data-act="editSupplement" data-id="${s.id}">
    <span><b>${esc(s.name)}</b><span class="small muted" style="display:block">${s.role === 'd3' ? 'target follows the loading schedule' : suppTarget(s) ? 'target ' + esc(suppTarget(s)) + ' a day' : 'no target'}${s.default_amount != null ? ` · dose ${fmtAmt(s.default_amount)} ${esc(s.uom)}` : ''}${s.course_days ? ` · ${s.course_days}-day course` : ''}</span></span>
    <span class="muted">›</span></button>`;
  const active = list.filter(s => !s.archived), arch = list.filter(s => s.archived);
  h += `<section>${active.map(row).join('') || '<p class="muted">None yet.</p>'}</section>`;
  if (arch.length) h += `<section><h2>Archived</h2>${arch.map(row).join('')}</section>`;
  app.innerHTML = h;
  S.supplements = list;
  setBar(`<button class="btn primary" data-act="editSupplement">+ Add supplement</button>`);
}
const suppTarget = s => (s.target_min == null && s.target_max == null ? ''
  : s.target_min != null && s.target_max != null && s.target_max !== s.target_min ? `${fmtAmt(s.target_min)}–${fmtAmt(s.target_max)} ${s.uom}`
    : `${fmtAmt(s.target_min ?? s.target_max)} ${s.uom}`).trim();

/* ---------------------------------------------------------------- views: one treatment */

/** Every use of one treatment within a cycle (or outside cycles), from Stats → Treatments. */
async function viewMed(tid, scope) {
  const [r, cycle] = await Promise.all([api(`/treatments/${tid}/log?cycle_id=${scope}&today=${today()}`),
    /^\d+$/.test(scope) ? api('/cycles/' + scope) : null]);
  const t = r.treatment, s = r.summary, dur = t.mode === 'duration';
  S.tab = 'stats';  // back returns to the Stats tab
  let h = pageHead(esc(t.name), scope === 'none' ? '#/loose' : '#/cycle/' + scope);
  h += `<p class="muted">${cycle ? esc(cycle.name) : 'Outside a cycle'} · ${CAT_LABEL[t.category] || ''}${dur ? ' · start / stop' : ''}</p>`;
  if (r.others.length > 1 && !r.others.some(o => o.treatment_id === t.id)) r.others.unshift({ treatment_id: t.id, name: t.name, uses: 0 });
  if (r.others.length > 1) {
    h += `<label class="f" for="medpick">Show</label><select id="medpick" style="margin-bottom:16px">${r.others.map(o =>
      `<option value="${o.treatment_id}"${o.treatment_id === t.id ? ' selected' : ''}>${esc(o.name)} (${o.uses})</option>`).join('')}</select>`;
  }
  if (!s) {
    app.innerHTML = h + `<div class="empty"><p>Not used here yet.</p></div>`;
    $('#medpick')?.addEventListener('change', ev => { location.hash = `#/med/${ev.target.value}/${scope}`; });
    return;
  }
  h += `<div class="tiles">
    <div class="tile"><div class="num">${s.uses}</div><div class="small">${dur ? 'sessions' : 'uses'}</div></div>
    <div class="tile"><div class="num">${s.in_attacks}</div><div class="small">during headaches</div></div>
    <div class="tile"><div class="num">${fmtDur(s.to_end.median)}</div><div class="small">to headache end${s.to_end.n ? ` · n=${s.to_end.n}` : ''}</div></div>
    ${dur ? `<div class="tile"><div class="num">${fmtDur(s.session.median)}</div><div class="small">median session${s.session.n ? ` · n=${s.session.n}` : ''}</div></div>
      <div class="tile"><div class="num">${fmtDur(s.total_min)}</div><div class="small">total time</div></div>` : ''}
  </div>`;
  const byDay = new Map();
  for (const d of r.doses.slice().reverse()) {
    S.entries[d.id] = d;
    if (!byDay.has(d.at.slice(0, 10))) byDay.set(d.at.slice(0, 10), []);
    byDay.get(d.at.slice(0, 10)).push(d);
  }
  h += `<section><h2>Every use · newest first</h2>`;
  for (const [day, list] of byDay) {
    h += `<h3 class="day">${dayLabel(day)}${cycle ? ` <span class="muted">· day ${cycleDay(cycle, day)}</span>` : ''}</h3>`;
    h += list.map(d => `<div class="jrow${d.attack_id ? ' in' : ''}" data-act="editEntry" data-id="${d.id}" role="button" tabindex="0">
      <span class="t">${hhmm(d.at)}</span><span class="tag">${TAGS.treatment}</span><span class="txt">${entryText(d)}${d.attack_id ? `<span class="sub"><a href="#/attack/${d.attack_id}">headache #${d.attack_number ?? '?'}</a>${d.to_end != null ? ` · ended ${fmtDur(d.to_end)} later` : ''}</span>` : ''}</span></div>`).join('');
  }
  h += `<p class="help">Tap a row to edit it. "Ended … later" is the time from this use to the end of that headache.</p></section>`;
  app.innerHTML = h;
  $('#medpick')?.addEventListener('change', ev => { location.hash = `#/med/${ev.target.value}/${scope}`; });
}

/* ---------------------------------------------------------------- views: export */

async function viewExport() {
  const cycles = await api('/cycles?today=' + today());
  const open = cycles.find(c => !c.ended_on);
  let h = pageHead('Report', '#/');
  h += `<form id="exp" class="pad" novalidate>
    <h2>Date range</h2>
    <div class="chips">
      ${open ? `<button type="button" class="chip" data-act="preset" data-start="${open.started_on}">This cycle</button>` : ''}
      <button type="button" class="chip" data-act="preset" data-days="7">7 days</button>
      <button type="button" class="chip" data-act="preset" data-days="30">30 days</button>
      <button type="button" class="chip" data-act="preset" data-days="90">90 days</button>
    </div>
    <div class="row"><div><label class="f">From</label><input type="date" name="start" value="${open ? open.started_on : addDays(today(), -29)}"></div>
      <div><label class="f">To</label><input type="date" name="end" value="${today()}"></div></div>
    <label class="f">Include</label>
    <select name="cycle_id"><option value="all">Everything in the date range</option>
      ${cycles.map(c => `<option value="${c.id}">Only cycle: ${esc(c.name)}</option>`).join('')}
      <option value="none">Only entries outside a cycle</option></select>

    <button type="button" class="btn primary wide big" data-act="openReport" data-fmt="text" data-dl="1" style="margin-top:24px">Download report (.txt)</button>
    <p class="help">A plain-text file — just the facts, no formatting. Attach it to an email to your neurologist.
      On iPhone it lands in Files → Downloads.</p>
    <section><h2>Other formats</h2><div class="stack">
      <div class="row"><button type="button" class="btn" data-act="copyReport">Copy text</button>
        <button type="button" class="btn" data-act="openReport" data-fmt="csv" data-dl="1">Spreadsheet (CSV)</button></div>
      <button type="button" class="btn ghost wide" data-act="openReport" data-fmt="html">Printable page with chart</button>
    </div></section>
    <section><h2>Preview</h2><pre class="preview" id="preview">Loading…</pre></section>
  </form>`;
  app.innerHTML = h;
  $('#exp').addEventListener('change', updatePreview);
  updatePreview();
}

function exportParams() {
  const f = formValues($('#exp'));
  if (!f.start || !f.end) throw new Error('Pick a start and end date');
  return f;
}
const reportQuery = (f, fmt) => `/report?start=${f.start}&end=${f.end}&cycle_id=${encodeURIComponent(f.cycle_id)}&format=${fmt}`;
async function updatePreview() {
  const pre = $('#preview');
  try { pre.textContent = await api(reportQuery(exportParams(), 'text')); } catch (e) { pre.textContent = e.message; }
}

/* ---------------------------------------------------------------- views: settings */

async function viewSettings() {
  await loadSettings();
  const [cycles, backups] = await Promise.all([api('/cycles?today=' + today()), api('/backups')]);
  const s = S.settings;
  let h = pageHead('Settings', '#/');
  h += `<form id="settings" novalidate>
    <section><h2>Text size</h2><div class="chips">${FONT_SCALES.map(([v, l]) =>
      `<button type="button" class="chip ${String(s.font_scale) === v ? 'on' : ''}" data-act="fontScale" data-v="${v}">${l}</button>`).join('')}</div></section>
    <section><h2>Display</h2><div class="chips">${THEMES.map(([v, l]) =>
      `<button type="button" class="chip ${(s.theme || 'normal') === v ? 'on' : ''}" data-act="theme" data-v="${v}">${l}</button>`).join('')}</div>
      <p class="help" style="margin-top:0">Dim uses grey instead of white so the screen glares less at night.</p></section>
    <section><h2>You &amp; your neurologist</h2>
      <label class="f">Your name <span class="muted">(shown on reports)</span></label><input name="patient_name" value="${esc(s.patient_name)}" autocomplete="name">
      <label class="f">Neurologist's name <span class="muted">(shown on reports)</span></label><input name="neurologist_name" value="${esc(s.neurologist_name)}" placeholder="Dr. …">
    </section>
    <section><h2>Weather location</h2>
      <p class="help" style="margin-top:0">Weather (°C, humidity %, pressure cmHg) is recorded automatically for each headache from Open-Meteo. ${s.place ? `Currently: <b>${esc(s.place)}</b>` : 'No location set.'}</p>
      <div class="row"><input name="geo" placeholder="City, e.g. Calgary"><button type="button" class="btn" data-act="geocode" style="flex:0 0 auto">Find</button></div>
      <div id="georesults"></div>
      <div class="row"><div><label class="f">Latitude</label><input name="lat" value="${esc(s.lat)}" inputmode="decimal"></div>
        <div><label class="f">Longitude</label><input name="lon" value="${esc(s.lon)}" inputmode="decimal"></div></div>
      <input type="hidden" name="place" value="${esc(s.place)}">
    </section>
    <section><h2>Pain options</h2>
      <label class="f">Locations <span class="muted">(one per line)</span></label><textarea name="pain_locations" rows="6">${esc(s.pain_locations.join('\n'))}</textarea>
      <label class="f">Pain types <span class="muted">(one per line)</span></label><textarea name="pain_types" rows="6">${esc(s.pain_types.join('\n'))}</textarea>
    </section>
  </form>
  <section><h2>Backup &amp; move to another server</h2>
    <p class="help" style="margin-top:0">An automatic backup is made daily (last 30 kept, ${backups.length} on file). The JSON file below contains everything.</p>
    <div class="stack"><a class="btn wide" href="/api/backup" download>Download full backup (JSON)</a>
      <button class="btn wide ghost" data-act="backupNow">Make a server backup now</button>
      <label class="btn wide ghost" for="restorefile">Restore from a JSON backup…</label>
      <input type="file" id="restorefile" accept="application/json,.json" class="hide"></div>
  </section>
  <section><h2>Import an old text log</h2>
    <p class="help" style="margin-top:0">Paste notes like your Evernote/Docs logs — day headers (<b>Feb 7</b>) followed by lines like <b>0042 - start oxygen, kip 6</b>. Each line becomes a note; lines mentioning "kip N" become pain points. Afterwards, create headaches with a start and end time and the entries inside are grouped into them automatically.</p>
    <form id="importf" novalidate>
      <textarea name="text" rows="8" placeholder="Feb 7&#10;0035 - woken up&#10;0042 - start oxygen, kip 6"></textarea>
      <div class="row"><div><label class="f">Year of first day</label><input name="year" inputmode="numeric" value="${new Date().getFullYear()}"></div>
        <div><label class="f">Into cycle</label><select name="cycle_id"><option value="">Outside a cycle</option>${cycles.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select></div></div>
      <div class="row" style="margin-top:16px"><button type="button" class="btn" data-act="importLog" data-dry="1">Preview</button><button type="button" class="btn primary" data-act="importLog">Import</button></div>
      <pre class="preview hide" id="importpreview"></pre>
    </form>
  </section>
  <p class="small muted pad">ClusterLog ${esc((await api('/health')).version)} · data lives in a single SQLite file on the server.</p>`;
  app.innerHTML = h;
  setBar(`<button class="btn primary" data-act="saveSettings">Save settings</button>`);
  $('#restorefile').addEventListener('change', restoreBackup);
}

async function restoreBackup(ev) {
  const file = ev.target.files[0];
  if (!file) return;
  if (!confirm(`Replace ALL current data with the contents of ${file.name}? A safety backup of the current data is made first.`)) return;
  try {
    const r = await api('/restore', { method: 'POST', body: await file.text() });
    await Promise.all([loadTreatments(), loadSettings()]);
    toast(`Restored: ${r.counts.cycles} cycles, ${r.counts.attacks} headaches, ${r.counts.entries} entries`);
    refresh();
  } catch (e) { toast(e.message); }
}

/* ---------------------------------------------------------------- sheets */

function cycleSheet(c = null) {
  openSheet(c ? 'Edit cycle' : 'New cycle', `
    <label class="f">Name</label><input name="name" value="${esc(c?.name || '')}" placeholder="e.g. Fall ${new Date().getFullYear()}" required>
    <label class="f">Started on</label><input type="date" name="started_on" value="${c?.started_on || today()}">
    <label class="f">Ended on <span class="muted">(leave blank while active)</span></label>
    <input type="date" name="ended_on" value="${c?.ended_on || ''}">
    <label class="f">D3 regimen</label><div class="chips" style="margin-bottom:0">${radios('d3_schedule', D3_SCHEDULES, c?.d3_schedule || 'maintenance')}</div>
    <p class="help">Two-week: 50,000 IU a day for 7 days, then 40,000 IU for 6 days. Four-week: 20,000 IU a day plus one 50,000 IU dose a week for 2 weeks, then 15,000 IU a day for 2 weeks. Both then drop to 10,000 IU a day.</p>
    <div id="d3startwrap"><label class="f">Loading started on <span class="muted">(blank = your first D3 dose tracked in this cycle)</span></label>
    <input type="date" name="d3_started_on" value="${c?.d3_started_on || ''}"></div>
    <label class="f">Notes</label><textarea name="notes" rows="3">${esc(c?.notes || '')}</textarea>
    ${c?.ended_on || c?.learnings ? `<label class="f">Cycle learnings</label><textarea name="learnings" rows="6">${esc(c?.learnings || '')}</textarea>` : ''}`, {
    submitLabel: c ? 'Save' : 'Create cycle',
    onOpen: form => {
      const sync = () => $('#d3startwrap', form).classList.toggle('hide', (formValues(form).d3_schedule || 'maintenance') === 'maintenance');
      form.addEventListener('change', sync); sync();
    },
    extra: c ? `${c.ended_on ? '' : `<button type="button" class="btn" data-act="endCycle" data-id="${c.id}">End cycle</button>`}
      <button type="button" class="btn ghost danger" data-act="deleteCycle" data-id="${c.id}">Delete</button>` : '',
    onSubmit: async f => {
      const body = { name: f.name, started_on: f.started_on, ended_on: f.ended_on || null, notes: f.notes,
        learnings: f.learnings ?? c?.learnings ?? '', d3_schedule: f.d3_schedule || 'maintenance',
        d3_started_on: f.d3_schedule && f.d3_schedule !== 'maintenance' ? f.d3_started_on || null : null };
      if (c) {
        const saved = await api('/cycles/' + c.id, { method: 'PUT', body });
        if (saved.ended_on && !c.ended_on && !saved.learnings) setTimeout(() => learningsSheet(saved, true), 50);
      } else {
        const nc = await api('/cycles', { method: 'POST', body });
        location.hash = '#/cycle/' + nc.id;
        const past = await api('/learnings');
        if (past.length) setTimeout(() => pastLearningsSheet(past), 50);
      }
    },
  });
}

function learningsSheet(c, ending = false) {
  openSheet('Cycle learnings', `
    <p class="muted">${ending ? `${esc(c.name)} is over. ` : ''}What did this cycle teach you? What actually mattered, what worked, what to do sooner next time? Future you will see this when the next cycle starts.</p>
    <textarea name="learnings" rows="10" placeholder="e.g. Start verapamil the first week, not week 3. Oxygen at 15 L/min wasn't enough — 25 L/min aborts in ~10 min. Book the nerve block early.">${esc(c.learnings || '')}</textarea>`, {
    submitLabel: 'Save learnings',
    onSubmit: f => api('/cycles/' + c.id, { method: 'PUT', body: { ...c, learnings: f.learnings } }),
  });
}

function pastLearningsSheet(list) {
  openSheet('From past you', `<p class="muted">New cycle started. Here's what you wrote at the end of previous cycles:</p>
    ${list.map(learningCard).join('')}`, { submitLabel: 'Got it', onSubmit: () => {} });
}

async function startAttackSheet(cycleId) {
  const last = await api('/attacks/last-details');
  let side = last.side || '';
  try { side = localStorage.getItem('lastSide') ?? side; } catch { /* private mode */ }
  openSheet('Start headache', `
    <label class="f">Started at</label><input type="datetime-local" name="started_at" value="${nowLocal()}">
    <label class="f">How did it start?</label><div class="chips">${radios('phase', [['shadow', 'Shadows'], ['onset', 'Pain onset']], 'shadow')}</div>
    <label class="f">Pain level (KIP) <span class="muted">— optional</span></label>${kipRadios(null)}
    ${headacheDetailFields({ side, locations: [], pain_types: [] })}
    <label class="f">Note <span class="muted">(optional)</span></label><input name="note" placeholder="e.g. woken up">
    <details class="more"><summary>Logging a past headache?</summary>
      <label class="f">Ended at</label><input type="datetime-local" name="ended_at"></details>`, {
    submitLabel: 'Start headache',
    onSubmit: async f => {
      try { localStorage.setItem('lastSide', f.side || ''); } catch { /* private mode */ }
      const a = await api('/attacks', { method: 'POST', body: {
        cycle_id: cycleId ? +cycleId : null, started_at: f.started_at, ended_at: f.ended_at || null,
        kip: f.kip == null ? null : +f.kip, phase: f.phase || 'shadow', note: f.note,
        side: f.side || '', locations: f.locations || [], pain_types: await painTypesWithCustom(f) } });
      location.hash = '#/attack/' + a.id;
    },
  });
}

/** "Add event" chooser: pain level (inside a headache), medication, note. */
function addEventSheet(d) {
  const ctx = d.attack ? `data-attack="${d.attack}"` : `data-cycle="${d.cycle || ''}"`;
  const choice = (act, title, sub) => `<button type="button" class="btn wide big choice" data-act="${act}" ${ctx}>${title}<span class="small">${sub}</span></button>`;
  openSheet('Add event', `<div class="stack" style="margin-top:16px">
    ${d.attack ? choice('addPain', 'Pain level', 'KIP 0–10 · shadows, building, peak, subsiding') : ''}
    ${choice('addTreatment', 'Medication / treatment', 'oxygen, Zomig, cold compress, injection…')}
    ${choice('addNote', 'Note', 'anything, with a timestamp')}</div>`);
}

const undoToast = (msg, e, edit) => toast(msg, [
  { label: 'Undo', fn: async () => { await api('/entries/' + e.id, { method: 'DELETE' }); refresh(); } },
  { label: 'Edit', fn: () => edit(e) }]);

function treatmentSheet({ cycle = null, attack = null, entry = null, recent = [] } = {}) {
  const used = id => recent.find(r => r.treatment_id === +id)?.count || 0;
  const cur = entry ? (entry.kind === 'event' ? '' : entry.treatment_id) : null;
  const groups = CATS.map(([cat, label]) => {
    const list = S.treatments.filter(t => t.category === cat && (!t.archived || t.id === cur));
    return list.length ? `<div class="small muted" style="margin:16px 0 8px">${label}</div><div class="chips" style="margin:0">
      ${list.map(t => opt('radio', 'treatment_id', t.id, t.name, t.id === cur)).join('')}</div>` : '';
  }).join('');
  const isEvent = entry?.kind === 'event';
  const atDefault = entry ? entry.at : nowLocal();
  const quick = entry ? [] : activeTreatments().filter(t => t.quick);
  openSheet(entry ? (isEvent ? 'Edit event' : entry.mode === 'duration' ? 'Edit session' : 'Edit dose') : 'Medication / treatment', `
    <label class="f" id="atlbl">When</label><input type="datetime-local" name="at" value="${atDefault}">
    ${quick.length ? `<label class="f">Tap to log</label><div class="stack">${quick.map(t =>
      `<button type="submit" class="btn wide" name="quick" value="${t.id}">${t.mode === 'duration' ? 'Start ' : ''}${esc(doseLabel(t, t.default_amount))}${t.max_per_day ? `<span class="small" style="font-weight:400">${used(t.id)}/${t.max_per_day} in 24h</span>` : ''}</button>`).join('')}</div>
      <label class="f" style="margin-top:32px">Or pick one and set the dose</label>` : ''}
    ${groups}
    <div class="chips" style="margin-top:16px">${opt('radio', 'treatment_id', '', 'Other / custom event…', isEvent)}</div>
    <div id="endwrap"><label class="f">Stopped <span class="muted">(blank = still running)</span></label><input type="datetime-local" name="ended_at" value="${entry?.ended_at || ''}"></div>
    <div id="amountwrap"><label class="f">Amount <span class="muted" id="uomlbl"></span></label><input name="amount" value="${esc(entry?.amount || '')}" autocomplete="off"></div>
    <div id="titlewrap"><label class="f">Event name</label><input name="title" value="${esc(isEvent ? entry.title : '')}" placeholder="e.g. Neurologist visit, steroid taper start"></div>
    <label class="f">Notes <span class="muted">(optional)</span></label><textarea name="note" rows="3">${esc(entry?.note || '')}</textarea>
    <p class="help" id="preview"></p>`, {
    submitLabel: entry ? 'Save' : 'Log it',
    extra: entry ? `<button type="button" class="btn ghost danger" data-act="deleteEntry" data-id="${entry.id}">Delete</button>` : '',
    onOpen: form => {
      const sync = (fill) => {
        const tid = form.querySelector('input[name=treatment_id]:checked')?.value;
        const t = tid ? treatment(tid) : null;
        $('#amountwrap', form).classList.toggle('hide', !t);
        $('#endwrap', form).classList.toggle('hide', t?.mode !== 'duration');
        $('#atlbl', form).textContent = t?.mode === 'duration' ? 'Started' : 'When';
        $('#titlewrap', form).classList.toggle('hide', !(tid === ''));
        $('#uomlbl', form).textContent = t?.uom ? `(${t.uom})` : '';
        if (fill && t) form.amount.value = t.default_amount;
        $('#preview', form).textContent = t ? 'Logs as: ' + doseLabel(t, form.amount.value) : '';
      };
      form.addEventListener('change', ev => sync(ev.target.name === 'treatment_id'));
      form.amount.addEventListener('input', () => sync(false));
      sync(false);
    },
    onSubmit: async f => {
      let body;
      if (f.quick) body = { kind: 'treatment', treatment_id: +f.quick, amount: treatment(f.quick).default_amount, note: f.note };
      else if (f.treatment_id == null) throw new Error('Pick a treatment, or "Other / custom event"');
      else body = f.treatment_id
        ? { kind: 'treatment', treatment_id: +f.treatment_id, amount: f.amount, note: f.note,
            ended_at: treatment(f.treatment_id)?.mode === 'duration' ? f.ended_at || null : null }
        : { kind: 'event', title: f.title, note: f.note };
      const t = body.treatment_id && treatment(body.treatment_id);
      if (!entry && t?.max_per_day && used(t.id) >= t.max_per_day
          && !confirm(`${t.name}: ${used(t.id)} of ${t.max_per_day} doses already in the last 24 hours. Log anyway?`)) return true;
      Object.assign(body, { at: f.at,
        attack_id: entry ? entry.attack_id : (attack ? +attack : null),
        cycle_id: entry ? entry.cycle_id : (cycle ? +cycle : null) });
      const e = await api(entry ? '/entries/' + entry.id : '/entries', { method: entry ? 'PUT' : 'POST', body });
      if (entry) toast('Saved');
      else undoToast(`${e.title}${isRunning(e) ? ' started' : ''} · ${hhmm(e.at)}`, e, x => treatmentSheet({ entry: x }));
    },
  });
}

function noteSheet({ cycle = null, attack = null, entry = null } = {}) {
  openSheet(entry ? 'Edit note' : 'Note', `
    <label class="f">When</label><input type="datetime-local" name="at" value="${entry ? entry.at : nowLocal()}">
    <label class="f">Note</label><textarea name="note" rows="6" placeholder="Anything — what you're feeling, what you tried…">${esc(entry?.note || '')}</textarea>`, {
    submitLabel: entry ? 'Save' : 'Add note',
    extra: entry ? `<button type="button" class="btn ghost danger" data-act="deleteEntry" data-id="${entry.id}">Delete</button>` : '',
    onOpen: form => setTimeout(() => form.note.focus(), 200),
    onSubmit: f => api(entry ? '/entries/' + entry.id : '/entries', { method: entry ? 'PUT' : 'POST', body: {
      kind: 'note', at: f.at, note: f.note,
      attack_id: entry ? entry.attack_id : (attack ? +attack : null),
      cycle_id: entry ? entry.cycle_id : (cycle ? +cycle : null) } }),
  });
}

function painSheet({ attack = null, entry = null } = {}) {
  if (entry) {
    openSheet('Edit pain level', `
      <label class="f">When</label><input type="datetime-local" name="at" value="${entry.at}">
      <label class="f">KIP</label>${kipRadios(entry.kip)}
      <label class="f">Phase</label><div class="chips">${radios('phase', [['', '—'], ...PHASES], entry.phase || '')}</div>
      <label class="f">Note <span class="muted">(optional)</span></label><input name="note" value="${esc(entry.note || '')}">`, {
      extra: `<button type="button" class="btn ghost danger" data-act="deleteEntry" data-id="${entry.id}">Delete</button>`,
      onSubmit: f => {
        if (f.kip == null) throw new Error('Pick a KIP level');
        return api('/entries/' + entry.id, { method: 'PUT', body: { ...entry, at: f.at, kip: +f.kip, phase: f.phase || null, note: f.note } });
      },
    });
    return;
  }
  const a = S.attack;
  openSheet('Pain level', `
    <label class="f">When</label><input type="datetime-local" name="at" value="${a.ended_at ? a.started_at : nowLocal()}">
    <label class="f">Phase</label><div class="chips">${radios('phase', [['auto', 'Auto'], ...PHASES], 'auto')}</div>
    <label class="f">Note <span class="muted">(optional)</span></label><input name="note" autocomplete="off">
    <label class="f">Tap the KIP to log it</label>
    <div class="kip-grid">${[...Array(11).keys()].map(i => `<button type="submit" class="btn" name="kip" value="${i}">${i}</button>`).join('')}</div>`, {
    submitLabel: null,
    onSubmit: async f => {
      const kip = +f.kip;
      const auto = f.phase === 'auto';
      const phase = auto ? autoPhase(a, kip) : f.phase;
      const e = await api('/entries', { method: 'POST', body: { kind: 'pain', at: f.at, attack_id: +attack || a.id, kip, phase, note: f.note } });
      // the first drop after the climb marks the highest point as the peak
      if (auto && phase === 'subside' && !a.entries.some(x => x.phase === 'peak')) {
        const hi = a.entries.filter(x => x.kind === 'pain').reduce((m, x) => (x.kip >= (m?.kip ?? -1) ? x : m), null);
        if (hi) await api('/entries/' + hi.id, { method: 'PUT', body: { ...hi, phase: 'peak' } });
      }
      undoToast(`KIP ${kip} · ${PHASE_LABEL[phase]} · ${hhmm(e.at)}`, e, x => painSheet({ entry: x }));
    },
  });
}

async function attackSheet(a) {
  const cycles = await api('/cycles?today=' + today());
  openSheet(`Edit headache #${a.number}`, `
    <label class="f">Started</label><input type="datetime-local" name="started_at" value="${a.started_at}">
    <label class="f">Ended <span class="muted">(blank = still going)</span></label><input type="datetime-local" name="ended_at" value="${a.ended_at || ''}">
    ${headacheDetailFields(a)}
    <label class="f">Cycle</label><select name="cycle_id"><option value="">Outside a cycle</option>
      ${cycles.map(c => `<option value="${c.id}"${c.id === a.cycle_id ? ' selected' : ''}>${esc(c.name)}</option>`).join('')}</select>
    <label class="f">Notes</label><textarea name="notes" rows="4">${esc(a.notes || '')}</textarea>
    <p class="help">Weather is recorded automatically and can't be edited.</p>`, {
    extra: `<button type="button" class="btn ghost danger" data-act="deleteAttack" data-id="${a.id}">Delete</button>`,
    onSubmit: async f => api('/attacks/' + a.id, { method: 'PATCH', body: {
      started_at: f.started_at, ended_at: f.ended_at || null, cycle_id: f.cycle_id ? +f.cycle_id : null, notes: f.notes,
      side: f.side || '', locations: f.locations || [], pain_types: await painTypesWithCustom(f) } }),
  });
}

async function endAttackSheet(a) {
  const running = await runningNow();
  openSheet('End headache', `
    <label class="f">Ended at</label><input type="datetime-local" name="ended_at" value="${nowLocal()}">
    ${running.length ? `<label class="f">Also stop <span class="muted">(leave unticked to keep going)</span></label>
      ${running.map(e => `<div class="check"><input type="checkbox" id="stop${e.id}" name="stop_ids" value="${e.id}"><label for="stop${e.id}">${esc(e.title)} <span class="muted">· running ${fmtDur(minsSince(e.at))}</span></label></div>`).join('')}` : ''}
    <label class="f">Note <span class="muted">(optional)</span></label><input name="note" placeholder="e.g. pain gone, back to bed">`, {
    submitLabel: 'End headache',
    onSubmit: async f => {
      await api(`/attacks/${a.id}/end`, { method: 'POST', body: { ...f, stop_ids: (f.stop_ids || []).map(Number) } });
      S.justEnded = a.id;
    },
  });
}

/** Track D3 Regimen: every active supplement pre-filled with its dose; untick what you skipped. Totals add up through the day. */
async function regimenSheet({ cycle = null, log = null } = {}) {
  const cid = log ? log.cycle_id : (cycle ? +cycle : null);
  const at = log ? log.at : nowLocal();
  const r = await api(`/regimen?date=${at.slice(0, 10)}${cid ? '&cycle_id=' + cid : ''}${log ? '&exclude_log=' + log.id : ''}`);
  const mine = log ? Object.fromEntries(log.items.filter(i => !i.loading).map(i => [i.supplement_id, i])) : {};
  const loadingItem = log?.items.find(i => i.loading);
  const list = r.supplements.filter(s => !s.archived || mine[s.id]);
  const d3 = r.d3;
  const hint = s => {
    const bits = [s.taken ? `today ${fmtAmt(s.taken)}${s.target ? ' of ' + s.target : ''}${s.met ? ' ✓' : ''}` : s.target ? `target ${s.target}` : ''];
    if (s.course) bits.push(s.course.days_left ? `${plural(s.course.days_left, 'day')} remaining` : 'course complete');
    else if (s.course_days) bits.push(`${s.course_days}-day course`);
    return bits.filter(Boolean).join(' · ');
  };
  const row = s => {
    const it = mine[s.id];
    const on = log ? !!it : !s.met && !(s.course && !s.course.days_left);
    const amt = it ? it.amount : s.role === 'd3' && s.remaining > 0 ? s.remaining : s.default_amount;
    return `<div class="supp" data-sid="${s.id}">
      <div class="check"><input type="checkbox" id="sp${s.id}" name="on" value="${s.id}"${on ? ' checked' : ''}><label for="sp${s.id}"><b>${esc(s.name)}</b>
        <span class="small muted hint" style="display:block">${esc(hint(s))}</span></label></div>
      <div class="supp-dose"><input name="amt_${s.id}" inputmode="decimal" value="${amt ?? ''}" aria-label="${esc(s.name)} amount"><span class="uom">${esc(s.uom)}</span>
        <span class="chips">${radios('src_' + s.id, [['supplement', 'Supplement'], ['food', 'Food']], it?.source || 'supplement')}</span></div></div>`;
  };
  const d3s = list.find(s => s.role === 'd3');
  const loadingRow = d3s && (d3.weekly_loading || loadingItem) ? `<div class="supp">
    <div class="check"><input type="checkbox" id="sploading" name="loading"${loadingItem ? ' checked' : ''}><label for="sploading"><b>D3 weekly loading dose</b>
      <span class="small muted" style="display:block">once a week in weeks 1 and 2 · ${d3.loading_taken ? 'already taken this week ✓' : 'not taken yet this week'}</span></label></div>
    <div class="supp-dose"><input name="loading_amt" inputmode="decimal" value="${loadingItem ? loadingItem.amount ?? '' : 50000}" aria-label="Loading dose amount"><span class="uom">IU</span></div></div>` : '';
  openSheet(log ? 'Edit D3 regimen' : 'Track D3 Regimen', `
    <div class="card" style="margin-top:16px"><b>${esc(d3.schedule_label)}</b>${cid ? '' : ' <span class="muted">(outside a cycle)</span>'}
      <div class="small muted">${esc(d3StatusText(d3))}${d3.schedule !== 'maintenance' && !d3.day ? ` · ${plural(d3.until_maintenance, 'day')} of loading` : ''}</div></div>
    <label class="f">When</label><input type="datetime-local" name="at" value="${at}">
    <label class="f">Taken <span class="muted">— untick what you skipped; change an amount if it differs</span></label>
    ${list.map(row).join('')}${loadingRow}
    <label class="f">Note <span class="muted">(optional)</span></label><input name="note" value="${esc(log?.note || '')}" autocomplete="off">
    <p class="help">Several times a day is fine: each save adds to the day's totals. <a href="#/supplements">Add or remove supplements</a></p>`, {
    submitLabel: log ? 'Save' : 'Save doses',
    extra: log ? `<button type="button" class="btn ghost danger" data-act="deleteSupp" data-id="${log.id}">Delete</button>` : '',
    onSubmit: async f => {
      const num = (v, name) => {
        if (v == null || String(v).trim() === '') return null;
        const n = Number(String(v).replace(/,/g, ''));
        if (!isFinite(n) || n < 0) throw new Error(`${name}: amount isn't a number`);
        return n;
      };
      const items = (f.on || []).map(id => ({ supplement_id: +id, source: f['src_' + id] || 'supplement',
        amount: num(f['amt_' + id], list.find(s => s.id === +id).name) }));
      if (f.loading) items.push({ supplement_id: d3s.id, amount: num(f.loading_amt, 'Loading dose'), source: 'supplement', loading: true });
      if (!items.length) throw new Error('Tick at least one supplement');
      const saved = await api(log ? '/supplement-logs/' + log.id : '/supplement-logs', { method: log ? 'PUT' : 'POST',
        body: { at: f.at, cycle_id: cid, note: f.note, items } });
      if (log) toast('Saved');
      else toast(`D3 regimen · ${plural(saved.items.length, 'supplement')} · ${hhmm(saved.at)}`, [
        { label: 'Undo', fn: async () => { await api('/supplement-logs/' + saved.id, { method: 'DELETE' }); refresh(); } }]);
    },
  });
}

function supplementEditSheet(s = null) {
  const d3 = s?.role === 'd3';
  openSheet(s ? 'Edit supplement' : 'New supplement', `
    <label class="f">Name</label><input name="name" value="${esc(s?.name || '')}" placeholder="e.g. Vitamin C">
    <div class="row"><div><label class="f">Dose</label><input name="default_amount" inputmode="decimal" value="${s?.default_amount ?? ''}" placeholder="500"></div>
      <div><label class="f">Unit</label><input name="uom" value="${esc(s?.uom || '')}" placeholder="mg, mcg, IU"></div></div>
    ${d3 ? `<p class="help">The daily target follows the cycle's loading schedule (10,000 IU a day outside a cycle and once maintenance starts).</p>`
      : `<div class="row"><div><label class="f">Daily target</label><input name="target_min" inputmode="decimal" value="${s?.target_min ?? ''}" placeholder="minimum"></div>
      <div><label class="f">Up to <span class="muted">(optional)</span></label><input name="target_max" inputmode="decimal" value="${s?.target_max ?? ''}" placeholder="maximum"></div></div>`}
    <label class="f">Note <span class="muted">(optional)</span></label><input name="target_note" value="${esc(s?.target_note || '')}" placeholder="e.g. glycinate or citrate">
    ${d3 ? '' : `<label class="f">Course length in days <span class="muted">(blank = ongoing)</span></label>
    <input name="course_days" inputmode="numeric" value="${s?.course_days ?? ''}" placeholder="e.g. 90 for B-50">
    <p class="help">With a course length, Track D3 Regimen shows how many days remain, counted from the first dose.</p>`}
    ${s ? `<div class="check"><input type="checkbox" id="sar" name="archived" data-bool${s.archived ? ' checked' : ''}><label for="sar">Archived (hidden from Track D3 Regimen)</label></div>` : ''}
    <label class="f">Sort order <span class="muted">(lower = first)</span></label><input name="sort" inputmode="numeric" value="${s?.sort ?? 100}">`, {
    submitLabel: s ? 'Save' : 'Add',
    extra: s ? `<button type="button" class="btn ghost danger" data-act="deleteSupplement" data-id="${s.id}">${d3 ? 'Archive' : 'Delete'}</button>` : '',
    onSubmit: async f => {
      const num = v => (String(v ?? '').trim() === '' ? null : Number(v));
      const body = { name: f.name, uom: f.uom, target_note: f.target_note, default_amount: num(f.default_amount),
        target_min: d3 ? s.target_min : num(f.target_min), target_max: d3 ? s.target_max : num(f.target_max),
        course_days: d3 ? null : parseInt(f.course_days, 10) || null, archived: !!f.archived, sort: parseInt(f.sort, 10) || 0 };
      for (const k of ['default_amount', 'target_min', 'target_max']) if (Number.isNaN(body[k])) throw new Error('Amounts must be numbers');
      await api(s ? '/supplements/' + s.id : '/supplements', { method: s ? 'PUT' : 'POST', body });
    },
  });
}

function treatmentEditSheet(t = null) {
  openSheet(t ? 'Edit treatment' : 'New treatment', `
    <label class="f">Name</label><input name="name" value="${esc(t?.name || '')}" placeholder="e.g. Zomig nasal spray">
    <label class="f">Category</label><div class="chips">${radios('category', CATS, t?.category || 'abortive')}</div>
    <label class="f">Type</label><div class="chips">${radios('mode', [['dose', 'Dose (one moment)'], ['duration', 'Duration (start, then stop)']], t?.mode || 'dose')}</div>
    <div class="row"><div><label class="f">Default amount</label><input name="default_amount" value="${esc(t?.default_amount || '')}" placeholder="5"></div>
      <div><label class="f">Unit</label><input name="uom" value="${esc(t?.uom || '')}" placeholder="mg, L/min, level"></div></div>
    <div class="check"><input type="checkbox" id="pfx" name="uom_prefix" data-bool${t?.uom_prefix ? ' checked' : ''}><label for="pfx">Unit goes before the amount (e.g. "level 3")</label></div>
    <div class="check"><input type="checkbox" id="qk" name="quick" data-bool${t?.quick ? ' checked' : ''}><label for="qk">Quick: listed first under Medication, one tap logs it</label></div>
    ${t ? `<div class="check"><input type="checkbox" id="ar" name="archived" data-bool${t.archived ? ' checked' : ''}><label for="ar">Archived (hidden from pickers)</label></div>` : ''}
    <label class="f">Daily limit <span class="muted">(doses per 24h — blank for none)</span></label>
    <input name="max_per_day" inputmode="numeric" value="${t?.max_per_day ?? ''}" placeholder="e.g. 2 for triptans">
    <label class="f">Sort order <span class="muted">(lower = first)</span></label><input name="sort" inputmode="numeric" value="${t?.sort ?? 100}">
    <p class="help" id="tpreview"></p>`, {
    submitLabel: t ? 'Save' : 'Add',
    extra: t ? `<button type="button" class="btn ghost danger" data-act="deleteTreatment" data-id="${t.id}">Delete</button>` : '',
    onOpen: form => {
      const sync = () => {
        const f = formValues(form);
        $('#tpreview', form).textContent = f.name ? 'Logs as: ' + doseLabel({ name: f.name, uom: f.uom, uom_prefix: f.uom_prefix }, f.default_amount) : '';
      };
      form.addEventListener('input', sync); form.addEventListener('change', sync); sync();
    },
    onSubmit: async f => {
      const body = { ...f, sort: parseInt(f.sort, 10) || 0, archived: !!f.archived, max_per_day: parseInt(f.max_per_day, 10) || null };
      await api(t ? '/treatments/' + t.id : '/treatments', { method: t ? 'PUT' : 'POST', body });
      await loadTreatments();
    },
  });
}

/* ---------------------------------------------------------------- actions */

const ACT = {
  closeSheet: () => closeSheet(),
  newCycle: () => cycleSheet(),
  editCycle: async d => cycleSheet(await api('/cycles/' + d.id)),
  endCycle: async d => {
    const c = await api('/cycles/' + d.id);
    const saved = await api('/cycles/' + d.id, { method: 'PUT', body: { ...c, ended_on: today() } });
    closeSheet(); await refresh();
    learningsSheet(saved, true);
  },
  deleteCycle: async d => {
    if (!confirm('Delete this cycle? Its headaches and entries are kept and moved to "Outside a cycle".')) return;
    await api('/cycles/' + d.id, { method: 'DELETE' }); closeSheet(); location.hash = '#/';
  },
  editLearnings: async d => learningsSheet(await api('/cycles/' + d.id), false),
  tab: d => { S.tab = d.v; refresh(); },
  meds: d => { S.meds = d.v; refresh(); },
  startAttack: d => startAttackSheet(d.cycle),
  addTreatment: async d => treatmentSheet({ cycle: d.cycle || null, attack: d.attack || null, recent: await recentSince() }),
  addNote: d => noteSheet({ cycle: d.cycle || null, attack: d.attack || null }),
  addPain: d => painSheet({ attack: d.attack }),
  editEntry: d => {
    const e = S.entries[d.id];
    if (!e) return;
    if (e.kind === 'pain') painSheet({ entry: e });
    else if (e.kind === 'note') noteSheet({ entry: e });
    else treatmentSheet({ entry: e });
  },
  deleteEntry: async d => {
    if (!confirm('Delete this entry?')) return;
    await api('/entries/' + d.id, { method: 'DELETE' }); closeSheet(); refresh();
  },
  editAttack: d => attackSheet(S.attacks[d.id] || S.attack),
  deleteAttack: async d => {
    if (!confirm('Delete this headache and everything logged inside it?')) return;
    const a = S.attacks[d.id] || S.attack;
    await api('/attacks/' + d.id, { method: 'DELETE' }); closeSheet();
    location.hash = a && a.cycle_id ? '#/cycle/' + a.cycle_id : '#/loose';
  },
  endAttack: () => endAttackSheet(S.attack),
  stopEntry: d => {
    const e = S.entries[d.id];
    if (!e) return;
    const now = nowLocal();
    openSheet(`Stop ${e.title}`, `<p class="muted">Started ${hhmm(e.at)} · running ${fmtDur(minsSince(e.at))}</p>
      <label class="f">Stopped at</label><input type="datetime-local" name="ended_at" value="${now < e.at ? e.at : now}">`, {
      submitLabel: 'Stop',
      onSubmit: async f => {
        const x = await api(`/entries/${e.id}/stop`, { method: 'POST', body: f });
        toast(`${x.title} stopped · ${fmtDur(minsBetween(x.at, x.ended_at))}`);
      },
    });
  },
  addEvent: d => addEventSheet(d),
  trackD3: d => regimenSheet({ cycle: d.cycle || null }),
  editSupp: d => { const l = S.supps[d.id]; if (l) regimenSheet({ log: l }); },
  deleteSupp: async d => {
    if (!confirm('Delete these supplement doses?')) return;
    await api('/supplement-logs/' + d.id, { method: 'DELETE' }); closeSheet(); refresh();
  },
  editSupplement: d => supplementEditSheet(d.id ? S.supplements.find(s => s.id === +d.id) : null),
  deleteSupplement: async d => {
    if (!confirm('Remove this supplement? If it has been logged it will be archived instead, so your history stays intact.')) return;
    const r = await api('/supplements/' + d.id, { method: 'DELETE' });
    closeSheet(); toast(r.archived ? 'Archived' : 'Deleted'); refresh();
  },
  editTreatment: d => treatmentEditSheet(d.id ? treatment(d.id) : null),
  deleteTreatment: async d => {
    if (!confirm('Delete this treatment? If it has been used it will be archived instead, so your history stays intact.')) return;
    const r = await api('/treatments/' + d.id, { method: 'DELETE' });
    await loadTreatments(); closeSheet(); toast(r.archived ? 'Archived (it is used in your log)' : 'Deleted'); refresh();
  },
  preset: (d) => {
    const f = $('#exp');
    f.start.value = d.start || addDays(today(), -(+d.days - 1));
    f.end.value = today();
    updatePreview();
  },
  openReport: d => {
    const f = exportParams();
    window.open('/api' + reportQuery(f, d.fmt) + (d.dl ? '&download=true' : ''), '_blank');
  },
  copyReport: async () => {
    const t = await api(reportQuery(exportParams(), 'text'));
    toast((await copyText(t)) ? 'Report copied — paste it into an email' : 'Copy failed — select the preview text instead');
  },
  theme: async (d, el) => {
    applyTheme(d.v);
    el.parentElement.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', c === el));
    S.settings = await api('/settings', { method: 'PUT', body: { theme: d.v } });
  },
  fontScale: async (d, el) => {
    applyFontScale(d.v);
    el.parentElement.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', c === el));
    S.settings = await api('/settings', { method: 'PUT', body: { font_scale: d.v } });
  },
  saveSettings: async () => {
    const f = formValues($('#settings'));
    delete f.geo;
    f.pain_locations = f.pain_locations.split('\n');
    f.pain_types = f.pain_types.split('\n');
    S.settings = await api('/settings', { method: 'PUT', body: f });
    toast('Settings saved');
    refresh();
  },
  geocode: async () => {
    const form = $('#settings');
    const name = form.geo.value.trim();
    if (!name) return;
    const res = await api('/geocode?name=' + encodeURIComponent(name));
    $('#georesults').innerHTML = res.length ? res.map(r =>
      `<button type="button" class="list-row" data-act="pickPlace" data-lat="${r.lat}" data-lon="${r.lon}" data-label="${esc(r.label)}"><span>${esc(r.label)}</span><span class="small muted">${r.lat.toFixed(2)}, ${r.lon.toFixed(2)}</span></button>`).join('')
      : '<p class="help">No matches.</p>';
  },
  pickPlace: d => {
    const form = $('#settings');
    form.lat.value = d.lat; form.lon.value = d.lon; form.place.value = d.label;
    $('#georesults').innerHTML = `<p class="help">Selected <b>${esc(d.label)}</b> — tap Save settings.</p>`;
  },
  backupNow: async () => { const r = await api('/backups', { method: 'POST' }); toast('Saved ' + r.name); },
  importLog: async d => {
    const f = formValues($('#importf'));
    const body = { text: f.text, year: parseInt(f.year, 10), cycle_id: f.cycle_id ? +f.cycle_id : null, dry_run: !!d.dry };
    if (!body.text.trim()) throw new Error('Paste a log first');
    if (!d.dry && !confirm('Import these entries?')) return;
    const r = await api('/import/text', { method: 'POST', body });
    const pre = $('#importpreview');
    pre.classList.remove('hide');
    if (d.dry) {
      pre.textContent = `${r.count} entries found.\n\n` + r.rows.map(x => `${x.at.replace('T', ' ')}  ${x.kind === 'pain' ? `KIP ${x.kip}  ` : ''}${x.note}`).join('\n')
        + (r.errors.length ? `\n\nCouldn't place these lines:\n${r.errors.join('\n')}` : '');
    } else {
      pre.textContent = `Imported ${r.count} entries.`;
      toast(`Imported ${r.count} entries`);
    }
  },
};

document.addEventListener('click', async ev => {
  const el = ev.target.closest('[data-act]');
  if (!el || el.contains(ev.target.closest('a[href]'))) return;
  const fn = ACT[el.dataset.act];
  if (!fn) return;
  ev.preventDefault();
  try { await fn(el.dataset, el, ev); } catch (e) { toast(e.message); }
});
document.addEventListener('keydown', ev => {
  if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.matches('[role=button][data-act]')) { ev.preventDefault(); ev.target.click(); }
  if (ev.key === 'Escape') closeSheet();
});

/* ---------------------------------------------------------------- router */

const ROUTES = [
  [/^#?\/?$/, viewHome],
  [/^#\/cycle\/(\d+)$/, viewCycle],
  [/^#\/attack\/(\d+)$/, viewAttack],
  [/^#\/loose$/, viewLoose],
  [/^#\/learnings$/, viewLearnings],
  [/^#\/treatments$/, viewTreatments],
  [/^#\/supplements$/, viewSupplements],
  [/^#\/med\/(\d+)\/(\d+|none|all)$/, viewMed],
  [/^#\/export$/, viewExport],
  [/^#\/settings$/, viewSettings],
];

let lastRoute = null;
async function render() {
  const hash = location.hash || '#/';
  for (const [re, fn] of ROUTES) {
    const m = hash.match(re);
    if (!m) continue;
    if (hash !== lastRoute) { closeSheet(); setBar(''); }
    try { await fn(...m.slice(1)); } catch (e) {
      app.innerHTML = pageHead('Something went wrong', '#/') + `<div class="empty"><p>${esc(e.message)}</p><a class="btn" href="#/">Home</a></div>`;
      setBar('');
    }
    if (hash !== lastRoute) window.scrollTo(0, 0);
    lastRoute = hash;
    return;
  }
  location.hash = '#/';
}
async function refresh() {
  const y = S.justEnded ? 0 : window.scrollY;  // show the "attack over" card from the top
  await render();
  window.scrollTo(0, y);
}

function tick() {
  applyTheme();
  document.querySelectorAll('.ago[data-since]').forEach(el => { el.textContent = fmtDur(minsSince(el.dataset.since)); });
}

window.addEventListener('hashchange', render);
document.addEventListener('visibilitychange', () => { if (!document.hidden && !document.querySelector('.sheet-wrap')) refresh(); });
setInterval(tick, 15000);

(async () => {
  try { await Promise.all([loadTreatments(), loadSettings()]); } catch (e) { toast(e.message); }
  render();
})();
