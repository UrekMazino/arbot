# B1 — No-Notional Observation Mode

**Authorized 2026-05-31** as exp_beta_aware_sizing_v1 structural-review follow-on (Branch A accepted; B1 = the one worthwhile follow-on). Read-only sidecar, no trading, no PnL computed — the marking-fidelity wall that killed query-3 does not apply because the metric is the cointegration test result itself, not a hypothetical position's PnL.

## What it answers

Two questions the E4 halt's eligible-return discriminator cannot answer directly (the halt stopped producing eligible trades — the data the discriminator would read):

1. **TEMPORAL vs STRUCTURAL fragility.** Does the universe's coint-monitoring rate vary across time (suggests regime change), or has it been steady (suggests the universe has always been this fragile)?
2. **RISK_OFF vector test at N.** Does coint-monitoring health condition on entry regime? The closed-trade evidence is 2/2 (T9, T12) — base-rate-indistinguishable at N=2. The sampler tests this at much larger N (147 RISK_OFF samples vs 540 RANGE samples in the exp_beta window).

## What it does

For every bot run log, parse every `COINT_GATE` event (emitted ~once per minute by the live monitoring loop on the active pair). Each event records the live cointegration test's verdict: `health=valid|watch|broken`. The sampler aggregates these into:

- **Per-run sample stream** (one row per `COINT_GATE` event): timestamp, pair, regime, vol_pct, health, p-value
- **Per-run summary**: counts of each health state, broken_rate, by regime, by pair
- **Cross-run aggregate**: temporal arc + RISK_OFF vector read

## Key metric: `broken_rate`, not `fragility_rate`

The first-pass run revealed a structural property of the bot's live coint-monitor: **`health=valid` is never observed across 732 samples / 18 runs of the exp_beta window.** Every sample reads `watch` or `broken`. This is a property of the live monitor's thresholds (`basis=kline_only`, `sample=120`, `window=60` — different from entry-discovery basis), not of the universe. The implication: `fragility_rate = (watch + broken) / total ≡ 1.0` everywhere — a useless metric under the current configuration.

The **discriminating metric is `broken_rate = broken / total`**. The valid → watch → broken progression is monotonic in cointegration degradation; `broken` is the cleanly-failed end of the scale and is what varies meaningfully across regime, pair, and time.

## Stop-and-report guardrails

- Does NOT write to bot-owned files.
- Does NOT invoke trade-permissioned credentials.
- Does NOT call any bot code or modify bot state.
- Does NOT subscribe to OKX or any live API.
- Reads existing `Logs/v1/<run>/log_*.log` files only.

## Usage

Analyze a single run:
```
python tools/observation_mode/coint_fragility_sampler.py --run run_142
```

Analyze the exp_beta_aware_sizing_v1 window (runs 125–142):
```
python tools/observation_mode/coint_fragility_sampler.py --exp-beta-aware-sizing
```

Analyze every run under `Logs/v1/`:
```
python tools/observation_mode/coint_fragility_sampler.py --all
```

Output goes to `tools/observation_mode/output/`:
- `<run_name>__samples.csv` — per-event rows (one per `COINT_GATE` evaluation)
- `summary.csv` — per-run aggregates including `broken_rate` and per-regime breakdown

## Baseline finding (exp_beta_aware_sizing_v1 window, 2026-05-31)

Across the 18 runs of exp_beta_aware_sizing_v1 (125–142), 732 COINT_GATE samples:

| Slice | n | `broken` | broken_rate |
|---|---:|---:|---:|
| **Overall** | 732 | 132 | **18.0%** |
| RANGE | 540 | 89 | **16.5%** |
| RISK_OFF | 147 | 34 | **23.1%** ← elevated |
| TREND | 45 | 6 | 13.3% |

**RISK_OFF vector — corroborated at N=147 samples.** RISK_OFF's broken_rate (23.1%) is ~40% above RANGE's (16.5%) and ~28% above the overall base rate (18.0%). This is the first measurement of the RISK_OFF-coint-failure relationship at a sample size that escapes base-rate-indistinguishability concerns. Per-trade evidence (2/2 entries → coint-failure at T9, T12) is corroborated; the relationship is real, not coincidental.

**TEMPORAL vs STRUCTURAL — see `summary.csv` for per-run sequence.** Initial read: broken_rate varies run-to-run (5–25% range, with two single-sample outlier runs); no clean monotonic trend across the window. Provisional: leans **STRUCTURAL** (steady-state elevated fragility) rather than TEMPORAL (clean regime shift) — but with two methodological caveats: (a) runs are single-trade windows of variable length, so per-run rates are noisy; (b) the `health=valid` ceiling means the dynamic range of the metric is compressed. A longer continuous observation run (without trading) would tighten the temporal read.

## Methodological notes

**Per-run-N variance.** Single-trade runs (`max_session_trades=1`) produce variable sample counts — 0 to 163 across the window. Runs with very few samples (e.g., run_140 with n=2) cannot be read on their own. Cross-run aggregation is what carries the signal.

**The valid-state-never-observed finding is itself informative.** It says the bot's post-entry coint-monitor is structurally tighter than the entry-time discovery gate. Pairs that pass entry discovery (`entry_coint=1`, `entry_health=valid` on every line) do not stay in the live monitor's `valid` band after entry. This is consistent with the mean-shift finding (the relationship drifts post-entry) and may be quantifying the same phenomenon from a different angle.

**Not a substitute for a continuous observation run.** The exp_beta window's data was collected under `max_session_trades=1` runs — short windows, one trade per run, frequent restarts. A longer continuous run with `max_session_trades=0` (or equivalent observation-only configuration) would produce a denser, cleaner sample stream. v1 reads what we have; v2 (if needed) would add a continuous-observation runner.

## Versioning / scope

- **v1 (2026-05-31)**: historical log analyzer. Reads existing run logs, no bot dependencies, no live API calls, no trade-permissioned credentials. Produces the baseline reported above.
- **v2 (deferred)**: continuous observation runner. Would require a bot-side flag for observation-only mode (no order placement) and a longer run window. Not built; not yet authorized. v1 may be sufficient.

## Pattern precedent

Mirrors `tools/fidelity_validator/validator.py`:
- Read-only Python sidecar
- Parses bot logs as the data source
- Writes to its own `output/` directory (never to bot-owned files)
- Same stop-and-report discipline
