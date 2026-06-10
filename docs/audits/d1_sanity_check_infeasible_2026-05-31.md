# D1 §1.3 Sanity Check — INFEASIBLE-INSTRUMENT (as originally specified) + Standing Meta-Finding

*Run 2026-05-31 per work item `docs/prompts/work_item_d1_continuation_pretest.md` §1.3 (v1.1). Tool: `tools/observation_mode/d1_sanity_check.py`. Result: the original two-stage gate fails definitively; the strategist has ratified a single re-spec to a differenced-quantity gate (recorded in work item v1.2) with a one-re-spec-only bind. This artifact persists the original result and extracts the meta-finding before the re-spec runs.*

---

## Verdict on the gate as originally specified: INFEASIBLE-INSTRUMENT

The §1.3 two-stage reconstruction validation — kline-reconstructed z levels and velocities against the bot's logged z on the 15 in-trade overlap windows — fails completely:

| Stage | Pass criterion | Result |
|---|---|---|
| Stage 1 (levels) | mean \|Δz\| ≤ 0.10σ on ≥13/15 trades; no tick >0.5σ | **0/15 pass; 13 trades have >0.5σ ticks** |
| Stage 2 (velocities) | mean \|Δdz/dt\| ≤ 0.15σ/min on ≥13/15 trades | **0/15 pass** |

Per-trade mean level errors range 0.16σ (T3) to 1.46σ (T4) — between 1.6× and 14.6× the tolerance. The error pattern is pair-specific and persistent (T4 DOGE/AAVE worst at 1.46σ mean; T1 JUP/YGG at 1.10σ; T11 AVAX/ETC best at 0.18σ but still 1.8× tolerance), which matches the §9.5 basis-finding signature: the bot's internal basis differs from public kline data in a structural, pair-dependent way.

Per the work item: **INFEASIBLE-INSTRUMENT is distinct from CONTINUATION-DEAD.** The data layer beneath the simulation failed its validation; nothing about the continuation hypothesis has been tested. Per-tick comparison data preserved at `tools/observation_mode/output/d1_sanity_check_per_tick.csv` (regenerable from the tool).

### Why the reconstruction fails (root cause, consistent with two prior diagnostics)

The bot computes z from **orderbook-mid prices on the current bar with per-tick OLS β-refit** (`entry_basis=orderbook_mid` per COINT_GATE logs). The reconstruction uses **kline close prices with the logged entry-β held fixed**. Three compounding differences:

1. **Price basis:** orderbook-mid ≠ kline close (the §9.5 finding at the test-statistic level; the query-3 finding at the PnL level).
2. **β dynamics:** the bot refits β each tick; the reconstruction froze entry-β. Query 2 established rolling β is *stable* (−1.6%/+0.6% over holds), so this contributes modestly — but on a z normalized by a small rolling σ, even small β differences shift levels materially.
3. **Rolling-window state:** the bot's rolling mean/σ at trade time was seeded by *its own* price history (orderbook-mid); the reconstruction's rolling stats are seeded by kline history. Different windows on different price streams → different normalization even where raw spreads agree.

---

## STANDING META-FINDING (third converging diagnostic — carry to all future analyses)

> **The bot's internal basis is not reconstructable from any public historical source.** Three independent diagnostics now converge:
> 1. **Query-3 §5 fidelity gate (2026-05-30):** OKX's internal `markPx` (used for `upl`) is not externally subscribable — offline klines 1/57 within $0.01; live WS mark-price 0/28 within $0.01, structural ~5.9bps offset. Killed the shadow-simulation build.
> 2. **§9.5 basis-mismatch diagnostic (2026-05-31):** the selector (orderbook-mid) and monitor (kline-only) cointegration tests disagree structurally — `health=valid` never observed in 732 samples under kline basis while entry-discovery passes the same pairs under orderbook-mid.
> 3. **D1 §1.3 sanity check (2026-05-31, this artifact):** the bot's z trajectory cannot be reproduced from public klines — 0/15 trades within 0.10σ level tolerance, 0/15 within 0.15σ/min velocity tolerance.
>
> **Constraint for future analyses:** any analysis requiring the bot's internal-basis quantities must (a) use logged values only, (b) work in differenced quantities where stable basis offsets cancel — subject to validating that cancellation on the in-trade overlap, or (c) accept INFEASIBLE. Level reconstruction from public data is closed as a method, three-for-three.

This goes to the deferred-items list as a standing constraint, alongside the refuted-lever guardrail.

---

## The strategist's re-spec ruling (recorded; runs next)

**Rejected — Option 2 (tolerance relaxation):** moving the bar from 0.10σ to 0.20σ because the instrument can only hit 0.20σ is gate-shopping. Additionally fatal on the merits: 0.20σ level noise compounds to ~0.28σ/min velocity noise against a 0.3σ/min detector threshold — the lowest velocity row would be mostly noise even if the relaxed gate "passed."

**Ratified — one re-spec, gating the quantity the analysis actually uses.** The decomposition: (1) broken-event triggers are the bot's own logged events, untouched by reconstruction; (2) the outcome variable is a **windowed PnL change**, not a level — and the basis offset ε is structural and stable over short horizons (query-3: consistent ~5.9bps across 28 ticks; §9.5: pair-stable), so it largely cancels in differences; (3) the kline-velocity detector is a *deployable detector in its own right* — a live system could compute exactly it from live klines, so testing it honestly labeled is the design intent anyway, not a degradation.

**The re-specced gate (pre-committed before it runs):** on the in-trade overlap windows, mean abs(kline-derived position-PnL change − logged `upl` change) over matched 5–15 min intervals **≤ $0.03 at $200 notional, passing on ≥13/15 trades**.

**The bind (strategist, verbatim):** *"One re-spec, justified by the original gate testing a stricter question than needed; a second re-spec after a second failure would be exactly the iterate-until-passes pattern, and it does not happen."* If the differenced quantities fail too, the offset isn't stable enough, INFEASIBLE-INSTRUMENT is definitive, the D1 pre-test closes, and the pivot decision returns to the operator with "the premise couldn't be cheaply tested" as its honest status.

**Legitimacy parallel:** the §9.5 classifier change earned its legitimacy because the first method measured a known constant; this re-spec earns it because differencing provably cancels the offset the level-test choked on. Both are corrections of *what is measured*, justified by facts that predate the answer — not adjustments of *how hard the test is*.

---

## Implementation notes bound into the re-specced run (strategist's three, verbatim in substance)

- **(a) Out-of-trade β:** no logged β exists for non-active-pair events. Pre-commit: hypothetical position's β = OLS on the kline lookback at trigger time (what a deployable system would do), cross-checked against logged β on the in-trade overlap. Query 2 says β is stable; large divergence there is a flag, not a fudge.
- **(b) Outcome-basis consistency:** the confound sub-analysis must compute *both* populations' outcomes on the kline basis — no mixing logged outcomes for in-trade events with kline outcomes for the rest.
- **(c) Timestamp alignment:** the metadata builder's dual-offset timezone handling must be hard-verified against `trade_closes.csv` UTC timestamps before window extraction. Misaligned timestamps would silently corrupt every window — a worse failure mode than an honest gate fail.

**§6 wording consequence:** the verdicts now claim things about *the detectors actually tested* — the bot's logged broken flag and the kline-velocity detector (two real, deployable instruments) — not about "the bot's z-velocity," which is unreconstructable.

---

*D1 §1.3 sanity check artifact, 2026-05-31. Original gate: INFEASIBLE as specified (0/15 both stages). Meta-finding: internal basis unreconstructable from public sources — three diagnostics converge; standing constraint. Re-spec ratified: differenced-quantity gate, ≤$0.03 @ $200 on ≥13/15 trades, one-re-spec-only bind. Tools: `d1_kline_fetcher.py`, `d1_metadata_builder.py`, `d1_sanity_check.py` (+ v2 gate to follow). Kline cache and tooling remain reusable assets regardless of the re-spec outcome.*
