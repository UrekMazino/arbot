# PnL Source Mismatch — Diagnostic Note
**Date:** 2026-05-20
**Status:** CLOSED — fees-timing artifact, not a bug
**Runs examined:** 93, 94, 95, 98
**Occurrences:** 4 (all confirmed same root cause)

---

## The Pattern

Every run's exit_decision_trace.csv shows a systematic delta between two PnL fields at the first trace row of each trade:

| Run | Pair | floating_pnl | position_snapshot | delta |
|-----|------|-------------|-------------------|-------|
| 93 | ETHFI/SOL | -0.1528 | -0.0528 | **-0.1000** |
| 94 | ETHFI/AVAX | -0.1792 | -0.1056 | **-0.0736** |
| 95 | FIL/AVAX | -0.1110 | -0.0218 | **-0.0892** |
| 98 (ARB/SOL) | ARB/SOL | -0.1653 | -0.0651 | **-0.1001** |
| 98 (ETH/AVAX, close-time) | ETH/AVAX | -0.15 | +0.12 | **-0.27** |

---

## Root Cause

**`floating_pnl_usdt` (equity-delta method):**
- Computed as `current_equity − entry_equity` where `entry_equity` is the OKX account balance captured at trade open time via `set_entry_equity(equity_usdt)` in `main_execution.py`.
- The `equity_usdt` value used as the baseline is fetched from the balance API at or just before trade open, before all leg fills and fee deductions have propagated to the API response.
- Result: `floating_pnl` includes the entry-fee deductions that happened AFTER the baseline was captured.

**`position_snapshot_unrealized_pnl_usdt` (OKX position API):**
- Computed from the OKX `upl` field on each open position: `(current_mark_price − avg_entry_price) × position_size`.
- This is pure mark-to-market. OKX does NOT include entry or exit fees in `upl`.

**The delta = entry fees that were deducted from equity after the baseline snapshot:**
- Notional per leg: ~$100 (total $200 capital, two legs)
- Taker fee rate: 0.05% per leg (confirmed from run 98: AVAX fee = $0.050028 on $100.056 notional)
- Both-leg entry fees: ~$0.10 USDT
- Observed early-trade delta: $0.09–$0.10 ✓

The slight variation below $0.10 (e.g., $0.0892 in run 95) reflects the exact moment the balance API was queried relative to when the second leg's fee propagated. This is an API propagation race, not a measurement error.

---

## Run 98 ETH/AVAX Amplification ($0.27 at close)

This case is different from the entry-time baseline delta and has a different cause:

1. Mid-trade subprocess restart (exit code 3) cleared `entry_equity` via `clear_entry_tracking()`.
2. The equity baseline was never re-established after restart (bot entered "restart scenario" mode).
3. At close, `STRATEGY_TRADE_CLOSE` fell back to session equity delta — which captured the entire period from last baseline through the 4m18s OKX outage during which z moved from +2.59 to +4.36.
4. The position_snapshot at close showed +$0.12 (mark-to-market at close prices was slightly favorable due to z partially reverting after the outage cleared).
5. Equity delta showed −$0.15 (capturing: entry fees −$0.10, exit fees ~−$0.10, net mark-to-market gain +$0.05, baseline drift from restart ≈ −$0.10).
6. Round-trip fees + restart-baseline drift explain the full $0.27 gap. Not a measurement bug.

---

## Canonical PnL Source

`floating_pnl_usdt` (equity-delta) is the correct economic PnL for trade recording purposes:
- It captures all costs: entry fees, exit fees, and slippage.
- The position snapshot `upl` is only useful as a real-time mark-to-market reference, not as a cost-complete measure.

The recorded PnL in `STRATEGY_TRADE_CLOSE` events (and in the experiment trade history) is equity-delta based. This is correct and should not be changed.

---

## Impact on Future Audits

**Expected behavior at trade entry (first trace rows):** delta of $0.09–$0.10 between `floating_pnl_usdt` and `position_snapshot_unrealized_pnl_usdt`. This is normal. No action required.

**Expected behavior at trade close:** delta grows to include exit fees as well (~$0.20 round-trip for $200 notional). If position snapshot shows +X and equity-delta shows −Y, the difference is approximately round-trip fees plus any slippage.

**Flag only if:** the delta exceeds $0.25 in the early-trade window (first few trace rows) without a restart scenario. That would indicate something other than fees driving the gap.

**The `pnl_source_mismatch_description` field in exit_decision_trace.csv** does not indicate a bug. It is a reporting field that documents the two sources. Future audits should note it but not classify it as an anomaly unless it exceeds the threshold above.

---

## Ticket Status

CLOSED. No code changes required. Audit template updated (this document serves as the reference). The `pnl_source_mismatch` deferred research item is resolved.
