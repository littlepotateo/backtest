// Chart drawing for the dashboard. Colors come from the CSS variables, so a theme switch just redraws.
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
function tokens() {
  return { s1: cssVar('--series-1'), s2: cssVar('--series-2'), text: cssVar('--text-primary'), text2: cssVar('--text-secondary'),
           muted: cssVar('--text-muted'), grid: cssVar('--grid'), surface: cssVar('--surface-1'), pos: cssVar('--pos'),
           neg: cssVar('--neg'), mid: cssVar('--mid'), dark: document.documentElement.dataset.theme === 'dark' ||
           (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches) };
}
const rgba = (hex, a) => { const h = hex.replace('#', ''); const n = parseInt(h, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; };
function layout(t, extra = {}) {
  return Object.assign({ paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', margin: { l: 64, r: 24, t: 16, b: 44 },
    font: { color: t.text2, family: 'system-ui, sans-serif', size: 12 }, hovermode: 'x unified',
    xaxis: { gridcolor: t.grid, linecolor: t.grid, zeroline: false }, yaxis: { gridcolor: t.grid, linecolor: t.grid, zeroline: false },
    legend: { orientation: 'h', y: -0.18, font: { color: t.text2 } }, hoverlabel: { bgcolor: t.surface, font: { color: t.text } } }, extra);
}
const CFG = { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['select2d', 'lasso2d'] };
const $ = (id) => document.getElementById(id);
const DATA = () => JSON.parse(document.getElementById('chart-data').textContent);
const endLabel = (x, y, text, color) => ({ x, y, text, showarrow: false, xanchor: 'right', yanchor: 'bottom', yshift: 6, font: { color: color, size: 12 } });
const fmtPct = (v) => (v == null ? 'n/a' : (v * 100).toFixed(1) + '%');

function drawEquity(d, t) {
  if (!$('equity') || !d.equity) return;
  const log = $('log-scale') && $('log-scale').checked;
  const traces = [{ x: d.equity.x, y: d.equity.y, name: d.strategy_name, mode: 'lines', line: { color: t.s1, width: 2 }, hovertemplate: '$%{y:,.0f}' }];
  const ann = [endLabel(d.equity.x.at(-1), d.equity.y.at(-1), d.strategy_name, t.s1)];
  if (d.benchmark) {
    traces.push({ x: d.benchmark.x, y: d.benchmark.y, name: (d.benchmark_name || 'Benchmark') + ' (buy and hold)', mode: 'lines',
      line: { color: t.s2, width: 2 }, hovertemplate: '$%{y:,.0f}' });
    ann.push(endLabel(d.benchmark.x.at(-1), d.benchmark.y.at(-1), d.benchmark_name || 'Benchmark', t.s2));
  }
  Plotly.react('equity', traces, layout(t, { yaxis: { gridcolor: t.grid, linecolor: t.grid, tickprefix: '$', tickformat: ',.0f', type: log ? 'log' : 'linear' },
    annotations: ann, margin: { l: 72, r: 24, t: 24, b: 56 } }), CFG);
}
function drawDrawdown(d, t) {
  if (!$('drawdown') || !d.drawdown) return;
  const traces = [{ x: d.drawdown.x, y: d.drawdown.y, name: d.strategy_name, mode: 'lines', fill: 'tozeroy', fillcolor: rgba(t.s1, 0.25),
    line: { color: t.s1, width: 2 }, hovertemplate: '%{y:.1f}%' }];
  if (d.bench_drawdown) traces.push({ x: d.bench_drawdown.x, y: d.bench_drawdown.y, name: (d.benchmark_name || 'Benchmark'), mode: 'lines',
    line: { color: t.s2, width: 2 }, hovertemplate: '%{y:.1f}%' });
  Plotly.react('drawdown', traces, layout(t, { yaxis: { gridcolor: t.grid, linecolor: t.grid, ticksuffix: '%', title: { text: 'Fall from peak' } } }), CFG);
}
function drawWalkforward(d, t) {
  if (!$('walkforward') || !d.walkforward.length) return;
  const x = d.walkforward.map((w) => w.window);
  Plotly.react('walkforward', [
    { type: 'bar', x, y: d.walkforward.map((w) => w.is), name: 'In-sample', marker: { color: t.s2 }, hovertemplate: 'Sharpe %{y:.2f}' },
    { type: 'bar', x, y: d.walkforward.map((w) => w.oos), name: 'Out-of-sample', marker: { color: t.s1 }, hovertemplate: 'Sharpe %{y:.2f}' }],
    layout(t, { barmode: 'group', bargap: 0.25, yaxis: { gridcolor: t.grid, linecolor: t.grid, title: { text: 'Sharpe ratio' }, zeroline: true, zerolinecolor: t.muted },
      xaxis: { title: { text: 'Start of the out-of-sample window' }, type: 'category', gridcolor: t.grid } }), CFG);
}
function niceTicks(lo, hi) {
  return [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500].filter((v) => v >= lo * 0.85 && v <= hi * 1.15);
}
function drawFan(d, t) {
  if (!$('fan') || !d.fan) return;
  const f = d.fan, n = f.p50.length, x = f.p50.map((_, i) => Math.round(i * (d.fan_days || n) / (n - 1)));
  const line = (y, name, extra) => Object.assign({ x, y, name, mode: 'lines', line: { width: 0 }, hoverinfo: 'y', showlegend: false }, extra);
  Plotly.react('fan', [
    line(f.p5, '5th'), line(f.p95, '5th to 95th percentile', { fill: 'tonexty', fillcolor: rgba(t.s1, 0.16), showlegend: true }),
    line(f.p25, '25th'), line(f.p75, '25th to 75th percentile', { fill: 'tonexty', fillcolor: rgba(t.s1, 0.32), showlegend: true }),
    { x, y: f.p50, name: 'Median', mode: 'lines', line: { color: t.s1, width: 2 }, hovertemplate: '%{y:.2f}x' }],
    layout(t, { yaxis: { gridcolor: t.grid, linecolor: t.grid, ticksuffix: 'x', title: { text: 'Growth of 1' }, type: 'log',
        tickmode: 'array', tickvals: niceTicks(Math.min(...f.p5), Math.max(...f.p95)), minor: { showgrid: false } },
      xaxis: { title: { text: 'Trading days' }, gridcolor: t.grid } }), CFG);
}
function drawKelly(d, t) {
  if (!$('kelly') || !d.kelly) return;
  const c = d.kelly, pt = d.kelly_point, g = d.kelly_at || {};
  const marks = [['quarter_kelly', 0.25 * pt, 'Quarter Kelly'], ['half_kelly', 0.5 * pt, 'Half Kelly'], ['full_kelly', pt, 'Full Kelly'], ['as_backtested', 1, 'As backtested']]
    .filter((m) => g[m[0]] != null);
  Plotly.react('kelly', [
    { x: c.multiple, y: c.annual_log_growth.map((v) => v * 100), mode: 'lines', name: 'Growth rate', line: { color: t.s1, width: 2 }, hovertemplate: '%{y:.1f}% a year at %{x:.2f}x' },
    { x: marks.map((m) => m[1]), y: marks.map((m) => g[m[0]] * 100), mode: 'markers+text', name: 'Sizing choices', text: marks.map((m) => m[2]),
      textposition: marks.map((m) => ({ quarter_kelly: 'top left', as_backtested: 'bottom right' }[m[0]] || 'top center')),
      textfont: { color: t.text2 }, marker: { size: 10, color: t.s1, line: { color: t.surface, width: 2 } }, hoverinfo: 'skip', showlegend: false }],
    layout(t, { hovermode: 'closest', xaxis: { title: { text: 'Position size, as a multiple of the size backtested' }, gridcolor: t.grid, ticksuffix: 'x' },
      yaxis: { gridcolor: t.grid, ticksuffix: '%', title: { text: 'Long-run growth a year (log)' }, zeroline: true, zerolinecolor: t.muted }, showlegend: false }), CFG);
}
function drawBars(id, labels, values, t, ytitle) {
  if (!$(id)) return;
  Plotly.react(id, [{ type: 'bar', x: labels, y: values.map((v) => v * 100), marker: { color: t.s1 }, text: values.map(fmtPct), textposition: 'outside',
    textfont: { color: t.text2 }, hoverinfo: 'skip', cliponaxis: false }],
    layout(t, { hovermode: false, bargap: 0.4, showlegend: false, yaxis: { gridcolor: t.grid, ticksuffix: '%', title: { text: ytitle }, rangemode: 'tozero' },
      margin: { l: 72, r: 24, t: 32, b: 56 } }), CFG);
}
function drawCosts(d, t) {
  if (!d.costs) return;
  const lv = d.costs.levels;
  drawBars('costs', lv.map((r) => r.cost_multiplier + 'x costs').concat(['1 bar late']), lv.map((r) => r.total_return).concat([d.costs.delayed_fill.total_return]), t, 'Total return');
}
function drawPricing(d, t) {
  if (!d.pricing) return;
  drawBars('pricing', d.pricing.cases.map((c) => c.case), d.pricing.cases.map((c) => c.total_return), t, 'Total return');
}
function drawCompare(t) {
  const el = $('compare'); if (!el) return;
  const d = DATA();
  Plotly.react('compare', [
    { x: d.a.x, y: d.a.y, name: d.a.name, mode: 'lines', line: { color: t.s1, width: 2 }, hovertemplate: '%{y:.2f}x' },
    { x: d.b.x, y: d.b.y, name: d.b.name, mode: 'lines', line: { color: t.s2, width: 2 }, hovertemplate: '%{y:.2f}x' }],
    layout(t, { yaxis: { gridcolor: t.grid, ticksuffix: 'x', title: { text: 'Growth of 1' }, type: $('log-scale') && $('log-scale').checked ? 'log' : 'linear' },
      annotations: [endLabel(d.a.x.at(-1), d.a.y.at(-1), d.a.short, t.s1), endLabel(d.b.x.at(-1), d.b.y.at(-1), d.b.short, t.s2)] }), CFG);
}
async function drawSurface(t) {
  const sel = $('surf-kind'); if (!sel) return;
  const [kind, what] = sel.value.split(':');
  const qs = new URLSearchParams({ kind, what, date: $('surf-date').value, right: $('surf-right').value });
  const box = $('surface'), msg = $('surf-msg');
  const r = await fetch(`/api/run/${window.RUN_ID}/surface?${qs}`);
  if (!r.ok) { msg.textContent = (await r.json()).detail || 'Could not draw this surface.'; Plotly.purge('surface'); return; }
  const s = await r.json();
  msg.textContent = (s.legs ? 'Legs: ' + s.legs.join(', ') + '. ' : '') + (s.note || '') + ' Prices are modelled, not quotes.';
  const blues = t.dark ? [[0, '#0d366b'], [0.5, '#2a78d6'], [1, '#cde2fb']] : [[0, '#cde2fb'], [0.5, '#3987e5'], [1, '#0d366b']];
  const div = [[0, t.neg], [0.5, t.mid], [1, t.pos]];
  const ax = (title) => ({ title: { text: title, font: { color: t.text2 } }, gridcolor: t.grid, color: t.text2, backgroundcolor: 'rgba(0,0,0,0)', showbackground: false });
  Plotly.react('surface', [{ type: 'surface', x: s.x, y: s.y, z: s.z, colorscale: s.scale === 'diverging' ? div : blues,
    cmid: s.scale === 'diverging' ? 0 : undefined, colorbar: { title: { text: s.z_label, font: { color: t.text2 } }, tickfont: { color: t.text2 } },
    hovertemplate: s.x_label + ' %{x:.1f}<br>' + s.y_label + ' %{y:.1f}<br>' + s.z_label + ' %{z:.4f}<extra></extra>' }],
    { paper_bgcolor: 'rgba(0,0,0,0)', margin: { l: 0, r: 0, t: 36, b: 0 }, title: { text: s.title, font: { color: t.text2, size: 13 } },
      scene: { xaxis: ax(s.x_label), yaxis: ax(s.y_label), zaxis: ax(s.z_label), camera: { eye: { x: 1.6, y: -1.6, z: 0.9 } } } }, CFG);
}
function draw() {
  const t = tokens();
  if ($('chart-data') && !$('compare')) {
    const d = DATA();
    drawEquity(d, t); drawDrawdown(d, t); drawWalkforward(d, t); drawFan(d, t); drawKelly(d, t); drawCosts(d, t); drawPricing(d, t);
  }
  drawCompare(t);
  drawSurface(t);
}
function setTheme(mode) {
  if (mode) document.documentElement.dataset.theme = mode; else delete document.documentElement.dataset.theme;
  try { localStorage.setItem('theme', mode || ''); } catch (e) {}
  draw();
}
document.addEventListener('DOMContentLoaded', () => {
  try { const m = localStorage.getItem('theme'); if (m) document.documentElement.dataset.theme = m; } catch (e) {}
  const tb = $('theme-toggle');
  if (tb) tb.addEventListener('click', () => { const dark = tokens().dark; setTheme(dark ? 'light' : 'dark'); });
  document.querySelectorAll('[data-redraw]').forEach((el) => el.addEventListener('change', draw));
  const f = $('run-filter');
  if (f) f.addEventListener('input', () => { const q = f.value.toLowerCase();
    document.querySelectorAll('#runs-table tbody tr').forEach((tr) => { tr.hidden = !tr.textContent.toLowerCase().includes(q); }); });
  draw();
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', draw);
