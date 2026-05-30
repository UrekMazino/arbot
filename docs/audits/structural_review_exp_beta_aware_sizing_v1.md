# Structural Review — exp_beta_aware_sizing_v1
## β-Aware Sizing: H1 Resolution, E4 Halt, and the Cost-Clearance Finding

**Status:** DRAFT for operator review. Triggered by the E4 mechanical halt at T15 (9/15 = 60.0% coint-failure rate), not by the 20-trade gate (superseded by the halt).
**Window:** T1–T15 (runs 125–142), 2026-05-28 → 2026-05-31. β-aware sizing live throughout.
**Prior review:** structural_review_exp_coint_stability_v1.md (sizing-mismatch discovery → this experiment).
**§7 centerpiece artifact:** cost_diagnostic_post_T15_halt.md.
**Pre-committed criteria source:** structural-review template v1.4/v1.5 (§4 gate + E4 + T15 pre-commit; §5 negative bar; §6 mean-shift finding).

**Verdict structure (per operator Q2):** findings → decision tree with pre-committed triggers → recommended decision with the reasoning chain visible. Most of the "decision" is mechanical once the evidence is in hand (the pre-commits fire); the consequential calls (accept negative result; choose next direction; build the observation-mode instrument) are surfaced explicitly as operator decisions with my recommendation and reasoning shown, so disagreement can be placed at the right link.

---

## 0. One-paragraph synthesis

β-aware sizing is a **clean success on what it was built to fix** (H1): signal and position are aligned on every eligible trade, 5/5 sign-positive, β-sizing mechanically exact 15/15 across the full observed β range [0.378, 1.841]. But the experiment **halted at T15 on universe coint-fragility** (E4, mechanical, pre-committed cold at T13), and the cost diagnostic — the centerpiece analysis on whether the now-correctly-sized strategy clears costs — returns a verdict that is **AMBIGUOUS on the mechanism but robust on the bottom line: 0 of 6 eligible trades clear cost even under the most generous cost assumption.** The strategy, correctly sized, does not show capturable edge above the cost stack at $200 notional on this universe. This is the §5 pre-committed negative-result reading — fired not from a single clean diagnostic but from a convergent evidence stack (0/6 robust-pass, mean-shift β-independent loss mechanism, eligible-population stall, the halt itself). **It is a finding, not a failure:** sizing was the prerequisite, sizing is solved, and the corrected strategy reveals that the binding constraint is edge-vs-cost on this universe at this notional — which the experiment was built to be able to discover.

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

---

## 5. The cost diagnostic — does the correctly-sized strategy clear costs? (§7 CENTERPIECE)

**Verdict: AMBIGUOUS-at-N on the mechanism; ROBUST on the bottom line — 0/6 clear cost.**

### 5.1 The reframe that matters most
The pre-committed verdict is AMBIGUOUS-at-N (the three-cost-assumption robustness test cannot isolate edge-too-thin from cost-too-high at N=6). **But AMBIGUOUS describes the inability to isolate the *mechanism*, not the bottom line.** The single most decisive number in the diagnostic:

> **0 of 6 eligible trades clear cost under the most generous assumption (cost − $0.06).** Not one — including T7, the only realized win and the deepest entry. Every trade in the eligible population sits within or below the cost-model's measurement-noise band at $200 notional.

That is not ambiguous. The ambiguity is about *why* the strategy doesn't clear costs (is the edge inherently thin, or is cost inherently high on a subset?); it is **not** ambiguous about *whether* it clears costs at $200 notional on this universe — it does not, robustly, on any of six trades. **The review's headline is therefore "the diagnostic robustly establishes the strategy does not clear costs at current notional; it is inconclusive only on the mechanism" — not "the diagnostic was inconclusive."**

### 5.2 What the diagnostic robustly establishes (survives the ±$0.06 error bar)
1. **0/6 ROBUST-PASS.** No trade clears cost even under adverse cost (cost + $0.06), and none clears under generous cost (cost − $0.06) either except the sign-flip cases that are within noise. The bottom line is robust to measurement uncertainty in the direction that matters.
2. **The "deep-entry-only viable subset" is NOT supported.** T7 (deepest entry, only win) has a point-estimate gap of only +$0.015 — smaller than half the ±$0.06 error band — and sign-flips negative under adverse cost. The STRUCTURAL-with-VIABLE-SUBSET branch's most promising candidate does not survive the robustness test. The one win was within the cost-model's noise band.
3. **Two clean cost-driven failures (T2, T6) ROBUST-FAIL.** T2 ($0.251 cost, recon-FAIL, KSM thin-leg — parallels the prior experiment's T10/FIL-ICP) and T6 ($0.194 cost on liquid SOL/AVAX, clean recon — the harder case, fully attributable and just structurally high). These contribute a cost-too-high sub-mode.

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
2. **0/6 ROBUST-PASS** (§5) — no trade clears cost even generously, including the win.
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
Pre-committed conclusion: *the strategy does not have a capturable edge at the current notional and universe.* Supported by the convergent stack. This is a clean finding: sizing solved, edge insufficient on this universe, dominant loss mode (mean-shift) entry-unpredictable. **Next move: stop optimizing this configuration.** Not a sizing or exit refinement (mean-shift forecloses entry levers; 0/6-robust-fail forecloses exit-capture as a rescue — there's no robust edge for a better exit to capture). Either redirect to a different universe/horizon/strategy-class, or conclude the line.

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
2. **0/6 trades clear cost robustly, including the win (ROBUST).** → At $200 notional on this universe, there is no demonstrated capturable edge above the cost stack. *[Disagree here if you think N=6 is too small to conclude even on the robust bottom line — but note all three slices agree, and the win itself doesn't clear.]*
3. **The dominant loss mode (mean-shift) is entry-unpredictable and has no entry lever (FINDING).** → You cannot fix the coint-failures at entry; the only handles are post-entry exit-speed or structural restriction. *[Disagree here only with contrary evidence on entry-predictability — the window shows none across 9 coint-failures.]*
4. **The two surviving remedies (exit-speed, universe restriction) are both undercut by step 2.** → A better exit cannot capture an edge that isn't robustly there (0/6); a universe restriction (Branch C) rests on N=2 directional hypotheses and a base-rate-indistinguishable RISK_OFF vector. Neither is a strong enough lever to justify resuming *trading* on this configuration. *[This is the key link — see step 5.]*
5. **The mechanism (edge-thin vs cost-high) is unresolvable at current cost-model precision (±$0.06 ≈ edge size).** → Resuming trading to gather more eligible data would (a) require un-halting a universe the halt just judged too fragile, and (b) still not resolve the mechanism without a cost-precision upgrade. So *more trading is the wrong next step regardless of branch.*
6. **Therefore:** accept the negative result for this configuration (Branch A). The honest finding is *"β-aware sizing is correct and settled; the strategy does not show capturable edge above costs at $200 notional on this universe; the dominant loss mode is entry-unpredictable mean-shift; the universe is coint-fragile (E4 halt)."* 
7. **The one worthwhile follow-on is B1 (no-notional observation mode)** — because it is the *only* instrument that resolves the open temporal-vs-structural fragility question (does eligibility return? is the universe always this fragile?) *without trading*, and it would also test the RISK_OFF vector at N. It is cheap, it touches nothing live (read-only on the monitoring loop, no PnL, no orders), and it answers the question that decides whether *any* future universe/horizon is worth pursuing. **This is the operator decision I'd flag as genuinely worth making** — not a trading experiment, an observation instrument.

**Operator decisions surfaced (with my recommendation):**
- [ ] **Accept the negative result for this configuration?** → Recommend YES (Branch A). The convergent stack supports it; the pre-committed bar's bottom-line antecedent is met.
- [ ] **Build the no-notional observation mode (B1)?** → Recommend YES — it's the only non-trading instrument that resolves the fragility question and tests the RISK_OFF vector, and it's read-only/no-PnL so the marking-fidelity wall doesn't apply.
- [ ] **Pursue B2/C as trading experiments now?** → Recommend NO — undercut by 0/6-robust-fail and the cost-precision ceiling; resuming trading on a halted fragile universe is the wrong next step.
- [ ] **Next strategic direction** (if Branch A accepted): different universe (liquid-only, screened for coint-stability), different hold horizon (mean-shift is a *timescale* phenomenon — a shorter horizon might outrun the drift), or different strategy class. → This is genuine operator/strategy judgment; the observation mode (B1) would inform it by characterizing which universes are less fragile. I'd not pick a direction until B1 data exists.

---

## 10. What this review does NOT claim (honesty guardrails)

- It does **not** claim the strategy is proven unprofitable in all configurations — only that it does not clear costs at $200 notional on this universe, robustly, across the trades observed. A different universe/horizon is untested.
- It does **not** resolve edge-thin vs cost-high — the diagnostic is explicit that N=6 at ±$0.06 cost precision cannot isolate them.
- It does **not** treat the RISK_OFF vector or the cost-driven exclusion as findings — both are directional at N=2.
- It does **not** read the halt as proof of permanent structural fragility — the temporal-vs-structural question is open and requires the observation mode to answer.
- It **does** treat as findings: H1 success (HIGH), mean-shift as the β-independent entry-unpredictable loss mechanism (HIGH), 0/6 robust cost-clearance failure (robust within N), and the E4 halt as correctly fired.

---

*Structural review v1.0 (DRAFT for operator review). Triggered by E4 halt at T15 (9/15 = 60.0%). §7 centerpiece: cost_diagnostic_post_T15_halt.md (AMBIGUOUS-at-N; 0/6 ROBUST-PASS). Pre-committed criteria: structural-review template v1.4/v1.5. Inputs: per-run audit T1–T15 (runs 125–142); CURRENT_STATE; the cost diagnostic; the query-3 redirect terminal finding; the prior exp_coint_stability_v1 review. Verdict structure per operator Q2: findings + decision tree + recommended decision with reasoning chain visible. Recommendation: Branch A (accept negative result for this configuration) + B1 (no-notional observation mode) as the worthwhile follow-on; not B2/C as trading experiments. The call is the operator's; the chain is shown so disagreement can be placed at the right link.*
