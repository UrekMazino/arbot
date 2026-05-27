# Run 116 Post-Run Audit — exp_coint_stability_v1

**Audit template:** exp_coint_stability_v1_per_run_audit.md v1.2
**Run key:** run_116_20260526_160116
**Audit date:** 2026-05-26

---

## Experiment State Block

```
experiment_group: exp_coint_stability_v1
runs_since_experiment_start: 105, 106, 107, 108, 109, 111, 112 (no-trade), 113, 114 (no-trade), 115, 116
trades_since_experiment_start_entering_this_run: 3 (T5, T6, T7)
trades_since_experiment_start_after_this_run: 4 (T8)
trades_remaining_to_action_threshold: 16
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7 (coint stability entry filter), Patch 7.1 (monitoring-loop buffer population), Patch 7.2 (entry-slope persistence for accepted trades)
experiment_phase: Calibration Window
```

---

## Data Sources

```
Reports/v1/run_116_20260526_160116/
  summary.json
  config_snapshot.json
  trade_closes.csv
  reconciliation_checks.csv
  entry_rejections.csv
bot logs (STRATEGY_TRADE_OPEN / STRATEGY_TRADE_CLOSE — run_116_20260526_160116)
```

**Note:** `entry_coint_stability_slope` now present in trade_closes.csv — Patch 7.2 CSV fix deployed before this run. Slope read directly from structured field; no log-parsing fallback needed for T8.

---

## Pre-Audit Config Verification

| Check | Value | Status |
|---|---|---|
| `STATBOT_ENTRY_COINT_STABILITY_ENABLED` | true | PASS |
| `STATBOT_ENTRY_COINT_STABILITY_WINDOW` | 5 | PASS |
| `STATBOT_ENTRY_COINT_STABILITY_SLOPE_MAX` | 0.020 | PASS |
| `STATBOT_ENTRY_COINT_STABILITY_MIN_SAMPLE_INTERVAL_SECONDS` | 60.0 | PASS |
| `STATBOT_FULL_TP_GUARD_MULTIPLIER` | 0.50 | PASS |
| `max_break_risk` | 0.12 | PASS |
| `tradeable_capital_usdt` | 200.0 | PASS |
| ETHFI/HMSTR/FLOKI permanently graveyarded (ttl_days: null) | confirmed | PASS |

All frozen variables confirmed unchanged.

---

## Section 1 — Run Summary

| Field | Value |
|---|---|
| Duration | 18,457s (5.13 h) |
| Start / End | 2026-05-26T08:01:16 UTC / 2026-05-26T13:08:53 UTC |
| entry_safety_gate evaluations | 44 |
| Total accepted trades | 1 |
| Total rejected entries | 118 |
| Closed trades | 1 |
| Open trades at run end | 0 |
| Session PnL | −$0.065 |
| Starting equity / Ending equity | $2,656.92 / $2,656.86 |
| Win / Loss / Win rate | 0 / 1 / 0% |
| Avg win / Avg loss | N/A / −$0.065 |
| Avg hold | 88.3 min (calculated; hold_minutes null in CSV — see Section 3) |
| Pair switches | 5 (6 pairs total: BTC/HBAR → AVAX/ETH → HBAR/SOL → PEPE/HBAR → ADA/SOL → SOL/AVAX) |
| Circuit breaker | Not tripped (consecutive losses: 1/3; session loss −$0.065 < $5.00 limit) |

**Run context:** Run began immediately after run_115 (no restart gap). BTC/HBAR carryover from run_115 was force-switched at 08:02:56 UTC (pair no longer in universe). AVAX/ETH was hospitalized via cointegration_watch_timeout. HBAR/SOL was hospitalized via cointegration_lost_unproven. PEPE/HBAR was active during RISK_OFF. ADA/SOL (5th pair, shown in rejections as ADA-USDT-SWAP/SOL-USDT-SWAP) was hospitalized at 11:34:13 UTC for cointegration_lost_weak_history. SOL/AVAX (6th pair) was selected as hospital replacement at 11:34:13 UTC; T8 traded there.

**SOL/AVAX pair universe status:** Selected as hospital replacement at 11:34:13 UTC. By 12:20:30 UTC (~46 min into T8 position), flagged as "no longer Pair Doctor eligible — not in the supplied Pair Universe." Switch deferred because open position was present (SOL 1.17, AVAX 10.70). Bot held the position until MR exit at 13:06:59 UTC. Close executed via EMERGENCY_FLATTEN path.

**Strategy cooldown at startup:** STATARB_MR low_win_rate cooldown active for ~20 min after run start (carry-over from run_115 loss). Explains re-entry cooldown rejections on BTC/HBAR at the start.

**Reconciliation warning:** 1 `reconciliation_warning` event and 1 `data_quality_warning` event fired this session. See Section 3.

---

## Section 2 — Per-Trade Telemetry

### T8 — SOL-USDT-SWAP / AVAX-USDT-SWAP

| Field | Value |
|---|---|
| Side | long SOL / short AVAX (long_negative_short_positive) |
| Entry regime | RANGE |
| Entry strategy | STATARB_MR |
| Entry z-score | −2.1203 |
| Exit z-score | −0.2155 |
| Exit reason | normal |
| Hold duration | 88.3 min (calculated: 11:38:40 → 13:06:59 UTC; hold_minutes null in CSV — data quality) |
| Gross MFE | unavailable (max_favorable_pnl_usdt absent from report) |
| MAE | unavailable (max_adverse_pnl_usdt absent from report) |
| Net PnL | −$0.065 (equity-based; position PnL = +$0.129 — see Section 3) |
| Post-entry cointegration | intact (exit_reason=normal; z reverted from −2.12 past exit threshold −0.35 to −0.2155) |
| full_tp_touched | False |
| guard_blocked_full_tp_count | 0 |
| partial_exit_before_full_tp | False |
| Outcome | Loss |

**Exit narrative:** z entered at −2.12 and reverted past the exit threshold (−0.35) to −0.2155 at close. Standard mean-reversion exit. Position PnL was positive (+$0.129) but costs exceeded spread capture, producing a net equity loss of −$0.065. No full-TP involvement.

---

## Section 3 — Reconciliation Telemetry

### T8 — SOL-USDT-SWAP / AVAX-USDT-SWAP

| Field | Value |
|---|---|
| Trade PnL (position) | +$0.129 |
| Equity delta | −$0.065 |
| Difference | −$0.194 |
| Fees | $0.00 |
| Slippage (estimated) | $0.00 |
| Funding | $0.00 |
| Unexplained | −$0.194 |
| Basis | position_pnl |
| large_delta_warning | True |
| large_unexplained_warning | True |
| Result | **FAIL** — unexplained −$0.194 >> $0.05 threshold |

**Reconciliation FAIL — root cause and position verification:**

**Position confirmed flat.** Log evidence: `EMERGENCY_FLATTEN_FLAT: tickers=AVAX-USDT-SWAP/SOL-USDT-SWAP retry_count=3 requested_qty=11.87000000 filled_qty=10.70000000 remaining_qty=0.00000000 final_position_qty=0.00000000 open_orders=0`. Both legs closed: AVAX 10.7 sold, SOL 1.17 sold. OKX exchange should be confirmed visually as an additional check, but log confirms flat.

**Root cause — retry_count=3 on close verification, post-close fee snapshot timing gap:** The MR exit fired (z=−0.2155 past threshold). The close path is the same for all trades: `close_account_positions_and_confirm()` → `close_all_positions_and_confirm()` — the `EMERGENCY_FLATTEN_FLAT` log fires on every trade close; it is not a special path. Fee capture (pre-close snapshot, close call, post-close snapshot, `actual_fee_delta = max(post − pre, 0.0)`) runs for all closes. T8 specifically had `retry_count=3`, meaning verification required 3 polling cycles. The post-close fee snapshot was taken after those retries, but OKX's fill API had not yet settled T8's fills by that time — `post_fee_total − pre_fee_total = 0`, so `actual_fee_delta = 0`. The `basis = position_pnl` fallback triggered because post-close equity was unavailable or untrusted when the retries completed.

- `fees = $0.00`, `slippage = $0.00`: post-close fee snapshot taken before OKX fill API settled T8's fills (timing gap introduced by retry_count=3)
- `basis = position_pnl` (not `pre_close_equity_delta`): reconciliation fallback — post-close equity unavailable or untrusted after retried close
- `hold_minutes = null`: STRATEGY_TRADE_CLOSE logged `hold_min=n/a` — expected when close is unverified
- `data_quality_warning: 1`: confirms the reconciliation detected the unreliable equity snapshot
- `retry_count=3` vs 0 for T7: T8 was on an out-of-universe pair at close time (flagged at 12:20 UTC, 46 min before close); extra verification cycles may be related

**T8 PnL is unreliable for economic analysis.** Position PnL (+$0.129) and equity delta (−$0.065) are recorded but the cost breakdown is missing (fees absorbed into unexplained −$0.194). T8's net PnL is flagged **unreliable** for the cumulative economic tally. It remains valid for gate/slope analysis (exit_category=normal, slope=+3.99e-04 are unaffected by the reconciliation issue).

**This is not a meme-token pattern.** SOL and AVAX are highly liquid. No escalation to Item 12.

**Open item:** First reconciliation FAIL in the experiment window. All closes use the same path; the unique factor is `retry_count=3`. Hypothesis: pair was out-of-universe at close time, causing extra verification cycles that pushed the post-close fee snapshot past OKX's fill-API settlement window. Flag for structural review: "Investigate why T8 required retry_count=3 and whether retry_count > 0 reliably correlates with missed fees in post-close snapshot. Fix candidate: delay post-close fee snapshot by one OKX fill-history settlement window (~2–5s) after flat confirmation." T8 excluded from economic PnL analysis; included in gate/slope analysis.

**Meme-token sub-pattern tracker:** No new occurrence. Cumulative: HMSTR (run_102, −$0.226) + FLOKI (run_111, −$0.093), both permanently graveyarded.

---

## Section 4 — Patch 7 Cointegration Stability Filter — Per-Trade Gate Status

### 4A — Watch-Time and Gate Status (T8)

| Field | Value |
|---|---|
| pair | SOL-USDT-SWAP / AVAX-USDT-SWAP |
| pair_activation_timestamp | 2026-05-26T11:34:13 UTC (from log: `Switching from SOL-USDT-SWAP/ADA-USDT-SWAP to SOL-USDT-SWAP/AVAX-USDT-SWAP`) |
| entry_timestamp | 2026-05-26T11:38:40 UTC |
| watch_time_before_entry_seconds | **267s** (11:34:13 → 11:38:40) |
| watch_time_before_entry_minutes | **4.45 min** |
| gate_status | **evaluated** |
| coint_stability_check_evaluated_count | 1 (from trade_closes.csv — **Patch 7.2 CSV field, confirmed present**) |
| coint_stability_insufficient_history_count | 1 (one row at 11:35:52 UTC — 99s into watch; buffer not yet at 5 samples) |
| coint_stability_check_blocked_count | 0 |
| gate_reached | yes |
| slope at entry | **+3.99e-04 = +0.000399** (from trade_closes.csv `entry_coint_stability_slope` — Patch 7.2 CSV read, first confirmed CSV delivery) |
| slope_max threshold | 0.020 |
| delta_from_threshold | **+0.01960** (far below threshold) |
| exit_category | **normal** |

**Patch 7.2 CSV verification (FIRST CSV READ — T8):**

| Check | Result |
|---|---|
| Slope from trade_closes.csv | +0.000399 |
| Slope from STRATEGY_TRADE_OPEN log at 11:38:40 UTC | `coint_stability_slope=0.000399` |
| Values consistent? | **YES** |
| Verdict | **CSV DELIVERY CONFIRMED — Patch 7.2 CSV fix working** |

The slope field now appears in trade_closes.csv as intended. This is the first trade where the structured CSV field was read (T7's staleness verification used the log; T8 is the first full CSV delivery). No log-parsing fallback was needed. The Patch 7.2 CSV gap is closed.

**Watch-time and buffer trace:** Pair activated at 11:34:13 UTC. Monitoring loop adds one sample per 60s minimum interval. Buffer at each checkpoint:
- ~11:34:13: sample 1 added (activation)
- ~11:35:13: sample 2 (monitoring loop, post-warmup)
- 11:35:52 gate check (99s after activation): last sample ~99s-60s = 39s ago < 60s → no sample added; buffer has 2 samples < 5 → **insufficient_history** ✓
- ~11:36:13: sample 3 (monitoring loop)
- ~11:37:13: sample 4 (monitoring loop)
- 11:38:40 gate check at entry (267s after activation): last sample was at ~11:37:13, 87s ago ≥ 60s → gate adds sample 5; buffer = 5 samples ≥ window=5 → **evaluated** ✓

The gate code requires `len(_p_values) >= coint_stability_window` (verified: line 423 of entry_safety_gate.py). T8 evaluated with exactly 5 samples — the minimum. The slope (+3.99e-04) is computed on the full window=5. **T8's slope is valid.**

The earlier audit estimated 173s watch time using the first rejection row as a proxy for pair activation — this was incorrect. The exact pair switch timestamp (11:34:13 UTC) was in the log. Actual watch time is 267s = 4.45 min.

**Distance-from-threshold:** Delta +0.01960 — far below threshold. Exit was normal. Data point consistent with prior normal-exit slope region (T7: delta +0.0200, normal exit).

### 4B — Session Aggregate (entry_safety_gate rows)

| Metric | Value |
|---|---|
| Total entry_safety_gate rows | 44 |
| evaluated_count ≥ 1 | 42 |
| insufficient_history ≥ 1 | 2 (HBAR/SOL at 09:01:25 UTC; SOL/AVAX at 11:35:52 UTC) |
| blocked_count ≥ 1 | 0 |
| insuff / (eval + insuff) | 2/44 = **4.5%** |
| Gate fire rate (blocked / evaluated) | 0/42 = **0%** |

Session ratio 4.5% — very low, no post-restart inflation. Both insufficient_history occurrences are first-signal events on freshly-switched pairs (expected).

Cumulative trade-level insuff/(eval+insuff) across Patch 7.1 window (T5–T8): 0/4 = 0%.

### 4C — Watch-Time Distribution Tracker (Cumulative)

| Trade # | Run | Pair | Watch Time (s) | Gate Status |
|---|---|---|---|---|
| T1 | run_106 | LINK/SUI | 22320 (6.2h) | evaluated (pre-7.1, excluded) |
| T2 | run_107 | SUI/AAVE | 85 | insufficient_history (pre-7.1, excluded) |
| T3 | run_108 | ETH/AVAX | 864 (14.4min) | not_reached — RISK_OFF (pre-7.1, excluded) |
| T4 | run_109 | BCH/CRCL | 1944 (32.4min) | insufficient_history (pre-7.1, excluded) |
| T5 | run_111 | FIL/FLOKI | 878 (14.6min) | **evaluated** |
| T6 | run_113 | DOGE/SUI | 1035 (17.25min) | **evaluated** |
| T7 | run_115 | BTC/HBAR | 359 (5.98min) | **evaluated** |
| T8 | run_116 | SOL/AVAX | 267s (4.45min) | **evaluated** (exactly 5 samples at evaluation) |

Patch 7.1 window (T5 onward):
- evaluated: 4
- insufficient_history: 0
- not_reached: 0
- Effectiveness fraction: **4/4 = 100%**

T8 watch time (267s) is the shortest evaluated trade in the window. Buffer contained exactly 5 samples (window minimum) at entry. Slope computed on full window — valid.

### 4C-TRIGGER — Gate-Inactivity

```
gate_inactivity_trigger:
  total_closed_trades: 4
  gate_reaching_trades (evaluated + insufficient_history): 4
  evaluated: 4
  insufficient_history: 0
  not_reached: 0
  cumulative_effectiveness_fraction: 4/4 = 100%
  rolling_6_gate_reaching_fraction: N/A (need 6 gate-reaching trades, have 4)
  trigger_status: MONITORING (need 2 more gate-reaching trades)
```

### 4D — Running Slope-vs-Outcome Tally (Evaluated Trades Only)

Population: gate_status=evaluated AND blocked_count=0 AND trade closed.

| Trade # | Run | Pair | Slope at Entry | Delta from Threshold | Exit Category |
|---|---|---|---|---|---|
| T5 | run_111 | FIL/FLOKI | −0.00449 | +0.02449 | coint-failure |
| T6 | run_113 | DOGE/SUI | unavailable (pre-7.2) | unavailable | coint-failure |
| T7 | run_115 | BTC/HBAR | −7.63e-07 ≈ 0 | +0.0200 | normal |
| T8 | run_116 | SOL/AVAX | +3.99e-04 | +0.01960 | **normal** |

coint_stability_slope_exceeded count: **18** (unchanged — 0 blocks this session)

- coint-failure: 2 / normal: 2 / total evaluated: 4
- Both visible slopes from coint-failure (T5) and normal exits (T7, T8) are far below threshold
- Deltas: T5 +0.02449, T7 +0.0200, T8 +0.01960 — all > 0.015 (far-below-threshold zone)
- No clustering by outcome visible. All three observable slopes occupy the same region of slope space.

**Premise-tracking note:** At 4 trades (2 with coint-failure, 2 normal exits), all observable slopes are far below threshold and in the same region. The filter has not been close to catching any trade in this window. Record and continue.

---

## Section 5 — Early-Stop Trigger Check

**Status: RETIRED** — 3-trade check passed at T7 (run_115). Gate-inactivity trigger (4C-TRIGGER) is the sole active stop mechanism.

---

## Section 6 — Entry Rejection Distribution

| Reject Type | Count |
|---|---|
| strategy_gate | 67 |
| entry_safety_gate | 44 |
| trade_quality_gate | 7 |
| **Total** | **118** |

entry_safety_gate breakdown:

| Reason | Count (approx) |
|---|---|
| advanced_ml_break_risk_high | ~30 |
| liquidity_at_floor | ~7 |
| risk_off_thin_liquidity | ~5 |
| correlation_component_below_threshold | 7 (PEPE/HBAR, ~10:07–10:08 UTC) |
| coint_stability_slope_exceeded | **0** |

trade_quality_gate: 7 rows, all `score_below_threshold` (PEPE/HBAR, 10:06–10:07 UTC; scores 70.42 and 71.87 vs min 72).

No coint_stability blocks this session. Cumulative slope_exceeded: 18 events, 1 distinct pair (AVAX/ADA, run_113 only).

**Pair-specific notes:**
- AVAX/ETH: 5 blocks on advanced_ml_break_risk_high (break_risk=0.15), then cointegration_watch_timeout
- HBAR/SOL: 1 block on liquidity_at_floor, then cointegration_lost_unproven
- PEPE/HBAR: ~18 blocks spread across advanced_ml_break_risk_high, risk_off_thin_liquidity, correlation_below, trade_quality_gate (RISK_OFF regime throughout)
- ADA/SOL: ~12 blocks on advanced_ml_break_risk_high and liquidity_at_floor, TREND regime gate activity
- SOL/AVAX: 1 insufficient_history row; entry accepted on next cycle

---

## Section 7 — Counter Update and Next Step

```
trades_since_experiment_start: 4
evaluated_trade_count: 4 (T5, T6, T7, T8 all evaluated)
insufficient_history_trade_count: 0
not_reached_trade_count: 0
trades_remaining_to_action_threshold: 16
cumulative PnL (experiment window, T5–T8, economic analysis): −$1.448 [T5+T6+T7 only — T8 PnL UNRELIABLE, excluded]
cumulative PnL (experiment window, T5–T8, all trades): −$1.513 (T5 −$0.555, T6 −$0.786, T7 −$0.107, T8 −$0.065 [unreliable])
win rate (experiment window): 0/4 = 0%
coint-exit losses so far: 2 trades, −$1.341 (T5 FIL/FLOKI, T6 DOGE/SUI — T7 and T8 were normal exits)
coint_stability_slope_exceeded count: 18 events, 1 distinct pair (AVAX/ADA, unchanged)
gate fire rate (session): 0/42 = 0%
gate_inactivity_trigger_status: MONITORING (need 2 more gate-reaching trades)
Section 5 status: RETIRED
next step: run 117 with frozen configuration
```

**T8 per-analysis exclusion:** T8 is **telemetry-complete for gate/slope analysis** (gate_status=evaluated, slope=+3.99e-04 valid, exit_category=normal — all unaffected by reconciliation). T8 is **PnL-unreliable for economic analysis** (reconciliation FAIL, fees=0, basis=position_pnl, close via emergency flatten path). The −$0.065 equity PnL is recorded but not trusted for cost attribution. At the 20-trade structural review, T8 contributes to the slope-premise analysis but is excluded from economic analysis (same pattern as run_98 restart exclusion and run_100 manual-close exclusion in prior windows).

**Open item — Emergency flatten close path:** Close via EMERGENCY_FLATTEN bypasses the standard fee-capture path. fees=0, basis=position_pnl, hold_minutes=null result. This is the first occurrence in the experiment window. Route to structural review.

**Patch 7.2 CSV delivery confirmed:** entry_coint_stability_slope and entry_coint_stability_evaluated_count now appear in trade_closes.csv as expected. The slope logging gap is closed. T8 is the first trade where the structured CSV field was the primary slope source.

---

*Audit completed 2026-05-26. Section 5 retired. Run 117 is next.*
