# Lever-B Offline Pre-Test — Verdict 2026-05-31

*Tested the premise of Lever B (shorter hold horizon outruns mean-shift) on the 15 closed trades' position-snapshot data. Read-only, no trades, no bot contact, no marking-fidelity wall (real cent-exact `upl`). Pre-committed verdicts cold in `docs/prompts/work_item_lever_b_offline_pretest.md` §4 with strategist self-binding anti-rationalization lock. Tool: `tools/observation_mode/lever_b_hold_cap_simulation.py`.*

---

## Verdict: **LEVER-B-DEAD**

The fast-reverting-at-mean sub-population that Lever B requires does not exist in the data. Across all 5 candidate caps M ∈ {1, 2, 3, 5, 8} minutes, the count of trades that (a) clear cost at the cap, robustly to the ±$0.06 cost-model noise band, (b) were not already going to clear at realized exit, and (c) were positioned in-zone (|z| ≤ 0.5, thesis-capture-at-mean — not at overshoot) is **0/13** at every cap. The thesis-capture signal Lever B requires is absent.

**This substantially firms the negative result. Pivot-or-stop is now earned, not premature.**

---

## The anti-rationalization lock fires as the work item specified

The strategist self-bound (work item §4): *"I have been advocating Lever B as the soundest dominant-mode lever. If this returns LEVER-B-DEAD, I write 'the most promising lever has no pulse, the negative result firms, the honest move is pivot-or-stop' with the same readiness I'd write LEVER-B-HAS-PULSE."*

The data says DEAD. **The most promising dominant-mode lever has no pulse. The negative result firms substantially. The honest move is pivot-or-stop.**

This is the discipline working at the hardest moment — the one where the analyst's own prior was wrong. The simulation ran to answer whether the fast-reverting-at-mean sub-population exists; it does not. That answer holds whether or not anyone wanted it.

---

## Method (one-line)

For each of the 15 trades, force-exit at minute-offset M ∈ {1, 2, 3, 5, 8} using the existing 1-minute-cadence position-snapshot stream. At each cap, classify whether the cap rescues a trade — defined as cleared-at-cap-robustly (point estimate + adverse cost) AND not realized-cleared (the realized hold didn't win) AND rescued-at-mean (|z| ≤ 0.5 at the cap moment, thesis-capture rather than overshoot luck).

---

## Per-trade data loaded

| Trade | n_snap | realized_gross | real_cost | Recon | Realized cleared? |
|---|---:|---:|---:|---|---|
| T1 | 17 | −$0.328 | $0.257 | FAIL | no |
| T2 | 4 | +$0.145 | $0.251 | FAIL | no (cost-overrun) |
| T3 | 11 | −$0.036 | $0.000 | PASS | no |
| T4 | 11 | −$0.007 | $0.143 | PASS | no |
| T5 | 29 | +$0.221 | $0.100 | PASS | **yes** |
| T6 | 19 | +$0.233 | $0.194 | PASS | **yes** |
| T7 | **1** | −$0.013 | $0.215 | PASS | no (motivating; INSUFFICIENT) |
| T8 | 9 | +$0.282 | $0.159 | PASS | **yes** |
| T9 | 25 | +$0.106 | $0.113 | PASS | no (marginal) |
| T10 | **1** | −$0.038 | $0.156 | PASS | no (INSUFFICIENT) |
| T11 | 10 | −$0.341 | $0.122 | PASS | no |
| T12 | 14 | −$0.397 | $0.336 | FAIL | no (heavy loss) |
| T13 | 37 | −$0.091 | $0.134 | PASS | no |
| T14 | 38 | −$0.212 | $0.115 | PASS | no |
| T15 | 20 | −$0.016 | $0.098 | PASS | no (basis-mismatch suspect) |

**INSUFFICIENT-TICKS (no imputation):** T7 and T10 (1 snapshot each). T7 is the motivating case for Lever B and cannot itself test the cap hypothesis — its 1.1-min hold means it was effectively self-capped by fast reversion, but no alternative caps can be simulated. T7 motivates, contributes zero. Evaluable N = **13**.

**Realized-cleared (would have won anyway):** T5, T6, T8 (3 trades). These cleared at realized exit regardless of cap — caps cannot "rescue" what already won. Any rescue must come from trades that did NOT clear at realized.

**Trades available for rescue:** the 10 non-realized-cleared evaluable trades (T1, T2, T3, T4, T9, T11, T12, T13, T14, T15).

---

## Per-cap aggregate results

| Cap (min) | n_eval | cleared @cap (point) | cleared @cap (adverse) | rescued (point) | rescued (robust) | **rescued (robust, at-mean)** | agg_simulated | agg_realized |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 13 | 0 | 0 | 0 | 0 | **0** | −$2.410 | −$2.464 |
| 2 | 13 | 0 | 0 | 0 | 0 | **0** | −$1.912 | −$2.464 |
| 3 | 13 | 1 | 0 | 0 | 0 | **0** | −$1.847 | −$2.464 |
| 5 | 13 | 1 | 0 | 1 | 0 | **0** | −$1.973 | −$2.464 |
| 8 | 13 | 1 | 1 | 0 | 0 | **0** | −$2.259 | −$2.464 |

**Load-bearing column: `rescued (robust, at-mean)` is 0 at every cap.** The signal Lever B requires — clean thesis-capture rescues at the mean — is absent from the data.

The 1 robust-rescue at cap=8 was rescued-at-overshoot (z out of zone) — momentum luck, not thesis-capture. The 1 point-rescue at cap=5 was non-robust (sign-flipped under adverse cost). Neither counts toward PULSE per §3.4 of the work item.

---

## Why the data structurally supports DEAD (not just statistically thin)

The aggregate improvement (~$0.62 across 13 trades = **+$0.048/trade average**) is **within the ±$0.06 per-trade cost-model noise band**. The improvement comes from one mechanism only: shorter holds incur slightly less total time-cost (funding + maybe a hair of slippage) — but the per-trade improvement isn't statistically distinguishable from cost-model precision. It is **not** evidence of a fast-reverting sub-population.

The structural reason rescues don't appear, visible in the per-trade data:

- **T5, T6, T8** (the three realized-winners): had meaningful positive gross moments → cleared at realized → not rescuable by cap (already won).
- **T1, T11, T12, T14**: heavy losses (−$0.21 to −$0.40 net) driven by relationship breakdown that started early in the hold. No early profitable moment to cap-and-cash.
- **T3, T4**: near-flat gross pnl throughout (−$0.04, −$0.01). The position barely moved — no rescue possible because no edge ever materialized.
- **T9, T13, T15**: marginal losses where gross was small at every snapshot. The pattern: gross hovered near zero through the hold, never exceeded cost at any minute-mark.
- **T2**: cost-overrun case ($0.25 cost on a thin KSM leg). Gross was +$0.14 — wouldn't clear at any cap because the cost is structurally too high.
- **T7, T10**: insufficient snapshots, excluded.

**The unifying structural fact:** the loss profile isn't "spreads reverted early then drifted away" (which a cap would rescue). It's "spreads either failed to revert at all (DECOUPLED, dollar-negative throughout the in-zone window) or reverted and gave it back beyond the noise band" (TRACKED-THEN-BROKE pattern). Mean-shift's signature is dollar-decoupling — and dollar-decoupling means there's no profitable early moment for a cap to capture.

This is consistent with the §9.5 finding (6/9 DECOUPLED cases were dollar-negative even at z=0 — at the mean) and with T15's specific shape (positive +$0.102 at mean, but below cost-clearance $0.14 — even the rescue moment wasn't cost-clearing).

**Lever B's premise — fast capture before drift — assumes there's a profitable moment to capture. The data says there usually isn't.**

---

## What this changes about the forward-options reading

**The most-promising dominant-mode lever is dead on the data.** The forward-options analysis identified only two levers that target the dominant loss mechanism (mean-shift): Lever B (shorter hold, outrun the drift mechanically) and Lever I/F (predictive selection, bet on stability). The strategist's reasoning ranked B above I/F because I/F bets on prediction (the thing the slope filter died trying to do) while B bets on mechanical exit (no prediction required). With Lever B now DEAD on the data:

- **Lever I/F** is the remaining "addresses mean-shift" lever, and it bets on the same predictive relationship the slope filter falsified. Even less defensible than before — Lever B was the more credible dominant-mode lever, and it has no pulse.
- **Levers C, D, E** are hygiene levers that trim secondary modes (~1pp on broken_rate, 2/15 cost-outliers, 1/15 basis artifact). They cannot rescue a strategy whose dominant loss mode has no addressable lever.
- **Lever A** (notional scaling) was off the table even before; with no odds-improvement lever supported, it stays off.
- **Lever H** (cost-model precision) is informative — it would resolve whether the secondary cost-mode is edge-thin or cost-high — but does NOT change the dominant-mode-no-lever finding.
- **Lever F** (different universe) and **Lever G** (different strategy class) become the only remaining "real" options, and both are fresh starts, not refinements of the current strategy.

**The honest forward-options synthesis post-Lever-B-DEAD:**

> The strategy as designed has no demonstrated lever for its dominant loss mode. The most promising dominant-mode lever (shorter hold) is empirically absent on the data; the only other dominant-mode lever (predictive selection) is in tension with a previously falsified finding. Hygiene levers exist but cannot rescue a 60%-loss-rate dominant mode they don't address. The remaining genuine options are: (1) accept the negative result and stop, (2) pivot to a different strategy class (G), (3) start fresh on a different universe (F). All three are now legitimate calls; none is "fixing the current strategy" because no fix exists on the data.

---

## What Lever-B-DEAD does NOT prove

- Does NOT prove a live hold-cap experiment would fail — the simulation is a pure time-cap on 13 thin trades, not a live policy spec.
- Does NOT prove mean-shift is unaddressable in general — only that on N=13 evaluable trades, the fast-reverting-at-mean signal is absent.
- Does NOT prove the strategy is unprofitable in a different configuration (notional, universe, horizon) — only that within the configuration tested, Lever B doesn't have empirical support.
- Does NOT change H1 (sizing is still settled), the cost-clearance finding (0/6 still robust), the mean-shift FINDING (6/9 DECOUPLED unchanged), the basis-disagreement configuration finding, or the RISK_OFF vector corroboration.

## What Lever-B-DEAD DOES prove

- **The fast-reverting-at-mean sub-population does not exist on N=13 evaluable trades** at any cap M ∈ {1, 2, 3, 5, 8} minutes.
- The aggregate simulated improvement is within cost-model noise — not a signal.
- The strategist's prior (Lever B is the soundest dominant-mode lever) was data-falsified. The analysis ran to answer the question, not to vindicate the prior, and accepted what fired.

---

## Honesty residue

Two things I'd want operator-aware before this lands:

**1. N=13 is thin.** The work item flagged this explicitly. A larger N might surface 2–3 rescued-at-mean trades that didn't appear here. But the work item also pre-committed that "≤1 robustly-rescued at-mean" = DEAD precisely because thin-N can't be salvaged by "we just need more trades" — that route was foreclosed by the halt. The verdict respects the pre-commit at the cost of certainty: at this N, the answer is DEAD, and the alternative ("collect more data at $200") is refuted.

**2. The cost-proxy direction holds.** Using realized cost as proxy for capped cost is conservative (funding scales with hold, so capped trades' real cost is ≤ realized). The DEAD verdict is therefore robust: if accurate per-fill costs were used, capped costs would be slightly LOWER, but the 0 robust-at-mean rescues would remain 0 because the gross pnl at each cap was the binding constraint, not the cost — most trades had small or negative gross at every cap, regardless of cost adjustment. The cost-proxy looseness can't manufacture a signal where the gross side has none.

---

*Lever-B offline pre-test, run 2026-05-31. Tool: `tools/observation_mode/lever_b_hold_cap_simulation.py`. Output: `tools/observation_mode/output/lever_b_simulation.csv` (per-trade per-cap data, gitignored). Pre-commit + anti-rationalization lock: `docs/prompts/work_item_lever_b_offline_pretest.md` §4. Verdict: LEVER-B-DEAD. The fast-reverting-at-mean sub-population does not exist on the data; the most promising dominant-mode lever has no pulse; pivot-or-stop is earned. The strategist's prior was wrong, written cleanly as the pre-commit bound.*
