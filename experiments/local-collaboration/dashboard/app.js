'use strict';
const $ = id => document.getElementById(id);
let token = '', current = null, busy = false, chosen = '';
let refreshGeneration = 0;
const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; };
const date = seconds => new Date(seconds * 1000).toLocaleString();
const short = id => id.slice(0, 8);
function state(value) { const marks = {current:'✓', completed:'✓', stale:'△', unverifiable:'?', active:'◇', accepted:'○', abandoned:'×', rejected:'×', proposed:'◌', testing:'◇', superseded:'↪'}; return el('span', `${marks[value] || '○'} ${value}`, `chip state-${value}`); }
function announce(text, error = false) { $('notice').hidden = true; $('error').hidden = true; const node = $(error ? 'error' : 'notice'); node.textContent = text; node.hidden = false; if (error) node.focus(); }
async function api(path, data) {
  const options = {headers: {'X-Lattice-Token': token}, cache:'no-store'};
  if (data !== undefined) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(data); }
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload.result;
}
async function refresh() {
  const generation = ++refreshGeneration;
  try {
    const result = await api('/api/status');
    if (generation !== refreshGeneration) return;
    current = result; render(result);
    $('connection').textContent = '✓ Local database connected';
    $('updated').textContent = `Observed ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    if (generation === refreshGeneration) throw error;
  }
}
async function mutate(path, data, message, form) {
  if (busy) return;
  busy = true; const buttons = [...document.querySelectorAll('button')]; buttons.forEach(b => b.disabled = true);
  try { await api(path, data); if (form) form.reset(); await refresh(); announce(message); }
  catch (error) { announce(error.message, true); }
  finally { busy = false; document.querySelectorAll('button').forEach(b => b.disabled = false); }
}
function button(text, action) { const b = el('button', text); b.type = 'button'; b.addEventListener('click', action); return b; }
function options(id, items, label, empty) { const select = $(id), value = select.value; select.replaceChildren(el('option', empty)); select.firstChild.value = ''; for (const item of items) { const o = el('option', label(item)); o.value = item.id; select.append(o); } select.value = [...select.options].some(o => o.value === value) ? value : ''; }
function render(s) {
  $('root').textContent = s.workspace.root; $('protocol').textContent = s.workspace.protocol;
  $('count-active').textContent = s.intentions.filter(i => i.status === 'active').length;
  $('count-conflicts').textContent = s.conflicts.length;
  $('count-stale').textContent = s.observations.filter(o => o.state === 'stale').length;
  $('count-alternatives').textContent = s.alternatives.length;
  const actors = s.actors || [];
  $('actors').replaceChildren(); $('actor-names').replaceChildren();
  for (const actor of actors) { const row = el('div', undefined, 'actor-row'); row.append(el('strong', actor.name), el('span', actor.registration === 'explicit' ? 'Registered' : 'From intention')); $('actors').append(row); const o = el('option'); o.value = actor.name; $('actor-names').append(o); }
  if (!actors.length) $('actors').append(el('p', 'No actor names recorded yet.', 'empty'));
  options('supersedes', s.intentions.filter(i => i.status === 'active'), i => `${i.actor} · ${short(i.id)} · r${i.revision}`, 'New intention');
  options('alternative-intent', s.intentions, i => `${i.actor} · ${short(i.id)} · ${i.status}`, 'Choose an intention');
  $('conflicts').replaceChildren();
  for (const c of s.conflicts) { const row = el('div', undefined, 'record overlap'); row.append(el('strong', `△ ${c.kind} overlap`), el('p', `${short(c.left_intent)} / ${c.left_path} ↔ ${short(c.right_intent)} / ${c.right_path}`)); $('conflicts').append(row); }
  const observations = new Map(s.observations.map(o => [o.intent_id, o]));
  $('intentions').replaceChildren();
  for (const i of [...s.intentions].reverse()) {
    const card = el('article', undefined, 'record' + (chosen === i.id ? ' selected' : '')); card.id = `intent-${i.id}`;
    const heading = el('div', undefined, 'record-header'); heading.append(el('strong', `${i.actor} · revision ${i.revision}`), state(i.status)); card.append(heading, el('code', i.id));
    card.append(el('p', `Read: ${i.reads.join(', ') || 'None'}`), el('p', `Write: ${i.writes.join(', ') || 'None'}`));
    const o = observations.get(i.id);
    if (o) { card.append(state(o.state)); if (o.changed_paths?.length) card.append(el('p', `Changed: ${o.changed_paths.join(', ')}`)); if (o.error) card.append(el('p', o.error)); }
    else card.append(el('p', 'Closed intention · baseline is no longer re-observed.', 'muted'));
    const detail = el('details'); detail.append(el('summary', 'Baseline details'), el('p', `Captured ${date(i.created_at)}`), el('code', i.baseline_digest)); if (i.supersedes) detail.append(el('p', `Supersedes ${i.supersedes}`)); card.append(detail);
    if (i.status === 'active') { const actions = el('div', undefined, 'actions'); for (const status of ['completed', 'abandoned']) actions.append(button(status === 'completed' ? 'Close as completed ✓' : 'Abandon intention ×', () => mutate('/api/intentions/finish', {id:i.id,status}, `Intention ${short(i.id)} recorded as ${status}. This is a declaration, not test evidence.`))); card.append(actions); }
    $('intentions').append(card);
  }
  if (!s.intentions.length) $('intentions').append(el('p', 'No intentions yet. Declare read and write scopes to start the shared record.', 'empty'));
  $('alternatives').replaceChildren();
  for (const a of [...s.alternatives].reverse()) {
    const card = el('article', undefined, 'record'); const heading = el('div', undefined, 'record-header'); heading.append(el('strong', a.label), state(a.status)); card.append(heading, el('code', a.id), el('p', `Intention ${a.intent_id}`), el('p', `Location: ${a.location}`), el('p', a.candidate_digest ? `Caller-asserted SHA-256: ${a.candidate_digest}` : 'Candidate digest: not supplied'));
    const actions = el('div', undefined, 'actions'); for (const status of ['proposed','testing','accepted','rejected']) { const b = button(status === 'accepted' ? 'Select accepted (advisory)' : `Set ${status}`, () => mutate('/api/alternatives/status', {id:a.id,status}, `Candidate ${short(a.id)} recorded as ${status}. Source files were not changed.`)); b.setAttribute('aria-pressed', String(status === a.status)); actions.append(b); } card.append(actions); $('alternatives').append(card);
  }
  if (!s.alternatives.length) $('alternatives').append(el('p', 'No alternatives recorded. Preserve a candidate location and label to compare directions.', 'empty'));
  $('events').replaceChildren();
  for (const e of [...s.events].reverse().slice(0,40)) { const row = el('li'); const time = el('time', date(e.time)); time.dateTime = new Date(e.time * 1000).toISOString(); const details = el('details'); details.append(el('summary', `#${e.sequence} ${e.kind}`), el('pre', JSON.stringify(e.data,null,2))); row.append(time, details); $('events').append(row); }
  if (!s.events.length) $('events').append(el('li', 'No events recorded.'));
  lattice(s, observations);
}
function svg(tag, attrs = {}, text) { const node = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [key,value] of Object.entries(attrs)) node.setAttribute(key, value); if (text !== undefined) node.textContent = text; return node; }
function lattice(s, observations) {
  const canvas = $('lattice'); canvas.replaceChildren();
  for (const r of [70,130,190]) { const points = Array.from({length:6}, (_,k) => `${350+r*Math.cos(k*Math.PI/3)},${218+r*Math.sin(k*Math.PI/3)}`).join(' '); canvas.append(svg('polygon',{points,fill:'none',stroke:'#22262b','stroke-dasharray':'4 7'})); }
  const shown = s.intentions.slice(-48), points = new Map();
  shown.forEach((item,k) => { const ring = k < 6 ? 0 : k < 18 ? 1 : 2; const base = [0,6,18][ring], count = [6,12,30][ring], r = [70,130,190][ring]; const angle = (k-base) * 2*Math.PI/count-Math.PI/2; points.set(item.id,{x:350+r*Math.cos(angle),y:218+r*Math.sin(angle)}); });
  for (const c of s.conflicts) { const a = points.get(c.left_intent), b = points.get(c.right_intent); if (a && b) canvas.append(svg('line',{x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:'#f2ab6d','stroke-opacity':'.65','stroke-dasharray':'4 5'})); }
  canvas.append(svg('circle',{cx:350,cy:218,r:22,fill:'#3a2717',stroke:'#f2ab6d','stroke-width':1.5}),svg('text',{x:350,y:222,fill:'#f2ab6d','text-anchor':'middle','font-size':13},'○'),svg('text',{x:350,y:262,fill:'#a9b0b9','text-anchor':'middle','font-size':10},'Human direction'));
  for (const i of shown) { const {x,y} = points.get(i.id), observation = observations.get(i.id)?.state || i.status; const color = ['stale','unverifiable','abandoned'].includes(observation) ? '#f2ab6d' : i.status === 'active' ? '#7cc6f2' : '#868e98'; const node = svg('g',{'class':'node',tabindex:0,role:'button','aria-label':`${i.actor}, intention ${short(i.id)}, ${i.status}, baseline ${observation}. Inspect intention.`}); node.append(svg('title',{},`${i.actor} · ${short(i.id)} · ${observation}`),svg('circle',{cx:x,cy:y,r:23,fill:'transparent',stroke:'none','class':'hit'}),svg('polygon',{points:`${x},${y-10} ${x+10},${y} ${x},${y+10} ${x-10},${y}`,fill:i.status === 'active' ? '#13303f' : '#14171a',stroke:color,'stroke-width':1.5}),svg('text',{x,y:y+31,fill:color,'text-anchor':'middle','font-size':9},short(i.id)));
    const focus = () => { chosen = i.id; document.querySelectorAll('.record.selected').forEach(n => n.classList.remove('selected')); const card = $(`intent-${i.id}`); card.classList.add('selected'); card.tabIndex = -1; card.focus(); card.scrollIntoView({block:'center'}); }; node.addEventListener('click',focus); node.addEventListener('keydown',event => { if (['Enter',' '].includes(event.key)) {event.preventDefault();focus();} }); canvas.append(node);
  }
  $('lattice-caption').textContent = shown.length ? `${shown.length} of ${s.intentions.length} intentions shown · select a diamond to inspect · dashed edges are scope overlaps` : 'No intentions recorded. The lattice will grow from real declarations.';
}
$('actor-form').addEventListener('submit', event => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.target)); mutate('/api/actors', data, `Actor name “${data.name}” registered as caller-asserted.`, event.target); });
$('intent-form').addEventListener('submit', event => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.target)); data.reads = data.reads.split('\n').map(x => x.trim()).filter(Boolean); data.writes = data.writes.split('\n').map(x => x.trim()).filter(Boolean); if (!data.supersedes) delete data.supersedes; mutate('/api/intentions', data, 'Intention recorded with a baseline of the current scoped files.', event.target); });
$('alternative-form').addEventListener('submit', event => { event.preventDefault(); const data = Object.fromEntries(new FormData(event.target)); if (!data.candidate_digest) delete data.candidate_digest; mutate('/api/alternatives', data, 'Alternative preserved as proposed. No candidate content was fetched or applied.', event.target); });
$('refresh').addEventListener('click', async () => { try { await refresh(); announce('Current database and file observations refreshed.'); } catch(error) { announce(error.message,true); } });
async function start() { try { const response = await fetch('/api/session',{headers:{'X-Lattice-Bootstrap':'1'},cache:'no-store'}); const session = await response.json(); if (!response.ok || !session.ok) throw new Error(session.error || 'Bootstrap failed'); token = session.token; await refresh(); } catch(error) { $('connection').textContent = '△ Disconnected'; announce(error.message,true); } }
setInterval(async () => { if (!token || busy || document.hidden || document.activeElement.matches('input,textarea,select,button,summary')) return; try { await refresh(); } catch(error) { $('connection').textContent = '△ Disconnected'; $('updated').textContent = 'Last rendered state may be outdated. Reload to reconnect.'; } },5000);
start();
