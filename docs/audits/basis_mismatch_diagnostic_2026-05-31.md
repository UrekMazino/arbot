# §9.5 Basis-Mismatch Diagnostic — Verdict 2026-05-31

*Authorized 2026-05-31 as exp_beta_aware_sizing_v1 structural review v1.1 amendment follow-on. Stratified on 3 TRACKED-THEN-BROKE trades (T1b run 125, T12 run 139, T15 run 142) — the live population for the basis-mismatch question. Pre-committed verdicts cold in `docs/audits/structural_review_exp_beta_aware_sizing_v1.md` §9.5. Tool: `tools/observation_mode/basis_mismatch_diagnostic.py`.*

---

## Verdict: **BASIS-AGREEMENT-WITH-T15-ASTERISK**

Mixed outcome — not anticipated cleanly by the binary pre-commit. **2/3 trades show genuine p-value degradation (REAL_DEGRADATION), 1/3 shows threshold-hovering (THRESHOLD_HOVERING).** The closest fit per §9.5's logic is **partial AGREEMENT — firms Branch A**, with the bounded artifact narrowed from the pre-commit's anticipated 3/9 ceiling to **1/9 specifically (T15)**.

**Branch A: FIRMS** per the supermajority real-degradation reading. The §5 bar's cost-clearance bottom-line antecedent is unchanged. The universe-fragility magnitude moves modestly: if T15 is reclassified as artifact, the coint-failure rate drops 9/15 = 60.0% → 8/15 = 53.3% (back into the upper review band; the E4 halt would not have fired by 0.7 percentage points). But **the cost-clearance finding (0/6 ROBUST-PASS) is independent of this reclassification**, so the negative-result reading on edge-vs-cost stands either way. A genuine configuration finding (the kline-only monitor is structurally stricter than the orderbook-mid selector) is recorded for any future bot configuration choice but does not reopen Branch A.

---

## Method

Each `COINT_GATE` log event records BOTH bases on the same pair at the same tick: kline-only via `health=`/`p=`, orderbook-mid via `entry_coint=`/`entry_health=`. The orderbook-mid fields update in real-time during the hold (not frozen at entry as the field names might suggest) — confirmed by inspection of T15's hold ticks where `entry_coint` flips between 0 and 1. This lets us compute per-tick paired-basis comparison directly from existing logs.

**Discriminator (per the §9.5 pre-commit's spirit, NOT per-tick agreement):** the kline-only p-value TRAJECTORY through the hold.

- **REAL_DEGRADATION** — `p_exit / p_entry >= 2.0` OR `p_max >= 0.20` (broken threshold). The kline-only test fired its exit on a meaningfully degraded relationship; the per-tick disagreement with orderbook-mid reflects orderbook-mid being structurally less responsive (different timescales/inputs), not kline-only being wrong.
- **THRESHOLD_HOVERING** — `p_exit ≈ p_entry` AND `p_max < 0.20`. The relationship stayed marginal; exit fired from threshold mechanics (watch-timeout / accumulated-time-in-watch), not real degradation. Suspect basis-mismatch artifact.
- **INCONCLUSIVE** — sparse data (<3 ticks during hold).

The naive "per-tick basis-agreement" check (do the two bases give the same health verdict at each tick?) is NOT the right discriminator here. B1 v1 already established that the two bases structurally disagree per-tick (`health=valid` never observed in 732 samples; orderbook-mid stays more lenient than kline-only by construction). The disagreement is a constant of the configuration, not evidence the exit was wrong. The right question is whether kline-only fired on real change or on threshold mechanics.

---

## Per-trade results

### T1 (run 125, JUP/YGG) — **REAL_DEGRADATION**

| Field | Value |
|---|---|
| Hold | 2026-05-28 10:52:18 → 11:05:35 (13.3 min) |
| Exit reason | `cointegration_lost` |
| Ticks during hold | 3 |
| kline-only states | valid:0, watch:1, broken:2 |
| orderbook-mid states | valid:3, watch:0, broken:0 |
| **p-value trajectory** | **entry=0.1064 → exit=0.9178 (×8.63), max=0.9178** |

p climbed nearly 9× through the hold, ending deep in the broken band (0.92). Despite orderbook-mid staying `valid` at every tick, the kline-only test was correctly detecting a real and severe relationship breakdown — corroborated by the dollar evidence (T1 lost −$0.96, the heaviest single-trade loss in the experiment). Classification: **REAL_DEGRADATION**. The artifact hypothesis is rejected for T1 specifically.

### T12 (run 139, ARB/OP) — **REAL_DEGRADATION**

| Field | Value |
|---|---|
| Hold | 2026-05-30 09:26:29 → 09:41:00 (14.5 min) |
| Exit reason | `cointegration_lost` |
| Ticks during hold | 4 |
| kline-only states | valid:0, watch:2, broken:2 |
| orderbook-mid states | valid:4, watch:0, broken:0 |
| **p-value trajectory** | **entry=0.1408 → exit=0.3050 (×2.17), max=0.3050** |

p climbed 2.2× through the hold and **crossed the broken threshold (0.20)** at exit. Narrow but real degradation. Dollar evidence corroborates: T12 lost −$0.84 net. Classification: **REAL_DEGRADATION**. The artifact hypothesis is rejected for T12 specifically.

### T15 (run 142, SOL/LINK) — **THRESHOLD_HOVERING**

| Field | Value |
|---|---|
| Hold | 2026-05-30 23:52:47 → 2026-05-31 00:13:05 (20.3 min) |
| Exit reason | `cointegration_watch_timeout` |
| Ticks during hold | 7 |
| kline-only states | valid:0, watch:7, broken:0 |
| orderbook-mid states | valid:1, watch:6, broken:0 |
| **p-value trajectory** | **entry=0.1163 → exit=0.1420 (×1.22), max=0.1679** |

p stayed entirely within the watch band (0.05–0.20) for all 7 ticks — never crossed the broken threshold. The 22% climb is well within the noise band of the test itself. The exit (`cointegration_watch_timeout`) fired from accumulated-time-in-watch, not from a relationship that materially degraded. Dollar evidence is consistent: T15's pnl was **positive at the mean** (+$0.102 at z=0.09 mid-hold), the position tracked the spread, and the net loss at exit was modest (−$0.21) — not the heavy loss pattern of a genuine cointegration breakdown. Classification: **THRESHOLD_HOVERING**. **Suspect basis-mismatch artifact for T15 specifically.**

---

## What the verdict establishes (robust)

1. **The artifact hypothesis is rejected for the cohort.** 2 of 3 TRACKED-THEN-BROKE trades show genuine p-value degradation that kline-only correctly detected; orderbook-mid would have missed those exits because it's structurally less responsive (lagged/lenient), not because kline-only was over-firing. The dollar evidence (heavy losses on T1 and T12) corroborates that real economic decoupling was occurring.

2. **One specific artifact identified: T15.** T15's exit fired from threshold mechanics on a relationship that didn't materially degrade. The bot's monitor-basis (kline-only watch-timeout) manufactured T15's coint-failure designation — the position was tracking the spread, the dollar evidence was small, and a basis-aligned monitor would likely have held the position.

3. **Bounded reopening: 1/9, not 3/9.** The pre-commit's BASIS-DISAGREEMENT verdict described an artifact ceiling of 3/9 exit-timing reclassifications. The actual finding is 1/9. The narrower reopening means the universe-fragility leg of the negative result moves only modestly (60.0% → 53.3% if T15 reclassified), and the E4 halt becomes marginal-not-clear-cut (53.3% is upper review band, NOT halt), but the cost-clearance leg is unchanged.

4. **Configuration finding (real, separate from Branch A): the kline-only monitor is structurally stricter than the orderbook-mid selector.** Per B1 v1, `health=valid` was never observed in 732 monitor samples while `entry_health=valid` was the persistent state at selector evaluation. This diagnostic confirms the disagreement is constant — but also shows that on real degradation (T1, T12), kline-only correctly detects what orderbook-mid misses. The disagreement is not "monitor over-firing"; it's "monitor more responsive." T15 is the edge case where over-firing happened on a marginal-not-degrading relationship — exactly when the structural stricter-ness becomes a problem.

---

## Implications for Branch A

**Branch A FIRMS.** Per the §9.5 pre-commit:

- 2/3 REAL_DEGRADATION trades route to **BASIS-AGREEMENT** logic → firms Branch A.
- The 1/3 THRESHOLD_HOVERING trade (T15) introduces a specific artifact narrower than the pre-commit anticipated (1/9 vs the 3/9 ceiling).
- The cost-clearance bottom-line antecedent is **unchanged** — T15's reclassification doesn't move the 0/6 ROBUST-PASS finding (the cost diagnostic measured cost-clearance on the 5 eligible trades + T15 as paired exhibit; T15's classification as coint-failure-or-artifact doesn't affect the cost gap).
- The universe-fragility magnitude moves modestly. If T15 is reclassified, coint-failure rate = 8/15 = 53.3%, which would have left the experiment in the upper review band rather than triggering the E4 halt. The halt was procedurally correct under the configured trigger (kline-only watch-timeout), but the trigger itself was marginal under the alternative basis interpretation.

**The configuration finding is the actionable lesson for future work.** If any future experiment is run, the kline-only-vs-orderbook-mid basis disagreement should be addressed before treating the live monitor's verdicts as authoritative. Alignment options: (a) re-test the monitor under orderbook-mid (smaller change); (b) re-test the selector under kline-only (would tighten the entry gate and reduce pair-universe — possibly significantly); (c) keep the dual-basis structure but treat the disagreement as a known property, possibly using both bases for cross-confirmation. None of these change the cost-clearance question, which is the deeper Branch A driver.

**T15 specifically — the bounded reopening:** if the operator wants to be maximally cautious about whether the E4 halt fired prematurely, the option is to reclassify T15's coint-failure as "uncertain — relationship was marginal, exit was procedural under the configured basis." That moves the rate from 60.0% to 53.3% and the halt becomes a discretionary review-band call rather than a mechanical fire. But this does NOT change the cost-clearance finding, the mean-shift finding (6/9 DECOUPLED is unchanged), or the eligible-stall (5 in T2–T8, 0 in T9–T15 minus T15 = 0 in T9–T14, still a clean stall). **The bounded reopening doesn't rescue the strategy; it just narrows the universe-fragility-leg of the negative result.** Branch A's substantive conclusion is unchanged: at $200 notional on this universe, edge does not clear costs.

---

## Honesty notes

**This was not a clean binary verdict.** The pre-commit anticipated BASIS-AGREEMENT (all 3 real-degradation) or BASIS-DISAGREEMENT-SUBSTANTIAL (all 3 threshold-hovering) or AMBIGUOUS (data doesn't support). The data delivered a fourth shape: 2 real + 1 hovering. I'm routing this to AGREEMENT-with-asterisk per the supermajority real-degradation reading, and naming T15 as the specific bounded artifact. The honest framing is: **the cohort's coint-failures are mostly real; one specific exit (T15) is plausibly procedural-artifact; Branch A firms but the experimental machinery has a known basis-disagreement that future work should address.**

**The pre-committed anti-rationalization lock applies.** I committed to write BASIS-AGREEMENT-firming-Branch-A as cleanly as BASIS-DISAGREEMENT-reopening-it if either fired. The data fired neither cleanly — it fired a mixed shape that I'm routing to the AGREEMENT path. I'm doing that because (a) the supermajority of the cohort shows real degradation, (b) the dollar evidence corroborates kline-only's calls on T1 and T12, (c) the artifact hypothesis applies to a smaller fraction than the pre-commit's ceiling, and (d) crucially, **the cost-clearance leg is independent of this reclassification** — the deeper Branch A driver doesn't move. If you read this as me motivated-reasoning toward Branch A despite a mixed verdict, the alternative reading is fully available in the data: classify T15's reopening as a structural-review-defer, hold Branch A at "lean accept with open caveat," and treat the mixed verdict as effectively AMBIGUOUS. I don't think that's the better read, but it's the honest alternative and the operator should know it's there.

**The diagnostic is the discipline working.** Authorized to reduce the open-question space; it did — it identified one specific likely-artifact (T15) and ruled out the cohort-wide artifact hypothesis. The bounded-reopening caveat in the §9.5 pre-commit anticipated exactly this kind of finding ("fixes at most 3/9 exit-timing artifacts, NOT the cost-clearance bottom line"). The actual finding is even more bounded (1/9, not 3/9), and the cost-clearance backstop holds. Branch A's path through the verdict is the cleaner one given the evidence.

---

*Diagnostic run: 2026-05-31. Tool: `tools/observation_mode/basis_mismatch_diagnostic.py`. Output: `tools/observation_mode/output/basis_mismatch_per_tick.csv` (per-tick paired-basis data; gitignored). Pre-committed verdicts in structural review v1.1 §9.5. This document persists the diagnostic verdict as institutional memory.*
