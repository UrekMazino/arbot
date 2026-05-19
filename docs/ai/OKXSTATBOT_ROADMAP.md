Active:
1. Run experiment exp_guard050_ethfi_excluded_v1 (guard 0.50, ETHFI excluded).
2. Collect minimum 20 closed trades. At ~3 trades per circuit-breaker-limited run, this is ~7 runs.
3. Per-run audit: report MFE timing buckets, z-score at MFE peak, TP-zone PnL, profit-lock activation count.
4. Attribution decomposition at 20-trade threshold:
   - ETHFI effect: did coint-failure exit rate drop vs 56% baseline?
   - Guard effect: did profit-lock activation count or trailing-stop exit count increase?

Upcoming (deferred until 20-trade threshold):
1. Forward-looking cointegration stability at entry gate — highest-confidence, largest-magnitude problem ($1.811 in coint-decay losses across 9 trades). Research phase only.
2. max_break_risk recalibration — median rejected break_risk was 0.150 in run 94, threshold is 0.12. Evaluate only after coint stability is addressed.

Future:
1. Pair universe quality hardening.
2. Mean reversion escape test.
3. Adaptive volatility/regime filters.
4. Bayesian/online ranking improvements.

Do not do until evidence threshold is met:
- Exit z-zone widening (changes timing architecture; higher risk than guard adjustment).
- Notional scaling (ratios unchanged with notional; not a lever until edge question is resolved).
- Circuit breaker recalibration (only if breaker trips block data collection across many runs).
- Router activation (shadow mode only until entry quality stabilizes).
- ML live gating.
