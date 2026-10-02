# frontend/ — VAYU-SUCHAK 2.0 dashboard

`index.html` is the single-page operator console (design + stages in
`../docs/frontend-build-plan.md`). No build step — open it or let the backend
serve it at `GET /`.

## Current state

The prototype currently runs a **self-contained simulation**: `runAudit()` →
`simulate()` reimplements IQR / Laspeyres / festival in JS and animates fake
stage lines. It does **not** yet call the backend.

## Wiring it to the live backend (a frontend-plan task)

Replace the `simulate()` path in `runAudit()` with an `EventSource`:

```js
const q = new URLSearchParams({ corridor, start, end, k_factor, mode: 'auto' });
const es = new EventSource(`/api/execute-audit?${q}`);
es.onmessage = (e) => {
  const d = JSON.parse(e.data);              // {stage, message, ...}
  appendLine(`[${d.stage}] ${d.message}`);
  if (d.done) {                              // final line
    showIndexBig(d.index, d.index_ex_festival);
    refreshHistoryChart();                   // GET /api/runs
    es.close();
  }
};
```

### Backend contract (see `../backend/README.md`)

| Endpoint | Use |
|---|---|
| `GET /api/corridors` | populate the corridor `<select>` |
| `GET /api/execute-audit?corridor&start&end&k_factor&mode` | SSE run stream |
| `GET /api/runs?corridor&limit` | history chart |
| `POST /api/import-csv` (multipart `file`) | CSV import path → JSON result |
| `GET /api/report/{run_id}` | PDF report data |

SSE stages, in order: `SYSTEM · INGEST · FESTIVAL · IQR · INTEGRITY · NOWCAST ·
LASPEYRES · DB · EXPLAIN · SYSTEM(done)`. The final `SYSTEM` line carries
`done:true, index, index_ex_festival, festival_component, anomalies, ml_flagged,
imputed, ingestion_source, db_target, annotation`.
