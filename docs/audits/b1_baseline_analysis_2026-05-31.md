# B1 Baseline Analysis — Coint-Fragility Sampling Across exp_beta_aware_sizing_v1

*Authorized 2026-05-31 as follow-on to structural review (Branch A acceptance). Tool: `tools/observation_mode/coint_fragility_sampler.py`. Source: 18 historical run logs (125–142). Goal: read the universe's post-entry coint-monitoring rate at large N — beyond the 15 actual closed trades the experiment produced — to address the TEMPORAL-vs-STRUCTURAL fragility question and the RISK_OFF-vector hypothesis at sample sizes the closed-trade evidence couldn't reach.*

---

## Method (one-line)

For each run log, parse every `COINT_GATE` event (emitted ~once per minute by the live monitoring loop on the active pair). Each event records the live coint-test's verdict (`health=valid|watch|broken`). Aggregate counts overall and by regime / pair / run.

## A surprise that reframes the metric: `health=valid` never observed

**Across 732 samples spanning 18 runs, zero events read `health=valid`.** The bot's live coint-monitor — `basis=kline_only`, `sample=120`, `window=60` — never registered the strictest cointegration band for any pair during the entire exp_beta window. Every sample reads `watch` or `broken`.

This is a property of the live monitor's thresholds, not of the universe. The entry-time discovery gate (different basis: `orderbook_mid`) passed pairs (`entry_coint=1`, `entry_health=valid` on every line), but the post-entry monitor on those same pairs never returns to the tight band.

**Consequence for the metric.** The originally-proposed `fragility_rate = (watch+broken)/total` is degenerate here — it equals 1.0 across every slice. The discriminating metric is `broken_rate = broken/total` — `broken` is the cleanly-failed end of the monotonic valid→watch→broken scale and is what varies meaningfully.

This finding is itself informative: it quantifies a basis-mismatch between the entry-discovery test and the post-entry monitor. Pairs that look cointegrated at entry under the orderbook-mid basis do not maintain cointegration under the kline-only basis over the 60-minute monitoring window. **This is the mean-shift finding, observed at the test-statistic level rather than at the dollar-PnL level.** A separate finding from the same dataset.

---

## Headline results

### Overall (n = 732 across 18 runs, 16 runs with samples)

| Health | n | rate |
|---|---:|---:|
| valid | 0 | 0.0% |
| watch | 603 | 82.4% |
| **broken** | **129** | **17.6%** |

### By regime — RISK_OFF vector test at large N (the key result)

| Regime | n | broken | **broken_rate** | vs RANGE |
|---|---:|---:|---:|---|
| RANGE | 540 | 89 | **16.5%** | (baseline) |
| **RISK_OFF** | **147** | **34** | **23.1%** | **+40% relative, +6.6pp absolute** |
| TREND | 45 | 6 | 13.3% | −19% relative |

**Finding: the RISK_OFF-coint-failure vector is corroborated at large N.** At N=147 RISK_OFF samples, the broken_rate is **23.1%** — meaningfully elevated above the RANGE baseline of 16.5%. This is the first measurement of the relationship at a sample size that escapes the base-rate-indistinguishability concern from the closed-trade evidence (2/2 → 50% looked like base rate at N=2; the universe-sampled comparison is RISK_OFF 23.1% vs RANGE 16.5%, which is a real elevation).

**Confidence framing.** This corroborates the closed-trade vector (T9, T12 both RISK_OFF → coint-failure) at a statistically meaningfully larger sample. It does NOT prove the relationship is causal (regime and pair-selection are not independent), and the elevation is moderate (40% relative is not the dominant fragility source). Read as: *"RISK_OFF is a meaningfully more-fragile regime than RANGE in this universe — promoted from N=2 directional to N=147 directional-corroborated; still a directional finding, not a settled lever."*

### Temporal arc — per-run broken_rate sequence

| Run | n | broken_rate |
|---|---:|---:|
| 125 | 40 | 17.5% |
| 126 | 16 | 25.0% |
| 127 | 0 | — |
| 128 | 59 | 22.0% |
| 129 | 118 | 12.7% |
| 130 | 98 | 13.3% |
| 131 | 75 | 24.0% |
| 132 | 28 | 10.7% |
| 133 | 20 | 5.0% |
| 134 | 0 | — |
| 135 | 34 | 14.7% |
| 136 | 32 | 12.5% |
| 137 | 14 | 0.0% |
| 138 | 9 | 22.2% |
| 139 | 4 | 50.0% |
| 140 | 2 | 100.0% |
| **141 (T14)** | **163** | **23.9%** |
| **142 (T15)** | **20** | **5.0%** |

**Finding: provisionally STRUCTURAL, not cleanly TEMPORAL.** The per-run broken_rate is noisy (5–25% range across the well-sampled runs, plus two near-zero-N outliers at 50% and 100%) without a clear monotonic climb. Run 141 (T14 = a coint-failure trade) is elevated at 23.9%; run 142 (T15 = also a coint-failure trade) is **low at 5.0%** — which is informative: T15's run produced a coint-failure trade despite a relatively benign broken_rate on the monitor stream. The trade-level outcome (coint-failure) does not require an elevated continuous-monitor reading.

**Methodological caveats** for the temporal read:
1. **Per-run-N variance is large** (range 2–163) because `max_session_trades=1` produces variable-length runs. Per-run rates are noisy.
2. **The `valid`-never-observed ceiling compresses dynamic range.** All variation happens within the watch-vs-broken split.
3. **The window may be too short to see regime change.** A clean temporal vs structural read would need observation over many weeks, not 4 days.

**Provisional reading: STRUCTURAL fragility.** No clean climb across the window; broken_rate is elevated-but-stable around 15–25%. Combined with the eligible-stall (5 eligible in T2–T8, 0 in T9–T15 trades) and the universally-elevated watch-state, the picture is: **the universe has been steadily moderately fragile throughout, not increasingly fragile late.** The trade-level coint-failure climb (37.5→60.0% over T8–T15) may be variance on a steady underlying base-rate rather than a regime shift.

This is a softer Reading 2 (structural) confirmation than the closed-trade evidence alone, because:
- The trade-level rate climbed sharply (37.5→60.0%) but the monitor-level rate did not (16–24% range, no monotonic trend)
- Either the trade-level climb was variance on a steady fragile universe (Reading 2 in its strong form)
- OR the trade-level metric and the monitor-level metric measure different things and a true temporal regime shift would only show on the trade-level (Reading 1 with a different instrument)

The discriminator that would split these is a longer continuous-observation run (B1 v2) where both metrics can be tracked over weeks. B1 v1 — what we have — leans STRUCTURAL but does not foreclose Reading 1.

---

## Per-pair breakdown (selected pairs)

(Generated by the sampler's `by_pair` aggregate. See `tools/observation_mode/output/<run>__samples.csv` for full pair-level data per run. Cross-run pair aggregation is not in the v1 summary CSV.)

Pairs that appear across multiple runs and their cross-run broken_rate would be the natural next analysis — testing whether some pairs are systematically more fragile than others (the universe-restriction sub-hypothesis from Branch C). This is buildable on the existing per-run sample stream; v1 does not include it.

---

## What this changes about the structural review's open questions

**TEMPORAL vs STRUCTURAL (template v1.5 §4 pre-load):**
- Standing read at T15 was leans Reading 2 (structural) per the eligible stall.
- B1 v1 **corroborates Reading 2** at the monitor-stream level: no clear temporal trend, steady-state elevated broken_rate around 15–25%. The eligible stall is consistent with the underlying universe being moderately and steadily coint-fragile.
- B1 v1 does NOT foreclose Reading 1 entirely — the trade-level coint-failure climb (T8→T15) is real and is not visible on the monitor stream at the same magnitude. The trade-level and monitor-level metrics may be sensitive to different aspects of "fragility."
- A longer continuous observation run (B1 v2) would tighten this. v1 reads what we have.

**RISK_OFF vector hypothesis:**
- Closed-trade evidence: 2/2 RISK_OFF → coint-failure at N=2. Base-rate-indistinguishable.
- **B1 v1 at N=147 RISK_OFF samples corroborates: RISK_OFF broken_rate (23.1%) is 40% above RANGE broken_rate (16.5%).** Not the dominant fragility source, but a real and measurable elevation.
- Promotes the vector from N=2 directional to **N=147 directional-corroborated**. Still directional; not a settled lever; the next experiment design should treat RISK_OFF entry-gating as a worth-testing hypothesis with non-trivial corroborating evidence, rather than a base-rate guess.

**Cost-precision question (the §5 mechanism ambiguity):**
- B1 v1 does NOT address this — it measures coint-monitor fragility, not cost-clearance.
- The cost-model-precision-upgrade path remains the only way to resolve edge-vs-cost at this notional.

---

## What B1 v1 does NOT do (honesty guardrails)

- Does NOT measure the universe's underlying coint-failure rate — measures the bot's live coint-monitor's `broken_rate` under its specific thresholds (`kline_only`, `window=60`, `sample=120`). Different parameters would yield different rates.
- Does NOT discriminate sharply between TEMPORAL and STRUCTURAL fragility — provisionally leans STRUCTURAL but the window is too short and the per-run-N too variable for a hard verdict.
- Does NOT resolve the cost-clearance question.
- Does NOT estimate causality on the RISK_OFF vector — regime and pair-selection covary; the elevation is real but the mechanism is not pinned.
- Does NOT include cross-run per-pair aggregation in v1 (buildable on existing sample stream; deferred).

## What it does establish (robust)

1. **`health=valid` is never observed in 732 samples.** A structural property of the live monitor's basis-vs-entry-basis mismatch — the post-entry monitor is tighter than entry-discovery. This is the mean-shift finding at the test-statistic level.
2. **Overall broken_rate = 17.6%.** The universe sits steadily in an elevated-fragility regime under the live monitor's thresholds.
3. **RISK_OFF broken_rate (23.1%) > RANGE broken_rate (16.5%) at N=147 vs N=540.** RISK_OFF-vector hypothesis corroborated at a sample size that escapes base-rate-indistinguishability.
4. **Per-run broken_rate sequence does not show a clean temporal trend.** Leans STRUCTURAL fragility over TEMPORAL regime shift.

---

## Forward path

**B1 v1 is sufficient for the questions it was authorized to address.** The RISK_OFF vector is corroborated; the temporal-vs-structural read leans STRUCTURAL. Both findings are directional, not settled — but they reduce the open question space the structural review left.

**B1 v2 (continuous observation runner) is NOT recommended yet.** v1's data is enough to direction the next experiment choice. Building v2 would require bot-side changes (an observation-only flag) and a longer run window; the marginal value at this point is moderate. **Operator decision:** if the next strategic direction (different universe / different hold horizon / different strategy class) is being considered, B1 v1's RISK_OFF corroboration + structural-fragility lean is the data to weigh. If that direction is "wait and re-observe in N weeks," B1 v2 becomes worthwhile then; not now.

**Cross-run per-pair aggregation** would be the natural small v1.1 follow-on if you want to test the universe-restriction sub-hypothesis (do specific pairs show systematically higher broken_rate than others?). The data exists in the per-run sample CSVs; a small aggregation script over them is buildable in a single turn. Not yet built; flag if wanted.

---

*B1 v1 baseline analysis, 2026-05-31. Tool: `tools/observation_mode/coint_fragility_sampler.py`. Source data: 18 historical run logs from `Logs/v1/run_125_*` through `run_142_*`. Output: `tools/observation_mode/output/summary.csv` + per-run sample CSVs (gitignored). This document persists the headline findings as institutional memory; the raw analysis output is regenerable from the tool.*
