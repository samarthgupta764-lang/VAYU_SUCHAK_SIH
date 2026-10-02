(function () {
  const API = '';
  const topnav = document.getElementById('topnav');
  const analyticsView = document.getElementById('analyticsView');
  const app = document.getElementById('app');
  let loaded = false;

  function setView(view) {
    app.classList.toggle('view-analytics', view === 'analytics');
    topnav.querySelectorAll('.tn-btn').forEach((b) => {
      const on = b.dataset.view === view;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    const status = document.getElementById('anViewStatus');
    if (view === 'analytics') {
      if (status) status.textContent = 'Analytics view — loading 8 panels…';
      if (!loaded) {
        loaded = true;
        loadCollectionStatus();
        loadRouteOptions();
        loadFareDecomposition();
        loadCarrierComparison();
        loadTimeSeries('daily');
        loadHeatmap();
        loadBacktest();
        setTimeout(() => { if (status) status.textContent = 'Analytics view loaded — 8 panels'; }, 2500);
      } else if (status) {
        status.textContent = 'Analytics view';
      }
    } else if (status) {
      status.textContent = 'Live Audit view';
    }
  }

  topnav.addEventListener('click', (e) => {
    const btn = e.target.closest('.tn-btn');
    if (btn) setView(btn.dataset.view);
  });

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function barRows(counts, total) {
    const entries = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
    if (!entries.length) return '<div class="an-empty">no data yet</div>';
    return entries.map(([k, n]) => {
      const pct = total ? Math.round((100 * n) / total) : 0;
      return `<div class="an-bar-row"><span class="lbl" title="${esc(k)}">${esc(k)}</span>` +
             `<span class="track"><span class="fill" style="width:${pct}%"></span></span>` +
             `<span class="n">${n}</span></div>`;
    }).join('');
  }

  function fmtTs(iso) {
    if (!iso) return '—';
    try { return new Date(iso).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }); }
    catch (e) { return iso; }
  }

  async function loadCollectionStatus() {
    const tiles = document.getElementById('anStatusTiles');
    const srcEl = document.getElementById('anBySource'), srcChip = document.getElementById('anSrcChip');
    const carEl = document.getElementById('anByCarrier'), carChip = document.getElementById('anCarChip');
    const winEl = document.getElementById('anByWindow'), winChip = document.getElementById('anWinChip');
    const runsBody = document.querySelector('#anRunsTable tbody');

    let d;
    try {
      const r = await fetch(API + '/api/collector/status', { cache: 'no-store' });
      if (!r.ok) throw new Error('http ' + r.status);
      d = await r.json();
    } catch (e) {
      tiles.innerHTML = `<div class="an-empty" style="grid-column:1/-1;">collector status unavailable — ${esc(e.message || e)}</div>`;
      runsBody.innerHTML = '<tr><td colspan="5" class="an-empty">—</td></tr>';
      return;
    }

    const days = d.days_toward_backtest || 0;
    const latest = d.latest || {};
    const latestTotal = Object.values(latest.by_source || {}).reduce((a, b) => a + b, 0);

    tiles.innerHTML = [
      { label: 'Total quotes', value: (d.total_quotes || 0).toLocaleString('en-IN'), sub: 'all-time, fare_quotes' },
      { label: 'Routes covered', value: d.routes || 0, sub: 'distinct routes seen' },
      { label: 'Carriers covered', value: d.carriers || 0, sub: '6E/AI/QP/SG/IX + more' },
      { label: 'Back-test days', value: `${days}/30`, sub: days < 30 ? 'still collecting' : 'ready', cls: days < 30 ? 'warn' : 'ok' },
      { label: 'Latest run', value: d.latest_date || '—', sub: (latest.sold_out || 0) + ' sold-out that day' },
    ].map((t) => `<div class="an-tile ${t.cls || ''}"><div class="t-label">${esc(t.label)}</div>` +
                  `<div class="t-value">${esc(t.value)}</div><div class="t-sub">${esc(t.sub)}</div></div>`).join('');

    srcEl.innerHTML = barRows(latest.by_source, latestTotal);
    srcChip.textContent = d.latest_date || '—';
    carEl.innerHTML = barRows(latest.by_carrier, latestTotal);
    carChip.textContent = d.latest_date || '—';
    winEl.innerHTML = barRows(latest.by_window, latestTotal);
    winChip.textContent = d.latest_date || '—';

    const runs = d.recent_runs || [];
    runsBody.innerHTML = runs.length ? runs.map((r) => {
      const ok = r.status === 'ok';
      return `<tr><td>${fmtTs(r.started_at)}</td><td>${esc(r.trigger || '—')}</td>` +
             `<td>${r.routes_count ?? '—'}</td><td>${r.quotes_written ?? '—'}</td>` +
             `<td class="${ok ? 'st-ok' : 'st-fail'}">${esc(r.status || '—')}</td></tr>`;
    }).join('') : '<tr><td colspan="5" class="an-empty">no collector runs recorded yet</td></tr>';
  }

  /* ---- Fare decomposition — base/tax/UDF/convenience/other per carrier --- */
  const fdSelect = document.getElementById('anFdRoute');
  const elSelect = document.getElementById('anElRoute');

  async function loadRouteOptions() {
    try {
      const r = await fetch(API + '/api/routes', { cache: 'no-store' });
      if (!r.ok) return;
      const d = await r.json();
      const sorted = (d.routes || []).slice().sort();
      sorted.forEach((rt) => {
        const o = document.createElement('option'); o.value = rt; o.textContent = rt;
        fdSelect.appendChild(o);
      });
      sorted.forEach((rt) => {
        const o = document.createElement('option'); o.value = rt; o.textContent = rt;
        elSelect.appendChild(o);
      });
      if (sorted.length) { elSelect.value = sorted.includes('DEL-BOM') ? 'DEL-BOM' : sorted[0]; loadElasticity(); }
    } catch (e) { /* selects just stay empty / "All routes" */ }
  }
  fdSelect.addEventListener('change', () => loadFareDecomposition());
  elSelect.addEventListener('change', () => loadElasticity());

  const fmtMoney = (n) => '₹' + Math.round(n).toLocaleString('en-IN');

  async function loadFareDecomposition() {
    const rowsEl = document.getElementById('anFdRows');
    const covEl = document.getElementById('anFdCoverage');
    const route = fdSelect.value;
    let d;
    try {
      const url = API + '/api/fare-decomposition' + (route ? ('?route=' + encodeURIComponent(route)) : '');
      const r = await fetch(url, { cache: 'no-store' });
      if (!r.ok) throw new Error('http ' + r.status);
      d = await r.json();
    } catch (e) {
      rowsEl.innerHTML = `<div class="an-empty">fare decomposition unavailable — ${esc(e.message || e)}</div>`;
      covEl.textContent = '—';
      return;
    }
    const cov = d.coverage || {};
    covEl.textContent = cov.quotes_priced
      ? `${cov.quotes_with_breakdown}/${cov.quotes_priced} quotes (${cov.pct}%) carry a breakdown`
      : 'no priced quotes yet';

    const carriers = (d.carriers || []).slice().sort((a, b) => b.total - a.total);
    if (!carriers.length) {
      rowsEl.innerHTML = `<div class="an-empty">no fare-decomposition data for ${esc(route || 'any route')} yet — only Air India, Akasa and Yatra populate base/tax/UDF</div>`;
      return;
    }
    rowsEl.innerHTML = carriers.map((c) => {
      const total = c.total || (c.base + c.taxes + c.udf + c.convenience_fee + c.other) || 1;
      const seg = (v, cls) => v > 0 ? `<span class="${cls}" style="width:${(100 * v / total).toFixed(2)}%" title="${fmtMoney(v)}"></span>` : '';
      return `<div class="an-fd-row">
        <div class="fd-head">
          <span><span class="fd-carrier">${esc(c.carrier)}</span><span class="fd-n">n=${c.n}</span></span>
          <span class="fd-total">${fmtMoney(c.total)}</span>
        </div>
        <div class="an-fd-bar">
          ${seg(c.base, 'fd-base')}${seg(c.taxes, 'fd-tax')}${seg(c.udf, 'fd-udf')}${seg(c.convenience_fee, 'fd-conv')}${seg(c.other, 'fd-other')}
        </div>
        <div class="fd-sources">base ${fmtMoney(c.base)} · tax ${fmtMoney(c.taxes)}` +
        `${c.udf ? ' · UDF ' + fmtMoney(c.udf) : ''}${c.convenience_fee ? ' · conv ' + fmtMoney(c.convenience_fee) : ''}${c.other ? ' · other ' + fmtMoney(c.other) : ''}` +
        ` · via ${esc((c.sources || []).join(', '))}</div>
      </div>`;
    }).join('');
  }

  /* ---- Lead-time elasticity — avg fare by advance-purchase window ------- */
  async function loadElasticity() {
    const box = document.getElementById('anElChart');
    const chip = document.getElementById('anElChip');
    const route = elSelect.value;
    if (!route) { box.innerHTML = '<div class="an-empty">no routes yet</div>'; return; }
    let d;
    try {
      const r = await fetch(API + '/api/elasticity/' + encodeURIComponent(route), { cache: 'no-store' });
      if (!r.ok) throw new Error('http ' + r.status);
      d = await r.json();
    } catch (e) {
      box.innerHTML = `<div class="an-empty">elasticity unavailable — ${esc(e.message || e)}</div>`;
      chip.textContent = '—';
      return;
    }
    const curve = d.curve || [];
    const totalN = curve.reduce((a, p) => a + (p.n || 0), 0);
    chip.textContent = totalN ? `${totalN} quotes` : '—';
    if (curve.length < 2) {
      box.innerHTML = `<div class="an-empty">not enough advance-purchase windows collected yet for ${esc(route)} — need at least 2, have ${curve.length}</div>`;
      return;
    }

    const W = 640, H = 220, padL = 56, padR = 20, padT = 16, padB = 30;
    const fares = curve.map((p) => p.avg_fare);
    const lo = Math.min(...fares), hi = Math.max(...fares);
    const span = (hi - lo) || 1;
    const yPad = span * 0.15;
    const yMin = lo - yPad, yMax = hi + yPad;
    const x = (i) => padL + (i / (curve.length - 1)) * (W - padL - padR);
    const y = (v) => padT + (1 - (v - yMin) / (yMax - yMin)) * (H - padT - padB);

    const gridLines = [0, 0.5, 1].map((t) => {
      const yy = padT + t * (H - padT - padB);
      const val = yMax - t * (yMax - yMin);
      return `<line class="el-grid" x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}"/>` +
             `<text class="el-ylabel" x="${padL - 30}" y="${yy + 3}">${fmtMoney(val)}</text>`;
    }).join('');

    const linePath = curve.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(p.avg_fare).toFixed(1)}`).join(' ');
    const dots = curve.map((p, i) =>
      `<circle class="el-dot" cx="${x(i).toFixed(1)}" cy="${y(p.avg_fare).toFixed(1)}" r="4"><title>${esc(p.window)}: ${fmtMoney(p.avg_fare)} (n=${p.n})</title></circle>` +
      `<text class="el-xlabel" x="${x(i).toFixed(1)}" y="${H - 8}">${esc(p.window)}</text>` +
      `<text class="el-nlabel" x="${x(i).toFixed(1)}" y="${y(p.avg_fare) - 12}">n=${p.n}</text>`
    ).join('');

    box.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${gridLines}<path class="el-line" d="${linePath}"/>${dots}</svg>`;
  }

  /* ---- Carrier comparison — current basket-wide index per carrier ------- */
  async function loadCarrierComparison() {
    const rowsEl = document.getElementById('anCcRows');
    const chip = document.getElementById('anCcChip');
    let carriers;
    try {
      const r = await fetch(API + '/api/collector/status', { cache: 'no-store' });
      if (!r.ok) throw new Error('http ' + r.status);
      const d = await r.json();
      carriers = Object.keys((d.latest || {}).by_carrier || {});
    } catch (e) {
      rowsEl.innerHTML = `<div class="an-empty">carrier list unavailable — ${esc(e.message || e)}</div>`;
      return;
    }
    if (!carriers.length) { rowsEl.innerHTML = '<div class="an-empty">no carriers collected yet</div>'; return; }

    const results = await Promise.all(carriers.map(async (cr) => {
      try {
        const r = await fetch(API + '/api/apix/latest?scope=' + encodeURIComponent('carrier:' + cr), { cache: 'no-store' });
        if (!r.ok) return null;
        const d = await r.json();
        return { carrier: cr, ...d };
      } catch (e) { return null; }
    }));
    const rows = results.filter((r) => r && r.index_value != null).sort((a, b) => b.index_value - a.index_value);
    if (!rows.length) { rowsEl.innerHTML = '<div class="an-empty">no per-carrier index available yet</div>'; return; }

    chip.textContent = `base 2022 = 100 · ${rows.length} carriers`;
    const maxIdx = Math.max(200, ...rows.map((r) => r.index_value)) * 1.05;
    const basePct = (100 / maxIdx * 100).toFixed(2);
    rowsEl.innerHTML = rows.map((r) => {
      const band = r.index_value < 100 ? 'lo' : r.index_value < 150 ? 'mid' : 'hi';
      const observed = (r.routes_matched || 0) - (r.imputed_count || 0);
      return `<div class="an-cc-row">
        <div class="cc-head"><span class="cc-carrier">${esc(r.carrier)}</span><span class="cc-idx ${band}">${r.index_value.toFixed(2)}</span></div>
        <div class="an-cc-track"><div class="cc-base" style="left:${basePct}%"></div><div class="cc-fill ${band}" style="width:${(100 * r.index_value / maxIdx).toFixed(2)}%"></div></div>
        <div class="cc-sub">${r.n_quotes} quotes · ${observed}/${r.routes_matched} routes observed${r.imputed_count ? ` (${r.imputed_count} imputed)` : ''}</div>
      </div>`;
    }).join('');
  }

  /* ---- APIx time series + CPI overlay — the centerpiece ------------------
     Two series on one date-scaled axis, both rebased to the SAME base
     (2022=100): VAYU's own daily/weekly/monthly APIx (real Laspeyres, from
     compute_point) and MoSPI's published CPI Air Fare (native base 2012=100,
     rebased here using the real 2022 monthly average — the same base year
     our own index freezes P0 at, so the two lines are honestly comparable,
     not just visually overlaid). CPI lags real life by months; VAYU doesn't
     — the gap between the two lines' right edges is real, not a bug. */
  let cpiCache = null;
  async function getRebasedCpi() {
    if (cpiCache) return cpiCache;
    try {
      const r = await fetch(API + '/api/cpi', { cache: 'no-store' });
      if (!r.ok) return (cpiCache = []);
      const d = await r.json();
      const af = d.air_fare || [];
      const y2022 = af.filter((x) => x.month.startsWith('2022')).map((x) => x.index);
      if (!y2022.length) return (cpiCache = []);
      const base2022 = y2022.reduce((a, b) => a + b, 0) / y2022.length;
      cpiCache = af.map((x) => ({
        date: new Date(x.month + '-01T00:00:00Z'), value: (x.index / base2022) * 100, month: x.month,
      }));
    } catch (e) { cpiCache = []; }
    return cpiCache;
  }

  function isoWeekToDate(s) {
    const m = /^(\d{4})-W(\d{2})$/.exec(s || '');
    if (!m) return null;
    const year = +m[1], week = +m[2];
    const simple = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
    const dow = simple.getUTCDay() || 7;
    simple.setUTCDate(simple.getUTCDate() - dow + 1); // Monday of that ISO week
    return simple;
  }
  function periodToDate(freq, period) {
    if (freq === 'daily') return new Date(period + 'T00:00:00Z');
    if (freq === 'weekly') return isoWeekToDate(period);
    return new Date(period + '-01T00:00:00Z');
  }

  async function loadTimeSeries(freq) {
    const box = document.getElementById('anTsChart');
    const chip = document.getElementById('anTsChip');
    let vayu = [];
    try {
      const r = await fetch(API + `/api/apix?scope=overall&freq=${freq}&limit=400`, { cache: 'no-store' });
      if (r.ok) vayu = await r.json();
    } catch (e) { /* chart shows the empty state below */ }

    const vayuPts = vayu
      .map((p) => ({ date: periodToDate(freq, p.period), value: p.index_value, period: p.period, n: p.n_quotes }))
      .filter((p) => p.date && p.value != null)
      .sort((a, b) => a.date - b.date);

    if (!vayuPts.length) {
      box.innerHTML = '<div class="an-empty">no computed index points yet — run the daily collector or an Execute Audit first</div>';
      chip.textContent = '—';
      return;
    }

    const cpiAll = await getRebasedCpi();
    const cpiWindowed = cpiAll.slice(-24); // last 24 published months — the full 141-month history would swamp the chart
    const domainStart = new Date(Math.min(
      cpiWindowed.length ? cpiWindowed[0].date.getTime() : Infinity, vayuPts[0].date.getTime()));
    const domainEnd = new Date(Math.max(
      cpiWindowed.length ? cpiWindowed[cpiWindowed.length - 1].date.getTime() : -Infinity,
      vayuPts[vayuPts.length - 1].date.getTime()));
    chip.textContent = `${vayuPts.length} VAYU point${vayuPts.length === 1 ? '' : 's'}` +
      (cpiWindowed.length ? ` · CPI last ${cpiWindowed.length}/${cpiAll.length} months` : ' · CPI unavailable');

    const W = 720, H = 260, padL = 46, padR = 20, padT = 16, padB = 34;
    const span = (domainEnd - domainStart) || 1;
    const xPos = (d) => padL + ((d - domainStart) / span) * (W - padL - padR);
    const allVals = [...vayuPts.map((p) => p.value), ...cpiWindowed.map((p) => p.value), 100];
    const lo = Math.min(...allVals), hi = Math.max(...allVals);
    const ySpan = (hi - lo) || 1;
    const yPad = ySpan * 0.12;
    const yMin = lo - yPad, yMax = hi + yPad;
    const yPos = (v) => padT + (1 - (v - yMin) / (yMax - yMin)) * (H - padT - padB);

    const gridLines = [0, 0.5, 1].map((t) => {
      const yy = padT + t * (H - padT - padB);
      const val = yMax - t * (yMax - yMin);
      return `<line class="ts-grid" x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}"/>` +
             `<text class="ts-ylabel" x="${padL - 8}" y="${yy + 3}">${val.toFixed(0)}</text>`;
    }).join('');

    const spanDays = span / 86400000;
    const fmtTick = (d) => (spanDays < 60 ? d.toISOString().slice(5, 10) : d.toISOString().slice(0, 7));
    const nTicks = 5;
    const xLabels = Array.from({ length: nTicks }, (_, i) => {
      const d = new Date(domainStart.getTime() + (i / (nTicks - 1)) * span);
      return `<text class="ts-xlabel" x="${xPos(d).toFixed(1)}" y="${H - 10}">${fmtTick(d)}</text>`;
    }).join('');

    const cpiPath = cpiWindowed.length > 1
      ? cpiWindowed.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xPos(p.date).toFixed(1)} ${yPos(p.value).toFixed(1)}`).join(' ')
      : '';
    const vayuPath = vayuPts.length > 1
      ? vayuPts.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xPos(p.date).toFixed(1)} ${yPos(p.value).toFixed(1)}`).join(' ')
      : '';
    const vayuDots = vayuPts.map((p) =>
      `<circle class="ts-dot" cx="${xPos(p.date).toFixed(1)}" cy="${yPos(p.value).toFixed(1)}" r="4">` +
      `<title>${esc(p.period)}: ${p.value.toFixed(2)} (n=${p.n})</title></circle>`
    ).join('');
    const soloNote = vayuPts.length === 1
      ? `<text class="ts-note" x="${(xPos(vayuPts[0].date) + 10).toFixed(1)}" y="${(yPos(vayuPts[0].value) - 10).toFixed(1)}">first observation</text>`
      : '';

    box.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${gridLines}${xLabels}` +
      (cpiPath ? `<path class="ts-cpi" d="${cpiPath}"/>` : '') +
      (vayuPath ? `<path class="ts-vayu" d="${vayuPath}"/>` : '') +
      `${vayuDots}${soloNote}</svg>`;
  }

  document.querySelectorAll('#anTsFreq button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#anTsFreq button').forEach((b) => {
        const on = b === btn;
        b.classList.toggle('on', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      loadTimeSeries(btn.dataset.freq);
    });
  });

  /* ---- Sector-wise heatmap — every route's latest index + day-over-day
     delta. "Week-over-week" is the spec's word for this, but with 2 days
     of real collection so far a week-over-week comparison would just be
     fabricated — labelled honestly as day-over-day; the label upgrades
     itself once >=7 days exist. ------------------------------------------ */
  function heatColor(t) {
    t = Math.max(0, Math.min(1, t));
    const stops = [[63, 185, 80], [210, 153, 34], [248, 81, 73]]; // green -> amber -> red
    const seg = t < 0.5 ? 0 : 1;
    const lt = t < 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
    const a = stops[seg], b = stops[seg + 1];
    return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * lt)).join(',')})`;
  }

  async function loadHeatmap() {
    const grid = document.getElementById('anHmGrid');
    const chip = document.getElementById('anHmChip');
    let routes;
    try {
      const r = await fetch(API + '/api/routes', { cache: 'no-store' });
      if (!r.ok) throw new Error('http ' + r.status);
      routes = ((await r.json()).routes || []).slice().sort();
    } catch (e) {
      grid.innerHTML = `<div class="an-empty">route list unavailable — ${esc(e.message || e)}</div>`;
      return;
    }
    if (!routes.length) { grid.innerHTML = '<div class="an-empty">no routes in the basket yet</div>'; return; }

    const results = await Promise.all(routes.map(async (rt) => {
      try {
        const r = await fetch(API + `/api/apix?scope=${encodeURIComponent('route:' + rt)}&freq=daily&limit=2`, { cache: 'no-store' });
        if (!r.ok) return null;
        const pts = (await r.json()).filter((p) => p.index_value != null);
        if (!pts.length) return null;
        const latest = pts[pts.length - 1];
        const prev = pts.length > 1 ? pts[pts.length - 2] : null;
        // route-scoped now means exactly that route (fixed 2026-09-11 — used
        // to silently nowcast-fabricate the other 31 basket routes into this
        // number). imputed_count>0 here can only mean THIS route itself had
        // no clean quote and was nowcast-filled — surface that, band and all.
        const band = (latest.imputed_bands || {})[rt] || null;
        return {
          route: rt, idx: latest.index_value,
          delta: prev ? +(latest.index_value - prev.index_value).toFixed(2) : null,
          imputed: (latest.imputed_count || 0) > 0, band,
        };
      } catch (e) { return null; }
    }));
    const cells = results.filter(Boolean);
    if (!cells.length) { grid.innerHTML = '<div class="an-empty">no per-route index available yet</div>'; return; }

    const haveDelta = cells.some((c) => c.delta != null);
    chip.textContent = `${cells.length}/${routes.length} routes · ${haveDelta ? 'day-over-day Δ' : 'single day — no Δ yet'} · base 2022=100`;

    const vals = cells.map((c) => c.idx);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const spanV = (hi - lo) || 1;

    grid.innerHTML = cells.map((c) => {
      const t = (c.idx - lo) / spanV;
      const color = heatColor(t);
      // non-colour echo of the same tier the colour encodes — matches the
      // national map's BASE/NEAR/INFLATED legend convention, so the ranking
      // reads without relying on colour perception alone.
      const tier = t < 0.34 ? 'below basket avg' : t < 0.67 ? 'near basket avg' : 'above basket avg';
      const dCls = c.delta == null ? 'flat' : c.delta > 0.05 ? 'up' : c.delta < -0.05 ? 'down' : 'flat';
      const dTxt = c.delta == null ? 'no Δ yet' : `${c.delta > 0 ? '▲' : c.delta < 0 ? '▼' : '·'} ${Math.abs(c.delta).toFixed(2)}`;
      const bandTxt = c.band ? `~₹${Math.round(c.band.lower)}–${Math.round(c.band.upper)}` : '';
      const titleSuffix = c.imputed ? `, nowcast-imputed (no clean quote this period)${c.band ? ', 80% band ' + bandTxt : ''}` : '';
      return `<div class="an-hm-cell" style="border-left-color:${color};background:${color.replace('rgb', 'rgba').replace(')', ',0.12)')}" ` +
        `title="${esc(c.route)}: ${c.idx.toFixed(1)}, ${tier}${titleSuffix}">` +
        `<div class="hm-route">${esc(c.route)}${c.imputed ? ' <span class="hm-imp-badge" aria-label="nowcast-imputed, not a real observed quote">~imputed</span>' : ''}</div>` +
        `<div class="hm-idx">${c.idx.toFixed(1)}</div>` +
        `<div class="hm-tier">${tier}</div>` +
        (c.imputed && c.band ? `<div class="hm-band">80% band: ${bandTxt}</div>` : '') +
        `<div class="hm-delta ${dCls}">${dTxt}</div>` +
      `</div>`;
    }).join('');
  }

  /* ---- Back-test — APIx vs MoSPI CPI Air Fare -----------------------------
     Two independent renders (live + historical), matching /api/backtest's
     own shape: the live section is the real validation and is honestly
     near-empty until the collector has run through a full calendar month;
     the historical section is method-demonstration-only (2022 Kaggle
     corpus, no true scrape date) and is rendered visibly de-emphasized with
     its own badge — never presented with equal confidence to the live one. */
  function pct(v) { return v == null ? '—' : (100 * v).toFixed(0) + '%'; }
  function corr(v) { return v == null ? '—' : v.toFixed(2); }

  function renderBtBlock(d) {
    if (!d.months || !d.months.length) {
      return `<div class="an-empty">${esc(d.note || 'no overlapping months yet')}</div>`;
    }
    const stats = `<div class="an-bt-stats">` +
      `<div class="an-tile"><div class="t-label">Months compared</div><div class="t-value">${d.n_months}</div></div>` +
      `<div class="an-tile"><div class="t-label">MoM correlation</div><div class="t-value">${corr(d.mom_correlation)}</div></div>` +
      `<div class="an-tile ${d.direction_agreement != null && d.direction_agreement >= 0.5 ? 'ok' : ''}"><div class="t-label">Direction agreement</div><div class="t-value">${pct(d.direction_agreement)}</div></div>` +
    `</div>`;
    const rows = d.months.map((m, i) =>
      `<div class="bt-row"><b>${esc(m)}</b><span class="apix">VAYU ${d.apix[i].toFixed(2)}</span><span class="cpi">CPI ${d.cpi_air_fare[i].toFixed(2)}</span></div>`
    ).join('');
    return stats + `<div class="an-bt-months">${rows}</div><div class="an-bt-note">${esc(d.note || '')}</div>`;
  }

  async function loadBacktest() {
    const liveEl = document.getElementById('anBtLive'), liveChip = document.getElementById('anBtLiveChip');
    const histEl = document.getElementById('anBtHist');
    let d;
    try {
      const r = await fetch(API + '/api/backtest', { cache: 'no-store' });
      if (!r.ok) throw new Error('http ' + r.status);
      d = await r.json();
    } catch (e) {
      liveEl.innerHTML = histEl.innerHTML = `<div class="an-empty">back-test unavailable — ${esc(e.message || e)}</div>`;
      return;
    }
    const live = d.live || {}, hist = d.historical || {};
    liveChip.textContent = `${live.n_months || 0} month(s)`;
    liveEl.innerHTML = renderBtBlock(live);
    histEl.innerHTML = renderBtBlock(hist);
  }

  /* ---- API explorer — every public GET endpoint, live and try-able ------
     Not a mock: Run actually fires the request against this same backend
     and shows the real response. {route}/{run_id}-style path params are
     substituted before the call; everything else is a query param. */
  const API_ENDPOINTS = [
    { path: '/api/corridors', desc: 'route basket + base period', params: [] },
    { path: '/api/routes', desc: 'basket + base-year P0/Q0', params: [] },
    { path: '/api/collector/status', desc: 'daily-collector health', params: [] },
    { path: '/api/ml/status', desc: 'integrity + nowcast model eval', params: [] },
    { path: '/api/cpi', desc: 'MoSPI CPI air fare + transport series', params: [] },
    { path: '/api/backtest', desc: 'APIx vs CPI Air Fare validation', params: [] },
    { path: '/api/quotes', desc: 'raw fare_quotes rows', params: [
      { name: 'route', value: 'DEL-BOM' }, { name: 'limit', value: '20' } ] },
    { path: '/api/apix', desc: 'the index time series', params: [
      { name: 'scope', value: 'overall' }, { name: 'freq', value: 'daily' }, { name: 'limit', value: '20' } ] },
    { path: '/api/apix/latest', desc: 'most recent computed point', params: [
      { name: 'scope', value: 'overall' } ] },
    { path: '/api/elasticity/{route}', desc: 'lead-time (APW) curve', params: [
      { name: 'route', value: 'DEL-BOM', isPath: true } ] },
    { path: '/api/fare-decomposition', desc: 'base/tax/UDF/convenience split', params: [
      { name: 'route', value: 'DEL-BOM' } ] },
  ];

  function renderApiExplorer() {
    const box = document.getElementById('anApiRows');
    box.innerHTML = API_ENDPOINTS.map((ep, i) => `
      <div class="an-api-row" id="apiRow${i}">
        <button type="button" class="an-api-head" data-i="${i}" aria-expanded="false" aria-controls="apiBody${i}">
          <span class="an-api-method">GET</span>
          <span class="an-api-path">${esc(ep.path)}</span>
          <span class="an-api-desc">${esc(ep.desc)}</span>
        </button>
        <div class="an-api-body" id="apiBody${i}">
          <div class="an-api-params">
            ${ep.params.map((p) => `<div class="an-api-param"><label for="apiParam${i}-${esc(p.name)}">${esc(p.name)}</label>` +
              `<input type="text" id="apiParam${i}-${esc(p.name)}" data-i="${i}" data-p="${esc(p.name)}" value="${esc(p.value)}"></div>`).join('')}
            <div class="an-api-param" style="justify-content:flex-end;">
              <span aria-hidden="true" style="height:12px;"></span>
              <button class="an-api-run" data-i="${i}" aria-label="Run GET ${esc(ep.path)}">▶ Run</button></div>
          </div>
          <div class="an-api-url" id="apiUrl${i}"></div>
          <pre class="an-api-resp" id="apiResp${i}" aria-live="polite">not run yet</pre>
        </div>
      </div>`).join('');

    box.querySelectorAll('.an-api-head').forEach((h) => {
      h.addEventListener('click', () => {
        const open = document.getElementById('apiRow' + h.dataset.i).classList.toggle('open');
        h.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    });
    box.querySelectorAll('.an-api-run').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const i = +btn.dataset.i;
        const ep = API_ENDPOINTS[i];
        let path = ep.path;
        const qs = new URLSearchParams();
        box.querySelectorAll(`input[data-i="${i}"]`).forEach((inp) => {
          const p = ep.params.find((x) => x.name === inp.dataset.p);
          if (!inp.value) return;
          if (p && p.isPath) path = path.replace('{' + p.name + '}', encodeURIComponent(inp.value));
          else qs.set(inp.dataset.p, inp.value);
        });
        const url = API + path + (qs.toString() ? '?' + qs.toString() : '');
        document.getElementById('apiUrl' + i).textContent = 'GET ' + url;
        const respEl = document.getElementById('apiResp' + i);
        respEl.textContent = 'running…';
        try {
          const r = await fetch(url, { cache: 'no-store' });
          const text = await r.text();
          let pretty = text;
          try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch (err) { /* not JSON, show raw */ }
          respEl.textContent = `HTTP ${r.status}\n\n` + pretty;
        } catch (err) {
          respEl.textContent = 'request failed — ' + (err.message || err);
        }
      });
    });
  }
  renderApiExplorer();
})();
