/* ============================================================
   STAGE F6 — live data-viz: real IQR math, histogram, map corridor
   redraw + sub-index recolour, anomalies table, slider live update.
   window.VS.viz = { iqrFilter, drawHistogram, drawAnomTable,
                     setCorridor, paintArcs }
   ============================================================ */
(function () {
  const VS = window.VS;
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- fare source: a CSV extract, when one is loaded ---------
     importedFares is set by the Import CSV button. activeFares()
     is the fare set the imported-audit histogram + tape run on;
     a live/cache scrape gets its fares from the backend instead. */
  const MIN_FARES = 5;   // floor for a usable import (IQR needs a few quartile points)
  let importedFares = null;
  let importedRows = null;   // [{ price, airline, flight }] — real metadata when the CSV carried it
  const activeFares = () => (importedFares && importedFares.length >= MIN_FARES) ? importedFares : [];
  const isImported = () => !!(importedFares && importedFares.length >= MIN_FARES);
  function setImportedFares(arr, rows) {
    importedFares = (Array.isArray(arr) && arr.length >= MIN_FARES) ? arr.slice() : null;
    importedRows = (importedFares && Array.isArray(rows) && rows.length === arr.length) ? rows.slice() : null;
  }

  function iqrFilter(prices, k) {
    const s = [...prices].sort((a, b) => a - b);
    const q = (p) => {
      const idx = p * (s.length - 1), lo = Math.floor(idx), hi = Math.ceil(idx);
      return s[lo] + (s[hi] - s[lo]) * (idx - lo);
    };
    const Q1 = q(0.25), Q3 = q(0.75), IQR = Q3 - Q1;
    const lower = Q1 - k * IQR, upper = Q3 + k * IQR;
    const clean = prices.filter((p) => p >= lower && p <= upper);
    const anomalies = prices.filter((p) => p < lower || p > upper);
    return {
      Q1, Q3, IQR, lower, upper, clean, anomalies,
      low: anomalies.filter((p) => p < lower).length,
      high: anomalies.filter((p) => p > upper).length,
    };
  }

  /* ---- histogram ------------------------------------------- */
  const N = 16, PLOT_H = 84, BASE_Y = 94, SVG_W = 300;
  const histG = document.getElementById('histBars');
  const fenceLo = document.getElementById('fenceLo');
  const fenceHi = document.getElementById('fenceHi');
  let histRects = null, hMin = 0, hMax = 1;

  /* hover "pop" tooltip — reads the dataset written per-rect in drawHistogram */
  function initHistTip() {
    const tip = document.getElementById('histTip');
    const wrap = histG.closest('.viz-body');
    if (!tip || !wrap) return;
    const place = (rect) => {
      const count = Number(rect.dataset.count || 0);
      if (!count) { tip.classList.remove('show'); return; }
      const lo = Number(rect.dataset.lo).toLocaleString('en-IN');
      const hi = Number(rect.dataset.hi).toLocaleString('en-IN');
      tip.classList.toggle('anom', rect.classList.contains('anom'));
      tip.innerHTML = `₹${lo}–${hi} · <span class="cnt">${count} fare${count === 1 ? '' : 's'}</span>`;
      const wb = wrap.getBoundingClientRect(), rb = rect.getBoundingClientRect();
      tip.style.left = (rb.left + rb.width / 2 - wb.left) + 'px';
      tip.style.top  = (rb.top - wb.top) + 'px';
      tip.classList.add('show');
    };
    histG.addEventListener('mouseover', (e) => { if (e.target.tagName === 'rect') place(e.target); });
    histG.addEventListener('mousemove', (e) => { if (e.target.tagName === 'rect') place(e.target); });
    histG.addEventListener('mouseleave', () => tip.classList.remove('show'));
  }

  function drawHistogram(prices, r) {
    curK = parseFloat(document.getElementById('kfactor').value);
    // robust domain: a bit past each fence, clamped to the real data range.
    // keeps the bulk (Q1..Q3) centred and the fences visible; outliers land in the edge bins.
    const dataMin = Math.min(...prices), dataMax = Math.max(...prices);
    // frame ends just past each fence, so the excluded tail sits right beside it (no lone floating bar)
    hMin = Math.max(dataMin, Math.min(r.lower - 0.4 * r.IQR, r.Q1 - 1.8 * r.IQR));
    hMax = Math.min(dataMax, Math.max(r.upper + 0.4 * r.IQR, r.Q3 + 2 * r.IQR));
    if (hMax - hMin < r.IQR) { hMin = dataMin; hMax = dataMax; }
    const span = hMax - hMin || 1;
    const clamp = (p) => Math.max(hMin, Math.min(hMax - 1e-6, p));

    const bins = new Array(N).fill(0);
    prices.forEach((p) => { bins[Math.floor((clamp(p) - hMin) / span * N)]++; });
    const maxC = Math.max(...bins, 1);
    const bw = SVG_W / N;

    if (!histRects) {
      histG.innerHTML = bins.map((_, i) =>
        `<rect x="${(i * bw + 1).toFixed(1)}" width="${(bw - 2).toFixed(1)}" y="${BASE_Y}" height="0" style="transition:y .32s var(--ease) ${i * 14}ms, height .32s var(--ease) ${i * 14}ms, fill .25s, stroke .25s"/>`).join('');
      histRects = histG.querySelectorAll('rect');
      void histG.getBoundingClientRect();
      initHistTip();
    }
    bins.forEach((c, i) => {
      const h = c ? Math.max(1.5, c / maxC * PLOT_H) : 0;
      const binLo = hMin + i / N * span, binHi = hMin + (i + 1) / N * span;
      const binMid = hMin + (i + 0.5) / N * span;
      const anom = binMid < r.lower || binMid > r.upper;
      const rect = histRects[i];
      rect.setAttribute('y', (BASE_Y - h).toFixed(1));
      rect.setAttribute('height', h.toFixed(1));
      rect.setAttribute('fill', anom ? 'rgba(248,81,73,.42)' : 'rgba(88,166,255,.26)');
      rect.setAttribute('stroke', anom ? '#f85149' : '#58a6ff');
      rect.setAttribute('stroke-width', '0.6');
      rect.classList.toggle('anom', anom);
      rect.dataset.count = c;
      rect.dataset.lo = Math.round(binLo);
      rect.dataset.hi = Math.round(binHi);
    });
    const xForRaw = (p) => (p - hMin) / span * SVG_W;
    const rawLo = xForRaw(r.lower), rawHi = xForRaw(r.upper);
    const lo = Math.max(0, Math.min(SVG_W, rawLo)), hi = Math.max(0, Math.min(SVG_W, rawHi));
    fenceLo.setAttribute('x1', lo); fenceLo.setAttribute('x2', lo);
    fenceHi.setAttribute('x1', hi); fenceHi.setAttribute('x2', hi);
    // hide a fence unless it actually sits inside the plotted range (stops the stray edge line)
    fenceLo.style.opacity = (rawLo > 3 && rawLo < SVG_W - 3) ? '1' : '0';
    fenceHi.style.opacity = (rawHi > 3 && rawHi < SVG_W - 3) ? '1' : '0';
    const fl = document.getElementById('iqrFenceLabel');
    if (fl) fl.textContent = `fence ${Math.max(0, Math.round(r.lower)).toLocaleString('en-IN')}–${Math.round(r.upper).toLocaleString('en-IN')}`;
    const note = document.getElementById('iqrNote'); if (note) note.style.opacity = '0';
    const chip = document.getElementById('iqrChip'); if (chip) chip.textContent = `k=${curK.toFixed(1)}`;
  }

  /* ---- anomalies table --------------------------------------
     Rows come from the backend (anomaly_rows: real airline / flight /
     price / fence-reason / source). Falls back to the price list with
     the carrier column blank if the older payload shape is seen. */
  function drawAnomTable(r) {
    curK = parseFloat(document.getElementById('kfactor').value);
    const body = document.getElementById('anomBody');
    const chip = document.getElementById('anomChip');
    const rows = Array.isArray(r.anomalyRows) && r.anomalyRows.length
      ? r.anomalyRows.slice()
      : [...r.anomalies].map((price) => ({ price }));
    chip.textContent = rows.length;
    if (!rows.length) {
      body.innerHTML = `<tr><td colspan="4" style="color:var(--text-dim);border-left:none">no anomalies at k=${curK.toFixed(1)}</td></tr>`;
      return;
    }
    rows.sort((a, b) => a.price - b.price);
    body.innerHTML = rows.map((row) => {
      const price = row.price;
      const flight = (row.flight || '').toString().trim();
      const al = (row.airline || '').toString().trim();
      const label = flight && al && flight.toUpperCase().startsWith(al.toUpperCase())
        ? flight : [al, flight].filter(Boolean).join('-') || '—';
      const reason = row.reason
        ? row.reason.replace(/_/g, ' ')
        : (price < r.lower ? 'below lower fence' : 'above upper fence');
      const fence = price < r.lower ? r.lower : r.upper;
      return `<tr><td>${label}${row.source ? ` <span style="color:var(--text-dim)">· ${row.source}</span>` : ''}</td>` +
             `<td>${curCorridor.replace('-', '–')}</td>` +
             `<td class="fare">₹${Number(price).toLocaleString('en-IN')}</td>` +
             `<td>${reason} · ${Math.round(fence).toLocaleString('en-IN')}</td></tr>`;
    }).join('');
  }

  /* ---- map: corridor redraw + sub-index recolour --------- */
  // canonical corridor key — the two airport codes, alphabetical, so either
  // travel direction maps to one arc.
  const canonCorr = (name) => String(name || '').toUpperCase().split('-').filter(Boolean).sort().join('-');

  /* ---- generate the corridor arcs from the index basket -----
     One arc per city-pair in base_year_reference.json (16 metro pairs
     across DEL/BOM/BLR/CCU/GAU/HYD/MAA). City coordinates come from the
     <circle class="city"> nodes so positions stay in one place. */
  const CORR_PAIRS = [
    'BLR-BOM','BLR-CCU','BLR-DEL','BLR-HYD','BLR-MAA','BOM-CCU','BOM-DEL','BOM-HYD',
    'BOM-MAA','CCU-DEL','CCU-HYD','CCU-MAA','DEL-GAU','DEL-HYD','DEL-MAA','HYD-MAA',
  ];
  (function buildArcs() {
    const NS = 'http://www.w3.org/2000/svg';
    const gArc = document.getElementById('arcGen');
    const gHit = document.getElementById('arcHitGen');
    if (!gArc || !gHit) return;
    const cityXY = {};
    document.querySelectorAll('.map-body .city').forEach((c) => {
      cityXY[c.dataset.city] = [parseFloat(c.getAttribute('cx')), parseFloat(c.getAttribute('cy'))];
    });
    CORR_PAIRS.forEach((key) => {
      const [a, b] = key.split('-');
      const A = cityXY[a], B = cityXY[b];
      if (!A || !B) return;
      // quadratic curve with a perpendicular bow, ~16% of the span
      const mx = (A[0] + B[0]) / 2, my = (A[1] + B[1]) / 2;
      const dx = B[0] - A[0], dy = B[1] - A[1], len = Math.hypot(dx, dy) || 1;
      const bow = Math.min(46, len * 0.16);
      const cx = (mx - (dy / len) * bow).toFixed(1), cy = (my + (dx / len) * bow).toFixed(1);
      const d = `M${A[0]} ${A[1]} Q${cx} ${cy} ${B[0]} ${B[1]}`;
      const arc = document.createElementNS(NS, 'path');
      arc.setAttribute('class', 'arc');
      arc.setAttribute('data-corridor', key);
      arc.setAttribute('data-d', d);
      arc.setAttribute('d', d);
      gArc.appendChild(arc);
      const hit = document.createElementNS(NS, 'path');
      hit.setAttribute('class', 'arc-hit');
      hit.setAttribute('data-corridor', key);
      hit.setAttribute('d', d);
      gHit.appendChild(hit);
    });
  })();

  const arcs = [...document.querySelectorAll('.map-body .arc')];
  const arcGlow = document.getElementById('arcGlow');
  const arcTravel = document.getElementById('arcTravel');
  const mapPlane = document.getElementById('mapPlane');
  const mapSelLabel = document.getElementById('mapSelLabel');
  /* ---- base-year reference (P0, Q0) per corridor ------------
     Prototype fallback only — the authoritative P0/Q0 come from the
     backend (data/base_year_reference.json via /api/routes and the
     audit result's per_route table). */
  const BASE_REF = {
    'BOM-DEL': { P0: 5323, Q0: 100 }, 'BLR-DEL': { P0: 4500, Q0: 74 },
    'BLR-BOM': { P0: 6191, Q0: 41 },  'CCU-DEL': { P0: 6324, Q0: 52 },
    'DEL-GAU': { P0: 6100, Q0: 23 },
  };
  const baseRef = (name) => BASE_REF[canonCorr(name)] || { P0: 4700, Q0: 50 };
  let curCorridor = 'DEL-BOM', curK = parseFloat(document.getElementById('kfactor').value), travelT = 0;
  // corridors actually audited this session — only these get a real colour + value.
  // key is the canonical arc key (either direction resolves to it).
  const audited = new Set();
  const auditedVal = {};   // canonical corridor -> computed index

  function colorForIndex(v) {
    // green at base, amber ~ +50%, red-hot by ~ +130% (real per-route spread is wide)
    const t = Math.max(0, Math.min(1, (v - 100) / 130));
    const L = (a, b, u) => Math.round(a + (b - a) * u);
    if (t < 0.5) { const u = t / 0.5; return `rgb(${L(63,210,u)},${L(185,153,u)},${L(80,34,u)})`; }
    const u = (t - 0.5) / 0.5; return `rgb(${L(210,248,u)},${L(153,81,u)},${L(34,73,u)})`;
  }

  /* Only the selected corridor is drawn; every other arc is a barely-there
     ghost so the network is present but not noisy. Hovering a ghost lifts it
     (initArcHover) and shows its daily sub-index if one was collected. */
  function paintArcs() {
    arcs.forEach((a) => {
      if (a.classList.contains('active') || a.classList.contains('hovered')) {
        a.style.stroke = ''; a.style.opacity = ''; a.style.strokeDasharray = ''; return;
      }
      a.style.stroke = 'var(--text-dim)';
      a.style.strokeDasharray = '';
      a.style.opacity = '0.05';
    });
  }

  /* ---- corridor arc hover: sub-index pops out as a tooltip ------ */
  (function initArcHover() {
    const tip = document.getElementById('arcTip');
    const wrap = document.querySelector('.map-body');
    if (!tip || !wrap) return;
    const tierOf = (v) => (v - 100 < 15 ? 'near base' : v - 100 < 50 ? 'elevated' : 'inflated');
    const enter = (hit) => {
      const corr = hit.dataset.corridor;
      const visible = arcs.find((a) => a.dataset.corridor === corr);
      if (visible && !visible.classList.contains('active')) {
        visible.classList.add('hovered');
        visible.style.stroke = 'var(--text)';
        visible.style.opacity = '0.55';
      }
      if (audited.has(corr) && isFinite(auditedVal[corr])) {
        const v = auditedVal[corr];
        tip.innerHTML = `<b>${corr.replace('-', '–')}</b> · ${v.toFixed(1)} <span style="color:var(--text-dim)">· ${tierOf(v)} · today’s collection</span>`;
      } else {
        tip.innerHTML = `<b>${corr.replace('-', '–')}</b> <span style="color:var(--text-dim)">· no fares collected today</span>`;
      }
    };
    const move = (e, hit) => {
      const wb = wrap.getBoundingClientRect();
      tip.style.left = (e.clientX - wb.left) + 'px';
      tip.style.top  = (e.clientY - wb.top - 10) + 'px';
      tip.classList.add('show');
    };
    const leave = (hit) => {
      const corr = hit.dataset.corridor;
      const visible = arcs.find((a) => a.dataset.corridor === corr);
      if (visible) visible.classList.remove('hovered');
      paintArcs();
      tip.classList.remove('show');
    };
    document.querySelectorAll('.map-body .arc-hit').forEach((hit) => {
      hit.addEventListener('mouseenter', () => enter(hit));
      hit.addEventListener('mousemove', (e) => move(e, hit));
      hit.addEventListener('mouseleave', () => leave(hit));
    });
  })();

  const rev = (n) => n.split('-').reverse().join('-');

  function setCorridor(name) {
    curCorridor = name;
    const r = rev(name);
    arcs.forEach((a) => {
      a.style.transition = ''; a.style.strokeDasharray = ''; a.style.strokeDashoffset = '';
      a.classList.toggle('active', a.dataset.corridor === name || a.dataset.corridor === r);
    });
    const active = arcs.find((a) => a.dataset.corridor === name || a.dataset.corridor === r);
    if (!active) return;
    // the arc path runs in data-corridor's direction; flip the travelling pulse
    // when the selected route is the reverse of it (e.g. BOM→DEL on the DEL-BOM arc)
    const forward = active.dataset.corridor === name;
    const d = active.getAttribute('data-d');
    arcGlow.setAttribute('d', d);
    arcTravel.setAttribute('d', d);
    arcGlow.classList.remove('on');
    arcTravel.classList.remove('on');
    arcTravel.classList.toggle('reverse', !forward);
    if (mapPlane) {
      mapPlane.classList.remove('fly');
      mapPlane.style.offsetPath = `path("${d}")`;
      mapPlane.classList.toggle('reverse', !forward);
    }
    clearTimeout(travelT);

    const armPlane = () => {
      arcGlow.classList.add('on');
      arcTravel.classList.add('on');
      if (mapPlane) { void mapPlane.getBoundingClientRect(); mapPlane.classList.add('fly'); }
    };
    if (!reduce) {
      const len = active.getTotalLength();
      active.style.transition = 'none';
      active.style.strokeDasharray = len;
      active.style.strokeDashoffset = len;
      void active.getBoundingClientRect();
      active.style.transition = 'stroke-dashoffset 460ms ease-out';
      active.style.strokeDashoffset = '0';
      travelT = setTimeout(() => {
        active.style.transition = ''; active.style.strokeDasharray = ''; active.style.strokeDashoffset = '';
        armPlane();
      }, 480);
    } else {
      armPlane();
    }

    const [c1, c2] = name.split('-');
    document.querySelectorAll('.map-body [data-city]').forEach((el) => {
      el.classList.toggle('on', el.dataset.city === c1 || el.dataset.city === c2);
    });
    if (mapSelLabel) mapSelLabel.textContent = 'selected: ' + name.replace('-', '–');
    // radar pings from the two endpoints
    const ping = document.getElementById('radarPings');
    if (ping) {
      ping.innerHTML = '';
      [c1, c2].forEach((code, k) => {
        const src = document.querySelector(`.city[data-city="${code}"]`);
        if (!src) return;
        const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        c.setAttribute('class', 'radar-ping' + (k ? ' b' : ''));
        c.setAttribute('cx', src.getAttribute('cx'));
        c.setAttribute('cy', src.getAttribute('cy'));
        c.setAttribute('r', '5');
        ping.appendChild(c);
        if (!reduce) { void c.getBoundingClientRect(); c.classList.add('go'); }
      });
    }
    paintArcs();
  }

  function travelRunning(on) {
    arcTravel.classList.toggle('running', on);
    if (mapPlane) mapPlane.classList.toggle('running', on);
  }

  /* ---- k slider ----------------------------------------------
     k is a RUN PARAMETER, not a live control. Moving the slider only
     updates its own readout (F2). The IQR distribution, the anomalies
     table and the index recompute when the operator presses Execute —
     the audit applies whatever k is set at that moment. This mirrors
     the backend: changing k re-filters the already-scraped batch on
     the next run, it never triggers a re-scrape. */
  const kEl = document.getElementById('kfactor');
  kEl.addEventListener('input', () => {
    curK = parseFloat(kEl.value);
    const chip = document.getElementById('iqrChip');
    if (chip && document.getElementById('app').classList.contains('is-live')) chip.textContent = `k=${curK.toFixed(1)} · pending`;
  });

  /* ---- corridor selector -------------------------------- */
  document.getElementById('corridor').addEventListener('change', (e) => {
    setCorridor(e.target.value.replace(/\s*[–-]\s*/, '-'));
  });

  /* ---- Index History chart (built from each completed run) --- */
  const CW = 300, CH = 100, PAD = 10, TOP = 12, BOT = 84;
  const histSvg = document.getElementById('histSvg');
  const hLine   = document.getElementById('historyLine');   // retired: superseded by hSegs (kept so nothing 404s on it)
  const hSegs   = document.getElementById('histSegs');
  const hSegLabels = document.getElementById('histSegLabels');
  const cpiLine = document.getElementById('cpiLine');
  const hDots   = document.getElementById('histDots');
  const hPen    = document.getElementById('chartPen');
  const hSolo   = document.getElementById('histSolo');
  const hNote   = document.getElementById('chartNote');
  const hChip   = document.getElementById('histChip');
  const baseLine = document.getElementById('baseLine');
  const baseTag  = document.getElementById('baseTag');
  const history = [];   // { idx, exf, corr }

  /* real MoSPI CPI "Air Fare (Economy, adult)" — rebased so the base-year
     (2022) average = 100, matching the VAYU index base. Replaces the old
     synthetic drift. */
  let cpiSeries = [];   // [{ month, v }]  ascending, 2022 onward
  (async function loadCPI() {
    try {
      const r = await fetch('/api/cpi'); if (!r.ok) return;
      const raw = (await r.json()).air_fare || [];
      const since = raw.filter((p) => p.month >= '2022-01' && p.index);
      const anchor2022 = since.filter((p) => p.month.startsWith('2022'));
      const base = anchor2022.length
        ? anchor2022.reduce((a, p) => a + p.index, 0) / anchor2022.length
        : (since[0] && since[0].index);
      if (!base) return;
      cpiSeries = since.map((p) => ({ month: p.month, v: (p.index / base) * 100 }));
      drawHistoryChart(false);
    } catch (e) { /* leave the CPI line hidden */ }
  })();

  /* dot hover — delegated on the <g>, survives hDots.innerHTML being replaced each redraw */
  (function initChartTip() {
    const tip = document.getElementById('chartTip');
    const wrap = hDots.closest('.viz-body');
    if (!tip || !wrap) return;
    const place = (dot) => {
      const wb = wrap.getBoundingClientRect(), db = dot.getBoundingClientRect();
      tip.innerHTML = `run ${dot.dataset.run} · <b>${dot.dataset.corr}</b> · ${dot.dataset.idx}`;
      tip.style.left = (db.left + db.width / 2 - wb.left) + 'px';
      tip.style.top  = (db.top - wb.top) + 'px';
      tip.classList.add('show');
    };
    hDots.addEventListener('mouseover', (e) => { if (e.target.tagName === 'circle') place(e.target); });
    hDots.addEventListener('mousemove', (e) => { if (e.target.tagName === 'circle') place(e.target); });
    hDots.addEventListener('mouseleave', () => tip.classList.remove('show'));
  })();

  function drawHistoryChart(animate) {
    const n = history.length;
    const corridorCount = new Set(history.map((h) => h.corr)).size;
    hChip.textContent = n + (n === 1 ? ' run' : ' runs') + (corridorCount > 1 ? ` · ${corridorCount} corridors` : '');
    if (!n) { hLine.style.opacity = 0; hSegs.innerHTML = ''; hSegLabels.innerHTML = ''; cpiLine.setAttribute('points', ''); hDots.innerHTML = ''; hPen.style.opacity = 0; if (hSolo) { hSolo.style.opacity = 0; hSolo.classList.remove('on'); } hNote.style.opacity = 1; hNote.textContent = 'awaiting first audit'; return; }

    // real CPI air-fare line (2022 = 100), drawn full-width as context
    const cpiVals = cpiSeries.map((p) => p.v);
    const vals = history.map((h) => h.idx).concat(cpiVals.length ? cpiVals : []);
    const dMin = Math.min(...vals), dMax = Math.max(...vals);
    const pad = Math.max(1.4, (dMax - dMin) * 0.32);   // focus on the data, keep small moves visible
    const lo = dMin - pad;
    const hi = dMax + pad;
    const span = hi - lo || 1;
    // a single observation sits at "today" (right edge), where the CPI line
    // also ends, so the two are on a shared time axis
    const X = (i) => n === 1 ? CW - PAD : PAD + (i / (n - 1)) * (CW - 2 * PAD);
    const Y = (v) => TOP + (1 - (Math.max(lo, Math.min(hi, v)) - lo) / span) * (BOT - TOP);

    // base=100 gridline — drawn where 100 falls (clamped into view); label shows the real value
    const y100 = Y(100);
    baseLine.setAttribute('y1', y100); baseLine.setAttribute('y2', y100);
    const inRange = 100 >= lo && 100 <= hi;
    baseLine.style.opacity = inRange ? '.6' : '.25';
    baseTag.textContent = inRange ? '100' : (100 < lo ? '↓100' : '↑100');
    baseTag.style.top = ((y100 / CH) * baseTag.parentElement.clientHeight - 5) + 'px';

    // CPI air-fare line — real MoSPI monthly series, full chart width
    if (cpiSeries.length > 1) {
      const cx = (i) => PAD + (i / (cpiSeries.length - 1)) * (CW - 2 * PAD);
      cpiLine.setAttribute('points',
        cpiSeries.map((p, i) => `${cx(i).toFixed(1)},${Y(p.v).toFixed(1)}`).join(' '));
      cpiLine.style.opacity = '.7';
    } else {
      cpiLine.setAttribute('points', ''); cpiLine.style.opacity = '0';
    }

    hDots.innerHTML = history.map((h, i) =>
      `<circle ${animate && i === n - 1 ? 'class="pop" ' : ''}cx="${X(i).toFixed(1)}" cy="${Y(h.idx).toFixed(1)}" r="${i === n - 1 ? 2.6 : 1.7}" fill="#3fb950" ` +
      `data-run="${i + 1}" data-idx="${h.idx.toFixed(2)}" data-corr="${h.corr.replace('-', '–')}"/>`).join('');
    hPen.setAttribute('cx', X(n - 1)); hPen.setAttribute('cy', Y(history[n - 1].idx)); hPen.style.opacity = 1;

    // Each corridor's index is scaled to ITS OWN 2022 base fare, not one shared
    // national number — a DEL-BOM run and a CCU-DEL run are not two samples of
    // the same series. So the line is drawn in same-corridor segments only:
    // a corridor switch breaks the line rather than being plotted as if the
    // index itself moved. hLine (the old single full-width polyline) is retired.
    hLine.style.opacity = 0;
    const segments = [];
    history.forEach((h, i) => {
      if (i > 0 && h.corr === history[i - 1].corr) segments[segments.length - 1].push(i);
      else segments.push([i]);
    });
    const lastSeg = segments[segments.length - 1];

    if (n === 1) {
      hNote.textContent = `first observation · ${history[0].idx.toFixed(2)}`;
      hNote.style.opacity = 1;
      if (hSolo) { hSolo.setAttribute('cx', X(0)); hSolo.setAttribute('cy', Y(history[0].idx)); hSolo.style.opacity = 1; hSolo.classList.toggle('on', !reduce); }
    } else if (lastSeg.length === 1) {
      // the newest run started a corridor with no prior point this session —
      // same "nothing to connect yet" treatment as the very first observation
      hNote.textContent = `first ${history[n - 1].corr.replace('-', '–')} observation · ${history[n - 1].idx.toFixed(2)}`;
      hNote.style.opacity = 1;
      if (hSolo) { hSolo.setAttribute('cx', X(n - 1)); hSolo.setAttribute('cy', Y(history[n - 1].idx)); hSolo.style.opacity = 1; hSolo.classList.toggle('on', !reduce); }
    } else {
      hNote.style.opacity = 0;
      if (hSolo) { hSolo.style.opacity = 0; hSolo.classList.remove('on'); }
    }

    hSegs.innerHTML = segments.filter((s) => s.length > 1).map((s) =>
      `<polyline points="${s.map((i) => `${X(i).toFixed(1)},${Y(history[i].idx).toFixed(1)}`).join(' ')}" ` +
      `fill="none" stroke="#3fb950" stroke-width="2"/>`).join('');

    // corridor tag under each segment (HTML overlay, not SVG text — the chart's
    // viewBox is non-uniformly scaled so SVG <text> would distort). Positioned
    // off histSvg's own rendered box, not hSegLabels' positioning parent
    // (.viz-body), which is taller than the svg alone — it also holds the
    // legend row below the chart, so a naive %-of-parent placement bled down
    // into the legend text instead of sitting at the chart's own bottom edge.
    const wrapBox = hSegLabels.getBoundingClientRect();
    const svgBox = histSvg.getBoundingClientRect();
    const svgLeftPct = ((svgBox.left - wrapBox.left) / wrapBox.width) * 100;
    const svgWidthPct = (svgBox.width / wrapBox.width) * 100;
    const svgTopPct = ((svgBox.top - wrapBox.top) / wrapBox.height) * 100;
    const svgHeightPct = (svgBox.height / wrapBox.height) * 100;
    hSegLabels.innerHTML = segments.map((s) => {
      const mid = s[Math.floor(s.length / 2)];
      const left = (svgLeftPct + (X(mid) / CW) * svgWidthPct).toFixed(1);
      const top = (svgTopPct + (94 / CH) * svgHeightPct).toFixed(1);
      return `<span style="position:absolute;left:${left}%;top:${top}%;transform:translateX(-50%);` +
        `font-family:var(--font-mono);font-size:7px;color:var(--text-dim);opacity:.6;white-space:nowrap;">` +
        `${history[mid].corr.replace('-', '–')}</span>`;
    }).join('');

    if (animate && !reduce && !document.hidden && lastSeg.length > 1) {
      const segEl = hSegs.lastElementChild;
      if (segEl) {
        const len = segEl.getTotalLength();
        segEl.style.transition = 'none';
        segEl.style.strokeDasharray = len; segEl.style.strokeDashoffset = len;
        void segEl.getBoundingClientRect();
        segEl.style.transition = 'stroke-dashoffset 520ms ease-out';
        segEl.style.strokeDashoffset = 0;
      }
    }
    hPen.classList.remove('draw'); void hPen.getBoundingClientRect(); hPen.classList.add('draw');
  }

  function pushHistory(idx, exf) {
    history.push({ idx, exf, corr: curCorridor });
    if (history.length > 24) history.shift();
    drawHistoryChart(true);
  }

  /* ---- fare tape (top ticker) + audit commit ---------------
     After an imported-CSV audit, build a per-fare tape for the
     corridor from the same fare set the IQR filter ran on, marking
     which fares the fence excluded. Airline / flight come from the
     CSV when it carried those columns. A live scrape feeds the
     ticker from the daily per-route APIx instead (routeIndex). */
  let fareTape = null;   // [{ al, fno, price, excl, tier }]
  let routeIndex = [];   // [{ route, rel, Pt }] — daily APIx per-route, for the ticker + map
  function commitAudit(corridor, sim) {
    const key = canonCorr(corridor);
    audited.add(key);
    auditedVal[key] = sim.index;
    const r = sim.iqr;
    const prices = activeFares();
    const meta = importedRows || [];
    const bySorted = meta.length === prices.length ? [...meta].sort((a, b) => a.price - b.price) : null;
    fareTape = [...prices].sort((a, b) => a - b).map((p, i) => {
      let tier = 'green';                                  // inside the inter-quartile band
      if (r) {
        if (p < r.lower || p > r.upper) tier = 'red';      // outside the fence — excluded
        else if (p < r.Q1 || p > r.Q3) tier = 'amber';     // in the tails, still counted
      }
      const m = bySorted && bySorted[i];
      return {
        al: (m && (m.airline || '').trim()) || '—',
        fno: (m && (m.flight || '').trim()) || '',
        price: p,
        excl: tier === 'red',
        tier,
      };
    });
    // integrity tile — share of fares inside the fence
    const integ = document.querySelector('[data-tile="integrity"]');
    if (integ && r) {
      const pct = (100 * r.clean.length / (r.clean.length + r.anomalies.length));
      integ.textContent = pct.toFixed(1);
      integ.classList.remove('flash'); void integ.offsetWidth; integ.classList.add('flash');
    }
    paintArcs();
    // lock-in pulse on the audited corridor
    if (!reduce) {
      const act = arcs.find((a) => a.classList.contains('active'));
      if (act) { act.classList.remove('locked'); void act.getBoundingClientRect(); act.classList.add('locked'); }
    }
  }

  /* Build the top-ticker fare tape from a live scrape's own fares (this
     corridor only). rows: [{airline, flight, price, source}] kept + excluded;
     fences: {lower, upper, Q1, Q3}. */
  function setRunTape(corridor, keptRows, exclRows, fences) {
    const key = canonCorr(corridor);
    audited.add(key);
    const tag = (p) => {
      if (!fences) return 'green';
      if (p < fences.lower || p > fences.upper) return 'red';
      if (p < fences.Q1 || p > fences.Q3) return 'amber';
      return 'green';
    };
    const mk = (row, excluded) => ({
      al: (row.airline || '').toString().trim() || '—',
      fno: (row.flight || '').toString().trim(),
      src: (row.source || '').toString().trim(),
      price: row.price,
      excl: excluded,
      tier: excluded ? 'red' : tag(row.price),
    });
    fareTape = (keptRows || []).map((r) => mk(r, false))
      .concat((exclRows || []).map((r) => mk(r, true)))
      .sort((a, b) => a.price - b.price);
    paintArcs();
  }

  /* ---- expose + initial state -------------------------------
     Nothing is drawn until the first Execute — the IQR panel and the
     map start empty so no number on screen is uncomputed. */
  VS.viz = {
    iqrFilter, drawHistogram, drawAnomTable, setCorridor, paintArcs,
    travelRunning, pushHistory, drawHistoryChart, commitAudit, setRunTape,
    activeFares, isImported, setImportedFares,
    importedRows: () => importedRows,
    fareTape: () => fareTape,
    auditedCount: () => audited.size,
    historyLen: () => history.length,
    // base-year reference (P0, Q0) per corridor — the denominator of the index
    baseRef: (corr) => ({ ...baseRef(corr) }),
    setSubIndex: (corr, v) => { auditedVal[canonCorr(corr)] = v; audited.add(canonCorr(corr)); paintArcs(); },
    // seed every arc + the ticker from the daily APIx per-route table
    seedFromLatest: (perRoute) => {
      if (!Array.isArray(perRoute)) return;
      routeIndex = perRoute.map((r) => ({ route: r.route, rel: r.rel, Pt: r.Pt }));
      perRoute.forEach((r) => {
        const k = canonCorr(r.route);
        if (isFinite(r.rel)) { auditedVal[k] = r.rel; audited.add(k); }
      });
      paintArcs();
    },
    routeIndex: () => routeIndex,
    get curCorridor() { return curCorridor; },
    get curK() { return curK; },
  };

  paintArcs();
  setCorridor('DEL-BOM');
})();
