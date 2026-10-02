(function () {
  const btn = document.getElementById('modeToggle');
  if (!btn) return;
  const dot = btn.querySelector('.mt-dot'), label = btn.querySelector('.mt-label');

  function paint(mode) {
    btn.dataset.mode = mode;
    btn.setAttribute('aria-pressed', mode === 'cache' ? 'true' : 'false');
    label.textContent = mode === 'cache' ? 'Cached data' : 'Live scrape';
    btn.title = mode === 'cache'
      ? "Reading today's already-collected snapshot — no network load on any live source. Click to switch to a live scrape."
      : 'Live scrape hits the real airline/OTA sites. Click to switch to cached data instead.';
  }

  let saved;
  try { saved = localStorage.getItem('vsMode'); } catch (e) { saved = null; }
  paint(saved === 'cache' ? 'cache' : 'live');

  btn.addEventListener('click', () => {
    const next = btn.dataset.mode === 'cache' ? 'live' : 'cache';
    paint(next);
    try { localStorage.setItem('vsMode', next); } catch (e) { /* private mode — fine, just not sticky */ }
  });
})();
