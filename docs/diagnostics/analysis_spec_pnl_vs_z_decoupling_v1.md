# Analysis Spec — PnL-vs-z Trajectory & Failure-Mechanism Diagnostic
## Read-only / diagnostics-only. One prioritized spec, three queries.

**Task class:** READ-ONLY AUDIT / DIAGNOSTICS-ONLY. No config change, no behavior change, no live-execution change. Operates on already-logged telemetry (query 1), then historical klines for *known* trade windows (query 2), then a gated scale study (query 3). Respects every frozen variable. Live collection (exp_beta_aware_sizing_v1, run 132+) continues untouched in parallel — this does not pause, alter, or depend on it.

**Drafted:** 2026-05-29, after T5 (run 131). Counter 5/20, 2 $/σ-eligible.
**Owner split:** Strategist specifies (this doc). Code assistant executes (extraction + computation). Operator decides any lever that emerges and authorizes query 3 (engineering cost).

---

## 0. Why one spec, not two

Two open strategic questions were heading toward two separate analyses. They share a single primitive, so one read answers both:

> **Dollar (unrealized) PnL as a function of z, across the per-trade monitoring snapshot series.**

- **H2 bifurcation** (working trades, e.g. T2/T5): positive $/σ but realized edge doesn't clear costs. Read **PnL at the z≈0 mean-crossing** and compare to costs → distinguishes *pure-cost* vs *exit-too-late* vs *zone-too-narrow*. (Motivation: T5's MFE +$0.187 peaked at z≈2.16 — an overshoot extreme — not at the mean. MFE is a hindsight peak; "MFE > costs" does not establish "thesis-capturable edge > costs." The mean-crossing PnL is the disambiguating number and it is already logged.)
- **Mean-shift / decoupling mechanism** (coint-failures, e.g. T1/T3/T4): z reverts favorably but dollar PnL stays negative throughout, costs clean, liquid pairs. Read **whether PnL tracks z-reversion or decouples** → tests whether the failure is the cointegrating relationship's mean drifting mid-hold (so z→0 ≠ dollar-reversion).

Both are the same plot read two ways. Query 1 builds it once, at zero new data cost, over the full closed-trade history.

---

## 1. Data-availability preconditions (CONFIRM before running)

- [ ] **Snapshot series retrievable per trade:** the per-monitoring-cycle `(timestamp, z, unrealized_pnl)` triples. Audits reference ~11 snapshots/trade carrying both z and unrealized PnL (T4: "−0.067 → −0.007 across 11 snapshots"; T5: "peaking ~+$0.25 at z≈2.16"), so the data exists for current trades. **Identify the source** (monitoring bot log / trade-monitor CSV / event payload) and **confirm retention + format for the prior-experiment trades (T1–T14, exp_coint_stability_v1).**
- [ ] **Per-trade real_costs** from reconciliation telemetry (already tabulated). Inherit the existing recon-disposition rule: `basis=position_pnl` trades (T8) are cost-unreliable → exclude from cost-clearance comparison; `basis=pre_close_equity_delta` with unattributed costs (T10) → include PnL, mark costs approximate.
- [ ] **Entry β** per trade (BETA_SIZING line for current trades; `metrics["hedge_ratio"]` for prior). Already available.
- [ ] **Snapshot PnL is unrealized mark-to-market** — independent of the fee-settlement timing gap, so it should exist even for recon-FAIL trades. Confirm.

If snapshots are missing/sparse for some prior trades, run query 1 on whatever subset has them and report coverage; do not block.

---

## 2. Scope of trades

Run over the **union of all closed trades**, tagged by experiment and exit class:
- exp_coint_stability_v1: T1–T14 (equal-notional sizing — see confound note below).
- exp_beta_aware_sizing_v1: T1–T5 and all subsequent (β-sized).

**Sizing confound (methodological, must be stated in output):**
- Prior-experiment trades ran under **broken equal-notional sizing** (β computed but not applied). For those, dollar-PnL-vs-z reflects equal-notional, so any decoupling could be *either* mean-shift *or* the sizing mismatch (β≠1 → dollars≠z even with a healthy relationship). → Prior coint-failures are **sizing-confounded for the decoupling interpretation** (still valid for MFE-in-z location and exit characterization).
- **Current trades (T1/T3/T4) are β-sized**, so decoupling there is **not** a sizing artifact → cleanest evidence for mean-shift. Weight the decoupling conclusion on the current β-sized coint-failures; use prior ones as directional context only.
- Query 2's kline recompute resolves this for *all* trades (it recomputes the spread at β-correct sizing, sizing-independent).

---

## 3. QUERY 1 — PnL-vs-z trajectory (ZERO new data; run first)

For each trade, from the snapshot series, compute:

**3.1 Trajectory primitives**
| Quantity | Definition |
|---|---|
| `pnl_at_entry` | unrealized PnL at first snapshot (≈0 expected) |
| `pnl_at_mean` | unrealized PnL at the snapshot where \|z\| is minimal (interpolate to z=0 if the series straddles it) |
| `pnl_at_zone_entry` | unrealized PnL at the FIRST snapshot with \|z\|<0.35 (what a disciplined mean-exit would have captured) |
| `mfe` | max unrealized PnL over the series |
| `z_at_mfe` | z at the MFE snapshot |
| `pnl_at_exit` | unrealized PnL at the actual exit snapshot (≈ realized gross) |
| `real_costs` | from recon telemetry |

Sign convention: define "favorable reversion" generically as \|z\| decreasing toward 0 from the entry extreme (works for both `negative_z`→long-spread and `positive_z`→short-spread entries). A tracking position has `pnl_at_mean > pnl_at_entry`.

**3.2 Classification A — coint-failure decoupling test** (apply to coint-failure exits: `cointegration_lost`, `cointegration_watch_timeout`)

Mechanical:
- **PRECONDITION (RULE, added 2026-05-29 after first Query-1 pass):** a trade is eligible for the decoupled/tracked test **only if `|Δz| ≥ 0.5`** (same floor Rule v1.2 uses for $/σ). Below that, z did not revert, so there is nothing to decouple *from* — a DECOUPLED label would be a measurement artifact. Trades with `|Δz| < 0.5` are EXCLUDED from Classification A entirely (not counted in the decoupled-rate denominator). *(First pass: this dropped T2c |Δz|=0.08 and T5c |Δz|=0.10, both spuriously DECOUPLED on a stuck z.)*
- **DECOUPLED** if z reverted favorably (z crossed into, or materially toward, the zone) **AND** `pnl_at_mean ≤ ~0` (PnL did not rise as z reverted). → mean-shift/β-drift signature.
- **TRACKED-THEN-BROKE** if `pnl_at_mean > 0` (relationship held and profited) but exit was still a coint-failure (broke late). → different sub-case; points at exit-speed, not relationship instability.
- Report the **decoupled rate** among coint-failures, split current (β-sized, clean) vs prior (confounded).

**3.3 Classification B — H2 working-trade leak** (apply to $/σ-eligible normal exits: T2, T5, future)

Mechanical, pre-committed:
- **PURE-COST** if `mfe < real_costs` → edge never beat costs at any point. Lever: cost/universe (Branch 2a) or notional-is-not-a-lever confirmation.
- **EXIT-TOO-LATE** if `pnl_at_zone_entry ≥ real_costs` **AND** `pnl_at_exit < pnl_at_zone_entry` → thesis edge cleared costs at the mean, but the position held past the mean (into overshoot) and gave it back. **Lever: tighten/respect the mean exit — NOT widen the zone.** (This is the *opposite* of Item 14's "zone too narrow.")
- **ZONE-TOO-NARROW (Item 14)** if `pnl_at_zone_entry < real_costs` **AND** `mfe ≥ real_costs` **AND** `|z_at_mfe| > 0.35` (MFE at overshoot) → the only profit lived outside the exit zone. **Flag explicitly as momentum-flavored / anti-thesis**: capturing it requires holding past the mean and betting on continued overshoot, at which point the strategy's own logic signals the opposite trade. Item 14 is *supported* only by repeated instances of this bucket — not by one favorable overshoot.

**3.4 Outputs**
- The full per-trade table (3.1 primitives + A/B class).
- PnL-vs-z trajectory plot per eligible trade (and per current coint-failure), exit zone and MFE marked.
- Bucket counts with N stated. **Promote the H2 bifurcation to two tracked columns going forward — `mfe > costs?` AND `pnl_at_mean > costs?` — appended to the per-run audit's Section 3D.** Not a verdict yet.

**Kill conditions (state the result honestly even if it dissolves a hypothesis):**
- If most current coint-failures are **TRACKED-THEN-BROKE** (PnL did rise with z-reversion) → the mean-shift hypothesis is **wrong**; the failure is late breakage, look at exit-speed instead. Drop mean-shift.
- If eligible trades classify **EXIT-TOO-LATE** → Item 14 "widen the zone" is the wrong lever; the indicated lever is mean-exit discipline (a tightening). Update the structural-review Branch-1 framing accordingly.
- If eligible trades classify **PURE-COST** → exit redesign is not the lever at all; Branch 2 (cost/universe + maker) is.

---

## 4. QUERY 2 — mean-shift vs β-drift decomposition (cheap; klines for KNOWN windows)

Runs only on trades flagged **DECOUPLED** by query 1. Uses the existing kline-pull capability (`core/chart_audit/retroactive_beta.py` already pulls 1m klines for trade windows). No look-ahead risk — the trades happened, the windows are known.

For each decoupled trade, pull leg klines over the exact hold window and compute:
1. **Dollar spread at β-correct sizing**: reconstruct `leg1_value − leg2_value` at the entry β sizing, across the hold. Did its **level drift** — i.e., the spread failed to return to its entry-window mean even as z (vs rolling mean) returned to 0? → **mean-shift**.
2. **Rolling β**: trailing-window OLS β through the hold. Did β move materially from entry β? → **β-drift**.
3. **Decompose** the z-reversion into "mean moved toward price" vs "price moved toward mean."

**Levers each mechanism points to (note the refuted-lever guardrail in §6):**
- **mean-shift dominant** → post-entry/structural levers: early exit on dollar-divergence (if dollars are red while z reverts, bail before `watch_timeout` — *exit-speed*, un-refuted), tighter hold-time cap, or a historically-stability-screened universe (§7 of the structural-review template; the graveyarding on measured footing). Connects to research-paper §9.5 dynamic-coint-monitoring deferred item.
- **β-drift dominant** → dynamic re-hedging (re-estimate β mid-hold, adjust legs — architecture change, higher risk) or a β-stability screen.
- **Neither / both small** → the decoupling is something else; report and reconsider.

---

## 5. QUERY 3 — universe rate & $/σ distribution at scale (GATED on operator go-ahead; real engineering)

Answers the **E4 question at scale**: is the live 60–75% coint-failure rate the true universe rate, or small-sample? And: does a relationship-stable subset of the universe exist with edge that could clear costs? Resolves the central question far faster than ~30 live trades.

Two build options (operator/engineering choice):
- **(3a) Historical replay** — fast, generates hundreds of entries. **Look-ahead discipline mandatory**: establish cointegration using *only* pre-entry data, then measure the relationship forward over the hold. Survivorship caveat: today's pair universe ≠ the historical universe — state it.
- **(3b) Shadow-pipeline mode** — run the *actual* live discovery/signal pipeline with order placement stubbed, freed from `max_session_trades=1` and the circuit breaker. Slower than replay but **faithful** (no signal re-implementation, no look-ahead). Preferred for fidelity on this codebase.

Output: coint-failure rate at N=hundreds (with CI); $/σ-sign distribution; relationship-stability by pair/structure-category.

---

## 6. Discipline guardrails (apply to all queries)

- **Measure, do not fit.** Queries 1–2 measure structural facts (price-path-deterministic). Query 3's universe-stability finding **must** use walk-forward / out-of-sample — selecting the pairs that worked historically is the overfit trap this project avoids.
- **Real costs cannot be backtested.** The 1.8×/2.8×/3.8× overruns are live-fill truths. Live collection stays as the cost instrument; these queries answer only the *structure* questions live can't reach quickly. This is **additive** to live, not a replacement.
- **Refuted-lever guardrail.** Any "stability screen" that emerges must **not** be an entry-time cointegration metric (slope or level) — both refuted (exp_coint_stability_v1 Verdict 10B; T1/T3/T4 all entered with benign/improving slopes and failed). Surviving levers are post-entry (exit-speed), structural (universe selection), or architectural (re-hedge).
- **N-discipline.** Query-1 results on 2 eligible / ~4 clean coint-failures are **directional only**. The value is they are cheap and extend automatically as trades accumulate. Report rates with N; do not over-read. One favorable overshoot (T5) is not evidence for exit redesign.
- **Hypotheses are droppable.** State the kill conditions (§3.4) plainly; if the data disconfirms mean-shift or exit-too-late, say so and redirect.

---

## 7. What this feeds

- **Structural-review template (exp_beta_aware_sizing_v1 v1.1):** query 1 Classification B resolves which §6 branch the H2-null implies (and whether Item 14 / Branch 1 is even the right lever); query 3 resolves the §4 **E4** question (universe-too-fragile) at scale, potentially before trade 10.
- **Deferred items:** mean-shift ↔ research-paper §9.5 (dynamic coint monitoring); exit disambiguation ↔ Item 14; universe-stability ↔ §7 categorical spread-gating + the graveyarding (HMSTR/FLOKI/ETHFI/FIL, JUP/YGG watch).
- **Cost diagnostic (template §7):** query 1's `pnl_at_*` vs `real_costs` columns feed the residual-vs-effective-half-spread study directly.

---

## 8. Action items

**Code assistant:**
- [ ] Confirm §1 preconditions (snapshot source/retention/format).
- [ ] Run **query 1** over the full closed-trade union; emit the per-trade table, trajectory plots, bucket counts, and the two new tracked columns into the per-run audit.
- [ ] Run **query 2** on query-1's DECOUPLED set.
- [ ] **Hold query 3** pending operator go-ahead (engineering cost); when authorized, recommend 3a vs 3b.

**Operator:**
- [ ] Authorize query 3 build (and 3a replay vs 3b shadow) once query 1–2 results are in.

**Strategist:**
- [ ] Read query 1–2 outputs; update the structural-review template's Branch-1/Branch-2 framing and the E4 read per what the buckets show.

---

*Analysis spec v1.0. Read-only / diagnostics-only. No frozen variable touched; live collection unaffected. Inputs: per-run audit runs 125–131 (T1–T5); structural_review_exp_beta_aware_sizing_v1_template_v1.md v1.1; exp_coint_stability_v1 closed record; code traces (taker confirmation, limit_order_basis) 2026-05-29.*
