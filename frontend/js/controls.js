/* ============================================================
   STAGE F2 — controls + command-bar keyboard. State only, no pipeline.
   ============================================================ */
(function () {
  const $  = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));

  const corridorEl = $('#corridor');
  const dateEls    = $$('input[type="date"]');
  const kEl        = $('#kfactor');
  const kValEl     = $('.kval');
  const btn        = $('#execute');
  const glyphEl    = btn.querySelector('.glyph');
  const labelEl    = btn.querySelector('.btn-label');
  const debugEl    = $('#f2Debug');
  const cmdDot     = $('.command-bar .dot');
  const cmdTxt     = $('.command-bar .status-txt');

  const norm = (v) => v.replace(/\s*[–-]\s*/, '-');

  // default date range = today -> +29 days (real "now", not a fixed demo
  // month) — the Diwali/Nov/Q4 chips stay below for jumping to those windows.
  const isoLocal = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  if (!dateEls[0].value || !dateEls[1].value) {
    const today = new Date();
    const in30 = new Date(today.getTime() + 29 * 86400000);
    dateEls[0].value = isoLocal(today);
    dateEls[1].value = isoLocal(in30);
  }

  const state = {
    corridor: norm(corridorEl.value),
    start:    dateEls[0].value,
    end:      dateEls[1].value,
    kFactor:  parseFloat(kEl.value),
  };

  function render() {
    debugEl.textContent =
      `state · ${state.corridor} · ${state.start}→${state.end} · k=${state.kFactor.toFixed(1)}`;
  }

  function paintSlider() {
    const pct = ((kEl.value - kEl.min) / (kEl.max - kEl.min)) * 100;
    kEl.style.background =
      `linear-gradient(to right, var(--green) 0%, var(--green) ${pct}%, var(--surface-2) ${pct}%, var(--surface-2) 100%)`;
  }

  let settingK = false;
  function setK(v) {
    v = Math.min(5, Math.max(0.5, Math.round(v * 2) / 2));
    if (!isFinite(v)) return;
    settingK = true;
    kEl.value = v;
    state.kFactor = v;
    kValEl.textContent = v.toFixed(1);
    paintSlider();
    // let other modules (F6 viz) react — they listen for `input` on #kfactor,
    // which arrow-key / preset changes would otherwise never fire
    kEl.dispatchEvent(new Event('input', { bubbles: true }));
    settingK = false;
    render();
  }

  corridorEl.addEventListener('change', (e) => { state.corridor = norm(e.target.value); render(); });

  /* ---- date range + presets --------------------------------- */
  const drSpan = document.getElementById('drSpan');
  function refreshSpan() {
    const a = new Date(dateEls[0].value), b = new Date(dateEls[1].value);
    const d = Math.round((b - a) / 86400000) + 1;
    if (drSpan) drSpan.textContent = isFinite(d) && d > 0 ? `${d} days` : '—';
  }
  function setRange(from, to, chip) {
    dateEls[0].value = from; dateEls[1].value = to;
    state.start = from; state.end = to;
    document.querySelectorAll('.dr-chip').forEach((c) => c.classList.toggle('on', c === chip));
    refreshSpan(); render();
  }
  const PRESETS = {
    diwali: ['2026-11-01', '2026-11-15'],   // Diwali ~Nov 8, ±7d
    nov:    ['2026-11-01', '2026-11-30'],
    q4:     ['2026-10-01', '2026-12-31'],
  };
  document.querySelectorAll('.dr-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      const p = PRESETS[chip.dataset.preset];
      if (p) setRange(p[0], p[1], chip);
    });
  });
  dateEls[0].addEventListener('change', (e) => { state.start = e.target.value; document.querySelectorAll('.dr-chip').forEach((c) => c.classList.remove('on')); refreshSpan(); render(); });
  dateEls[1].addEventListener('change', (e) => { state.end   = e.target.value; document.querySelectorAll('.dr-chip').forEach((c) => c.classList.remove('on')); refreshSpan(); render(); });
  refreshSpan();

  kEl.addEventListener('input', () => { if (!settingK) setK(parseFloat(kEl.value)); });

  // F4 owns the run lifecycle; F2 just triggers it.
  function execute() {
    if (window.VS && window.VS.runAudit) { window.VS.runAudit(); return; }
    // fallback if F4 not loaded: brief busy flash
    btn.disabled = true; labelEl.textContent = 'Auditing…';
    setTimeout(() => { btn.disabled = false; labelEl.textContent = 'Execute Audit'; }, 1500);
  }
  btn.addEventListener('click', execute);

  window.VS = Object.assign(window.VS || {}, { getState: () => ({ ...state }) });

  function cycleCorridor() {
    corridorEl.selectedIndex = (corridorEl.selectedIndex + 1) % corridorEl.options.length;
    state.corridor = norm(corridorEl.value);
    corridorEl.dispatchEvent(new Event('change', { bubbles: true }));
    render();
  }

  document.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const inField = /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);

    if (e.key === 'Enter' && e.target.tagName !== 'BUTTON' && e.target.type !== 'date') { e.preventDefault(); execute(); }
    else if (e.key === 'ArrowUp'   && !inField) { e.preventDefault(); setK(state.kFactor + 0.5); }
    else if (e.key === 'ArrowDown' && !inField) { e.preventDefault(); setK(state.kFactor - 0.5); }
    else if ((e.key === 'c' || e.key === 'C') && !inField) { cycleCorridor(); }
    // 'M' (sound toggle) is owned solely by F8
  });

  paintSlider();
  render();
})();
