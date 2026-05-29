# Structural Review Template — exp_beta_aware_sizing_v1
## Pre-committed criteria, decision tree, and analysis specs

**Status:** DRAFT — strategic, read-only. No config or code touched.
**Drafted at:** T3 (run 129), 2026-05-29. To be *filled in* at the review trigger (§4).
**Purpose:** Fix the success/null/negative criteria and the next-experiment decision tree **before** the data arrives. This is the project's stated defense against its own most documented failure mode — the "coherent reframe" (Patch 5 floor miscalibration, the level-check, the $/σ-gate; see structural_review_exp_coint_stability_v1.md §12). Pre-writing the bar is what makes a negative result un-reframable later.

This document fixes the criteria and the branches. It does **not** pre-judge the outcome. My current base case (sizing works, costs bind) is stated where relevant but is explicitly held as a hypothesis, not a conclusion.

---

## 0. Owner roles for this review

- **Operator (decisions):** sign off on §4 early gate, §6 branch selection at trigger, §8 maker design fork (if reached), §5 negative-bar wording.
- **Code assistant (code + data):** all CSV extraction, the §7 cost diagnostic computation, the §8 maker implementation if authorized, the §10 operational patch, and the limit_order_basis trap log/fix (§11).
- **Strategist (this doc):** fill the template at trigger; produce the branch-specific experiment spec once the branch is known.

---

## 1. Experiment-state header (fill at review)

```
Experiment group:        exp_beta_aware_sizing_v1
Sizing mode:             gross_normalized_beta (Option C); gross=$200; leg1=gross/(1+β), leg2=gross×β/(1+β)
Trades since start:      [N total]   ($/σ-eligible: [k])
Runs since start:        [list]
Circuit breaker trips:   [N]
β range observed:        [min, max]   (binding discovery envelope [0.3, 3.0]; sizing fallback [0.20, 5.00] nearly inert)
β fallback activations:  [N]   (expected 0 inside the discovery envelope)
Patches active:          4.1, 5, 6, 7, 7.1, 7.2, Beta-Aware Sizing[, Patch 6 item 5 if landed]
Confidence level:        LOW until §4 gate met
Sampling caveat:         circuit-breaker / one-trade-per-session bias — dataset over-represents early-session states
```

---

## 2. The question this experiment answers — and the one it cannot

**Primary (H1 — sizing alignment).** With β correctly threaded into sizing, does the dollar position track the spread? Diagnostic: `$/σ` sign stability across $/σ-eligible trades. This is the structural-prerequisite question — it asks whether the strategy is now being *fairly tested*, not whether it is profitable.

**Secondary (H2 — edge clears costs).** Equally important per early data. Even when β-sizing aligns signal and position (positive `$/σ`), does the captured edge exceed *real* costs? Diagnostic: the `edge_clears_costs` column (position_pnl vs real_costs). T2 is the cleanest single data point in the project and answered **no** in isolation (+$0.146 position, $0.251 real cost, 1.8× model) — the dual-problem structure surfacing again with sizing correctly handled.

**Out of scope (maintenance only).** Coint-failure rate. β-sizing does not touch the cointegration signal; the running ~2/3 in-window failure rate is consistent with the 40–56% lifetime baseline and is tracked in the coint-failure tracker, **not** read as a result of this experiment. The entry-slope lever for coint-failure is already refuted (exp_coint_stability_v1, Verdict 10B).

---

## 3. $/σ inclusion rule v1.2 (locked — restate verbatim)

Compute `$/σ` only if **ALL three** hold:
- **(a)** `exit_reason ∈ {normal, trailing_stop, profit_lock}` — **NOT** `cointegration_lost`, `cointegration_watch_timeout`, or any coint-failure category;
- **(b)** `MFE > 0`;
- **(c)** `|Δz| ≥ 0.5`.

Coint-failure exits go to the **coint-failure tracker**, never the `$/σ` table — regardless of whether z reverted favorably. Mechanical; no per-trade judgment. Rationale: a coint-failure trade is one where β ceased to be the right hedge ratio mid-hold, so *no* β would have aligned it — including it measures coint deterioration (already established), not the sizing question.

---

## 4. Review trigger and early-resolution criteria

**Review trigger (LOCKED — operator sign-off 2026-05-29): `≥ 20 closed trades` AND `≥ 8 $/σ-eligible (normal-exit) trades`, whichever is later.**
*Rationale:* coint-failures are running ~2/3 and are excluded from the `$/σ` population, so 20 *total* trades may yield only ~6–7 eligible — below the k≥5–8 that E1/E3 and the H1 sign-flip read require. Counting by eligible-trade progress prevents concluding on too-thin an eligible population. The `≥20 total` floor is retained in the AND so a fragility signal that shows up only in total-trade count (see E4) is not skipped by an eligible-only gate. The two gates pair: eligible-count protects the `$/σ` read; total-count + E4 protect against a universe too fragile to test. Mirrors the established early-resolution pattern (exp_coint_stability fired early at T11/T14).

**Early-resolution criteria (each pre-commits an action; mirrors the exp_coint_stability discipline):**

| ID | Condition | Pre-committed action |
|----|-----------|----------------------|
| **E1 — sizing-confirmed-positive** | First k≥5 eligible trades all positive `$/σ`, clear magnitude (\|$/σ\| > $0.005), 0 sign flips | H1 answered early (success). Proceed to H2 read; do not keep collecting solely for H1. |
| **E2 — sizing-negative** | ≥2 sign flips among eligible trades | H1 incomplete — sizing mismatch was not the (whole) `$/σ` driver. Stop; open Branch 3 (§6). Substantive negative result. |
| **E3 — cost-domination confirmed** | `edge_clears_costs = 0/k` over k≥5 eligible trades **with** positive `$/σ` | H1 success + H2 fail confirmed early. Begin Branch-2 prep (§7, §8) before reaching 20; the binding constraint is cost/universe, not sizing. |
| **E4 — universe-too-fragile (KILL-CRITERION, not a branch)** | coint-failure rate **> 60%** over **≥ 10 closed trades**. Denominator is **total closed trades, NOT eligible** — coint-failures are definitionally excluded from the eligible population, so an eligible-denominator rate is structurally ~0 and could never fire. | **Halt the sizing test.** The binding problem is coint-fragility of the *universe*, not sizing — too few trades will ever reach the eligible population to fairly test H1. Address exit-speed (coint-watch recalibration) or universe quality first, regardless of H1/H2 progress. Coint-failure has no tunable entry-knob (entry-slope refuted), so this is a committed *halt*, not a tuning action — the answer to "is the largest loss source being ignored?" |

**E4 calibration note (the trap to avoid).** The established coint-failure baseline is *already* high and has been **drifting down**, not up: 55.6% (raw 9-trade) → 36.8% (exp_guard050, 19) → 40.0% (exp_coint_stability, 10). A threshold near the top of that band would risk a **false halt on ordinary small-window variance** — and a false halt is itself a reframe risk (halting a fine test, then narrating fragility that wasn't there). So E4 fires **only on a clear breach (> 60% over ≥10 closed)**. The 45–60% band is **elevated-but-plausibly-baseline → review, do not halt**: note it, check whether it reflects drift above the pair universe's own prior windows rather than a level, and carry to the structural review as a flag. The honest signal is *drift above prior windows*, not the absolute level; the >60% line is the defensible auto-halt floor, the 45–60% review band catches the softer case without over-triggering.

---

## 5. Success / null / negative criteria (pre-committed)

**H1 — β-sizing aligns signal and position**
- **Success:** `$/σ` sign-flip rate ≤ 10% over the eligible population; cumulative aggregate `$/σ` positive.
- **Null:** sign-flip rate > 10%, or aggregate `$/σ` ≤ 0. → Branch 3.

**H2 — aligned edge clears real costs**
- **Success:** `edge_clears_costs = yes` on a clear majority of eligible trades; cumulative window PnL improves vs the equal-notional baseline.
- **Null:** `edge_clears_costs` stays near 0 despite positive `$/σ`. → Branch 2.

**Confidence labeling (project scale):** HIGH (multiple runs, directional consistency, clear mechanism, few alternatives) / MEDIUM (directional, small-sample, plausible mechanism) / MEDIUM-LOW (depends on assumptions that may not hold) / LOW (worth testing, indistinguishable from noise). Label H1 and H2 separately at review; do not collapse.

### THE NEGATIVE-RESULT BAR (load-bearing — anti-reframe commitment)

Pre-committed, to be held to the same standard that caught the Patch 5 A→B inversion, the level-check refutation, and the $/σ-gate:

> If, over ≥ 8 `$/σ`-eligible trades, **H1 is a success (signs stable-positive) AND H2 is a null (`edge_clears_costs` stays near 0)**, and the §7 cost diagnostic shows the cost gap is **structural** (clusters by spread category, does not shrink with N), and no cost lever in §8 plausibly closes the gap at $200 notional —
> then the **pre-committed conclusion is:** *the strategy does not have a capturable edge at the current notional and universe.* The correct next move is a universe/cost intervention (§7) or a stop decision — **NOT** another sizing or exit refinement, and **NOT** a re-narration of why this window was unrepresentative.

A success on H1 with a null on H2 is a *clean, valuable result*: it converts "the strategy failed" into "the strategy was correctly sized and the binding constraint is execution cost on this universe." That is a finding, not a setback. It must not be reframed into "needs one more patch" without new evidence clearing this bar.

---

## 6. Decision tree — pre-committed next experiment per branch

> **EMPIRICAL UPDATE (2026-05-29, post Query 1 + Query 2; N=2 clean eligible — DIRECTIONAL, branches below remain the pre-committed structure):**
> The zero-cost PnL-vs-z diagnostic (analysis_spec_pnl_vs_z_decoupling_v1) moved the branch likelihoods without changing the committed criteria:
> - **Branch 1 (exit redesign / Item 14) is now LESS likely the next lever.** Both clean β-sized eligible trades (T2b, T5b) have `pnl_at_mean (z≈0) ≈ +$0.052 < costs ($0.10–$0.25)` — the *thesis-exit* edge did not clear costs. T5's apparent edge (+$0.249) lived at a +2.16σ overshoot (anti-thesis momentum, where the strategy signals the opposite trade), not at the mean. **Zero trades classified EXIT-TOO-LATE; kill-condition 3 fired directionally.** The leak is *not* "held past a profitable mean"; the mean was never profitable enough. Item 14 "widen/redesign the exit zone" is **not indicated on the clean data.** Do not enter Branch 1 on N=2 — but its prior MEDIUM+ confidence is downgraded pending more eligible trades.
> - **Branch 2 is the leading direction — but the sub-lever is UNDETERMINED.** "pnl_at_mean < costs" has two readings the clean data cannot yet separate: **cost-too-high** (→ §7 cost levers: maker 2b, spread-gating 2a) vs **edge-too-thin** (+$0.052 mean-reversion capture at $200 may be structurally small on this universe; *no cost reduction saves a $0.05 edge* → this is a signal-quality / negative-result reading, NOT a cost-lever problem). Both T2b and T5b cluster at ≈+$0.052 (suspicious on N=2 — coincidence or a capture ceiling). **The §7 cost diagnostic (residual vs effective half-spread) is the discriminator and is hereby promoted from prep to critical path** (see §7 banner).
> - **Coint-failure mechanism: β-drift RULED OUT** (rolling β stable ±1.6% over T3b/T4b holds — robust positive measurement → re-hedging is NOT a lever). **Mean-shift is the leading surviving hypothesis by elimination** (dollars decoupled + β stable), **but attribution is UNVERIFIED** — the bar-close z reconstruction could not reproduce live intrabar z, so the price-vs-mean % is unreliable and not reported as fact. Honest status: *not β-drift; mean-shift consistent with evidence; microstructure/execution-noise on the holds not excluded; n=2 cannot establish it as the dominant universe failure mode* — that is Query 3's job. Lever mapping holds: mean-shift → post-entry/structural (exit-on-dollar-divergence, hold-time cap, stability-screened universe); **refuted-lever guardrail intact — no entry-slope/level revival.**
> - **Convergent through-line (HYPOTHESIS, N=2-clean):** every clean signal points away from entry-time and exit-zone-geometry fixes, toward **hold-window behavior + universe selection**. Recorded as hypothesis-converging, explicitly N-flagged — this is exactly the "coherent narrative at low N" shape the research paper warns about, so it does not harden into a finding until Query 3 / more eligible trades.

Read H1 and H2 at the §4 trigger, then:

**Branch 1 — H1 success AND H2 success (you have a strategy).**
Next experiment: **exit redesign (Item 14).** full_tp has captured *zero* exits in the Patch 7.1 window; MFE peaks at overshoot extrema *outside* the |z|<0.35 zone; the only win (T12) came from an incidental regime_break at overshoot, not designed capture. Exit-capture is miscalibrated on two axes (floor **and** zone). Deferred until now for the right reason — exit redesign is only testable once the `$/σ`-eligible population is clear of pairs no exit could save. *Confidence to enter:* MEDIUM+ on both H1 and H2. **[2026-05-29 DOWNGRADE: see §6 empirical-update banner — clean data shows the thesis-mean edge below costs and zero EXIT-TOO-LATE trades; Item 14 no longer the presumptive next lever. Re-confirm only if later eligible trades show `pnl_at_mean ≥ costs` with the exit leaking it.]**

**Branch 2 — H1 success BUT H2 null (cost/universe binds). [my current base case — held as hypothesis]**
Two handles, run **one at a time**:
- **(2a) Categorical spread-gating of the universe** (§7) — exclude structurally wide-spread token types (meme / reflexive-tokenomics / very-thin perps) on a *measured* footing, generalizing the one-off graveyarding (HMSTR, FLOKI). Lowest-risk; config/universe change.
- **(2b) Maker conversion** (§8) — a real but sharp-tradeoff execution change; behavior change requiring new code. Its own isolated experiment.
**Notional is explicitly NOT a lever** — edge and costs scale together at $200; doubling changes neither the edge ratio nor the cost-clearance probability (research paper §7.3). Do not propose notional scaling out of Branch 2.

**Branch 3 — H1 null (signs stay mixed).**
The sizing-mismatch hypothesis was incomplete. Re-open the `$/σ`-instability drivers: path-dependency (T11-class z-reversion-then-re-expansion), measurement error on near-breakeven trades (cost-model ±$0.05–$0.07 can exceed the quantity measured), or a residual sizing/exec defect. Substantive negative result; do **not** advance to exit redesign or cost levers until the `$/σ` instrument itself is trusted.

**Coint-failure (the largest single loss source) is deliberately not a branch.** The entry lever is refuted. The only remaining handles are exit-*speed* (recalibrate the coint-watch confirmation-count / loss-threshold to cut failing trades faster — lower-risk) and the research-phase pre-entry regime-flip detector (T3 deferred item). Both compete with exit redesign for the *experiment-after-next* slot; neither is ready to be the current variable. It is the biggest number but has no tunable knob — so it is handled not as a branch but as the **E4 kill-criterion (§4)**: if the universe is too coint-fragile to ever reach a testable eligible population, the committed action is to *halt* the sizing test and address exit-speed/universe first, regardless of H1/H2 progress. That is the answer to "is it being ignored?" — a committed halt-trigger, not a silent demotion.

---

## 7. Cost diagnostic spec (refined)

> **CRITICAL-PATH PROMOTION (2026-05-29, post Query 1+2):** This diagnostic was prep; it is now **the analysis that resolves which Branch-2 sub-lever you are in** — and, just as importantly, whether you are in a cost problem at all. Query 1 established that the clean-trade thesis edge (`pnl_at_mean ≈ +$0.052`) sits below costs, but "edge < cost" has two readings (§6 banner): **cost-too-high** (cost levers help) vs **edge-too-thin** (no cost reduction saves a ~$0.05 edge → negative-result territory). This diagnostic is the discriminator:
> - If costs **cluster structurally** by spread category and the gap to a tight-spread subset's costs is enough that `pnl_at_mean` would clear them → **cost-too-high → Branch 2 cost levers (maker §8, spread-gating).**
> - If costs are **near-model and roughly flat** across the universe while `pnl_at_mean` stays ≈$0.05 → **edge-too-thin → no cost lever closes the gap; this is the §5 negative-result bar**, not a cost intervention. Notional is not a rescue (edge and cost scale together).
> Run this **before** authorizing any Branch-2b maker build — it determines whether a maker build is even the right move or whether the honest finding is negative. Feed it the per-trade `pnl_at_mean` and `real_costs` columns Query 1 already produced.

**Prior result:** the T5–T14 residual-vs-**orderbook-depth** plot returned "pair-specific bias, NOT liquidity-tier-correlated" (T9 LINEA: $522 thin-by-depth leg, **positive** +$0.073 residual — a counterexample that kills a smooth depth gradient).

**Why the prior x-axis was likely wrong.** Depth (USDT available) and spread (bid-ask width) are different liquidity dimensions. A taker market order at $200 notional consumes little depth, so the first-order cost term is the **spread crossed**, not depth impact. A pair can be thin-by-depth yet tight-by-spread (plausibly LINEA), which is exactly the shape that makes a depth plot look "pair-specific" while a spread plot would resolve cleanly. The signal is probably **categorical by spread structure**, not continuous in depth.

**New spec (code assistant runs on existing telemetry):**
- **x (primary):** effective half-spread at entry (or quoted spread ÷ notional).
- **x (secondary):** spread × (notional / depth) as an impact proxy, to confirm depth is second-order at $200.
- **y:** unexplained reconciliation residual (from reconciliation_checks.csv).
- **tag:** structural category ∈ {major/mid-liquid, thin-alt, meme/reflexive}.
- **Data-availability check (flag):** does `liquidity_checks.csv` log bid-ask spread at entry, or must effective half-spread be reconstructed from the entry orderbook snapshot? Confirm before running.

**Decision this resolves (the fix-vs-infer fork):**
- **Random / unbiased** (scatter around zero regardless of spread) → √N averaging works; flat $0.14 model is fine in aggregate; **accumulate and infer**.
- **Structural / clustered** (residual sign & magnitude cluster by spread category) → averaging converges on the *wrong* answer; require either a **per-category cost model** or a **spread-gated universe**. This reframes the headline from *"is the strategy viable at $200 notional?"* to *"is it viable on the tight-spread subset?"*

**Two distinct cost components — keep separate:**
1. **Fee + quoted slippage** (T2: ~$0.10 + $0.04) — the directly addressable, mechanical cost; this is the **maker lever's** target (§8).
2. **Unexplained residual** (T2: −$0.111) — structural execution cost not captured in the fee/slippage fields; this is **this diagnostic's** target and where the random-vs-structural fork lives.

**Graveyard carry-forwards:** FIL (3 negative-residual events: run_99, T5/FLOKI, T10/ICP) is a standing candidate. JUP/YGG (T1, −$0.394, 3.8× — 4th thin-pair occurrence) → escalate to category-exclusion proposal on any recurrence.

---

## 8. Maker-conversion experiment (Branch-2b candidate) — scoping only, NOT authorized

**Critical precondition — code finding (credit: code assistant trace).** `limit_order_basis` does **not** enable maker entries. Live entries are unconditional taker/market: `func_trade_management.py:3469/3558` call `initialise_order_execution(...)` with no `limit_offset` → defaults `0.0` → `func_execution_calls.py:733` selects `"market"` → `place_market_order` (`:951`, `ordType="market"`). No `postOnly`/TIF exists anywhere in the Execution layer. `limit_order_basis` (`config_execution_api.py:276`) is wired only to capital-injection sizing (`func_trade_management.py:2900`) and two post-entry top-ups (`:3642`, `:3712`) — never to entry order type. **A maker conversion is therefore new code** threading `limit_offset`/`postOnly` through `initialise_order_execution → place_entry_with_stop`, and a **behavior/execution change** — not a config flip. (See §11: log the trap, fix the comment.)

**Expected benefit.** Fee component ~60% lower (VIP0 taker 0.05% → maker 0.02%; **confirm the account's actual fee tier** — rebates/levels vary) **plus** ceasing to pay the half-spread that currently appears as slippage on resting fills. Addresses cost component (1), not (2).

**The real MR-entry risks (refining the adverse-selection framing).** On a symmetric MR entry you rest where you'd be content to fill, so filling *on a further stretch* yields a **better** entry z — that is *not* classic adverse selection. The genuine risks are:
- **Non-fill selection bias [PRIMARY]:** resting orders miss the *fastest* reversions — likely the most profitable trades — so the *filled* population skews toward slow/non-reverting trades. Per-fill cost can improve while the trade population gets worse.
- **Legging risk [PRIMARY for a paired entry]:** one leg fills maker, the other doesn't → naked directional exposure until the second leg fills or is chased as taker (reintroducing taker cost + slippage on that leg, and contaminating the cost comparison).

**Design fork — OPERATOR DECISION:**
- **Pure-maker:** clean cost attribution; real legging/non-fill risk.
- **Maker-with-taker-timeout-fallback:** post-only rest, convert to market after N seconds if unfilled — bounds legging/miss but muddies attribution (some fills maker, some taker).

**Primary metrics (NOT fee savings alone):**
- per-leg maker-fill rate; both-legs-maker-filled rate vs legged rate;
- **realized-entry-z vs signal-z** (the selection-bias detector — if filled trades systematically show less favorable realized entry z, you are missing the good ones);
- time-to-both-legs-filled; realized total cost incl. any taker-fallback;
- the **`$/σ` and `edge_clears_costs` distribution of maker-filled trades vs the taker baseline** — the decisive comparison.

**Protocol:** run alone (one variable), per the single-variable intervention rule.

---

## 9. Frozen variables — what this review does NOT change

No notional change; no Advanced ML live; no router activation; no z exit-threshold change; no cointegration-window change; no `max_break_risk` change; no circuit-breaker change; no mean-reversion-escape; no `slope_max` change mid-window (pre-committed 0.020→0.030 applies only if the coint-stability filter is ever reactivated — does not reopen the premise). Process note: pause further refinement of the analytical machinery (inclusion-rule versions, new trackers) until N grows — at current N this is the "increasing sophistication faster than the dataset" failure mode the research paper warns against.

---

## 10. Operational dependency (independent of this review's outcome)

**Patch 6 item 5 — alert + clean halt after N consecutive emergency-flatten failures.** Confirmed needed twice (run 98 ~4m18s; run 128 77-min futile loop, manual stop). Backoff works but has no terminal state for sustained outages. Stated prerequisite before any move to live trading. Safe to implement *during* the collection window: it touches only the failure path during sustained outages (zero trades occur), so it cannot contaminate experiment data or alter normal execution. This is the obvious use of otherwise-idle collection-window engineering time.

---

## 11. Action items by owner

**Operator (decisions):**
- [x] §4 — **DECIDED: require both** (≥20 total AND ≥8 eligible, whichever is later); E4 kill-criterion added (>60% coint-failure over ≥10 closed, total-closed denominator).
- [ ] §8 — choose maker design fork (pure vs fallback) *if* Branch 2 is reached. *(Operator lean: fallback — legging risk on a paired entry is the worse hazard; accept muddier attribution. Deferred to if/when Branch 2.)*
- [x] §5 — **APPROVED verbatim**; anti-reframe clause ("must not be reframed into 'needs one more patch' without new evidence clearing this bar") retained as the load-bearing lock.

**Code assistant (code + data):**
- [ ] §7 — compute residual vs effective half-spread (+ secondary impact proxy), tag pairs by structure; confirm `liquidity_checks.csv` spread availability first.
- [x] §11 — `limit_order_basis` trap logged in DECISION_LOG.md (Section-8A class) and comment corrected at `config_execution_api.py:276` (verified comment-only; no behavior change; run 130 not restarted).
- [ ] §10 — implement Patch 6 item 5.
- [ ] (if Branch 2b authorized) implement maker entry path with the agreed design.

**Strategist:**
- [ ] Fill this template at the §4 trigger.
- [ ] Produce the branch-specific experiment spec once the branch is known.

---

*Template version: exp_beta_aware_sizing_v1 structural-review template v1.2 (DRAFT, pre-trigger; §4 gate locked + E4 added; §5 negative-bar approved verbatim; §6/§7 updated post Query 1+2 — Branch-1/Item-14 downgraded, §7 cost diagnostic promoted to critical path, mean-shift recorded as leading-by-elimination/attribution-unverified, all N=2-clean directional).*
*Drafted: 2026-05-29 at T3. To be executed at the §4 review trigger.*
*Inputs: per-run audit (runs 125–129, T1–T3); structural_review_exp_coint_stability_v1.md; project_experiment_state.md; OKXSTATBOT_CURRENT_STATE/ROADMAP/DECISION_LOG; code trace (taker confirmation + limit_order_basis) from code assistant, 2026-05-29.*
