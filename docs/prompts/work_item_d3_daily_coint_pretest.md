# Work Item — D3 Daily-Bar Cointegration Pre-Test
## Read-only / analysis-only on public 1D klines. No trades, no bot contact, no frozen-variable touch.

**Authorized 2026-06-11** (operator: "proceed that direction," post-D1 INFEASIBLE closure). Tests the premise of Direction 3 (multi-day swing on the same universe): **do daily-bar cointegrating relationships on the exp_beta instrument universe survive over multi-day hold horizons at a rate that could support a swing-scale pairs strategy, with per-trade edges that clear the multi-day cost stack?**

**Task class:** READ-ONLY analysis. One fresh pull of public 1D klines (OKX history-candles, no auth); all computation offline. No trades, no live trade API, no bot code paths.
**Drafted:** 2026-06-11, verdicts locked BEFORE the data pull (this commit precedes any 1D bar being fetched).
**Owner split:** code assistant drafts the whole item including verdicts (operator directed proceed); the pre-commit-before-data discipline is the protection — verdicts and thresholds in this document are locked at commit time and cannot move after the data exists. Operator/strategist may amend ONLY before the pull begins.

---

## 0. Why this pre-test is feasible where D1's was not (the instrument question, settled by design)

The D1 pre-test died on INFEASIBLE-INSTRUMENT: the bot's minute-scale internal basis (orderbook-mid, per-tick OLS β) is a private coordinate system, unreproducible from public data — four converging diagnostics. **D3 escapes that wall by construction:** a daily-bar swing strategy would compute its signals from public daily closes. Public 1D klines are not a proxy for a private mark here — they ARE the native basis of the contemplated strategy. The instrument being validated and the instrument being deployed are the same object. INFEASIBLE-INSTRUMENT is not applicable to this design (the meta-finding's escape clause (b)/(c): "operate at a timescale where public data is the native basis").

Consequence: there is no reconstruction gate. If an implementation bug is found mid-run, fixing it is repair (D1 contract-multiplier precedent); there is no re-spec surface because nothing is being reconstructed.

---

## 1. Data specification

- **Universe:** the 46 USDT-SWAP instruments that appeared in the bot's monitored pairs during the exp_beta window (extracted from B1 v1 per-run sample CSVs). Pairs = all C(46,2) = 1,035 unordered combinations. All-combinations (not just the 129 observed pairs) avoids selecting on the bot's minute-scale choices; deployment filtering is a later question.
- **Bars:** 1D klines, up to 400 most-recent complete bars per instrument (≈ May 2025 → June 2026), OKX history-candles public endpoint, cached to `tools/observation_mode/output/kline_cache_1d/<INST>.csv`.
- **Insufficient history:** instruments with < 140 complete daily bars are dropped (no imputation); pairs require both legs present with ≥ 120 overlapping bars in a discovery window plus the forward horizon. Report dropped instruments and coverage.

## 2. Mechanics

- **Spread spec (program convention):** `spread(t) = log p1(t) − β·log p2(t) − c`, β and intercept c from OLS on the discovery window.
- **Discovery:** window = 120 daily bars. Pass = Engle-Granger cointegration test (statsmodels `coint`, EG-corrected p-values) **p ≤ 0.05** — mirrors the monitor's `valid` band.
- **Survival at horizon H ∈ {+5, +10, +20} calendar days (THE GATED QUANTITY, frozen-β):** hold the discovery β and c **frozen** (a held position's hedge is frozen — this is exactly the quantity whose minute-scale failure was MR's mean-shift death), compute the spread over the 120-bar window ending at discovery-end + H, run plain ADF (`adfuller`; valid without EG correction because β was NOT fit on the test window). **Survival = p ≤ 0.20** — mirrors the monitor's broken threshold (>0.20 = broken). Strict survival (p ≤ 0.05) and refit-β survival reported as context, NOT gated.
- **Walk-forward folds:** discovery windows ending every 20 days across available history (~14 folds at full 400-bar depth). Each (pair, fold) with a discovery pass = one observation; pooled across folds.
- **β-drift report:** |Δβ|/β between discovery and +H windows (refit), reported not gated — daily-scale mean-shift's cousin.

## 3. Part B — edge-vs-cost arithmetic (secondary premise)

For each surviving (pair, fold): dollar edge proxy = **2 × σ_s × $200** (a 2σ→mean reversion in log-spread terms at $200 gross; σ_s = std of discovery-window spread residuals). Cost stack for a 10-day hold = $0.14 entry/exit + funding on $200 total notional at {0.005%, 0.01%, 0.03%}/8h × 3/day × 10 days = stacks of **{$0.44, $0.74, $1.94}**. Funding is assumption-based (not pulled); directionality: real funding varies and can be received not paid — the middle assumption is the gate, sensitivity reported at all three. **Gate: median dollar edge of surviving observations ≥ 3 × $0.74 = $2.22.**

## 4. Pre-committed verdicts (LOCKED at commit, before any bar is pulled)

> **D3-PREMISE-SUPPORTED** — pooled frozen-β survival **≥ 70% at +10d AND ≥ 50% at +20d**, with N-guards met (≥ 30 (pair, fold) observations AND ≥ 8 distinct pairs contributing), AND Part B median edge ≥ $2.22. Routes to: scope the D3 experiment design (paper-vs-live, sample-accumulation timeline — weeks per trade — and the full apparatus). Mandatory caveats: funding assumption-based; survival ≠ profitability; this is premise-support, not a backtest.
>
> **D3-PREMISE-DEAD** — pooled frozen-β survival **≤ 40% at +10d** with N-guards met. 40% is the minute-scale analogue: trade-level coint-failure ran 60% (⇒ ~40% survival over a hold), and that rate is what killed MR. If daily-scale survival is no better, the timescale hypothesis is falsified — relationships on this universe don't stabilize with timescale. Routes to: D3 closes; remaining options are G (strategy-class pivot) or stop, both genuinely the operator's. **Lock: written as cleanly as Lever-B-DEAD and D1-INFEASIBLE.** No retreat to "wrong window length" or "wrong threshold" — these were locked before the data existed.
>
> **D3-PREMISE-AMBIGUOUS** — anything between, with the firing sub-cause named (un-blurrable):
> 1. **GRAY-ZONE** — survival between 40% and 70% at +10d. The premise is neither supported nor refuted at this universe/window.
> 2. **UNDERPOWERED** — N-guards unmet (< 30 observations or < 8 distinct pairs passing discovery). Few daily-scale cointegrations exist to even test — itself informative about the universe.
> 3. **EDGE-FAILS-COSTS** — survival ≥ 70%/50% but Part B median edge < $2.22. Relationships hold but the captured move doesn't clear the multi-day stack at $200 gross.
> 4. **UNIVERSE-COVERAGE** — < 10 instruments qualify with sufficient 1D history. The pull can't represent the universe.
>
> Routes to: operator's call with the sub-cause as the routing input.

**Lock direction (binding):** D3 is the last cheaply-testable direction standing — the program's momentum wants SUPPORTED. Therefore borderline resolves DOWN (toward AMBIGUOUS, never up to SUPPORTED); thresholds do not move after data exists; a single spectacular fold or pair does not carry a verdict (pooled quantities only).

## 5. Guardrails

Read-only; public endpoint, no auth; no bot contact; no imputation; dropped-data reported; verdict artifact persisted to `docs/audits/`; same stop-and-report posture as every prior gate.

---

*D3 daily-coint pre-test work item v1.0, 2026-06-11. Verdicts and thresholds locked at commit time, before any 1D bar was pulled. Sequenced after D1 INFEASIBLE closure per strategist's landscape re-ranking (D3 holds the only viable offline pre-test; testability is a sequencing virtue, not a truth claim — the direction was the operator's pick). Universe: 46 instruments / 1,035 pairs from the exp_beta monitored set. Gated quantity: frozen-β survival (the daily-scale analogue of the mean-shift exposure that killed MR). Tools: `tools/observation_mode/d3_daily_coint_pretest.py` (to follow this commit).*
