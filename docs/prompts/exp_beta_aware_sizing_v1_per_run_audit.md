# Per-Run Audit Template — exp_beta_aware_sizing_v1

**Use this template for every run in the exp_beta_aware_sizing_v1 window that closes at least one trade.**
**Stop using it when trades_since_experiment_start ≥ 20. Use the structural review template instead.**

---

## Experiment State Block (Required at Top of Audit)

Report verbatim:

```
experiment_group: exp_beta_aware_sizing_v1
runs_since_experiment_start: [list]
trades_since_experiment_start_entering_this_run: [N]
trades_since_experiment_start_after_this_run: [N+closed]
trades_remaining_to_action_threshold: [20 − count]
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7, Patch 7.1, Patch 7.2, Beta-Aware Sizing
sizing_mode: gross_normalized_beta (Option C) — STATBOT_HEDGE_RATIO_SIZING_ENABLED=true
```

If trades_since_experiment_start crosses 20 in this run, do NOT use this template. Use the 20-trade structural review template instead.

---

## Data Sources

```
Reports/v1/<run_id>/
  config_snapshot.json
  trade_closes.csv            ← entry_coint_stability_slope, entry_coint_stability_evaluated_count
  exit_decision_trace.csv
  exit_opportunity_summary.csv
  entry_rejections.csv        ← entry_gate_component_scores now includes hedge_ratio
  reconciliation_checks.csv
  liquidity_checks.csv
bot log                       ← BETA_SIZING log line (primary β-sizing telemetry source)
```

---

## Pre-Audit Config Verification

Confirm before any analysis:

- `STATBOT_HEDGE_RATIO_SIZING_ENABLED = true`
- `STATBOT_MIN_HEDGE_RATIO = 0.20`
- `STATBOT_MAX_HEDGE_RATIO = 5.00`
- `STATBOT_ENTRY_COINT_STABILITY_ENABLED = true`
- `STATBOT_ENTRY_COINT_STABILITY_SLOPE_MAX = 0.020`
- `STATBOT_FULL_TP_GUARD_MULTIPLIER = 0.50`
- ETHFI-USDT-SWAP, HMSTR-USDT-SWAP, FLOKI-USDT-SWAP permanently graveyarded with `ttl_days: null`
- All frozen variables unchanged (exit z-thresholds, max_break_risk=0.12, notional=$200 gross, circuit breaker, profit-lock giveback=0.50)

If any verification fails, halt audit and report the discrepancy.

---

## Section 1 — Run Summary (Telemetry Only, No Interpretation)

Report:

- duration (hours)
- total entry signal gate evaluations
- total entry attempts
- total accepted trades
- total rejected entries
- closed trades count
- open trades at run end
- realized session PnL
- win count / loss count / win rate
- avg win, avg loss
- avg hold duration
- pair switches
- circuit breaker status and trip reason (if any)
- consecutive_loss progression (session and persistent counters)

Do not compare to prior runs in this section. Just report.

---

## Section 2 — Per-Trade Telemetry (Required for Every Closed Trade)

For each closed trade, report:

- pair
- entry regime
- entry z-score
- exit z-score
- exit reason
- hold duration (minutes)
- gross MFE
- MAE
- net PnL (equity delta)
- post-entry cointegration status at close
- outcome (win / loss)

---

## Section 3 — β-Sizing Mechanical Verification (Primary Experiment Section)

**This section is the primary experiment measurement. Complete it for every closed trade.**

### 3A — BETA_SIZING Log Line (Per Trade)

For each accepted trade, locate the `BETA_SIZING` log line at entry time in the bot log.

| Field | Value |
|---|---|
| pair | |
| beta (hedge_ratio at entry) | |
| gross (should equal 200.00) | |
| capital_long | |
| capital_short | |
| side (positive_z / negative_z) | |
| leg1_expected = gross/(1+β) | (compute and compare to capital for that instrument) |
| leg2_expected = gross×β/(1+β) | (compute and compare) |
| gross_check: capital_long + capital_short | (should equal 200.00 exactly) |
| fallback_used (equal_notional) | yes / no |

**If BETA_SIZING line is absent:** report `MISSING` — sizing may have fallen back to equal-notional silently. Check for `BETA_SIZING_INVALID` log line; if that is also absent, the sizing block was not reached (flag as bug).

**Post-restart check:** If this run followed a bot restart, the first trade's BETA_SIZING line warrants extra scrutiny. After a restart, `metrics` and pair state are rebuilt from scratch; if the first trade enters before a full evaluation cycle completes, `metrics["hedge_ratio"]` may be None or 0, triggering the equal-notional fallback. Check: did the first post-restart trade use a sensible β or fall back? If fallback was used on the first post-restart trade due to metrics not yet populated → expected behavior, note it and move on. If fallback was used on a subsequent trade with no restart explanation → flag as bug.

**If fallback_used=yes:** record the reason from `BETA_SIZING_INVALID` log line (invalid β, out-of-bounds, etc.). Fallback is expected only when β is outside [0.20, 5.00] or metrics["hedge_ratio"] is None/0. Fallback on an in-range β is a bug.

**First-trade staleness verification (perform on T1 only):**
Cross-reference `hedge_ratio` from the BETA_SIZING log against `hedge_ratio` in `entry_gate_component_scores` (entry_rejections.csv, the pre-entry rejection rows for the same pair and session). If they match → wiring is correct. If they diverge → hedge_ratio logging source and sizing source are misaligned; flag immediately.

After T1 verification passes, mark "hedge_ratio source verified" for subsequent runs.

### 3B — hedge_ratio in entry_gate_component_scores (Day 1 Telemetry)

From entry_rejections.csv, for rejection rows from this session:

- Does `entry_gate_component_scores` include `hedge_ratio` field? (yes / no)
- Sample hedge_ratio values from rejected-entry rows (report 2–3 examples)
- If hedge_ratio is absent from component_scores: this is a Day 1 telemetry failure — flag immediately

This field is present on every gate evaluation regardless of whether the trade was accepted. It is diagnostic infrastructure, not a gate criterion.

### 3C — $/σ Sign per Trade

**Primary diagnostic for exp_beta_aware_sizing_v1.** Compute for every normal-exit closed trade with meaningful z-movement (|Δz| ≥ 0.5).

```
$/σ = position_pnl / |Δz|
Δz  = |exit_z − entry_z|
```

- `position_pnl` from reconciliation_checks.csv (gross position PnL before fees/slippage)
- `entry_z` and `exit_z` from trade_closes.csv

| Field | Value |
|---|---|
| pair | |
| entry_z | |
| exit_z | |
| Δz (abs) | |
| position_pnl | |
| $/σ | |
| sign (positive / negative / zero) | |
| exit_reason | |

**Sign interpretation (record, do not conclude mid-window):**
- Positive $/σ: dollar PnL moved in same direction as z-reversion — β-sizing aligned with stat-arb assumption
- Negative $/σ: dollar PnL moved opposite to z-reversion — β-mismatch persists or other confound
- Zero/near-zero $/σ (|$/σ| < $0.01): PnL near flat despite z-movement — likely cost-dominated

**Exclusion rule:** Only compute $/σ on trades where MFE > 0 (position was at some point favorable — spread reverted at least partially before exit). If MFE ≤ 0 the spread never moved favorably and there is no reversion to align with; record as "N/A (MFE ≤ 0, no reversion)". This correctly handles T11-class cases (coint-failure with partial reversion then re-expansion) and avoids ambiguity over what "adverse spread divergence" means — MFE is objective.

Additionally exclude trades with |Δz| < 0.5 regardless of MFE, as the signal is too weak to interpret. Record as "N/A (Δz < 0.5)".

Do not conclude from $/σ sign mid-window. Record and report.

### 3D — Running $/σ Sign Stability Table (Cumulative, Normal-Exit Trades)

Maintain this table across all normal-exit trades in the experiment window. Update each run.

| Trade # | Run | Pair | β | Δz | position_pnl | real_costs | edge_clears_costs | $/σ | Sign |
|---|---|---|---|---|---|---|---|---|---|
| T[N] | run_[X] | [pair] | [β] | [Δz] | [$] | [$] | yes/no | [$] | [+/−] |

`real_costs = position_pnl − equity_change` (total actual cost including fees, slippage, and unexplained).
`edge_clears_costs`: yes if position_pnl > real_costs (trade would have been profitable at zero cost); no otherwise. This is the viability signal — a correctly-sized, correctly-directional trade still needs position_pnl > real_costs to be viable.

After each run, report:
- Trades with $/σ computed (MFE > 0, |Δz| ≥ 0.5): [N]
- Sign-positive count: [N]
- Sign-negative count: [N] (sign-flip rate = negative / total)
- Current sign-flip rate: [X%]
- Cumulative position_pnl $/σ in aggregate (sum of all $/σ values): [$]
- Trades where edge_clears_costs = yes: [N] / [total computed]
- Excluded trades (MFE ≤ 0 or Δz < 0.5): [N] with reasons

**Success criterion (multi-part, all required):**
1. Sign-flip rate ≤ 10% (≤ 2 of 20 normal-exit trades with MFE > 0 and |Δz| ≥ 0.5)
2. Cumulative position_pnl $/σ in aggregate > 0 (dollar PnL tracks reversion in net)
3. Cumulative PnL improvement vs equal-notional baseline (counterfactual δ > 0 over the window)

**Null-result caveat (record at structural review):** The counterfactual showed 1 sign flip in 10 trades under equal-notional (10% rate). If β-sizing produces exactly 1–2 sign flips in 20 trades (10%) with no cumulative $/σ improvement, the result is **null** — β-sizing made no difference — not success. Criterion 2 (aggregate $/σ > 0) is what distinguishes "didn't make things worse" from "demonstrably improved alignment." If criterion 1 passes but criterion 2 fails, state result as null.

Do not declare success or failure before 20 trades. Record direction each run.

### 3E — β Distribution Tracker (Cumulative)

Maintain a running record of β values across all accepted trades. Update each run.

| Trade # | Run | Pair | β at entry | Within bounds [0.20–5.00]? | Fallback used? |
|---|---|---|---|---|---|
| T[N] | run_[X] | [pair] | [β] | yes/no | yes/no |

After each run, report:
- β range observed (min, max across all trades so far)
- Trades with β < 1.0: [N] / total: [N]
- Trades with β outside [0.8, 1.2] (materially non-unity): [N] / total: [N]
- Fallback (equal-notional) activations: [N]

**Why this matters:** the counterfactual confirmed β range [0.471, 1.433] in the previous window. If this window's β distribution is concentrated near 1.0, the cumulative $/σ improvement from β-sizing will be small — which is not evidence β-sizing failed, but that the sample lacked pairs with material β deviation. The β distribution is a prerequisite for interpreting the $/σ result at the structural review.

**Structural-review preparation note (add to 20-trade review):** Compare this window's β distribution to the counterfactual's β distribution ([0.471, 1.433], 7/10 below 1.0, 3/10 outside [0.8, 1.2]). If the populations look similar → the experiment tested sizing on a comparable pair universe and the counterfactual's predicted effect should approximately materialize. If this window's β is clustered near 1.0 with few tail values → the experiment hit a lower-deviation pair universe; the predicted +$0.988 effect does not apply and more trades are needed to see meaningful sizing differences. State this comparison explicitly before drawing conclusions about β-sizing effectiveness.

---

## Section 4 — Reconciliation Telemetry

For each closed trade:

- gross PnL (position-level, from reconciliation_checks.csv)
- equity delta
- fees + slippage estimated ($0.14 flat estimate)
- unexplained residual (equity_delta − position_pnl + fees + slippage)
- reconciliation basis (pre_close_equity_delta / position_pnl)
- reconciliation result (PASS / FAIL) and reason if FAIL

Flag any trade where unexplained residual exceeds $0.05 and a restart scenario was not active.

**Reconciliation basis disposition rule:**
- basis=position_pnl → OKX fee API not yet settled; fees=0; PnL unreliable. **Exclude from economic analysis.** Gate/β-sizing analysis valid.
- basis=pre_close_equity_delta → equity change reliable; cost attribution may fail but PnL total is correct. **Include in economic analysis; mark costs as unattributed.**

**Execution cost sub-pattern tracker (cumulative):**
Meme/thin-pair negative residual history:
- HMSTR (run_102): −$0.226 → graveyarded
- FLOKI (run_111): −$0.093 → graveyarded
- FIL/ICP (run_118, T10): −$0.255 (FIL ratio 5.76, barely above floor) → costs 2.8× model

If this run produces a new negative-residual occurrence on a non-graveyarded pair: report pair, notional, liquidity ratio, and magnitude. Third thin-pair occurrence → route to structural review as category-exclusion proposal.

---

## Section 5 — Coint Stability Gate Status (Maintenance Reporting)

Patch 7/7.1 remain active. Report gate activity as maintenance telemetry — this experiment is not measuring the gate, but the gate data should not be silently dropped.

For each closed trade, report:
- `entry_coint_stability_slope` (from trade_closes.csv)
- `coint_stability_check_evaluated_count` (from trade_closes.csv)
- gate_status: evaluated / insufficient_history / not_reached

Session aggregate from entry_rejections.csv:
- `coint_stability_slope_exceeded` block count and distinct pairs blocked (if any)
- Total evaluated vs insufficient_history counts

**Do not route gate findings to the structural review as the primary signal.** Gate premise was assessed NEGATIVE in exp_coint_stability_v1 structural review (2026-05-28). Report gate activity for completeness only.

---

## Section 6 — Entry Rejection Distribution

Report rejection reason counts from entry_rejections.csv:

- `strategy_gate` (coint_invalid or similar)
- `entry_safety_gate` (all reasons)
  - `advanced_ml_break_risk_high`
  - `liquidity_at_floor`
  - `trade_quality_gate`
  - `statarb_mr_trend_regime_block`
  - `risk_off_thin_liquidity`
  - `cointegration_component_below`
  - `coint_stability_slope_exceeded`
  - other
- Total rows

Report break_risk distribution at rejection (mean, median, max) if present.

---

## Section 7 — Counter Update and Next Step

Close the audit with:

```
trades_since_experiment_start: [updated count]
normal_exit_trades_with_sigma_computed: [N]       ← $/σ denominator
sign_flip_rate_so_far: [N negative / N total]     ← primary diagnostic
beta_range_observed: [min, max]
beta_fallback_activations: [N]
cumulative PnL (experiment window): [sum]
win rate (experiment window): [wins/total]
coint-exit losses so far: [count and $ sum]
trades_remaining_to_action_threshold: [20 − count]
next step: [if count < 20: "run [N+1] with frozen configuration"; if count ≥ 20: "20-trade Structural Review"]
```

No recommendations. No "next priority" lists. If trades_since_experiment_start < 20, the next action is the next run with frozen configuration.

---

## Section 8 — Forbidden Inferences (Audit Hygiene)

The audit must NOT contain:

- "β-sizing is working / not working" based on fewer than 20 normal-exit trades
- "$/σ sign flip rate is acceptable / unacceptable" before 20-trade threshold
- "β-sizing improves PnL" based on mid-window data (cumulative improvement requires 20-trade window)
- "β-sizing has no effect" because $/σ improvement is small (may reflect near-unity β distribution, not sizing failure)
- "the coint filter is / isn't working" — that experiment is closed; this section is maintenance telemetry only
- Any recommendation to adjust β bounds, exit z-thresholds, or notional mid-window
- Any narrative framing about the experiment's direction based on early trades

If language resembles the above, flag it and rewrite.

---

## Section 9 — Permitted Observations

The audit MAY contain:

- Factual per-trade BETA_SIZING log values (β, gross, capital_long, capital_short)
- Factual $/σ per trade (sign recorded, no interpretation)
- Factual running tally of sign-flip rate and β distribution
- Direct observation of β-distribution concentration (e.g., "7/8 trades had β < 1.0 — similar to counterfactual window")
- Direct observation of gross conservation (capital_long + capital_short = $200.00)
- Factual reconciliation anomalies
- Factual note on whether the run followed a restart and any post-restart effects
- Factual circuit-breaker state

---

*Template version: exp_beta_aware_sizing_v1 v1.2, created 2026-05-28.*
*v1.1 changes: $/σ exclusion rule tightened to MFE > 0; success criterion expanded to multi-part with null-result caveat; β-distribution structural-review comparison note added to 3E; post-restart check added to 3A.*
*v1.2 changes: 3D table adds real_costs and edge_clears_costs columns. real_costs = position_pnl − equity_change. edge_clears_costs tracks whether the correctly-sized captured edge exceeds actual execution costs — the viability signal that sign alone cannot provide. Rationale: T2 (LTC/KSM) demonstrated a positive-sign, correctly-sized position (+$0.146) converted to a loss by 1.8× cost overrun ($0.251 real vs $0.14 estimated). Sign tracks β-sizing correctness; edge_clears_costs tracks strategy viability once sizing is fixed.*
*Primary diagnostic: $/σ sign stability — sign-flip rate ≤ 10% AND aggregate $/σ > 0 over 20 normal-exit trades with MFE > 0.*
*Sizing mode: Option C gross-normalized-beta. Sources: BETA_SIZING bot log line (per-trade β and leg sizes); entry_gate_component_scores hedge_ratio field (CSV telemetry).*
*Coint stability gate remains active but its premise was assessed NEGATIVE in prior structural review — report as maintenance telemetry only.*
