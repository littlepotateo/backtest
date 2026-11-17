// Data page: download, import, update, delete, check.
const INTERVAL_LABEL = { '1d': 'Daily', '1h': 'Hourly', '30m': '30 min', '15m': '15 min', '5m': '5 min', '2m': '2 min', '1m': '1 min', '1w': 'Weekly' };
let busy = 0;

function renderDatasets(rows) {
  const body = document.querySelector('#datasets tbody');
  body.replaceChildren();
  $id('datasets-empty').hidden = rows.length > 0;
  document.querySelector('#datasets').hidden = rows.length === 0;
  rows.forEach((d) => {
    const st = d.stale ? el('span', { class: 'status warn' }, el('span', { class: 'dot', text: '!' }), `${d.age_days} days old`)
                       : el('span', { class: 'status ok' }, el('span', { class: 'dot', text: '✓' }), 'Up to date');
    const upd = el('button', { type: 'button', text: 'Update' });
    const del = el('button', { type: 'button', class: 'danger', text: 'Delete' });
    upd.onclick = () => run(`Update ${d.symbol}`, () => API.post('/api/data/fetch', { items: [{ symbol: d.symbol, interval: d.interval, start: d.start }] }));
    del.onclick = async () => {
      if (!confirm(`Delete the saved ${d.symbol} (${INTERVAL_LABEL[d.interval] || d.interval}) data? You can download it again later.`)) return;
      try { await API.post('/api/data/delete', { symbol: d.symbol, interval: d.interval }); toast(`${d.symbol} deleted.`, 'ok'); loadDatasets(); } catch (e) { toast(e.message, 'bad', 0); }
    };
    const label = d.kind === 'rate' ? `${d.symbol} (interest rate)` : d.kind === 'index' ? `${d.symbol} (index)` : d.symbol;
    body.append(el('tr', {}, el('td', { text: label }), el('td', { text: INTERVAL_LABEL[d.interval] || d.interval }), el('td', { text: d.start }), el('td', { text: d.end }),
      el('td', { class: 'n', text: d.bars.toLocaleString() }), el('td', { text: d.source }), el('td', {}, st), el('td', { class: 'row' }, upd, del)));
  });
  const hasRates = rows.some((d) => d.symbol === '^IRX');
  const rs = $id('rates-status'); rs.replaceChildren();
  rs.append(hasRates ? el('span', { class: 'status ok' }, el('span', { class: 'dot', text: '✓' }), 'Downloaded')
                     : el('span', { class: 'status warn' }, el('span', { class: 'dot', text: '!' }), 'Not downloaded yet'));
}

async function loadDatasets() {
  try { renderDatasets((await API.get('/api/data/list')).datasets); } catch (e) { toast(e.message, 'bad', 0); }
}

// Start a task through `starter`, show it in Activity, and refresh the table when it ends.
async function run(title, starter) {
  $id('activity-empty')?.remove();
  busy++; document.querySelectorAll('button[type=submit], #rates-btn, #update-btn, #check-btn').forEach((b) => { b.disabled = true; });
  try {
    const { task_id } = await starter();
    await followTask(task_id, $id('activity'), title);
  } catch (e) {
    toast(e.message, 'bad', 0);
  } finally {
    busy--; if (!busy) document.querySelectorAll('button[type=submit], #rates-btn, #update-btn, #check-btn').forEach((b) => { b.disabled = false; });
    loadDatasets();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  renderDatasets(JSON.parse($id('initial-datasets').textContent));
  rememberForm('data', ['symbols', 'start', 'interval']);
  $id('fetch-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const symbols = $id('symbols').value.trim();
    if (!symbols) { toast('Type at least one symbol, for example SPY.', 'warn'); return; }
    run('Download ' + symbols.slice(0, 40), () => API.post('/api/data/fetch', { symbols, start: $id('start').value, interval: $id('interval').value }));
  });
  document.querySelectorAll('.quick').forEach((b) => b.addEventListener('click', () => {
    $id('symbols').value = b.dataset.symbols; $id('symbols').dispatchEvent(new Event('input'));
  }));
  $id('rates-btn').addEventListener('click', () => run('Download interest rates', () => API.post('/api/data/rates', {})));
  $id('update-btn').addEventListener('click', () => run('Update all datasets', () => API.post('/api/data/update', {})));
  $id('check-btn').addEventListener('click', () => run('Check my setup', () => API.post('/api/data/check', {})));
  dropZone($id('data-drop'), $id('data-file'), (files) => {
    const fd = new FormData();
    [...files].forEach((f) => fd.append('files', f));
    const sym = $id('import-symbol').value.trim(); if (sym) fd.append('symbol', sym);
    run(`Import ${files.length} file(s)`, () => API.upload('/api/data/upload', fd));
  });
});
