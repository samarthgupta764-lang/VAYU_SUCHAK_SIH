/* ============================================================
   STAGE F8 — optional FX: synthesised sound, glitch-on-error,
   CRT console. All off by default (glitch on), session-persisted.
   window.VS.fx = { tick, rise, chime, buzz, glitch }
   ============================================================ */
(function () {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const liveConsole = document.getElementById('liveConsole');
  const hint = document.getElementById('fxHint');

  // internal flags — no settings UI. sound off (M toggles), glitch-on-error on.
  let soundOn = false;
  const glitchOn = true;
  try { if (new URLSearchParams(location.search).get('crt') === '1' && liveConsole) liveConsole.classList.add('crt'); } catch {}

  /* ---- web audio synth (lazy) -------------------------- */
  let ac = null;
  function ctx() {
    if (!ac) { try { ac = new (window.AudioContext || window.webkitAudioContext)(); } catch { ac = false; } }
    if (ac && ac.state === 'suspended') ac.resume();
    return ac || null;
  }
  function blip(freq, dur, type, gain) {
    const c = ctx(); if (!c) return;
    const o = c.createOscillator(), g = c.createGain();
    o.type = type || 'triangle'; o.frequency.value = freq;
    g.gain.value = 0; o.connect(g); g.connect(c.destination);
    const t = c.currentTime;
    g.gain.linearRampToValueAtTime(gain || 0.04, t + 0.008);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.start(t); o.stop(t + dur + 0.02);
  }
  function sweep(f0, f1, dur, gain) {
    const c = ctx(); if (!c) return;
    const o = c.createOscillator(), g = c.createGain();
    o.type = 'sine'; o.frequency.setValueAtTime(f0, c.currentTime);
    o.frequency.exponentialRampToValueAtTime(f1, c.currentTime + dur);
    g.gain.value = 0; o.connect(g); g.connect(c.destination);
    const t = c.currentTime;
    g.gain.linearRampToValueAtTime(gain || 0.03, t + 0.05);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.start(t); o.stop(t + dur + 0.02);
  }

  const fx = {
    tick(fallback) { if (soundOn) blip(fallback ? 320 : 1180 + Math.random() * 120, 0.05, 'square', 0.02); },
    rise() { if (soundOn) sweep(300, 780, 0.7, 0.028); },
    chime() { if (soundOn) { blip(660, 0.16, 'sine', 0.05); setTimeout(() => blip(988, 0.28, 'sine', 0.045), 120); } },
    buzz() { if (soundOn) blip(110, 0.28, 'sawtooth', 0.05); },
    glitch(el) {
      if (!glitchOn || reduce || !el) return;
      el.classList.remove('glitching'); void el.offsetWidth; el.classList.add('glitching');
      setTimeout(() => el.classList.remove('glitching'), 600);
    },
  };
  window.VS = Object.assign(window.VS || {}, { fx });

  /* ---- M key = sound toggle -------------------------- */
  function showHint(txt) {
    if (!hint) return;
    hint.textContent = txt; hint.hidden = false;
    hint.style.animation = 'none'; void hint.offsetWidth; hint.style.animation = '';
  }
  document.addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === 'm' || e.key === 'M') {
      soundOn = !soundOn;
      showHint(soundOn ? '♪ sound on' : '♪ sound off');
      if (soundOn) fx.chime();
    }
    if (e.key === 'p' || e.key === 'P') {
      const on = document.body.classList.toggle('present');
      showHint(on ? '▣ presentation mode on' : '▣ presentation mode off');
    }
  });
  if (/[?&]present=1\b/.test(location.search)) document.body.classList.add('present');

  /* ---- glitch the console on error state -------------- */
  const cmdDot = document.querySelector('.command-bar .dot');
  if (cmdDot) {
    new MutationObserver(() => {
      if (cmdDot.classList.contains('err')) {
        const panel = liveConsole && liveConsole.closest('.panel');
        fx.glitch(panel); fx.buzz();
      }
    }).observe(cmdDot, { attributes: true, attributeFilter: ['class'] });
  }
})();
