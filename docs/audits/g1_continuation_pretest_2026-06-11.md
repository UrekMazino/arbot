# Pivot G — G1 Daily Spread-Continuation Pre-Test — Verdict 2026-06-11

*Per work item `docs/prompts/work_item_g_pivot_scoping.md` (v1.0, grid, verdicts, taint mitigations, and the stop-becomes-default clause LOCKED at commit `d0f5529` before the extended data pull). Tool: `tools/observation_mode/g1_continuation_pretest.py`. Read-only; 800-day public daily data (early ~400 days never touched by any prior analysis in this program). Zero live dollars.*

---

## Verdict: **G1-DEAD**

No cell of the locked 6-cell grid is net-positive at BASE costs. **The last program-evidence-backed direction closes.** Per the clause locked before the result existed: *stop becomes the strong default; G3 remains as an explicitly evidence-free fresh bet.*

| Cell (z_entry / trail) | n | pairs | win% | net @BASE | net @STRESS | early-half | late-half |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1.5 / 0.75 | 3,361 | 818 | 37.5% | −$1,634 | −$2,926 | −$2,368 | +$734 |
| 1.5 / 1.25 | 3,188 | 818 | 36.4% | −$1,779 | −$3,266 | −$1,638 | −$141 |
| 2.0 / 0.75 | 2,682 | 776 | 38.0% | −$1,395 | −$2,369 | −$1,578 | +$183 |
| 2.0 / 1.25 | 2,567 | 776 | 37.6% | −$878 | −$2,022 | −$712 | −$166 |
| 2.5 / 0.75 | 2,039 | 713 | 37.4% | −$1,339 | −$2,054 | −$679 | −$661 |
| 2.5 / 1.25 | 1,963 | 713 | 37.0% | −$931 | −$1,769 | −$95 | −$835 |

**Exit-reason economics (15,800 simulated trades):**

| Exit | share | % gross-positive | avg gross |
|---|---:|---:|---:|
| max_hold (rode 20d) | 7.2% | **90.4%** | **+$13.48** |
| data_end | 3.3% | 63.2% | +$8.75 |
| trail (chopped out) | **75.2%** | 36.0% | −$1.20 |
| rev_stop (thesis failed) | 14.3% | 18.0% | −$4.48 |

## What the data says, precisely

1. **The continuation effect is real when it runs** — trades that survived to max-hold won +$13.48 on average at a 90% win rate. The Phase B byproduct (30% of extensions continue) was not an illusion.
2. **But 75% of trades trail out in chop first.** The spread paths between "clean continuation" and "clean reversion" — the ~57% middle Phase B saw — are where a continuation rule family bleeds. Pooled gross is **−$0.29/trade: approximately breakeven before costs**, decisively negative after.
3. **The taint mitigation did exactly its job.** Late half (the hypothesis-generating window): +$0.12 gross/trade ≈ zero. Early half (fresh, untouched data): **−$0.86 gross/trade.** The byproduct observation was regime-local. Without the locked 800-day extension and per-half requirement, the recent window alone could have returned a tempting gray result; the fresh data falsifies cleanly.
4. **Symmetric audit passed** (same duty as every verdict): winners look like winners, losers like losers, exit-reason economics are internally coherent, no sign or leak artifacts found.

## The program-level picture this completes

Mean-reversion at minute scale: closed (Branch A, live, −$4.65). Lever-B: dead. D1 (minute continuation): infeasible offline. D3 (daily MR): premise supported, capture dead. **G1 (daily continuation): dead — breakeven gross, killed by chop and costs, with the supporting observation revealed as regime-local.** G2 (funding capture): closed on measured arithmetic. G4: infeasible at scale.

Both directions of the spread bet are now measured at daily scale: **reversion loses −$1.4/trade gross; continuation loses −$0.3/trade gross.** The honest synthesis: on this universe, at this scale, the spread's movements after statistical events are — net of the chop between clean outcomes — too close to noise to clear even $0.25 of costs, in either direction. That is a complete, three-week, ~$4.65 answer to the question the program was built to ask.

## Routing (per the clause locked at d0f5529, before this result existed)

> **Stop is the strong default.** A program whose evidence-backed paths are exhausted is complete, and reaching for evidence-free paths is momentum, not research.

**G3 (single-asset daily momentum) remains available** — flagged, as locked, as a fresh literature bet that inherits the apparatus and the toolchain but none of the program's evidence. The decision is the operator's, with no clock. What stopping preserves: H1 (β-sizing, settled), the four-point instrument meta-finding, the extension-selects-breakdown finding (measured at two timescales, both directions), the full read-only toolchain, and a discipline apparatus that held its locks through five wanted-and-unwanted verdicts in a row.

---

*G1 artifact, 2026-06-11. Verdict G1-DEAD per locked gates; audit passed; the stop-becomes-default clause was written before the data existed and is now active. Per-trade data: `output/g1_continuation_trades.csv` (15,800 trades; regenerable). The pivot-G arc consumed zero live dollars.*
