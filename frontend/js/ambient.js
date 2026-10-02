/* ============================================================
   STAGE F7 — ambient layer + progressive disclosure.
   grid/cursor glow · live clock · DORMANT heartbeat · ticker
   data · telemetry jitter. All gated by prefers-reduced-motion.
   ============================================================ */
(function () {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const app = document.getElementById('app');
  const root = document.documentElement;

  /* ---- cursor glow (throttled) --------------------------- */
  if (!reduce) {
    let ticking = false;
    addEventListener('pointermove', (e) => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        root.style.setProperty('--mx', e.clientX + 'px');
        root.style.setProperty('--my', e.clientY + 'px');
        ticking = false;
      });
    }, { passive: true });
  }

  /* ---- live clock --------------------------------------- */
  const clockTile = document.querySelector('[data-tile="clock"]');
  function nowIST() {
    return new Date().toLocaleTimeString('en-GB', { hour12: false, timeZone: 'Asia/Kolkata' });
  }
  setInterval(() => { if (clockTile) clockTile.textContent = nowIST(); }, 1000);

  /* ---- DORMANT heartbeat — just a clock tick while the boot plays --- */
  const dormConsole = document.querySelector('.dormant-console');
  function heartbeat() {
    if (app.classList.contains('is-live') || !dormConsole) return;
    const cursor = dormConsole.querySelector('.cline:last-child');
    const line = document.createElement('div');
    line.className = 'cline hb';
    line.innerHTML = `<span class="prompt">&gt; </span><span class="dim">${nowIST()} IST · standing by</span>`;
    dormConsole.insertBefore(line, cursor);
    const hbs = dormConsole.querySelectorAll('.cline.hb');
    if (hbs.length > 3) hbs[0].remove();
  }
  setInterval(heartbeat, 4200);

  /* ---- ticker tape = scraped-fare feed for the audited route ----
     Before any audit: a neutral prompt. After an audit: the actual
     fares the pipeline pulled for the selected corridor + window,
     with the ones the IQR fence excluded marked in red. This is the
     raw INPUT to the index — not a fake per-route index board. */
  const track = document.getElementById('tickerTrack');
  const inr = (n) => '₹' + Math.round(n).toLocaleString('en-IN');
  function renderTicker() {
    const tape = (window.VS.viz && window.VS.viz.fareTape) ? window.VS.viz.fareTape() : null;
    const st = (window.VS.getState) ? window.VS.getState() : null;
    if (!tape || !tape.length) {
      // daily APIx per-route sub-index feed (real)
      const ri = (window.VS.viz && window.VS.viz.routeIndex) ? window.VS.viz.routeIndex() : [];
      if (ri.length) {
        const cls = (v) => (v < 115 ? 'down' : v < 150 ? 'mid' : 'excl');
        const arr = (v) => (v >= 100 ? '▲' : '▼');
        const items = ri.slice().sort((a, b) => b.rel - a.rel).map((r) =>
          `<span class="ti"><b>${r.route.replace('-', '–')}</b> ` +
          `<span class="${cls(r.rel)}">${r.rel.toFixed(1)} ${arr(r.rel)}</span></span>`);
        const one = `<span class="ti head">NATIONAL BOARD · per-route index · base 2022 = 100</span>` +
                    items.join('') + `<span class="ti dim">from today’s 06:00 collection · press Execute to scrape one route live</span>`;
        track.innerHTML = one + one;
        track.style.animationDuration = Math.max(60, ri.length * 2) + 's';
        return;
      }
      const one = `<span class="ti head">VAYU-SUCHAK · scraped-fare feed</span>` +
                  `<span class="ti dim">select a route + date range, press Execute — live fares stream here</span>` +
                  `<span class="ti dim">base 2022 = 100</span>`;
      track.innerHTML = one + one;
      return;
    }
    const corr = st ? st.corridor.replace('-', '–') : '';
    const win = st ? `${st.start} → ${st.end}` : '';
    const cls = { green: 'down', amber: 'mid', red: 'excl' };
    const nRed = tape.filter((f) => f.tier === 'red').length;
    const nAmber = tape.filter((f) => f.tier === 'amber').length;
    const feedLabel = (window.VS.viz && window.VS.viz.isImported && window.VS.viz.isImported())
      ? 'IMPORTED FARES' : 'LIVE SCRAPE · this corridor';
    const head = `<span class="ti head">${feedLabel} · <b>${corr}</b> · ${win} · n=${tape.length} · ` +
                 `<span class="down">${tape.length - nRed - nAmber} core</span> · ` +
                 `<span class="mid">${nAmber} tail</span> · <span class="excl">${nRed} excluded</span></span>`;
    const label = (f) => {
      const al = (f.al || '').trim(), fn = (f.fno || '').trim();
      let base = (fn && al && fn.toUpperCase().startsWith(al.toUpperCase())) ? fn
        : [al, fn].filter((x) => x && x !== '—').join('-') || '—';
      return f.src ? `${base} <span class="ti dim">${f.src}</span>` : base;
    };
    const items = tape.map((f) =>
      `<span class="ti"><b>${label(f)}</b> <span class="${cls[f.tier] || 'down'}">${inr(f.price)}${f.excl ? ' ✕' : ''}</span></span>`);
    const one = head + items.join('') + `<span class="ti dim">updated ${nowIST()} IST · base 2022 = 100</span>`;
    track.innerHTML = one + one;   // x2 for the -50% loop
    // scroll speed scales with how much tape there is — ~1.2s per fare, so a
    // ~150-fare feed takes ~3 min for one full pass and stays readable.
    track.style.animation = 'none'; void track.offsetWidth;
    track.style.animation = '';
    track.style.animationDuration = Math.max(60, Math.round(tape.length * 1.2)) + 's';
  }
  window.__renderTicker = renderTicker;
  renderTicker();
  setInterval(() => { if (!app.classList.contains('is-live') || !fareTapeLive()) renderTicker(); }, 15000);
  function fareTapeLive() { const t = window.VS.viz && window.VS.viz.fareTape && window.VS.viz.fareTape(); return t && t.length; }

  /* ---- status tiles ------------------------------------------
     Scrape RTT / Throughput / Queue / Integrity are written only by
     the SSE stream (runAudit setTile()) from real per-stage numbers.
     While a stage is in flight the tile holds its last real value —
     no synthetic jitter. A '·' placeholder shows until the first
     real number arrives. */
  const latEl = document.querySelector('[data-tile="latency"]');
  const thrEl = document.querySelector('[data-tile="throughput"]');
  const qEl   = document.querySelector('[data-tile="queue"]');
  const cmdDot = document.querySelector('.command-bar .dot');
  function startJitter() {
    [latEl, thrEl, qEl].forEach((el) => { if (el && !el.dataset.real) el.textContent = '·'; });
  }
  function stopJitter() {}

  /* ---- one observer on the status dot: ticker refresh once a run settles --- */
  if (cmdDot) {
    let wasRunning = cmdDot.classList.contains('running');
    new MutationObserver(() => {
      const running = cmdDot.classList.contains('running');
      if (running !== wasRunning) {
        wasRunning = running;
        if (running) startJitter();
        else { stopJitter(); setTimeout(renderTicker, 400); }   // pick up the new sub-index once a run settles
      }
    }).observe(cmdDot, { attributes: true, attributeFilter: ['class'] });
  }
})();
