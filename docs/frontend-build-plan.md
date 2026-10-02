# VAYU-SUCHAK 2.0 — Frontend Build Plan (v2 · DORMANT→LIVE)

**Owner:** Anant · **Scope:** the dashboard only (backend build order = engineering deep-dive §10)
**Golden rule:** build one stage, verify against its acceptance test, then move on. Build strictly one stage at a time; do not implement later stages.

---

## 0. Design intent

> **A dormant instrument that boots in front of the judge when you pull the trigger.**

Two ideas drive everything:

1. **DORMANT → LIVE.** Before Execute, the screen is stripped back and calm — wordmark, controls, a dead console, a live ticker. Pressing Execute makes the whole machine *power on*: panels unfold, numbers spin up, the pipeline ignites, data reveals itself stage by stage.
2. **Only data worth showing gets shown.** No panel displays until it has something real to say. Anomalies table stays hidden at zero. The chart says "first observation" on run 1. Fallback badges appear only if a fallback fired.

**The one guardrail:** every animation must mark a *real event* — data arriving, a stage completing, a value changing. That's what makes it defensible in the interview ("each motion is the UI executing a real pipeline step"), not "we added effects." Crazy in *choreography and feedback density*, never gratuitous.

**User-facing surface = 4 controls + 1 button.** Everything else is read-only ambient complexity the operator never touches.

---

## 1. Design DNA (condensed — full profile in the deep-dive doc)

### Colour — every colour is a status, never decoration

| Token | Hex | Meaning |
|---|---|---|
| `--bg` | `#0d1117` | app background |
| `--surface` | `#161b22` | panels |
| `--surface-2` | `#1c2230` | inputs, header rows |
| `--border` | `#30363d` | 1px hairline everywhere |
| `--text` | `#e6edf3` | primary text |
| `--text-dim` | `#8b949e` | secondary text, `[SYSTEM]` tag |
| `--green` `#3fb950` | **VALID / GO** — index, Execute, `[LASPEYRES]`, postgres, VAYU line, near-base map arcs |
| `--blue` `#58a6ff` | **REFERENCE** — `[INGEST]` `[DB]` tags, CPI line, cache badge |
| `--amber` `#d29922` | **ATTENTION / DEVIATION** — `[FESTIVAL]` `[IQR]`, festival chips, `[*][FALLBACK]`, sqlite, mildly-inflated map arcs |
| `--red` `#f85149` | **EXCLUDED / FAILED** — anomaly rows, errors, ejected packets, inflated map arcs |

### Type

| Role | Size | Font / weight |
|---|---|---|
| split-flap index | 76px | Mono 600, tabular-nums |
| readout secondary | 26px | Mono 500 |
| panel title | 19px | Inter 600 |
| app title | 15px | Inter 700 |
| body / control label | 14px | Inter 400/500 |
| console line | 13px | Mono 400 |
| stage tag / ticker | 12px | Mono 600 |
| eyebrow label / command bar | 11px | Mono 600, UPPERCASE, +0.08em |

- UI font `Inter, system-ui, sans-serif` · Data font `'JetBrains Mono', ui-monospace, monospace` — both from Google Fonts with fallbacks.

### Shape / spacing / motion

- Radius **6px**. Borders **1px hairline**. Shadows **flat** — depth via border + contrast. One green glow on completion.
- Spacing unit **4px**. Density **compact**. Panel gap **16px**.
- Easing `cubic-bezier(0.2, 0, 0, 1)` — snappy, mechanical, never bouncy.
- Durations: **120–200ms** UI, **800ms** index count-up, **~5s** full boot sequence.

---

## 2. The two states

### 2.1 DORMANT (before first run)

```
┌ TICKER · DEL–BOM ▲2.1%  BOM–BLR ▼0.4%  DEL–CCU ▲1.8% … (scrolling) ─────┐
│                                                                          │
│                        VAYU-SUCHAK 2.0                                    │
│              Real-time Airfare Price Index · MoSPI                        │
│                                                                          │
│     [Corridor ▾]   [From] [To]   [k_factor ●──── 1.5]   [ ▶ EXECUTE ]    │
│                                                                          │
│   ┌──────────────────────────────────────────────────────────────┐      │
│   │  > VAYU-SUCHAK KERNEL v2.0                                     │      │
│   │  > SYSTEM READY — awaiting audit parameters                    │      │
│   │  _                                                             │      │
│   └──────────────────────────────────────────────────────────────┘      │
│                                                                          │
│  ⏎ execute   ↑↓ k-factor   C corridor                          ● IDLE   │
└──────────────────────────────────────────────────────────────────────────┘
```
- Pipeline, status strip, readout, map, charts, anomalies — **not rendered.**
- Ambient: background grid drifting slowly; status dot breathing; a faint telemetry "heartbeat" tick every ~4s in the console (`> heartbeat · nodes 5/5 · integrity 99.4%`).
- The console is centered and roomy. One clear call to action.

### 2.2 LIVE (during / after a run)

```
┌ TICKER TAPE · 22px ──────────────────────────────────────────────────────┐
┌ HEADER · 52px ·  VAYU-SUCHAK 2.0 … run a1b2c3d4        ● RUNNING          ┐
┌ STATUS STRIP · 40px ·  NODES 5/5 │ LATENCY 48ms │ THROUGHPUT 412 │ … ─────┐
┌ CONTROL BAR · 72px ─────────────────────────────────────────────────────┐
├──────────┬─────────────────┬────────────────┬─────────────────────────┤
│ PIPELINE │  CONSOLE         │  NATIONAL MAP  │  READOUT                │
│ 0.5fr    │  1fr             │  0.85fr        │  0.8fr                  │
│ ① INGEST │  > [SYSTEM] …    │   india SVG    │   ┌─────────────────┐   │
│ ┋(pulse) │  > [INGEST] …    │   + corridor   │   │ 1  1  8 . 7  5  │   │  split-flap
│ ② FEST   │  > [FESTIVAL]…   │   arcs, glow,  │   └─────────────────┘   │
│ ┋        │  > [IQR] …       │   recoloured   │   ex-festival 116.40    │
│ ③ IQR    │  > [LASPEYRES]…  │   by sub-index │   ─────────────────     │
│ ┋        │  > [DB] …        │                │   INDEX HISTORY  (svg)  │
│ ④ LASPEY │  _               │                │   ─────────────────     │
│ ┋        │  «packet flow    │                │   IQR DISTRIBUTION(svg) │
│ ⑤ DB     │   canvas layer»  │                │                        │
├──────────┴─────────────────┴────────────────┴─────────────────────────┤
│ ANOMALIES EXCLUDED (2)   ·   conditional — hidden when count = 0        │
├───────────────────────────────────────────────────────────────────────┤
│ COMMAND BAR · 26px ·  ⏎ execute · ↑↓ k-factor · C corridor · M mute     │
└───────────────────────────────────────────────────────────────────────┘

grid-template-rows: 22px 52px 40px 72px 1fr auto 26px;
main row grid-template-columns: 0.5fr 1fr 0.85fr 0.8fr;  gap 16px;
readout column stacks: [readout auto] [history 1fr] [iqr-dist 1fr]
clamp to 100vh; only CONSOLE + ANOMALIES scroll.
< 1200px: map drops below console. < 900px: everything stacks, page scrolls.
```

### 2.3 Boot choreography (the centerpiece — Stage F4)

| beat | event |
|---|---|
| 0.0s | Execute collapses to a spinner · status dot → pulsing green · background grid pulses brighter for ~400ms |
| 0.15s | ticker tape speeds up briefly · header run-id hex types in |
| 0.2s | **grid expands** — status strip drops down, pipeline slides in from left, console narrows to make room, map fades up, readout column unfolds right (staggered 60ms) |
| 0.5s | status-strip numbers **odometer from 0** to live values |
| 0.6s | console runs the **BIOS boot** (`KERNEL v2.0` · `festival_dict … [OK]` · `travelpayouts.api handshake … [OK]` · `base_year_reference … [OK]`) ~0.9s |
| 1.5s | pipeline node ① ignites — **energy pulse travels down the connector**; `[INGEST]` line streams |
| 1.5s+ | **packet flow** begins: ~412 dots stream INGEST→FESTIVAL→IQR (canvas) · histogram builds bin-by-bin as packets land |
| per stage | node completes → **its output materialises**: INGEST → records figure counts up · FESTIVAL → 38 packets flash amber, festival chips pop · IQR → fence line sweeps across the histogram, 2 outer bars turn red and **packets eject downward** into the anomalies bin |
| ~3.0s | LASPEYRES done → big index **split-flaps from 100.00 → 118.75** · radial green glow · scale-punch on settle · map arcs recolour by sub-index |
| ~3.4s | DB done → provenance badges **stamp in** · history chart **draws left-to-right** with a glowing pen-tip · new point drops in |
| ~3.8s | **reproducibility seal** rotates in: `RUN a1b2c3d4 · SHA e7f2… · REPRODUCIBLE` · status dot → solid green `COMPLETE` · Execute returns |

### 2.4 Re-run (change k_factor or corridor, press Execute again)

**No full boot.** Fast re-compute (~800ms): only IQR + readout + histogram + anomalies + affected map arcs flash and update; index split-flaps to the new value; a single `[IQR] k=3.0 · re-evaluated · N excluded` console line.

### 2.5 Progressive disclosure rules

| Element | Shows only when |
|---|---|
| Anomalies table | `anomaly_count > 0` — else one line `no anomalies at k=1.5` |
| ex-festival delta chip | gap > ~1.0 index points |
| `[FALLBACK]` badges | a fallback fired this run |
| Confidence band on chart | imputation / nowcast actually ran |
| Index History chart | run 1 → "first observation" marker; real trend from run 2 |
| Pipeline / status strip / map / readout | only in LIVE — absent when DORMANT |

---

## 3. Stage overview

| Stage | Name | Backend? | Output |
|---|---|---|---|
| **F0** | Shell + tokens + DORMANT | no | dormant view, styled |
| **F1** | LIVE skeleton | no | every live panel, frozen fake data, DORMANT↔LIVE dev toggle |
| **F2** | Controls + command bar | no | 4 inputs wired + keyboard operation |
| **F3** | Console renderer | no | `appendLine` + typewriter + latency stamps + BIOS boot |
| **F4** | Boot choreography | no | the full DORMANT→LIVE cinematic on fake data |
| **F5** | Packet-flow pipeline viz | no | canvas: records flow + eject at IQR |
| **F6** | Live data-viz | no | slider→real IQR math→histogram/chart/map react |
| **F7** | Ambient + disclosure polish | no | grid, heartbeat, ticker data, jitter, disclosure rules, reduced-motion |
| **F8** | Optional FX toggles | no | Web-Audio sound + glitch error transition (off by default) |
| **F8.1** | Model correctness | no | index from `mean(clean)`, corridor-aware; readout = map = ticker; real CPI series or none |
| **F8.2** | Failure + edge states | no | date validation, `runAudit` try/catch, ERROR state, deterministic seal, no stuck button |
| **F8.3** | Event bus | no | `VS.bus` replaces the 4 status-dot `MutationObserver`s — unblocks F9 |
| **F8.4** | A11y + demo-hardening | no | aria-live, linked labels, non-colour status tokens, 1366×768 fit, embedded fonts |
| **F9** | Backend integration | **yes** | split into `static/` modules; `EventSource` drives it; sim stays as `?demo=1` |
| **F10** | Responsive + demo-ready | yes | empty/error states, stacking, pywebview, checklist |

**File:** one self-contained `vayu-suchak-dashboard.html` through F8.4. At **F9** it splits:
```
static/
├── index.html
├── css/styles.css
└── js/{ main, console, pipeline, packets, charts, map, telemetry, sound, api }.js   (ES modules)
```
No frameworks. No build step. All charts/map/packets hand-rolled SVG + Canvas 2D. Only external load = Google Fonts.

---

## 4. Stage detail + acceptance tests

### F0 — Shell + tokens + DORMANT
**Build:** the file · Google Fonts · `:root` tokens · the DORMANT layout only: ticker strip (static text), centered wordmark + subtitle, control bar (styled, not wired), dormant console showing `VAYU-SUCHAK KERNEL v2.0` / `SYSTEM READY`, command bar, idle status dot. A `--live` CSS class on `.app` that will later reveal the LIVE grid (define the grid, don't populate it).
**Do NOT:** render pipeline/status-strip/map/readout/charts/anomalies; no JS; no ambient motion.
**Acceptance:**
- [ ] Opens, no console errors
- [ ] DORMANT view is centered, calm, intentional at 1440px
- [ ] Ticker strip present (can be static)
- [ ] Command bar shows `⏎ execute · ↑↓ k-factor · C corridor`
- [ ] Colours + fonts match tokens

---

### F1 — LIVE skeleton (frozen fake data)
**Build:** every LIVE panel, fully styled, frozen:
- status strip — 6 tiles with static values
- pipeline — 5 nodes (①② done+check, ③ active+ring, ④⑤ idle), connector line green through done
- console — BIOS lines + 7 audit lines + static cursor
- **national map** — SVG India outline, 5 city dots, the DEL–BOM arc glowing green, others dim
- readout — **split-flap** index showing `118.75` (static faces), ex-festival, meta, badges
- index history — static SVG polyline (VAYU) + dashed (CPI)
- IQR distribution — static SVG histogram, 2 red bars past an amber fence line
- anomalies — 2 static rows
- a hidden dev toggle that switches `.app.--live` on/off **instantly** (no animation)
**Do NOT:** wire controls, add animation, add real math.
**Acceptance:**
- [ ] LIVE view reads as a finished cockpit at 1440–1600px
- [ ] Every tag / arc / bar colour follows the signal system
- [ ] Split-flap index is the dominant element
- [ ] DORMANT↔LIVE dev toggle flips the whole layout
- [ ] India map is recognisable; arc connects the right two cities

---

### F2 — Controls + command bar
**Build:**
- corridor `<select>` (5 corridors, en-dash), two `<input type="date">` (Nov 2026 default), `k_factor` `<input type="range">` + live mono label + green fill track, Execute button with idle→running (`◐ Auditing…`, spin, disabled)→idle
- `state = { corridor, start, end, kFactor }`, updated on change, echoed to a temp `#debug` line + `console.log`
- **keyboard:** `Enter` → execute · `↑`/`↓` → k_factor ±0.5 (with the label + track updating) · `C` → cycle corridor · `M` → toggle mute flag (no sound yet)
- helper line: *"Select a corridor and press Execute."*
**Do NOT:** run any pipeline logic — Execute just holds the running state 3s.
**Acceptance:**
- [ ] Slider label + fill track follow the handle
- [ ] `↑↓` change k_factor and update the UI; `C` cycles corridor; `Enter` fires Execute
- [ ] State changes visible in the debug line
- [ ] Tab reaches every control

---

### F3 — Console renderer
**Build:** `window.VS.appendLine(stage, msg, {fallback})` — coloured tag, chunked typewriter (~36 ticks, instant when `document.hidden`), auto-scroll, `.cursor-line` between lines, removed when idle. Plus:
- **latency timestamps:** each line prefixed `[+0.312s]` accumulating from run start
- **BIOS boot:** `runBios()` streams `KERNEL v2.0` · `festival_dict.json … [OK]` · `amadeus.api handshake … [OK]` · `base_year_reference.json … [OK]` · `pipeline.armed`
- dev buttons: `▸ demo run`, `▸ demo fallback`, `▸ bios`
**Acceptance:**
- [ ] Lines typewriter in one at a time, correct tag colours
- [ ] `[+n.nnns]` timestamps accumulate
- [ ] BIOS runs as its own short sequence
- [ ] `*FALLBACK` line tints the whole row red
- [ ] Console pinned to newest line; cursor blinks during, hidden when idle

---

### F4 — Boot choreography (DORMANT → LIVE)
**Build:** Execute → `runAudit()` playing §2.3 beat-for-beat on simulated data:
- `lockUI()` · spinner · dot pulsing · grid pulse
- reveal LIVE grid with staggered panel entrances (`.panel` `--enter` class, 60ms stagger)
- status-strip odometer spin-up (`countUp(el, 0, target, 700)`)
- `runBios()` then the 7 audit lines via `appendLine`, each fired as its stage runs
- pipeline: `setNode(i,'active')` (pulse + connector energy pulse) → await fake work → `setNode(i,'done')` (green + check draw)
- on LASPEYRES: `splitFlapTo(indexEl, 100, 118.75, 900)` + radial glow + scale-punch
- on DB: `stampBadges()` + `drawChart()` + `stampSeal(runId, sha)`
- `unlockUI()` · dot `COMPLETE`
- **re-run path:** if already LIVE and only k/corridor changed → `recompute()` (~800ms, no grid re-entrance)
**Acceptance:**
- [ ] One click plays the full ~5s sequence unattended, DORMANT→LIVE
- [ ] Panels enter staggered; status numbers spin up; pipeline ignites ①→⑤ with connector pulse
- [ ] Console streams in sync with the pipeline
- [ ] Index split-flaps + glows; seal stamps in at the end
- [ ] Second run (change k) does the fast re-compute, not a full boot
- [ ] Re-running resets cleanly, no leftover state

---

### F5 — Packet-flow pipeline viz
**Build:** a `<canvas>` layer behind the pipeline+console area.
- `FAKE_RECORDS = 412` → spawn that many dots (throttled draw; represent as ~120 visible with a count label)
- dots travel INGEST→FESTIVAL→IQR→LASPEYRES along the connector path
- at FESTIVAL: ~38 dots flash `--amber` briefly
- at IQR: 2 dots divert **downward, red**, into an "anomalies" sink; the rest continue
- packet emission synced to F4 stage timing; `prefers-reduced-motion` → skip packets, just update counts
**Acceptance:**
- [ ] Dot volume visibly scales with record count
- [ ] 38 flash amber at FESTIVAL, 2 eject red at IQR
- [ ] Runs smoothly (no jank) during the full sequence
- [ ] Reduced-motion disables the canvas cleanly

---

### F6 — Live data-viz (histogram + chart + map)
**Build:**
- `FAKE_PRICES` (~140 values, outliers ₹1,200×2 low, ₹9k/₹12k/₹15k high) · `iqrFilter(prices, k)` real math
- **histogram:** `drawHistogram()` — bars grow from baseline; on re-run the fence line sweeps to its new x and outer bars flip red/blue with a transition
- **history chart:** `drawChart(history)` — polyline self-draws via `stroke-dashoffset`; glowing pen-tip dot leads the stroke; optional confidence band (gradient fill) when nowcast flag set
- **national map:** `paintArcs(subIndexByCorridor)` — each corridor arc's colour interpolates green→amber→red by its sub-index; selected corridor arc is thicker + glowing; a dashed "flight" dash travels along it during a run
- k_factor slider `input` → recompute → redraw histogram + anomalies table + integrity tile + map; if LIVE, also `appendLine('IQR', …re-evaluated…)` and re-split-flap the index
**Acceptance:**
- [ ] Dragging k 1.5→3.0 visibly shrinks the red region + drops the anomaly count; histogram animates (not a hard cut)
- [ ] Anomalies table count == `[IQR]` log line == red bars
- [ ] Chart draws itself with the pen-tip; rescales smoothly on new points
- [ ] Map arcs recolour by sub-index on completion; selected arc stands out

---

### F7 — Ambient + progressive disclosure polish
**Build:**
- background grid drift (CSS transform keyframe) + slight brighten near cursor (JS, throttled) + a brighten pulse on each stage completion
- DORMANT console **heartbeat** line every ~4s
- ticker tape fed from `subIndexByCorridor` (updates after each run) — CSS marquee
- status dot states: grey `IDLE` → pulsing `RUNNING` → solid `COMPLETE` → red `ERROR`
- telemetry micro-jitter (latency 40–60ms, throughput 300–450) only while `running`, freeze on complete, with a brief digit-scramble settle
- **enforce disclosure rules** from §2.5: anomalies hidden at 0; delta chip threshold; conditional fallback badges; chart run-1 state
- `@media (prefers-reduced-motion: reduce)` — kill grid drift, jitter, typewriter, packets, split-flap (snap instead); keep state changes
**Acceptance:**
- [ ] DORMANT screen feels alive (grid drift, heartbeat, ticker, breathing dot)
- [ ] All 6 disclosure rules fire correctly (test: k high enough for 0 anomalies → table gone)
- [ ] Telemetry jitters only during a run
- [ ] Reduced-motion disables all ambient motion; app still fully works

---

### F8 — Optional FX toggles
**Build:** a small settings affordance (gear icon, top-right) with 3 switches:
- **Sound** (default OFF): Web Audio synthesised — soft tick per console line, rising tone during split-flap, chime on complete, low buzz on error. `M` key toggles.
- **Glitch on error** (default ON): RGB-split + slice offset on the failing panel for ~200ms
- **CRT console glow** (default OFF): subtle text-shadow + scanline on the console
**Acceptance:**
- [ ] Each toggle works and persists for the session
- [ ] Sound is off by default; `M` mutes/unmutes; no audio files loaded
- [ ] Nothing here is required for the core demo

---

> **F8.1–F8.4 — the integrity pass.** Everything through F8 is a beautiful shell. These four
> stages close the gaps an SIH judge finds by *touching* it — numbers that contradict each other
> on screen, dead controls, a "REPRODUCIBLE" seal that isn't, no failure path. Still zero backend,
> still one file. Do these before F9; F8.3 in particular makes F9 much cheaper.

---

### F8.1 — Model correctness (the numbers must agree)
**Why:** the readout index is `118.75 + (k−1.5)·0.42` — corridor is never an input, the IQR
`clean` set is computed then ignored, `ex-festival` is a constant `−2.35`, and the CPI line is a
synthetic ramp. Switch corridor → readout (~119) openly contradicts the map arc + ticker
(`DEL–GAU 124.2`). First thing a judge breaks.
**Build:**
- `simulate(s)` takes `s.corridor`. Per-corridor fare sample (own seed, or scale the shared one) so `mean(clean)` lands near that corridor's `SUB_INDEX`.
- `index = mean(r.clean) / BASE_2022[corridor] × 100` — real Laspeyres-shaped calc off the filtered set. Delete the `+0.42` fudge. `BASE_2022` = a 5-entry constant.
- k_factor moves the index *because* `r.clean` changes — the `[LASPEYRES]` console line becomes honest.
- `exFestival = index − festivalLift(corridor, range)`; `festivalLift` returns 0 when the date range holds no flagged festival.
- After every run/re-run: write the new index back to `SUB_INDEX[corridor]`, re-fire `paintArcs()` + `renderTicker()`. Readout, map arc, `mapSelLabel`, ticker → always the same number for the selected corridor.
- CPI: embed the real **MoSPI CPI "Transport" monthly series 2022→2026** as a static array (small, published, no backend). Plot that. If it can't be sourced before the deadline, **delete the CPI line + legend** — do not ship the ramp.
- FESTIVAL console count reflects the actual window (no `Christmas:7` in a Nov-only range).
**Do NOT:** add any fetch / live data — still fully offline. Don't retime the choreography.
**Acceptance:**
- [ ] Change corridor + Execute → readout index == map arc value == ticker entry for that corridor
- [ ] Drag k 1.5→3.0 → `index === mean(clean)/base×100` at every stop (not a fixed slope)
- [ ] Diwali preset vs a Jan range → different festival lift, different ex-festival gap, different FESTIVAL count
- [ ] CPI line is real published data, or absent — never synthetic
- [ ] Identical inputs twice → identical index

---

### F8.2 — Failure + edge states
**Why:** `err` is set nowhere — F8's glitch observer, F7's ERROR dot, F10's 422 are all dead code.
End-before-start date runs anyway. If any `await` in `runAudit` throws, `busy` stays `true` and
Execute is dead until reload. The seal says `SHA e7f2` (4 hex chars = theatre) with a random
`run` id, so "REPRODUCIBLE" is false.
**Build:**
- Date validation: `end ≥ start`, span ≤ an allowed max → invalid shows an inline red helper under the range, Execute disabled, no console line.
- `runAudit()` in `try / catch / finally`. `finally` always clears `busy` + `unlockBtn()`. `catch` → `setDot('err','ERROR')`, one `[SYSTEM] audit.failed · <reason>` line, seal suppressed.
- Deterministic identity: `runId = shortHash(corridor + start + end + kFactor + DATA_SNAPSHOT_DATE)`; `SHA` = first 10 chars of `crypto.subtle.digest('SHA-256', …)` of the same string. Same inputs → same seal, and "REPRODUCIBLE" is now true.
- Enter key: `if (inField && key === 'Enter' && target.id !== 'execute') return;`
- Delete the hardcoded `run a1b2c3d4` / `COMPLETE` from the static header markup — blank until a run populates it.
- `?fail=1` dev flag forces the catch path so ERROR is demoable.
**Do NOT:** build retry / backoff / reconnect — that's F9.
**Acceptance:**
- [ ] End date before start → red helper, Execute blocked, nothing runs
- [ ] `?fail=1` → ERROR dot, console-panel glitch fires, button returns to idle and is clickable again
- [ ] Two runs, same inputs → identical run id + SHA in the seal
- [ ] Enter inside the corridor / k field does not start an audit
- [ ] Toggle to LIVE before any run → empty header, not a fake completed run

---

### F8.3 — Event bus (unblocks F9)
**Why:** F7 and F8 detect run state with four `MutationObserver`s on `.command-bar .dot`'s
className. F9 ("`EventSource` drives it") fights every one. The status dot is a view being used
as the model.
**Build:**
- `VS.bus = new EventTarget()`. Events: `audit:start`, `audit:stage {name,status}`, `audit:recompute`, `audit:done {index,exFestival,anomalies,subIndex}`, `audit:error {reason}`.
- `runAudit()` emits them at the beats it already has.
- F7 jitter start/stop, F8 glitch/buzz, ticker post-run refresh → subscribe to `VS.bus`; delete the observers.
- `setDot()` becomes a pure `bus` subscriber — nothing else reads/writes the dot class for logic.
**Do NOT:** split into `static/` modules yet (F9). One file still.
**Acceptance:**
- [ ] Grep: zero `MutationObserver` on `.dot` remain
- [ ] Jitter, glitch, ticker refresh still fire at the right moments, now via `bus`
- [ ] `VS.bus` events log in correct order for a full run and a re-run
- [ ] F9 can emit the same events from `EventSource.onmessage` with no change to any view code

---

### F8.4 — Accessibility + demo-hardening
**Why:** one `aria-label` in the whole app; console updates are invisible to screen readers; the
entire signal system is colour-only (plan brags about it — ~8% of male judges have CVD); layout
clips the anomalies drawer at 1366×768 (the standard SIH projector); offline venue = no fonts.
**Build:**
- `aria-live="polite"` on `#liveConsole` and the status strip; `aria-busy` on `.app` during a run.
- Link every control: `<label for>` ↔ `id` for the route selects and both date inputs; `aria-pressed` on mute.
- Non-colour status tokens: a glyph or 2–3 letter tag beside every coloured state — pipeline node (`▶` / `✓`), map legend (`BASE` / `ELEV` / `INFL`), anomaly row (`✕`). Colour stays, stops being the only channel.
- `:focus-visible` → 2px `--green` outline + offset on all interactive elements.
- Gate the F3 typewriter on `prefers-reduced-motion` (snap to full text) — per the original F7 spec.
- Layout fits **1366×768 and 1280×720** with the anomalies table visible without scrolling — drop `.live-main{min-height:600px}`, make the two readout-column charts collapsible or the anomalies panel a toggle. Test both.
- Embed JetBrains Mono + Inter as local `@font-face` (woff2, Latin subset + glyphs used). Google Fonts `<link>` stays as progressive enhancement only.
- `?dev=1` gates the DORMANT/LIVE toggle button; hidden otherwise.
- `<title>`, favicon, `<meta name="description">` — pulled forward from F10.
**Do NOT:** full WCAG-AA audit, skip-links, landmark pass — stretch goal, not pre-demo.
**Acceptance:**
- [ ] VoiceOver/NVDA announces each console line as it lands during a run
- [ ] Every Tab-reachable control has a visible 2px focus ring
- [ ] Greyscale screenshot — pipeline state, map tiers, anomalies still legible
- [ ] Usable at 1366×768 with the anomalies table on screen without scrolling
- [ ] Wifi off → fonts still load (embedded), split-flap width stable
- [ ] `prefers-reduced-motion` → console fills instantly, app fully works

---

### F9 — Backend integration
**Build:** split to `static/` ES modules · `GET /api/corridors` fills the dropdown · Execute → `EventSource('/api/execute-audit?…')` · `onmessage` → `appendLine` + advance pipeline + packet emit · final `{done, index, index_ex_festival, anomalies, sub_index, …}` → split-flap + badges + chart + map + seal · `onerror` → `ERROR` state + glitch · simulation kept behind `?demo=1`.
**Acceptance:**
- [ ] Real pipeline run drives the identical choreography
- [ ] Dropdown populated from backend
- [ ] Backend killed mid-run → clean `ERROR` state, button recovers
- [ ] `?demo=1` still runs the offline simulation

---

### F10 — Responsive + demo-ready
**Build:** _(date validation, 1366×768 fit, favicon/title/meta, reduced-motion typewriter → already done in F8.2/F8.4; this stage is the full responsive + native-shell pass)_ first-load empty states · `<1200px` map below console · `<900px` full stack + page scroll + type steps down · backend 422 wired to the F8.2 inline helper · final reduced-motion sweep · `pywebview` wrapper in `run.py` (~15 lines, native window + title + icon).
**Acceptance:** engineering deep-dive §12 checklist + first-load state clean · bad dates show inline error · usable stacked at 390px · launches as a native window via `python run.py`.

---

## 5. Animation catalogue

| # | Animation | Stage | Tech | Duration |
|---|---|---|---|---|
| 1 | DORMANT→LIVE grid expand (panels stagger in) | F4 | CSS transition + JS stagger | 60ms/panel |
| 2 | Status-strip odometer spin-up | F4 | JS rAF count-up | 700ms |
| 3 | BIOS boot lines | F3 | typewriter | ~900ms |
| 4 | Console line entrance (fade+slide) | F3 | CSS | 120ms |
| 5 | Typewriter message | F3 | JS chunked | ~600ms/line |
| 6 | Latency timestamp prefix | F3 | JS | — |
| 7 | Blinking cursor | F3 | CSS steps | 1s loop |
| 8 | Pipeline node active pulse | F4 | CSS box-shadow keyframe | 1.4s loop |
| 9 | Connector energy pulse (data flowing) | F4 | CSS background-position / SVG | 400ms |
| 10 | Pipeline node done — check draw-in | F4 | SVG dashoffset | 300ms |
| 11 | Packet flow along the pipeline | F5 | Canvas 2D | continuous |
| 12 | Festival packets flash amber | F5 | Canvas | 200ms |
| 13 | Anomaly packets eject red into sink | F5 | Canvas | 400ms |
| 14 | Histogram bars grow from baseline | F6 | CSS height transition | 200ms |
| 15 | IQR fence line sweep | F6 | CSS transform transition | 300ms |
| 16 | Outer bars flip red/blue on re-classify | F6 | CSS colour transition | 200ms |
| 17 | Split-flap index digits | F4 | CSS 3D flip per digit | 900ms |
| 18 | Index radial glow + scale-punch | F4 | CSS keyframe, one-shot | 600ms |
| 19 | Provenance badges stamp in | F4 | CSS scale+rotate | 250ms |
| 20 | History chart self-draw + pen-tip | F6 | SVG dashoffset + moving dot | 400ms |
| 21 | Chart new-point drop-in | F4/F9 | SVG transition | 300ms |
| 22 | Chart confidence band fill | F6 | SVG gradient reveal | 400ms |
| 23 | Map corridor arc glow (selected) | F1/F6 | SVG filter + keyframe | 1.6s loop |
| 24 | Map arcs recolour by sub-index | F4/F6 | SVG stroke transition | 500ms |
| 25 | Map "flight" dash travels the arc | F6 | SVG stroke-dashoffset | 2s loop |
| 26 | Reproducibility seal rotate-in | F4 | CSS scale+rotate | 400ms |
| 27 | Ticker tape scroll | F0/F7 | CSS marquee | 30s loop |
| 28 | Background grid drift | F7 | CSS transform | 20s loop |
| 29 | Grid brighten near cursor / on stage-complete | F7 | JS + CSS | 300ms |
| 30 | DORMANT console heartbeat line | F7 | JS interval | every 4s |
| 31 | Telemetry digit-scramble settle | F7 | JS | 250ms |
| 32 | Telemetry micro-jitter during run | F7 | JS interval | 120ms tick |
| 33 | Status dot pulse (running) | F7 | CSS keyframe | 1.2s loop |
| 34 | Execute glyph spin | F2 | CSS rotate | 0.9s loop |
| 35 | Error glitch (RGB split + slice) | F8 | CSS keyframe | 200ms |

All CSS / SVG / Canvas 2D — no libraries, `pywebview`-safe. Every entry above is gated by `prefers-reduced-motion`.

---

## 6. Component specs (quick reference)

### Split-flap index
```
5 digit cells + a fixed "." — each cell is a flap that rotates on Y axis when its value changes.
On set: only cells whose digit differs animate; they cascade left→right, 40ms apart.
Colour --green, Mono 600, tabular-nums. Container has the radial-glow keyframe on completion.
Re-run: same mechanism, usually only 1–2 digits move.
```

### National map
```
SVG: simplified India outline (single path) · 5 city dots (DEL BOM BLR CCU GAU) at fixed coords.
Arc between two cities = quadratic Bézier bowed toward the nearer coast.
states: dim (#30363d, 1px) · selected (2px, --green stroke, glow filter, travelling dash) ·
        recoloured (stroke lerps green→amber→red by sub-index, 500ms transition)
```

### Pipeline node
```
idle : border --border, dim number+label
active: border --green, breathing glow, connector above = filled --green with a moving highlight
done : marker bg --green, dark check drawn in
connector: 2px vertical; filled green up to the furthest completed node
```

### Console line
```
[+1.204s] > [IQR]  k=1.5 · fences [3120, 7600] · 2 excluded
   ▲        ▲   ▲
   │        │   └ .tag  — coloured by stage
   │        └ .prompt — --text-dim
   └ .ts — --text-dim, monospace, accumulates from run start
FALLBACK: whole row background --red-dim, tag --red, tag text [STAGE][FALLBACK]
```

### Reproducibility seal
```
appears bottom-right of the readout on completion. Circular badge, --green hairline,
rotates in (scale 0.6→1, rotate -12°→0). Text: RUN a1b2c3d4 · SHA e7f2 · REPRODUCIBLE
```

### Ticker tape
```
thin strip, full width, top of viewport. CSS marquee (translateX loop, duplicated content).
items: "DEL–BOM ▲2.1%" — arrow + colour by sign. Data = per-corridor sub-index vs last run.
DORMANT: shows last-known / seed values. Updates after each run.
```

---

## 7. Tech constraints

- **One file** through F8. Self-contained. Only external request = Google Fonts (system fallback).
- **No frameworks, no build step, no npm.** Vanilla JS, hand-rolled SVG + Canvas 2D.
- Must run smoothly in **`pywebview`** on a modest laptop → no WebGL, no particle libs; the packet canvas caps visible dots and stops when off-screen / reduced-motion.
- **`prefers-reduced-motion`** honoured from F7 on — every animation has a snap fallback.
- Simulation (`runAudit` on fake data) kept permanently as `?demo=1` offline mode.
- Split to `static/` ES modules only at **F9**; nothing before that is wasted.

---

## 8. Start

Begin at **F0** (rebuild DORMANT view). Then F1. Do not batch stages.
