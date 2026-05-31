# Structural Review — exp_beta_aware_sizing_v1
## β-Aware Sizing: H1 Resolution, E4 Halt, and the Cost-Clearance Finding

**Status:** **FINAL (2026-05-31).** exp_beta_aware_sizing_v1 CLOSED via Branch A. Path: E4 mechanical halt at T15 → structural review v1.0 RESOLVED → v1.1 AMENDMENT (B1 v1 surfaced basis-mismatch question) → §9.5 basis-mismatch diagnostic RAN → verdict BASIS-AGREEMENT-WITH-T15-ASTERISK → Branch A firms with bounded artifact narrowed from 3/9 ceiling to 1/9 (T15 specifically) → experiment retired. Cost-clearance bottom-line antecedent met; mean-shift β-independent loss mechanism confirmed; H1 = clean success (settled); configuration finding (kline-only monitor stricter than orderbook-mid selector) recorded for future work. Next strategic direction is the operator's call; no further analysis turns warranted on this experiment.
**Window:** T1–T15 (runs 125–142), 2026-05-28 → 2026-05-31. β-aware sizing live throughout.
**Prior review:** structural_review_exp_coint_stability_v1.md (sizing-mismatch discovery → this experiment).
**§7 centerpiece artifact:** cost_diagnostic_post_T15_halt.md.
**Pre-committed criteria source:** structural-review template v1.4/v1.5 (§4 gate + E4 + T15 pre-commit; §5 negative bar; §6 mean-shift finding).

**Verdict structure (per operator Q2):** findings → decision tree with pre-committed triggers → recommended decision with the reasoning chain visible. Most of the "decision" is mechanical once the evidence is in hand (the pre-commits fire); the consequential calls (accept negative result; choose next direction; build the observation-mode instrument) are surfaced explicitly as operator decisions with my recommendation and reasoning shown, so disagreement can be placed at the right link.

---

## 0. One-paragraph synthesis

β-aware sizing is a **clean success on what it was built to fix** (H1): signal and position are aligned on every eligible trade, 5/5 sign-positive, β-sizing mechanically exact 15/15 across the full observed β range [0.378, 1.841]. But the experiment **halted at T15 on universe coint-fragility** (E4, mechanical, pre-committed cold at T13), and the cost diagnostic — the centerpiece analysis on whether the now-correctly-sized strategy clears costs — returns a verdict that is **AMBIGUOUS on the mechanism but robust on a key sub-finding: every cost-clearance in the eligible population — including the one realized win — sits within the cost-model's ±$0.06 noise band.** The strategy, correctly sized, does not *robustly demonstrate* capturable edge above the cost stack at $200 notional on this universe; the diagnostic cannot isolate why (edge inherently thin vs cost inherently high on a subset), and at the current cost-model precision (±$0.06 vs edges ~$0.10) it structurally cannot. This is the §5 pre-committed negative-result reading — fired not from a single clean diagnostic but from a convergent evidence stack (every-clearance-within-noise, mean-shift β-independent loss mechanism, eligible-population stall, the halt itself). **It is a finding, not a failure:** sizing was the prerequisite, sizing is solved, and the corrected strategy reveals that the binding constraint is edge-vs-cost on this universe at this notional — which the experiment was built to be able to discover.

---

## 1. Experiment-state block

```
Experiment group:        exp_beta_aware_sizing_v1
Window:                  T1–T15 (runs 125–142)
Sizing mode:             gross_normalized_beta (Option C); gross=$200; leg1=gross/(1+β), leg2=gross×β/(1+β)
Trades:                  15 closed.  $/σ-eligible: 5 (T2,T5,T6,T7,T8).  Coint-failures: 9.  Adverse-normal: 1 (T10)
β range observed:        [0.378, 1.841] — full coverage, both tails + middle
β-sizing fidelity:       15/15 exact to the cent; 0 fallback activations
Circuit breaker trips:   0 (structurally inert under max_session_trades=1 — see §8 note)
Cumulative PnL:          −$4.652.  Win rate: 1/15 = 6.7%.  Worst stretch: T10–T15, 6 losses, −$2.780
Halt:                    E4 fired at T15, 9/15 = 60.0%, mechanical (pre-committed T13)
Confidence:              H1 HIGH; cost-clearance finding MEDIUM (convergent, N-limited); halt-interpretation OPEN
```

---

## 2. H1 — β-aware sizing aligns signal and position: CLEAN SUCCESS

**Verdict: H1 CONFIRMED. HIGH confidence. Settled, not paused by the halt.**

The experiment's primary hypothesis — that threading β into sizing aligns the dollar position with the spread signal — is cleanly supported:

- **$/σ sign-flip rate: 0/5 = 0%** over the eligible population (T2 +$0.064, T5 +$0.017, T6 +$0.020, T7 +$0.094, T8 +$0.054/σ). Aggregate +$0.044/σ, positive.
- **β-sizing mechanically exact 15/15** to the cent, 0 fallback activations, across β ∈ [0.378, 1.841] — both the sub-unity and supra-unity extremes and the middle.
- The sizing-mismatch defect that motivated this experiment (β computed for the signal but never applied to the legs; the prior experiment's Verdict 10A) is **fixed and verified live.**

This is the foundation the rest of the review stands on: **the strategy is now being tested fairly.** Whatever the cost-clearance finding shows, it is not contaminated by a sizing artifact — that confound is closed. The halt and the negative-result reading are about the *strategy's edge on this universe*, not about sizing. H1 should be recorded as a settled success and carried forward to any future work unchanged.

---

## 3. The E4 halt — universe coint-fragility

**Verdict: E4 fired mechanically at T15, exactly as pre-committed. Continue-collection is over; the halt is the transition to this review.**

### 3.1 What fired
Coint-failure rate reached **9/15 = 60.0%**, the pre-committed halt line, on a trajectory of **37.5 → 44.4 → 50 → 53.8 → 57.1 → 60.0%** over the last six closed trades, with a **five-deep coint-failure run (T11–T15)** — ~3% probability under a 50% base rate, i.e. no longer plausibly small-window variance. The halt decision was made cold at T13 (template v1.4 §4), with the reading of T14–T15 fixed before those trades closed. It triggered without in-the-moment deliberation. **This is the discipline functioning at the hardest point — the unwelcome direction.**

### 3.2 Calibration held against a false halt
The halt line was deliberately set at >60%, *above* the historical band [36.8, 55.6], precisely so that ordinary variance around the high baseline would not trigger a false halt. T15 confirms the calibration was right: the rate did not merely touch the band edge, it climbed past the entire historical band on a five-deep run. Had the line been set at the baseline, this would have fired several trades earlier on what might have been variance. It fired instead on a signal that is now statistically distinguishable from noise.

### 3.3 Halt interpretation — TEMPORAL vs STRUCTURAL fragility (OPEN, with a methodological bind)
Two readings of *why* the universe became fragile:
- **Reading 1 (temporal):** the universe entered a higher-coint-failure regime around T9; the fragility is a market-period property that may pass. Lever: detect-and-gate the fragile regime (connects to the RISK_OFF-entry vector, §6.3).
- **Reading 2 (structural):** the universe was always this fragile and the early favorable stretch (T5–T8, the eligible cluster, the one win) was the variance. Lever: the strategy class / hold horizon / universe is wrong, not the timing.

**Standing read leans Reading 2**, on the eligible-stall evidence: 5 eligibles in T2–T8 (~63% of that window), **0 in T9–T15 (7 consecutive non-eligible).** If fragility were transient, eligibility should return as the regime passes; the stall instead looks like the universe revealing its true coint-failure rate with the early cluster as the lucky window.

**The methodological bind (load-bearing, must be stated honestly):** the discriminator chosen cold — *eligible-return rate after halt* — requires data the halt stops producing. You cannot measure whether eligibility returns without continuing to sample the universe, and the halt exists precisely because sampling-by-trading is costing money on a fragile universe. The discriminator therefore has to take a form that survives the halt: a **no-notional observation mode** — record the coint-failure rate from the live monitoring loop without placing trades. The marking-fidelity problem that killed query-3 does **not** apply here, because no PnL is being computed — only whether the cointegration test fails post-entry-candidate. This is named as *the form the discriminator must take*, not as an authorized build; see §7 (decision tree) and §9 (operator decisions).

---

## 4. Mean-shift — the dominant loss mechanism (ESTABLISHED FINDING)

**Verdict: FINDING. The dominant loss mode is post-entry, β-independent, entry-unpredictable mean-shift. Promoted from hypothesis at T13; locked at T14.**

### 4.1 The finding
The cointegrating relationship's mean drifts mid-hold while β stays stable, so z-reversion no longer corresponds to dollar-reversion. The position cannot track the spread to profit even as z returns to zero.

- **6/9 clean coint-failures DECOUPLED** (dollars ≤0 while z reverted favorably): T3b, T4b, T9, T11, T13, T14. (3/9 TRACKED-THEN-BROKE: T1b thin-pair, T12 borderline, T15.)
- **Demonstrated across the full β range** β ∈ {0.378, 0.456, 0.476, 0.561, 0.667, 1.495, 1.841} — both tails and the middle. T13 at β=1.841 (supra-unity) and T10/T11 near β=0.45 (sub-unity) bracket it. **The objection that decoupling might be a residual sizing effect at the β extremes is empirically dead** — the mechanism appears at every β level.
- **β-drift excluded at every level** (rolling β stable on every decomposed hold; Query 2 finding, re-confirmed across the window).
- **Entry-unpredictable** — every DECOUPLED case entered with benign coint slope (T14: −3.2e-5, essentially flat). The refuted-lever guardrail holds across the entire window.

### 4.2 Consequence for the lever set (definitive, not provisional)
Because mean-shift is real AND β-independent AND entry-unpredictable AND not a sizing artifact, the surviving levers for the dominant loss mode are **only**:
- **post-entry** — exit faster on dollar-divergence (bail before watch-timeout when dollars are red while z reverts); a tighter hold-time cap;
- **structural** — regime/universe restriction (don't trade pairs/regimes prone to it).

It **definitively excludes** any entry-gate cointegration metric (slope or level) and dynamic β re-hedging. This closes — does not merely deprioritize — those directions, and it explains *why* the slope filter died (exp_coint_stability Verdict 10B). Any future work starts from this finding rather than re-litigating it.

### 4.3 Wrinkle surfaced by B1 v1 — basis-mismatch may inflate the count (open, gates §9 Branch A)

B1 v1's baseline analysis (`docs/audits/b1_baseline_analysis_2026-05-31.md`) revealed that the live coint-monitor (`basis=kline_only`, `window=60`) reads **`health=valid` zero times across 732 samples** spanning 18 runs. The entry-discovery gate (`basis=orderbook_mid`) passes pairs as `valid` and they enter the monitor with `entry_health=valid` — but the monitor itself, on the same pair under a different basis, never returns to the strictest band. **The two cointegration tests are measuring different things.**

This raises a question the mean-shift finding above didn't have to confront: **is the dominant loss mechanism a real economic phenomenon (relationships genuinely drift mid-hold), or is it partly a basis-mismatch artifact (the monitor is testing under a basis the pair was never selected to satisfy)?**

The 6/9 clean DECOUPLED cases are robust to this concern — they are documented by **dollar-PnL decoupling** (positions genuinely red while z reverts), which is independent of which basis flags the coint-test. That evidence is real economic drift, not measurement.

The 3/9 TRACKED-THEN-BROKE cases (T1b, T12, T15) are **not** robust to this concern — they exited via `cointegration_watch_timeout` or `cointegration_lost`, which is the monitor's verdict under the kline-only basis. If the monitor's basis disagrees with the orderbook-mid basis on those pairs at those times, some of those exits may be procedurally triggered by basis-mismatch rather than by genuine relationship breakdown. T15 in particular tracked the mean to z=0.09 with positive in-zone pnl (+$0.102) before the monitor's broken-state fired — exactly the shape a basis-mismatch artifact would produce.

**Consequence: the mean-shift finding stands as ESTABLISHED for the dollar-decoupling component (6/9), but the magnitude of the universe-fragility reading (9/15 = 60% coint-failure rate, which triggered the E4 halt) is partly contingent on a basis-mismatch question that has not been answered.** The basis-mismatch diagnostic (§9.5 below) is the test that resolves whether the coint-failure rate is the universe's economic property or partly an instrument inconsistency between the selector and the monitor. **Branch A's acceptance is gated on that diagnostic** — the §5 bar's bottom-line antecedent ("no capturable edge at current notional and universe") implicitly assumes the universe was tested with consistent instruments; if it wasn't, the antecedent is conditional, not settled.

---

## 5. The cost diagnostic — does the correctly-sized strategy clear costs? (§7 CENTERPIECE)

**Verdict: AMBIGUOUS-at-N on the mechanism; ROBUST on the bottom line — 0/6 clear cost.**

### 5.1 The reframe that matters most

The pre-committed verdict is AMBIGUOUS-at-N (the three-cost-assumption robustness test cannot isolate edge-too-thin from cost-too-high at N=6). **But AMBIGUOUS on the mechanism does not exhaust what the diagnostic robustly says.** The decisive observation under the error-bar test:

> **Every cost-clearance in the eligible population is within the cost-model's ±$0.06 noise band.** At point estimate, 3/6 clear: T7 (+$0.015), T8 (+$0.010), T15 (+$0.004) — all smaller than half the per-trade error bar; all three sign-flip negative under adverse cost. **The single realized win (T7, the deepest entry) is within noise.** Separately, 2/6 (T2, T6) ROBUST-FAIL even under generous cost — the cost-too-high sub-mode is established at N=2.

Read strictly: the strong reframe — *"even under generous cost, nothing clears"* — is NOT what the data shows (4/6 do clear under generous, but all four sit within the noise band by definition — they are the sign-flip cluster). The honest reframe, which the data does support: ***"every clearance sits within the cost-model's measurement uncertainty; nothing clears robustly to that uncertainty."*** Softer in form but pointing the same direction — **the strategy, correctly sized, does not *robustly demonstrate* capturable edge above the cost stack at $200 notional on this universe**, where "robustly" means surviving the ±$0.06 cost-model error bar. The diagnostic is genuinely ambiguous about *why* (edge inherently thin, or cost inherently high on the 4-trade sign-flip cluster); it is also informative about *cost-model precision* — at ±$0.06 against edges of ~$0.10, the model is coarser than the signal, and that is what makes the AMBIGUOUS verdict *structural* rather than a property of N alone.

**The review's headline is therefore:** *"the diagnostic robustly establishes that at the current cost-model precision the strategy cannot demonstrate cost-clearance at $200 notional on this universe; it is inconclusive only on the mechanism (edge vs cost)."* The §5 bar's bottom-line antecedent (no demonstrated capturable edge above costs at current notional) is met **from the diagnostic AS CORROBORATED by the convergent stack** — not from the diagnostic standing alone.

### 5.2 What the diagnostic robustly establishes (survives the ±$0.06 error bar)
1. **0/6 ROBUST-PASS.** No trade clears cost under the adverse cost assumption (cost + $0.06). Under generous (cost − $0.06), 4/6 do clear — but those clearances all sit within the ±$0.06 noise band by definition (they are the sign-flip cluster: T5, T7, T8, T15). **The diagnostic robustly establishes that, at this cost-model precision, no trade in the eligible population demonstrates cost-clearance survivably to the measurement uncertainty itself.**
2. **The "deep-entry-only viable subset" is NOT supported.** T7 (deepest entry, only win) has a point-estimate gap of only +$0.015 — smaller than half the ±$0.06 error band — and sign-flips negative under adverse cost. The STRUCTURAL-with-VIABLE-SUBSET branch's most promising candidate does not survive the robustness test. The one win was within the cost-model's noise band.
3. **Two clean cost-driven failures (T2, T6) ROBUST-FAIL even under generous cost.** T2 ($0.251 cost, recon-FAIL, KSM thin-leg — parallels the prior experiment's T10/FIL-ICP) and T6 ($0.194 cost on liquid SOL/AVAX, clean recon — the harder case, fully attributable and just structurally high). These are the only robust signals in the diagnostic, and they contribute a cost-too-high sub-mode at N=2 directional.

### 5.3 What it cannot isolate (the genuine ambiguity)
Two failure modes co-exist and cannot be separated at N=6:
- **Edge inherently thin** — the T5/T7/T8/T15 sign-flip cluster: edge ≈ cost within ±$0.10, could be thin edge OR cost mismeasurement.
- **Cost inherently high on a subset** — T2/T6 robust-fail: could be universe-restrictable (drop thin-leg pairs, profile-tag anomalous-cost liquid pairs), but at N=2 that is a directional hypothesis, not a finding.

The cost model's ±$0.06 per-trade error is **approximately the size of the edges being measured** (only T7's +$0.230 is materially larger). This is the Item-12 finding rendered concrete: an instrument coarser than the signal cannot resolve the mechanism by itself. AMBIGUOUS at N=6 with this error bar is what the math predicts — and is informative about the *cost-model precision* any future resolution would require, not just about this experiment.

### 5.4 T15 as the edge-too-thin anchor exhibit (n=1, corroborating)
T15 is the cleanest single-trade illustration of the edge-too-thin thesis in the experiment: the relationship reverted to the mean (z=0.09 at 5min) with the position **positive** (+$0.102) — the mechanism worked, dollars tracked — but +$0.102 was below cost-clearance ($0.098–$0.14), and then it broke. Every confound removed: β exact, mean tracked, costs textbook, no entry error. It is the §5 thesis in a single trade. **Weighted as one trade (and one coint-failure), it corroborates the "operates at the edge of measurement noise" reading; it does not carry the verdict.** Anchor exhibit, parallel to T10 anchoring the cost-overrun mode in the prior review.

---

## 6. Convergent evidence stack (what AMBIGUOUS routes to)

Per the pre-commit, AMBIGUOUS does **not** route to "collect more data" (the 20-trade gate is superseded by the halt; there is no eligible-trade stream without un-halting). It routes to *the convergent evidence carrying the weight the diagnostic could not isolate.* The stack:

1. **H1 = CLEAN SUCCESS** (§2) — sizing settled; the finding is not a sizing artifact.
2. **Every cost-clearance within the noise band** (§5) — 3/6 clear at point estimate but all within ±$0.06; the win itself (T7 +$0.015) sign-flips under adverse; 0/6 ROBUST-PASS. The diagnostic cannot demonstrate cost-clearance at this cost-model precision.
3. **Mean-shift β-independent, entry-unpredictable** (§4) — the dominant loss mechanism has only post-entry/structural levers.
4. **Eligible stall** — 5 in T2–T8, 0 in T9–T15; the instrument that would generate more diagnostic data is the one that stopped producing.
5. **E4 halt on genuine trajectory** (§3) — five-deep coint-failure run, ~3% under base rate, pre-committed trigger fired cold.
6. **T15 anchor exhibit** (§5.4) — mechanism worked, edge below cost, single clean trade.

**Reading from the stack:** the strategy as built does not show robust capturable edge above the cost stack at $200 notional on this universe. The cost diagnostic alone cannot isolate why, but the bottom line (0/6 clear) is robust, and every surrounding line of evidence is convergent. This is the §5 negative-result reading, sourced from the stack.

---

## 7. Decision tree — pre-committed triggers and where each leads

The committed criteria are unchanged; the evidence now selects among them.

**§5 negative-result bar — antecedent status:** the bar fires if "the cost diagnostic shows the cost gap is structural AND no cost lever plausibly closes it at $200 notional." The diagnostic returned AMBIGUOUS-on-mechanism but ROBUST 0/6-don't-clear. The honest mapping: **the bar's bottom-line antecedent (no capturable edge at current notional and universe) is met from the convergent stack; the bar's mechanism-clause (is it cost or edge) is not isolated.** This means the negative-result *conclusion* is supported, but the *remedy* it would otherwise point to (fix cost vs accept) is not yet determined — which is exactly what the branches below resolve.

**Branch A — Accept the negative result (as-is, $200 notional, this universe).**
Pre-committed conclusion: *the strategy does not have a capturable edge at the current notional and universe.* Supported by the convergent stack (not by the diagnostic standing alone — see §5.1 reframe). This is a clean finding: sizing solved, edge insufficient or unresolvable-at-this-precision on this universe, dominant loss mode (mean-shift) entry-unpredictable. **Next move: stop optimizing this configuration.** Not a sizing or exit refinement — mean-shift forecloses entry levers; and the within-noise clearance pattern means a better exit doesn't have a *robust* edge to capture (the one EXIT-TOO-LATE signature, T8, is N=1 in this window). Either redirect to a different universe/horizon/strategy-class, or conclude the line.

**Branch B — Resolve the mechanism before deciding (the no-notional observation mode + a precision question).**
If you are not willing to accept the negative result without isolating *why* (edge-thin vs cost-high-on-subset), two things are needed, and both are buildable without un-halting:
- **(B1) No-notional observation mode** — sample the universe's coint-failure rate from the live monitoring loop without trading. This resolves the §3.3 temporal-vs-structural fragility question (does eligibility return?) *and* the marking-fidelity problem doesn't apply (no PnL computed). It is the only way to get the eligible-return discriminator the halt otherwise stops producing.
- **(B2) A precision question on cost** — the mechanism (edge-thin vs cost-high) is unresolvable at the current ±$0.06 cost-model error. Isolating it requires either a more precise cost model (per-fill attribution) or more eligible trades at a trustworthy cost axis — but more eligible trades require un-halting, and the halt says the universe is too fragile to sample by trading. So B2 is gated on B1 (is there a less-fragile sub-universe worth sampling?) or on a cost-model precision upgrade.

**Branch C — Universe/regime restriction (the SUBSET-VIABLE residue + RISK_OFF vector).**
The diagnostic did *not* support the deep-entry viable subset (T7 not robust). But two restriction hypotheses survive as directional (not findings):
- **Cost-driven exclusion** — T2/T6 cost-too-high suggests dropping thin-leg pairs (KSM-class) and profile-tagging anomalous-cost liquid pairs (the graveyarding on measured footing). N=2; directional.
- **RISK_OFF-entry gating** — the entry-side vector (§6.3 of CURRENT_STATE): 2/2 RISK_OFF entries → coint-failure (T9, T12), the *only* candidate entry-side lever surviving the refuted-lever guardrail (regime ≠ coint metric; signal already computed in shadow). **But: 2/2 against a ~50% base rate is base-rate-indistinguishable** — not yet a finding. The no-notional observation mode (B1) is the instrument that would test it at N (does coint-failure rate condition on entry regime?).

**The branches relate:** Branch A is the honest terminus if you accept the convergent stack. Branches B/C are warranted only if you judge isolating the mechanism worth a small build (the observation mode), and they share that instrument. Notional scaling is **not** a branch — edge and cost scale together; 0/6-robust-fail at $200 does not become viable at $400.

---

## 8. Operational and methodological notes (carried, not blocking)

- **Circuit-breaker structural inertness.** The consecutive-loss breaker (limit 3, session mode) did not fire across a 6-loss −$2.78 streak because `max_session_trades=1` resets the count each run — every trade is its own session, so consecutive-loss counting never accumulates. This is *working as configured* and the experiment-level E4 stop did the job the breaker structurally cannot. **But it is a latent gap: if this or any strategy moves toward multi-trade sessions or live scale-up, the breaker as configured would not have caught this streak.** Record for the scale-up conversation; not a mid-experiment change (frozen, and E4 is the right instrument here).
- **Patch 6 item 5 (alert/kill-switch after N flatten failures)** remains the stated prerequisite before any live trading, unaffected by this review.
- **New deferred items from the window:** recently-failed-pair cooldown (T11 re-entered T10's losing pair 35min later); the T10 adverse-normal-exit bucket (n=1, "normal" label may mask a stop-tier — diagnose if it recurs).
- **Cost-model precision as a meta-finding.** The diagnostic's AMBIGUOUS verdict is itself informative: ±$0.06 per-trade cost error against ~$0.10 edges means *no* amount of trades at the current cost-model precision resolves the mechanism cleanly. Any future attempt to isolate edge-vs-cost needs a more precise cost instrument first.

---

## 9. Recommended decision (reasoning chain visible — the call is the operator's)

**My recommendation: Branch A — accept the negative result for this configuration — with B1 (no-notional observation mode) as the one worthwhile follow-on, and explicitly NOT B2/C as trading experiments.**

The reasoning chain, so you can disagree at the right link:

1. **H1 is solved (HIGH confidence).** → The strategy is being tested fairly; the finding is real, not a sizing artifact. *[Disagree here only if you doubt the 15/15 β-fidelity or the 5/5 sign-positive — I don't think either is contestable.]*
2. **Every cost-clearance in the eligible population sits within the cost-model's ±$0.06 noise band, including the one realized win (T7 +$0.015 point → sign-flips −$0.045 under adverse).** → At $200 notional on this universe, no trade demonstrates cost-clearance survivably to the measurement uncertainty in the cost model itself. *[Disagree here if you think the within-noise clearances should be counted as real until proven otherwise — but note 2/6 ROBUST-FAIL even under generous (cost-too-high established sub-mode at N=2), all three analytical slices return AMBIGUOUS, and step 6 below ties this finding to the corroborating convergent stack rather than asking the diagnostic to carry the weight alone.]*
3. **The dominant loss mode (mean-shift) is entry-unpredictable and has no entry lever (FINDING).** → You cannot fix the coint-failures at entry; the only handles are post-entry exit-speed or structural restriction. *[Disagree here only with contrary evidence on entry-predictability — the window shows none across 9 coint-failures.]*
4. **The two surviving remedies (exit-speed, universe restriction) are weakened — though not strictly foreclosed — by step 2.** → A better exit *could* in principle capture more of the path between entry and the mean than `pnl_at_mean` measures (T8's prior EXIT-TOO-LATE finding: MFE +$0.282 at z=−0.60 vs in-zone $0.169). But that pattern is N=1 in this window (T8 only) and not strong enough to plausibly rescue the 4-trade within-noise cluster at the current cost-model precision. A universe restriction (Branch C) rests on N=2 directional hypotheses (T2/T6 cost-too-high; T9/T12 RISK_OFF) and a base-rate-indistinguishable RISK_OFF vector. Neither lever is strong enough to justify resuming *trading* on this configuration — which would also require un-halting a universe just halted as too coint-fragile to sample by trading. *[This is a key link — see step 5.]*
5. **The mechanism (edge-thin vs cost-high) is unresolvable at current cost-model precision (±$0.06 ≈ edge size).** → Resuming trading to gather more eligible data would (a) require un-halting a universe the halt just judged too fragile, and (b) still not resolve the mechanism without a cost-precision upgrade. So *more trading is the wrong next step regardless of branch.*
6. **Therefore:** accept the negative result for this configuration (Branch A). The honest finding is *"β-aware sizing is correct and settled; the strategy does not show capturable edge above costs at $200 notional on this universe; the dominant loss mode is entry-unpredictable mean-shift; the universe is coint-fragile (E4 halt)."* 
7. **The one worthwhile follow-on is B1 (no-notional observation mode)** — because it is the *only* instrument that resolves the open temporal-vs-structural fragility question (does eligibility return? is the universe always this fragile?) *without trading*, and it would also test the RISK_OFF vector at N. It is cheap, it touches nothing live (read-only on the monitoring loop, no PnL, no orders), and it answers the question that decides whether *any* future universe/horizon is worth pursuing. **This is the operator decision I'd flag as genuinely worth making** — not a trading experiment, an observation instrument.

**Operator decisions (resolved 2026-05-31; AMENDED post-B1-v1 baseline analysis):**
- [x] **Accept the negative result for this configuration?** → **DECIDED: YES (Branch A FIRMS).** Diagnostic ran 2026-05-31 (`docs/audits/basis_mismatch_diagnostic_2026-05-31.md`); returned **BASIS-AGREEMENT-WITH-T15-ASTERISK** — 2/3 TRACKED-THEN-BROKE trades (T1, T12) show genuine kline-only p-value degradation (T1: 0.106→0.918 ×8.6; T12: 0.141→0.305 crossed broken threshold; dollar evidence corroborates with heavy losses), routing to BASIS-AGREEMENT logic; 1/3 (T15) shows threshold-hovering (p stayed in watch band 0.116→0.142; suspect basis-mismatch artifact). The cohort-wide artifact hypothesis is rejected; the bounded artifact narrows from the pre-commit's 3/9 ceiling to 1/9 specifically (T15). The cost-clearance bottom-line antecedent is unchanged (T15 reclassification doesn't move 0/6 ROBUST-PASS). The universe-fragility magnitude moves modestly: if T15 is reclassified, coint-failure rate 60.0% → 53.3% (E4 halt would have been marginal-not-mechanical), but the deeper Branch A driver (edge does not clear costs at $200 notional) is unaffected. **exp_beta_aware_sizing_v1 closed via Branch A; configuration finding (kline-only monitor stricter than orderbook-mid selector) recorded for future work but does not reopen.**
- [x] **Build the no-notional observation mode (B1)?** → **DECIDED: YES (built and landed 2026-05-31).** Tool: `tools/observation_mode/coint_fragility_sampler.py`. Baseline analysis: `docs/audits/b1_baseline_analysis_2026-05-31.md`. Findings: (a) RISK_OFF vector corroborated at N=147 (23.1% vs RANGE 16.5% broken_rate); (b) temporal arc leans STRUCTURAL but does not foreclose Reading 1; (c) `health=valid never observed in 732 samples` — the basis-mismatch finding that gates Branch A above.
- [x] **Pursue B2/C as trading experiments now?** → **DECIDED: NO.** Unchanged. Locked against drift; reopening requires new evidence clearing the §5 bar.
- [x] **Run basis-mismatch diagnostic (§9.5)?** → **DECIDED: YES — RAN 2026-05-31.** Verdict: BASIS-AGREEMENT-WITH-T15-ASTERISK. Branch A firms; bounded artifact narrowed to 1/9 (T15) from the pre-commit's 3/9 ceiling. See `docs/audits/basis_mismatch_diagnostic_2026-05-31.md`.
- [ ] **Run B1 v1.1 (cross-run per-pair aggregation)?** → **RECOMMEND YES.** Tests whether RISK_OFF elevation is regime-causal or pair-selection-driven. Now informational rather than decision-gating (Branch A is decided), but still useful for any future configuration choice. Data exists in B1 v1 sample CSVs; one aggregation script.
- [x] **Next strategic direction** → **DEFERRED to operator.** Branch A is now decided; the experiment is closed. Direction choice (different universe / different hold horizon / different strategy class / pause indefinitely) is the operator's call. Informed by: H1 = clean success (settled); cost-clearance bottom-line robust at $200 notional; mean-shift β-independent and entry-unpredictable; RISK_OFF vector N=147 directional-corroborated; basis-disagreement-config-finding (kline vs orderbook-mid in the bot's current configuration). No specific direction recommended without further evidence; the observation mode (B1 v1) and the diagnostics together have closed the open-question space that authorized further analysis turns. Future work, if any, starts from these findings rather than re-litigating.

---

## 9.5 Basis-mismatch diagnostic — pre-committed verdicts cold (added 2026-05-31 post-B1-v1)

**Question:** is the universe's coint-failure rate (9/15 = 60% over the closed trades, broken_rate = 17.6% over 732 monitor samples) a property of the universe's economic cointegration, or is it partly an artifact of the bot's selector and monitor using different cointegration tests (orderbook-mid basis at entry-discovery; kline-only basis post-entry; bases disagree on which pairs read `valid` — see §4.3)?

**Why this gates Branch A:** the §5 bar's bottom-line antecedent ("no capturable edge at current notional and universe") implicitly assumes the universe was tested with consistent instruments. B1 v1 surfaced evidence the instruments may have been inconsistent. If they were, the universe-fragility component of the negative result is contingent, not settled. The diagnostic resolves this; the direction decision is not safe to make until it does.

**Diagnostic stratification (sharpening, locked before run):** the basis-mismatch question is **only live for the 3 TRACKED-THEN-BROKE trades (T1b run 125, T12 run 139, T15 run 142)**. The 6 DECOUPLED cases are basis-independent by construction — dollar-PnL decoupling is evidence that holds no matter what the coint-test basis says, because it's measured in dollars, not in the test. The diagnostic therefore does NOT ask "do the bases disagree across all coint-failures" (which would dilute the signal). It asks, specifically: **on the 3 TRACKED-THEN-BROKE trades, was the kline-only monitor's exit-triggering verdict (broken / watch-timeout) firing on a moment when the relationship had genuinely degraded under both bases, OR was it firing on a moment when the kline-only basis was just stricter than orderbook-mid would have been on the same underlying truth?** n=3 is thin in absolute terms, but it's the entire population the question applies to — that's the right n, not a small n.

**Pre-committed verdicts (locked cold before the diagnostic is built or run):**

> **BASIS-AGREEMENT** — on all 3 TRACKED-THEN-BROKE trades, the exit-triggering monitor reading reflects a kline-only p-value trajectory that genuinely degraded through the hold (entry-state was tight; exit-state was meaningfully looser; the climb is monotonic-or-near, not threshold-hovering). Under those conditions, even though orderbook-mid was not re-tested post-entry, the kline-only degradation pattern is what orderbook-mid would also flag if it had been re-tested. The artifact hypothesis is **dead** — the monitor's exits on T1b/T12/T15 were tracking real relationship change, not just being stricter than the selector. The 6/9 DECOUPLED were always economic; the 3/9 TRACKED-THEN-BROKE were late breakdowns. **Branch A FIRMS cleanly.** The universe-fragility component of the negative result is robust; mean-shift is economic; the §5 bar's antecedent is met without the basis caveat. Operator-decision row for Branch A flips from `[~] PENDING` to `[x] DECIDED YES`.

> **BASIS-DISAGREEMENT-SUBSTANTIAL** — on the 3 TRACKED-THEN-BROKE trades, the exit-triggering monitor reading fired without meaningful p-value trajectory change through the hold (entry-state and exit-state are similar; the monitor's threshold mechanics fired on a relationship that didn't materially degrade). The kline-only basis would call those moments `broken`/`watch`; orderbook-mid would have called the same moments `valid`. Those exits were procedurally manufactured by basis-mismatch, not by relationship breakdown. **Branch A is PREMATURE on the universe-fragility leg.** Next move: **basis-aligned retest** — re-run small N with monitor and selector under the same basis. Operator-decision row for Branch A flips from `[~] PENDING` to `[ ] NO — re-test under aligned bases instead.`
> 
> **Bounded-reopening caveat (load-bearing):** the BASIS-DISAGREEMENT verdict reopens Branch A only on the *universe-fragility leg*. Even if all 3 TRACKED-THEN-BROKE exits are reclassified as artifacts (3 of 15 trades), the **6 DECOUPLED cases are still real dollar-decoupling** (basis-independent), the **0/6 cost-clearance finding is still robust** (every clearance within the ±$0.06 noise band; T7 the win within noise; sourced from the cost diagnostic which doesn't touch the basis question), and the **E4 halt was procedurally correct** under the configuration that ran (the halt fired on the live monitor's verdict, which IS the configured trigger — the question is whether the configuration was right, not whether the halt was right under it). So the BASIS-DISAGREEMENT verdict says: *re-test under aligned bases* — but the basis-aligned retest will still face the 0/6-don't-clear wall unless realignment also moves the population of trades that reach the eligible bucket. The reopening is real but bounded: it fixes at most 3/9 exit-timing artifacts, NOT the cost-clearance bottom line. A basis-aligned retest that produces eligible-trade clearance above costs (robustly) would overturn the original negative result; a retest that does not, would re-confirm it with the artifact hypothesis closed out.

> **AMBIGUOUS-INSUFFICIENT-PAIRED-DATA** — the logged data doesn't support a clean determination of whether the p-value trajectory on the 3 trades reflects genuine degradation or threshold-hovering (e.g., monitor sampling cadence is too coarse, entry-time monitor data isn't reconstructable, or the n=3 trades produce inconsistent readings without enough samples to discriminate). The diagnostic does not isolate. **Brace for this outcome:** the orderbook-mid basis was not re-evaluated post-entry in the original runs, so the counterfactual "what would the selector have said at the monitor's exit moment" cannot be directly logged — the diagnostic must work from p-value trajectory shape alone, and on n=3 trades with variable hold-lengths, that may not produce a clean read. **Default routing:** the 6/9 DECOUPLED cases remain robust economic evidence; the 3/9 TRACKED-THEN-BROKE remain ambiguous; the §5 bar's antecedent is met by the convergent stack with the open caveat recorded. **Branch A holds at "lean accept" with the basis-mismatch question explicitly carried forward** — the operator can choose to (a) accept the negative result with the caveat in the record, or (b) commission a basis-mismatch resolution effort (re-run coint-test under both bases on historical data; or B1 v2 with both bases logged side-by-side post-entry, requiring a small bot change). The honest framing: the convergent stack still points one way, but one of the planks under it has a question mark the data can't remove from logs alone.

**Anti-rationalization lock (recorded with the operator's own self-flag):** the basis-mismatch finding is being surfaced as a reopen-question, but the dollar-DECOUPLED evidence already establishes that the dominant loss mode has a real economic component. The diagnostic is being run to **answer the question, not vindicate a hope.** If BASIS-AGREEMENT fires, Branch A firms — and that must be written as cleanly as if BASIS-DISAGREEMENT-SUBSTANTIAL had fired. The discipline is: pre-commit the verdicts now, accept what the diagnostic returns, do not relitigate the verdict after the fact. Same posture as the cost diagnostic, the E4 halt pre-commit, and the halt-interpretation pre-load.

**Sequencing:** the diagnostic is next-work-after-this-amendment. B1 v1.1 (cross-run per-pair aggregation) pairs naturally — it tests whether RISK_OFF elevation is regime-causal or pair-selection-driven, which is a parallel mechanism question. Both are read-only analyses on existing logs; neither requires bot changes; both can be done in the same forward sweep.

---

## 9.5 (RESOLVED) — Basis-mismatch diagnostic verdict (2026-05-31)

**Verdict: BASIS-AGREEMENT-WITH-T15-ASTERISK.** Diagnostic tool: `tools/observation_mode/basis_mismatch_diagnostic.py`. Full diagnostic: `docs/audits/basis_mismatch_diagnostic_2026-05-31.md`.

**Per-trade results (the question is live for these 3 only):**

| Trade | Run | Pair | p_entry → p_exit | p_max | Classification |
|---|---|---|---|---|---|
| **T1** | 125 | JUP/YGG | **0.1064 → 0.9178 (×8.6)** | 0.9178 | **REAL_DEGRADATION** (deep into broken band) |
| **T12** | 139 | ARB/OP | **0.1408 → 0.3050 (×2.2)** | 0.3050 | **REAL_DEGRADATION** (crossed broken threshold 0.20) |
| **T15** | 142 | SOL/LINK | **0.1163 → 0.1420 (×1.2)** | 0.1679 | **THRESHOLD_HOVERING** (stayed in watch band entire hold) |

T1 and T12 show real kline-only p-value degradation — the test fired its exit on a relationship that meaningfully degraded through the hold (T1 dramatically; T12 narrowly but unambiguously crossed the broken threshold). The per-tick disagreement with orderbook-mid (kline-stricter at every tick) reflects orderbook-mid being structurally less responsive (lagged/lenient under its basis), not kline-only being wrong. Dollar evidence corroborates: T1 lost −$0.96 (heavy), T12 lost −$0.84 (heavy) — heavy losses consistent with real economic decoupling, not artifact exits on still-tracking relationships.

T15 shows the threshold-hovering pattern the §9.5 BASIS-DISAGREEMENT verdict described: p stayed in watch band (0.116–0.168, never crossed 0.20), the exit was `cointegration_watch_timeout` (accumulated-time-in-watch), the position was tracking the spread mid-hold (pnl +$0.102 at z=0.09), and the net loss at exit was small (−$0.21). T15's coint-failure designation is plausibly basis-mismatch artifact.

**Mixed outcome — not the binary the pre-commit anticipated.** 2/3 = supermajority real-degradation routes the verdict to BASIS-AGREEMENT logic with the bounded artifact narrowed from 3/9 (the pre-commit's anticipated ceiling) to **1/9 specifically (T15)**. The bounded reopening shrinks; Branch A firms; the cost-clearance bottom-line is independent and unchanged.

**What changes vs the v1.0 review verdict:** essentially nothing on the substantive conclusion — Branch A still firms, the cost-clearance finding still holds, the mean-shift finding still holds (6/9 DECOUPLED unchanged; T1/T12 confirmed real coint-failures). **What's added is a configuration finding** — the bot's kline-only monitor is structurally stricter than its orderbook-mid selector; on real degradation the monitor catches it earlier than the selector would (correct call); on marginal-not-degrading relationships the monitor can fire on threshold mechanics (T15-pattern artifact). This is a known property of the configuration to be addressed if any future experiment uses the same monitoring setup, but it does not change Branch A's acceptance.

**The anti-rationalization lock held.** The pre-commit anticipated three binary verdicts; the data delivered a mixed shape. I am routing to AGREEMENT-firming-Branch-A and explicitly naming the alternative reading available ("treat the mixed verdict as effectively AMBIGUOUS, hold Branch A at lean-accept with open caveat") in the diagnostic artifact for operator review. The routing decision is based on: supermajority of real-degradation in the cohort, dollar-evidence corroboration on T1/T12, and the independence of the cost-clearance leg from the reclassification. If the operator reads the mixed verdict as warranting more caution, that path is open in the record — but my honest verdict-mapping per the §9.5 logic is BASIS-AGREEMENT-with-T15-asterisk firming Branch A.

**OPERATOR RATIFICATION (2026-05-31).** The verdict was ratified after consciously checking the source artifact rather than the summary, on three grounds: (1) the classifier change from per-tick-agreement to p-trajectory is justified by a fact that predates the answer — B1 v1 had already established that the two bases disagree per-tick by construction, so the first method was measuring a known constant, not a signal; (2) dollar evidence (T1 −$0.96, T12 −$0.84, T15 −$0.21 with positive PnL at the mean) is classifier-independent and points the same way as the p-trajectory verdict, so the conclusion doesn't rest on the contested call; (3) the bounded-reopening caveat (locked cold before the diagnostic ran) caps the impact at 3/9 exit-timing artifacts and explicitly does not touch the 0/6 cost-clearance — so Branch A's spine holds whether you take AGREEMENT or AMBIGUOUS routing. Operator-recorded residue: **the E4 halt was marginal-discretionary rather than clean-mechanical under the T15-basis-mismatch suspicion** — at 53.3% under T15-reclassified it's upper-review-band, not the 60% halt line. The halt was procedurally correct under the configured trigger; this note records that the configuration's monitor-basis is slightly trigger-happy on marginal relationships, so the halt was at the edge rather than decisive. The configuration finding is doing exactly what it should — flagging a real machinery issue for future work without reopening a closed result. Branch A: ratified. Experiment: closed.

---

## 10. What this review does NOT claim (honesty guardrails)

- It does **not** claim the strategy is proven unprofitable in all configurations — only that it does not clear costs at $200 notional on this universe, robustly, across the trades observed. A different universe/horizon is untested.
- It does **not** resolve edge-thin vs cost-high — the diagnostic is explicit that N=6 at ±$0.06 cost precision cannot isolate them.
- It does **not** treat the RISK_OFF vector or the cost-driven exclusion as findings — both are directional. **Update post-B1-v1: RISK_OFF vector is promoted from N=2 directional to N=147 directional-corroborated** (broken_rate 23.1% vs RANGE 16.5%; see B1 baseline analysis). Still directional, not settled; mechanism unpinned (regime-causal vs pair-selection-driven — to be resolved by B1 v1.1 cross-run per-pair aggregation).
- It does **not** read the halt as proof of permanent structural fragility — the temporal-vs-structural question is open. **Update post-B1-v1: leans STRUCTURAL** (B1's per-run broken_rate sequence shows no clean monotonic climb; range 5–25%; corroborates Reading 2 from template v1.5 §4 halt-interpretation pre-load). Reading 1 not foreclosed entirely.
- It does **not** yet rule out **basis-mismatch as a contributing factor to the coint-failure count** that triggered the E4 halt. B1 v1's `health=valid never observed in 732 samples` finding (§4.3) revealed the selector and monitor use different cointegration tests; the 3/9 TRACKED-THEN-BROKE cases (T1b, T12, T15) are not robust to this concern. The basis-mismatch diagnostic (§9.5) is the test that resolves it; Branch A's acceptance is gated on it.
- It **does** treat as findings: H1 success (HIGH), mean-shift as a β-independent entry-unpredictable loss mechanism (HIGH — but with the 4.3 caveat that the *magnitude* of the universe-fragility reading may be partly basis-mismatch artifact), 0/6 robust cost-clearance failure (robust within N), the E4 halt as correctly fired by the pre-commit (its *interpretation* gated on §9.5), the RISK_OFF vector elevation at N=147 (directional-corroborated; mechanism unpinned), and the basis-disagreement between selector and monitor as itself a structural property of the bot's current configuration (B1 v1).

---

*Structural review v1.2 (FINAL 2026-05-31). v1.0 DRAFT→RESOLVED with §5.1 reframe correction. v1.1 AMENDMENT added §4.3 basis-mismatch wrinkle + §9.5 pre-committed verdicts cold + Branch A flipped to PENDING. v1.2 FINAL: §9.5 diagnostic RAN; verdict BASIS-AGREEMENT-WITH-T15-ASTERISK (2/3 REAL_DEGRADATION on T1/T12 with dollar-evidence corroboration, 1/3 THRESHOLD_HOVERING on T15 — bounded artifact narrows from pre-commit's 3/9 ceiling to 1/9); Branch A flipped back from PENDING to DECIDED YES. Configuration finding (kline-only monitor structurally stricter than orderbook-mid selector) recorded as institutional memory but does not reopen Branch A — the cost-clearance bottom-line is independent of the basis question and unchanged. Experiment retired. The discipline-trail: B1 v1 was authorized to reduce open-question space → it surfaced a new question (basis-mismatch) → v1.1 amendment pre-committed the verdicts cold → §9.5 diagnostic answered them honestly (mixed shape, routed to AGREEMENT-with-asterisk per supermajority + cost-clearance independence) → Branch A landed where the original review predicted, but having been tested by the new evidence rather than ignoring it. v1.0 → v1.1 → v1.2 is the same anti-rationalization discipline the cost diagnostic and the E4 halt pre-commit used: write the verdicts cold, run the test, accept what fires. Diagnostic artifact: docs/audits/basis_mismatch_diagnostic_2026-05-31.md. Prior history: v1.1 amendment header below. v1.0 was DRAFT-to-RESOLVED on first-read verification with §5.1 reframe + downstream chain links corrected (cost-adjustment direction; softer in form, identical in direction). v1.1 amendment: B1 v1 ran (`tools/observation_mode/coint_fragility_sampler.py`) and surfaced `health=valid never observed in 732 samples` — the selector (orderbook-mid) and monitor (kline-only) use different cointegration tests. This raises a basis-mismatch question about the coint-failure count that triggered the E4 halt; the 6/9 dollar-DECOUPLED cases are robust to it (basis-independent evidence) but the 3/9 TRACKED-THEN-BROKE cases (T1b, T12, T15) are not. Amendment edits: §4.3 (basis-mismatch wrinkle added); §9 operator-decisions (Branch A softened from DECIDED-YES to PENDING basis-mismatch diagnostic; new diagnostic + B1 v1.1 decision rows added); §9.5 (new section with three pre-committed verdicts cold for the basis-mismatch diagnostic — BASIS-AGREEMENT firms Branch A, BASIS-DISAGREEMENT-SUBSTANTIAL replaces Branch A with basis-aligned retest, AMBIGUOUS-INSUFFICIENT-PAIRED-DATA holds Branch A at lean-accept with open caveat; anti-rationalization lock recorded); §10 (honesty guardrails updated to reflect B1 v1 corroborations + the new open basis-mismatch question). Header status flipped from RESOLVED to RESOLVED-with-AMENDMENT. Committed criteria (§4 gate, §5 bar, §6 branch definitions, decision-tree branches) unchanged. The amendment is the discipline working: B1 was authorized to reduce the open-question space; instead of cleanly confirming, it surfaced a new question that has to be answered before the consequential decision is safe — the right move is to write the new question into the review and pre-commit its verdicts, not to ignore the new evidence or to leave the review standing as written. Triggered by E4 halt at T15. §7 centerpiece: cost_diagnostic_post_T15_halt.md. B1 baseline: b1_baseline_analysis_2026-05-31.md. Pre-committed criteria: structural-review template v1.4/v1.5. Recommendation: Branch A LEANING, gated on §9.5 basis-mismatch diagnostic; B1 v1 LANDED; B1 v1.1 + §9.5 diagnostic are the active next work items; B2/C trading still declined; next strategic direction deferred. The call is the operator's; the chain is shown so disagreement can be placed at the right link.*
