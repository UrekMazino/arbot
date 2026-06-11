# Work Item — D3 Experiment Design Phase
## Read-only / analysis-only until the design phase completes. No trades, no bot contact.

**Authorized 2026-06-11** (operator: "proceed with the next artifact," routing from D3-PREMISE-SUPPORTED at `docs/audits/d3_daily_coint_pretest_2026-06-11.md`). Translates premise-support into a testable experiment spec — or kills D3 at the design level if realism erases the premise's headroom.

**Sequencing (locked):** Phase A (funding reality) → Phase B (capture-realism walk-forward) → experiment spec (deliverable, only if B passes). Phase B's verdicts are locked IN THIS DOCUMENT, before any backtest code or output exists. Phase A has no verdict surface (it replaces an assumption with a measurement); Phase B is the prior-leakage surface and carries the locks.

---

## 0. What the design phase must answer

The pre-test established: discovered daily-bar relationships survive 10-day holds at 82.4% (null baseline 39%), and 2σ edges are 12–55× the assumed cost stacks. Two gaps stand between that and an experiment:

1. **Funding was assumed, not measured** — and the assumption grid charged BOTH legs as paying. A pairs position is one long + one short: net funding is the rate *differential*, which for correlated perps may largely cancel — or spike on one leg. Phase A measures the real pair-level distribution.
2. **Survival ≠ capture.** The pre-test never entered or exited anything. Phase B simulates a locked entry/exit rule walk-forward on the native daily basis (legitimate here — no instrument wall, by the same escape clause as the pre-test) and asks whether realistic capture nets positive after real costs.

## 1. Phase A — funding reality (measurement, no verdict)

- Pull funding-rate history (public endpoint, no auth) for the 44 qualified instruments over the cached 400-day window; cache to `output/funding_cache/`.
- Compute: per-instrument funding distribution; **pair-level 10-day net funding cost** = |Σ over 30 periods of (r_long − r_short)| × $100 per leg-side convention at $200 gross — reported as a distribution across (pair, window) samples, not a point.
- Deliverable: replace the {$0.44, $0.74, $1.94} assumed stacks with measured percentiles (p50 / p90 / p99) of the real pair-level stack. These percentiles feed Phase B's cost model.

## 2. Phase B — capture-realism walk-forward (LOCKED spec)

**Strategy rule (single family, small pre-committed grid — no parameter additions after data exists):**
- Discovery: 120-bar window, EG p ≤ 0.05, refreshed every 20 bars (the pre-test's folds).
- Signal: z = frozen-β spread residual / discovery-window σ_s.
- **Entry:** |z| ≥ z_entry at day-t close → position opened at day **t+1 close** (one-day lag locks out close-timing lookahead). β-aware sizing per H1, $200 gross.
- **Exit (first-of):** |z| ≤ z_exit (reversion target) · |z| ≥ 4.0 (divergence stop, fixed) · frozen-β ADF p > 0.20 on the rolling 120-bar window (the daily coint-watch, fixed) · 20-day max hold (fixed, = the surviving horizon). Exits execute at next-day close (same lag rule).
- **Grid (6 cells, LOCKED):** z_entry ∈ {1.5, 2.0, 2.5} × z_exit ∈ {0.0, 0.5}. Ridge logic per the D1 pattern: a verdict cannot rest on one cell; **≥ 2 adjacent cells** (neighboring z_entry at same z_exit, or the two z_exit at same z_entry) must qualify.
- **Costs per trade:** $0.14 entry+exit (program convention) + Phase A's **measured p50 funding** for the realized hold length; robustness leg at **p90 funding + 2× slippage** ($0.28). A qualifying cell must be net-positive at BOTH cost levels.
- **Concurrency realism:** trades simulated independently; portfolio view reported with max K=5 concurrent positions (first-come, capacity-dropped entries logged). Pooled economics gated on the independent view; the K=5 view is reported context for the spec.
- **No-lookahead protocol:** all signals from data ≤ t; discovery windows end ≥ 1 bar before entry signal evaluation; fold boundaries identical to the pre-test.

## 3. Phase B verdicts (LOCKED at this commit, before any backtest exists)

> **DESIGN-VIABLE** — a ridge (≥2 adjacent cells) where pooled net PnL is positive at BOTH cost levels (p50, and p90+2×slippage), with ≥ 30 simulated trades per qualifying cell AND ≥ 10 distinct pairs contributing AND no single pair contributing > 40% of a cell's net (concentration guard). Routes to: write the experiment spec — **paper-first is pre-committed** (forward signal-tracking on live daily closes, no orders, pre-committed length and criteria locked in the spec); live only after paper validates. Mandatory caveats carry: backtest ≠ forward performance; daily closes are fill proxies.
>
> **DESIGN-DEAD** — no cell net-positive even at the p50 cost level, or positivity exists only as a single-cell spike, or only via concentration (one pair carrying a cell). The premise survives but capture doesn't reach it at $200 gross with this rule family. Routes to: D3 closes at the design level; remaining options G (class pivot) or stop. **Lock: written as cleanly as Lever-B-DEAD if it fires.** No post-hoc grid extensions, no "the rule family was wrong" retreat — the family was locked as adequate here.
>
> **DESIGN-AMBIGUOUS** — named sub-causes, un-blurrable: **RIDGE-DIES-UNDER-STRESS** (positive at p50, dies at p90+2×slippage → cost-tail question routes to operator) · **UNDERPOWERED** (< 30 trades per cell or < 10 pairs — the signal fires too rarely to test, itself informative about sample-accumulation timeline) · **CONCENTRATION** (net rests on ≤ 3 pairs — fragile, routes to universe question) · **GRAY** (mixed cells, no ridge). Routes to operator with sub-cause as routing input.

**Lock direction (binding):** the program just got its first wanted answer and the operator said proceed — every pressure points toward VIABLE. Borderline resolves DOWN. The grid does not grow. Single-cell heroes are pre-named noise. The concentration guard cannot be waived because "those pairs look solid."

## 4. Design-phase deliverable (only if B fires VIABLE)

The experiment spec document, containing: frozen strategy parameters (the ridge's cells, one chosen, justified); paper-validation protocol (length ≥ 8 weeks or ≥ 10 completed paper trades, whichever later — locked here); success/null criteria and the negative-result bar for the paper period; kill-criterion (E4-analogue at daily scale — to be derived from Phase B's observed failure modes, locked in the spec before paper starts); build scope (the daily-swing runner is NEW lightweight build, not the minute-scale bot — H1 β-sizing transfers, basis alignment N/A by construction, circuit-breaker semantics re-scoped per the v1.5 §10 standing note); sample-accumulation timeline from Phase B's observed trade frequency.

## 5. Guardrails

Read-only throughout the design phase; public endpoints only; no bot contact; no imputation; dropped-data reported; verdict artifacts to `docs/audits/`; the one-re-spec precedent does NOT apply here (nothing is being reconstructed — native basis); implementation bug-fixes are repair, not re-spec (D1 contract-multiplier precedent).

---

*D3 design-phase work item v1.0, 2026-06-11. Phase B verdicts and grid locked at commit time, before any backtest code or output exists. Phase A is measurement (no verdict surface). Routes from D3-PREMISE-SUPPORTED (commit 681ab19). Paper-first pre-committed on VIABLE. Lock direction: borderline resolves DOWN; the program's first wanted answer gets the most scrutiny, not the least.*
