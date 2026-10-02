/* ============================================================
   STAGE F4 — boot choreography. Defines window.VS.runAudit().
   Simulated data (F6 wires real IQR math; F9 wires the backend).
   ============================================================ */
(function () {
  const VS  = window.VS;
  const app = document.getElementById('app');
  const btn = document.getElementById('execute');
  const glyph = btn.querySelector('.glyph');
  const label = btn.querySelector('.btn-label');

  const flap       = document.getElementById('indexFlap');
  const flapCells  = flap.querySelectorAll('.flap-cell');
  const readoutPanel = document.getElementById('readoutPanel');
  const exfestVal  = document.getElementById('exfestVal');
  const deltaChip  = document.getElementById('deltaChip');
  const metaLine   = document.getElementById('metaLine');
  const badges     = document.getElementById('badges');
  const seal       = null;   /* reproducibility seal removed */
  const consoleChip = document.getElementById('consoleChip');
  const nodes      = document.querySelectorAll('.pnode');
  const historyLine = document.getElementById('historyLine');
  const cmdDot     = document.querySelector('.command-bar .dot');
  const cmdTxt     = document.querySelector('.command-bar .status-txt');
  const hDot       = document.querySelector('.header .dot');
  const hStat      = document.querySelector('.header .hstatus');
  const runidEl    = null;   /* per-run id removed */

  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hex = (n) => Array.from({ length: n }, () => Math.floor(Math.random() * 16).toString(16)).join('');

  let busy = false, hasRun = false, curIndex = 100, runCount = 0;

  /* ---- small animation helpers ------------------------------ */
  function countUp(el, to, dur, dec) {
    if (reduce || document.hidden) { el.textContent = dec ? to.toFixed(dec) : Math.round(to); return; }
    const t0 = performance.now();
    const step = (now) => {
      const p = Math.min(1, (now - t0) / dur);
      const e = 1 - Math.pow(1 - p, 3);
      el.textContent = dec ? (to * e).toFixed(dec) : Math.round(to * e);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  const digitsOf = (v) => Math.max(0, v).toFixed(2).replace('.', '').padStart(5, '0').slice(-5).split('');

  function splitFlapTo(from, to, dur) {
    if (reduce || document.hidden) {
      digitsOf(to).forEach((d, i) => (flapCells[i].textContent = d));
      return Promise.resolve();
    }
    return new Promise((res) => {
      const t0 = performance.now();
      const step = (now) => {
        const p = Math.min(1, (now - t0) / dur);
        const e = 1 - Math.pow(1 - p, 3);
        digitsOf(from + (to - from) * e).forEach((d, i) => {
          if (flapCells[i].textContent !== d) {
            flapCells[i].textContent = d;
            flapCells[i].classList.remove('flip'); void flapCells[i].offsetWidth; flapCells[i].classList.add('flip');
          }
        });
        if (p < 1) requestAnimationFrame(step);
        else { flapCells.forEach((c) => c.classList.remove('flip')); res(); }
      };
      requestAnimationFrame(step);
    });
  }

  function setNode(i, s, sub) {
    const n = nodes[i];
    const was = n.classList.contains('done') ? 'done' : n.classList.contains('active') ? 'active' : 'idle';
    n.classList.remove('idle', 'active', 'done');
    n.classList.add(s);
    const nt = document.querySelector('.status-strip [data-tile="nodes"]');
    if (nt) nt.textContent = String([...nodes].filter((x) => x.classList.contains('done')).length);
    const m = n.querySelector('.marker');
    const num = n.querySelector('.num');
    if (num) num.textContent = String(i + 1);
    n.querySelector('.p-sub').textContent = sub || (s === 'active' ? 'running…' : s === 'idle' ? 'idle' : '');

    // "on-deck" hint: the next still-idle node breathes so the flow reads left-to-right
    nodes.forEach((node, j) => node.classList.toggle('on-deck', !reduce && s === 'active' && j === i + 1 && node.classList.contains('idle')));

    if (reduce) return;
    if (s !== was && (s === 'active' || s === 'done')) {
      m.classList.remove('kick'); void m.offsetWidth; m.classList.add('kick');
    }
    // restart the connector fill + data-bead each time this node goes active
    if (s === 'active') {
      const fillEl = n.querySelector('.conn > i'), dotEl = n.querySelector('.conn > b');
      [fillEl, dotEl].forEach((el) => { if (el) { el.style.animation = 'none'; void el.offsetWidth; el.style.animation = ''; } });
    }
  }

  const hStatTxt = hStat && hStat.querySelector('.hstatus-txt');
  function setDot(cls, txt) {
    [cmdDot, hDot].forEach((d) => d && (d.className = 'dot ' + cls));
    if (cmdTxt) cmdTxt.textContent = ' ' + txt;
    if (hStatTxt) hStatTxt.textContent = ' ' + txt;
  }

  function lockBtn() { btn.disabled = true; btn.setAttribute('aria-busy', 'true'); btn.classList.add('running'); glyph.textContent = '◐'; label.textContent = 'Auditing…'; }
  function unlockBtn() { btn.disabled = false; btn.setAttribute('aria-busy', 'false'); btn.classList.remove('running'); glyph.textContent = '▶'; label.textContent = 'Execute Audit'; }

  function revealPanels() {
    const panels = [
      document.querySelector('.header'),
      document.querySelector('.status-strip'),
      ...document.querySelectorAll('.live-main > .panel'),
      ...document.querySelectorAll('.readout-col > .panel'),
      document.querySelector('.anomalies'),
    ].filter(Boolean);
    panels.forEach((p, i) => {
      if (reduce) { p.style.animation = 'none'; return; }
      p.style.animation = 'none'; void p.offsetWidth;
      p.style.animation = `panelIn 320ms var(--ease) ${i * 50}ms both`;
    });
  }

  // Index History is drawn by F6 from the actual run log (VS.viz.pushHistory).
  function drawHistory(idx, exf) {
    if (VS.viz && VS.viz.pushHistory) VS.viz.pushHistory(idx, exf);
  }

  const metaFor = (idx) => `base 2022 = 100 · ${idx >= 100 ? '+' : ''}${(idx - 100).toFixed(2)}%`;

  // festival_component = headline index − ex-festival index. It is the festival
  // window's *contribution* to the headline, NOT a change in the ex-festival
  // number, so it carries its own sign and direction.
  function setFestivalChip(fc) {
    fc = +fc || 0;
    deltaChip.hidden = Math.abs(fc) < 1.0;
    deltaChip.classList.toggle('neg', fc < 0);
    deltaChip.textContent = `${fc >= 0 ? '▲ +' : '▼ −'}${Math.abs(fc).toFixed(2)} festival`;
    deltaChip.title = fc >= 0
      ? `festival-window fares lift the index by ${fc.toFixed(2)} pts`
      : `festival-window fares sit ${Math.abs(fc).toFixed(2)} pts below the rest of the basket in this sample`;
  }

  function resetForBoot() {
    for (let i = 0; i < 7; i++) setNode(i, 'idle', 'idle');
    digitsOf(100).forEach((d, i) => (flapCells[i].textContent = d));
    exfestVal.textContent = '—';
    deltaChip.hidden = true;
    metaLine.textContent = 'base 2022 = 100 · auditing…';
    badges.classList.remove('in');
    readoutPanel.classList.remove('complete');
    consoleChip.textContent = 'running';
  }

  /* The index math lives in the backend now (pipeline/index_engine.py +
     laspeyres.py): every number on screen comes from /api/execute-audit
     (live/cache scrape) or /api/apix (the daily-collected series). There is
     no client-side estimate — if the backend is unreachable the run reports
     that honestly rather than inventing a figure. */

  const consolePanel = consoleChip.closest('.panel');
  const setBusy = (on) => { if (consolePanel && !reduce) consolePanel.classList.toggle('busy', on); };

  /* ============================================================
     runAudit — drives the boot choreography from the real backend
     SSE stream (/api/execute-audit). A loaded CSV routes to
     runImportedAudit() (POST /api/import-csv). No offline estimate:
     if the backend can't be reached the run stops and says so.
     ============================================================ */
  const NODE_OF = { INGEST: 0, FESTIVAL: 1, IQR: 2, INTEGRITY: 3, NOWCAST: 4, LASPEYRES: 5, DB: 6 };

  async function runAudit() {
    if (busy) return;
    const s = VS.getState();
    // Live scrape by default (scraper only — no Travelpayouts/cache top-up,
    // so a source that's down shows up as down, not silently backfilled).
    // The mode-toggle button (below) switches to cache — today's already-
    // collected snapshot, zero network load on any live source — for
    // testing/demo runs where you don't want to hit real sites again.
    // ?mode=auto is the third, unexposed option: live scrape, but if fewer
    // than ingest_min_fares come back it silently tops up from Travelpayouts
    // then same-day cache (backend already supports this — pipeline/ingest.py
    // fetch_fares — it just wasn't reachable from the UI before). Per-source
    // status still reports honestly either way; only the "is the run usable"
    // floor gets a safety net. Use it if a source flakes mid-demo.
    // ?mode= in the URL still overrides both, for quick manual checks.
    const mode = new URLSearchParams(location.search).get('mode')
              || localStorage.getItem('vsMode') || 'live';
    const imported = !!(VS.viz && VS.viz.isImported && VS.viz.isImported());
    if (imported) return runImportedAudit(s);

    // guard the date range before we open the stream
    const dayspan = Math.round((new Date(s.end) - new Date(s.start)) / 86400000);
    if (!(dayspan >= 0)) {
      if (VS.toast) VS.toast('warn', 'Check the date range', 'end date is before the start date');
      return;
    }
    if (dayspan > 100) {
      if (VS.toast) VS.toast('warn', 'Date range too wide', `${dayspan} days — the audit window is capped at 100 days`);
      return;
    }

    busy = true; lockBtn(); setBusy(true);

    const srcBadge = document.getElementById('srcBadge');
    if (srcBadge) {
      const bd = srcBadge.querySelector('.bdot'); if (bd) bd.className = 'bdot scrape';
      const t = srcBadge.querySelector('.src-txt');
      if (t) t.textContent = mode === 'cache' ? 'cache snapshot' : mode === 'auto' ? 'live scrape (auto top-up)' : 'live scrape';
    }

    const fresh = !(hasRun && app.classList.contains('is-live'));
    runCount++;
    app.classList.remove('flash'); void app.offsetWidth; app.classList.add('flash');
    setDot('running', 'RUNNING');
    app.classList.add('is-live');
    resetForBoot();
    if (fresh) revealPanels();
    if (VS.f9 && VS.f9.onRunStart) VS.f9.onRunStart(s.corridor, null);
    // tiles show '·' until the SSE stream delivers real numbers (Stages counts up live)
    document.querySelectorAll('.status-strip [data-tile]').forEach((el) => {
      if (el.dataset.tile === 'clock') return;
      if (el.dataset.tile === 'nodes') { el.textContent = '0'; return; }
      el.textContent = '·'; delete el.dataset.real;
    });
    VS.clearConsole(); VS.resetClock(); VS.showCursor();
    if (fresh) await VS.runBios();
    if (VS.viz) { VS.viz.setCorridor(s.corridor); VS.viz.travelRunning(true); }

    let iqrShape = null, gotAnyStage = false, lastNode = -1, sourcesVerifying = false;
    const runT0 = performance.now();
    let ingestedN = 0, ingestSecs = 0;
    const tile = (name) => document.querySelector('.status-strip [data-tile="' + name + '"]');
    const setTile = (name, val, dec) => {
      const el = tile(name); if (!el) return;
      el.dataset.to = String(val); el.dataset.real = '1';
      el.textContent = dec != null ? Number(val).toFixed(dec) : String(Math.round(val));
    };
    const advanceTo = (ni) => {
      for (let j = lastNode + 1; j < ni; j++) setNode(j, 'done');
      if (ni > lastNode) { setNode(ni, 'active'); lastNode = ni; }
    };

    const done = await new Promise((resolve) => {
      const q = new URLSearchParams({
        corridor: s.corridor, start: s.start, end: s.end,
        k_factor: s.kFactor, mode: (mode === 'cache' || mode === 'auto') ? mode : 'live',
      });
      let es;
      try { es = new EventSource('/api/execute-audit?' + q); }
      catch (err) { resolve(null); return; }

      es.onmessage = (e) => {
        let d; try { d = JSON.parse(e.data); } catch (err) { return; }
        gotAnyStage = true;
        // ixigo isn't shown in the Scrape Sources panel — don't leak its
        // "blocked" line into the console either, same reasoning throughout.
        if (d.stage === 'SOURCE' && d.source === 'ixigo') return;

        const isFallback = d.stage === 'INGEST' && /fallback|degraded|cache|travelpayouts/i.test(d.message);
        VS.appendLine(d.stage, d.message, { fallback: isFallback });
        VS.showCursor();

        if (d.stage in NODE_OF) advanceTo(NODE_OF[d.stage]);

        if (d.stage === 'SOURCE') {
          if (!sourcesVerifying) { sourcesVerifying = true; if (VS.f9 && VS.f9.markVerifying) VS.f9.markVerifying(); }
          if (VS.f9 && VS.f9.applySourceOne) VS.f9.applySourceOne(d.source, d);
        } else if (d.stage === 'INGEST') {
          if (VS.f9 && VS.f9.applySources) VS.f9.applySources(d.sources, d.ingestion_source);
          // reflect an auto-mode fallback on the source badge, not just explicit cache mode
          if (srcBadge) {
            const st = d.ingestion_source;
            const lbl = st === 'cache' ? 'cache snapshot' : st === 'travelpayouts' ? 'travelpayouts API'
              : (d.tiers && d.tiers.length > 1) ? 'live + fallback' : 'live scrape';
            const t = srcBadge.querySelector('.src-txt'); if (t) t.textContent = lbl;
            const bd = srcBadge.querySelector('.bdot'); if (bd) bd.className = 'bdot ' + (st === 'live_scrape' ? 'scrape' : 'cache');
          }
          ingestedN = d.fares || 0;
          ingestSecs = Math.max(0.1, (performance.now() - runT0) / 1000);
          const srcs = d.sources && typeof d.sources === 'object' ? Object.entries(d.sources) : [];
          const lat = srcs.map(([, x]) => x).filter((x) => x && x.latency_ms).map((x) => x.latency_ms);
          const rtt = lat.length ? Math.max.apply(null, lat) / 1000 : ingestSecs;
          setTile('latency', +rtt.toFixed(1), 1);
          setTile('throughput', Math.max(1, Math.round(ingestedN / ingestSecs)));
          const pending = srcs.filter(([, x]) => x && x.status === 'pending').length;
          setTile('queue', pending);
          // real graceful-degrade banner: name the sources the pool couldn't use
          // (ixigo excluded — dropped from the panel, not named in the demo)
          const blk = srcs.filter(([n, x]) => n !== 'ixigo' && x && (x.status === 'blocked' || x.status === 'unavailable'))
                          .map(([n, x]) => `${({indigo:'IndiGo',makemytrip:'MakeMyTrip',googleflights:'Google Flights',airindia:'Air India'})[n] || n}${/robots/.test(x.block_reason || '') ? ' (robots.txt)' : ''}`);
          if (blk.length && VS.f9 && VS.f9.degrade) {
            const okN = srcs.filter(([, x]) => x && x.status === 'ok').length;
            VS.f9.degrade('warn', `${blk.join(', ')} not crawled — ${okN} source${okN === 1 ? '' : 's'} live, routed via the rest + cache`);
          }
          setNode(0, 'done', (d.fares != null ? d.fares + ' fares' : (d.ingestion_source || 'done')));
        } else if (d.stage === 'FESTIVAL') {
          setNode(1, 'done', (d.flagged || 0) + ' flagged');
        } else if (d.stage === 'IQR') {
          const all = (d.clean_prices || []).concat(d.anomaly_prices || []);
          const f = d.fences || {};
          iqrShape = {
            lower: f.lower_fence, upper: f.upper_fence, IQR: f.IQR, Q1: f.Q1, Q3: f.Q3,
            anomalies: d.anomaly_prices || [], clean: d.clean_prices || [],
            anomalyRows: d.anomaly_rows || [],
            low: d.excluded_low || 0, high: d.excluded_high || 0,
          };
          if (VS.viz && all.length) {
            try { VS.viz.drawHistogram(all, iqrShape); VS.viz.drawAnomTable(iqrShape); } catch (err) {}
          }
          // top ticker → this corridor's own scraped fares
          if (VS.viz && VS.viz.setRunTape) {
            const fen = { lower: f.lower_fence, upper: f.upper_fence, Q1: f.Q1, Q3: f.Q3 };
            const keptRows = (d.clean_rows && d.clean_rows.length)
              ? d.clean_rows
              : (d.clean_prices || []).map((p) => ({ price: p }));
            VS.viz.setRunTape(s.corridor, keptRows, d.anomaly_rows || [], fen);
            if (window.__renderTicker) window.__renderTicker();
          }
          if (ingestedN) {
            const kept = Math.max(0, ingestedN - (d.anomalies || 0));
            setTile('integrity', +(100 * kept / ingestedN).toFixed(1), 1);
          }
          setNode(2, 'done', 'k' + (+s.kFactor).toFixed(1) + ' · ' + (d.anomalies || 0) + ' excl');
        } else if (d.stage === 'INTEGRITY') {
          setNode(3, 'done', d.model_loaded ? (d.ml_flagged || 0) + ' flagged' : (d.ml_flagged || 0) + ' flagged (fallback)');
        } else if (d.stage === 'NOWCAST') {
          setNode(4, 'done', d.imputed ? d.imputed + ' imputed' : 'no gaps');
        } else if (d.stage === 'LASPEYRES') {
          if (VS.fx && VS.fx.rise) VS.fx.rise();
          splitFlapTo(curIndex, d.index, 900);
          flap.classList.remove('punch'); void flap.offsetWidth; flap.classList.add('punch');
          readoutPanel.classList.add('complete');
          if (!reduce) { readoutPanel.classList.remove('scan'); void readoutPanel.offsetWidth; readoutPanel.classList.add('scan'); setTimeout(function () { readoutPanel.classList.remove('scan'); }, 800); }
          countUp(exfestVal, d.index_ex_festival != null ? d.index_ex_festival : d.index, 700, 2);
          setFestivalChip(d.festival_component);
          metaLine.textContent = metaFor(d.index);
          if (VS.viz && VS.viz.setSubIndex) VS.viz.setSubIndex(s.corridor, d.index);
          setNode(5, 'done', (+d.index).toFixed(2));
          curIndex = d.index;
        } else if (d.stage === 'DB') {
          setNode(6, 'done', d.db_target || 'db');
          const dbB = document.getElementById('dbBadge');
          if (dbB) {
            const t = d.db_target === 'postgres' ? 'postgres'
                    : d.db_target === 'sqlite_fallback' ? 'sqlite (wal)' : (d.db_target || 'database');
            dbB.querySelector('.db-txt').textContent = t;
            dbB.querySelector('.bdot').className = 'bdot ' + (d.db_target === 'postgres' ? 'postgres' : 'scrape');
          }
          badges.classList.add('in');
        }

        if (d.done) {
          if (d.records_ingested) {
            const kept = Math.max(0, d.records_ingested - (d.anomalies || 0) - (d.ml_flagged || 0));
            setTile('integrity', +(100 * kept / d.records_ingested).toFixed(1), 1);
          }
          setTile('queue', 0);
          es.close(); resolve(d.error ? null : d);
        }
      };

      es.onerror = function () {
        es.close();
        resolve(gotAnyStage ? '__partial__' : null);
      };
    });

    if (done === null && !gotAnyStage) {
      VS.appendLine('SYSTEM', 'no response from the API server (is run.py running on :8000?)', { fallback: true });
      VS.removeCursor();
      if (VS.viz) VS.viz.travelRunning(false);
      setDot('warn', 'API OFFLINE');
      consoleChip.textContent = 'offline';
      if (VS.toast) VS.toast('err', 'API server not responding', 'start the backend: python run.py');
      setBusy(false);
      hasRun = false; busy = false; unlockBtn();
      return;
    }
    // the stream delivered only an error frame (bad params etc.)
    if (done === null && gotAnyStage) {
      VS.removeCursor();
      if (VS.viz) VS.viz.travelRunning(false);
      setDot('warn', 'REJECTED');
      consoleChip.textContent = 'error';
      setBusy(false);
      hasRun = false; busy = false; unlockBtn();
      return;
    }

    const d = (done && done !== '__partial__') ? done : {};

    if (d.index != null) {
      drawHistory(d.index, d.index_ex_festival);
      if (d.annotation) await VS.appendLine('EXPLAIN', d.annotation);
    }
    VS.removeCursor();
    if (VS.viz) VS.viz.travelRunning(false);
    if (VS.fx && VS.fx.chime) VS.fx.chime();
    setDot(d.index != null ? 'ok' : 'warn', d.index != null ? 'COMPLETE' : 'INCOMPLETE');
    consoleChip.textContent = 'done';
    setBusy(false);

    if (d.index != null && VS.f9 && VS.f9.onComplete) {
      const cr = d.corridor_row || {};
      VS.f9.onComplete({
        runId: (d.run_id || '').slice(0, 8), corridor: s.corridor, index: d.index, exf: d.index_ex_festival,
        k: s.kFactor, excl: d.anomalies || 0,
        lower: (d.fences || {}).lower_fence, upper: (d.fences || {}).upper_fence,
        fest: d.festival_component || 0, festFlags: d.festival_flagged || 0,
        start: s.start, end: s.end, nFares: d.records_ingested || null, imported: false,
        iqr: iqrShape, Pt: cr.Pt, P0: cr.P0, Q0: cr.Q0, priceRelative: d.index_ex_festival,
      });
    }
    hasRun = true; busy = false; unlockBtn();
  }

  /* ============================================================
     runImportedAudit — a loaded CSV runs through the SAME backend
     pipeline as a scrape, via POST /api/import-csv. The rows the
     importer already filtered to the selected corridor are posted
     back as a tiny CSV; the backend returns the real index + IQR.
     ============================================================ */
  async function runImportedAudit(s) {
    if (busy) return;
    busy = true; lockBtn(); setBusy(true);

    const rows = (VS.viz && VS.viz.importedRows && VS.viz.importedRows()) || [];
    const fares = (VS.viz && VS.viz.activeFares && VS.viz.activeFares()) || [];
    // synthesize a CSV the backend sanitizer accepts: it needs route, price,
    // airline and a departure timestamp, plus a unique flight_id per row.
    const dep = (s.start || new Date().toISOString().slice(0, 10)) + 'T06:00:00+05:30';
    const esc = (v) => { const t = String(v == null ? '' : v); return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; };
    const src = rows.length ? rows : fares.map((p) => ({ price: p }));
    const csv = 'flight_id,price,route,airline,flight_number,departure_ts\n' + src.map((r, i) => [
      'imp-' + i,
      r.price,
      (r.route || s.corridor).replace(/–/g, '-'),
      r.airline || '',
      r.flight || '',
      dep,
    ].map(esc).join(',')).join('\n');

    const srcBadge = document.getElementById('srcBadge');
    if (srcBadge) {
      const bd = srcBadge.querySelector('.bdot'); if (bd) bd.className = 'bdot csv';
      const t = srcBadge.querySelector('.src-txt'); if (t) t.textContent = `imported csv (${fares.length})`;
    }

    const fresh = !(hasRun && app.classList.contains('is-live'));
    runCount++;
    app.classList.remove('flash'); void app.offsetWidth; app.classList.add('flash');
    setDot('running', 'RUNNING');
    app.classList.add('is-live');
    resetForBoot();
    if (fresh) revealPanels();
    if (VS.f9 && VS.f9.onRunStart) VS.f9.onRunStart(s.corridor, null);
    VS.clearConsole(); VS.resetClock(); VS.showCursor();
    if (fresh) await VS.runBios();
    if (VS.viz) { VS.viz.setCorridor(s.corridor); VS.viz.travelRunning(true); }

    for (let i = 0; i < 7; i++) setNode(i, i === 0 ? 'active' : 'idle');
    await VS.appendLine('INGEST', `csv extract · ${s.corridor} · ${fares.length} fare records (no live scrape)`);
    setNode(0, 'done', `csv · ${fares.length}`);

    let d = null;
    try {
      const fd = new FormData();
      fd.append('file', new Blob([csv], { type: 'text/csv' }), 'import.csv');
      const r = await fetch(`/api/import-csv?k_factor=${encodeURIComponent(s.kFactor)}`,
                            { method: 'POST', body: fd });
      if (r.ok) d = await r.json();
      else await VS.appendLine('SYSTEM', `import rejected (${r.status}) — check the CSV`, { fallback: true });
    } catch (e) {
      await VS.appendLine('SYSTEM', 'backend unreachable — start the API server and retry', { fallback: true });
    }

    if (!d || d.index == null) {
      VS.removeCursor();
      if (VS.viz) VS.viz.travelRunning(false);
      setDot('warn', d ? 'IMPORT FAILED' : 'BACKEND OFFLINE');
      consoleChip.textContent = d ? 'failed' : 'offline';
      setBusy(false); hasRun = false; busy = false; unlockBtn();
      return;
    }

    setNode(1, 'active'); await VS.wait(140);
    await VS.appendLine('FESTIVAL', `holidays.India ±7d · ${d.festival_flagged || 0}/${d.records_ingested || fares.length} fares in a festival window`);
    setNode(1, 'done', `${d.festival_flagged || 0} flagged`);

    const f = d.fences || {};
    const iqrShape = {
      lower: f.lower_fence, upper: f.upper_fence, IQR: f.IQR, Q1: f.Q1, Q3: f.Q3,
      anomalies: d.anomaly_prices || [], clean: d.clean_prices || [],
      anomalyRows: d.anomaly_rows || [],
      low: d.excluded_low || 0, high: d.excluded_high || 0,
    };
    setNode(2, 'active'); await VS.wait(140);
    await VS.appendLine('IQR', `k=${(+s.kFactor).toFixed(1)} · fences [${Math.round(f.lower_fence)}, ${Math.round(f.upper_fence)}] · ${d.anomalies || 0} excluded (${d.excluded_low || 0} low, ${d.excluded_high || 0} high)`);
    const allPrices = (d.clean_prices || []).concat(d.anomaly_prices || []);
    if (VS.viz && allPrices.length) {
      try { VS.viz.drawHistogram(allPrices, iqrShape); VS.viz.drawAnomTable(iqrShape); } catch (err) {}
    }
    if (VS.viz && VS.viz.commitAudit) VS.viz.commitAudit(s.corridor, { index: d.index, iqr: iqrShape });
    if (window.__renderTicker) window.__renderTicker();
    setNode(2, 'done', `k${(+s.kFactor).toFixed(1)} · ${d.anomalies || 0} excl`);

    // CSV import bypasses the orchestrator's ML pass (/api/import-csv is a
    // plain sanitize -> IQR -> Laspeyres call) — no IsolationForest re-score,
    // no nowcast imputation for a single imported corridor. Say so honestly
    // rather than fake a value for these two nodes.
    setNode(3, 'done', 'n/a · csv import');
    setNode(4, 'done', 'n/a · csv import');

    setNode(5, 'active'); await VS.wait(140);
    await VS.appendLine('LASPEYRES', `Σ(Pt·Q0)/Σ(P0·Q0)×100 = ${(+d.index).toFixed(2)}${d.festival_component ? ` · +festival ${(+d.festival_component).toFixed(2)}` : ''} · Index = ${(+d.index).toFixed(2)}`);
    if (VS.fx && VS.fx.rise) VS.fx.rise();
    splitFlapTo(curIndex, d.index, 900);
    flap.classList.remove('punch'); void flap.offsetWidth; flap.classList.add('punch');
    readoutPanel.classList.add('complete');
    if (!reduce) { readoutPanel.classList.remove('scan'); void readoutPanel.offsetWidth; readoutPanel.classList.add('scan'); setTimeout(() => readoutPanel.classList.remove('scan'), 800); }
    countUp(exfestVal, d.index_ex_festival != null ? d.index_ex_festival : d.index, 700, 2);
    const fc = d.festival_component || 0;
    setFestivalChip(fc);
    metaLine.textContent = metaFor(d.index) + ` · ${d.routes_matched || 1} route${(d.routes_matched || 1) === 1 ? '' : 's'} · imported`;
    if (VS.viz && VS.viz.setSubIndex) VS.viz.setSubIndex(s.corridor, d.index);
    setNode(5, 'done', (+d.index).toFixed(2));
    curIndex = d.index;

    setNode(6, 'active'); await VS.wait(120);
    await VS.appendLine('DB', `${d.db_target || 'db'}.commit OK · audit_runs · run=${(d.run_id || '').slice(0, 8)}`);
    setNode(6, 'done', d.db_target || 'db');
    badges.classList.add('in');

    await VS.appendLine('SYSTEM', `import.complete · Index = ${(+d.index).toFixed(2)}`);
    VS.removeCursor();
    if (VS.viz) VS.viz.travelRunning(false);
    if (VS.fx && VS.fx.chime) VS.fx.chime();
    setDot('ok', 'COMPLETE');
    consoleChip.textContent = 'done';
    setBusy(false);
    drawHistory(d.index, d.index_ex_festival);

    if (VS.f9 && VS.f9.onComplete) {
      const pr = (d.index_detail && d.index_detail.per_route && d.index_detail.per_route[0]) || {};
      VS.f9.onComplete({
        runId: (d.run_id || '').slice(0, 8), corridor: s.corridor, index: d.index,
        exf: d.index_ex_festival, k: s.kFactor, excl: d.anomalies || 0,
        lower: f.lower_fence, upper: f.upper_fence,
        fest: fc, festFlags: d.festival_flagged || 0,
        start: s.start, end: s.end, nFares: d.records_ingested || fares.length, imported: true,
        iqr: iqrShape, Pt: pr.Pt, P0: pr.P0, Q0: pr.Q0, priceRelative: d.index_ex_festival,
      });
    }
    hasRun = true; busy = false; unlockBtn();
  }

  VS.runAudit = runAudit;
  // lets the F9 replay scrubber keep the split-flap's animation origin in sync
  // with whatever snapshot is currently on screen
  VS.syncIndex = (v) => { if (isFinite(v)) curIndex = +v; };

  /* paint the readout from the daily-collected APIx (/api/apix/latest) without
     running an audit — the "it's already there" layer shown on page load. */
  VS.showLatest = (d) => {
    if (!d || d.index_value == null || hasRun) return;
    app.classList.add('is-live');
    splitFlapTo(curIndex, d.index_value, 700);
    curIndex = d.index_value;
    flap.classList.remove('punch'); void flap.offsetWidth; flap.classList.add('punch');
    readoutPanel.classList.add('complete');
    if (!reduce) {
      readoutPanel.classList.remove('scan'); void readoutPanel.offsetWidth;
      readoutPanel.classList.add('scan');
      setTimeout(() => readoutPanel.classList.remove('scan'), 800);
    }
    if (VS.fx && VS.fx.rise) VS.fx.rise();
    countUp(exfestVal, d.index_ex_festival != null ? d.index_ex_festival : d.index_value, 600, 2);
    setFestivalChip(d.festival_component);
    metaLine.textContent = metaFor(d.index_value)
      + ` · ${d.routes_matched}/${(d.per_route || []).length || d.routes_matched} routes`
      + (d.provisional ? ' · provisional' : '');
    consoleChip.textContent = 'daily';
    setDot('ok', 'DAILY COLLECTION');
  };

  /* ---- boot cinematic on page load -------------------------
     Land on DORMANT, show the last-collection status, play the
     BIOS reveal, then drop into LIVE with today's collected numbers
     already on screen. ?noboot=1 skips straight to LIVE. */
  VS.boot = async (d) => {
    if (hasRun || app.classList.contains('is-live')) { if (d) VS.showLatest(d); return; }
    const noboot = new URLSearchParams(location.search).has('noboot') || reduce;
    const dc = document.getElementById('console');
    const dim = dc && dc.querySelector('.dim');
    if (dim && d && d.index_value != null) {
      let when = 'today';
      try {
        when = new Date(d.computed_at).toLocaleTimeString('en-GB',
          { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }) + ' IST';
      } catch (e) {}
      dim.textContent = `last collection ${when} · national index ${d.index_value.toFixed(2)} · base 2022 = 100`;
    }
    if (!noboot) await new Promise((r) => setTimeout(r, 1600));

    app.classList.add('is-live');
    if (!noboot) {
      revealPanels();
      setDot('running', 'BOOT');
      VS.clearConsole(); VS.resetClock(); VS.showCursor();
      await VS.runBios();
      await VS.wait(120);
    }
    if (d) VS.showLatest(d);
  };
})();

/* STAGE F5 removed — packet-flow canvas dropped in favour of the connector data-dot. */
window.VS = Object.assign(window.VS || {}, { packets: { start(){}, stop(){}, reset(){} } });
