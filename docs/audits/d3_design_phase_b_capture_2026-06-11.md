# D3 Design Phase B — Capture-Realism Walk-Forward — Verdict 2026-06-11

*Per work item `docs/prompts/work_item_d3_design_phase.md` (v1.0, grid and verdicts LOCKED at commit `d9efdcc` before this analysis existed). Tool: `tools/observation_mode/d3_capture_realism.py`. Read-only, cached public daily data, measured Phase A costs. The verdict is the one the program's momentum did not want, written per the lock as cleanly as Lever-B-DEAD.*

---

## Verdict: **DESIGN-DEAD**

No cell of the locked 6-cell grid is net-positive **even at BASE costs** ($0.244/trade-equivalent), before stress. The failure is **gross-dominated, not cost-dominated** — average gross PnL per trade is −$1.17 to −$2.65 across cells against ~$0.25 costs. Capture does not reach the premise at $200 gross with this rule family.

| Cell (z_entry / z_exit) | n | pairs | win% | avg hold | net @BASE | net @STRESS |
|---|---:|---:|---:|---:|---:|---:|
| 1.5 / 0.0 | 1,098 | 666 | 39.7% | 10.9d | −$2,908 | −$3,500 |
| 1.5 / 0.5 | 1,193 | 666 | 44.7% | 8.2d | −$2,547 | −$3,071 |
| 2.0 / 0.0 | 956 | 618 | 42.4% | 9.1d | −$2,087 | −$2,539 |
| 2.0 / 0.5 | 1,001 | 618 | 45.0% | 7.1d | −$1,657 | −$2,058 |
| 2.5 / 0.0 | 791 | 551 | 46.0% | 7.3d | −$1,293 | −$1,615 |
| 2.5 / 0.5 | 813 | 551 | 47.5% | 6.0d | −$949 | −$1,241 |

**Exit-reason economics (pooled 5,852 simulated trades — the structural story):**

| Exit | share | % gross-positive | avg gross |
|---|---:|---:|---:|
| reversion (target hit) | **10.6%** | 95.3% | **+$9.92** |
| max_hold (20d) | 14.8% | 75.8% | +$5.95 |
| data_end | 2.2% | 62.3% | +$4.60 |
| coint_watch (relationship broke) | **42.3%** | 41.4% | −$1.99 |
| stop (diverged to 4σ) | **30.1%** | 16.4% | **−$9.68** |

**72% of holds end in breakdown-mode exits** (coint-watch + stop); only 10.6% reach the reversion target. When reversion IS captured it's worth ~$10 (consistent with the pre-test's $24 2σ-edge at partial capture) — the wins are real. The losses dominate: 30% of 2σ-extension entries continued diverging a *further* 2σ to the stop at −$9.68 average.

## Skeptical pass (symmetric duty — SUPPORTED got the null baseline; DEAD got the sign audit)

The most dangerous possible bug — a sign error making a profitable strategy look losing — is excluded by the exit-reason audit: reversion exits are 95.3% gross-positive and stops are 83.6% gross-negative, with magnitudes that match the spread-σ arithmetic. Wins look like wins, losses look like losses, and the expectancy decomposition (0.106×$9.92 + 0.148×$5.95 + 0.022×$4.60 − 0.423×$1.99 − 0.301×$9.68 ≈ −$1.7/trade) reproduces the observed cell averages. Implementation note: same-fold re-entry after an exit is suppressed (undercounts trades; no per-trade PnL bias — conservative on N only).

## The structural finding — and it unifies the whole program

**Unconditional survival and conditional-on-extension survival are different populations, and the strategy can only trade the second.** Reconciliation with the pre-test (both results are true):

- Pre-test: discovered relationships survive 10-day holds at **82.4%** — *unconditionally*, i.e., mostly while sitting near their means.
- Phase B: conditional on the spread being **≥2σ extended** (the only moments a reversion strategy trades), **72% of holds end in breakdown-mode exits.** The extension event itself is evidence the relationship is failing, not noise around a stable mean.

This is the **mean-shift finding reproduced at daily scale**. The program has now measured the same phenomenon three independent ways:
1. **MR live (minute scale):** 60% trade-level coint-failure; 6/9 dollar-DECOUPLED while z "reverted" (mean-shift).
2. **Lever-B (minute scale, offline):** zero early-capture moments existed — extensions didn't produce rescuable reversions at any cap.
3. **D3 Phase B (daily scale, offline):** extension-conditioned entries hit 72% breakdown-mode exits; 30% continue a further 2σ against.

**Program-level unified finding:** *on this crypto-perp universe, statistical extension of a cointegrated spread is more often the onset of relationship breakdown than a mean-reversion opportunity — at minute scale and at daily scale.* The pre-test's mandatory caveat ("survival ≠ profitability") was exactly the gap this lived in.

## Byproduct observation (reported, NOT a verdict — carries the opposite-trap warning)

30.1% of 2σ-extension events continued to 4σ (avg −$9.68 against the reversion side = avg ~+$9 for the continuation side, before costs and before whipsaw accounting on the other 70%). This is, incidentally, the first *measurable* signal bearing on D1's continuation hypothesis — at daily scale, on the native public basis, where D1's minute-scale version was INFEASIBLE. **It is NOT an inverted-strategy endorsement:** the strategist's standing warning applies ("the opposite of a losing strategy is a winning one" is a known trap — the 10.6% clean reversions and the 57% chop become the continuation bet's loss modes, and expectancy does not invert symmetrically because exits don't mirror). It is data for the operator's G-vs-stop deliberation, nothing more.

## What DESIGN-DEAD claims and does not claim

- **Claims:** at $200 gross, with the locked rule family (extension entry, reversion/stop/coint-watch/max-hold exits), on this universe, walk-forward capture is decisively net-negative at measured costs. Per the lock: no grid extensions, no rule-family retreat — the family was locked as adequate for the design question.
- **Does not claim:** that the survival premise was false (it stands, unconditionally); that some entirely different entry conditioning (e.g., post-extension confirmation) couldn't work — that is a *different direction*, not a Phase B re-spec; that larger notional changes the verdict (the failure is gross, not cost — notional scales both).

## Routing (per the locked verdict)

**D3 closes at the design level.** Remaining options: **G (strategy-class pivot) or stop** — both genuinely the operator's. The full decision picture: MR closed (Branch A, negative result); Lever-B dead; D1 infeasible-offline; D3 premise supported but design dead. Every pairs-mean-reversion configuration tested on this universe has now failed on the same underlying phenomenon, measured at two timescales.

---

*Phase B artifact, 2026-06-11. Verdict DESIGN-DEAD per locked gates (d9efdcc); sign audit passed; the lock held on the program's side — the first wanted answer (the pre-test) was scrutinized hardest, and the unwanted answer here is written without retreat. Per-trade data: `output/d3_capture_trades.csv` (5,852 trades; regenerable). The design phase consumed zero live dollars.*
