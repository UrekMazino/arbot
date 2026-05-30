# Cost Diagnostic — Post T15 / E4 Halt
*Categorical cost diagnostic on real `real_costs` for the 5 eligible trades + T15 paired exhibit. Runs the three-cost-assumption robustness test (point estimate, cost−$0.06, cost+$0.06) per pre-committed spec. Verdict pre-committed cold before data pull; AMBIGUOUS-at-N fires.*

---

## Pre-committed verdict criteria (locked before data pull; verbatim from operator spec)

- **STRUCTURAL-INSUFFICIENT** — edge-at-mean sits below achievable cost across essentially all six points, *robustly to the ±$0.06 error bar* (even shifting every cost down by the full error, the edges don't clear). → §5 negative-result conclusion fires cleanly.
- **STRUCTURAL-with-VIABLE-SUBSET** — a cleanly identifiable subset (by liquidity tier, β band, or entry depth) clears cost robustly while the rest don't. → SUBSET-VIABLE branch with named subset, recommended next direction = universe restriction.
- **AMBIGUOUS-at-N** — the ±$0.06 error bar straddles the viability line on too many points to isolate cleanly. → Diagnostic does not isolate the verdict at this N; the negative-result reading is supported by convergent evidence (eligible stall, mean-shift β-independent, T15 below-cost-tracked) but not by the cost diagnostic alone. **Does NOT route to "collect more data"** — the §4 gate is superseded by the halt; no eligible-trade stream without un-halting. Routes to *"convergent evidence carries the weight the diagnostic couldn't,"* lands near negative-result reading sourced differently.

---

## Methodology

**Population.** Six trades: the 5 `$/σ`-eligible (T2, T5, T6, T7, T8) plus T15 as a paired exhibit (coint-failure exit, but the only point where edge-at-mean can be directly compared to cost on a trade that tracked the mean and exited for procedural-not-substantive reasons).

**Edge-at-mean (per-trade).** Snapshot `unrealized_pnl_usdt` at the snapshot with `current_z` closest to 0. Exception: T7 had only 1 snapshot (1.1-min hold, fastest in the window) — used gross `position_pnl_usdt` at exit (z=−0.34, zone edge) as the edge-at-mean proxy. This is the strongest available proxy and was carried forward from the per-run audit.

**Real cost (per-trade).** `|difference|` from `reconciliation_checks.csv` (= |trade_pnl − equity_change|, the realized cost gap including fees, slippage, funding, and the unexplained residual).

**Three-cost-assumption robustness test (per pre-commit spec):** for each trade compute edge_at_mean minus cost under three assumptions:
- **Point estimate** — recorded `real_costs`
- **Generous (cost − $0.06)** — most favorable to the strategy (assumes cost was systematically over-attributed by the full Item 12 error bar)
- **Adverse (cost + $0.06)** — most unfavorable to the strategy

**Trade-level classification:**
- **ROBUST-FAIL** — edge minus generous cost < 0 (fails even under the most generous cost assumption)
- **ROBUST-PASS** — edge minus adverse cost > 0 (passes even under the most adverse cost assumption)
- **SIGN-FLIPS** — sign of (edge − cost) changes across the ±$0.06 band (the gap exists at point but isn't robust to measurement uncertainty)

---

## Results

### Full six-trade table (eligible + T15 paired exhibit)

| Trade | Pair | \|entry_z\| | edge_at_mean | real_cost | edge − cost (point) | gen (−$0.06) | adv (+$0.06) | Robustness | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| T2  | LTC/KSM   | 2.01 | +$0.053 | $0.251 | −$0.198 | −$0.138 | −$0.258 | **ROBUST-FAIL** | recon-FAIL (large_delta_warning); KSM thin-leg cost driver suspect |
| T5  | AVAX/DOT  | 2.16 | +$0.052 | $0.100 | −$0.048 | +$0.012 | −$0.108 | SIGN-FLIPS | PASS recon |
| T6  | SOL/AVAX  | 2.06 | +$0.050 | $0.194 | −$0.144 | −$0.084 | −$0.204 | **ROBUST-FAIL** | PASS recon; high cost on liquid pair — Item 12 territory |
| T7  | SOL/CRV   | 2.78 | +$0.230 | $0.215 | +$0.015 | +$0.075 | −$0.045 | SIGN-FLIPS | **THE ONLY WIN; deepest entry**; even at +$0.015 point, flips under adverse |
| T8  | BCH/ETC   | 2.17 | +$0.169 | $0.159 | +$0.010 | +$0.070 | −$0.050 | SIGN-FLIPS | cleared at mean then EXIT-TOO-LATE overshot |
| T15 | SOL/LINK  | 2.18 | +$0.102 | $0.098 | +$0.004 | +$0.064 | −$0.056 | SIGN-FLIPS | **paired exhibit (n=1 coint-failure)**; tracked-then-broke; corroborates direction |

### Summary counts

| Slice | ROBUST-FAIL | SIGN-FLIPS | ROBUST-PASS | Verdict |
|---|---:|---:|---:|---|
| **Full (6 trades)** | 2/6 — T2, T6 | 4/6 — T5, T7, T8, T15 | **0/6** | **AMBIGUOUS-at-N** |
| Eligible-only (5 trades, drop T15) | 2/5 — T2, T6 | 3/5 — T5, T7, T8 | 0/5 | AMBIGUOUS-at-N |
| Recon-clean (5 trades, drop T2) | 1/5 — T6 | 4/5 — T5, T7, T8, T15 | 0/5 | AMBIGUOUS-at-N |

**All three slices return the same verdict.** Stable across analytical choices.

---

## Verdict: AMBIGUOUS-at-N

The three-cost-assumption robustness test does not isolate a verdict cleanly at N=6 (or N=5 in either reduced slice). The pre-committed reading fires per spec:

> *The cost diagnostic does not isolate the verdict at this N; the negative-result reading is supported by convergent evidence (eligible stall, mean-shift β-independent, T15 below-cost-tracked) but not by the cost diagnostic alone.*

### What the diagnostic *does* establish (robust to the error bar)

Even though the verdict is AMBIGUOUS, three findings within the diagnostic survive the error-bar test:

1. **No trade clears robustly.** 0/6 ROBUST-PASS. Not a single trade — including T7, the only win and the deepest entry — has edge-at-mean clearing cost under the adverse-cost assumption. **At $200 notional, every trade in the eligible population is within the cost-model's measurement noise band.**

2. **T7 (deepest entry, only win) is NOT robust.** The candidate "deep-entry-only viable subset" the operator named pre-pull does not survive the error-bar test — T7's point-estimate gap (+$0.015) is smaller than half the ±$0.06 error band; it sign-flips under adverse. **STRUCTURAL-with-VIABLE-SUBSET is not supported by the deepest-entry candidate.**

3. **Two clean cost-driven failures: T2, T6.** Robust-fail under the most generous cost assumption. T2's $0.251 cost coincides with recon-FAIL (large_delta_warning) and KSM thin-leg suspicion — consistent with the prior experiment's T10 / FIL-ICP cost-overrun anchor. T6's $0.194 cost on a liquid pair (SOL/AVAX) is the cleaner case: no recon issue, fully attributable, just high. **These two contribute the "cost-too-high" sub-mode to the failure-mode taxonomy.**

### Sub-distinction within AMBIGUOUS (cannot be isolated at this N but worth surfacing)

The four sign-flip cases (T5, T7, T8, T15) and the two robust-fails (T2, T6) suggest the diagnostic is *not* uniform across the population:
- T5, T7, T8, T15 cluster near the noise edge in BOTH directions of (edge − cost): edge ≈ cost within ±$0.10. *Could be edge-thin OR cost-mismeasured at this N — diagnostic cannot isolate.*
- T2, T6 cluster as clean cost-too-high cases. *Could be universe-restrictable (drop KSM-class thin legs, profile-tag liquid pairs with anomalous costs) — but at N=2 this is a directional hypothesis, not a finding.*

This is the textbook AMBIGUOUS shape: the data wants to tell two different stories ("edge thin" and "cost high on subset") and at N=6 cannot separate them cleanly enough to act.

### T15 paired-exhibit reading (n=1, corroborating only — guardrail honored)

T15's classification is SIGN-FLIPS at point estimate (edge − cost = +$0.004). On a single trade this is essentially zero — the cleanest single-trade illustration in the data of *"the mechanism worked and the edge was within the noise band of cost"*. It is the §5 edge-too-thin thesis in a single trade, with every confound removed (β exact, mean tracked, costs textbook, no entry error). **It corroborates the AMBIGUOUS verdict's "operates at the edge of measurement noise" reading.** It does NOT carry the verdict — it is one coint-failure trade and N=1 cannot isolate edge-too-thin from random small positives. Weighted as one trade, anchor exhibit for the edge-too-thin sub-mode in the review's evidence section.

---

## What AMBIGUOUS routes to (per pre-commit, verbatim)

> *AMBIGUOUS does not route to "collect more data" — the §4 gate is superseded by the halt, and there's no eligible-trade stream without un-halting. AMBIGUOUS routes to "the convergent evidence carries the weight the diagnostic couldn't," which still lands near the negative-result reading, just sourced differently.*

The convergent-evidence stack the review now reads against the verdict:

1. **H1 = CLEAN SUCCESS** (5/5 $/σ-eligible positive, 0 sign flips, aggregate +$0.044/σ, β-sizing 15/15 mechanically exact across β range [0.378, 1.841]). Sizing is settled. Not contested by this diagnostic.

2. **Mean-shift β-independent loss mechanism** (6/9 = 67% of clean coint-failures DECOUPLED, demonstrated at β ∈ {0.378, 0.456, 0.476, 0.561, 0.667, 1.495, 1.841}). Entry-unpredictable. Refuted-lever guardrail intact across the window.

3. **Eligible stall** (5 in T2–T8, **0 in T9–T15**, 7 consecutive non-eligible). The instrument that would generate more diagnostic data is the one that stopped producing.

4. **E4 halt fired on genuine trajectory** (37.5 → 44.4 → 50 → 53.8 → 57.1 → 60.0%, 5-deep coint-failure run at ~3% probability under 50% base rate). Cold pre-commit triggered exactly as designed.

5. **T15 as anchor exhibit for edge-too-thin** (mechanism worked, mean tracked, edge below cost at $200 notional). Single trade, corroborates direction, does not carry verdict alone.

6. **T7 (the one win) does NOT robustly clear cost** even on the deepest entry. The realized win was within the cost-model's noise band.

**Reading from the convergent stack:** the strategy as-built does not show robust capturable edge above the cost stack at $200 notional on this universe. The cost diagnostic alone cannot prove it, but it cannot disprove it either — and the surrounding evidence is convergent. This is *near* the §5 negative-result reading, sourced from the stack rather than from the diagnostic.

---

## Methodological notes carried for the review

- **The discriminator-bind on the halt-interpretation question (TEMPORAL vs STRUCTURAL fragility, per template v1.5 §4 pre-load) remains open.** The cost diagnostic doesn't resolve it; the eligible-return rate after halt would, but the halt stops producing the stream. The natural form the discriminator has to take if it's going to survive the halt is the **no-notional observation mode** — record coint-failure rate from the live monitoring loop without trading (marking-fidelity problem from the validator does not apply because no PnL is being computed). This is a deferred buildable that connects to but is distinct from the diagnostic; the review should name it as the form the discriminator must take, not as a build proposal.

- **The cost-model error bar (±$0.06 per trade) is approximately the size of the edges being measured.** This is the Item 12 finding rendered concrete: an instrument coarser than the signal cannot resolve the question by itself. AMBIGUOUS at N=6 with this error bar is what the math predicts; the failure mode of the diagnostic is informative about the cost-model precision required to ever resolve the question, not just about this experiment.

- **Two failure modes co-exist in the data and cannot be separated at this N.** "Edge inherently thin" (T7/T8/T15 sign-flip cluster) and "cost inherently high on subset" (T2/T6 robust-fail). The structural review must hold both as live sub-hypotheses; the cost diagnostic is not the instrument that separates them at N=6.

---

*Diagnostic run: 2026-05-31, post T15 / E4 halt. Operator pre-committed three verdicts cold before data pull; AMBIGUOUS-at-N fires under the pre-commit per the three-cost-assumption robustness test. Routes to convergent-evidence reading per pre-commit; structural review § 7 centerpiece.*
