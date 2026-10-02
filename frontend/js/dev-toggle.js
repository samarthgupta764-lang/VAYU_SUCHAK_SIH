/* STAGE F1 — dev toggle (removed at F9). Flips the layout instantly. */
document.getElementById('devToggle').addEventListener('click', () => {
  document.getElementById('app').classList.toggle('is-live');
});
