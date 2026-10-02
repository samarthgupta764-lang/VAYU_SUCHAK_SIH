/* ============================================================
   Route controller — origin + dest + swap → keeps #corridor in sync.
   Runs before F2 so #corridor has a value on load.
   ============================================================ */
(function () {
  // the index basket — seeded with a default, replaced by window.__setRoutes()
  // once loadCorridors() has fetched /api/corridors.
  let AIRPORTS = ['DEL', 'BOM', 'BLR', 'CCU', 'GAU', 'HYD', 'MAA'];
  let ROUTES = [
    ['BLR', 'BOM'], ['BLR', 'CCU'], ['BLR', 'DEL'], ['BLR', 'HYD'], ['BLR', 'MAA'],
    ['BOM', 'CCU'], ['BOM', 'DEL'], ['BOM', 'HYD'], ['BOM', 'MAA'], ['CCU', 'DEL'],
    ['CCU', 'HYD'], ['CCU', 'MAA'], ['DEL', 'GAU'], ['DEL', 'HYD'], ['DEL', 'MAA'], ['HYD', 'MAA'],
  ];
  const partners = (a) => ROUTES.filter((r) => r.includes(a)).map((r) => (r[0] === a ? r[1] : r[0]));
  const isRoute  = (o, d) => ROUTES.some((r) => (r[0] === o && r[1] === d) || (r[0] === d && r[1] === o));

  const originEl = document.getElementById('origin');
  const destEl   = document.getElementById('dest');
  const swapEl   = document.getElementById('swapBtn');
  const corrEl   = document.getElementById('corridor');

  const opt = (v) => { const o = document.createElement('option'); o.value = v; o.textContent = v; return o; };
  AIRPORTS.forEach((a) => originEl.appendChild(opt(a)));
  // hidden #corridor: only the modelled routes, both directions
  ROUTES.forEach(([a, b]) => { corrEl.appendChild(opt(`${a}-${b}`)); corrEl.appendChild(opt(`${b}-${a}`)); });

  let syncing = false;

  // rebuild the destination list to the valid partners of the current origin
  function fillDest(keep) {
    const list = partners(originEl.value);
    const want = keep && list.includes(keep) ? keep : list[0];
    destEl.innerHTML = '';
    list.forEach((p) => destEl.appendChild(opt(p)));
    destEl.value = want;
  }

  function commit() {
    corrEl.value = `${originEl.value}-${destEl.value}`;
    corrEl.dispatchEvent(new Event('change', { bubbles: true }));
  }

  originEl.value = 'DEL';
  fillDest('BOM');

  originEl.addEventListener('change', () => {
    if (syncing) return;
    syncing = true; fillDest(destEl.value); commit(); syncing = false;
  });
  destEl.addEventListener('change', () => {
    if (syncing) return;
    syncing = true; commit(); syncing = false;
  });

  let swapTurns = 0;
  swapEl.addEventListener('click', () => {
    if (!isRoute(destEl.value, originEl.value)) return;
    syncing = true;
    const o = originEl.value;
    originEl.value = destEl.value;
    fillDest(o);
    swapEl.style.transform = `rotate(${(swapTurns += 180)}deg)`;
    commit();
    syncing = false;
  });

  // back-sync when #corridor changes elsewhere (C key / map click / F4 setCorridor)
  corrEl.addEventListener('change', () => {
    if (syncing) return;
    const [o, d] = corrEl.value.split('-');
    if (isRoute(o, d)) {
      syncing = true; originEl.value = o; fillDest(d); syncing = false;
    }
  });

  corrEl.value = 'DEL-BOM';

  // let loadCorridors() (F10) swap in the real basket from /api/corridors
  window.__setRoutes = (pairs) => {
    if (!Array.isArray(pairs) || !pairs.length) return;
    ROUTES = pairs.map((p) => (Array.isArray(p) ? p : String(p).split('-')));
    AIRPORTS = [...new Set(ROUTES.flat())].sort();
    const keepO = originEl.value, keepD = destEl.value;
    originEl.innerHTML = '';
    AIRPORTS.forEach((a) => originEl.appendChild(opt(a)));
    corrEl.innerHTML = '';
    ROUTES.forEach(([a, b]) => { corrEl.appendChild(opt(`${a}-${b}`)); corrEl.appendChild(opt(`${b}-${a}`)); });
    originEl.value = AIRPORTS.includes(keepO) ? keepO : AIRPORTS[0];
    syncing = true; fillDest(keepD); syncing = false;
    commit();
  };
})();
