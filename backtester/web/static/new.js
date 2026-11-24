// New-backtest page: pick a strategy, see what data it needs, fetch what is missing, run.
const PRESETS = {
  quick: { tests: ['checks', 'montecarlo'], paths: 1000, synthetic: 0 },
  full: { tests: null, paths: 2000, synthetic: 0 },     // null = the default cheap tests
  deep: { tests: null, paths: 2000, synthetic: 200 },
};
let currentNeeds = null;

function applyPreset(name) {
  const p = PRESETS[name];
  document.querySelectorAll('#test-boxes input').forEach((b) => {
    const isDefault = b.defaultChecked;
    b.checked = p.tests ? p.tests.includes(b.value) : isDefault;
  });
  $id('paths').value = p.paths; $id('synthetic').value = p.synthetic;
}

function renderNeeds(data) {
  currentNeeds = data;
  const box = $id('needs'); box.replaceChildren();
  data.needs.forEach((n) => {
    const st = n.cached ? el('span', { class: 'status ok' }, el('span', { class: 'dot', text: '✓' }), `Ready (${n.first} to ${n.last})`)
                        : el('span', { class: 'status bad' }, el('span', { class: 'dot', text: '✕' }), 'Missing');
    box.append(el('div', { class: 'row between' }, el('span', {}, el('strong', { text: n.symbol }), el('span', { class: 'muted small', text: ` ${n.interval} · ${n.purpose}` })), st));
  });
  const missing = data.needs.filter((n) => !n.cached);
  const btn = $id('fetch-missing');
  btn.hidden = missing.length === 0;
  $id('fetch-note').textContent = missing.length ? '' : 'Everything this strategy needs is downloaded.';
  const rateOnly = missing.length && missing.every((n) => n.symbol === '^IRX');
  if (rateOnly) $id('fetch-note').textContent = 'Only the interest rates are missing; the backtest can run without them but will not earn or pay interest.';
  $id('run-btn').disabled = missing.some((n) => n.symbol !== '^IRX');
  $id('run-note').textContent = $id('run-btn').disabled ? 'Download the missing data first.' : '';
  if (data.suggested_start && !$id('start').value) $id('start').value = data.suggested_start;
  $id('start-hint').textContent = data.suggested_start
    ? `Suggested start: ${data.suggested_start}, which leaves room for the indicators to warm up after the data begins.` : '';
}

let coverageTimer = null;
function currentPath() { const r = document.querySelector('input[name=strategy]:checked'); return r ? r.value : ''; }

async function refreshCoverage() {
  const note = $id('coverage-note');
  const path = currentPath();
  if (!path) { note.textContent = ''; return; }
  const q = `path=${encodeURIComponent(path)}&symbols=${encodeURIComponent($id('symbols').value)}&start=${encodeURIComponent($id('start').value)}`;
  try {
    const c = await API.get('/api/strategies/coverage?' + q);
    if (c.ok) {
      note.textContent = c.earliest_start
        ? `The data covers this run. Earliest usable start: ${c.earliest_start}${c.earliest_train_end ? `; earliest training end: ${c.earliest_train_end}` : ''}.`
        : 'The data covers this run.';
      note.className = 'small ok';
    } else {
      note.textContent = c.problems.join(' ');
      note.className = 'small bad';
    }
  } catch (e) { note.textContent = e.message; note.className = 'small bad'; }
  try {
    const data = await API.get(`/api/strategies/needs?path=${encodeURIComponent(path)}&symbols=${encodeURIComponent($id('symbols').value)}`);
    renderNeeds(data);
  } catch (e) { /* the needs list keeps its last state */ }
}

async function pick(path) {
  $id('after-pick').hidden = false;
  try {
    const data = await API.get('/api/strategies/needs?path=' + encodeURIComponent(path));
    $id('params').value = Object.entries(data.strategy.params).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join('\n');
    $id('start').value = data.suggested_start || '';
    renderNeeds(data);
    refreshCoverage();
  } catch (e) { toast(e.message, 'bad', 0); }
}

document.addEventListener('DOMContentLoaded', () => {
  const radios = document.querySelectorAll('input[name=strategy]');
  radios.forEach((r) => r.addEventListener('change', () => { try { localStorage.setItem('lastStrategy', r.value); } catch (e) { /* ignore */ } pick(r.value); }));
  document.querySelectorAll('input[name=preset]').forEach((r) => r.addEventListener('change', () => applyPreset(r.value)));
  const schedule = () => { clearTimeout(coverageTimer); coverageTimer = setTimeout(refreshCoverage, 350); };
  $id('symbols').addEventListener('input', schedule);
  $id('start').addEventListener('change', schedule);
  let chosen = [...radios].find((r) => r.checked);
  if (!chosen) { try { const last = localStorage.getItem('lastStrategy'); chosen = [...radios].find((r) => r.value === last); if (chosen) chosen.checked = true; } catch (e) { /* ignore */ } }
  if (chosen) pick(chosen.value);
  $id('fetch-missing').addEventListener('click', async () => {
    const missing = currentNeeds.needs.filter((n) => !n.cached).map((n) => ({ symbol: n.symbol, interval: n.interval, start: '2000-01-01' }));
    const btn = $id('fetch-missing'); btn.disabled = true;
    try {
      const { task_id } = await API.post('/api/data/fetch', { items: missing });
      const t = await followTask(task_id, $id('fetch-activity'), 'Download missing data');
      if (t && t.status === 'done') { $id('start').value = ''; await pick(document.querySelector('input[name=strategy]:checked').value); }
    } catch (e) { toast(e.message, 'bad', 0); } finally { btn.disabled = false; }
  });
  $id('new-form').addEventListener('submit', () => { $id('run-btn').disabled = true; $id('run-btn').textContent = 'Starting…'; });
  applyPreset('full');
});
