/* ============================================================
   STAGE F9 — scrape monitor · degraded/error state ·
   methodology + comparison drawers · run-replay scrubber ·
   click-a-corridor-on-the-map. Exposes window.VS.f9.
   ============================================================ */
(function () {
  const VS = window.VS;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  function seedRand(str) {
    let s = 0; for (let i = 0; i < str.length; i++) s += str.charCodeAt(i) * (i + 11) * 2.719;
    return () => { s = Math.sin(s) * 43758.5453; return s - Math.floor(s); };
  }

  /* ---------- scrape monitor ------------------------------- */
  const scrapeMon = document.getElementById('scrapeMon');
  const srcRows = scrapeMon ? [...scrapeMon.querySelectorAll('.srow')] : [];
  const srcChip = document.getElementById('srcChip');
  const SLOW_MS = 6000; // resolved ok past this latency -> tagged "slow", not plain "live"
  function setSource(name, state, lat, detail) {
    const row = srcRows.find((r) => r.dataset.src === name);
    if (!row) return;
    row.className = 'srow ' + state;
    if (detail) row.title = detail; else row.removeAttribute('title');
    const latEl = row.querySelector('.slat'), tagEl = row.querySelector('.stag');
    latEl.textContent = lat != null ? lat + ' ms'
      : state === 'block' ? 'blocked' : state === 'cache' ? 'cached'
      : state === 'verifying' ? '…' : '—';
    tagEl.textContent = state === 'live' ? 'live' : state === 'slow' ? 'slow'
      : state === 'block' ? 'blocked' : state === 'cache' ? 'cache'
      : state === 'zero' ? '0 fares' : state === 'verifying' ? 'verifying' : 'idle';
  }
  function resetSources() { srcRows.forEach((r) => setSource(r.dataset.src, 'idle')); }
  // Sources start "pending" and are painted with their real per-source status
  // when the INGEST frame arrives (VS.f9.applySources off the backend). A CSV
  // run does no scraping — every source reads from the extract.
  function runSources(blocked, imported) {
    if (imported) {
      srcRows.forEach((r, i) => setTimeout(() => setSource(r.dataset.src, 'cache'), 90 + i * 90));
      if (srcChip) srcChip.textContent = 'csv extract';
      return;
    }
    srcRows.forEach((r, i) => setTimeout(() => setSource(r.dataset.src, 'idle'), 60 + i * 70));
    if (srcChip) srcChip.textContent = 'connecting…';
  }

  /* ---------- degraded / error banner --------------------- */
  const banner = document.getElementById('degradedBanner');
  const bannerText = document.getElementById('degradedText');
  document.getElementById('degradedX').addEventListener('click', () => (banner.hidden = true));
  function degrade(kind, msg) {
    if (!banner) return;
    banner.hidden = false;
    banner.classList.toggle('err', kind === 'err');
    bannerText.textContent = msg;
    banner.style.animation = 'none'; void banner.offsetWidth; banner.style.animation = '';
  }
  function clearDegrade() { if (banner) banner.hidden = true; }

  /* ---------- map: click a corridor to select it ---------- */
  const canonKey = (n) => String(n || '').toUpperCase().split('-').filter(Boolean).sort().join('-');
  document.querySelectorAll('.map-body .arc').forEach((arc) => {
    arc.style.cursor = 'pointer';
    arc.addEventListener('click', () => {
      const sel = document.getElementById('corridor');
      const cur = VS.viz ? VS.viz.curCorridor : '';
      const c = arc.dataset.corridor;
      // if this arc is already the selected route, clicking flips its direction
      const next = (canonKey(cur) === c) ? c.split('-').reverse().join('-') : c;
      if (sel) { sel.value = next; sel.dispatchEvent(new Event('change', { bubbles: true })); }
    });
  });

  /* ---------- drawers ------------------------------------- */
  const scrim = document.getElementById('drawerScrim');
  const methodDrawer = document.getElementById('methodDrawer');
  function openDrawer(d) {
    d.classList.add('open'); d.setAttribute('aria-hidden', 'false');
    scrim.classList.add('open');
  }
  function closeDrawers() {
    methodDrawer.classList.remove('open'); methodDrawer.setAttribute('aria-hidden', 'true');
    scrim.classList.remove('open');
  }
  scrim.addEventListener('click', closeDrawers);
  document.getElementById('methodX').addEventListener('click', closeDrawers);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDrawers(); });

  const btnMethod = document.getElementById('btnMethod');
  const btnPrint = document.getElementById('btnPrint');
  btnMethod.addEventListener('click', () => { fillMethod(); openDrawer(methodDrawer); });
  function openReportPreview() {
    buildReport();
    document.body.classList.add('report-preview');
    window.scrollTo(0, 0);
  }
  function closeReportPreview() { document.body.classList.remove('report-preview'); }
  btnPrint.addEventListener('click', openReportPreview);
  const rpbPrint = document.getElementById('rpbPrint');
  const rpbClose = document.getElementById('rpbClose');
  if (rpbPrint) rpbPrint.addEventListener('click', () => window.print());
  if (rpbClose) rpbClose.addEventListener('click', closeReportPreview);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeReportPreview(); });
  // raw Cmd/Ctrl-P (without opening the preview) still gets a freshly composed report
  window.addEventListener('beforeprint', () => { if (lastRun) buildReport(); });

  /* ---------- CSV export — the audited fare set, previewed like the PDF ---------- */
  const btnCsv = document.getElementById('btnCsv');
  let csvPayload = '';
  let csvName = 'vayu-suchak.csv';

  // rebuild the same fare ledger the report uses: every fare + a flight label +
  // its fence status + z-score against the kept set. self-contained.
  function ledgerFor(r) {
    const iq = r.iqr || {};
    const kept = Array.isArray(iq.clean) ? [...iq.clean] : [];
    const excl = Array.isArray(iq.anomalies) ? [...iq.anomalies] : [];
    const all = kept.concat(excl);
    const st = stats(all) || stats([4700]);
    const stKept = stats(kept) || st;
    const meta = (VS.viz && VS.viz.importedRows) ? (VS.viz.importedRows() || null) : null;
    const AL = ['6E', 'AI', 'UK', 'SG', 'QP', 'IX'];
    const sortedAll = [...all].sort((a, c) => a - c);
    const metaSorted = (meta && meta.length === all.length) ? [...meta].sort((a, c) => a.price - c.price) : null;
    const flightLabel = (p, i) => {
      const mm = metaSorted && metaSorted[i];
      if (mm && (mm.airline || mm.flight)) {
        const al = (mm.airline || '').trim(), fl = (mm.flight || '').trim();
        if (fl && al && fl.toUpperCase().includes(al.toUpperCase())) return fl;
        return [al, fl].filter(Boolean).join(' ');
      }
      return `${AL[i % AL.length]}-${1000 + Math.floor(Math.abs(Math.sin(p * 1.7)) * 8000)}`;
    };
    const rows = sortedAll.map((p, i) => {
      const status = (p < r.lower) ? 'excluded·low' : (p > r.upper) ? 'excluded·high'
        : (p < st.p10 || p > st.p90) ? 'kept·tail' : 'kept';
      const z = stKept.sd ? (p - stKept.mean) / stKept.sd : 0;
      return {
        no: i + 1, flight: flightLabel(p, i), price: p, status, z, dMed: p - stKept.med,
        cls: status.startsWith('excluded') ? 'is-excl' : status === 'kept·tail' ? 'is-tail' : '',
      };
    });
    return { rows, st, stKept, kept, excl, all };
  }

  const csvCell = (v) => {
    const s = String(v == null ? '' : v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };

  function buildCsv() {
    const host = document.getElementById('csvSheet');
    if (!host) return;
    const r = lastRun;
    if (!r) { host.innerHTML = '<div class="cs-title">No completed audit yet</div><div class="cs-sub">Run an audit, then export.</div>'; csvPayload = ''; return; }
    const L = ledgerFor(r);
    const now = new Date().toLocaleString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false });
    const corr = r.corridor.toUpperCase();
    const festDelta = +(r.index - r.exf).toFixed(2);
    const b = fareBasis(r);
    const carrierOf = (label) => (label.match(/^[A-Za-z0-9]{2}/) || [''])[0];

    const head = ['row', 'route', 'airline', 'flight_id', 'fare_inr', 'fence_status', 'z_score', 'delta_median_inr'];
    const dataLines = L.rows.map((row) => [
      row.no, corr, carrierOf(row.flight), row.flight,
      Math.round(row.price), row.status, row.z.toFixed(3), Math.round(row.dMed),
    ].map(csvCell).join(','));

    const metaLines = [
      '',
      '# --- run metadata (ignored on re-import) ---',
      `# run_id,${r.runId}`,
      `# corridor,${corr}`,
      `# window,${r.start}..${r.end}`,
      `# k_factor,${r.k.toFixed(1)}`,
      `# index,${r.index.toFixed(2)}`,
      `# ex_festival,${r.exf.toFixed(2)}`,
      `# price_relative,${(r.priceRelative != null ? r.priceRelative : r.index).toFixed(2)}`,
      `# festival_component,${festDelta.toFixed(2)}`,
      `# Pt_median_kept_inr,${b.Pt != null ? Math.round(b.Pt) : ''}`,
      `# P0_base_inr,${Math.round(b.P0)}`,
      `# Q0_volume_wt,${b.Q0}`,
      `# fares_ingested,${L.st.n}`,
      `# fares_kept,${L.kept.length}`,
      `# fares_excluded,${L.excl.length}`,
      `# fence_lower_inr,${Math.round(r.lower)}`,
      `# fence_upper_inr,${Math.round(r.upper)}`,
      `# acquisition,${r.imported ? 'csv extract' : 'playwright scrape pool'}`,
      `# base_period,2022=100`,
      `# generated,${now} IST`,
      `# note,P0 = Kaggle 2022 median economy fare · Q0 = DGCA 2022 city-pair passenger volume · festival component from holidays.India ±7d.`,
    ];

    csvPayload = head.join(',') + '\n' + dataLines.join('\n') + '\n' + metaLines.join('\n') + '\n';
    csvName = `vayu-suchak_${corr}_${r.runId}.csv`.replace(/[^a-z0-9_.-]/gi, '');

    const cap = 200;
    const shown = L.rows.slice(0, cap);
    host.innerHTML = `
      <div class="cs-title">VAYU-SUCHAK — Audited Fare Set</div>
      <div class="cs-sub">CSV export · ${esc(corr.replace('-', '–'))} · run ${esc(r.runId)} · ${L.st.n} fares</div>
      <div class="cs-meta">
        <div><span>corridor</span> <b>${esc(corr.replace('-', '–'))}</b></div>
        <div><span>window</span> <b>${esc(r.start)} → ${esc(r.end)}</b></div>
        <div><span>k_factor</span> <b>${r.k.toFixed(1)}</b></div>
        <div><span>index</span> <b>${r.index.toFixed(2)}</b></div>
        <div><span>ex-festival</span> <b>${r.exf.toFixed(2)}</b></div>
        <div><span>fence</span> <b>${inr(r.lower)}–${inr(r.upper)}</b></div>
        <div><span>kept / excluded</span> <b>${L.kept.length} / ${L.excl.length}</b></div>
        <div><span>acquisition</span> <b>${r.imported ? 'CSV extract' : 'scrape pool'}</b></div>
        <div><span>base period</span> <b>2022 = 100</b></div>
      </div>
      <div class="cs-note">Every fare the index was computed from — the IQR-excluded ones included, flagged in <code>fence_status</code> rather than dropped from the file. Column headers match the importer, so this file re-imports into VAYU-SUCHAK cleanly; run metadata rides along as trailing <code>#</code> lines the importer skips.</div>
      <div class="cs-scroll"><table>
        <thead><tr><th>row</th><th>route</th><th>airline</th><th>flight_id</th><th class="num">fare_inr</th><th>fence_status</th><th class="num">z_score</th><th class="num">Δmedian</th></tr></thead>
        <tbody>${shown.map((row) => `<tr class="${row.cls}"><td>${row.no}</td><td>${esc(corr)}</td><td>${esc(carrierOf(row.flight))}</td><td>${esc(row.flight)}</td><td class="num">${Math.round(row.price).toLocaleString('en-IN')}</td><td>${esc(row.status)}</td><td class="num">${(row.z >= 0 ? '+' : '') + row.z.toFixed(2)}</td><td class="num">${(row.dMed >= 0 ? '+' : '') + Math.round(row.dMed).toLocaleString('en-IN')}</td></tr>`).join('')}</tbody>
      </table></div>
      ${L.rows.length > cap ? `<div class="cs-fname">preview shows first ${cap} of ${L.rows.length} rows — the file has all ${L.rows.length}</div>` : ''}
      <div class="cs-fname">file: ${esc(csvName)}</div>
    `;
  }

  function openCsvPreview() { buildCsv(); document.body.classList.add('csv-preview'); window.scrollTo(0, 0); }
  function closeCsvPreview() { document.body.classList.remove('csv-preview'); }
  if (btnCsv) btnCsv.addEventListener('click', openCsvPreview);
  const cpbDownload = document.getElementById('cpbDownload');
  const cpbCopy = document.getElementById('cpbCopy');
  const cpbClose = document.getElementById('cpbClose');
  if (cpbClose) cpbClose.addEventListener('click', closeCsvPreview);
  if (cpbDownload) cpbDownload.addEventListener('click', () => {
    if (!csvPayload) return;
    try {
      const blob = new Blob([csvPayload], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = csvName;
      document.body.appendChild(a); a.click();
      setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 600);
      if (VS.toast) VS.toast('ok', 'CSV exported', csvName);
    } catch (e) { if (VS.toast) VS.toast('err', 'Export failed', String((e && e.message) || e)); }
  });
  if (cpbCopy) cpbCopy.addEventListener('click', () => {
    if (!csvPayload) return;
    const done = () => { if (VS.toast) VS.toast('ok', 'CSV copied to clipboard', csvName); };
    const fail = () => { if (VS.toast) VS.toast('warn', 'Clipboard blocked', 'use download instead'); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(csvPayload).then(done, fail);
    else fail();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeCsvPreview(); });

  let lastRun = null;
  function fareBasis(r) {
    // all of these come straight from the audit result the backend
    // returned — the same numbers the index was computed from.
    const kept = r.iqr ? r.iqr.clean.length : 0;
    return {
      Pt: (r.Pt != null) ? r.Pt : null,
      P0: r.P0 || (VS.viz && VS.viz.baseRef ? VS.viz.baseRef(r.corridor).P0 : 4700),
      Q0: r.Q0 || (VS.viz && VS.viz.baseRef ? VS.viz.baseRef(r.corridor).Q0 : 50),
      rel: (r.priceRelative != null) ? r.priceRelative : null,
      n: r.nFares, kept,
    };
  }
  function fillMethod() {
    const mv = document.getElementById('methodVals');
    const mi = document.getElementById('methodIqr');
    const fb = document.getElementById('methodFareBasis');
    if (!lastRun) { mv.innerHTML = '<div class="kv"><span>status</span><b>no run yet</b></div>'; fb.innerHTML = '<div class="kv"><span>status</span><b>no run yet</b></div>'; return; }
    const r = lastRun;
    mv.innerHTML = `
      <div class="kv"><span>run id</span><b>${r.runId}</b></div>
      <div class="kv"><span>corridor</span><b>${r.corridor.replace('-', '–')}</b></div>
      <div class="kv"><span>window</span><b>${r.start} → ${r.end}</b></div>
      <div class="kv"><span>Σ(Pt·Q0) / Σ(P0·Q0) ×100</span><b>${(r.priceRelative != null ? r.priceRelative : r.index).toFixed(2)}</b></div>
      <div class="kv"><span>+ festival component</span><b>${(r.fest || 0).toFixed(2)}</b></div>
      <div class="kv"><span>index</span><b>${r.index.toFixed(2)}</b></div>
      <div class="kv"><span>ex-festival</span><b>${r.exf.toFixed(2)}</b></div>
      <div class="kv"><span>k_factor</span><b>${r.k.toFixed(1)}</b></div>
      <div class="kv"><span>fares excluded</span><b>${r.excl}</b></div>`;
    const b = fareBasis(r);
    fb.innerHTML = `
      <div class="kv"><span>fares ingested (n)</span><b>${b.n ?? '—'}</b></div>
      <div class="kv"><span>within IQR fence</span><b>${b.kept}</b></div>
      <div class="kv"><span>Pt · median kept fare</span><b>${b.Pt != null ? '₹' + Math.round(b.Pt).toLocaleString('en-IN') : '—'}</b></div>
      <div class="kv"><span>P0 · base-year price</span><b>₹${b.P0.toLocaleString('en-IN')}</b></div>
      <div class="kv"><span>Q0 · base-year volume wt</span><b>${b.Q0}</b></div>
      <div class="kv"><span>Pt / P0 ×100</span><b>${b.rel != null ? b.rel.toFixed(2) : '—'}</b></div>
      <div class="kv"><span>festival fares flagged</span><b>${r.festFlags ?? '—'}</b></div>`;
    mi.innerHTML = `At k=<span class="v">${r.k.toFixed(1)}</span> the fence is <b>₹${Math.round(r.lower).toLocaleString('en-IN')} – ₹${Math.round(r.upper).toLocaleString('en-IN')}</b>; ${r.excl} fare(s) fell outside and were dropped before the median. The filter runs on Execute, not on slider move.`;
  }

  /* ---------- run replay scrubber ------------------------- */
  const scrubber = document.getElementById('scrubber');
  const scrubRange = document.getElementById('scrubRange');
  const scrubBadge = document.getElementById('scrubBadge');
  const snapshots = [];
  const flapCells = document.querySelectorAll('#indexFlap .flap-cell');
  const digitsOf = (v) => Math.max(0, v).toFixed(2).replace('.', '').padStart(5, '0').slice(-5).split('');
  function pushSnapshot(snap) {
    snapshots.push(snap);
    btnPrint.hidden = false;
    if (btnCsv) btnCsv.hidden = false;
    if (snapshots.length > 1) {
      scrubber.hidden = false;
      scrubRange.max = snapshots.length - 1;
      scrubRange.value = snapshots.length - 1;
      updateScrubBadge();
    }
  }
  function updateScrubBadge() {
    const i = +scrubRange.value;
    scrubBadge.textContent = `run ${i + 1}/${snapshots.length}`;
  }
  scrubRange.addEventListener('input', () => {
    const s = snapshots[+scrubRange.value];
    if (!s) return;
    updateScrubBadge();
    digitsOf(s.index).forEach((d, i) => { if (flapCells[i]) flapCells[i].textContent = d; });
    // keep F4's split-flap animation origin aligned with what's on screen
    if (VS.syncIndex) VS.syncIndex(s.index);
    const ex = document.getElementById('exfestVal'); if (ex) ex.textContent = s.exf.toFixed(2);
    const ml = document.getElementById('metaLine'); if (ml) ml.textContent = `run ${+scrubRange.value + 1} · ${s.corridor.replace('-', '–')} · index ${s.index.toFixed(2)}`;
  });

  /* ---------- expose hooks for F4 ------------------------- */
  VS.f9 = {
    _history: [],
    onRunStart(corridor, blocked) {
      clearDegrade();
      resetSources();
      const imported = !!(VS.viz && VS.viz.isImported && VS.viz.isImported());
      runSources(blocked, imported);
    },
    onIqr(sim) {},
    onComplete(run) {
      lastRun = run;
      VS.f9._history.push({ idx: run.index, exf: run.exf, corr: run.corridor });
      pushSnapshot({ index: run.index, exf: run.exf, corridor: run.corridor, lower: run.lower, upper: run.upper });
    },
    // Cleartrip (and sometimes Akasa) can run well behind the httpx-direct
    // sources — instead of every row sitting on "idle" and looking stuck,
    // flip whatever hasn't reported yet to "verifying" the moment the first
    // per-source SOURCE event of this run arrives.
    markVerifying() {
      srcRows.forEach((r) => { if (/(?:^| )idle(?: |$)/.test(r.className)) setSource(r.dataset.src, 'verifying'); });
    },
    // one adapter just resolved (live SOURCE event, ahead of the aggregate
    // INGEST frame) — paint its row immediately. status = SourceStatus dict.
    applySourceOne(name, status) {
      if (!name || name === 'ixigo') return;
      const NAME = { googleflights: 'gflights' };
      const MAP = { ok: 'live', degraded: 'zero', blocked: 'block', error: 'block',
                    unavailable: 'block', pending: 'idle' };
      const key = NAME[name] || name;
      const lat = status && status.latency_ms;
      let state = MAP[status && status.status] || 'idle';
      if (state === 'live' && lat && lat > SLOW_MS) state = 'slow'; // resolved ok, just took a while
      setSource(key, state, lat ? Math.round(lat) : null, status && status.detail);
    },
    applySources(sources, ingestionSource) {
      const NAME = { googleflights: 'gflights' };
      const MAP = { ok: 'live', degraded: 'zero', blocked: 'block', error: 'block',
                    unavailable: 'block', pending: 'idle' };
      const entries = sources && typeof sources === 'object' ? Object.entries(sources) : [];
      if (!entries.length) {
        // ?mode=cache run — no live pool was opened; every source read from
        // this morning's cached snapshot
        srcRows.forEach((r) => setSource(r.dataset.src, 'cache', null, 'cache mode — read from today’s 06:00 collected snapshot'));
        if (srcChip) srcChip.textContent = 'cache snapshot';
        return;
      }
      let live = 0, blocked = 0;
      entries.forEach(([name, s]) => {
        if (name === 'ixigo') return; // not shown in the panel — don't count it either
        const key = NAME[name] || name;
        let state = MAP[s && s.status] || 'idle';
        const lat = s && s.latency_ms;
        if (state === 'live' && lat && lat > SLOW_MS) state = 'slow'; // resolved ok, just took a while
        if (state === 'live' || state === 'slow') live++;
        if (state === 'block') blocked++;
        setSource(key, state, lat ? Math.round(lat) : null, s && s.detail);
      });
      // sources the pool didn't report (e.g. skipped) → mark cache, not idle
      srcRows.forEach((r) => { if (/idle/.test(r.className)) setSource(r.dataset.src, 'cache'); });
      if (srcChip) srcChip.textContent = `${live} live · ${blocked} blocked`;
    },
    degrade,
  };

  /* ============================================================
     TOAST — lightweight status feedback that shows in every view
     (dormant, live, preview). Used by the CSV importer below.
     ============================================================ */
  function toast(kind, title, detail, ms) {
    const wrap = document.getElementById('toastWrap');
    if (!wrap) { console[kind === 'err' ? 'error' : 'log'](title, detail || ''); return; }
    const ico = kind === 'ok' ? '✓' : kind === 'warn' ? '▲' : kind === 'err' ? '✕' : 'ℹ';
    const el = document.createElement('div');
    el.className = 'toast ' + kind;
    el.innerHTML = `<span class="ti-ico">${ico}</span><span class="ti-body"><b>${title}</b>${detail ? `<br><span class="dim">${detail}</span>` : ''}</span>`;
    wrap.appendChild(el);
    const kill = () => { el.classList.add('out'); setTimeout(() => el.remove(), 320); };
    setTimeout(kill, ms || 5200);
    el.addEventListener('click', kill);
  }
  VS.toast = toast;

  /* ============================================================
     IMPORT CSV — load a pre-scraped fare extract for the selected
     route in place of a live scrape. Tolerant of real-world exports:
       • header row, columns in ANY order
       • delimiter auto-detected: comma / semicolon / tab / pipe
       • UTF-8 BOM stripped; quoted fields; ₹ and thousands separators
       • price column matched on price|fare|amount|inr|cost|rate|total
       • optional route/sector column → rows filtered to the selected
         corridor; optional airline + flight columns kept for the report
     ============================================================ */
  (function initImport() {
    const btn = document.getElementById('btnImport');
    const input = document.getElementById('csvInput');
    const badge = document.getElementById('srcBadge');
    if (!btn || !input) return;
    btn.addEventListener('click', () => input.click());

    const MIN_FARES_UI = 5;    // hard floor — IQR quartiles need a handful of points
    const SOFT_FARES   = 12;   // below this the index is noisy; import still proceeds with a warning
    const setHelper = (msg) => { const h = document.querySelector('.execute-wrap .helper'); if (h) h.textContent = msg; };

    function detectDelim(line) {
      const cand = [',', ';', '\t', '|'];
      let best = ',', bestN = 0;
      for (const d of cand) {
        const n = line.split(d).length - 1;
        if (n > bestN) { bestN = n; best = d; }
      }
      return best;
    }
    function splitLine(l, d) {
      const out = []; let cur = '', q = false;
      for (let i = 0; i < l.length; i++) {
        const c = l[i];
        if (c === '"') { if (q && l[i + 1] === '"') { cur += '"'; i++; } else q = !q; }
        else if (c === d && !q) { out.push(cur); cur = ''; }
        else cur += c;
      }
      out.push(cur); return out;
    }
    // "₹4,820.00" → 4820 ; "4 820" → 4820 ; "4.820,50" (EU) → 4820.5
    function toNum(raw) {
      let s = String(raw).trim().replace(/[^0-9.,-]/g, '');
      if (s.indexOf(',') > -1 && s.indexOf('.') > -1) {
        s = (s.lastIndexOf(',') > s.lastIndexOf('.'))
          ? s.replace(/\./g, '').replace(',', '.')   // EU: 1.234,56
          : s.replace(/,/g, '');                     // IN/US: 1,234.56
      } else if (s.indexOf(',') > -1) {
        s = (/,\d{2}$/.test(s) && !/,\d{3}$/.test(s)) ? s.replace(',', '.') : s.replace(/,/g, '');
      }
      return parseFloat(s);
    }

    function parseCSV(text) {
      text = String(text).replace(/^﻿/, '').replace(/\r\n?/g, '\n');
      const rows = text.split('\n').filter((l) => l.trim().length);
      if (rows.length < 2) return { rows: [], err: 'file has no data rows' };
      const d = detectDelim(rows[0]);
      const head = splitLine(rows[0], d).map((h) => h.trim().toLowerCase().replace(/^﻿/, ''));
      const pi = head.findIndex((h) => /price|fare|amount|(^|_)inr$|(^|_)rs$|cost|rate|total/.test(h));
      const ri = head.findIndex((h) => /^(route|corridor|sector|od|o-d|origin-destination|pair)$/.test(h));
      const ai = head.findIndex((h) => /^(airline|carrier|operator|al)$/.test(h));
      const fi = head.findIndex((h) => /^(flight|flight_id|flight_no|flightnumber|flight_number|fno)$/.test(h));
      if (pi < 0) return { rows: [], err: `no price column found — headers were: ${head.join(', ') || '(none)'}` };
      const out = [];
      for (const line of rows.slice(1)) {
        const f = splitLine(line, d);
        const price = toNum(f[pi]);
        if (!isFinite(price) || price <= 0) continue;
        out.push({
          price,
          route: ri >= 0 ? String(f[ri] || '').trim().toUpperCase().replace(/[^A-Z0-9]+/g, '-').replace(/^-+|-+$/g, '') : null,
          airline: ai >= 0 ? String(f[ai] || '').trim() : null,
          flight: fi >= 0 ? String(f[fi] || '').trim() : null,
        });
      }
      return { rows: out, delim: d === '\t' ? 'tab' : d, headers: head, skipped: (rows.length - 1) - out.length };
    }

    input.addEventListener('change', () => {
      const file = input.files && input.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onerror = () => { toast('err', 'CSV read failed', file.name); input.value = ''; };
      reader.onload = () => {
        let parsed;
        try { parsed = parseCSV(reader.result || ''); }
        catch (e) { toast('err', 'CSV parse error', String(e && e.message || e)); input.value = ''; return; }
        const all = parsed.rows;
        if (!all.length) {
          toast('err', 'CSV import failed', parsed.err || 'no usable fare values in the price column');
          setHelper('CSV import failed — ' + (parsed.err || 'check the price column') + '.');
          input.value = ''; return;
        }
        const st = VS.getState ? VS.getState() : null;
        const want = st ? st.corridor : null;
        const norm = (s) => (s || '').split('-').filter(Boolean).sort().join('-');
        const haveRoutes = all.some((x) => x.route);
        const matched = (haveRoutes && want) ? all.filter((x) => norm(x.route) === norm(want)) : all;
        const routeFiltered = haveRoutes && want && matched.length >= MIN_FARES_UI;
        const use = routeFiltered ? matched : all;
        const prices = use.map((x) => x.price);

        if (prices.length < MIN_FARES_UI) {
          const why = (haveRoutes && want && matched.length < MIN_FARES_UI)
            ? `only ${matched.length} row(s) match ${want.replace('-', '–')} (file has ${all.length}) — check the route column or switch corridor`
            : `only ${prices.length} usable fare(s) — need ≥ ${MIN_FARES_UI}`;
          toast('err', 'CSV import failed', why);
          setHelper('CSV: ' + why + '.');
          input.value = ''; return;
        }

        if (VS.viz && VS.viz.setImportedFares) VS.viz.setImportedFares(prices, use);
        if (badge) { badge.querySelector('.bdot').className = 'bdot csv'; badge.querySelector('.src-txt').textContent = `imported csv (${prices.length})`; }

        const srt = [...prices].sort((a, c) => a - c);
        const med = srt.length % 2 ? srt[(srt.length - 1) / 2] : (srt[srt.length / 2 - 1] + srt[srt.length / 2]) / 2;
        const rng = `₹${Math.round(srt[0]).toLocaleString('en-IN')}–₹${Math.round(srt[srt.length - 1]).toLocaleString('en-IN')}`;
        const bits = [
          `${prices.length} fares`,
          routeFiltered ? `for ${want.replace('-', '–')}` : (haveRoutes ? 'all routes (no corridor match)' : 'route column absent'),
          `median ₹${Math.round(med).toLocaleString('en-IN')} · ${rng}`,
          `delim "${parsed.delim}"`,
        ];
        if (parsed.skipped) bits.push(`${parsed.skipped} row(s) skipped`);
        if (prices.length < SOFT_FARES) {
          toast('warn', `Imported ${prices.length} fares — small sample`, bits.join(' · ') + ` · index will be noisy below ${SOFT_FARES} fares`, 8000);
        } else {
          toast('ok', `Imported ${prices.length} fares — press Execute`, bits.join(' · '), 7000);
        }
        setHelper(`Imported ${prices.length} fares${routeFiltered ? ' for ' + want.replace('-', '–') : ''} — press Execute to audit.`);
        btn.textContent = `⬍ csv loaded (${prices.length})`;
        if (VS.appendLine && document.getElementById('app').classList.contains('is-live')) {
          VS.appendLine('INGEST', `csv re-import · ${prices.length} fares · median ₹${Math.round(med).toLocaleString('en-IN')} · ${rng} — press Execute to recompute`);
        }
        input.value = '';
      };
      reader.readAsText(file);
    });
  })();

  /* ============================================================
     INSIGHT REPORT — every chart below is generated from THIS run's
     own numbers (fare set, IQR fences, index components, session
     history). Nothing is a screenshot of the dashboard. Toggled on
     screen by ⎙; the only thing that prints.
     ============================================================ */
  const RC = {   // print-safe palette
    ink:'#222', sub:'#666', grid:'#d0d0d0', axis:'#888',
    kept:'#2f6f3e', tail:'#b9852b', excl:'#c0392b',
    base:'#555', fest:'#7a4fb5', idx:'#1f6f3e',
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
  const inr  = (n) => '₹' + Math.round(n).toLocaleString('en-IN');
  const inrK = (n) => n >= 1000 ? '₹' + (n / 1000).toFixed(n < 10000 ? 1 : 0) + 'k' : '₹' + Math.round(n);
  function stats(arr) {
    const s = [...arr].sort((a, b) => a - b), n = s.length;
    if (!n) return null;
    const q = (p) => { const i = p * (n - 1), lo = Math.floor(i), hi = Math.ceil(i); return s[lo] + (s[hi] - s[lo]) * (i - lo); };
    const mean = s.reduce((a, b) => a + b, 0) / n;
    const sd = Math.sqrt(s.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, n - 1));
    const med = n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
    return { n, min: s[0], max: s[n - 1], q1: q(0.25), q3: q(0.75), p10: q(0.10), p90: q(0.90), med, mean, sd, cv: mean ? sd / mean * 100 : 0, sorted: s };
  }
  // tiny SVG builders
  const T = (x, y, txt, o = {}) =>
    `<text x="${x}" y="${y}" font-family="'JetBrains Mono',ui-monospace,monospace" font-size="${o.s || 10}" fill="${o.fill || RC.ink}" text-anchor="${o.a || 'start'}"${o.w ? ` font-weight="${o.w}"` : ''}${o.rot ? ` transform="rotate(${o.rot} ${x} ${y})"` : ''}>${esc(txt)}</text>`;
  const L = (x1, y1, x2, y2, o = {}) =>
    `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${o.stroke || RC.grid}" stroke-width="${o.sw || 1}"${o.dash ? ` stroke-dasharray="${o.dash}"` : ''}/>`;
  const svg = (w, h, inner) =>
    `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" font-family="'JetBrains Mono',ui-monospace,monospace">${inner}</svg>`;

  // focus a domain on the bulk of the data (fences + kept spread), so a lone
  // extreme outlier can't squash every other bar into one column.
  function focusDomain(stKept, r) {
    const pad = Math.max((stKept.q3 - stKept.q1) * 0.6, (stKept.max - stKept.min) * 0.12, 200);
    const lo = Math.min(r.lower, stKept.min) - pad;
    const hi = Math.max(r.upper, stKept.max) + pad;
    return { lo: Math.max(0, lo), hi, span: (hi - Math.max(0, lo)) || 1 };
  }

  /* ---- Chart A: fare distribution histogram, fully annotated ---- */
  function chartHistogram(all, st, stKept, r) {
    const W = 660, H = 258, ml = 34, mr = 14, mt = 40, mb = 46;
    const pw = W - ml - mr, ph = H - mt - mb;
    const { lo, hi, span } = focusDomain(stKept, r);
    const nb = Math.max(6, Math.min(16, Math.round(Math.sqrt(st.n)) + 4));
    const bw = span / nb;
    const bins = new Array(nb).fill(0);
    let clampedLo = 0, clampedHi = 0;
    all.forEach((p) => {
      let i = Math.floor((p - lo) / span * nb);
      if (i < 0) { i = 0; clampedLo++; }
      if (i >= nb) { i = nb - 1; clampedHi++; }
      bins[i]++;
    });
    const maxC = Math.max(...bins, 1);
    const X = (v) => ml + (Math.max(lo, Math.min(hi, v)) - lo) / span * pw;
    const Yc = (c) => mt + ph - c / maxC * ph;
    let g = '';
    for (let c = 0; c <= maxC; c += Math.ceil(maxC / 4) || 1) {
      g += L(ml, Yc(c), W - mr, Yc(c), { stroke: RC.grid });
      g += T(ml - 5, Yc(c) + 3, String(c), { a: 'end', s: 8, fill: RC.sub });
    }
    bins.forEach((c, i) => {
      const x0 = ml + (i / nb) * pw + 1, x1 = ml + ((i + 1) / nb) * pw - 1;
      const mid = lo + (i + 0.5) * bw;
      const edge = (i === 0 && clampedLo) || (i === nb - 1 && clampedHi);
      const col = (mid < r.lower || mid > r.upper || edge) ? RC.excl : (mid < st.p10 || mid > st.p90) ? RC.tail : RC.kept;
      if (c > 0) {
        g += `<rect x="${x0.toFixed(1)}" y="${Yc(c).toFixed(1)}" width="${(x1 - x0).toFixed(1)}" height="${(mt + ph - Yc(c)).toFixed(1)}" fill="${col}" fill-opacity="0.55" stroke="${col}" stroke-width="0.8"/>`;
        g += T((x0 + x1) / 2, Yc(c) - 3, String(c), { a: 'middle', s: 8, fill: RC.ink, w: 700 });
      }
    });
    if (clampedLo) g += T(ml + 2, mt + 10, `◄ ${clampedLo} below ${inrK(lo)}`, { s: 7, fill: RC.excl });
    if (clampedHi) g += T(W - mr - 2, mt + 10, `${clampedHi} above ${inrK(hi)} ►`, { a: 'end', s: 7, fill: RC.excl });
    // marker lines, labels staggered across three rows so they never overlap
    const marks = [
      [r.lower, 'lower ' + inrK(r.lower), RC.excl],
      [st.q1, 'Q1 ' + inrK(st.q1), RC.base],
      [st.med, 'Pt ' + inrK(st.med), RC.idx],
      [st.q3, 'Q3 ' + inrK(st.q3), RC.base],
      [r.upper, 'upper ' + inrK(r.upper), RC.excl],
    ];
    marks.forEach(([v, label, col], i) => {
      if (v < lo || v > hi) return;
      const yTop = mt - 6 - (i % 2) * 12;
      g += L(X(v), yTop + 2, X(v), mt + ph, { stroke: col, sw: 1.1, dash: '3 2' });
      g += T(X(v), yTop, label, { a: 'middle', s: 8, fill: col, w: 700 });
    });
    g += L(ml, mt + ph, W - mr, mt + ph, { stroke: RC.axis, sw: 1 });
    for (let t = 0; t <= 5; t++) g += T(ml + pw * t / 5, mt + ph + 14, inrK(lo + span * t / 5), { a: 'middle', s: 8, fill: RC.sub });
    g += T(ml, H - 6, 'fare (₹) →', { s: 8, fill: RC.sub });
    g += T(ml - 28, mt - 22, 'fares', { s: 8, fill: RC.sub });
    return svg(W, H, g);
  }

  /* ---- Chart B: horizontal box-and-whisker with every value ---- */
  function chartBox(all, st, stKept, r) {
    const W = 660, H = 176, ml = 16, mr = 16, mt = 52, mb = 46;
    const pw = W - ml - mr;
    const { lo, hi, span } = focusDomain(stKept, r);
    const X = (v) => ml + (Math.max(lo, Math.min(hi, v)) - lo) / span * pw;
    const cy = mt + 6;
    let g = '';
    g += L(ml, cy, W - mr, cy, { stroke: RC.grid });
    // whisker: lower fence .. upper fence
    g += L(X(r.lower), cy, X(r.upper), cy, { stroke: RC.axis, sw: 1.4 });
    g += L(X(r.lower), cy - 9, X(r.lower), cy + 9, { stroke: RC.excl, sw: 1.6 });
    g += L(X(r.upper), cy - 9, X(r.upper), cy + 9, { stroke: RC.excl, sw: 1.6 });
    // box Q1..Q3 + median
    g += `<rect x="${X(st.q1).toFixed(1)}" y="${cy - 15}" width="${Math.max(1, X(st.q3) - X(st.q1)).toFixed(1)}" height="30" fill="${RC.kept}" fill-opacity="0.16" stroke="${RC.kept}" stroke-width="1.2"/>`;
    g += L(X(st.med), cy - 15, X(st.med), cy + 15, { stroke: RC.idx, sw: 2 });
    // excluded points (clamped into view) with ₹ labels
    all.filter((p) => p < r.lower || p > r.upper).sort((a, c) => a - c).forEach((p, i) => {
      const x = X(p);
      g += `<circle cx="${x.toFixed(1)}" cy="${cy + 26}" r="3" fill="${RC.excl}"/>`;
      g += T(x, cy + 26 + (i % 2 ? 13 : -8), inr(p), { a: 'middle', s: 7, fill: RC.excl, w: 700 });
    });
    // value labels: lower/median/upper above the line, Q1 & Q3 stacked higher and side-anchored
    g += T(X(r.lower), cy - 20, 'lower ' + inr(r.lower), { a: 'middle', s: 8, fill: RC.excl, w: 700 });
    g += T(X(r.upper), cy - 20, 'upper ' + inr(r.upper), { a: 'middle', s: 8, fill: RC.excl, w: 700 });
    g += T(X(st.med), cy - 34, 'median ' + inr(st.med), { a: 'middle', s: 8, fill: RC.idx, w: 700 });
    g += T(X(st.q1) - 3, cy - 34, 'Q1 ' + inr(st.q1), { a: 'end', s: 8, fill: RC.base, w: 700 });
    g += T(X(st.q3) + 3, cy - 34, 'Q3 ' + inr(st.q3), { a: 'start', s: 8, fill: RC.base, w: 700 });
    g += T(ml, H - 10, `k = ${r.k.toFixed(1)}  ·  IQR = Q3 − Q1 = ${inr(st.q3 - st.q1)}  ·  fence = [Q1 − k·IQR , Q3 + k·IQR] = [${inr(r.lower)} , ${inr(r.upper)}]  ·  ${r.excl} excluded`, { s: 8, fill: RC.sub });
    return svg(W, H, g);
  }

  /* ---- Chart C: index-composition waterfall, labelled ---- */
  function chartWaterfall(r) {
    const W = 660, H = 250, ml = 40, mr = 16, mt = 22, mb = 40;
    const pw = W - ml - mr, ph = H - mt - mb;
    const steps = [
      { name: 'base 2022', from: 0, to: 100, col: RC.base, abs: true },
      { name: 'price relative', from: 100, to: r.priceRelative, col: r.priceRelative >= 100 ? RC.excl : RC.kept },
      { name: '+ festival', from: r.priceRelative, to: r.index, col: RC.fest },
      { name: 'INDEX', from: 0, to: r.index, col: RC.idx, abs: true },
    ];
    const vals = steps.flatMap((s) => [s.from, s.to]).concat([100]);
    const lo = Math.max(0, Math.min(...vals) - 3), hi = Math.max(...vals) + 5;
    const span = (hi - lo) || 1;
    const Y = (v) => mt + ph - (v - lo) / span * ph;
    const slot = pw / steps.length, bw = slot * 0.5;
    let g = '';
    for (let t = 0; t <= 4; t++) {
      const v = lo + span * t / 4;
      g += L(ml, Y(v), W - mr, Y(v), { stroke: RC.grid });
      g += T(ml - 6, Y(v) + 3, v.toFixed(0), { a: 'end', s: 8, fill: RC.sub });
    }
    g += L(ml, Y(100), W - mr, Y(100), { stroke: RC.base, sw: 1, dash: '4 3' });
    g += T(ml + 2, Y(100) - 4, 'base = 100', { a: 'start', s: 8, fill: RC.base, w: 700 });
    steps.forEach((s, i) => {
      const x = ml + slot * i + (slot - bw) / 2;
      const y0 = Y(Math.max(s.from, s.to)), y1 = Y(Math.min(s.from, s.to));
      g += `<rect x="${x.toFixed(1)}" y="${y0.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1.5, y1 - y0).toFixed(1)}" fill="${s.col}" fill-opacity="${s.abs ? 0.75 : 0.5}" stroke="${s.col}" stroke-width="1"/>`;
      g += T(x + bw / 2, y0 - 5, s.to.toFixed(2), { a: 'middle', s: 9, fill: RC.ink, w: 700 });
      if (!s.abs) {
        const d = s.to - s.from;
        g += T(x + bw / 2, y1 + 12, (d >= 0 ? '+' : '') + d.toFixed(2), { a: 'middle', s: 8, fill: s.col, w: 700 });
      }
      g += T(x + bw / 2, H - 22, s.name, { a: 'middle', s: 8, fill: RC.sub });
      if (i < steps.length - 1 && !steps[i + 1].abs) g += L(x + bw, Y(s.to), x + slot, Y(s.to), { stroke: RC.axis, dash: '2 2' });
    });
    g += T(ml, H - 6, 'index points', { s: 8, fill: RC.sub });
    return svg(W, H, g);
  }

  /* ---- Chart D: every fare, sorted low→high, on a ₹ scale ---- */
  function chartStrip(all, st, stKept, r) {
    const W = 660, H = 230, ml = 42, mr = 92, mt = 16, mb = 34;
    const pw = W - ml - mr, ph = H - mt - mb;
    const s = [...all].sort((a, b) => a - b);
    const { lo, hi, span } = focusDomain(stKept, r);
    const X = (i) => ml + (s.length === 1 ? pw / 2 : i / (s.length - 1) * pw);
    const Y = (v) => mt + ph - (Math.max(lo, Math.min(hi, v)) - lo) / span * ph;
    let g = '';
    for (let t = 0; t <= 4; t++) {
      const v = lo + span * t / 4;
      g += L(ml, Y(v), W - mr, Y(v), { stroke: RC.grid });
      g += T(ml - 6, Y(v) + 3, inrK(v), { a: 'end', s: 8, fill: RC.sub });
    }
    const hl = (v, name, col) => L(ml, Y(v), W - mr, Y(v), { stroke: col, sw: 1, dash: '4 3' }) + T(W - mr + 4, Y(v) + 3, name + ' ' + inr(v), { a: 'start', s: 8, fill: col, w: 700 });
    g += hl(r.lower, 'lower', RC.excl);
    g += hl(st.med, 'median', RC.idx);
    g += hl(r.upper, 'upper', RC.excl);
    s.forEach((p, i) => {
      const clamped = p < lo || p > hi;
      const col = (p < r.lower || p > r.upper) ? RC.excl : (p < st.p10 || p > st.p90) ? RC.tail : RC.kept;
      g += L(X(i), mt + ph, X(i), Y(p), { stroke: col, sw: 1 });
      g += `<circle cx="${X(i).toFixed(1)}" cy="${Y(p).toFixed(1)}" r="${clamped ? 3.4 : 2.6}" fill="${clamped ? '#fff' : col}" stroke="${col}" stroke-width="1.2"/>`;
      if (col === RC.excl) {
        const dy = clamped ? (p > hi ? 12 : -8) : (p > r.upper ? -7 : 13);
        g += T(X(i), Y(p) + dy, inr(p), { a: 'middle', s: 7, fill: RC.excl, w: 700 });
      }
    });
    g += L(ml, mt + ph, W - mr, mt + ph, { stroke: RC.axis });
    g += T(ml, H - 8, `fares sorted low → high  (n = ${s.length})  ·  hollow marker = value beyond axis, clamped`, { s: 8, fill: RC.sub });
    return svg(W, H, g);
  }

  /* ---- Chart E: session index history, each point labelled ---- */
  function chartHistory(hist) {
    const W = 660, H = 210, ml = 40, mr = 60, mt = 20, mb = 34;
    const pw = W - ml - mr, ph = H - mt - mb;
    const idx = hist.map((h) => h.idx);
    const vals = idx.concat([100]);
    const lo = Math.min(...vals) - 2, hi = Math.max(...vals) + 2;
    const span = (hi - lo) || 1;
    const X = (i) => ml + (hist.length === 1 ? pw / 2 : i / (hist.length - 1) * pw);
    const Y = (v) => mt + ph - (v - lo) / span * ph;
    let g = '';
    for (let t = 0; t <= 4; t++) {
      const v = lo + span * t / 4;
      g += L(ml, Y(v), W - mr, Y(v), { stroke: RC.grid });
      g += T(ml - 6, Y(v) + 3, v.toFixed(1), { a: 'end', s: 8, fill: RC.sub });
    }
    if (100 >= lo && 100 <= hi) { g += L(ml, Y(100), W - mr, Y(100), { stroke: RC.base, sw: 1, dash: '4 3' }); g += T(W - mr + 4, Y(100) + 3, 'base 100', { s: 8, fill: RC.base }); }
    // each corridor's index is scaled to its own base fare, not one shared
    // national number, so the line only connects consecutive runs of the SAME
    // corridor — a corridor switch breaks it rather than reading as a real move.
    const segs = [];
    hist.forEach((h, i) => {
      if (i > 0 && h.corr === hist[i - 1].corr) segs[segs.length - 1].push(i);
      else segs.push([i]);
    });
    segs.filter((s) => s.length > 1).forEach((s) => {
      g += `<polyline points="${s.map((i) => X(i).toFixed(1) + ',' + Y(hist[i].idx).toFixed(1)).join(' ')}" fill="none" stroke="${RC.idx}" stroke-width="1.8"/>`;
    });
    hist.forEach((h, i) => {
      g += `<circle cx="${X(i).toFixed(1)}" cy="${Y(h.idx).toFixed(1)}" r="3" fill="${RC.idx}"/>`;
      g += T(X(i), Y(h.idx) - 7, h.idx.toFixed(2), { a: 'middle', s: 8, fill: RC.idx, w: 700 });
      g += T(X(i), mt + ph + 13, 'run ' + (i + 1), { a: 'middle', s: 7, fill: RC.sub });
      g += T(X(i), mt + ph + 23, (h.corr || '').replace('-', '–'), { a: 'middle', s: 7, fill: RC.sub });
    });
    g += L(ml, mt + ph, W - mr, mt + ph, { stroke: RC.axis });
    return svg(W, H, g);
  }

  function buildReport() {
    const host = document.getElementById('reportSheet');
    if (!host) return;
    const r = lastRun;
    if (!r) {
      host.innerHTML = '<div class="r-cover"><div class="r-title">VAYU-SUCHAK — Airfare Price Index Report</div><div class="r-sub">No completed audit yet. Press Execute to run an audit, then open the report.</div></div>';
      return;
    }
    const b = fareBasis(r);
    const now = new Date().toLocaleString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false });
    const festDelta = +(r.index - r.exf).toFixed(2);
    const iq = r.iqr || {};
    const kept = Array.isArray(iq.clean) ? [...iq.clean] : [];
    const excl = Array.isArray(iq.anomalies) ? [...iq.anomalies] : [];
    const all = kept.concat(excl);
    const st = stats(all) || stats([b.P0 || 4700]);
    const stKept = stats(kept) || st;
    const tape = (VS.viz && VS.viz.fareTape) ? (VS.viz.fareTape() || []) : [];
    const meta = (VS.viz && VS.viz.importedRows) ? (VS.viz.importedRows() || null) : null;
    const hist = (VS.f9 && VS.f9._history) ? VS.f9._history.map((h) => ({ idx: h.idx, exf: h.exf, corr: h.corr })) : [];

    // fare ledger: pair every fare with airline/flight (real when the CSV carried it) + status + z-score.
    // when the import brought metadata for every row, sort it by price and zip 1:1 with the sorted fares.
    const AL = ['6E', 'AI', 'UK', 'SG', 'QP', 'IX'];
    const sortedAll = [...all].sort((a, c) => a - c);
    const metaSorted = (meta && meta.length === all.length) ? [...meta].sort((a, c) => a.price - c.price) : null;
    const flightLabel = (p, i) => {
      const mm = metaSorted && metaSorted[i];
      if (mm && (mm.airline || mm.flight)) {
        const al = (mm.airline || '').trim(), fl = (mm.flight || '').trim();
        if (fl && al && fl.toUpperCase().includes(al.toUpperCase())) return fl;
        return [al, fl].filter(Boolean).join(' ');
      }
      return `${AL[i % AL.length]}-${1000 + Math.floor(Math.abs(Math.sin(p * 1.7)) * 8000)}`;
    };
    const ledger = sortedAll.map((p, i) => {
      const status = (p < r.lower) ? 'excluded · low' : (p > r.upper) ? 'excluded · high'
        : (p < st.p10 || p > st.p90) ? 'kept · outer decile' : 'kept';
      const z = stKept.sd ? (p - stKept.mean) / stKept.sd : 0;
      return {
        flight: flightLabel(p, i), price: p, status, z,
        cls: status.startsWith('excluded') ? 'is-excl' : status.startsWith('kept ·') ? 'is-tail' : '',
      };
    });

    const trend = r.index >= 108 ? ['up', 'INFLATED'] : r.index >= 100 ? ['flat', 'NEAR BASE'] : ['flat', 'BELOW BASE'];

    host.innerHTML = `
      <div class="r-cover">
        <div class="r-title">VAYU-SUCHAK — Airfare Price Index Report</div>
        <div class="r-sub">Real-time Airfare Price Index for India · MoSPI · SIH26056 · Team Chakravyuh</div>
        <div class="r-meta">
          <div><span>run id</span> <b>${esc(r.runId)}</b></div>
          <div><span>corridor</span> <b>${esc(r.corridor.replace('-', '–'))}</b></div>
          <div><span>generated</span> <b>${esc(now)} IST</b></div>
          <div><span>date window</span> <b>${esc(r.start)} → ${esc(r.end)}</b></div>
          <div><span>k_factor</span> <b>${r.k.toFixed(1)}</b></div>
          <div><span>base period</span> <b>2022 = 100</b></div>
          <div><span>acquisition</span> <b>${r.imported ? 'CSV extract' : 'Playwright scrape pool'}</b></div>
          <div><span>fares ingested</span> <b>${st.n}</b></div>
          <div><span>fares kept / excluded</span> <b>${kept.length} / ${excl.length}</b></div>
        </div>
      </div>

      <div class="r-headline">
        <div class="r-idx">${r.index.toFixed(2)}<small>index</small></div>
        <div class="r-exf">ex-festival ${r.exf.toFixed(2)} &nbsp;·&nbsp; festival ${festDelta >= 0 ? '+' : ''}${festDelta.toFixed(2)} &nbsp;·&nbsp; ${(r.index - 100) >= 0 ? '+' : ''}${(r.index - 100).toFixed(2)}% vs base</div>
        <span class="r-badge ${trend[0]}">${trend[1]}</span>
      </div>

      <section>
        <h2>1 · Executive summary</h2>
        <div class="r-three">
          <div class="r-stat"><div class="sv">${r.index.toFixed(2)}</div><div class="sl">index (base 100)</div></div>
          <div class="r-stat"><div class="sv">${inr(b.Pt != null ? b.Pt : st.med)}</div><div class="sl">Pt · median kept fare</div></div>
          <div class="r-stat"><div class="sv">${inr(b.P0)}</div><div class="sl">P0 · base-year fare</div></div>
          <div class="r-stat"><div class="sv">${((b.Pt != null ? b.Pt : st.med) / b.P0 * 100 - 100 >= 0 ? '+' : '')}${((b.Pt != null ? b.Pt : st.med) / b.P0 * 100 - 100).toFixed(1)}%</div><div class="sl">real price change</div></div>
          <div class="r-stat"><div class="sv">${excl.length}</div><div class="sl">outliers removed (k=${r.k.toFixed(1)})</div></div>
          <div class="r-stat"><div class="sv">${festDelta >= 0 ? '+' : ''}${festDelta.toFixed(2)}</div><div class="sl">festival uplift (idx pts)</div></div>
        </div>
        <p>For <b>${esc(r.corridor.replace('-', '–'))}</b> over <b>${esc(r.start)} → ${esc(r.end)}</b>, ${st.n} fares were ${r.imported ? 'loaded from the CSV extract' : 'scraped'}; ${excl.length} fell outside the IQR fence <b>${inr(r.lower)}–${inr(r.upper)}</b> and were dropped before the median. The kept median <b>${inr(b.Pt != null ? b.Pt : st.med)}</b> against the 2022 base <b>${inr(b.P0)}</b> gives a price relative of <b>${r.priceRelative.toFixed(2)}</b>; the festival component adds <b>${festDelta >= 0 ? '+' : ''}${festDelta.toFixed(2)}</b>, for a headline index of <b>${r.index.toFixed(2)}</b> — ${(r.index - 100) >= 0 ? 'up' : 'down'} ${Math.abs(r.index - 100).toFixed(2)}% on the base period.</p>
      </section>

      <section>
        <h2>2 · Fare distribution <span class="h-note">n = ${st.n} · ${Math.max(6, Math.min(16, Math.round(Math.sqrt(st.n)) + 4))} bins</span></h2>
        <div class="r-chart">${chartHistogram(all, st, stKept, r)}<div class="cap">Bar height = fare count; number printed above each bar. Green = inside inter-quartile band, amber = distribution tail (still counted), red = outside the k-fence (dropped). The x-axis focuses on the kept spread; fares beyond it are counted into the edge bins and noted. Dashed verticals mark lower fence, Q1, Pt (median), Q3, upper fence — each with its ₹ value.</div></div>
        <table>
          <thead><tr><th>statistic</th><th class="num">all ingested</th><th class="num">kept (post-fence)</th></tr></thead>
          <tbody>
            <tr><td>count</td><td class="num">${st.n}</td><td class="num">${stKept.n}</td></tr>
            <tr><td>min</td><td class="num">${inr(st.min)}</td><td class="num">${inr(stKept.min)}</td></tr>
            <tr><td>Q1 (25th pct)</td><td class="num">${inr(st.q1)}</td><td class="num">${inr(stKept.q1)}</td></tr>
            <tr><td>median</td><td class="num">${inr(st.med)}</td><td class="num">${inr(stKept.med)}</td></tr>
            <tr><td>mean</td><td class="num">${inr(st.mean)}</td><td class="num">${inr(stKept.mean)}</td></tr>
            <tr><td>Q3 (75th pct)</td><td class="num">${inr(st.q3)}</td><td class="num">${inr(stKept.q3)}</td></tr>
            <tr><td>max</td><td class="num">${inr(st.max)}</td><td class="num">${inr(stKept.max)}</td></tr>
            <tr><td>std deviation</td><td class="num">${inr(st.sd)}</td><td class="num">${inr(stKept.sd)}</td></tr>
            <tr><td>coeff. of variation</td><td class="num">${st.cv.toFixed(1)}%</td><td class="num">${stKept.cv.toFixed(1)}%</td></tr>
            <tr><td>IQR</td><td class="num">${inr(st.q3 - st.q1)}</td><td class="num">${inr(stKept.q3 - stKept.q1)}</td></tr>
          </tbody>
        </table>
        <div class="r-chart">${chartStrip(all, st, stKept, r)}<div class="cap">Every individual fare in the run, sorted low → high. Stem colour: green = inter-quartile band, amber = tail (retained), red = outside the fence (dropped, ₹ labelled). Dashed horizontals mark the fence and the median.</div></div>
      </section>

      <section>
        <h2>3 · Two-tailed IQR outlier filter <span class="h-note">k = ${r.k.toFixed(1)}</span></h2>
        <div class="r-chart">${chartBox(all, st, stKept, r)}<div class="cap">Box = Q1→Q3, centre line = median, whiskers = k-fence. Red dots below the axis are the ${excl.length} excluded fare(s), ₹ labelled. All five cut points carry their ₹ values.</div></div>
        <div class="r-two">
          <div>
            <div class="r-kv"><span>Q1 − k·IQR (lower)</span><b>${inr(r.lower)}</b></div>
            <div class="r-kv"><span>Q3 + k·IQR (upper)</span><b>${inr(r.upper)}</b></div>
            <div class="r-kv"><span>IQR (Q3 − Q1)</span><b>${inr(st.q3 - st.q1)}</b></div>
          </div>
          <div>
            <div class="r-kv"><span>excluded — below</span><b>${iq.low ?? excl.filter((p) => p < r.lower).length}</b></div>
            <div class="r-kv"><span>excluded — above</span><b>${iq.high ?? excl.filter((p) => p > r.upper).length}</b></div>
            <div class="r-kv"><span>retention rate</span><b>${(100 * kept.length / Math.max(1, st.n)).toFixed(1)}%</b></div>
          </div>
        </div>
        ${excl.length ? `<table style="margin-top:8px;">
          <thead><tr><th>flight</th><th class="num">fare</th><th class="num">Δ vs fence</th><th class="num">z-score</th><th>reason</th></tr></thead>
          <tbody>${ledger.filter((row) => row.cls === 'is-excl').map((row) => {
            const lowOut = row.price < r.lower;
            const d = lowOut ? r.lower - row.price : row.price - r.upper;
            return `<tr class="is-excl"><td>${esc(row.flight)}</td><td class="num">${inr(row.price)}</td><td class="num">${inr(d)}</td><td class="num">${(row.z >= 0 ? '+' : '') + row.z.toFixed(1)}</td><td>${lowOut ? 'below lower fence' : 'above upper fence'}</td></tr>`;
          }).join('')}</tbody>
        </table>` : '<p>No fares fell outside the fence at this k.</p>'}
      </section>

      <section>
        <h2>4 · Index composition</h2>
        <div class="r-chart">${chartWaterfall(r)}<div class="cap">How the headline index is built: base 100 → price relative (Pt/P0 × 100 = ${r.priceRelative.toFixed(2)}) → + festival component (${festDelta >= 0 ? '+' : ''}${festDelta.toFixed(2)}) → index ${r.index.toFixed(2)}. Each bar and step is labelled.</div></div>
        <div class="r-formula">[ Σ(P<sub>t</sub>·Q<sub>0</sub>) / Σ(P<sub>0</sub>·Q<sub>0</sub>) ] × 100 = (${Math.round(b.Pt != null ? b.Pt : st.med).toLocaleString('en-IN')} / ${b.P0.toLocaleString('en-IN')}) × 100 = ${r.priceRelative.toFixed(2)} &nbsp;→&nbsp; + festival ${(r.fest || 0).toFixed(2)} &nbsp;→&nbsp; index ${r.index.toFixed(2)}</div>
        <table>
          <thead><tr><th>corridor</th><th class="num">Pt (median kept)</th><th class="num">P0 (base yr)</th><th class="num">Q0 (volume wt)</th><th class="num">Pt/P0 ×100</th><th class="num">+ festival</th><th class="num">index</th></tr></thead>
          <tbody><tr>
            <td>${esc(r.corridor.replace('-', '–'))}</td>
            <td class="num">${inr(b.Pt != null ? b.Pt : st.med)}</td>
            <td class="num">${inr(b.P0)}</td>
            <td class="num">${b.Q0}</td>
            <td class="num">${r.priceRelative.toFixed(2)}</td>
            <td class="num">${festDelta >= 0 ? '+' : ''}${festDelta.toFixed(2)}</td>
            <td class="num">${r.index.toFixed(2)}</td>
          </tr></tbody>
        </table>
        <p>P0 from a Kaggle historical Indian-domestic-fares dataset; Q0 from DGCA airport-pair passenger volumes (data.gov.in). This prototype audits one corridor per run — the national index is the Q0-weighted aggregate across all audited corridors.</p>
      </section>

      <section>
        <h2>5 · Festival adjustment <span class="h-note">holidays.India ±7 days</span></h2>
        <div class="r-two">
          <div>
            <div class="r-kv"><span>fares in a festival window</span><b>${r.festFlags ?? '—'} / ${st.n}</b></div>
            <div class="r-kv"><span>index — all fares</span><b>${r.index.toFixed(2)}</b></div>
            <div class="r-kv"><span>index — ex-festival</span><b>${r.exf.toFixed(2)}</b></div>
          </div>
          <div>
            <div class="r-kv"><span>festival component</span><b>${festDelta >= 0 ? '+' : ''}${festDelta.toFixed(2)} idx pts</b></div>
            <div class="r-kv"><span>share of the move</span><b>${r.index - 100 ? (100 * festDelta / (r.index - 100)).toFixed(0) : '0'}%</b></div>
            <div class="r-kv"><span>window vs Diwali (Nov 8)</span><b>${esc(r.start)} → ${esc(r.end)}</b></div>
          </div>
        </div>
        <p>Fares dated within ±7 days of a gazetted festival are tagged; the ex-festival index re-computes with them removed so a seasonal spike does not leak into the trend line.</p>
      </section>

      <section>
        <h2>6 · Session index history <span class="h-note">${hist.length} completed run(s)</span></h2>
        ${hist.length ? `<div class="r-chart">${chartHistory(hist)}<div class="cap">VAYU index per completed audit this session, each point labelled with its corridor. The line only connects consecutive runs of the same corridor — each index is scaled to its own base fare, so a corridor switch breaks the line rather than reading as a real move. Dashed: base = 100. The dashboard's Index History panel overlays the live MoSPI CPI air-fare series.</div></div>
        <table style="margin-top:6px;">
          <thead><tr><th>run</th><th>corridor</th><th class="num">index</th><th class="num">ex-festival</th><th class="num">Δ prev</th></tr></thead>
          <tbody>${hist.map((h, i) => `<tr><td>${i + 1}</td><td>${esc((h.corr || r.corridor).replace('-', '–'))}</td><td class="num">${h.idx.toFixed(2)}</td><td class="num">${h.exf.toFixed(2)}</td><td class="num">${i ? ((h.idx - hist[i - 1].idx) >= 0 ? '+' : '') + (h.idx - hist[i - 1].idx).toFixed(2) : '—'}</td></tr>`).join('')}</tbody>
        </table>` : '<p>This is the first completed run of the session — the history chart populates from the second audit onward.</p>'}
      </section>

      ${(() => {
        const LIM = 72;
        const full = ledger.length <= LIM;
        const shown = full ? ledger.map((row, i) => ({ row, i }))
          : ledger.map((row, i) => ({ row, i })).filter((x) => x.row.cls || x.i % Math.ceil(ledger.length / LIM) === 0);
        return `<section class="r-pagebreak">
        <h2>7 · Fare ledger <span class="h-note">${full ? `all ${ledger.length} fares` : `${shown.length} of ${ledger.length} — all outliers + tails + every ${Math.ceil(ledger.length / LIM)}ᵗʰ kept fare`}</span></h2>
        <table>
          <thead><tr><th class="num">#</th><th>flight</th><th class="num">fare</th><th class="num">z-score</th><th class="num">Δ median</th><th>status</th></tr></thead>
          <tbody>${shown.map(({ row, i }) => `<tr class="${row.cls}"><td class="num">${i + 1}</td><td>${esc(row.flight)}</td><td class="num">${inr(row.price)}</td><td class="num">${(row.z >= 0 ? '+' : '') + row.z.toFixed(2)}</td><td class="num">${(row.price - stKept.med >= 0 ? '+' : '') + inr(row.price - stKept.med)}</td><td>${row.status}</td></tr>`).join('')}</tbody>
        </table>
        <p>z-score is against the mean/σ of the kept fares (${inr(stKept.mean)} ± ${inr(stKept.sd)}). Shaded rows: red = excluded by the fence, amber = distribution tail but retained.${full ? '' : ' Every excluded and tail fare is listed in full; kept fares are sampled to keep the table to one page.'}</p>
      </section>`;
      })()}

      <div class="r-foot">
        run ${esc(r.runId)} · reproducible: identical (corridor, window, k, fare set) → identical index · pandas, no random seeds ·
        outliers flagged and stored, never deleted · Postgres primary, SQLite WAL fallback · charts generated in-browser from the run record.
        <span class="r-flag">Prototype scope: one corridor per Execute run (the national index is the Q0-weighted sum across the 16-corridor basket, collected daily). P0/Q0 from the 2022 base-year reference — Kaggle median economy fares + DGCA city-pair passenger volumes.</span>
      </div>
    `;
  }
})();
