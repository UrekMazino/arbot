# Program Closeout — OKXStatBot Statistical-Arbitrage Research Program
## STOPPED 2026-06-11, by operator decision, per the default locked before the final result existed

*The operator accepted the stop default ("ok stop") on 2026-06-11, activating the clause locked at commit `d0f5529` before G1's verdict existed: "a program whose evidence-backed paths are exhausted is complete, and reaching for evidence-free paths is momentum, not research." This document is the permanent institutional record of the full arc.*

---

## 1. The one-paragraph summary

The program asked whether statistical-arbitrage on OKX crypto perpetual pairs clears costs at small notional. Over three experiments and a four-direction pivot arc it produced a complete, multiply-measured answer: **no — on this universe, post-event spread movement is too close to noise to clear even ~$0.25 of costs, in either direction (reversion or continuation), at either tested timescale (minute or daily).** The sizing layer was solved cleanly along the way (H1, β-aware sizing, 15/15 exact). The live cost of the answer was −$4.65 over 15 trades; every investigation after the live halt — five pre-tests and design phases, each with verdicts locked before data — cost $0.

## 2. The arc

| Stage | Dates | Verdict | Cost |
|---|---|---|---|
| exp_guard050 / exp_coint_stability_v1 (predecessors) | 2026-05-19 → 05-28 | Sizing-mismatch found (10A); coint-filter premise refuted (10B) | live, prior ledger |
| **exp_beta_aware_sizing_v1** (live, 15 trades) | 05-28 → 05-31 | **H1 CLEAN SUCCESS** (sizing settled); E4 halt at T15; structural review v1.2: **Branch A — no robust edge above costs at $200** | **−$4.65 live** |
| §9.5 basis-mismatch diagnostic | 05-31 | BASIS-AGREEMENT-WITH-T15-ASTERISK — halt ratified, T15 artifact bounded at 1/9 | $0 |
| B1 observation mode (v1 + v1.1) | 05-31 | RISK_OFF corroborated N=147; fragility structural-leaning; selection-entangled | $0 |
| Lever-B offline pre-test (hold-cap) | 05-31 | **LEVER-B-DEAD** — zero rescued-at-mean at any cap | $0 |
| D1 continuation pre-test (minute) | 05-31 | **INFEASIBLE-INSTRUMENT, definitive** — one re-spec bind held; 4-point private-basis meta-finding | $0 |
| D3 pre-test (daily MR premise) | 06-11 | **SUPPORTED** — survival 82.4%@+10d (null 39.0%), edge 12–55× | $0 |
| D3 design Phase A (funding) | 06-11 | Pairs funding nets out (p50 $0.104/10d — assumptions were 6× pessimistic) | $0 |
| D3 design Phase B (capture) | 06-11 | **DESIGN-DEAD** — 72% breakdown-mode exits; gross-dominated failure | $0 |
| Pivot-G scoping + G1 (daily continuation) | 06-11 | **G1-DEAD** — breakeven gross, chop + costs; hypothesis revealed regime-local by fresh-data half | $0 |
| G2 (funding capture) / G4 (options) | 06-11 | Closed on measured arithmetic / scale | $0 |
| **Program** | **2026-06-11** | **STOPPED** | total live −$4.65 |

## 3. The findings ledger (what is now known)

1. **H1 — β-aware sizing (Option C, gross-normalized) is correct and settled.** 15/15 mechanically exact across β ∈ [0.378, 1.841]; 5/5 eligible trades sign-positive. Transfers to any future pairs structure.
2. **Extension-selects-breakdown (the program's unified finding).** Statistical extension of a cointegrated spread is more often the onset of relationship breakdown than a reversion opportunity — measured three independent ways at minute scale (60% live coint-failure; zero Lever-B capture moments; 6/9 dollar-DECOUPLED) and confirmed at daily scale (72% breakdown-mode exits from 2σ entries).
3. **Both directions fail at daily scale.** Reversion: −$1.4/trade gross. Continuation: −$0.3/trade gross (breakeven before costs; 75% chop-out rate; the real continuation tail — +$13.48 avg on max-hold survivors — is too rare to carry the chop).
4. **Unconditional ≠ conditional survival.** Discovered daily relationships survive 10-day holds at 82.4% unconditionally (vs 39.0% null) — but a strategy only trades the extended moments, and that conditioning inverts the population. "Survival ≠ profitability" was the locked caveat this lived in.
5. **The private-basis meta-finding (4 converging diagnostics).** The bot's internal minute-scale basis (orderbook-mid, per-tick OLS β, OKX markPx) is a private coordinate system: neither levels nor short-horizon differences are reproducible from any public source at decision-relevant tolerances. Offline analysis must use logged quantities or public-native timescales.
6. **Pairs funding nets out.** Measured pair-differential funding: p50 $0.104 / p90 $0.470 / p99 $2.005 per 10-day hold at $200 — both-legs-pay assumptions overstate ~6×; the tail is real.
7. **Universe characteristics:** RISK_OFF coint-fragility elevation corroborated at N=147 (selection-entangled); fragility structural-leaning, not temporal; per-pair broken rates 0–48%.
8. **Operational findings on record:** Patch 6 item 5 (flatten kill-switch) still the stated prerequisite for any future live trading; consecutive-loss circuit breaker structurally inert under one-trade-per-session (scale-up note, v1.5 §10); kline-only monitor stricter than orderbook-mid selector (T15-class artifact possible — basis alignment required if the minute-scale bot is ever revived).

## 4. The assets preserved

- **Toolchain (10 read-only tools, `tools/observation_mode/` + `tools/fidelity_validator/`):** coint-fragility sampler, per-pair aggregator, basis-mismatch diagnostic, Lever-B simulator, D1 kline fetcher/metadata/sanity gates, D3 pre-test, funding-reality tool, D3 capture walk-forward, G1 continuation pre-test, fidelity validator. All regenerate their outputs from caches/public data.
- **Data caches (gitignored, regenerable):** 1m klines (exp window), 1D klines (400d + 800d), funding history (44 instruments), all per-trade/per-fold result CSVs.
- **The discipline apparatus (the meta-asset):** verdicts locked before data; anti-rationalization locks binding the advocate; ridge requirements against multiple comparisons; skeptical audits applied hardest to wanted answers (D3's null-baseline check; the symmetric sign audits on DEAD verdicts); one-re-spec binds; taint mitigation via untouched-data halves; stop-as-default clauses written before results. It held through five consecutive verdicts, wanted and unwanted alike.
- **Work-item templates (`docs/prompts/`):** reusable gate structures for any future research program.

## 5. What would reopen anything (standing conditions, so stop stays honest)

- Nothing in this closeout forbids future work; it records that *current evidence supports none*. Reopening any direction requires **new evidence or a new regime**, not re-narration: e.g., a structurally different universe (not crypto perps at retail scale), materially lower cost structure (maker infrastructure, fee tier), or an exogenous reason to believe the extension-selects-breakdown regime has changed — testable first via the existing read-only toolchain at $0.
- G3 (single-asset daily momentum) remains what it was flagged as: an evidence-free fresh bet. If ever pursued, it starts with its own locked work item, not with this program's conclusions.
- The live bot remains stopped. Before ANY future live trading: Patch 6 item 5, basis alignment, circuit-breaker re-scope (all on record above).

## 6. Closing note

The program is complete, not abandoned. It asked one question, built the discipline to trust its own answer, and got that answer at the lowest cost the answer was available for: sizing works; the edge does not exist on this universe at this scale, in any direction, at any tested timescale. The negative result survived every audit it was given — including the ones that found errors and corrected them on the record. That is what makes it worth having.

---

*Program closeout, 2026-06-11. Operator decision: STOP, accepted per the pre-locked default. Final ledger: −$4.65 live across 15 trades; $0 across the entire post-halt research arc. All artifacts in `docs/audits/`; all work items in `docs/prompts/`; all tools in `tools/`. End of program.*
