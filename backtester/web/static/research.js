// Research page: drag-and-drop PDFs, search papers, edit and delete library entries.
async function reloadLibrary() {
  const r = await fetch('/research/library');
  if (r.ok) $id('library').innerHTML = await r.text();
}

function showUploadResults(results) {
  const box = $id('upload-results'); box.replaceChildren();
  results.forEach((x) => {
    const line = x.ok
      ? el('div', { class: 'status ' + (x.warning ? 'warn' : 'ok') }, el('span', { class: 'dot', text: x.warning ? '!' : '✓' }),
          `${x.file}: added as “${x.title}”${x.year ? ' (' + x.year + ')' : ''}, ${x.pages} pages${x.has_abstract ? '' : ', no abstract found'}.${x.warning ? ' ' + x.warning : ''}`)
      : el('div', { class: 'status bad' }, el('span', { class: 'dot', text: '✕' }), `${x.file}: ${x.error}`);
    box.append(el('p', { class: 'small' }, line));
  });
}

async function uploadPapers(files) {
  const fd = new FormData();
  [...files].forEach((f) => fd.append('files', f));
  const zone = $id('paper-drop'); zone.style.opacity = .6;
  try {
    const { results } = await API.upload('/api/papers/upload', fd);
    showUploadResults(results);
    const ok = results.filter((r) => r.ok).length;
    toast(ok ? `${ok} paper(s) added to the library. Check the title, then fill in the claimed results.` : 'No papers were added. See the messages below the drop zone.', ok ? 'ok' : 'bad', ok ? 7000 : 0);
    await reloadLibrary();
  } catch (e) { toast(e.message, 'bad', 0); } finally { zone.style.opacity = 1; }
}

function resultCard(p) {
  const add = el('button', { type: 'button', class: 'primary', text: 'Add to library' });
  add.onclick = async () => {
    add.disabled = true;
    try {
      await API.post('/api/papers/add', { title: p.title, authors: p.authors, year: p.year, venue: p.venue, url: p.url, doi: p.doi,
        finding: p.abstract ? p.abstract.slice(0, 600) : '', abstract: p.abstract, openalex_id: p.openalex_id });
      add.textContent = 'Added ✓'; toast('Added to the library.', 'ok'); reloadLibrary();
    } catch (e) { add.disabled = false; toast(e.message, 'bad', 0); }
  };
  const meta = [p.authors, p.year, p.venue, p.cited_by ? `cited ${p.cited_by.toLocaleString()} times` : ''].filter(Boolean).join(' · ');
  const kids = [el('div', { class: 'row between' }, el('h3', { text: p.title }), add), el('p', { class: 'muted small', text: meta })];
  if (p.abstract) kids.push(el('details', {}, el('summary', { text: 'Abstract' }), el('p', { class: 'abstract', text: p.abstract })));
  else kids.push(el('p', { class: 'muted small', text: 'No abstract available.' }));
  const links = el('p', { class: 'small' });
  if (p.url) links.append(el('a', { href: p.url, target: '_blank', rel: 'noopener noreferrer', text: 'Source' }));
  if (p.open_pdf) { links.append(' · '); links.append(el('a', { href: p.open_pdf, target: '_blank', rel: 'noopener noreferrer', text: 'Open-access PDF (download it, then drop it on the left)' })); }
  kids.push(links);
  return el('div', { class: 'card paper' }, ...kids);
}

document.addEventListener('DOMContentLoaded', () => {
  dropZone($id('paper-drop'), $id('paper-file'), uploadPapers);
  const showKey = async () => { try { const s = await API.get('/api/settings'); $id('key-status').textContent = s.openalex_key_set ? 'A key is saved.' : 'No key saved (using the free shared allowance).'; } catch (e) { /* ignore */ } };
  showKey();
  $id('save-key').addEventListener('click', async () => {
    const v = $id('openalex-key').value.trim(); if (!v) { toast('Paste a key first.', 'warn'); return; }
    try { await API.post('/api/settings', { openalex_api_key: v }); $id('openalex-key').value = ''; toast('Key saved on this computer.', 'ok'); showKey(); } catch (e) { toast(e.message, 'bad', 0); }
  });
  $id('clear-key').addEventListener('click', async () => { try { await API.post('/api/settings', { openalex_api_key: '' }); toast('Key removed.', 'ok'); showKey(); } catch (e) { toast(e.message, 'bad', 0); } });
  rememberForm('papers', ['search-q']);
  $id('search-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = $id('search-q').value.trim(), box = $id('search-results'), btn = $id('search-btn');
    btn.disabled = true; btn.textContent = 'Searching…'; box.replaceChildren();
    try {
      const { results } = await API.get('/api/papers/search?q=' + encodeURIComponent(q));
      box.append(el('h2', { text: results.length ? `Results for “${q}”` : 'No results' }));
      if (!results.length) box.append(el('p', { class: 'muted', text: 'Try different or fewer words.' }));
      results.forEach((p) => box.append(resultCard(p)));
    } catch (err) { toast(err.message, 'bad', 0); } finally { btn.disabled = false; btn.textContent = 'Search'; }
  });
  // Buttons inside library cards (the library is re-rendered, so listen on the container).
  $id('library').addEventListener('click', async (e) => {
    const card = e.target.closest('.paper'); if (!card) return;
    const id = card.dataset.id;
    if (e.target.classList.contains('copy-prompt')) {
      try { await navigator.clipboard.writeText(e.target.dataset.prompt); toast('Copied. Paste it into Claude Code.', 'ok', 4000); }
      catch (err) { prompt('Copy this text:', e.target.dataset.prompt); }
    } else if (e.target.classList.contains('delete-paper')) {
      if (!confirm('Delete this paper from the library, including its saved PDF? Results you ran from it are kept.')) return;
      try { await API.post(`/api/papers/${id}/delete`); toast('Paper deleted.', 'ok'); reloadLibrary(); } catch (err) { toast(err.message, 'bad', 0); }
    }
  });
  $id('library').addEventListener('submit', async (e) => {
    if (!e.target.classList.contains('edit-form')) return;
    e.preventDefault();
    const id = e.target.closest('.paper').dataset.id, f = new FormData(e.target);
    const body = { title: f.get('title'), authors: f.get('authors'), year: f.get('year'), venue: f.get('venue'), url: f.get('url'),
      finding: f.get('finding'), claims: f.get('claims'), status: f.get('status'), claims_from_full_text: f.get('claims_from_full_text') === 'on' };
    try { await API.post(`/api/papers/${id}/update`, body); toast('Saved.', 'ok', 3000); reloadLibrary(); } catch (err) { toast(err.message, 'bad', 0); }
  });
});
