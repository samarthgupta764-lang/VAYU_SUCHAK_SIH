/* ============================================================
   STAGE F10 — live backend glue: corridors, run history.
   (runAudit itself is wired in F4. CSV import stays client-side.)
   ============================================================ */
(function () {
  const API = '';

  /* ---- pull the real basket from /api/corridors and hand it to the
     route controller (F1 owns the origin/dest selects) ---- */
  async function loadCorridors() {
    let data;
    try {
      const r = await fetch(API + '/api/corridors', { cache: 'no-store' });
      if (!r.ok) return;
      data = await r.json();
    } catch (e) { return; }
    const routes = (data.corridors || []).filter((c) => /^[A-Z]{3}-[A-Z]{3}$/.test(c));
    if (!routes.length) return;

    // collapse directed routes -> unordered pairs
    const seen = new Set(), pairs = [];
    routes.forEach((c) => {
      const key = c.split('-').sort().join('-');
      if (!seen.has(key)) { seen.add(key); pairs.push(key.split('-')); }
    });
    window.__vsCorridors = routes;
    if (window.__setRoutes) window.__setRoutes(pairs);
    const cc = document.getElementById('mapCorrCount');
    if (cc) cc.textContent = pairs.length + ' corridors';
  }

  /* ---- seed the history chart + readout from the daily-collected APIx ----
     falls back to past manual runs if no daily series exists yet. */
  async function loadHistory() {
    if (!(window.VS && VS.viz && VS.viz.pushHistory)) return;

    // 1 · the daily APIx time-series (real, from the 6 AM collector)
    let daily = [];
    try {
      const r = await fetch(API + '/api/apix?scope=overall&freq=daily', { cache: 'no-store' });
      if (r.ok) daily = await r.json();
    } catch (e) { /* ignore */ }

    if (Array.isArray(daily) && daily.length) {
      daily.forEach((p) => {
        const idx = Number(p.index_value);
        const exf = p.index_ex_festival != null ? Number(p.index_ex_festival) : idx;
        if (isFinite(idx)) {
          try { VS.viz.pushHistory(idx, exf); } catch (e) {}
          if (VS.f9 && VS.f9._history) VS.f9._history.push({ idx, exf, corr: 'basket' });
        }
      });
    } else {
      // 2 · fallback: past manual audits
      try {
        const r = await fetch(API + '/api/runs?limit=20', { cache: 'no-store' });
        if (!r.ok) return;
        const rows = await r.json();
        if (!Array.isArray(rows) || !rows.length) return;
        rows.slice().reverse().forEach((row) => {
          const idx = Number(row.index_value);
          const exf = row.index_ex_festival != null ? Number(row.index_ex_festival) : idx;
          if (isFinite(idx)) { try { VS.viz.pushHistory(idx, exf); } catch (e) {} }
        });
      } catch (e) { return; }
    }
  }

  /* ---- boot: stay DORMANT until the visitor chooses + presses Execute ----
     Used to auto-paint yesterday's collected index on load (VS.boot /
     VS.showLatest) — deliberately disabled: first open should show a blank
     "choose a route, date range, k, then compute" screen, not a number
     nobody asked for yet. VS.boot/showLatest are left defined (unused) in
     case that's ever wanted back. Only the map's hover data still seeds
     quietly in the background — nothing is painted on screen from it. */
  async function loadLatest() {
    if (!(window.VS && VS.viz && VS.viz.seedFromLatest)) return;
    let d = null;
    try {
      const r = await fetch(API + '/api/apix/latest?scope=overall', { cache: 'no-store' });
      if (r.ok) d = await r.json();
    } catch (e) { /* no data yet — fine, stays DORMANT either way */ }
    if (d) VS.viz.seedFromLatest(d.per_route || []);
    if (VS.viz.routeIndex && window.__renderTicker) window.__renderTicker();
  }

  // loadHistory() and loadLatest() both pre-paint real computed numbers
  // (history chart / ticker+map sub-indices / readout) before the visitor
  // has chosen a route or pressed anything — same call, so both are left
  // out of boot() (functions kept, just unused). Only loadCorridors() runs:
  // it just populates the route dropdowns, nothing computed.
  const boot = () => { loadCorridors(); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
