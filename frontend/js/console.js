/* ============================================================
   STAGE F3 — console renderer.
   window.VS.appendLine / runBios / cursor helpers — F4 drives these.
   ============================================================ */
(function () {
  const consoleEl = document.querySelector('#liveConsole');
  const app = document.getElementById('app');
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  const TAG_CLASS = {
    SYSTEM: 't-system', SOURCE: 't-ingest', INGEST: 't-ingest', FESTIVAL: 't-festival',
    IQR: 't-iqr', INTEGRITY: 't-integrity', NOWCAST: 't-nowcast',
    LASPEYRES: 't-laspeyres', DB: 't-db',
  };

  let runT0 = performance.now();
  const stamp = () => `[+${((performance.now() - runT0) / 1000).toFixed(2)}s] `;

  function clearConsole() { consoleEl.innerHTML = ''; }
  function removeCursor() { const c = consoleEl.querySelector('.cursor-line'); if (c) c.remove(); }
  function showCursor() {
    removeCursor();
    const c = document.createElement('div');
    c.className = 'cursor-line';
    c.innerHTML = '<span class="cursor">_</span>';
    consoleEl.appendChild(c);
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }

  function typewrite(el, text) {
    return new Promise((res) => {
      if (document.hidden) { el.textContent = text; consoleEl.scrollTop = consoleEl.scrollHeight; res(); return; }
      const step = Math.max(1, Math.ceil(text.length / 36));
      let i = 0;
      const tick = () => {
        i = Math.min(text.length, i + step);
        el.textContent = text.slice(0, i);
        consoleEl.scrollTop = consoleEl.scrollHeight;
        if (i < text.length) setTimeout(tick, 16); else res();
      };
      tick();
    });
  }

  // appendLine("INGEST", "msg", { fallback, bios, noStamp })
  function appendLine(stage, message, opts = {}) {
    const empty = consoleEl.querySelector('.console-empty');
    if (empty) empty.remove();
    removeCursor();
    if (window.VS && window.VS.fx) window.VS.fx.tick(opts.fallback);

    const line = document.createElement('div');

    if (opts.bios) {
      line.className = 'cline bios';
      line.innerHTML = `<span class="prompt">&gt; </span><span class="msg"></span>`;
      consoleEl.appendChild(line);
      return typewrite(line.querySelector('.msg'), message);
    }

    const base = String(stage).replace(/[[\]]/g, '').split(/[/\s]/)[0].toUpperCase();
    const isFallback = opts.fallback || /FALLBACK/i.test(String(stage));
    line.className = 'cline' + (isFallback ? ' fallback' : '');
    const tagText = isFallback ? `[${base}][FALLBACK]` : `[${base}]`;
    const ts = opts.noStamp ? '' : stamp();
    line.innerHTML =
      `<span class="ts">${ts}</span><span class="prompt">&gt; </span>` +
      `<span class="tag ${TAG_CLASS[base] || 't-system'}">${tagText}</span> ` +
      `<span class="msg"></span>`;
    consoleEl.appendChild(line);
    return typewrite(line.querySelector('.msg'), message);
  }

  async function runBios() {
    const lines = [
      'VAYU-SUCHAK KERNEL',
      'holidays.India(2026) ....... [OK]',
      'scraper.pool handshake ..... [OK]',
      'base_year_reference.json ... [OK]',
      'pipeline.armed',
    ];
    for (const l of lines) { await appendLine(null, l, { bios: true }); showCursor(); await wait(64); }
    removeCursor();
  }

  window.VS = Object.assign(window.VS || {}, {
    appendLine, runBios, clearConsole, showCursor, removeCursor, wait,
    resetClock: () => { runT0 = performance.now(); },
  });

})();
