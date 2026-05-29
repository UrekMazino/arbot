# Per-Run Audit — exp_beta_aware_sizing_v1
## Runs 125–131 (T1–T5) — 2026-05-28 → 2026-05-29

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

**Read-only / diagnostics-only.** Per `analysis_spec_pnl_vs_z_decoupling_v1`. Reads dollar (unrealized, mark-to-market) PnL as a function of z across each trade's per-cycle snapshot series (`position_snapshots.csv`). One primitive answers two questions: the **H2 bifurcation** (working trades) and the **mean-shift/decoupling** test (coint-failures). Zero new data. Live collection (run 132+) untouched.

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
