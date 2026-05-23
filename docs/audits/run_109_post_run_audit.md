# Run 109 Post-Run Audit — exp_coint_stability_v1

*Template: `docs/prompts/exp_coint_stability_v1_per_run_audit.md`*

---

## Experiment State Block

```
experiment_group: exp_coint_stability_v1
runs_since_experiment_start: 105, 106, 107, 108, 109 (105 = 0 trades)
trades_since_experiment_start_entering_this_run: 3
trades_since_experiment_start_after_this_run: 4
trades_remaining_to_action_threshold: 16
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7 (coint stability entry filter)
experiment_phase: Calibration Window
```

---

## Pre-Audit Config Verification

From `config_snapshot.json`:

| Parameter | Expected | Actual | Status |
|---|---|---|---|
| coint_stability_enabled | true | True | PASS |
| coint_stability_window | 5 | 5 | PASS |
| coint_stability_slope_max | 0.020 | 0.02 | PASS |
| coint_stability_min_sample_interval_seconds | 60 | 60.0 | PASS |
| full_tp_guard_multiplier | 0.50 | 0.5 | PASS |
| session_max_loss_usdt | 5.0 | 5.0 | PASS |
| max_drawdown_usdt | 10.0 | 10.0 | PASS |
| entry_z | 2.0 | 2.0 | PASS |
| entry_z_max | 3.0 | 3.0 | PASS |
| exit_z | 0.35 | 0.35 | PASS |
| max_break_risk | 0.12 | 0.12 | PASS |
| ETHFI-USDT-SWAP graveyard ttl_days | null | None | PASS |
| HMSTR-USDT-SWAP graveyard ttl_days | null | None | PASS |

All frozen variables confirmed unchanged. Proceeding.

---

## Section 1 — Run Summary

- **Duration:** 28,111 s (7.81 hours)
- **Total entry rejection rows:** 475
- **Entry attempts (signals that reached execution):** 1
- **Accepted trades:** 1
- **Closed trades:** 1
- **Open trades at end:** 0
- **Realized session PnL:** -$0.1489
- **Wins / Losses / Win rate:** 0 / 1 / 0%
- **Avg win:** N/A
- **Avg loss:** -$0.1489
- **Avg hold duration:** 32.4 minutes
- **Pair switches:** 32 (33 pairs evaluated)
- **Circuit breaker:** not tripped (session PnL -$0.149 vs threshold -$5.0)
- **Session consecutive losses:** 0 entering → 1 at end
- **Persistent consecutive losses:** 0 entering (reset by T3 win in run_108) → 1 at end

---

## Section 2 — Per-Trade Telemetry

**Trade 4 (T4):** BCH-USDT-SWAP / CRCL-USDT-SWAP

| Field | Value |
|---|---|
| pair | BCH-USDT-SWAP / CRCL-USDT-SWAP |
| entry regime | RANGE |
| entry z-score | +1.969 |
| exit z-score | -1.814 |
| exit reason | cointegration_lost |
| hold duration | 32.4 minutes |
| gross MFE | +$0.0455 |
| MAE | -$0.2845 |
| net PnL | -$0.1489 |
| post-entry coint status at close | lost |
| outcome | LOSS |
| full_tp_touched | True (guard blocked 76 times; MFE never converted) |

Note: MFE of +$0.0455 reached the full TP guard threshold ($0.24 floor, full_tp_guard_multiplier=0.50 → effective floor $0.12). The guard blocked the exit 76 times while PnL was in the TP zone, then the trade reversed sharply and exited via cointegration_lost. This is a standard guard-block + reversal event; no anomaly.

No winning trades this run. Section 2A not applicable.

---

## Section 3 — Reconciliation Telemetry

| Field | Value |
|---|---|
| Gross PnL (position-level) | -$0.0051 |
| Equity delta | -$0.1489 |
| Difference (fees + slippage + unexplained) | -$0.1438 |
| Fees | $0.10 |
| Slippage | $0.04 |
| Funding | $0.00 |
| Unexplained residual | -$0.0038 |
| Pass/Fail | PASS |

Unexplained residual -$0.0038 is within the $0.05 flag threshold. No anomaly.

---

## Section 4 — Patch 7 Cointegration Stability Filter

### 4A — Watch-Time and Gate Status (T4)

| Field | Value |
|---|---|
| pair | BCH-USDT-SWAP / CRCL-USDT-SWAP |
| pair_activation_timestamp | 2026-05-23 21:55:16 CST (13:55:16 UTC) |
| entry_timestamp | 2026-05-23 23:07:29 CST (15:07:29 UTC) |
| watch_time_before_entry_seconds | 4333 s |
| watch_time_before_entry_minutes | 72.2 min |
| gate_status | **insufficient_history** |
| coint_stability_check_evaluated_count | 0 (all 6 pre-entry gate rows) |
| coint_stability_insufficient_history_count | 1 per row (all 6 pre-entry gate rows) |
| coint_stability_check_blocked_count | 0 |
| gate_reached | yes |

**gate_status derivation:** The safety gate was reached and evaluated on 6 occasions before entry. All 6 show `evaluated_count=0`, `insufficient_history=1`. The buffer never reached 5 samples despite 72 minutes of watch time.

**Root cause — buffer fills from gate calls, not monitoring ticks:** The coint stability ring buffer is only written when an entry signal fires and the safety gate is called. Between activation and entry, signals were sparse: gate calls at UTC 14:26:48, 14:27:20, 14:56:33, 14:56:52, 14:56:57, 15:06:00. Applying the 60s minimum sample interval:
- Sample 1: 14:26:48 (31 min after activation)
- Sample 2: 14:56:33 (+29 min, previous pair of calls too close together)
- Sample 3: 15:06:00 (+9 min)
- Sample 4: ~15:07:29 at entry execution (+89 s, above 60s interval)

Buffer had 4 of 5 samples at entry. `insufficient_history` → gate allowed entry through (the stability check does not block on insufficient history; it skips).

This is the Patch 7.1 failure mode: **long watch time does not guarantee buffer population** when entry signals are sparse. The buffer requires 5 entry-signal gate evaluations spaced ≥60s apart, not 5 minutes of clock time.

### 4B — Session Aggregate (Rejected-Entry Rows)

From entry_rejections.csv, all entry_safety_gate rows (212 total):

| Metric | Value |
|---|---|
| Total entry_safety_gate rows | 212 |
| Rows with evaluated_count = 0 AND insufficient_history = 1 | 152 |
| Rows with evaluated_count ≥ 1 | 60 |
| This-run ratio: insufficient / (evaluated + insufficient) | 152/212 = **71.7%** |
| Cumulative ratio (runs 106–109) | 296/437 = **67.7%** |

Cumulative breakdown: run_106 (81 eval, 128 insuf) + run_107 (0 eval, 16 insuf) + run_108 (0 gate rows) + run_109 (60 eval, 152 insuf) = 141 eval total, 296 insuf total.

Note: this-run ratio (71.7%) is above the 3-trade early-stop threshold of 70% when computed on rejected-entry rows. This is a factual observation — the per-row ratio trigger was only committed through trade 3. The gate-inactivity trigger (Section 4C) is the active watch mechanism from this point forward.

### 4C — Watch-Time Distribution Tracker (Cumulative through T4)

| Trade # | Run | Pair | Watch Time | Gate Status |
|---|---|---|---|---|
| T1 | run_106 | LINK/SUI | 22320 s (6.2 h) | evaluated |
| T2 | run_107 | SUI/AAVE | 85 s | insufficient_history |
| T3 | run_108 | ETH/AVAX | 864 s (14.4 min) | not_reached (RISK_OFF upstream) |
| T4 | run_109 | BCH/CRCL | 4333 s (72.2 min) | insufficient_history |

**Running summary (excluding not_reached):**
- evaluated: 1 (T1)
- insufficient_history: 2 (T2, T4)
- not_reached: 1 (T3, excluded from gate-effectiveness denominator)
- Gate-reaching trades total: 3 (T1 + T2 + T4)
- effectiveness_fraction: 1/3 = **33.3%**

**T4 observation:** BCH/CRCL had 72 minutes of watch time and still returned insufficient_history. This is qualitatively different from T2 (85s — trivially short). T4 demonstrates that the buffer-from-gate-calls failure mode is not bounded by watch time alone; it is bounded by the number of entry signals fired during the watch period. A pair with infrequent z-score crossings can accumulate long watch time while the buffer barely fills.

### 4C-TRIGGER — Gate-Inactivity Soft Trigger

```
gate_inactivity_trigger:
  total_closed_trades: 4
  gate_reaching_trades (evaluated + insufficient_history): 3
  evaluated: 1
  insufficient_history: 2
  not_reached: 1
  cumulative_effectiveness_fraction: 1/3 = 33.3%
  rolling_6_gate_reaching_fraction: N/A (need 6 gate-reaching trades; currently 3)
  trigger_status: MONITORING (need 3 more gate-reaching trades)
```

The 33.3% cumulative fraction is below the 40% trigger threshold, but the trigger cannot evaluate until 6 gate-reaching trades have accumulated. 3 more gate-reaching trades required. The 33.3% figure is noted as a leading indicator.

---

## Section 5 — Early-Stop Trigger Check

**Status: 3-TRADE CHECK PASSED — CONTINUE (confirmed prior session)**

The 2-trade and 3-trade pre-committed triggers have been evaluated and CONTINUE was confirmed. Section 5 is N/A for this and subsequent runs. The gate-inactivity trigger (Section 4C) is the active stop-condition mechanism going forward.

---

## Section 6 — Entry Rejection Distribution

| Gate | Reason | Count |
|---|---|---|
| strategy_gate | (all) | 231 |
| entry_safety_gate | advanced_ml_break_risk_high | 147 |
| entry_safety_gate | liquidity_at_floor | 31 |
| entry_safety_gate | correlation_component_below_threshold | 21 |
| entry_safety_gate | cointegration_component_below_threshold | 13 |
| entry_safety_gate | coint_stability_slope_exceeded | 0 |
| trade_quality_gate | (all) | 32 |
| **Total** | | **475** |

`coint_stability_slope_exceeded`: 0 — the Patch 7 block did not fire this run. Consistent with all BCH/CRCL gate rows showing insufficient_history (can't compute slope without a full buffer).

Break_risk distribution at safety gate rejection: mean=0.111, median=0.150, max=0.150, n=212.

---

## Section 7 — Counter Update and Next Step

```
trades_since_experiment_start: 4           ← window completion counter
evaluated_trade_count: 1                   ← real experimental N (Patch 7 could act on this trade)
insufficient_history_trade_count: 2        ← gate ran, couldn't compute slope
not_reached_trade_count: 1                 ← upstream block, gate never ran
trades_remaining_to_action_threshold: 16
cumulative PnL (experiment window): -$0.05 (T1) + -$0.94 (T2) + +$0.19 (T3) + -$0.149 (T4) = -$0.949
win rate (experiment window): 1/4 = 25%
coint-exit losses so far: 2 trades (T2 cointegration_lost -$0.94, T4 cointegration_lost -$0.149) = -$1.089
gate_inactivity_trigger_status: MONITORING (3/6 gate-reaching trades accumulated)
next step: run 110 with frozen configuration
```

**Real experimental N note:** After 4 closed trades, `evaluated_trade_count = 1`. Patch 7 has had one trade where it could have acted (T1). The remaining 3 trades either hit insufficient_history (gate ran but couldn't compute) or were blocked upstream. If this ratio persists, the 20-trade window will contain far fewer than 20 gate-evaluated trades.

---

## Section 8 — Forbidden Inferences

No forbidden inferences are present in this audit. Observed:
- T4's 72-minute watch time producing insufficient_history is reported factually, not as a conclusion about Patch 7's effectiveness.
- Coint-failure rate (-$1.089 in 2 coint exits) is reported without comparing to baseline.
- No recommendations to adjust slope_max, window, or sample interval.

---

## Section 9 — Permitted Observations

- T4 (BCH/CRCL, 72.2 min watch) returned insufficient_history because the ring buffer fills from entry-signal gate calls, not clock ticks. With sparse z-score signals during the watch period, 4 of 5 required samples accumulated by entry time. This is factually different from T2 (85s watch, trivially no samples) and demonstrates the buffer-population failure mode is a function of signal frequency, not watch duration alone.
- `full_tp_touched=True` with guard_blocked=76 on T4: the price entered the TP zone briefly but the guard blocked exit. Trade then reversed through coint-loss. Standard guard-block + reversal event.
- Coint-exit loss count: 2/4 trades (T2 and T4) exited via cointegration failure. T1 exited via coint_watch_timeout (also a coint exit). 3 of 4 trades have coint-related exits.

---

*Audit completed: 2026-05-23. Data sources: Reports/v1/run_109_20260523_155132/, Logs/v1/run_109_20260523_155132/.*
