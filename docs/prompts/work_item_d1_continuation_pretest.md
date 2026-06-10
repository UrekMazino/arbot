# Work Item — D1 Unified Continuation Pre-Test
## Read-only / analysis-only on existing logs + a fresh kline pull. No trades, no bot contact, no frozen-variable touch.

**Authorized 2026-05-31** as Direction-1 pivot's unified offline pre-test. Tests the shared premise of forms 1a (spread-velocity), 1b (coint-breakdown), 1c (z-velocity): **fast spread divergence at minute-scale on the exp_beta universe predicts continuation large enough to clear costs.** Picks the detector (binary `broken` flag vs continuous velocity) as a byproduct rather than as an input. Supersedes the prior D1 work item (the 15-MR-trade sign-flip simulation), which was the biased-sample version of the same hypothesis — the unbiased version costs one kline pull more.

**From:** strategist (analysis/strategy role).
**Task class:** READ-ONLY analysis on (a) existing logs + B1 v1 per-run CSVs, (b) a fresh historical-kline pull from OKX (the same API `core/chart_audit/retroactive_beta.py` already uses). No trades, no live trade API, no bot code paths invoked, no marking-fidelity wall (klines are public historical data, not virtual positions).
**Drafted:** 2026-05-31, post-Lever-B-DEAD verdict. Same anti-rationalization discipline.
**Owner split (per strategist instruction):** strategist owns §6 verdict definitions + §7 lock; code assistant owns §0–§5 mechanical scaffolding + §8 action items. The split puts the anti-rationalization machinery in the hands of the party that has demonstrated willingness to write the verdict that cuts against its own advocacy (Lever-B-DEAD precedent).

---

## 0. The question, stated precisely

For a grid of divergence-event triggers and post-event windows on the exp_beta_aware_sizing_v1 pair universe over the experiment window:

> **Given a divergence event (`broken` from the binary detector, OR a velocity crossing from the continuous detector grid), does the spread continue moving in the divergence direction over the next {5, 15, 30, 60} minutes — net of whipsaws and at $0.14 textbook costs — and does that continuation appear in a multi-cell ridge across the trigger × window grid rather than a single beautiful cell?**

This is upstream of the form choice (1a/1b/1c). If continuation exists, the detector that catches it is downstream and falls out of the same data. If continuation doesn't exist, all three forms close together cleanly.

---

## 1. Data preconditions (CONFIRM before running)

**1.1 Existing data (already on disk).**
- [ ] **B1 v1 per-run sample CSVs** (`tools/observation_mode/output/run_*__samples.csv`) — source for binary `broken` events. 132 events total across 18 runs per the B1 v1 baseline. Regime, pair, timestamp already extracted.
- [ ] **Trade hold windows for T1–T15** — from `Reports/v1/run_*/trade_closes.csv` and `position_snapshots.csv`. Source for the confound sub-analysis (§4.3).
- [ ] **Logged z trajectories during trade holds** — from `position_snapshots.csv`. Source for the sanity-check reconciliation against kline-reconstructed z (§1.3).
- [ ] **Logged β per active pair** — from `STRATEGY_TRADE_OPEN` and `BETA_SIZING` log lines. Used in z reconstruction for active-pair windows.

**1.2 Fresh kline pull (new).**
- [ ] **OKX 1-minute kline history** for each unique instrument appearing in the 18-run pair universe (~80–100 distinct instruments per B1 v1.1's 129 distinct pairs).
- [ ] **Date range:** 2026-05-28 00:00 UTC through 2026-05-31 03:00 UTC (covers run 125 start through run 142 end + 60-minute buffer past the last `broken` event for post-event windows).
- [ ] **Source:** OKX history-candles API. Reuse the pattern from `core/chart_audit/retroactive_beta.py` — same library code, same auth posture (public endpoint, no trade credentials).
- [ ] **Storage:** cache to `tools/observation_mode/output/kline_cache/<INSTRUMENT>.csv` per instrument. One-time pull; subsequent runs read from cache.

**1.3 Sanity-check the kline-derived z against logged z (STOP-AND-REPORT if it fails).**

The query-3 terminal finding (`tools/fidelity_validator/`) established that kline-derived values have limits — specifically, kline-mid prices are not the same as the bot's `markPx` used for live `upl`. That finding does NOT block this analysis (we're not computing PnL on virtual positions — we're computing spread evolution from public prices), BUT it means the kline-reconstructed z trajectory needs to agree with the logged z on the overlapping in-trade windows before any downstream conclusion can be trusted.

**The sanity check (two-stage: levels AND velocities, per strategist §1.3 extension):**

**Stage 1 — level reconstruction:**
- For each of the 15 trades, reconstruct z(t) from klines using the logged entry-β: `spread(t) = price_1(t) − β · price_2(t)`, then normalize by a rolling-window σ to get z. Use the same rolling window the bot uses (window=60).
- Compare reconstructed z(t) to logged z(t) from `position_snapshots.csv` at each snapshot.
- **Pass criterion:** mean absolute difference ≤ **0.10σ** across all snapshot ticks, on at least 13 of 15 trades. (T7 and T10 are single-snapshot trades from the Lever-B audit; they're a weak check but include them for completeness.)

**Stage 2 — velocity reconstruction (strategist's §1.3 extension; required because detectors consume dz/dt and differencing roughly multiplies the error):**
- For the same trades, compute reconstructed 1-min dz/dt from the kline z trajectory and logged 1-min dz/dt from the position-snapshot z trajectory.
- **Pass criterion:** mean absolute difference between reconstructed and logged 1-min dz/dt ≤ **0.15σ/min** across all overlapping ticks, on at least 13 of 15 trades. (Levels passing does not imply velocities pass — a 0.10σ level tolerance can yield ~0.14σ/min velocity error, which is material against a 0.3 threshold. Velocities are the load-bearing quantity; both stages must clear.)

**STOP-AND-REPORT (either stage):** if the level reconstruction diverges >0.5σ on any in-trade tick, OR mean abs level difference > 0.10σ on >2 trades, OR mean abs velocity difference > 0.15σ/min on >2 trades, the kline-based reconstruction can't carry the unconditioned-event analysis. Report it as **INFEASIBLE-INSTRUMENT** — a verdict distinct from DEAD. DEAD presumes the instrument is trustworthy; INFEASIBLE means the data layer beneath all the simulation logic is itself the failure point. The analysis halts; the strategist decides whether to commission a finer-grained data source (e.g., orderbook-mid history if OKX exposes it) or close the pre-test as INFEASIBLE-INSTRUMENT. **Levels-pass-velocities-fail still routes to INFEASIBLE**, because the triggers are velocity-based; level fidelity alone isn't enough.

**1.4 β handling for non-active-pair windows.**

The bot logs β only for the active pair. For the 132 `broken` events, all are emitted from active-pair `COINT_GATE` evaluations — so we have β for every binary-detector event. For velocity-detector events, we extend to pairs the bot evaluated but didn't trade; per B1 v1.1, the universe is 129 distinct pairs but β is only logged for the pair the bot was currently on.

**Decision (strategist confirm):** restrict velocity-detector event extraction to **the same active-pair windows the binary detector uses** — i.e., the pair the bot was currently active on at each timestamp. This keeps both detectors operating on the same pair-stream (avoids confounding "velocity detector caught more because it has access to more pairs") and means β is always logged. The pair-coverage is constrained but consistent across detectors. Cross-pair velocity events would require rolling-β refitting on each kline, which adds analysis surface for a constraint that doesn't help the detector comparison.

---

## 2. Trigger extraction (the grid)

**2.1 Detectors (10 total).**

| Detector ID | Definition |
|---|---|
| `binary_broken` | `health=broken` event from existing COINT_GATE log stream (from B1 v1 CSVs). One event per transition INTO `broken` (dedupe adjacent same-pair `broken` ticks within 60s). |
| `vel_w1_t0.3` | `|dz/dt|` computed over 1-min lookback ≥ 0.3 σ/min, threshold crossing event |
| `vel_w1_t0.5` | same, threshold 0.5 σ/min |
| `vel_w1_t0.8` | same, threshold 0.8 σ/min |
| `vel_w3_t0.3` | `|dz/dt|` over 3-min lookback ≥ 0.3 σ/min |
| `vel_w3_t0.5` | same, 0.5 |
| `vel_w3_t0.8` | same, 0.8 |
| `vel_w5_t0.3` | `|dz/dt|` over 5-min lookback ≥ 0.3 σ/min |
| `vel_w5_t0.5` | same, 0.5 |
| `vel_w5_t0.8` | same, 0.8 |

Velocity dz/dt computed on the kline-reconstructed z trajectory, on active-pair windows only (per §1.4). Threshold crossing = transition from below threshold to at-or-above threshold; dedupe adjacent crossings within the lookback window (a w=1, t=0.3 detector retriggers no sooner than 1 minute after firing).

**2.2 Per-event direction.**

Both detectors use the velocity sign at event time to determine bet direction: positive `dz/dt` → long-direction trend bet (bet spread continues rising); negative → short. For binary `broken` events, compute the dz/dt over the past 3 minutes at the event timestamp; sign that. (Binary detector is direction-agnostic in its trigger but the bet has to take a side; using the trailing velocity as the direction proxy is the natural way.)

**2.3 Per-event metadata recorded.**

For each event: `timestamp, pair, regime (from REGIME_STATUS at event time), detector_id, direction, z_at_event, dz_dt_at_event, in_trade_flag (timestamp ∈ any T1–T15 hold window)`.

---

## 3. Simulation loop (entry → exit, whipsaw accounting)

**3.1 Synthetic trade specification.**

- **Entry:** at event timestamp T, on pair P, direction D (per §2.2).
- **Position sizing:** β-aware per H1 (settled), gross=$200 (matches the experiment window; comparison is fair, and the cost model is the same; if the trend hypothesis demands larger notional that's a downstream live-experiment question — pre-test stays at $200 so costs can be directly compared to MR).
- **Hold and exit logic (first-of):**
  1. **Window expiry:** post-event window W minutes elapses without hitting other exits. Exit at T+W.
  2. **Trailing stop:** track peak unrealized PnL since entry; exit if PnL drops from peak by **$0.10** (≈ 50% of textbook cost; pre-committed, no in-analysis tuning).
  3. **Signal reversal:** dz/dt at current minute flips sign past −0.3 σ/min (in the trade-adverse direction) for any contiguous 2-minute window. Exit at the second minute of confirmed reversal.

**Exit-rule parameters are single pre-committed values, not optimized** (strategist §3.1 caveat, required). This pre-test answers premise-existence under *one* reasonable exit rule — not "what exit rule extracts the most value." A bad exit could butcher real continuation into net-negative; a generous exit could spuriously rescue noise. The trailing-stop and reversal thresholds are picked once, defensibly, and held. The premise-vs-capture split in §6 (Amendment 2) is how the verdict logic protects against the first failure mode without inflating the second.

**3.2 Per-window simulation.**

For each event T, simulate the trade at each post-event window W ∈ {5, 15, 30, 60} minutes **independently**. That is, the same event T spawns 4 synthetic trades, each with a different max-hold cap. This matches the per-cell aggregation in §4 — each (detector × window) cell has its own event-trade mapping.

**3.3 Per-trade outcome recorded.**

`exit_minute (offset from T), exit_reason ∈ {window_expiry, trailing_stop, signal_reversal}, gross_pnl_at_exit, peak_favorable_excursion (max gross_pnl reached at any tick between T and exit; strategist §3.1 requirement, load-bearing for §6 Amendment 2), whipsaw_flag (exit_reason ≠ window_expiry AND gross_pnl < cost — i.e., exited early without clearing)`.

**The peak_favorable_excursion field is independent of the exit rule** and isolates the premise from the capture mechanism: if peaks-clear-but-net-doesn't, continuation exists and the exit rule failed to capture it — a different verdict from "continuation absent." See §6 Amendment 2.

**3.4 Cost model.**

- **`real_cost = $0.14`** textbook (fees $0.10 + slippage $0.04) per the strategist call (§3 of strategist response).
- **Carry forward the strategist's directional asymmetry verbatim:** *"Using $0.14 (which excludes funding on possibly-longer holds) is generous toward the hypothesis — so DEAD is robust to the cost model, but EXISTS is not, and an EXISTS verdict must carry the caveat: at entry/exit costs only; funding on realistic hold lengths not included."* This is recorded in §6's EXISTS-verdict caveat exactly as the strategist wrote it.
- **Robustness band:** ±$0.06 (same as cost diagnostic and Lever-B). A cell's qualification depends on aggregate net surviving the adverse cost direction (`cost + $0.06`).

---

## 4. Aggregation, ridge detection, regime split, confound sub-analysis

**4.1 Per-cell aggregation (40 cells: 10 detectors × 4 windows).**

For each cell:
- `n_events` (count of synthetic trades for that detector × window)
- `n_continuing` (trades with gross_pnl > cost, point estimate)
- `n_whipsaw` (early-exit-without-clearing per §3.3)
- `aggregate_net_point` = Σ(gross_pnl − $0.14) across all trades in the cell
- `aggregate_net_adverse` = Σ(gross_pnl − ($0.14 + $0.06))
- `whipsaw_rate` = n_whipsaw / n_events
- **`cell_qualifies`** = `(n_events ≥ 20) AND (aggregate_net_point > 0) AND (aggregate_net_adverse > 0)` — the cell survives the adverse cost band

**4.2 Ridge detection.**

Per the strategist's verdict block, ridge = ≥2 adjacent qualifying cells. Adjacency defined as:
- **Same detector, neighboring windows:** (w=5 ↔ w=15), (w=15 ↔ w=30), (w=30 ↔ w=60). Applies to all 10 detectors.
- **Same window, neighboring thresholds within same lookback period:** for velocity detectors only, within same window-period (w1, w3, w5), thresholds {0.3, 0.5, 0.8} have neighbors (0.3 ↔ 0.5) and (0.5 ↔ 0.8). At fixed post-event window.
- **Binary `broken` detector has no threshold/period neighbor** — only window-axis adjacency applies to it (4 cells maximum can ridge, requiring ≥2 adjacent windows to qualify).

Cells separated by non-qualifying cells are not adjacent. A single beautiful cell surrounded by non-qualifying cells is a **spike**, not a ridge — pre-named as noise per §6 lock.

**4.3 Regime split (with N guards).**

For each cell, split aggregates by regime at event time: RANGE / RISK_OFF / TREND. Apply the same `cell_qualifies` and ridge logic within each regime subsample. **Sample-size guard:** any cell with `n_events_regime < 20` is reported as `INSUFFICIENT-N-REGIME` and does not qualify regardless of net direction. Per strategist §5: regime subsamples may be thin; if a verdict rests on a regime-conditional ridge, that's directional-at-best and must be flagged in the verdict text.

**4.4 Confound sub-analysis (§6 of strategist response — "the best idea in the response, elevated to permanent meta-finding").**

Identify in-trade events: events whose timestamp falls within any T1–T15 trade hold window (between STRATEGY_TRADE_OPEN and STRATEGY_TRADE_CLOSE for the trade on that pair).

Compute and report continuation_rate (n_continuing / n_events) on three splits:
- (a) All events (the headline, unconditioned)
- (b) In-trade subsample only (the original D1 evidence base)
- (c) Unconditioned subsample (all − in-trade)

**Report `delta = rate(b) − rate(c)`.** Whichever way this comes out is a permanent meta-finding about how much trade-derived evidence (selection-conditioned on the bot being in a position) misled or didn't mislead direction-of-investigation choices. The delta calibrates future trust in trade-derived evidence across the whole research program — it outlives this pre-test specifically.

---

## 5. Subtleties / handling

**5.1 No imputation on missing kline ticks.** If a pair's kline data has gaps within the experiment window (e.g., OKX listing delay, instrument suspension), events that would fire within the gap are skipped, not interpolated. Report skipped-event count per detector.

**5.2 Stop-and-report on kline reconstruction failure.** Per §1.3 — if z reconstruction fails the sanity check, the analysis halts and the result is reported as INFEASIBLE-INSTRUMENT, not as DEAD. DEAD requires the data instrument to be trustworthy; an untrusted instrument is a separate failure mode and must be named.

**5.3 Direction sign convention.** Established once at the top of the run and used uniformly: positive dz/dt → "long signal_positive, short signal_negative" (bet spread continues moving up). Verify against in-trade snapshots where direction is known.

**5.4 Per-trade vs per-event accounting.** A trade either qualifies as continuing (gross > cost) or doesn't. A trade either qualifies as whipsaw (early exit without clearing) or doesn't. The two flags are independent (a non-whipsaw trade can still fail to clear cost by expiring at window with PnL between 0 and cost). Report both counts cleanly.

**5.5 Sample-weighting for the aggregate.** `aggregate_net_*` sums per-trade nets without re-weighting. If two cells have very different n_events but the ridge requires both qualify on adverse-cost-aggregate, the aggregate is naturally biased by sample size — which is the right behavior (a small-N cell that barely qualifies shouldn't dominate the ridge).

**5.6 No detector tuning during the analysis.** The grid is pre-committed in §2.1. If during the run a "natural" threshold or window emerges as the obvious break point that wasn't in the grid, that observation is recorded as a post-hoc note but the verdict reads the grid as specified. Re-tuning to find the right cell is the multiple-comparisons trap the ridge requirement was designed to prevent.

---

## 6. Pre-committed verdicts (LOCKED before the run — strategist's block, embedded verbatim; with Amendments 1 + 2 embedded by strategist authorization, pre-run-only, lock-consistent)

> **CONTINUATION-EXISTS** — a ridge (≥2 adjacent grid cells: same detector at neighboring windows, or neighboring thresholds at same window) where aggregate net after whipsaws is positive and survives the cost band [−$0.06, +$0.06], each qualifying cell having ≥20 events. Routes to: detector choice (whichever detector owns the ridge), then live-experiment design with full apparatus. **Carries mandatory caveat: at entry/exit costs only; funding on realistic holds unmeasured; EXISTS is not robust to the cost model in the way DEAD is.**
>
> **CONTINUATION-DEAD** — DEAD now requires BOTH conditions, per Amendments 1 + 2 below:
>
> **(a) No net-positive ridge** (the original net-aggregate condition): no ridge anywhere on the grid (isolated spikes don't count), or aggregate net negative across all cells, or the post-event move distribution is symmetric/reverting on average.
>
> **(b) Peak-favorable-excursion failure** (Amendment 2 — premise-vs-capture split): the distribution of `peak_favorable_excursion` across events also fails to clear costs. Specifically — using the same ridge logic on peaks-aggregate as on net-aggregate — no ridge of cells where aggregate peak-excursion clears the cost band exists either. *Peaks measure whether the moves were there at all, independent of how the exit rule captured them.* If peaks fail too, the premise is dead, not just the capture; that's the proper basis for "continuation absent."
>
> **(c) Adequacy precondition (Amendment 1):** at minimum, the broken-detector row AND ≥1 velocity-detector row at ≥20 events must both have been evaluable. If all 9 velocity-detector rows starve (<20 events under the §1.4 active-pair-windows restriction), DEAD cannot be rendered for 1a/1c — the data never covered them. In that case the verdict splits into **broken-row-VERDICT for 1b (DEAD or AMBIGUOUS per (a)+(b) on the broken row alone)** plus **VELOCITY-UNDERPOWERED for 1a/1c** (data insufficient to evaluate; not negative; AMBIGUOUS-sub-cause per below). The split outcome is named in advance so it can't be blurred into either DEAD or AMBIGUOUS after the fact.
>
> Routes (if all three conditions of DEAD met): 1a/1b/1c all close together; D3 gains standing (divergence at minute-scale is noise in both directions — the timescale itself is implicated); operator re-decides D3-vs-stop. **Lock:** this gets written as cleanly as Lever-B-DEAD. No retreat to "the grid was too coarse" or "the windows were wrong" — the grid was pre-committed as adequate, and re-tuning it post-hoc is the exact move the lock forbids.
>
> **CONTINUATION-AMBIGUOUS** — the catch-basin verdict, with five distinct sub-causes that route differently. The artifact MUST report which sub-cause fired (pre-committed; un-blurrable post-hoc):
>
> 1. **SPIKES-WITHOUT-RIDGES** — isolated qualifying cells without adjacent qualifiers. Multiple-comparisons noise; pre-named as not-a-signal per §5.6 and the lock. Routes to: full stop on this hypothesis branch; operator decides D3-vs-stop. Same routing as DEAD substantively.
>
> 2. **RIDGE-DIES-IN-COST-BAND** — ridge exists at point estimate but doesn't survive the adverse-cost direction. Routes to: H-analog cost-precision question (would a precise cost model recover the verdict?). Operator's call whether a per-fill cost upgrade is worth running before any live test.
>
> 3. **REGIME-SUBSAMPLE-BELOW-GUARD** — ridge exists but only in a regime-conditional subsample whose `n_events_regime < 20`. Directional-at-best; not actionable as a finding. Routes to: operator's exploratory call; the conditional hypothesis is named explicitly for any future investigation.
>
> 4. **VELOCITY-UNDERPOWERED** (Amendment 1's split-outcome partner) — all 9 velocity-detector rows starve. 1a/1c can't be evaluated at this N under the §1.4 restriction; the broken-row verdict for 1b is rendered separately. Routes to: operator's call whether a longer collection window (B1 v2 continuous observation) is worth running to populate the velocity rows, or whether 1a/1c are closed by data-insufficiency in this universe.
>
> 5. **PEAKS-CLEAR-NET-DOESN'T** (Amendment 2's split-outcome) — continuation exists (peak-favorable-excursion ridge passes per §6(b)) BUT net under the pre-committed exit rule doesn't (no net-positive ridge per §6(a)). The moves are there; this exit rule failed to capture them. **Named cause: "continuation exists; capture under the pre-committed exit rule doesn't."** Routes to: operator judgment about whether exit-design is worth pursuing as a separate scoped piece of work. This is an honest open question, not a dead premise — and importantly, asymmetric: this door allows AMBIGUOUS to capture "real-but-uncaptured" without inflating EXISTS, because EXISTS still requires the stricter net-positive ridge.
>
> AMBIGUOUS is the modal expected outcome given the data structure (13 in-trade trades, 132 broken events, unknown velocity counts, one unoptimized exit rule). The five named sub-causes prevent a crowded AMBIGUOUS from becoming a Rorschach test.

---

## 7. Anti-rationalization lock (LOCKED — strategist's block, embedded verbatim)

> **Lock direction (binding both of us):** the pivot is chosen, the analyst called the mechanical case strongest, the code assistant has now invested in the design — every party's pressure points toward EXISTS. Therefore: **borderline resolves down (toward AMBIGUOUS, never up to EXISTS); the ridge requirement cannot be relaxed during the read; and a single-cell spike, however beautiful, is pre-named as noise.**
>
> **One last calibration, so expectations are set before the result exists:** this pre-test is the pivot's premise meeting unconditioned data for the first time. Everything until now — the mechanical case, the DECOUPLED evidence, the "strongest of any direction" assessment — was built on the conditioned sample the confound check will now audit. It is genuinely possible this comes back DEAD, and if it does, that's not the pivot failing — it's the pivot's premise being tested for $0 instead of being discovered at $200/trade. Same as Lever-B: the cheap no is the second-best outcome available, and only the genuine yes beats it.
>
> **Final calibration (added with Amendments 1 + 2):** with the amendments in, the most likely outcome is some flavor of AMBIGUOUS, the second most likely is DEAD, and EXISTS — requiring a multi-cell net-positive ridge surviving the cost band on ≥20-event cells — is deliberately the hardest verdict to reach. That's the correct shape for a test whose every interested party wants it to pass. If it passes anyway, it will have earned the live-experiment design that follows. The five named AMBIGUOUS sub-causes route differently (underpowered → maybe extend the stream; peaks-clear → exit-design question; spikes → multiple-comparisons noise, full stop; ridge-dies-in-band → cost-precision question; regime-conditional → exploratory call), so even a modal AMBIGUOUS verdict carries an actionable shape rather than dissolving into nothing.

---

## 8. Discipline guardrails

- **Read-only.** No trades, no live trade API, no bot code paths invoked, no frozen-variable touch. The kline pull uses a public historical endpoint with no auth. Same posture as the validator sidecar, the coint-fragility sampler, the basis-mismatch diagnostic, and the Lever-B simulation.
- **No imputation, no fudge, no post-hoc grid tuning.** §5.1, §5.2, §5.6.
- **STOP-AND-REPORT if the data instrument fails** (§1.3) — INFEASIBLE-INSTRUMENT is a separate verdict from DEAD and must be named distinctly. DEAD presumes the instrument is trustworthy.
- **Verdicts locked before the run** (§6); lock direction binds analyst and code assistant (§7).

---

## 9. Action items

**Code assistant (mechanical implementation):**
- [ ] Implement §1 data preconditions: load existing CSVs + B1 v1 outputs.
- [ ] Implement §1.2 kline pull (one-time): use the OKX history-candles API per `core/chart_audit/retroactive_beta.py` pattern; cache to `tools/observation_mode/output/kline_cache/`.
- [ ] Implement §1.3 z-reconstruction sanity check; STOP-AND-REPORT if it fails.
- [ ] Implement §2 trigger extraction (binary from B1 CSVs; 9 velocity variants computed from klines on active-pair windows).
- [ ] Implement §3 simulation loop with whipsaw accounting; cost = $0.14 textbook + ±$0.06 band.
- [ ] Implement §4 aggregation, ridge detection (per the strategist's adjacency definition), regime split, and §4.4 confound sub-analysis.
- [ ] Render one of §6's three pre-committed verdicts (or INFEASIBLE-INSTRUMENT per §5.2).
- [ ] Persist as a `docs/audits/` artifact (institutional memory, same shape as prior diagnostics).

**Strategist:**
- [ ] Confirm §1.4 β-handling decision (active-pair windows only) — or call differently.
- [ ] Confirm §3.1 trailing stop ($0.10) and signal-reversal threshold (−0.3 σ/min for 2 min) — or call differently.
- [ ] Read the verdict; whichever fires, write it cleanly per the §7 lock. If EXISTS, route to live-experiment scoping. If DEAD, write "the pivot's premise has no pulse on unconditioned data; D3 gains standing" with the same readiness as Lever-B-DEAD.
- [ ] Read the §4.4 confound sub-analysis result independently — calibrates trust in trade-derived evidence across the whole future research program.

**Operator:**
- [ ] Read the verdict; if EXISTS, the live-experiment design is the next decision. If DEAD, D3-vs-stop is the next decision. If AMBIGUOUS, exploratory-vs-D3-vs-stop is the judgment call.

---

*D1 unified continuation pre-test work item v1.1. Mechanical scaffolding (§0–§5, §8, §9) drafted by code assistant 2026-05-31; verdict definitions (§6) and anti-rationalization lock (§7) authored by strategist and embedded verbatim; v1.1 amendments to §1.3 (velocity-reconstruction validation), §3.1 (single-rule-not-optimized caveat), §3.3 (peak_favorable_excursion field), §6 (Amendment 1: adequacy precondition + VELOCITY-UNDERPOWERED split; Amendment 2: premise-vs-capture split with PEAKS-CLEAR-NET-DOESN'T sub-cause; AMBIGUOUS sub-cause taxonomy), §7 closing calibration — all by strategist authorization, pre-run, lock-consistent (refinement legitimate where post-hoc retreat is forbidden). Read-only / analysis-only. No trades, no bot contact, no frozen-variable touch. Supersedes the prior D1 work item (15-MR-trade sign-flip simulation) — the unbiased version costs one kline pull more. Sequenced after Lever-B-DEAD; same anti-rationalization discipline. Hypothesis under test: fast spread divergence at minute-scale on the exp_beta universe predicts continuation large enough to clear costs. Verdict cells: 10 detectors × 4 windows = 40-cell grid; ridge requirement (≥2 adjacent qualifying cells) closes the multiple-comparisons trap; regime split with N guards; confound sub-analysis as permanent meta-finding. AMBIGUOUS expected modal; sub-cause taxonomy keeps it actionable.*
