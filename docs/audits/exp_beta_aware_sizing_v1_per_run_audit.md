# Per-Run Audit — exp_beta_aware_sizing_v1
## Runs 125–140 (T1–T13) — 2026-05-28 → 2026-05-30

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

---
---

# Run 130 (2026-05-29) — T4 DOGE/AAVE

## Experiment State Block

```
experiment_group: exp_beta_aware_sizing_v1
runs_since_experiment_start: run_125, run_126, run_129, run_130
trades_since_experiment_start_after_this_run: 4 (T1 JUP/YGG, T2 LTC/KSM, T3 BNB/LINK, T4 DOGE/AAVE)
trades_remaining_to_action_threshold: 16 (to 20 total); $/σ-eligible remaining: ≥7 (only T2 eligible so far)
patches_active: 4.1, 5, 6, 7, 7.1, 7.2, Beta-Aware Sizing
sizing_mode: gross_normalized_beta (Option C) — STATBOT_HEDGE_RATIO_SIZING_ENABLED=true
run_end: RUN_END reason=max_session_trades (limit=1) — one trade per session.
```

---

## Section 1 — Run Summary (Run 130)

- Duration: ~13h (04:32:00–05:51:28 UTC span shown is local→UTC; entry 05:40 / exit 05:51 UTC are the trade window). Long watch, single accepted trade.
- Accepted trades: 1 (DOGE/AAVE). Closed experiment trades: 1 (T4).
- Session PnL: −$0.2528 (equity 2653.49 → 2653.24).
- Wins: 0, Losses: 1, Win rate: 0%.
- Gate maintenance-positive: **Patch 4.1 TREND block fired correctly** — ASTER/SOL blocked by `statarb_mr_trend_regime_block` (+ advanced_ml_break_risk_high) at 13:16 local, ~24 min before the DOGE/AAVE entry. The block is working in production.
- Circuit breaker: not tripped.
- Run end: `RUN_END reason=max_session_trades detail=limit=1 closed=1`.

---

## Section 2 — Per-Trade Telemetry

| Field | T4 (run_130) |
|---|---|
| Pair | DOGE-USDT-SWAP/AAVE-USDT-SWAP |
| Side | long_negative_short_positive (long DOGE, short AAVE; BUY_SPREAD, oversold) |
| Entry regime | RANGE |
| Entry z | −2.2015 |
| Exit z | −0.0974 |
| Δz (abs) | 2.104 (favorable reversion, all the way into the exit zone) |
| Exit reason | **cointegration_lost** |
| Hold (min) | 10.4 |
| MFE | −$0.103 (never crossed zero) |
| MAE | −$0.226 |
| position_pnl (gross) | **−$0.110** (negative before costs) |
| Net PnL (equity) | −$0.2528 |
| full_tp_touched / guard blocks | True / **23** (guard correctly blocked — max in-zone PnL −$0.103, always negative) |
| Coint at close | lost |
| Outcome | Loss — **coint-failure class** |

**Key observation (3rd time in 4 trades):** unrealized PnL negative at all 11 snapshots (−0.067 → −0.007) while z reverted −2.20 → −0.10 *into* the |z|<0.35 exit zone. full_tp was touched but the guard blocked 23× because PnL was never positive. Spread reverted in z-space; dollar position never tracked it. Coint deterioration signature, identical to T1 and T3.

---

## Section 3 — β-Sizing Mechanical Verification (T4)

### 3A — BETA_SIZING Log Line

**T4 (DOGE/AAVE) — entry 13:40:55 local / 05:40:55 UTC** (BETA_SIZING immediately preceding STRATEGY_TRADE_OPEN):

```
BETA_SIZING: beta=0.7605 gross=200.00 capital_long=113.61 capital_short=86.39 side=negative_z
```

| Field | Value |
|---|---|
| beta | 0.7605 (within [0.3, 3.0] discovery envelope; fallback bound [0.20, 5.00] not approached) |
| gross | 200.00 |
| capital_long | 113.61 (DOGE, inst_1 / negative ticker — long) |
| capital_short | 86.39 (AAVE, inst_2 / positive ticker — short) |
| side | negative_z (entry_z = −2.20 → long inst_1/DOGE, short inst_2/AAVE) |
| leg1_expected (long DOGE) = 200/(1+0.7605) | 200/1.7605 = **113.60** → matches 113.61 ✓ |
| leg2_expected (short AAVE) = 200×0.7605/(1+0.7605) | 152.10/1.7605 = **86.40** → matches 86.39 ✓ |
| gross_check: 113.61 + 86.39 | **200.00** ✓ |
| fallback_used | no |

Pre-trade notional check confirms execution: `long=113.16 short=86.41 total=199.56` → DOGE 1.14 ct @ 0.099261 (cap 113.61), AAVE 10.70 ct @ 80.7534 (cap 86.39). β-sizing verified to the cent.

### 3B — hedge_ratio in entry_gate_component_scores

DOGE/AAVE was the **accepted** trade, so its safety-gate evaluation was a PASS and does not appear as an `ENTRY_SAFETY_GATE_BLOCKED` row. The authoritative entry β is the BETA_SIZING line (0.7605), sourced from `metrics["hedge_ratio"]` at the entry instant.

**Telemetry-hygiene note (verified, NOT a discrepancy):** a quick whole-log scan surfaced `hedge_ratio: 1.1149` — but those rows are **ASTER/SOL** (a different pair, blocked at 13:16, 24 min pre-entry), not DOGE/AAVE. There is no β staleness/discrepancy at T4. (Flagged here only because the mismatched grep could otherwise be misread — Section 8A discipline: confirm the row's pair before asserting.)

### 3C — $/σ Classification (T4)

**T4 is EXCLUDED from the $/σ table under Rule v1.2** — fails (a): exit_reason = `cointegration_lost` (coint-failure category). Also fails (b): MFE = −$0.103 < 0. Recorded in the coint-failure tracker.

### 3E — β Distribution Tracker (cumulative)

| Trade # | Run | Pair | β at entry | In [0.3,3.0] envelope? | Fallback? |
|---|---|---|---|---|---|
| T1 | run_125 | JUP/YGG | 1.4946 | yes | no |
| T2 | run_126 | LTC/KSM | 0.6335 | yes | no |
| T3 | run_129 | BNB/LINK | 0.3776 | yes | no |
| T4 | run_130 | DOGE/AAVE | **0.7605** | yes | no |

**After T4:**
- β range: **[0.378, 1.495]** (unchanged; T4's 0.76 sits inside the existing range).
- Trades with β < 1.0: **3/4** (T2, T3, T4).
- Trades materially non-unity (outside [0.8, 1.2]): **4/4**.
- Fallback activations: 0. β-sizing mechanically flawless across all four trades.

---

## Section 4 — Reconciliation Telemetry (T4)

- position_pnl: **−$0.110** (gross, NEGATIVE)
- equity_change: −$0.253
- difference: −$0.143 | fees: $0.10 | slippage: $0.04 | funding: $0.00 | unexplained: **−$0.0025**
- basis: pre_close_equity_delta ✓
- unexplained_pct: 1.77% | large_delta_warning: False | large_unexplained_warning: False
- pass_fail: **PASS**

**Costs textbook again: ~$0.14 (1.0× model), unexplained only −$0.0025** — ties T3 as the cleanest reconciliation tier of the experiment. The loss is NOT a cost overrun; the gross position lost −$0.110 while z reverted favorably. Pure coint deterioration. DOGE and AAVE are liquid majors — no thin-pair cost flag. (Cumulative pattern: coint-failures on *liquid* pairs reconcile cleanly with normal costs — the loss is the relationship breaking, not execution.)

---

## Section 5 — Coint Stability Gate Status (T4, Maintenance)

- T4: entry_coint_stability_slope = **−0.000579**, evaluated_count = **1**. Gate reached and evaluated; slope flat/slightly-improving, far below 0.020 threshold — gate passed.
- Coint failure was **post-entry, not predictable from the entry slope** (slope was negative = p-values improving at entry, i.e., cointegration *strengthening* — yet it failed). This is now the **third** coint-failure (T1, T3, T4) that entered with a passing/benign slope and failed mid-hold. Consistent with exp_coint_stability_v1's premise-NEGATIVE verdict: entry-time coint metrics do not predict post-entry collapse. Maintenance telemetry only.

---

## Section 6 — Cumulative Counter Update (after T4)

```
trades_since_experiment_start: 4 (T1 JUP/YGG, T2 LTC/KSM, T3 BNB/LINK, T4 DOGE/AAVE)
$/σ computable population: 1 (T2 only) — T1, T3, T4 all excluded as coint-failures (Rule v1.2)
sign_positive: 1/1 | sign_flip_rate: 0/1 = 0% (target ≤10%)
cumulative_aggregate_sigma: +$0.064/σ (positive; unchanged — T4 not in population)
coint-failure count (experiment window): 3/4 = 75% (T1 coint_lost, T3 watch_timeout, T4 coint_lost)
beta_range_observed: [0.378, 1.495]
beta_fallback_activations: 0
cumulative PnL (experiment window): −$1.587 (T1 −$0.962, T2 −$0.105, T3 −$0.267, T4 −$0.253)
win rate (experiment window): 0/4 = 0%
trades_remaining_to_action_threshold: 16 (to 20 total); ≥7 more $/σ-eligible needed
next step: run_131+ with frozen configuration
```

---

## Section 7 — E4 Early-Warning (NOT yet firing — flagged per template)

**Coint-failure rate is now 3/4 = 75% in-window.** The template's **E4 kill-criterion** (>60% coint-failure over **≥10 closed trades** → halt sizing test) is **not yet evaluable** — only 4 closed trades, below the ≥10 minimum. We are in **watch**, not fire.

But the trajectory is the exact scenario E4 was written to catch:
- 3 of 4 trades never reached the $/σ-eligible population. After 4 trades, eligible N is still **1**. At this rate, ≥8 eligible would require ~30+ total trades.
- Current 75% is above the >60% halt line AND above the established baseline band (prior windows: 55.6% → 36.8% → 40.0%, which had been drifting *down*). If this rate holds, E4 fires at trade 10.
- **Pre-committed posture (per E4 calibration note):** at 4 trades this is "watch, do not halt." At ≥10 closed, if coint-failure rate is still >60%, halt and address coint-fragility (exit-speed / universe) before continuing the sizing test. Operator should be aware the experiment may resolve via E4 (universe-too-fragile) before H1/H2 become readable.

**This is the dilution problem the eligible-count gate + E4 were designed for, now materializing.** β-sizing remains mechanically flawless (4/4 exact, 0 fallbacks); the binding constraint on the experiment is coint-fragility of the universe, not sizing — exactly the Branch-2/Section-7 hypothesis surfacing in the collection data.

---

*Audit covers: run_130_20260529_043200 (T4 DOGE/AAVE).*
*Template: exp_beta_aware_sizing_v1_per_run_audit.md v1.2.*
*β-sizing mechanical verification: PASS (β=0.7605, gross conserved to the cent, 0 fallbacks). Reconciliation: PASS (textbook 1.0× costs). $/σ: excluded (coint-failure). E4: WATCH (3/4=75%, below ≥10-trade evaluability floor).*

---
---

# Run 131 (2026-05-29) — T5 AVAX/DOT  ← 2nd $/σ-ELIGIBLE trade

## Experiment State Block

```
experiment_group: exp_beta_aware_sizing_v1
runs_since_experiment_start: run_125, 126, 129, 130, 131
trades_since_experiment_start_after_this_run: 5 (T1 JUP/YGG, T2 LTC/KSM, T3 BNB/LINK, T4 DOGE/AAVE, T5 AVAX/DOT)
$/σ-eligible trades: 2 (T2, T5)
trades_remaining_to_action_threshold: 15 (to 20 total); ≥6 more $/σ-eligible needed
patches_active: 4.1, 5, 6, 7, 7.1, 7.2, Beta-Aware Sizing
run_end: RUN_END reason=max_session_trades (limit=1).
```

---

## Section 1 — Run Summary (Run 131)

- Accepted trades: 1 (AVAX/DOT). Closed experiment trades: 1 (T5).
- Session PnL: −$0.0303 (equity 2653.24 → 2653.21).
- Wins: 0, Losses: 1 (net), but **gross position_pnl POSITIVE** (+$0.069) — strategy worked; costs converted to a small net loss.
- Circuit breaker: not tripped.
- Run end: `RUN_END reason=max_session_trades`.

---

## Section 2 — Per-Trade Telemetry

| Field | T5 (run_131) |
|---|---|
| Pair | AVAX-USDT-SWAP/DOT-USDT-SWAP |
| Side | long_negative_short_positive (long AVAX, short DOT; BUY_SPREAD, oversold) |
| Entry regime | RANGE |
| Entry z | −2.1569 |
| Exit z | +1.8450 (reverted through 0 and overshot) |
| Δz (abs) | **4.002** (large favorable traversal) |
| Exit reason | **normal** (mechanism: `trade_manager_pnl_profit_lock`) |
| Hold (min) | 30.4 |
| MFE | **+$0.187** (equity-delta) / +$0.25 peak (position-snapshot) — **POSITIVE** |
| MAE | −$0.138 |
| position_pnl (gross) | **+$0.069** (POSITIVE) |
| Net PnL (equity) | −$0.0303 |
| full_tp_touched / guard blocks | True / **65** |
| Outcome | Net loss, but **$/σ-eligible and sign-positive** |

**Trajectory:** unrealized PnL was positive at nearly every snapshot (one −$0.023 dip early), rose with z as the spread reverted −2.16 → 0 → +2.46, peaking ~+$0.25 (z≈2.16). The position **tracked the favorable z-move correctly** — β-sizing aligned signal and position. It then gave back to +$0.069 gross at the profit-lock exit (z=+1.845), and costs took it to −$0.030 net.

---

## Section 3 — β-Sizing Mechanical Verification (T5)

### 3A — BETA_SIZING Log Line

**T5 (AVAX/DOT) — entry 17:26:46 local / 09:26:47 UTC:**

```
BETA_SIZING: beta=0.6594 gross=200.00 capital_long=120.52 capital_short=79.48 side=negative_z
```

| Field | Value |
|---|---|
| beta | 0.6594 (inside [0.3, 3.0] envelope) |
| leg1 (long AVAX, inst_1/neg) = 200/(1+0.6594) | 200/1.6594 = **120.53** → matches 120.52 ✓ |
| leg2 (short DOT, inst_2/pos) = 200×0.6594/(1+0.6594) | 131.88/1.6594 = **79.47** → matches 79.48 ✓ |
| gross_check: 120.52 + 79.48 | **200.00** ✓ |
| fallback_used | no |

**β-sizing is now 5/5 mechanically exact, 0 fallbacks.**

### 3C — $/σ Classification (T5) — ELIGIBLE

T5 passes ALL THREE Rule v1.2 conditions: (a) exit_reason = normal/profit_lock ✓; (b) MFE = +$0.187 > 0 ✓; (c) |Δz| = 4.002 ≥ 0.5 ✓. **INCLUDED in the $/σ table.**

| Field | Value |
|---|---|
| entry_z → exit_z | −2.1569 → +1.8450 |
| Δz (abs) | 4.002 |
| position_pnl (gross) | +$0.069 |
| **$/σ = position_pnl / Δz** | +0.069 / 4.002 = **+$0.017/σ** |
| Sign | **POSITIVE** ✓ |

The dollar position tracked the spread in the correct direction across a 4σ favorable move. β-sizing aligned signal and position — second confirmation of H1.

### 3D — Running $/σ Sign Stability Table

| Trade # | Run | Pair | β | Δz | position_pnl | real_costs | edge_clears_costs | $/σ | Sign |
|---|---|---|---|---|---|---|---|---|---|
| T2 | run_126 | LTC/KSM | 0.6335 | 2.270 | +$0.146 | $0.251 | no | +$0.064 | **+** |
| T5 | run_131 | AVAX/DOT | 0.6594 | 4.002 | +$0.069 | $0.100 | no | +$0.017 | **+** |

**After 5 trades (2 eligible):**
- Sign-positive: **2/2** | Sign-negative: 0 | **Sign-flip rate: 0/2 = 0%** (target ≤10%)
- Aggregate $/σ (pooled = Σpnl/Σ|Δz|): (0.146+0.069)/(2.270+4.002) = **+$0.034/σ** (positive ✓)
- **edge_clears_costs = yes: 0/2** — both eligible trades had positive, correctly-sized $/σ but the captured edge did NOT clear real costs.

### 3E — β Distribution Tracker (cumulative)

| Trade # | Run | Pair | β | In [0.3,3.0]? | Fallback? |
|---|---|---|---|---|---|
| T1 | run_125 | JUP/YGG | 1.4946 | yes | no |
| T2 | run_126 | LTC/KSM | 0.6335 | yes | no |
| T3 | run_129 | BNB/LINK | 0.3776 | yes | no |
| T4 | run_130 | DOGE/AAVE | 0.7605 | yes | no |
| T5 | run_131 | AVAX/DOT | 0.6594 | yes | no |

β range [0.378, 1.495] unchanged; β<1.0: 4/5; non-unity: 5/5; fallback: 0.

---

## Section 4 — Reconciliation Telemetry (T5)

- position_pnl: **+$0.069** (gross, POSITIVE)
- equity_change: −$0.0303
- difference: −$0.0996 | fees: $0.10 | slippage: $0.04 | funding: $0.00 | unexplained: **+$0.040** (positive residual — actual costs < model; 8th positive-residual occurrence on a liquid pair)
- basis: pre_close_equity_delta ✓ | large_delta_warning: False | large_unexplained_warning: False | pass_fail: **PASS**
- Real costs ≈ $0.0996 (~$0.10). Gross edge +$0.069 < costs → **edge_clears_costs = NO**.

---

## Section 5 — Coint Stability Gate Status (T5, Maintenance)

- entry_coint_stability_slope = −0.000061, evaluated_count = 1. Gate passed. T5 is a **normal exit** (not a coint-failure) — cointegration held through the hold. Maintenance telemetry only.

---

## Section 6 — Cumulative Counter Update (after T5)

```
trades_since_experiment_start: 5 (T1, T2, T3, T4, T5)
$/σ computable population: 2 (T2, T5) — T1, T3, T4 excluded as coint-failures
sign_positive: 2/2 | sign_flip_rate: 0/2 = 0% (target ≤10%)
aggregate $/σ (pooled): +$0.034/σ (positive)
edge_clears_costs: 0/2 (both positive $/σ, neither cleared costs at realized exit)
coint-failure count (window): 3/5 = 60% (T1, T3, T4) — down from 3/4=75% after T5 normal exit
beta_range_observed: [0.378, 1.495]; fallback activations: 0
cumulative PnL (experiment window): −$1.617 (T1 −0.962, T2 −0.105, T3 −0.267, T4 −0.253, T5 −0.030)
win rate (experiment window): 0/5 = 0%
trades_remaining_to_action_threshold: 15 (to 20 total); ≥6 more $/σ-eligible
next step: run_132+ (already started) with frozen configuration
```

---

## Section 7 — Reads from T5 (the richest trade so far)

**1. H1 (sizing alignment) — strengthening. 2/2 eligible trades sign-positive, sign-flip rate 0%.** β-sizing tracked a 4σ favorable move with positive PnL throughout. The architecture patch is doing exactly what it was built to do.

**2. H2 (edge clears costs) — the bifurcation concept is right; the T5 ASSIGNMENT below is RETRACTED.** edge_clears_costs is 0/2 at the realized exit. The split into *pure-cost* vs *exit-capture* is the correct frame:
   - **Pure cost problem** (the edge never exceeds costs) — vs —
   - **Exit-capture problem** (the edge exists at MFE but the exit leaks it).

   > **RETRACTION (Query 1 PnL-vs-z diagnostic, 2026-05-29 — see Cross-Trade Diagnostic section below):** I assigned T5 to "exit-capture / Item 14 exhibit." That was wrong — it rested on **MFE, a hindsight peak that sat at a +2.16σ overshoot (anti-thesis momentum), not a thesis-capturable quantity.** The disambiguating number is **PnL at the z≈0 mean-crossing: +$0.052 < costs $0.10.** The thesis edge never cleared costs; the only above-cost profit lived in opposite-side overshoot. T5 does **not** support exit redesign / Item 14. See the cross-trade diagnostic for the corrected classification.

**3. Profit-lock fired for the first time in the experiment.** Exit = `trade_manager_pnl_profit_lock`: `pnl=0.0693 ≤ floor=0.120 (MFE=0.1865, giveback=0.50)`. The mechanism the exp_guard050 review found *never activated* (0 activations) **did activate here** and captured +$0.069 gross. But the **profit-lock floor ($0.120) sits below the cost-clearing level (~$0.10 net needs >~$0.14 gross at realized giveback)** — so even a mechanically-successful profit-lock exit netted a loss. Calibration finding: the floor/giveback is tuned below cost-clearance. (Frozen variable — observation only, not a mid-window change.)

**4. Coint-failure rate eased to 3/5 = 60%** (from 3/4=75%) — T5's normal exit pulled it to the E4 boundary. **E4 still not evaluable** (needs ≥10 closed; we're at 5). At exactly 60% it sits on the line between the >60% halt and the 45–60% review band — trending down, watch continues.

**Net read (n=2 eligible — directional only):** β-sizing works. The binding constraint is not sizing; it is the combination of (a) coint-fragility removing 3/5 trades from the eligible population and (b) on the trades that *do* work, exit-capture + costs preventing the realized edge from clearing costs even though the peak edge does. This is sharpening toward a **Branch-1-and-2 blend**: exit redesign (Item 14) is now supported by direct evidence (T5 MFE > costs, leaked at exit), not just deferred reasoning — but it remains gated behind the eligible-population growing and E4 not firing.

---

*Audit covers: run_131_20260529_135131 (T5 AVAX/DOT). Run 132 already started.*
*Template: exp_beta_aware_sizing_v1_per_run_audit.md v1.2.*
*β-sizing: PASS (β=0.6594, gross to the cent, 0 fallbacks; 5/5 exact). Reconciliation: PASS (+$0.040 positive residual). $/σ: INCLUDED, +$0.017/σ POSITIVE (2/2 eligible positive). E4: WATCH (3/5=60%, not yet evaluable).*

---
---

# Cross-Trade Diagnostic — Query 1 (PnL-vs-z), 2026-05-29

**Read-only / diagnostics-only.** Per [`docs/diagnostics/analysis_spec_pnl_vs_z_decoupling_v1.md`](../diagnostics/analysis_spec_pnl_vs_z_decoupling_v1.md). Reads dollar (unrealized, mark-to-market) PnL as a function of z across each trade's per-cycle snapshot series (`position_snapshots.csv`). One primitive answers two questions: the **H2 bifurcation** (working trades) and the **mean-shift/decoupling** test (coint-failures). Zero new data. Live collection (run 132+) untouched.

**Preconditions (confirmed):** snapshot source = `Reports/v1/run_*/position_snapshots.csv` (`current_z`, `unrealized_pnl_usdt`); coverage complete for all 19 in-scope trades. **T8c excluded** (recon `basis=position_pnl`, cost-unreliable). real_costs = `trade_pnl − equity_change` from reconciliation.

**Sizing confound (stated):** exp_coint_stability_v1 trades (T1c–T14c) ran **equal-notional** (β computed, not applied) — their dollar magnitudes are sizing-confounded; usable for MFE-in-z *location*, not for clean decoupling. **Clean evidence = β-sized current trades** (T1b–T5b). Query 2 (kline recompute) resolves the confound for the decoupled set.

## RULE PROMOTED — Classification A |Δz| precondition
A trade is eligible for the decoupled/tracked test **only if |Δz| ≥ 0.5** (same floor Rule v1.2 uses for $/σ). Below that, z did not revert, so there is nothing to decouple *from* — a DECOUPLED label would be a measurement artifact. **This drops T2c (|Δz|=0.08) and T5c (|Δz|=0.10) from Class A** (both were spuriously DECOUPLED on a stuck z). Applies to this run and all future Query-1 passes.

## Per-trade table (snapshot-derived; gross mark-to-market vs real_costs)

| Trade | Sizing | Exit | \|Δz\| | cost | pnl@mean (z) | mfe (z) | pnl@exit | Class |
|---|---|---|---|---|---|---|---|---|
| T1c LINK/SUI | eq | coint_wt | 3.45 | 0.122 | +0.039 (+0.03) | +0.193 (+1.15) | +0.174 | A:TRACKED |
| T4c BCH/CRCL | eq | coint_lost | 3.78 | 0.144 | −0.064 (−0.03) | +0.136 (−2.89) | +0.095 | A:DECOUPLED |
| T6c DOGE/SUI | eq | coint_lost | 0.54 | 0.111 | +0.047 (−0.71) | +0.047 (−0.71) | −0.577 | A:TRACKED |
| T11c CRV/IOTA | eq | coint_wt | 2.42 | 0.100 | −0.076 (0.00) | +0.077 (−1.77) | −0.299 | A:DECOUPLED |
| T14c SOL/ALGO | eq | coint_lost | 1.80 | 0.123 | −0.335 (+0.20) | +0.062 (+1.27) | −0.380 | A:DECOUPLED |
| T1b JUP/YGG | **β** | coint_lost | 1.22 | 0.534 | +0.102 (−0.21) | +0.102 (−0.33) | −0.328 | A:TRACKED (thin-pair cost) |
| **T3b BNB/LINK** | **β** | coint_wt | 1.54 | 0.130 | −0.036 (+0.58) | −0.026 (+1.46) | −0.036 | **A:DECOUPLED (clean)** |
| **T4b DOGE/AAVE** | **β** | coint_lost | 2.10 | 0.143 | −0.007 (−0.10) | −0.007 (−0.10) | −0.007 | **A:DECOUPLED (clean)** |
| T2c, T5c | eq | coint_lost | 0.08, 0.10 | — | — | — | — | EXCLUDED (\|Δz\|<0.5) |
| — eligible normal exits — | | | | | | | | |
| T3c ETH/AVAX | eq | normal | 1.39 | 0.108 | +0.119 (−1.44) | +0.119 (−1.44) | +0.119 | B:ZONE-NARROW |
| T7c BTC/HBAR | eq | normal | 4.39 | 0.100 | +0.078 (+0.05) | +0.218 (+2.50) | +0.099 | B:ZONE-NARROW |
| T9c LINEA/ZRO | eq | normal | 2.98 | 0.067 | +0.114 (−0.47) | +0.114 (−0.47) | +0.114 | B:ZONE-NARROW |
| T10c FIL/ICP | eq | normal | 4.12 | 0.395 | +0.019 (+0.15) | +0.337 (−2.06) | +0.337 | B:PURE-COST |
| T12c SOL/BTC | eq | normal | 4.14 | 0.117 | +0.102 (−0.03) | +0.241 (−2.21) | +0.241 | B:CAPTURED (the win) |
| T13c BNB/COMP | eq | normal | 4.37 | 0.113 | −0.201 (−0.05) | +0.023 (+1.15) | −0.274 | B:PURE-COST |
| **T2b LTC/KSM** | **β** | normal | 2.27 | 0.251 | +0.052 (+0.12) | +0.144 (−0.13) | +0.144 | **B:PURE-COST (clean)** |
| **T5b AVAX/DOT** | **β** | normal/plock | 4.00 | 0.100 | **+0.052 (−0.10)** | +0.249 (**+2.16**) | +0.221 | **B:ZONE-NARROW (clean)** |
| T8c SOL/AVAX | eq | normal | 1.90 | — | +0.127 | +0.235 (+1.43) | +0.096 | B:cost-unreliable |

## Reads (framing)

**H1 (sizing alignment):** unchanged, strengthening — separate track. Not a Query-1 question.

**Classification B (H2):** **exit-redesign / Item 14 is NOT indicated on the clean data.** Both β-sized eligible trades have **pnl_at_mean below costs** (T2b +0.052 vs 0.251; T5b +0.052 vs 0.100). Zero trades anywhere classified EXIT-TOO-LATE. Kill condition 3 fires **directionally (N=2 clean)**: the leak is not "held past a profitable mean" — the mean was never profitable enough to clear costs. → **Points toward Branch 2, sub-lever UNDETERMINED:**
   - *cost-too-high* (→ maker 2b / spread-gating 2a) **vs** *edge-too-thin* (mean-reversion capture at $200 on this universe is structurally ~$0.05 — no cost lever closes a $0.05 gap → §5 negative-result territory).
   - The clean data cannot yet separate these. **The §7 cost diagnostic (residual vs effective half-spread) is the discriminator** — promoted from prep to critical path. Do NOT assert "Branch 2 = cost/universe" flatly.
   - Note the suspiciously tight clustering: both clean eligible trades sit at **pnl_at_mean ≈ +$0.052**. At N=2 this may be coincidence or may indicate a mean-reversion-capture ceiling on this universe. Flag, do not over-read.

**Classification A (mean-shift):** **not killed.** 2/3 clean β-sized coint-failures (T3b, T4b) are DECOUPLED — z reverted materially favorably (1.54σ, 2.10σ) while dollar PnL stayed ≤0 throughout. On β-sized trades this is **not** a sizing artifact. (T1b TRACKED-THEN-BROKE, and separately a thin-pair cost case — out of the decoupled set.) **Query 2 decomposes the *mechanism* (mean-shift vs β-drift) on these two holds — it cannot establish a rate (that is Query 3).** Refuted-lever guardrail intact: no entry-slope/level revival.

**Directional through-line (HYPOTHESIS, N-flagged):** every clean signal now points the same way — *away from entry-time and exit-geometry fixes, toward hold-window behavior and universe selection.* H1: sizing solved. Class B: leak is not exit-timing. Class A: failures are relationship instability *during the hold*, invisible at entry. The remaining leverage — if any exists — looks like it lives in hold-window monitoring and universe quality. Stated **as a converging hypothesis at N=2-clean, not a finding** (this is exactly the low-N "coherent through-line" shape the research paper warns about — so it is labeled, not concluded).

## Two tracked columns — ADD to future per-run Section 3D
For every $/σ-eligible trade going forward, record both: **`mfe > costs?`** AND **`pnl_at_mean > costs?`**. The second is the thesis-relevant one (the first is hindsight-peak). Current clean eligible: T2b (no / no), T5b (yes / **no**).

*Query 1 covers the full closed-trade union (exp_coint_stability_v1 T1c–T14c equal-notional + exp_beta_aware_sizing_v1 T1b–T5b β-sized). N-discipline: clean (β-sized) eligible N=2, clean coint-failures N=3 — directional only. Query 3 (scale) gated on operator.*

---

## Query 2 — mean-shift vs β-drift decomposition (DECOUPLED set: T3b, T4b)

**Method:** pulled 1m klines (OKX history-candles, via `retroactive_beta.py` machinery) over each hold window + 200-bar pre-entry context; recomputed rolling OLS β (log-price, window matching live) at entry and exit; reconstructed the log-spread and its rolling z. N=2 holds — **mechanism on these two, not a rate** (rate is Query 3).

**Robust result — β-drift RULED OUT (both holds):**

| Trade | rolling β entry | rolling β exit | drift |
|---|---|---|---|
| T3b BNB/LINK | 0.398 | 0.391 | **−1.6%** |
| T4b DOGE/AAVE | 0.755 | 0.760 | **+0.6%** |

Entry β reproduced the logged values (0.378 / 0.760); β barely moved over the ~11-min holds. β is a 200-bar OLS, robust to intrabar timing → this conclusion is solid. **Dynamic re-hedging / β-stability-screen is NOT the indicated lever.**

**Caveat (stated):** the bar-close z reconstruction did **not** faithfully reproduce the live *intrabar* z — T3b exit z +0.96 vs logged +0.58; T4b entry z **sign-flipped** (+1.24 vs logged −2.20), a leg-order/intrabar-timing artifact. So the direct price-vs-mean attribution % is **not reliable** and is not reported as fact.

**Mechanism by elimination (robust):** Query 1 established dollar decoupling (PnL ≤0 while z reverted, β-sized). Query 2 shows β was stable. Therefore, had price *truly* reverted toward the entry-window level with stable β, the β-correct position **would have profited** — it did not. So the z-reversion was the **rolling mean drifting toward price (mean-shift)**, not price returning. Mean-shift is implicated by elimination; T3b's direct attribution leaned the same way (imprecise).

**Lever mapping (spec §4, refuted-lever guardrail intact):** mean-shift + stable β → **post-entry/structural** levers: exit-speed on dollar-divergence (bail when dollars are red while z reverts, before `watch_timeout`), hold-time cap, historically-stability-screened universe (connects to research-paper §9.5 dynamic-coint-monitoring). **NOT** re-hedge (β stable), **NOT** entry-slope/level (refuted, exp_coint_stability_v1 Verdict 10B).

*Query 2: β-drift ruled out (robust, N=2); mean-shift implicated by elimination; price-vs-mean % unreliable (z-reconstruction caveat). Feeds structural-review Branch framing — strategist to fold.*

---
---

# Run 132 (2026-05-29) — T6 SOL/AVAX  ← 3rd $/σ-ELIGIBLE trade (near-replica of T5)

## Section 1 — Run Summary
- Accepted trades: 1 (SOL/AVAX). Closed: 1 (T6). Run end: `RUN_END reason=max_session_trades`.
- Session PnL: −$0.1285 (equity 2653.21 → 2653.08). Wins 0 / Losses 1 (net); **gross position_pnl POSITIVE (+$0.065)** — strategy worked, costs ate it.
- Circuit breaker: not tripped. (Note: SOL/AVAX is the same pair as T8c in exp_coint_stability_v1 — recurring liquid pair.)

## Section 2 — Per-Trade Telemetry

| Field | T6 (run_132) |
|---|---|
| Pair | SOL-USDT-SWAP/AVAX-USDT-SWAP |
| Side | long_negative_short_positive (long SOL, short AVAX; BUY_SPREAD) |
| Entry z → Exit z | −2.0637 → **+1.1997** (reverted through 0, overshot) |
| Δz (abs) | **3.263** |
| Exit reason | normal (mechanism: `trade_manager_pnl_profit_lock`) |
| Hold (min) | 20.8 |
| MFE | +$0.179 (equity) / +$0.233 (snapshot, z=+2.25) — **POSITIVE** |
| position_pnl (gross) | **+$0.065** (POSITIVE) |
| Net PnL (equity) | −$0.1285 |
| full_tp_touched / guard blocks | True / **86** |
| **max PnL inside |z|<0.35 zone** | **+$0.0067** (at z=+0.084) — the decisive number |

## Section 3 — β-Sizing Mechanical Verification

```
BETA_SIZING: beta=0.9107 gross=200.00 capital_long=104.68 capital_short=95.32 side=negative_z
```
- leg1 (long SOL) = 200/(1+0.9107) = **104.67** → matches 104.68 ✓; leg2 (short AVAX) = 200×0.9107/1.9107 = **95.33** → matches 95.32 ✓; gross = 200.00 ✓; no fallback.
- **β-sizing now 6/6 mechanically exact, 0 fallbacks.**
- **β=0.9107 is the first NEAR-UNITY β** (inside [0.8, 1.2]). β<1.0: 4/6; materially non-unity: **5/6** (T6 is the exception); range [0.378, 1.495] unchanged.

## Section 3C/3D — $/σ (ELIGIBLE) + the two tracked columns

T6 passes Rule v1.2: exit=normal ✓, MFE>0 ✓, |Δz|=3.26≥0.5 ✓. **$/σ = gross +$0.065 / 3.263 = +$0.020/σ, POSITIVE.**

| Trade # | Run | Pair | β | Δz | position_pnl | real_costs | **mfe>cost?** | **pnl_at_mean>cost?** | $/σ | Sign |
|---|---|---|---|---|---|---|---|---|---|---|
| T2 | run_126 | LTC/KSM | 0.633 | 2.270 | +$0.146 | $0.251 | no | **no** (+0.052) | +$0.064 | **+** |
| T5 | run_131 | AVAX/DOT | 0.659 | 4.002 | +$0.069 | $0.100 | yes | **no** (+0.052) | +$0.017 | **+** |
| T6 | run_132 | SOL/AVAX | 0.911 | 3.263 | +$0.065 | $0.194 | borderline (snap 0.233≥0.194; equity 0.179<0.194) | **no** (+0.026; in-zone max +$0.007) | +$0.020 | **+** |

**After 6 trades (3 eligible):**
- **Sign-flip rate: 0/3 = 0%** (all positive). Aggregate $/σ (pooled): (0.146+0.069+0.065)/(2.270+4.002+3.263) = **+$0.029/σ** (positive). **H1 holding strong — β-sizing aligns signal and position, 3/3.**
- **edge_clears_costs: 0/3.** And the disambiguating column **`pnl_at_mean > cost?` is NO on all 3** (+0.052, +0.052, +0.026 — all far below their costs). The thesis-exit edge has **never** cleared costs across the eligible set.

## Section 4 — Reconciliation
- position_pnl +$0.065 (gross, positive); equity_change −$0.1285; fees $0.10 + slippage $0.04 + unexplained **−$0.054** = real costs **$0.194**. basis pre_close_equity_delta ✓; pass_fail PASS. Negative residual (−$0.054) but below the $0.15 flag.

## Section 5 — Coint Stability Gate (Maintenance)
- entry_coint_stability_slope ≈ 0 (1.3e-12), evaluated_count=1. Gate passed. T6 = normal exit (coint held). Maintenance only.

## Section 6 — Counter Update (after T6)

```
trades_since_experiment_start: 6 (T1 JUP/YGG, T2 LTC/KSM, T3 BNB/LINK, T4 DOGE/AAVE, T5 AVAX/DOT, T6 SOL/AVAX)
$/σ eligible: 3 (T2, T5, T6) — all positive; sign-flip 0/3 = 0%; aggregate +$0.029/σ
edge_clears_costs: 0/3 | pnl_at_mean > cost: 0/3
coint-failure count: 3/6 = 50% (T1, T3, T4) — trending DOWN (75% → 60% → 50%)
beta_range: [0.378, 1.495]; fallback: 0; β-sizing 6/6 exact
cumulative PnL (window): −$1.746 (T1 −0.962, T2 −0.105, T3 −0.267, T4 −0.253, T5 −0.030, T6 −0.1285)
win rate: 0/6 = 0%
trades_remaining: 14 (to 20 total); ≥5 more $/σ-eligible needed
next: run_133+ (already started), frozen config
```

## Section 7 — Reads from T6

**1. H1 confirmed-strengthening (3/3 eligible positive, sign-flip 0%).** T6 at near-unity β (0.911) tracked a 3.3σ move with positive gross PnL — β-sizing works across the β range now (0.38 → 1.49).

**2. T6 KILLS THE SIZING-ARTIFACT CONFOUND — the real advance.** The worry through T5: "in-zone edge below costs" might be a β≠1 artifact (at extreme β the dollar hedge and statistical hedge diverge, so tiny in-zone capture could be a sizing shadow, not signal). **T6 ran at β=0.91 (near-unity), where dollar and statistical hedge nearly coincide — and the in-zone capture was the SMALLEST yet (+$0.0067).** The thin in-zone edge survives precisely where sizing mismatch is minimal. Headline disambiguator for T6: **in-zone max PnL = +$0.0067 (at z=+0.084).** Cross-trade fact: **in-zone capture across 3 eligible trades spans +$0.007 to +$0.052, all below their respective cost floors, at β = 0.38 / 0.91 / 1.49 (sub-unity → supra-unity) — so NOT a sizing artifact.** The pattern is mechanism, not artifact.

**Mechanical account (named precisely, so §7 tests the right thing):** the strategy enters at |z|≈2+, bets on reversion to mean, exits in |z|<0.35. But dollar profit is not distributed evenly across the z-path — it concentrates at the extremes, and the |z|<0.35 zone is, almost by construction, where the spread is smallest and least dollar movement remains. By the time the spread reverts to its mean, there is almost nothing left to capture. This is NOT an exit-tuning problem (no zone placement captures dollars that aren't in-zone), and increasingly does not look like an exit problem at all.

**Holding the N-discipline — 3/3 confirms the pattern is REAL and not a sizing artifact; it does NOT yet pick the Branch-2 sub-reading.** Two reasons it is not a verdict: (a) **§7 hasn't run** — if costs cluster structurally high on these pairs and a tight-spread subset carries materially lower costs, a +$0.05 mean-edge against a +$0.03 cost floor *does* clear → cost-too-high after all; the clustering leans edge-too-thin but does not rule out cost-too-high until residual-vs-effective-half-spread is plotted. (b) **N=3 eligible are all liquid-major pairs** (LTC/KSM, AVAX/DOT, SOL/AVAX) — a narrow universe slice; in-zone capture could differ on pairs with other volatility-to-spread ratios. So: **pattern real and β-robust; sub-lever (cost-too-high vs edge-too-thin) still undetermined — §7 is the discriminator.** Exit-redesign / Item 14 still NOT indicated (no EXIT-TOO-LATE; above-cost profit is overshoot).

**3. Profit-lock fired again (2nd activation), again below cost-clearance.** `pnl=0.078 ≤ floor=0.120 (MFE=0.180)`. 2/2 profit-lock activations have locked sub-cost-clearing profit — the floor-below-cost-clearance calibration finding repeats. (Frozen variable; observation only.)

**4. E4 trending favorably.** Coint-failure rate 50% (3/6), down from 75%→60%→50% — now mid-band (45–60% review). Still **not evaluable** (needs ≥10 closed). The eligible population is growing (3 in last 2 trades) — the dilution looked worse at T4 than it does now.

*Audit covers: run_132_20260529_175721 (T6 SOL/AVAX). Run 133 already started.*
*β-sizing: PASS (β=0.9107, gross to the cent, 0 fallbacks; 6/6 exact). Reconciliation: PASS. $/σ: INCLUDED +$0.020 POSITIVE (3/3 eligible positive). pnl_at_mean > cost: NO (3/3). E4: WATCH (3/6=50%, not evaluable).*

---
---

# Premise-Check Correction (2026-05-29) — recorded so a killed premise isn't silently rebuilt

**Context:** the T6 reads above (Section 7) leaned the H2-null toward edge-too-thin partly on an implicit "the eligible set is the liquid-major cost floor, and still doesn't clear" structural argument. A read-only premise-check on the 19 reliable trades' `real_cost` **refuted that premise.** Recorded here per the decision-log principle that a disproven argument must be preserved, not quietly dropped.

**What the premise-check found (cost ranks over 19 reliable trades):**
- The 3 eligible trades rank **#3 ($0.100 AVAX/DOT), #15 ($0.194 SOL/AVAX), #17 ($0.251 LTC/KSM)** — they **span the distribution**, two in the expensive half; T2b is 3rd-priciest overall. **The eligible set is NOT the cost floor.**
- Cheapest trade overall: **T9c LINEA/ZRO $0.067 — a thin-leg pair, not a pure-major** (Item-12 counterexample re-confirmed). 2nd-priciest: FIL/ICP $0.395 (thin-alt, not meme). **Cost is pair-specific, NOT liquidity-tier-ordered.**
- Within-category spread: **pure-major $0.10–$0.19 (~2×, tight); has-thin-leg $0.067–$0.395 (~6×, uninformative).**

**Correction to the T6 Section-7 framing:**
- The **edge-too-thin lean is RETRACTED as a near-verdict** — its clean argument (eligible = cost floor) is false.
- What survives is **weaker and two-sided:** the cheapest *observed* cost ($0.067) still exceeds the ~$0.03 in-zone edge (suggestive of edge-too-thin), BUT eligible costs span 2.5× so there is real headroom (cost-too-high not dead). **The fork is genuinely unresolvable from N=3.**
- Consequence: **§7-as-specified (residual vs effective half-spread) is data-blocked** — half-spread is in no telemetry (depth-only in liquidity_checks.csv; no orderbook snapshot; OHLC klines lack bid/ask). The fork now routes to the **query-3 joint (in-zone-edge, cost) distribution at scale** (`docs/prompts/query3_output_spec_universe_scale_joint_distribution_v1.md`), which §3.1 resolves cleanly only on the pure-major subset (where category predicts cost) — itself a SUBSET-VIABLE-shaped outcome.
- Refuted-lever guardrail unchanged; no entry-slope revival.

*This correction postdates the T6 audit body and supersedes its directional edge-too-thin lean. β-sizing (H1) verdict is unaffected — sizing works (3/3 eligible $/σ-positive). The correction is only to which Branch-2 sub-lever the H2-null implies: undetermined, pending query 3.*

---
---

# Runs 134–135 (2026-05-30) — T7 SOL/CRV + T8 BCH/ETC  ← BOTH eligible; the fork picture SHIFTS

**Headline: `pnl_at_mean > cost` is now 2/5 eligible (T7, T8), up from 0/3.** Two new eligible trades both cleared costs at the thesis mean — the in-zone edge is NOT uniformly thin; it is **pair-dependent**. This further weakens the (already-retracted) edge-too-thin near-verdict and sharpens the SUBSET-VIABLE-shaped read.

## β-Sizing (both)
- T7 SOL/CRV: β=0.8865 → leg1 SOL 200/(1.8865)=106.02 ✓, leg2 CRV 93.98 ✓, gross 200. side=negative_z.
- T8 BCH/ETC: β=0.8633 → leg1 BCH(short) 200/(1.8633)=107.34 ✓, leg2 ETC(long) 92.66 ✓, gross 200. side=positive_z (long ETC, short BCH).
- **β-sizing now 8/8 mechanically exact, 0 fallbacks.** Both near-unity (β<1.0: 6/8; materially non-unity: 5/8).

## T7 — SOL/CRV (run 134): FIRST eligible WIN

| Field | T7 |
|---|---|
| Side / entry_z → exit_z | long SOL short CRV / **−2.784** (deepest entry yet) → −0.342 |
| Δz | 2.442 |
| Exit / hold | normal / **1.1 min** (fastest) |
| MFE / z_at_MFE | +$0.230 / **−0.342 (the zone edge)** |
| gross position_pnl | **+$0.230** (= MFE; exited AT its peak) |
| real_costs | $0.215 |
| Net PnL | **+$0.0153 — WIN** |
| guard blocks | **0** (in-zone PnL above floor → full_tp fired) |
| $/σ | +0.230/2.442 = **+$0.094/σ** (highest yet), POSITIVE |
| pnl_at_mean > cost? | **YES** (+$0.230 at z=−0.34 zone edge > $0.215) |

**Why T7 won where T5/T6 didn't:** deeper entry (z=−2.78 vs −2.06) → bigger dollar reversion; the spread reverted *fast* (1.1 min) and the exit caught it **at the zone edge (z=−0.34) with the edge intact (+$0.230 > floor $0.12)** → guard passed, full_tp fired, edge cleared costs. It did NOT overshoot. (Only 1 snapshot due to the 1.1-min hold; close data is authoritative.)

## T8 — BCH/ETC (run 135): edge CLEARED at the mean, but the exit LEAKED it

| Field | T8 |
|---|---|
| Side / entry_z → exit_z | long ETC short BCH / +2.174 → −0.119 |
| Δz | 2.293 |
| Exit / hold | normal / 9.6 min |
| MFE / z_at_MFE | +$0.282 (snapshot) / −0.60 (mild overshoot) |
| **pnl_at_mean (z≈0)** | **+$0.169 (at z=−0.051)** |
| gross position_pnl | +$0.124 |
| real_costs | $0.159 |
| Net PnL | −$0.035 (small loss) |
| guard blocks | 24 |
| $/σ | +0.124/2.293 = **+$0.054/σ**, POSITIVE |
| pnl_at_mean > cost? | **YES** (+$0.169 > $0.159) — but realized exit (+$0.124) gave it back |

**T8 is a genuine EXIT-TOO-LATE case** (distinct from T5/T6): the thesis-mean edge **did clear costs** (+$0.169 at z=−0.05 > $0.159), but the position held past the mean into a mild overshoot (z=−0.60, +$0.282) and the exit fired late at z=−0.12 (+$0.124), giving back the cleared edge to a net loss. **A mean-disciplined exit here would have netted a win.** (Mechanical bucket reads ZONE-NARROW off the *first* zone-entry +$0.127<cost, but the deeper mean-crossing +$0.169>cost is the truer read — exit-capture, not thin edge.)

## Cross-trade update (after T8) — the fork is now genuinely two-sided and pair-dependent

```
trades: 8 (T1–T8). $/σ eligible: 5 (T2, T5, T6, T7, T8) — ALL $/σ-positive, sign-flip 0/5 = 0%; pooled +$0.044/σ
edge_clears_costs (realized): 1/5 (T7 win) — up from 0/3
pnl_at_mean > cost: 2/5 (T7 +0.230>0.215, T8 +0.169>0.159) — up from 0/3  ← THE FORK UPDATE
  vs T2 (+0.052<0.251), T5 (+0.052<0.100), T6 (+0.026<0.194) — pnl_at_mean < cost
coint-failure: 3/8 = 37.5% (T1,T3,T4) — DOWN 75→60→50→37.5%, now BELOW the 40% baseline
beta: range [0.378,1.495]; 8/8 exact; 0 fallbacks
cumulative PnL: −$1.765 (T7 +0.0153, T8 −0.035); win rate 1/8
trades_remaining: 12 (to 20); ≥3 more eligible to the ≥8 gate
```

**What T7/T8 establish (held at N=5 eligible — directional):**
1. **In-zone edge is PAIR-DEPENDENT, not uniformly thin.** BCH/ETC and SOL/CRV cleared at the mean (+$0.169, +$0.230); AVAX/DOT, SOL/AVAX, LTC/KSM didn't (+$0.026–0.052). The dollar-spread traversed inside the zone differs by pair (volatility-to-spread structure) — confirming the §3.1 caveat with live data. **This is the SUBSET-VIABLE shape materializing.**
2. **Edge-too-thin is NOT a universal verdict** — 2/5 eligible cleared the thesis-mean edge. The last-turn lean is further weakened (it was already retracted as a near-verdict).
3. **On edge-bearing pairs, exit-capture matters again.** T7 captured the edge (exited at zone edge → win); T8 leaked it (held past the mean → loss). So **exit-redesign / Item 14 REOPENS for the edge-bearing subset** (distinct from edge-too-thin pairs where no exit helps). The N=3 retraction of "T5=exit-capture" stands (T5's edge was genuinely thin); T8 is a real exit-capture case.
4. **E4 trending strongly favorable** (37.5%, below the 40% baseline) — universe fragility looking less like the binding problem. Still not evaluable (<10 closed).

**This is exactly what query 3 was built to resolve** (the joint, pair-resolved distribution): which pairs carry in-zone edge that clears cost, and whether exit-capture recovers the leak on those. The live data is now *showing* the subset structure query 3 would map at scale — which strengthens the query-3 case but on its own merits (pair-dependent viability is real), not on the edge-too-thin lean (now clearly not universal).

*Audit covers: run_134 (T7 SOL/CRV, WIN) + run_135 (T8 BCH/ETC). Run 136 running. β-sizing 8/8 exact. H1: 5/5 eligible $/σ-positive, sign-flip 0%. Fork: pnl_at_mean>cost 2/5 — pair-dependent, SUBSET-VIABLE-shaped, exit-capture reopens for edge-bearing subset. E4: WATCH (3/8=37.5%, not evaluable).*

---
---

# Run 136 (2026-05-30) — T9 AVAX/CRV  ← COINT-FAILURE (β-sized DECOUPLED, clean)

## Section 1 — Run Summary
- Accepted trades: 1 (AVAX/CRV). Closed: 1 (T9). Run end: `RUN_END reason=max_session_trades`.
- Session PnL: −$0.1074 (equity 2653.06 → 2652.95).
- Exit_reason: `cointegration_watch_timeout` → **T9 is excluded from $/σ (Rule v1.2)**; routed to the coint-failure tracker.
- **Entry regime: `RISK_OFF`** — the shadow regime router did not block (regime router is in SHADOW mode per CURRENT_STATE; gate observes but does not enforce). RISK_OFF started ~6.5 min pre-entry and flipped back to RANGE ~15 min mid-hold (REGIME_CHANGE 06:12 local: RISK_OFF→RANGE, hold=1308s).
- Circuit breaker: not tripped.

## Section 2 — Per-Trade Telemetry

| Field | T9 (run_136) |
|---|---|
| Pair | AVAX-USDT-SWAP/CRV-USDT-SWAP |
| Side / entry_z → exit_z | long_positive_short_negative (long CRV, short AVAX) / **+2.205 → −0.498** |
| Δz | 2.703 (favorable reversion through 0 to mild overshoot) |
| Exit / hold | **cointegration_watch_timeout** / 25.7 min |
| MFE / z_at_MFE | +$0.161 (equity) / +$0.174 (snapshot, at z=−1.27) — overshoot side, past zone |
| **pnl_at_mean (z≈0)** | **−$0.015** (at z=−0.0006) — NEGATIVE despite favorable z-reversion |
| pnl_at_zone_entry | −$0.007 (first |z|<0.35 at z=+0.091) |
| gross position_pnl | +$0.006 (essentially zero) |
| Net PnL | −$0.1074 |
| Entry regime | **RISK_OFF** (shadow router didn't block) |

## Section 3 — β-Sizing Mechanical Verification

```
BETA_SIZING: beta=0.7649 gross=200.00 capital_long=86.68 capital_short=113.32 side=positive_z
```
- leg2 (long CRV, inst_2/positive) = 200×0.7649/1.7649 = **86.68** ✓
- leg1 (short AVAX, inst_1/negative) = 200/1.7649 = **113.32** ✓
- gross 200.00 ✓; no fallback.
- **β-sizing now 9/9 mechanically exact, 0 fallbacks.**
- β range unchanged [0.378, 1.495]; β<1.0: 7/9; materially non-unity: 6/9 (T6/T7/T8 near-unity).

## Section 3C — Classification A (coint-failure decoupling, |Δz|≥0.5 precondition applied)

**T9 = DECOUPLED (clean β-sized).** |Δz|=2.703 ✓ (precondition met); z reverted from +2.20 favorably through 0 into mild overshoot (z=−1.57 at MFE) and back to z=−0.50 at exit — *materially toward and through the zone*; **pnl_at_mean = −$0.015 ≤ 0** at z=−0.0006. The dollar position did not track the favorable z-reversion at the mean — same signature as T3b, T4b.

**β-sized coint-failure tally (Classification A):**
| Trade | Run | Pair | Class | pnl_at_mean | β-drift status (Q2) |
|---|---|---|---|---|---|
| T1b | r125 | JUP/YGG | TRACKED-THEN-BROKE | +0.102 | (not tested; thin-pair cost case) |
| T3b | r129 | BNB/LINK | **DECOUPLED** | −0.036 | β stable (Q2) |
| T4b | r130 | DOGE/AAVE | **DECOUPLED** | −0.007 | β stable (Q2) |
| **T9** | **r136** | **AVAX/CRV** | **DECOUPLED** | **−0.015** | not tested (n=3 now consistent with mean-shift) |

**3/4 clean β-sized coint-failures are DECOUPLED** (up from 2/3) — the mean-shift signature accumulates, β-drift remains ruled out (Q2 robust on T3b/T4b). T9 is a new clean data point consistent with the mean-shift mechanism. Refuted-lever guardrail intact (no entry-slope revival): T9 entered with `entry_coint_stability_slope=+0.000826`, well below the 0.020 threshold — yet another benign-slope coint-failure (the pattern from T1/T3/T4 continues).

## Section 4 — Reconciliation
- position_pnl +$0.006 (gross, near zero); equity_change −$0.107; difference −$0.113 ≈ fees $0.10 + slippage $0.04 + unexplained +$0.027 → real_costs **$0.113** (textbook). basis pre_close_equity_delta ✓; pass_fail PASS.

## Section 5 — RISK_OFF Entry Observation (deferred-item linkage)

T9 entered with `regime=RISK_OFF` and the shadow regime router did not block. This is documented shadow-mode behavior, but it is a **vector for coint-failure risk** worth noting alongside the existing deferred T3 item ("pre-entry regime-flip detection"): T3 flipped INTO RISK_OFF ~50s post-entry; T9 entered DURING RISK_OFF (started ~6.5 min before entry, flipped back to RANGE ~15 min mid-hold, then coint failed). Two distinct sub-cases of the same broader pattern (high-vol-regime entries → coint-failure risk). The deferred item should now cover both: (a) imminent-flip detection at entry (T3 case), and (b) entry-in-RISK_OFF blocking via shadow-router activation (T9 case). NOT actioned mid-window (frozen variable / shadow); flagged for the structural-review.

## Section 6 — Counter Update (after T9)

```
trades_since_experiment_start: 9 (T1–T9)
$/σ eligible: 5 (T2, T5, T6, T7, T8) — UNCHANGED (T9 excluded as coint-failure)
sign-flip rate: 0/5 = 0%; aggregate $/σ +$0.044/σ (unchanged); H1 still rock-solid
pnl_at_mean > cost: 2/5 (unchanged — T9 not in population)
coint-failure: 4/9 = 44.4% (T1, T3, T4, T9) — trajectory 75→60→50→37.5→44.4
  Reversed slightly above the 40% baseline; back in 40–50% band.
β: range [0.378, 1.495]; 9/9 mechanically exact; 0 fallbacks
cumulative PnL (window): −$1.872 (T9 −$0.107)
win rate: 1/9
trades_remaining: 11 (to 20); eligible: ≥3 more to the ≥8 gate
next: run_137+, frozen config
```

## Section 7 — E4 Read (now ONE trade from evaluability) and other notes

**E4 trajectory wobbled.** 37.5% → 44.4% — T9's coint-failure brought it back above the 40% baseline. The strongly-favorable narrative from last turn **softens, but does not reverse the direction**: it's still well below the >60% halt line and within the 45–60% review band's lower edge.

**One closed trade away from evaluability** (T10 = 10 closed → E4 becomes evaluable). Pre-committed posture per template §4 / E4 calibration note:
- T10 normal exit → 4/10 = 40% (at baseline, **not in halt band**, watch continues).
- T10 coint-failure → 5/10 = 50% (in 45–60% **review band, NOT halt**; flag for structural-review).
- For E4 to **fire (>60%)** in any near-term scenario, the next ≥2 trades would need to be coint-failures back-to-back. Plausible but not the base case given the recent trajectory.

So E4 is approaching evaluability with the picture in the favorable-but-not-resolved zone. No action this turn — pre-committed criteria hold.

**Other observations:** β-sizing remains flawless (9/9). H1 unchanged. Fork unchanged (T9 not in $/σ population). The DECOUPLED signature on clean β-sized coint-failures now at 3/4 — strengthens the mean-shift mechanism's empirical support without graduating it from "leading surviving hypothesis by elimination" (per Q2 framing, still requires Q3 for universe-rate / dominance).

*Audit covers: run_136_20260530_042557 (T9 AVAX/CRV, coint_watch_timeout, β-sized DECOUPLED). β-sizing: 9/9 exact. Coint-failure 4/9=44.4%, one trade from E4 evaluability. Mean-shift mechanism: 3/4 clean DECOUPLED. RISK_OFF shadow entry flagged for structural-review deferred items. H1 / Fork: unchanged (T9 not eligible).*

---
---

# Runs 137–139 (2026-05-30) — T10 + T11 + T12  ← E4 NOW EVALUABLE (review band, not halt) + a drawdown stretch

**Headlines:** Three losses back-to-back: −$0.405, −$0.563, −$0.845 = **−$1.813 in 3 trades** (single-trade losses 2nd and 3rd-largest in the experiment after T1 JUP/YGG −$0.962). **E4 is now evaluable** at 12 closed: **coint-failure 6/12 = 50% — in the 45–60% review band, NOT halt** per the calibration note. **T12 = first reconciliation FAIL in the β-sizing window** (unexplained −$0.196, ARB/OP RISK_OFF entry). **T10 is a new shape: "normal" exit with MFE<0** (z diverged in 35s) — neither Class A nor Class B; first adverse-normal exit in the experiment. **T11 used the same pair as T10 (AVAX/ETC) 35 min after T10 lost** — pair re-selection observation. β-sizing remains flawless (12/12 exact, 0 fallbacks).

## β-Sizing — 3 trades, all exact

| Trade | Run | Pair | β | gross | long cap | short cap | side | fallback |
|---|---|---|---|---|---|---|---|---|
| T10 | run_137 | AVAX/ETC | 0.4902 | 200.00 | 134.21 (AVAX) | 65.79 (ETC) | negative_z | no |
| T11 | run_138 | AVAX/ETC | 0.4571 | 200.00 | 62.74 (ETC) | 137.26 (AVAX) | positive_z | no |
| T12 | run_139 | ARB/OP | 0.6553 | 200.00 | 79.18 (OP) | 120.82 (ARB) | positive_z | no |

**β-sizing now 12/12 mechanically exact, 0 fallbacks.** T11 β=0.457 = 2nd-lowest β observed (after T3b 0.378). T10 β=0.490 = 3rd-lowest. β<1.0: 10/12; materially non-unity: 9/12.

## T10 — AVAX/ETC (run 137): NEW SHAPE — "normal" exit with MFE<0 (adverse-fast)

| Field | T10 |
|---|---|
| Side / entry_z → exit_z | long_neg_short_pos / **−2.077 → −3.729** (z DIVERGED further from 0) |
| Δz (abs) | 1.65 |
| Exit / hold | normal / **0.59 min (35 seconds)** |
| MFE / z_at_MFE | **−$0.138** (never positive) / −2.597 |
| MAE / z_at_MAE | −$0.257 / **−3.729 (the exit)** — exited AT max adverse |
| Snapshot count | **1** (0:35s into hold) |
| gross position_pnl | −$0.249 |
| real_costs | $0.156 (1.1× model; unexplained −$0.016, near zero) |
| Net PnL | **−$0.405** |
| **Classification** | **NEITHER A NOR B** — adverse-normal exit (MFE<0 fails Rule v1.2 (b); not coint-failure so not in Class A) |

**The shape:** entered at z=−2.08 expecting reversion up; z moved AGAINST it to −3.73 in 35 seconds, position closed "normal" at MAE. **First adverse-fast exit in the experiment** (no prior eligible/coint-failure trade has had MFE<0 — every prior trade had at least transient positive PnL). The "normal" exit label is the coarse trade_closes column; the actual mechanism may be a stop-tier (max_break_risk, hard-exit) firing on the rapid adverse move — worth checking in exit_decision_summary if this shape recurs. Goes to **neither the $/σ table nor the coint-failure tracker**; recorded as a new bucket (`adverse-normal`, n=1).

## T11 — AVAX/ETC (run 138, **SAME PAIR as T10**): coint-failure DECOUPLED

| Field | T11 |
|---|---|
| Side / entry_z → exit_z | long_pos_short_neg (long ETC, short AVAX) / +2.023 → +1.399 (partial revert, didn't reach zone) |
| Δz (abs) | 0.624 (just above the |Δz|≥0.5 Class-A precondition) |
| Exit / hold | **cointegration_lost** / 10.3 min |
| MFE / z_at_MFE | **−$0.091** (never positive) / +1.706 |
| MAE | −$0.511 |
| Snapshot count | 10 (all NEGATIVE PnL: −0.11 → −0.34) |
| **pnl_at_mean (z≈0)** | **−$0.34** (at z=+1.40 exit; never reached zone) |
| gross position_pnl | −$0.441 |
| real_costs | $0.122 (textbook; unexplained +$0.018) |
| Net PnL | **−$0.563** |
| **Classification A** | **DECOUPLED** — z reverted favorably (2.02 → 1.40, partial); pnl_at_mean −$0.34 ≤ 0; never tracked. β-sized → clean evidence for mean-shift mechanism |

**Pair re-selection observation (NEW for deferred items):** T11 entered AVAX/ETC at +2.02 only **~35 minutes after T10 exited the same pair at −$0.405 loss** (T10 exit 00:36, T11 entry 01:10). The pair-discovery pipeline re-selected an unstable pair within the cooldown-or-less window. The opposite side (T10 long-neg, T11 long-pos) doesn't sanitize the underlying instability. **Worth flagging:** a recently-failed-pair cooldown or memory mechanism could prevent this; goes to structural-review deferred items alongside the regime-detection items.

## T12 — ARB/OP (run 139): coint-failure TRACKED-THEN-BROKE + RISK_OFF entry + RECON FAIL

| Field | T12 |
|---|---|
| Side / entry_z → exit_z | long_pos_short_neg (long OP, short ARB) / +2.349 → +1.448 |
| Δz (abs) | 0.901 |
| Exit / hold | **cointegration_lost** / 14.5 min |
| **Entry regime** | **RISK_OFF** (shadow router did not block — 2nd occurrence after T9) |
| MFE / z_at_MFE | +$0.078 / −0.530 (brief overshoot through 0 to the negative side) |
| MAE | −$0.744 |
| Snapshot count | 14 |
| **pnl_at_mean (z≈0)** | **+$0.011** (at z=+0.889, t=4 min) — barely positive; trade briefly straddled 0 with marginal PnL |
| gross position_pnl | −$0.509 |
| real_costs | **$0.336 (2.4× model)** — elevated |
| **unexplained** | **−$0.196** (below the −$0.15 threshold) |
| pass_fail | **FAIL** (large_unexplained_warning=True, large_delta_warning=True) |
| Net PnL | **−$0.845** |
| **Classification A** | **TRACKED-THEN-BROKE** (pnl_at_mean +$0.011 > 0, borderline). Position briefly tracked through the mean (MFE +$0.078 at z=−0.53), then z came back to +2.37 and the coint relationship broke. |

**T12 is structurally important — three flags in one trade:**
1. **2nd RISK_OFF-entry case** (after T9), shadow router didn't block, ended in coint-failure. Strengthens the high-vol-regime-entry → coint-failure-risk vector (now **2/2** RISK_OFF entries → coint-failures in the β-sizing window).
2. **First reconciliation FAIL in the β-sizing experiment window** — unexplained −$0.196 (vs −$0.15 threshold). ARB/OP are mid-tier majors but the RISK_OFF execution environment may have widened spreads/funding effects. Real costs 2.4× model.
3. **The RISK_OFF cost penalty** ($0.336 vs textbook ~$0.14) — if this generalizes, it's evidence that the cost-too-high reading has real headroom on RISK_OFF entries specifically. Connects to the §3.1 cost-axis discussion: the RISK_OFF subset may have a different cost distribution from RANGE entries. **Worth tagging shadow-entries by entry-regime in query 3 instrumentation** (when authorized).

## Classification A update (β-sized coint-failures only — clean)

| Trade | Run | Pair | Class | pnl_at_mean |
|---|---|---|---|---|
| T1b | r125 | JUP/YGG | TRACKED (thin-pair cost case) | +$0.102 |
| T3b | r129 | BNB/LINK | **DECOUPLED** | −$0.036 |
| T4b | r130 | DOGE/AAVE | **DECOUPLED** | −$0.007 |
| T9 | r136 | AVAX/CRV | **DECOUPLED** | −$0.015 |
| **T11** | **r138** | **AVAX/ETC** | **DECOUPLED** | **−$0.34** |
| **T12** | **r139** | **ARB/OP** | **TRACKED-THEN-BROKE (borderline)** | **+$0.011** |

**4/6 clean β-sized coint-failures DECOUPLED** (up from 3/4); mean-shift signature continues to be the dominant pattern, now on a larger N. Refuted-lever guardrail intact: T11/T12 entry slopes both benign (T11 −0.00039, T12 −0.00082, far below the 0.020 threshold) — coint-failures continue to be unpredictable from entry-time coint metrics.

## Section — E4 Evaluation (NOW EVALUABLE, 12 closed)

```
coint-failure rate (window): 6/12 = 50.0% (T1, T3, T4, T9, T11, T12)
trajectory: 75 → 60 → 50 → 37.5 → 44.4 → 50 (oscillating, not monotonic)
prior-window baselines for comparison:
  exp_guard050 (19 trades): 36.8%
  exp_coint_stability (10 trades): 40.0%
  raw 9-trade pre-history: 55.6%
current 50% is ELEVATED vs the most recent baselines (36.8%, 40%) but WITHIN the historical band [36.8, 55.6]
```

**Pre-committed action per E4 calibration (template v1.1 §4):**
- 50% is in the **45–60% REVIEW BAND**, NOT the >60% HALT line.
- The calibration note specifically anticipated this case: *"the 45–60% band is elevated-but-plausibly-baseline → review, do not halt"* — exactly to avoid false halts on small-window variance near the baseline.
- Trajectory is oscillating (75→60→50→37.5→44.4→50), not breaking out upward. Within the historical band.
- **E4 is NOT firing.** Pre-committed action: **flag for structural-review, continue collection.**

**Structural-review flag (carried forward):** coint-failure rate stabilized in the 40–50% band over T1–T12; consistent with the universe's baseline coint-fragility, not a deterioration. The mean-shift mechanism (now 4/6 clean DECOUPLED) is the most testable hypothesis to address it, but query 3 remains the instrument to characterize the rate at scale.

## Section — RISK_OFF Entry Vector (n=2 cases now: T9, T12)

Both RISK_OFF entries in the β-sizing window led to coint-failures:
- **T9** AVAX/CRV: entered DURING RISK_OFF (regime started ~6.5 min pre-entry, flipped back mid-hold), coint timed out. Costs textbook ($0.113).
- **T12** ARB/OP: entered DURING RISK_OFF, coint broke at 14.5 min. **Costs 2.4× model** ($0.336, recon FAIL).

**Strengthened hypothesis (still n=2):** entry-during-RISK_OFF correlates with coint-failure AND possibly elevated execution cost. This survives the refuted-lever guardrail (regime ≠ entry-time coint metric); the regime router already computes the signal in SHADOW mode; activating it would be cheap to test. **Flagged for structural-review deferred items** alongside the T3 imminent-flip case. Two distinct sub-cases of the same broader pattern; should be folded into one combined deferred item.

## Section — Pair Re-Selection Observation (T10/T11 same pair, ~35 min apart)

T11 entered AVAX/ETC at +2.02 only 35 min after T10 exited the same pair at −$0.405. The opposite side doesn't sanitize the underlying instability — and indeed T11 also lost (−$0.563, coint-failure). **New deferred item for structural-review:** a recently-failed-pair cooldown / blacklist-with-decay mechanism. Currently no such cooldown — once a trade closes, the pair is immediately re-eligible. This is an entry-side lever that survives the refuted-lever guardrail (it's a recent-failure memory, not a coint metric).

## Cumulative Counter Update (after T12)

```
trades_since_experiment_start: 12 (T1–T12)
$/σ eligible: 5 (T2, T5, T6, T7, T8) — UNCHANGED. T10 fails MFE>0; T11, T12 are coint-failures.
sign-flip: 0/5 = 0%; aggregate pooled +$0.044/σ (unchanged); H1 STILL ROCK-SOLID
pnl_at_mean > cost: 2/5 unchanged (T7, T8); fork unchanged
coint-failure: 6/12 = 50% (T1, T3, T4, T9, T11, T12); E4 evaluable, REVIEW BAND, NOT HALT
adverse-normal exits (new bucket, MFE<0): 1 (T10)
classification A (β-sized): 4/6 DECOUPLED (T3b, T4b, T9, T11) | 2/6 TRACKED (T1b thin-pair, T12 borderline)
β: range [0.378, 1.495]; 12/12 exact; 0 fallbacks
RISK_OFF-entry vector: 2/2 cases → coint-failure (T9, T12)
recon FAIL (β-sizing window): 1 (T12 ARB/OP, −$0.196 unexplained, 2.4× cost overrun)
cumulative PnL (window): −$3.685 (T10 −0.405, T11 −0.563, T12 −0.845 = −$1.813 in last 3)
win rate: 1/12 = 8.3%
trades_remaining: 8 (to 20); eligible: ≥3 more to the ≥8 gate
next: run_140+, frozen config
```

## Strategic Read (held at N — directional, not verdict)

**The fork picture from T7/T8 is intact.** None of T10–T12 entered the $/σ population, so H1 (5/5 sign-positive, +$0.044/σ pooled) and the pair-dependent edge picture (pnl_at_mean>cost 2/5) are unchanged. The fork is still the live question, query 3 is still the instrument.

**Coint-failure mechanism is firming.** Now 4/6 clean β-sized DECOUPLED across the window. Mean-shift remains the leading surviving hypothesis (β-drift ruled out per Q2; entry-time coint metrics refuted; T9/T11/T12 all entered with benign slopes and failed).

**The RISK_OFF entry vector now has weight.** 2/2 RISK_OFF entries → coint-failures, AND T12 carries a 2.4× cost overrun. **This is the first candidate entry-side lever that connects coint-failure to a signal the bot already computes (in shadow).** Cheap to test (activate the regime gate from shadow to live). Still n=2 — candidate hypothesis, not a finding. Goes to structural-review.

**E4 evaluable, not firing.** 50% in review band; pre-committed action is to flag and continue. The trajectory (oscillating in 37.5–75 range) is within the historical baseline; no halt indicated. The pre-commit discipline held — and this is exactly the case the calibration anticipated.

**Drawdown stretch (−$1.813 over 3 trades) reframed:** all 3 losses are explainable mechanistically (T10 adverse-fast normal exit; T11 coint-failure on a re-selected unstable pair; T12 coint-failure on a RISK_OFF entry with elevated costs). None contradict the fork picture from T7/T8. But it's the worst 3-trade stretch in the experiment, and cumulative PnL is now −$3.685 — worth keeping eyes on whether this is mean-reverting noise or a regime shift.

*Audit covers: run_137 (T10 AVAX/ETC adverse-normal), run_138 (T11 AVAX/ETC coint_lost DECOUPLED), run_139 (T12 ARB/OP coint_lost TRACKED-borderline, RISK_OFF entry, RECON FAIL). β-sizing: 12/12 exact. E4 evaluable (6/12=50%, REVIEW band, NOT halt). 4 new structural-review items: RISK_OFF-entry vector (2 cases now), pair-re-selection cooldown (T10/T11 same pair), recon-fail on RISK_OFF entry (T12), adverse-normal exit shape (T10). H1 / Fork: unchanged. Cumulative −$3.685.*

---
---

# Run 140 (2026-05-30) — T13 BTC/DOGE  ← 4th loss in a row; **highest β observed**; β-sized DECOUPLED on supra-unity β; validator's anchor trade

**Headlines:** Coint-failure (cointegration_lost). **β=1.8414 — highest β in the experiment** (above T1's 1.4946; β range now extends to [0.378, 1.841]). Deep entry (z=+2.668, same depth class as T7's −2.78), but unlike T7 this was a coint-failure. **MFE never positive throughout 38-min hold** despite a 9σ total z-traversal. **Coint-failure rate now 7/13 = 53.8%** (up from 50%, into the upper part of the 45–60% review band — NOT halt, but the trajectory matters). 4 losses in a row (T10–T13, −$2.144 over 4 trades). Cumulative now −$4.016. **T13 is also the trade the §5 validator ran against — its 28-tick comparison series established the terminal finding** that retired the shadow-simulation build.

## β-Sizing

```
BETA_SIZING: beta=1.8414 gross=200.00 capital_long=129.61 capital_short=70.39 side=positive_z
```
- leg2 (long BTC, inst_2/positive) = 200×1.8414/(1+1.8414) = 368.28/2.8414 = **129.61** ✓
- leg1 (short DOGE, inst_1/negative) = 200/2.8414 = **70.39** ✓
- gross 200.00 ✓; no fallback. **β-sizing 13/13 mechanically exact, 0 fallbacks.**
- **β=1.8414 = highest β in the experiment.** Supra-unity / asymmetric leg weighting (1.84:1 BTC:DOGE notional). The DECOUPLED outcome on this β is structurally important — confirms mean-shift mechanism extends across the full observed β range (0.378 → 1.841), not concentrated in sub-unity territory.

## T13 — BTC/DOGE Per-Trade Telemetry

| Field | T13 |
|---|---|
| Side / entry_z → exit_z | long_pos_short_neg (long BTC, short DOGE) / +2.668 → +0.490 |
| Δz (abs) | 2.18 (precondition met for Class A) |
| **z-traversal range** | **+2.616 (MAE) → −2.994 (MFE) → exit +0.490** (~9σ total absolute) |
| Exit / hold | **cointegration_lost** / 38.2 min (longest coint-failure hold yet) |
| MFE / z_at_MFE | **−$0.022 (NEVER positive)** / z=**−2.994** (far overshoot) |
| MAE | −$0.274 at z=+2.616 (near entry) |
| **max in-zone PnL** | **−$0.086 at z=−0.265** (in-zone PnL was NEGATIVE throughout the 92 guard evaluations) |
| gross position_pnl | −$0.197 |
| real_costs | $0.134 (textbook; unexplained +$0.006) |
| Net PnL | **−$0.331** |
| Snapshot count | 38 (long hold, full data) |
| full_tp guard blocks | **92** (highest yet — guard correctly refused to fire on always-negative in-zone PnL) |
| entry_coint_stability slope/evaluated | None / 0 (insufficient_history — gate didn't evaluate) |

**The shape:** entered at z=+2.668. z moved adversely to +2.616 first (MAE at -$0.274). Then z reverted aggressively — through 0, through the |z|<0.35 zone (in-zone first at 05:29:46, 3 min in), past zero to z=−2.994 (a 5.66σ excursion!). MFE there was still only −$0.022. Then z came back up to +0.49 where it exited via cointegration_watch_timeout. **Total absolute z-distance traveled ~9σ; net dollar PnL never positive.**

## Classification A — DECOUPLED (on supra-unity β; mean-shift on the upper side of β)

Apply |Δz|≥0.5 precondition: 2.18 ≥ 0.5 ✓. z reverted favorably (entered and passed through the zone). **pnl_at_mean ≤ 0:** max in-zone PnL was **−$0.086** (definitively negative throughout the zone). **A:DECOUPLED.**

**Why this matters:** β=1.8414 means the dollar weight is **heavily on the long-BTC leg** (129.61 vs 70.39). The position should profit when BTC rises relative to DOGE (spread fall). Looking at actual movement (validator captured the marks): exit BTC=73569 (vs entry 73556 → BTC +0.017%), exit DOGE=0.10130 (vs entry 0.100989 → DOGE +0.31%). BOTH legs rose, but DOGE rose **18× faster in percentage terms.** Long BTC PnL = +$0.022; short DOGE PnL = -$0.217; net = -$0.20 ✓. **The "spread" in dollar terms went the wrong way — DOGE outpaced BTC dramatically — even as z statistically "reverted" toward 0.** That's mean-shift in cleanest form: z-reversion driven by the rolling mean catching up, not by price reversion to the entry level.

**Clean β-sized Class A tally now: 5/7 DECOUPLED** (T3b, T4b, T9, T11, T13; T1b TRACKED thin-pair, T12 borderline TRACKED). Mean-shift signature is **now demonstrated across β range 0.378 → 1.841 — the entire observed β distribution.** Q2's β-drift-ruled-out conclusion holds; the universe's coint-failure mechanism is mean-shift independently of where β sits in the distribution.

## Reconciliation

- position_pnl (gross): −$0.197 | equity_change: −$0.331 | diff (real_costs): $0.134 | fees $0.10 + slippage $0.04 + unexplained +$0.006 = textbook 0.96× model. basis pre_close_equity_delta ✓ | pass_fail: **PASS.** Clean reconciliation despite the large adverse trade — confirms the loss is from the position itself, not execution overrun.

## Validator Anchor — T13 served the §5 terminal finding

T13 is the trade the §5 Path-1 validator ran against (subscribed mid-trade, captured 28 ticks of WS-mark vs recorded-`upl` comparison). All 28 ticks were **outside $0.01** (median |diff| ~$0.13, range $0.091–$0.176, structural ~5.9 bps offset on BTC). This established the terminal finding that retired the shadow-simulation query-3 build. Evidence preserved at `docs/audits/fidelity_validator_run_140_terminal_finding_evidence.csv`. **T13's substantive outcome (coint-failure DECOUPLED on supra-unity β) and its validator role (anchor trade for the gate's terminal finding) are independent observations on the same trade — both worth recording.**

## Cumulative Update (after T13)

```
trades: 13. $/σ eligible: 5 unchanged (T13 is coint-failure, not eligible)
sign-flip: 0/5 = 0%; aggregate $/σ +$0.044/σ; H1 still rock-solid (no new eligible data)
pnl_at_mean > cost: 2/5 unchanged; fork unchanged
coint-failure: 7/13 = 53.8% (T1, T3, T4, T9, T11, T12, T13) — UP from 50%, into upper part of 45–60% review band
  trajectory: 75→60→50→37.5→44.4→50→53.8 (last 3 trades all coint-failures — directional uptick)
β range: [0.378, 1.841] (extended from 1.495 to 1.841); 13/13 exact; 0 fallbacks
recon FAIL count: 1 (T12 only; T13 reconciliation textbook)
adverse-normal bucket: 1 (T10 only)
cumulative PnL: −$4.016 (T13 −$0.331; 4 losses in a row: T10−T13 = −$2.144)
win rate: 1/13 = 7.7%
trades_remaining: 7 (to 20); eligible: ≥3 more needed for the ≥8 gate
next: run_141+, frozen config
```

## E4 Read — UP but still in review band; trajectory direction matters

**Coint-failure rate now 53.8% (7/13).** This is up from 50% (6/12) → still below the >60% halt line, BUT in the **upper part of the 45–60% review band**, and the last 3 trades (T11, T12, T13) were ALL coint-failures, dragging the rate up. Pre-committed E4 calibration:

- **Not yet halt** (>60% is the line; we're at 53.8%).
- Still within the historical band [36.8, 55.6] — barely (53.8 < 55.6).
- **Trajectory has reversed direction:** 37.5% → 44.4% → 50% → 53.8% over last 4 closed trades. The strongly-favorable framing from after T9 (37.5%) has fully reversed.
- **For halt at T14:** need 9/14 = 64.3% → next trade must be coint-failure AND we'd be at 8/14 = 57.1% (still below 60%); only at T15 with 9/15 = 60% does it hit the line; T15 coint-failure plus prior pattern would push to >60%.
- **Pre-committed action:** continue to flag for structural-review; no halt yet. But the trajectory is the structural review's main question now, not whether 50–55% is "noise."

**Honest read:** the E4 calibration's halt line is well-placed — it would have falsely halted at 50% on prior turn's wobble. Now at 53.8% with a 3-coint streak, the band's purpose is being tested: is this still "elevated-but-plausibly-baseline" or is it the start of a real regime shift? Pre-commit is unambiguous (no halt), but the structural review will need to weigh whether the universe entered a higher-coint-failure regime around T9 onward.

## Strategic Read (held at N — directional, not verdict)

**Fork unchanged.** T13 is coint-failure, doesn't enter the $/σ population. H1 and pnl_at_mean>cost both unmoved from the T7/T8 state.

**Mean-shift mechanism is now broad-spectrum.** 5/7 clean β-sized coint-failures DECOUPLED, **across β from 0.378 to 1.841** (the full observed range). β-drift is ruled out at every β level we've seen. Refuted-lever guardrail intact: T13 had insufficient_history on the entry slope gate (didn't evaluate) — not a slope-predicted failure.

**RISK_OFF-entry vector unchanged** (T13 was RANGE, not RISK_OFF). Still 2/2 RISK_OFF entries → coint-failure (T9, T12). T13 broadens the coint-failure landscape but doesn't add to the RISK_OFF vector specifically.

**Drawdown 4 in a row, cumulative −$4.016, 1 win in 13.** Honestly: this experiment continues to lean toward the §5 negative-result reading — sizing works (H1 holds), edge has cleared costs on 1 of 5 eligible (T7, the deepest entry), and the universe's coint-fragility appears to be trending up rather than down. The RISK_OFF lever is the most credible thing that could change the picture, but it's still n=2 and there's no live test of it. The fork is still genuinely unresolved on its own data — but the *background* keeps pointing more clearly at "viable subset narrow or absent."

**Query-3 redirect implication:** T13 reinforces why redirecting the fork resolution to real eligible trades was right. The validator's terminal finding came from THIS trade, and at the same time T13 produced a non-eligible coint-failure that doesn't move the fork data. The structural review will read the fork off real eligible trades (currently 5; 3 more to the ≥8 gate); with coint-failures now running 3-in-a-row, the eligible accumulation rate has slowed sharply. The structural review may arrive at the 20-trade gate with fewer than 8 eligibles — exactly the case the spec's negative-result-bar wording was designed to honor.

*Audit covers: run_140_20260530_132503 (T13 BTC/DOGE coint_lost DECOUPLED β=1.8414; also: validator anchor trade for §5 terminal finding). β-sizing: 13/13 exact. E4: 7/13=53.8%, UP into upper review band but NOT halt (trajectory reversed favorable-to-elevated over last 4 trades). Mean-shift confirmed across full β range [0.378, 1.841]. RECON: textbook PASS. H1 / Fork: unchanged (T13 not eligible). Cumulative −$4.016, win rate 1/13. Query-3 redirect (commit ca1999a) recorded.*

---

# Run 141 (2026-05-30) — T14 AVAX/ETH  ← 5th loss in a row; coint-failure DECOUPLED at mid-range β; E4 climbs again (8/14=57.1%); pre-commit hinges on T15

**Headlines:** Coint-failure (cointegration_lost). **β=0.4562 — mid-range β** (sits inside the [0.378, 1.841] band, between T13's 1.841 high and T10's 0.378 low). Deep entry (z=+2.546), 37.9-min hold, classic mean-shift signature in position_snapshots (z fully reverted to z=0.09 with pnl=−$0.21). **Coint-failure rate now 8/14 = 57.1%** (up from 53.8%, deeper into the upper 45–60% review band but still NOT halt). 5 losses in a row (T10–T14, −$2.572 over 5 trades). Cumulative now −$4.444. **The E4 pre-commit's mechanical halt is one trade away if T15 is also a coint-failure** (9/15 = 60.0% AT halt line); if T15 is normal, trajectory was variance.

## β-Sizing

```
BETA_SIZING: beta=0.4562 gross=200.00 capital_long=62.66 capital_short=137.34 side=positive_z
```
- leg2 (long AVAX, signal_positive) = 200×0.4562/(1+0.4562) = 91.24/1.4562 = **62.66** ✓
- leg1 (short ETH, signal_negative) = 200/1.4562 = **137.34** ✓
- gross 200.00 ✓; no fallback. **β-sizing 14/14 mechanically exact, 0 fallbacks.**
- β=0.4562 places this trade in the **middle of the observed β range** [0.378, 1.841]. With T13 (β=1.841 upper) and T10 (β=0.378 lower) already showing DECOUPLED mean-shift, T14's mid-range DECOUPLED outcome further fills the β-distribution coverage. Mean-shift mechanism now confirmed at lower, mid, and upper β extremes — no β-dependence in failure mode.

## T14 — AVAX/ETH Per-Trade Telemetry

| Field | T14 |
|---|---|
| Side / entry_z → exit_z | long_pos_short_neg (long AVAX, short ETH) / +2.546 → +0.754 |
| Δz (abs) | 1.79 (precondition met for Class A) |
| Snapshot z-traversal | entry 2.55 → bobbed mid-1s → **0.45 → 0.09 (≈mean) → 0.75 exit** (full reversion to mean, then bounced) |
| Exit / hold | **cointegration_lost** / 37.9 min |
| MFE / z_at_MFE (CSV) | +$0.469 / z=3.17 (tick-level peak between snapshots; snapshot-stream max pnl was only +$0.035 at t=5min) |
| MAE / z_at_MAE (CSV) | −$0.437 / z=−0.045 (essentially at mean) — confirms mean-shift: deepest loss occurred WHEN z was at the mean |
| **In-zone PnL (snapshots)** | **At z=0.09 (t=37min): pnl=−$0.21**; at z=0.45 (t=36min): pnl=−$0.18 — pnl was negative throughout the in-zone window |
| gross position_pnl | −$0.313 |
| real_costs | $0.115 (fees $0.10 + slippage $0.04 − unexplained +$0.025; unexplained_pct=22.1% but absolute small) |
| Net PnL | **−$0.428** |
| Snapshot count | 38 (full 1-min cadence) |
| Regime / vol_pct | RANGE / 0.73–0.94 throughout hold (not RISK_OFF) |
| entry_coint_stability slope | −3.2e−5 (essentially flat; gate evaluated 1 time, passed) |

**The shape:** entered at z=+2.546 on AVAX/ETH. z immediately moved adversely to +2.88 at t=0 (-$0.063), then began reverting. Through the first 13 minutes, z drifted from 2.88 down to 0.66 with pnl bobbing near zero (small positive transients up to +$0.035). Then from t=14 onward, z continued falling toward the mean while pnl DECOUPLED — by t=36 (z=0.45) pnl was −$0.18; by t=37 (z=0.09, ≈at mean) pnl was −$0.21; at exit t=38 (z=0.75, bouncing back up) pnl was still −$0.21 ⇒ exit fired via cointegration_lost. **Net: z reverted ~2.4σ favorably and ended up −$0.43 net. Textbook mean-shift.**

## Classification A — DECOUPLED (mid-range β; mean-shift in the middle of the β distribution)

Apply |Δz|≥0.5 precondition: 1.79 ≥ 0.5 ✓. z reverted favorably (entered the zone at t=36, touched z=0.09 ≈ at mean at t=37). **pnl_at_mean ≤ 0:** in-zone snapshot pnl was **−$0.18 to −$0.21** (definitively negative across the full in-zone window). **A:DECOUPLED.**

**Why the MFE/MAE z-labels in CSV look inverted from MR expectations:** MFE z=3.17 with pnl=+$0.47 sits between snapshots (t=5 snapshot had z=1.08 with pnl=+$0.035; the +$0.47 peak was a tick-level transient not captured in 1-min snapshots), and MAE z=-0.045 with pnl=-$0.44 reflects the deepest in-zone loss. The 1-min snapshots are the authoritative data for in-zone classification; the tick-level CSV summary is consistent once you read it as "pnl peak happened intra-tick during an adverse z-spike before the reversion began." Classification is unambiguous from snapshots.

**Clean β-sized Class A tally now: 6/8 DECOUPLED** (T3b, T4b, T9, T11, T13, T14; T1b TRACKED thin-pair, T12 borderline TRACKED). Mean-shift signature now demonstrated at **β ∈ {0.378, 0.456, 0.476, 0.561, 0.667, 1.495, 1.841}** — substantially covering the observed β range. The β-independence of the failure mode is structurally locked in.

## Reconciliation

- position_pnl (gross): −$0.313 | equity_change: −$0.428 | diff (real_costs): −$0.115 | fees $0.10 + slippage $0.04 + unexplained +$0.025 = 1.22× the explained-cost floor. basis pre_close_equity_delta ✓ | pass_fail: **PASS.** unexplained_pct=22.1% is above the typical textbook 0.96× model but well under the 50% warn threshold; small absolute ($0.025); no large_unexplained_warning fired.

## Section — E4 Evaluation (NOW EVALUABLE, 14 closed)

**Coint-failure rate: 8/14 = 57.1%.** UP again from 53.8% (4 coint-failures in a row: T11, T12, T13, T14). Pre-committed E4 calibration:

- **Not yet halt** (>60% is the line; we're at 57.1%).
- **No longer within the historical band [36.8, 55.6]** — 57.1% has now exceeded the historical upper bound by 1.5pp. First time the rate has been outside its empirical band.
- **Trajectory has continued upward:** 37.5% → 44.4% → 50% → 53.8% → 57.1% over last 5 closed trades. Four consecutive coint-failures.
- **Pre-commit standing (from template v1.4 §4):**
  - T14 was coint-failure → does NOT resolve pre-commit on its own
  - **If T15 is coint-failure → 9/15 = 60.0% AT halt line → HALT EXECUTES MECHANICALLY**
  - If T15 is normal exit → 8/15 = 53.3% (back within band) → trajectory was variance, continue
- **No deliberation needed at T15 close.** The reading is mechanical and pre-written.

**Honest E4 read:** the rate has now broken above its historical band for the first time, the streak is 4 coint-failures in a row, and the next trade is the resolution. The "trajectory was variance" reading remains viable but is the less-likely default given the 4-streak — base-rate of 4 consecutive coint-failures under 50% is ~6%. The pre-commit being mechanical is the load-bearing piece here.

## Section — RISK_OFF Entry Vector (still 2/2; n=2)

T14 entered in RANGE regime (vol_pct 0.73 at entry, drifting to 0.94 during hold), not RISK_OFF. **Vector unchanged at 2/2: T9, T12 only.** T14 broadens the universe's coint-failure landscape across RANGE regimes specifically — RISK_OFF is not the only failure regime, but it remains the only entry condition where 100% of trades have been coint-failures.

## Cumulative Counter Update (after T14)

```
trades: 14. $/σ eligible: 5 unchanged (T14 is coint-failure, not eligible)
sign-flip: 0/5 = 0%; aggregate $/σ +$0.044/σ; H1 unmoved (no new eligible data)
pnl_at_mean > cost: 2/5 unchanged; fork unchanged
coint-failure: 8/14 = 57.1% (T1, T3, T4, T9, T11, T12, T13, T14) — UP from 53.8%, FIRST TIME OUTSIDE historical band [36.8, 55.6]
  trajectory: 75→60→50→37.5→44.4→50→53.8→57.1 (last 4 trades all coint-failures)
β range: [0.378, 1.841] (unchanged); 14/14 exact; 0 fallbacks
recon FAIL count: 1 (T12 only; T14 PASS)
adverse-normal bucket: 1 (T10 only)
cumulative PnL: −$4.444 (T14 −$0.428; 5 losses in a row: T10−T14 = −$2.572)
win rate: 1/14 = 7.1%
trades_remaining: 6 (to 20); eligible: ≥3 more needed for the ≥8 gate
next: run_142+, frozen config
```

## Strategic Read (held at N — directional, not verdict)

**Fork unchanged.** T14 is coint-failure, doesn't enter the $/σ population. H1 and pnl_at_mean>cost both unmoved from the T7/T8/T13 state.

**Mean-shift mechanism is now broad-spectrum across β.** 6/8 clean β-sized coint-failures DECOUPLED, across β from 0.378 to 1.841. With T14 at β=0.456, the middle of the β-distribution is filled in alongside the prior tails. **β-dependence of failure mode is empirically dead at every β level we've seen.** Refuted-lever guardrail intact: T14's entry slope was essentially flat (−3.2e−5), evaluated once and passed — not a slope-predicted failure.

**E4 trajectory pre-commit dominates the next-step strategy.** Per template v1.4 §4, T15 is the resolution point. The pre-commit is unambiguous: T15 coint-failure → mechanical halt at 60.0%; T15 normal → continue. The 4-coint-streak background makes the halt path the more-likely outcome, but the resolution is data-only, not deliberation.

**Drawdown 5 in a row, cumulative −$4.444, 1 win in 14.** The §5 negative-result reading continues to harden — sizing works (H1 holds across 14 trades), edge has cleared costs on 1 of 5 eligible (T7), and the universe's coint-fragility is now empirically OUTSIDE its historical band. The pre-commit gives the experiment a clean way to conclude or continue based on T15 alone.

*Audit covers: run_141_20260530_140525 (T14 AVAX/ETH coint_lost DECOUPLED β=0.4562 mid-range). β-sizing: 14/14 exact. E4: 8/14=57.1%, FIRST TIME OUTSIDE historical band [36.8, 55.6], deeper into upper review band but NOT halt. Mean-shift confirmed at mid-range β; broad-spectrum coverage now locked in. RECON: PASS (unexplained $0.025 small). H1 / Fork: unchanged (T14 not eligible). Cumulative −$4.444, win rate 1/14. Pre-commit for T15 is the active reading.*

---

# Run 142 (2026-05-30) — T15 SOL/LINK  ← **E4 HALT FIRES — pre-commit executes mechanically (9/15 = 60.0% AT halt line, 5 consecutive coint-failures T11–T15)**; T15 classified TRACKED-THEN-BROKE (not DECOUPLED), edge briefly cleared at mean (+$0.102) but below cost ($0.14)

**Headlines:** Coint-failure (cointegration_watch_timeout). **β=0.6499 — mid-range** (joins T14's 0.4562 in the middle of the [0.378, 1.841] distribution). 20.3-min hold (shorter than T13's 38, T14's 38). Entry z=+2.184, exit z=+0.599, Δz=−1.585. **Critically: T15 is TRACKED-THEN-BROKE, NOT DECOUPLED** — snapshots show z reverted all the way to z=0.09 at t=5 min with pnl=**+$0.102** (positive, edge briefly tracked the mean), then z bounced back to 2.03 (t=11) and pnl went negative, then drifted to exit at z=0.60 with pnl=−$0.016. **Coint-failure rate now 9/15 = 60.0% — AT the E4 halt line.** **The pre-commit (template v1.4 §4) fires mechanically: HALT EXECUTES.** 6 losses in a row T10–T15 = −$2.780. Cumulative −$4.652.

## β-Sizing

```
BETA_SIZING: beta=0.6499 gross=200.00 capital_long=78.78 capital_short=121.22 side=positive_z
```
- leg2 (long LINK, signal_positive) = 200×0.6499/(1+0.6499) = 129.98/1.6499 = **$78.78** ✓
- leg1 (short SOL, signal_negative) = 200/1.6499 = **$121.22** ✓
- gross 200.00 ✓; no fallback. **β-sizing 15/15 mechanically exact, 0 fallbacks.**
- β=0.6499 = mid-range; with T14's 0.4562 also mid-range, the recent coint-failure cluster spans β ∈ {0.456, 0.476, 0.650, 1.841} across T11–T14–T15 (T12 0.655, T13 1.841, T14 0.456, T15 0.650).

## T15 — SOL/LINK Per-Trade Telemetry

| Field | T15 |
|---|---|
| Side / entry_z → exit_z | long_pos_short_neg (long LINK, short SOL) / +2.184 → +0.599 |
| Δz (abs) | 1.585 (precondition met for Class A) |
| **Snapshot z-traversal** | entry 2.18 → reverted to **0.09 (≈mean) at t=5min with pnl=+$0.102 POSITIVE** → re-expanded to z=2.03 at t=11min with pnl=−$0.091 → drifted to z=0.21 at t=17min with pnl=$0.000 → exit z=0.60 |
| Exit / hold | **cointegration_watch_timeout** / 20.3 min |
| MFE / z_at_MFE (CSV) | +$0.010 / z=2.20 (CSV tick-level peak from sub-snapshot data; snapshot-stream peak was +$0.102 at z=0.09, well above CSV — see anomaly note below) |
| MAE / z_at_MAE (CSV) | −$0.214 / z=−0.10 (past mean during a reversion overshoot before snapshot t=11's bounce; the deepest pnl loss occurred at the mean-overshoot trough) |
| **In-zone PnL (snapshots)** | **At z=0.09 (t=5): pnl=+$0.102 POSITIVE** — peak in-zone snapshot; below cost-clearance threshold (~$0.14) but positive |
| gross position_pnl | −$0.110 |
| real_costs | $0.098 (fees $0.10 + slippage $0.04 − unexplained +$0.042; unexplained_pct=43.0%, highest in window but under 50% warn threshold) |
| Net PnL | **−$0.208** |
| Snapshot count | 20 (full 1-min cadence; trade exit at t=20) |
| Regime | RANGE throughout (not RISK_OFF) |
| entry_coint_stability slope | −4.9e−7 (essentially flat; evaluated 1 time, passed) |

**The shape (different from prior coint-failures):** T15's spread DID briefly converge to the mean (z=0.09 at t=5) with a small positive pnl (+$0.102). Then z bounced back up toward entry (z=2.03 at t=11), pnl went negative (−$0.091), and the coint-watch-timeout fired as the relationship failed to stably re-converge. This is **NOT the mean-shift pattern** from T13/T14 — the rolling mean didn't drift away; the spread oscillated. The cointegration_watch_timeout (rather than cointegration_lost) reflects this: relationship is weak/oscillating, not broken.

## Classification A — TRACKED-THEN-BROKE (NOT DECOUPLED; first TRACKED-THEN-BROKE since T12)

Apply |Δz|≥0.5 precondition: 1.585 ≥ 0.5 ✓. z reverted favorably (touched z=0.09 at the mean). **pnl_at_mean > 0:** snapshot at t=5 (z=0.09) shows pnl=**+$0.102** (positive). **A:TRACKED-THEN-BROKE.** 

Important wrinkle: **edge at mean was POSITIVE but BELOW COST** ($0.102 < $0.14 textbook). So T15 demonstrates the in-zone edge of this pair on this entry, but the edge was insufficient to clear costs at the moment z touched the mean. Then the position couldn't hold and broke before any exit signal could fire (full_tp guard floor is $0.12 effective — $0.018 above the $0.102 in-zone peak; profit-lock floor is $0.170 — $0.068 above). The position was **structurally trapped between in-zone peak ($0.102) and exit-floor ($0.12)** — a familiar pattern from T7/T9 of the prior experiment, now appearing in this one as well.

**Clean β-sized Class A tally now: 6/9 DECOUPLED, 3/9 TRACKED-THEN-BROKE** (DECOUPLED: T3b, T4b, T9, T11, T13, T14; TRACKED-THEN-BROKE: T1b thin-pair, T12 borderline, T15 below-cost-floor). **Mean-shift remains the dominant coint-failure mode (6/9 = 67%)** but T15 adds a new sub-pattern to TRACKED-THEN-BROKE: edge-tracked-mean-but-below-cost-then-broke. T15 also connects to the §5 / Item 14 negative-result reading — even when β-sizing was correct AND the spread tracked the mean, the in-zone peak was insufficient to clear costs.

## CSV MFE / snapshot anomaly note

CSV reports MFE=+$0.010 at z=2.20 (near entry); snapshot at t=5 shows unrealized_pnl=+$0.102 at z=0.09. CSV is 10× smaller than snapshot peak. Direction is inverted from typical (usually CSV tick-level MFE is *higher* than 1-min snapshot peak). Possible causes: (a) CSV `max_favorable_pnl_usdt` may track a different quantity than snapshot `unrealized_pnl_usdt` (e.g., position_pnl excluding funding/upl difference); (b) accounting layer where MFE is taken from price-level only. The 1-min snapshot stream is authoritative for in-zone classification per prior audit convention; T15 classification rests on snapshot evidence (pnl_at_mean=+$0.102 from t=5 snapshot). Flag for follow-up if this anomaly is structural; not blocking the audit.

## Reconciliation

- position_pnl (gross): −$0.110 | equity_change: −$0.208 | diff (real_costs): −$0.098 | fees $0.10 + slippage $0.04 + unexplained +$0.042 = 1.43× textbook 0.96× model. basis pre_close_equity_delta ✓ | pass_fail: **PASS.** unexplained_pct=43.0% (highest single-trade % in the window, but under 50% warn threshold; absolute small $0.042). No large_unexplained_warning fired.

## E4 HALT — MECHANICAL EXECUTION (per template v1.4 §4 pre-commit)

**Coint-failure rate: 9/15 = 60.0%. AT THE HALT LINE.** Per the pre-commit verbatim:

> "If T14 AND T15 are BOTH coint-failures → 9/15 = 60.0%, AT the halt line… Halt executes mechanically without re-deliberation. No 'but wait, the rate is exactly at the line not above' judgment — the trajectory + level + run-depth together is the signal the calibration was designed to catch."

**Pre-commit conditions met:**
- T14 was coint-failure (cointegration_lost) ✓
- T15 is coint-failure (cointegration_watch_timeout) ✓
- 9/15 = 60.0% — AT halt line ✓
- 5-deep coint-failure run T11–T15 (probability ~3% at 50% base rate) ✓
- Trajectory: 37.5 → 44.4 → 50 → 53.8 → 57.1 → **60.0** ✓ (monotonically rising over 6 closed trades)

**MECHANICAL ACTION (no deliberation):** halt the sizing test. **The experiment-level kill-criterion E4 has fired as designed.** Per the E4 row in §4: address universe quality / exit-speed first; coint-failure has no tunable entry-knob (slope refuted, level refuted, mean-shift β-independent).

**The halt does NOT mean the experiment is closed** — it means the *sizing test* is paused pending the structural review. H1 (sizing alignment) was a clear success (5/5 eligible positive, no sign flips, β-sizing 15/15 exact). H2 (cost-clearance) and the universe-fragility question are what the halt addresses, not the sizing question.

## E4 trajectory — full trace

```
   T6 (E4 evaluable): 5/6 = 83.3%
   T7-T13 window:    sliding range 37.5 → 53.8
   T6-T9:  3/4 → 4/6 → 4/7 → 4/8 (= 50%)
   T7-T11: 4/9 → 5/10 → 5/11 (= 45.5%)
   T8-T12: 6/11 → 7/12 (= 58.3%)
   T9-T13: 7/13 = 53.8%
   T10-T14: 8/14 = 57.1%  ← first time outside historical band [36.8, 55.6]
   T11-T15: 9/15 = 60.0%  ← AT HALT LINE, mechanical halt fires
```

5 consecutive coint-failures: **T11 (DECOUPLED) → T12 (TRACKED-THEN-BROKE) → T13 (DECOUPLED) → T14 (DECOUPLED) → T15 (TRACKED-THEN-BROKE).**

## Halt-interpretation pre-load (v1.5 §4) — now ACTIVE; standing read leans Reading 2 (structural)

Per the pre-load committed in v1.5 §4, the question to bring to the structural review is: **TEMPORAL fragility (regime change since T9, eligible-return rate post-halt would recover toward ≈63%) vs STRUCTURAL fragility (universe was always this coint-fragile; T2–T8 cluster was the lucky window, eligible-return rate post-halt would stay ≤ 1 in 6+ trades).**

**Standing read at T15 (directional prior, not verdict — to be tested by post-halt evidence):**
- Eligibles all clustered T2–T8 (5 in 8 trades = 63%)
- T9–T15: **0 eligibles in 7 trades** (0%)
- T15 itself extends the non-eligible stretch and adds to the coint-failure count — does NOT discriminate between Reading 1 and Reading 2 on its own (a coint-failure is consistent with both)
- The standing prior continues to lean Reading 2 (the eligible stall is too clean to be transient variance; if Reading 1 were correct you'd expect at least one eligible to break through during T9–T15)
- T15 is also informative in a softer way: the position DID briefly track the mean with positive pnl (+$0.102), suggesting the universe's relationships aren't *gone*, just *too weak to clear costs at $200 notional*. This nudges toward a particular flavor of Reading 2: "universe + notional + cost-stack combination is structurally insufficient," NOT "universe is broken entirely." That sub-distinction connects directly to the §5 negative-result framing.

**Discriminator awaits post-halt evidence** — the read is not yet verdict.

## Cumulative Counter Update (after T15)

```
trades: 15. $/σ eligible: 5 unchanged (T15 is coint-failure, not eligible)
sign-flip: 0/5 = 0%; aggregate $/σ +$0.044/σ; H1 still rock-solid (no new eligible data; H1 is a CLEAN SUCCESS on this experiment)
pnl_at_mean > cost: 2/5 unchanged (T7, T8)
coint-failure: 9/15 = 60.0% (T1, T3, T4, T9, T11, T12, T13, T14, T15) — **AT E4 HALT LINE; HALT FIRED**
  trajectory: 75→60→50→37.5→44.4→50→53.8→57.1→**60.0** (last 5 trades all coint-failures)
clean Class A: 6 DECOUPLED + 3 TRACKED-THEN-BROKE (T15 newest TRACKED-THEN-BROKE; mean-shift = 6/9 = 67% of clean coint-failures)
β range: [0.378, 1.841] (unchanged); 15/15 exact; 0 fallbacks
recon FAIL count: 1 (T12 only; T13/T14/T15 PASS — T15 unexplained_pct 43% high but absolute small)
adverse-normal bucket: 1 (T10 only)
cumulative PnL: −$4.652 (T15 −$0.208; 6 LOSSES IN A ROW T10−T15 = −$2.780)
win rate: 1/15 = 6.7%
trades_remaining_to_20: 5 — but EXPERIMENT-LEVEL HALT supersedes; sizing collection paused pending structural review
```

## Strategic Read — HALT CONDITIONS MET, STRUCTURAL REVIEW SCOPE LOADED

**Pre-committed halt fired mechanically.** No deliberation, no judgment call, no "but the rate is exactly at the line." The pre-commit was written cold at T13 / template v1.4 with the explicit purpose of removing the in-the-moment temptation; the temptation didn't get a chance to operate because the rule was clearer than the moment. The discipline worked.

**What the structural review must hold (from v1.5 §4 + the prior commitments):**

1. **H1 (sizing) is a CLEAN SUCCESS.** 5/5 eligible positive, 0 sign flips, aggregate +$0.044/σ, β-sizing 15/15 mechanically exact across the full observed β range. The sizing question is *answered*, not paused. This must be carried into the review as a settled finding, not re-litigated.

2. **The halt is about UNIVERSE FRAGILITY, not sizing.** H1's success is preserved; what halt addresses is whether the universe holds β-fit relationships through a 60-min hold often enough to *test* anything further (E2/E3 cannot fire on a population that doesn't accumulate). The eligible stall (5 in T2–T8, 0 in T9–T15) is the headline evidence the review must read.

3. **Mean-shift remains the dominant loss mechanism** (6/9 clean coint-failures DECOUPLED across the full β range), but T15 adds a softer wrinkle (TRACKED-THEN-BROKE below cost): some pairs DO track the mean briefly but the edge at mean is insufficient to clear costs at $200 notional. This connects coint-failure to the §5 negative-result branch — they're related, not separate questions.

4. **Reading 1 vs Reading 2 (per v1.5 §4 halt-interpretation pre-load):** standing prior leans Reading 2 (structural fragility). Discriminator is eligible-return rate AFTER the halt (decided in advance, not to be re-narrated). If post-halt evidence produces eligibles at ≈ T2–T8 rate, Reading 1 is supported; if eligibles remain ≤ 1 in 6+ trades, Reading 2 confirms.

5. **The negative-result bar (§5) is now load-bearing.** With H1 clean and H2 / fork unresolved, the structural review's pre-committed conclusion if cost diagnostic shows structural cost gap → *"the strategy does not have a capturable edge at the current notional and universe."* That conclusion is a finding, not a setback. The temptation to reframe ("the regime was bad," "needs one more patch") is what §5 was written to refuse, and it must be refused.

6. **The circuit-breaker inertness (v1.5 §10)** is now visible against a concrete number: 6 losses in a row at −$2.780, breaker silent throughout. Not a fix request mid-experiment, but the scale-up conversation needs to acknowledge this when (if) it happens.

**Honest read:** the experiment delivered exactly what it was designed to deliver — a sizing test that came back clean, an experiment-level kill-criterion that fired before the test could continue past the point of value, and a halt-interpretation pre-load that frames the post-halt question correctly. The cumulative −$4.652 / 1-win-in-15 record is consistent with the §5 negative-result reading; the alternative (Reading 1, temporal fragility) is on the table but currently the less-supported prior. The structural review will resolve which reading the post-halt evidence supports, and the question it must answer was written cold before T15 fired.

*Audit covers: run_142_20260530_224156 (T15 SOL/LINK coint_watch_timeout TRACKED-THEN-BROKE β=0.6499 mid-range). β-sizing: 15/15 exact. **E4 HALT FIRED MECHANICALLY at 9/15 = 60.0%** per template v1.4 §4 pre-commit; 5 consecutive coint-failures T11–T15. T15 in-zone edge **positive but below cost** ($0.102 < $0.14) — connects coint-failure to §5 negative-result branch. Mean-shift 6/9 = 67% of clean coint-failures (still dominant). RECON: PASS (unexplained $0.042, 43% pct under threshold). H1 / Fork: unchanged (T15 not eligible); H1 = CLEAN SUCCESS. Cumulative −$4.652, win rate 1/15. **Halt-interpretation pre-load (v1.5 §4) now active; standing prior leans Reading 2 (structural fragility); discriminator awaits post-halt eligible-return rate.** Experiment-level halt — sizing collection paused; structural review is now the next action.*
