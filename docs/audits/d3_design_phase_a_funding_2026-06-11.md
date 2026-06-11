# D3 Design Phase A — Funding Reality (Measurement) — 2026-06-11

*Per work item `docs/prompts/work_item_d3_design_phase.md` (v1.0, commit `d9efdcc`). Tool: `tools/observation_mode/d3_funding_reality.py`. Measurement only — no verdict surface (Phase A replaces an assumption with data; Phase B carries the locks). Read-only, public funding-rate-history endpoint, no auth, no bot contact.*

---

## Result: the assumed funding stacks were ~6× too pessimistic at the median — pairs funding nets out

The pre-test's caveat #1 ("funding is assumption-based") is closed. The assumption grid charged **both legs as paying** funding; a pairs position is one long + one short, so the real cost is the **rate differential** between the legs — and on correlated crypto perps it mostly cancels.

**Data:** funding-rate history for all 44 qualified instruments (15,490 funding events, ~400-day window, cached at `output/funding_cache/`). Pair-level computation: for each of the 672 pre-test-contributing pairs, |Σ(r₁ − r₂)| × $100/leg over every 10-day window stepping 5 days — **11,424 (pair, window) samples**.

| Quantity | Assumed (pre-test grid) | **Measured (pair differential)** |
|---|---|---|
| 10-day funding, median | $0.60 (mid) | **$0.104 (p50)** |
| 10-day funding, adverse | $1.80 (high) | **$0.470 (p90)** |
| 10-day funding, tail | — | **$2.005 (p99)**, max $2.47 |

Per-event context: median single-instrument rate +0.005%/8h (p10 −0.012%, p90 +0.010%) — rates are usually small, often similar across correlated legs, and the differential cancels most of it. **The tail (p99 ≈ $2) is real** — one leg's funding can diverge (typically a crowded perp during a squeeze) — and is why Phase B's stress level uses p90, with p99 noted as the kill-criterion's territory for the eventual spec.

## Phase B cost levels (locked formula from the work item, now with measured inputs)

| Level | Formula | Value |
|---|---|---|
| **BASE** | $0.14 entry/exit + p50 funding | **$0.244** |
| **STRESS** | $0.28 (2× slippage) + p90 funding | **$0.750** |

**Effect on the premise's headroom:** the pre-test's median 2σ edge ($24.17) now sits at **~99× BASE and ~32× STRESS** — the measured reality is *more* favorable than the assumption grid (which already cleared at 12.5–54.9×). The funding caveat closed in the premise's favor; the binding uncertainty is now squarely **capture realism** (Phase B), not costs.

## Notes

- Leg notional approximated at $100/leg (central β case at $200 gross; β-sizing shifts legs within ~$60–$140 — the differential scales proportionally, second-order for this measurement).
- |net| is reported (magnitude): realized funding can also be *received*; the cost model conservatively treats the magnitude as cost.
- All 44 instruments had usable history; no skips.

**Next per the locked sequence: Phase B** — the capture-realism walk-forward on the locked 6-cell grid, gated at BOTH $0.244 and $0.750, verdicts already locked at `d9efdcc` (DESIGN-VIABLE / DESIGN-DEAD / DESIGN-AMBIGUOUS with named sub-causes; borderline resolves DOWN).

---

*Phase A artifact, 2026-06-11. Summary CSV: `output/d3_funding_summary.csv`; funding cache regenerable. No verdict — measurement only, feeding Phase B's locked cost levels.*
