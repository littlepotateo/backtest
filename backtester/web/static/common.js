// Helpers shared by every page: requests, toasts, background-task cards, refresh.
const $id = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
  kids.flat().forEach((k) => e.append(k));
  return e;
};

const API = {
  async request(url, options) {
    let r;
    try { r = await fetch(url, options); } catch (e) { throw new Error('Could not reach the dashboard server. Is it still running?'); }
    let j = {};
    try { j = await r.json(); } catch (e) { /* not JSON */ }
    if (!r.ok) throw new Error(j.error || j.detail || `The server answered with an error (${r.status}).`);
    return j;
  },
  get(url) { return this.request(url); },
  post(url, body) { return this.request(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }); },
  upload(url, formData) { return this.request(url, { method: 'POST', body: formData }); },
};

function toast(message, kind = 'info', ms = 7000) {
  const box = $id('toasts');
  const t = el('div', { class: `toast ${kind}`, role: kind === 'bad' ? 'alert' : 'status' }, el('span', { text: message }),
    el('button', { type: 'button', 'aria-label': 'Dismiss', text: '×' }));
  t.querySelector('button').onclick = () => t.remove();
  box.append(t);
  if (ms) setTimeout(() => t.remove(), ms);
}

// A card in the Activity panel that follows one background task until it finishes.
async function followTask(taskId, container, title) {
  const status = el('span', { class: 'status wait' }, el('span', { class: 'spinner', 'aria-hidden': 'true' }), 'Working…');
  const log = el('pre', { class: 'log small' });
  const card = el('div', { class: 'card task' }, el('div', { class: 'row between' }, el('strong', { text: title }), status), log);
  container.prepend(card);
  for (;;) {
    let t;
    try { t = await API.get(`/api/tasks/${taskId}`); } catch (e) { status.className = 'status bad'; status.textContent = '✕ ' + e.message; return null; }
    log.textContent = t.log.join('\n');
    log.scrollTop = log.scrollHeight;
    if (t.status !== 'running') {
      const ok = t.status === 'done';
      status.className = 'status ' + (ok ? 'ok' : 'bad');
      status.textContent = ok ? '✓ Done' : '✕ Failed';
      if (!ok && t.error) card.append(el('p', { class: 'error-line', text: t.error }));
      const partial = ok && t.result && t.result.failed && t.result.failed.length;
      if (partial) { status.className = 'status warn'; status.textContent = `! Done, ${t.result.failed.length} failed`; }
      toast(ok ? (partial ? `${title}: finished with ${t.result.failed.length} failure(s). See Activity.` : `${title}: done.`) : `${title}: failed. ${t.error || ''}`,
        ok ? (partial ? 'warn' : 'ok') : 'bad', ok ? 5000 : 0);
      return t;
    }
    await new Promise((r) => setTimeout(r, 700));
  }
}

// Reload from disk and reset what this browser remembers (filters, last-used form values, finished messages).
async function refreshUI() {
  const btn = $id('refresh-btn');
  if (btn) { btn.disabled = true; btn.textContent = '↻ Refreshing…'; }
  try { await API.post('/api/refresh'); } catch (e) { /* the page reloads anyway */ }
  let theme = null;
  try { theme = localStorage.getItem('theme'); sessionStorage.clear(); localStorage.clear(); if (theme) localStorage.setItem('theme', theme); } catch (e) { /* storage blocked */ }
  window.location.assign(window.location.pathname);   // a fresh load, without the query string
}
document.addEventListener('DOMContentLoaded', () => { const b = $id('refresh-btn'); if (b) b.addEventListener('click', refreshUI); });

// Remember a form's values between visits (cleared by Refresh).
function rememberForm(id, fields) {
  const key = 'form:' + id;
  try {
    const saved = JSON.parse(localStorage.getItem(key) || '{}');
    fields.forEach((n) => { const f = $id(n); if (f && saved[n] != null) f.value = saved[n]; });
    fields.forEach((n) => { const f = $id(n); if (f) f.addEventListener('input', () => {
      const cur = JSON.parse(localStorage.getItem(key) || '{}'); cur[n] = f.value; localStorage.setItem(key, JSON.stringify(cur)); }); });
  } catch (e) { /* storage blocked */ }
}

// Drag-and-drop zone: calls onFiles(FileList) for dropped or chosen files.
function dropZone(zone, input, onFiles) {
  ['dragenter', 'dragover'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove('over'); }));
  zone.addEventListener('drop', (e) => { if (e.dataTransfer.files.length) onFiles(e.dataTransfer.files); });
  zone.addEventListener('click', () => input.click());
  zone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
  input.addEventListener('change', () => { if (input.files.length) { onFiles(input.files); input.value = ''; } });
  // a file dropped outside the zone would make the browser open it and leave the page
  ['dragover', 'drop'].forEach((ev) => window.addEventListener(ev, (e) => e.preventDefault()));
}
