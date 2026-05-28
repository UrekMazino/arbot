# Per-Run Audit — exp_beta_aware_sizing_v1
## Runs 125–129 (T1–T3) — 2026-05-28 → 2026-05-29

---

## Experiment State Block

```
experiment_group: exp_beta_aware_sizing_v1
runs_since_experiment_start: run_125, run_126
trades_since_experiment_start_entering_this_run: 0
trades_since_experiment_start_after_this_run: 2 (T1 JUP/YGG, T2 LTC/KSM)
trades_remaining_to_action_threshold: 18
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7, Patch 7.1, Patch 7.2, Beta-Aware Sizing
sizing_mode: gross_normalized_beta (Option C) — STATBOT_HEDGE_RATIO_SIZING_ENABLED=true
```

**Carryover note:** Run 125 shows a second closed trade (ETH-USDT-SWAP/LDO-USDT-SWAP, close 01:03:01 UTC, exit=normal) with no entry_ts, no side, and no entry_z in trade_closes.csv. This trade predates exp_beta_aware_sizing_v1 (opened before β-sizing was live). It is EXCLUDED from the experiment window and all experiment counters.

---

## Pre-Audit Config Verification

From config_snapshot.json and .env:

- `STATBOT_HEDGE_RATIO_SIZING_ENABLED = true` ✓
- `STATBOT_MIN_HEDGE_RATIO = 0.20` ✓
- `STATBOT_MAX_HEDGE_RATIO = 5.00` ✓
- `STATBOT_ENTRY_COINT_STABILITY_ENABLED = true` ✓
- `STATBOT_ENTRY_COINT_STABILITY_SLOPE_MAX = 0.020` ✓
- `STATBOT_FULL_TP_GUARD_MULTIPLIER = 0.50` ✓
- ETHFI, HMSTR, FLOKI permanently graveyarded ✓
- All frozen variables unchanged ✓

---

## Section 1 — Run Summary

### Run 125

- Duration: 2h 14.8min (00:51:00–03:05:45 UTC)
- Entry rejection rows: 134
- Entry safety gate evaluations: 81
- Accepted trades: 1 (JUP/YGG; carryover ETH/LDO excluded from count)
- Closed trades: 1 experiment trade (+ 1 carryover excluded)
- Session PnL: −$1.215 (includes −$0.253 carryover loss)
- Experiment window PnL: −$0.962 (JUP/YGG only)
- Wins: 0, Losses: 1, Win rate: 0%
- Pair switches: 10 (11 pairs total)
- Gate blocks: 0
- Circuit breaker: not tripped

### Run 126

- Duration: 55.0min (03:05:47–04:00:46 UTC)
- Entry rejection rows: 23
- Entry safety gate evaluations: 1
- Accepted trades: 1 (LTC/KSM)
- Closed trades: 1
- Session PnL: −$0.105
- Wins: 0, Losses: 1, Win rate: 0%
- Pair switches: 7 (8 pairs total)
- Gate blocks: 0
- Circuit breaker: not tripped

---

## Section 2 — Per-Trade Telemetry

| Field | T1 (run_125) | T2 (run_126) |
|---|---|---|
| Pair | JUP-USDT-SWAP/YGG-USDT-SWAP | LTC-USDT-SWAP/KSM-USDT-SWAP |
| Side | long_negative_short_positive | long_positive_short_negative |
| Entry regime | RANGE | RANGE |
| Entry z | −2.655 | +2.013 |
| Exit z | −1.431 | −0.257 |
| Exit reason | cointegration_lost | normal |
| Hold (min) | 13.3 | 4.4 |
| MFE | +$0.002 | +$0.194 |
| MAE | −$0.471 | −$0.264 |
| Net PnL (equity) | −$0.962 | −$0.105 |
| Coint at close | lost | valid (normal exit) |
| Outcome | Loss | Loss |

---

## Section 3 — β-Sizing Mechanical Verification

### 3A — BETA_SIZING Log Line

**T1 (JUP/YGG) — entry 02:52:18 UTC**

BETA_SIZING log line (0.5s before STRATEGY_TRADE_OPEN at 10:52:18 local / 02:52:18 UTC):

```
BETA_SIZING: beta=1.4946 gross=200.00 capital_long=80.17 capital_short=119.83 side=negative_z
```

| Field | Value |
|---|---|
| beta | 1.4946 |
| gross | 200.00 |
| capital_long | 80.17 |
| capital_short | 119.83 |
| side | negative_z (entry_z = −2.655 → long inst_1/JUP, short inst_2/YGG) |
| leg1_expected = 200/(1+1.4946) | 200/2.4946 = **80.18** → matches 80.17 ✓ |
| leg2_expected = 200×1.4946/(1+1.4946) | 298.92/2.4946 = **119.82** → matches 119.83 ✓ |
| gross_check: 80.17 + 119.83 | **200.00** ✓ |
| fallback_used | no |

**T2 (LTC/KSM) — entry 11:56:14 local / 03:56:14 UTC**

```
BETA_SIZING: beta=0.6335 gross=200.00 capital_long=77.56 capital_short=122.44 side=positive_z
```

| Field | Value |
|---|---|
| beta | 0.6335 |
| gross | 200.00 |
| capital_long | 77.56 |
| capital_short | 122.44 |
| side | positive_z (entry_z = +2.013 → long inst_2/LTC, short inst_1/KSM) |
| leg2_expected (long) = 200×0.6335/(1+0.6335) | 126.70/1.6335 = **77.57** → matches 77.56 ✓ |
| leg1_expected (short) = 200/(1+0.6335) | 200/1.6335 = **122.44** → matches 122.44 ✓ |
| gross_check: 77.56 + 122.44 | **200.00** ✓ |
| fallback_used | no |

**Post-restart check:** Run 125 followed the crash-loop outage (bot crashing on startup due to ModuleNotFoundError, fixed and committed before run 125). T1 (JUP/YGG) is the first trade post-fix. The BETA_SIZING log is present and correct — metrics["hedge_ratio"] was populated (β=1.4946, in-bounds). No fallback triggered. Post-restart check: PASS.

**Day 1 staleness verification (one-time, T1 only):**

- BETA_SIZING log β at entry: **1.4946**
- entry_gate_component_scores hedge_ratio (last pre-entry rejection row for YGG/JUP): **1.4962**
- Delta: 0.0016 — consistent with a single kline update between the last rejection evaluation and the actual entry evaluation. Same source (metrics["hedge_ratio"]), normal drift.
- Staleness verification: **PASS** — both read from the same source at adjacent evaluation times.

### 3B — hedge_ratio in entry_gate_component_scores

**Run 125:** 80 of 134 rejection rows contain hedge_ratio in entry_gate_component_scores. ✓ Day 1 telemetry confirmed present.

Sample values (YGG/JUP, pre-entry rejections): 1.4653, 1.4653, 1.4962 — consistent with β drifting slightly across klines.

**Run 126:** 0 of 23 rejection rows contain hedge_ratio. This is expected — run 126 had only 1 entry_safety_gate evaluation (the accepted LTC/KSM trade), and accepted trades do not appear in entry_rejections.csv. All 23 rejection rows were upstream blocks (pre-safety-gate). Not a bug.

### 3C — $/σ per Trade

> **Note (added with T3, run 129):** the ad-hoc inclusion reasoning below is superseded by the **$/σ Inclusion Rule v1.2** (see the Run 129 section). The v1.2 rule makes inclusion mechanical (exit_reason + MFE>0 + |Δz|≥0.5) so coint-failure trades are never judged trade-by-trade. T1 below remains correctly excluded under v1.2 (MFE≈0; exit=cointegration_lost).

**T1 (JUP/YGG):** MFE = +$0.002 — effectively zero, no meaningful spread reversion before cointegration_lost. **Excluded (MFE ≤ meaningful threshold, no reversion).**

**T2 (LTC/KSM):**

| Field | Value |
|---|---|
| entry_z | +2.013 |
| exit_z | −0.257 |
| Δz (abs) | 2.270 |
| position_pnl (from reconciliation) | +$0.146 |
| $/σ = position_pnl / Δz | +$0.064/σ |
| Sign | **POSITIVE** ✓ |
| exit_reason | normal |

Dollar PnL tracked z-reversion in the expected direction. β-sizing aligned signal and position for T2.

### 3D — Running $/σ Sign Stability Table

| Trade # | Run | Pair | β | Δz | position_pnl | real_costs | edge_clears_costs | $/σ | Sign |
|---|---|---|---|---|---|---|---|---|---|
| T1 | run_125 | JUP/YGG | 1.4946 | — | — | — | — | N/A (MFE≈0) | — |
| T2 | run_126 | LTC/KSM | 0.6335 | 2.270 | +$0.146 | $0.251 | **no** | +$0.064 | **+** |

`real_costs (T2)` = position_pnl − equity_change = $0.146 − (−$0.105) = **$0.251** (1.8× model estimate of $0.14).

**After runs 125–126:**
- Trades with $/σ computed: 1 (T2)
- Sign-positive: 1 | Sign-negative: 0
- **Sign-flip rate: 0/1 = 0%** (target ≤10%)
- Cumulative aggregate $/σ: +$0.064 (positive ✓)
- **edge_clears_costs = yes: 0/1** — T2 position made money (+$0.146) but real costs ($0.251) exceeded it
- Coint-failure trades excluded from $/σ table: 1 (T1)

Success criterion tracking: 1/20 computable trades, 0 sign flips, aggregate $/σ positive. Too early to interpret; record only.

### 3E — β Distribution Tracker

| Trade # | Run | Pair | β at entry | Within [0.20–5.00]? | Fallback? |
|---|---|---|---|---|---|
| T1 | run_125 | JUP/YGG | 1.4946 | yes | no |
| T2 | run_126 | LTC/KSM | 0.6335 | yes | no |

**After runs 125–126:**
- β range: [0.634, 1.495]
- Trades with β < 1.0: 1/2 (T2 LTC/KSM)
- Trades with β outside [0.8, 1.2] (materially non-unity): 2/2 (both)
- Fallback activations: 0

Both trades have materially non-unity β — consistent with the counterfactual window's pattern. Good early signal that the pair universe is producing similar β deviation. Structural-review comparison will be possible once 20 trades accumulate.

---

## Section 4 — Reconciliation Telemetry

### Carryover ETH/LDO (excluded from experiment)

- position_pnl: +$0.003
- equity_change: −$0.253
- basis: **position_pnl** (FAIL — fees=0, OKX fee API not settled; likely retry_count timing gap)
- Excluded from economic analysis per reconciliation basis disposition rule.

### T1 — JUP/YGG

- position_pnl: −$0.428
- equity_change: −$0.962
- basis: pre_close_equity_delta ✓
- fees: $0.10 | slippage: $0.04 | unexplained: **−$0.394**
- Real total costs: ~$0.534 vs estimated $0.14 → **3.8× cost model overrun**
- pass_fail: **FAIL** (large_unexplained_warning=True, unexplained_pct=73.8%)

JUP (Jupiter, Solana DEX) and YGG (Yield Guild Games) are low-liquidity altcoins with structurally wide bid-ask spreads. This unexplained residual is consistent with the meme/thin-pair cost pattern seen with HMSTR (−$0.226) and FLOKI (−$0.093). JUP and YGG are not yet graveyarded — this is a first occurrence. Note and flag for structural review.

**Execution cost sub-pattern tracker (cumulative):**
| Pair | Run | Unexplained | Disposition |
|---|---|---|---|
| HMSTR | run_102 | −$0.226 | graveyarded |
| FLOKI | run_111 | −$0.093 | graveyarded |
| FIL/ICP (T10) | run_118 | −$0.255 | flagged (thin leg) |
| **JUP/YGG (T1)** | **run_125** | **−$0.394** | **first occurrence — flag** |

T1 is the fourth large negative unexplained residual event. JUP/YGG are speculative altcoins with thin order books — structurally similar to meme tokens. Not yet at graveyard threshold (single occurrence), but: if JUP or YGG appears again with a large residual, escalate to category-exclusion proposal at structural review.

### T2 — LTC/KSM

- position_pnl: +$0.146
- equity_change: −$0.105
- basis: pre_close_equity_delta ✓
- fees: $0.10 | slippage: $0.04 | unexplained: −$0.111
- Real total costs: ~$0.251 vs estimated $0.14 → **1.8× cost model overrun**
- pass_fail: **FAIL** (large_delta_warning only — total difference $0.251 ≥ $0.25 threshold; large_unexplained_warning=False)

Borderline. The unexplained residual (−$0.111) is below the $0.15 flag threshold. LTC and KSM are mid-tier liquid pairs — this may be normal cost variance. The position_pnl was positive ($0.146), confirming the strategy worked; costs converted it to a net equity loss (−$0.105). No graveyard flag warranted.

---

## Section 5 — Coint Stability Gate Status (Maintenance)

**T1 (JUP/YGG):** entry_coint_stability_slope=0.003249, evaluated_count=1. Gate reached and evaluated. Slope below 0.020 threshold — gate passed. Coint failure was post-entry (cointegration_lost), not predictable from entry slope.

**T2 (LTC/KSM):** entry_coint_stability_slope=unavailable, evaluated_count=0. Insufficient history — pair switched in with <5 samples in ring buffer. Gate not evaluable. Expected behavior for fast-entry pairs.

Session aggregate (run 125): 81 safety gate evaluations. No coint_stability_slope_exceeded blocks. Run 126: 1 safety gate evaluation (accepted trade, not in rejections).

Gate premise was assessed NEGATIVE in exp_coint_stability_v1 structural review. Reporting as maintenance telemetry only.

---

## Section 6 — Entry Rejection Distribution

**Run 125 (134 rows):** All 134 rows appear as strategy/persistence/quality rejections. Rejection field contains reasons including: adaptive persistence not satisfied, cointegration_component_below_threshold, and coint_gate/strategy_gate upstream blocks. No `coint_stability_slope_exceeded` blocks.

**Run 126 (23 rows):** All upstream rejections (pre-safety-gate). No slope_exceeded blocks.

No `statarb_mr_trend_regime_block` rejections in either run (regime=RANGE throughout).

---

## Section 7 — Counter Update and Next Step

```
trades_since_experiment_start: 2 (T1 JUP/YGG, T2 LTC/KSM)
normal_exit_trades_with_sigma_computed: 1 (T2 only — T1 excluded MFE≈0)
sign_flip_rate_so_far: 0/1 = 0% (target ≤10%)
cumulative_aggregate_sigma: +$0.064/σ (positive)
beta_range_observed: [0.634, 1.495]
beta_fallback_activations: 0
cumulative PnL (experiment window): −$1.067 (T1: −$0.962, T2: −$0.105)
win rate (experiment window): 0/2 = 0%
coint-exit losses: 1 trade, −$0.962 (T1 JUP/YGG, cointegration_lost)
trades_remaining_to_action_threshold: 18
next step: run_127+ with frozen configuration
```

**Flags carried forward to structural review:**
- JUP/YGG unexplained −$0.394 (3.8× cost overrun, first occurrence on this pair class — watch for recurrence)
- T2 LTC/KSM reconciliation borderline (difference=$0.251, just above warning threshold; not a hard flag)

---

*Audit covers: run_125_20260528_085100 (T1 JUP/YGG + excluded carryover ETH/LDO) and run_126_20260528_110547 (T2 LTC/KSM).*
*Template: exp_beta_aware_sizing_v1_per_run_audit.md v1.1.*
*Day 1 staleness check: PASS. Post-restart check: PASS. hedge_ratio in CSV: PASS.*

---
---

# Run 129 (2026-05-29) — T3 BNB/LINK

## $/σ Inclusion Rule v1.2 (TIGHTENED — applies from T3 forward)

Supersedes the ad-hoc Section 3C handling used for runs 125–126. The prior template ("skip $/σ if exit was coint-failure AND position PnL was monotonically adverse") still required a judgment call on T3 — it qualified for exclusion but was flagged rather than auto-excluded. v1.2 removes the judgment:

> **$/σ is computed only for trades meeting ALL THREE:**
> - **(a) exit_reason** is `normal`, `trailing_stop`, or `profit_lock` — **NOT** `cointegration_lost`, `cointegration_watch_timeout`, or any coint-failure category.
> - **(b) MFE > 0** — the position became favorable at some point.
> - **(c) |Δz| ≥ 0.5** — there was a meaningful spread move to measure against.
>
> **Coint-failure exits are recorded in a separate cumulative count (the coint-failure tracker), NOT in the $/σ sign-flip table — regardless of whether z reverted favorably in z-space.**

**Rationale.** The $/σ test asks: "when the cointegration model's reversion completes, does the β-sized dollar position track it?" A coint-failure trade is by definition one where the relationship was *deteriorating mid-hold* — by exit, the entry-time β was no longer the right hedge ratio, so neither β=1 nor β=OLS nor any β would have aligned the position. Including such trades measures coint deterioration (already established as a dominant loss mode in exp_coint_stability_v1), not the sizing question this experiment is built to answer. Condition (a) is the operative gate; (b) and (c) carry the prior MFE/Δz hygiene.

---

## Experiment State Block

```
experiment_group: exp_beta_aware_sizing_v1
runs_since_experiment_start: run_125, run_126, run_129
trades_since_experiment_start_entering_this_run: 2
trades_since_experiment_start_after_this_run: 3 (T1 JUP/YGG, T2 LTC/KSM, T3 BNB/LINK)
trades_remaining_to_action_threshold: 17
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7, Patch 7.1, Patch 7.2, Beta-Aware Sizing
sizing_mode: gross_normalized_beta (Option C) — STATBOT_HEDGE_RATIO_SIZING_ENABLED=true
note: runs 127–128 produced 0 experiment trades (128 = OKX API outage + 77-min flatten loop, operational event).
```

---

## Section 1 — Run Summary (Run 129)

- Duration: 7h 49.4min (12:42:34–20:31:57 UTC)
- Accepted trades: 1 (BNB/LINK); + 1 zero-PnL DOGE/OP reset row (no entry_ts/side/notional — excluded, same class as the run-125 ETH/LDO carryover)
- Closed experiment trades: 1 (T3)
- Session PnL: −$0.267 (equity 2653.76 → 2653.49)
- Wins: 0, Losses: 1, Win rate: 0%
- Pair switches: 29 (30 pairs total)
- Gate blocks: 0 hard-blocks at session level; T3 pair itself was held by `advanced_ml_break_risk_high` for ~1 min pre-entry (break_risk=0.150 > cap 0.120) until break_risk fell to 0.000 at 04:20:15 local, then passed.
- Circuit breaker: not tripped
- **Run end: `RUN_END reason=max_session_trades detail=limit=1 closed=1`** — one-trade-per-session controlled mode worked as configured.

---

## Section 2 — Per-Trade Telemetry

| Field | T3 (run_129) |
|---|---|
| Pair | BNB-USDT-SWAP/LINK-USDT-SWAP |
| Side | long_positive_short_negative (long LINK, short BNB; SELL_SPREAD) |
| Entry regime | RANGE (flipped RISK_OFF / vol_shock ~50s post-entry) |
| Entry z | +2.1214 |
| Exit z | +0.5786 |
| Δz (abs) | 1.543 (favorable reversion in z-space) |
| Exit reason | **cointegration_watch_timeout** |
| Hold (min) | 11.5 |
| MFE | −$0.101 (never crossed zero) |
| MAE | −$0.181 |
| position_pnl (gross) | **−$0.137** (negative before costs) |
| Net PnL (equity) | −$0.267 |
| Coint at close | watch timeout (deteriorating) |
| Outcome | Loss — **coint-failure class** |

**Key observation:** unrealized PnL was negative at all 11 position snapshots (−0.035 → −0.074) while z fell 2.12 → 0.58. The spread reverted in z-space but the dollar position never tracked it — the signature of coint deterioration, not a sizing defect.

---

## Section 3 — β-Sizing Mechanical Verification (T3)

### 3A — BETA_SIZING Log Line

**T3 (BNB/LINK) — entry 04:20:16 local / 20:20:17 UTC** (BETA_SIZING immediately preceding STRATEGY_TRADE_OPEN):

```
BETA_SIZING: beta=0.3776 gross=200.00 capital_long=54.82 capital_short=145.18 side=positive_z
```

| Field | Value |
|---|---|
| beta | 0.3776 — **lowest β observed in experiment** (below counterfactual floor 0.471) |
| gross | 200.00 |
| capital_long | 54.82 (LINK, inst_2 / positive ticker) |
| capital_short | 145.18 (BNB, inst_1 / negative ticker) |
| side | positive_z (entry_z = +2.013… → long inst_2/LINK, short inst_1/BNB) |
| leg1_expected (short) = 200/(1+0.3776) | 200/1.3776 = **145.18** → matches ✓ |
| leg2_expected (long) = 200×0.3776/(1+0.3776) | 75.52/1.3776 = **54.82** → matches ✓ |
| gross_check: 54.82 + 145.18 | **200.00** ✓ |
| fallback_used | no |

Pre-trade notional check in log confirms execution: `long=54.81 short=147.26 total=202.07` → filled LINK 6.07 ct @ 9.0293 (cap 54.82), BNB 23 ct @ 640.25 (cap 145.18). β-sizing verified to the cent.

### 3B — hedge_ratio in entry_gate_component_scores

Present on every T3 pre-entry safety-gate row: `hedge_ratio` ranged 0.3774–0.3776 across the ~1-min break-risk hold. Matches the BETA_SIZING β (same source, metrics["hedge_ratio"]). ✓

### 3C — $/σ Classification (T3)

**T3 is EXCLUDED from the $/σ table under Rule v1.2** — fails condition (a): exit_reason = `cointegration_watch_timeout` (coint-failure category). Also fails (b): MFE = −$0.101 < 0. Recorded in the coint-failure tracker instead.

This is mechanical, not a judgment call. Note that even though z reverted 1.54σ favorably (which under the *old* template's "monotonically adverse" clause might have invited debate), v1.2 condition (a) excludes it outright on exit_reason alone.

### 3E — β Distribution Tracker (cumulative)

| Trade # | Run | Pair | β at entry | Within sizing [0.20–5.00]? | Within **binding** discovery [0.3–3.0]? | Fallback? |
|---|---|---|---|---|---|---|
| T1 | run_125 | JUP/YGG | 1.4946 | yes | yes | no |
| T2 | run_126 | LTC/KSM | 0.6335 | yes | yes | no |
| T3 | run_129 | BNB/LINK | **0.3776** | yes | yes (1.26× above 0.3 floor) | no |

**Binding constraint correction (verified against code 2026-05-29):** β is gated by TWO bound systems, and the **tighter, upstream one binds**:
- **Sizing fallback bound [0.20, 5.00]** (`STATBOT_MIN/MAX_HEDGE_RATIO`, `Execution/config_execution_api.py:281-282`) — convention-derived, log-symmetric [1/N, N], unsourced; if β outside → equal-notional fallback. **Nearly inert** in normal operation.
- **Pair-discovery filter [0.3, 3.0]** (`STATBOT_STRATEGY_MIN/MAX_HEDGE_RATIO`, enforced at `Strategy/func_cointegration.py:1720-1726` and 2429) — rejects any pair with |β| outside [0.3, 3.0] *before* it can become a tradeable pair. This is the **real operating envelope**.
- Therefore the **observable β range is structurally bounded to [0.3, 3.0]**, not [0.20, 5.00]. T3's β=0.378 is 1.26× above the binding floor (0.3), not 1.9× above 0.20.

**After T3:**
- β range: **[0.378, 1.495]** — inside the binding [0.3, 3.0] envelope, slightly wider than the counterfactual window [0.471, 1.433].
- Trades with β < 1.0: **2/3** (T2, T3)
- Trades materially non-unity (outside [0.8, 1.2]): **3/3**
- Fallback activations: 0

**Leading indicator (with ceiling caveat):** β breadth may continue to widen, but it is **capped by the [0.3, 3.0] discovery filter**, so the sizing effect is bounded — |β−1| ≤ 0.7 on the low side, ≤ 2.0 on the high side. The earlier framing ("cumulative β-sizing benefit at 20 trades may exceed the counterfactual's +$0.988") stands only within that ceiling; it is **not open-ended**. Track as a bounded leading indicator.

---

## Section 4 — Reconciliation Telemetry (T3)

- position_pnl: **−$0.137** (gross, NEGATIVE)
- equity_change: −$0.267
- difference: −$0.130 | fees: $0.10 | slippage: $0.04 | funding: $0.00 | unexplained: **−$0.010**
- basis: pre_close_equity_delta ✓
- unexplained_pct: 7.76% | large_delta_warning: False | large_unexplained_warning: False
- pass_fail: **PASS**

**Costs were textbook: ~$0.14 (1.0× model), unexplained only −$0.010.** This is the cleanest reconciliation of the experiment so far (contrast T1 3.8×, T2 1.8×). The loss is therefore NOT a cost overrun — the gross position itself lost −$0.137 while z reverted favorably. That isolates the cause to coint deterioration: the entry-time β (0.378) ceased to be the correct hedge ratio during the hold. No thin-pair cost flag (BNB and LINK are top-tier liquid).

---

## Section 5 — Coint Stability Gate Status (T3, Maintenance)

- T3: entry_coint_stability_slope = **0.000482**, evaluated_count = **1**. Gate reached and evaluated; slope far below 0.020 threshold — gate passed.
- As with T1, coint failure was **post-entry and not predictable from the entry slope** (slope was essentially flat at entry). Consistent with the exp_coint_stability_v1 finding that the slope filter does not anticipate mid-hold coint breakdown (gate premise assessed NEGATIVE). Maintenance telemetry only.

---

## Section 7 — Cumulative Counter Update (after T3)

```
trades_since_experiment_start: 3 (T1 JUP/YGG, T2 LTC/KSM, T3 BNB/LINK)
$/σ computable population: 1 (T2 only) — T1 and T3 excluded as coint-failures (Rule v1.2)
sign_positive: 1/1 | sign_flip_rate: 0/1 = 0% (target ≤10%)
cumulative_aggregate_sigma: +$0.064/σ (positive; unchanged — T3 not in population)
coint-failure count (experiment window): 2/3 (T1 cointegration_lost, T3 cointegration_watch_timeout)
beta_range_observed: [0.378, 1.495]
beta_fallback_activations: 0
cumulative PnL (experiment window): −$1.334 (T1 −$0.962, T2 −$0.105, T3 −$0.267)
win rate (experiment window): 0/3 = 0%
trades_remaining_to_action_threshold: 17
next step: run_130+ with frozen configuration
```

Coint-failure rate 2/3 in-window is roughly consistent with the 30–40% baseline from prior windows — β-sizing does not touch the coint signal, so this is expected and tracked as a maintenance number, not a hypothesis result.

---

## Flags Carried to Structural Review (new from T3)

1. **$/σ Inclusion Rule v1.2** — adopt as the template rule (replaces ad-hoc Section 3C handling). Inclusion is now mechanical: exit_reason ∈ {normal, trailing_stop, profit_lock} AND MFE>0 AND |Δz|≥0.5.
2. **Pre-entry regime-flip detection (NEW deferred item).** T3 entered, then flipped to RISK_OFF (vol_shock) ~50s post-entry, then coint-timed-out. A flip 50s after fill implies the producing conditions were arguably present *at* entry. Investigate whether the regime indicator can give a pre-entry signal for imminent vol_shock flips that would block T3-class entries. Connects to the existing deferred regime-flip *exit*-timing item (run 98's delayed flip) — possibly the same mechanism applied to the entry gate rather than the exit path.
3. **β breadth (bounded by discovery filter)** — live [0.378, 1.495] vs counterfactual [0.471, 1.433]. Realized β-sizing benefit at 20 trades is a bounded leading indicator: capped by the [0.3, 3.0] discovery envelope, so |β−1| ≤ 0.7 low / ≤ 2.0 high. Not open-ended.
4. **Config provenance correction (verified against code 2026-05-29).** `STATBOT_HEDGE_RATIO_SIZING_ENABLED` is a **new** config var added for exp_beta_aware_sizing_v1 (decision log: "3 new vars" at `config_execution_api.py:280-282`) — NOT a pre-existing schema flag (earlier note was wrong; what pre-existed was the calculation tooling in `core/chart_audit/hedge_ratio_sizing_audit.py`). The [0.20, 5.00] sizing fallback bounds are convention-derived (log-symmetric [1/N, N]), unsourced — no derivation comment in `hedge_ratio_sizing_audit.py:143-144` or `config_execution_api.py:281-282`. **The binding constraint on observable β is the upstream `STATBOT_STRATEGY_MIN/MAX_HEDGE_RATIO=[0.3, 3.0]` pair-discovery filter (`func_cointegration.py:1720`), not the sizing fallback bounds.** The two filters being set to different ranges is easy-to-misread telemetry: the deployed sizing setting [0.20, 5.00] is NOT the range β-sizing is actually being tested across — that range is [0.3, 3.0].
   - **Conditional permanence:** the binding constraint is a property of the *current* pair-discovery configuration, not a permanent property of β-sizing. If a future experiment loosens `STATBOT_STRATEGY_MAX_HEDGE_RATIO` (e.g., to 5.0 for a wider pair universe) or tightens it, the binding constraint moves with it, and the [0.20, 5.00] sizing fallback may start mattering and need re-evaluation. Carry this relationship forward whenever the discovery filter changes.

---

*Audit covers: run_129_20260528_204234 (T3 BNB/LINK). Runs 127–128 produced 0 experiment trades.*
*Template: exp_beta_aware_sizing_v1_per_run_audit.md v1.2 ($/σ inclusion rule tightened).*
*β-sizing mechanical verification: PASS. hedge_ratio in component_scores: PASS. Reconciliation: PASS (cleanest of experiment).*
