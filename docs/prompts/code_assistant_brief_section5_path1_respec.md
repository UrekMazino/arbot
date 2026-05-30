# Code-Assistant Task Brief — §5 Fidelity-Gate Re-spec (Path 1) + Conditional Live Marking Validation

**From:** strategist (analysis/strategy role)
**Task class:** (1) doc edit to the query-3 spec [safe], then (2) a CONDITIONAL bounded read-only live integration [needs your confirmation + operator go before it runs].
**Frozen-config status:** intact. No frozen variable changes anywhere in this brief.
**Live trading:** the experiment continues untouched. Nothing here may perturb the live monitoring loop.

---

## Context (why this task exists)

The §5 offline fidelity-gate was run and **FAILED decisively**: 1/57 snapshots reproduced to the cent, median |diff| ~$0.10, systematically negative-biased. Root cause is diagnosed and is a **data-source impossibility, not a bug**:

- OKX computes unrealized PnL on swap perps from the **mark price** (an indexed/smoothed real-time value used for funding/liquidation), **not** last-trade OHLC. The history-candles endpoint returns last-trade OHLC → different numbers; the negative bias matches last-trade closes lagging the mark.
- Bar-close-vs-intrabar timing adds residual scatter (~$0.05–$0.20 leg-level), secondary.
- **The mark price is a derived real-time value OKX does not retain as a historical candle series → cent-level offline anchoring of the x-axis is structurally impossible from history alone.** Do not re-attempt the offline version; this is settled.

**Why this matters for query 3:** the joint-distribution x-axis (`pnl_at_mean`, `max_in_zone_capture`) carries the fork classification, and the cleared-vs-not-cleared margins are small (T6 in-zone max $0.0067; T8 `pnl_at_zone_entry − cost` gap $0.032). A ~$0.10 x-axis error would **swamp** the classification on exactly the marginal cases the fork turns on. So the gate is not optional and cannot be relaxed to a tolerance coarser than those margins — that would make the gate meaningless while keeping its name. **Path 1 (move the gate live) is the only revision that yields a trustworthy x-axis** (apples-to-apples against the same real-time mark feed the live bot uses).

---

## TASK 1 — Re-spec §5 of the query-3 spec to Path 1 [DO NOW; doc edit, safe]

File: `query3_output_spec_universe_scale_joint_distribution_v1.md` (or its committed repo path under `docs/diagnostics/`).

Rewrite the §5 **virtual-PnL marking-fidelity verification gate** from "reproduce recorded `position_snapshots` to the cent from offline historical data" to a **live concurrent-shadow verification**:

1. **Record the offline-gate failure and its diagnosis** in the spec (so no future session re-attempts the impossible offline version): the 1/57 result, the mark-price-vs-last-trade root cause, and the conclusion that offline anchoring is structurally impossible. One short paragraph; it's load-bearing institutional memory.
2. **Define the Path-1 gate:** run a shadow marking pass **alongside live trades** for a validation window, consuming **OKX's real-time mark price from the same endpoint/feed the live bot already uses**, and verify the shadow's per-tick virtual PnL matches the live monitoring loop's `unrealized_pnl_usdt` **to the cent in real time**. Apples-to-apples because both consume identical inputs.
3. **Pass criterion:** cent-level agreement on ≥ [propose a threshold — e.g. 99% of ticks within $0.01] across a validation window of [propose — e.g. ≥3 live trades' full snapshot series]. You set the exact numbers; state them in the spec and your rationale.
4. **State the consequence explicitly** (keep the spec honest): Path 1 converts the gate from "bounded offline verification" into "a small read-only live integration that runs concurrent with live trades." It is still far short of the full harness (read-only mark tap + per-tick compare; **no entry generation, no order path, no run-to-N, no cost model**), but it is no longer purely offline.
5. **Update the §7/footer / wherever the gate is referenced** so the spec is internally consistent (the gate is now a live prerequisite, not an offline one).

Do NOT touch the committed criteria this edit doesn't bear on (the fork classification logic, the §3.1 category-cost handling, the Q-A/Q-B split). This is a §5-scoped revision plus its cross-references.

Bump the spec version and note the Path-1 re-spec in the footer.

---

## TASK 2 — Confirm scope of the Path-1 live validation [DO NOW; analysis/report, no code]

Before anything runs live, **report back on two questions** — this is the gate on whether Task 3 is authorized:

**2a — Is it genuinely bounded read-only?** Can the live marking validation be implemented as a **read-only mark-price tap + per-tick comparison logger**, WITHOUT standing up any part of the shadow harness (no entry-signal generation, no order-placement path, no position state machine)? If it cannot be done without building most of the harness, **STOP and report** — it then collapses back into the full query-3 build decision, which is on hold. (This is the same stop-and-report guardrail that correctly fired on the offline gate. Honor it again.)

**2b — Is it confirmably non-perturbing to live execution?** Confirm the validation pass cannot interfere with the live monitoring loop's timing, rate limits, or state. Specifically: does sharing/subscribing to the mark-price feed add latency to the real bot's ticks, consume rate-limit budget the live loop needs, or touch any shared mutable state? **If there is any risk the validation perturbs a live trade, it waits** — the validation is not worth a single perturbed live trade during a frozen experiment.

Report 2a and 2b as a short written assessment. Do not write the integration code until the operator gives the go on Task 3.

---

## TASK 3 — Run the Path-1 live validation passively alongside collection [AUTHORIZED 2026-05-29 — proceed under the conditions below]

Task 2 cleared (2a bounded read-only; 2b non-perturbing). Operator has authorized. **Proceed — under the framing and binding conditions in this section.**

### Reframe — this is an X-AXIS FEASIBILITY TEST, not just a validation step

Run this with the correct framing, because the code-assistant's own Task-2 assessment surfaced the reason: the flagged risk (public-WS mark price may not equal OKX's *internal* mark-price-for-unrealized-PnL — different smoothing, index components not in the public stream) is not merely "the validator might disagree." It is a question about whether **a cent-level-anchored x-axis is achievable at all, by any available data source.** The logic: if public-WS mark ≠ internal mark, Path 1 fails the same way offline failed, and there is no Path 2 worth taking (relaxation defeats the gate). So:

- **Clean pass** → the build's x-axis prerequisite clears.
- **Consistent disagreement traceable to the mark-price-source mismatch** → **this is a STRUCTURAL FINDING, not a bug:** the query-3 joint-distribution x-axis cannot be built to the precision the fork requires, from any data source available. That would mean the cost-vs-edge fork is **not resolvable by the shadow-distribution approach**, and would have to be resolved another way (more live eligible trades, accepting the fork stays open, or a different instrument). **Report it as a finding and HOLD** — do not attempt to spec-revise around it, because there is nothing to revise *to*. That is the point of the test.

Both outcomes are decision-useful. The second one is genuinely important and would save authorizing a full harness build that cannot produce a trustworthy answer.

### What to do

- Implement the read-only mark-price tap + per-tick virtual-PnL comparison logger **as a separate process (sidecar)**.
- Run it **passively alongside the next several live runs** (it piggybacks on collection — it needs live trades to compare against, and those are flowing anyway; it does not compete with collection).
- Log per-tick: timestamp, leg marks, shadow virtual PnL, live `unrealized_pnl_usdt`, diff. Emit a pass/fail against the Task-1 criterion per validated trade.
- Target: marking fidelity validated live by ~the time the ≥8-eligible urgency gate approaches, so the query-3 build (when triggered) has a validated x-axis prerequisite already cleared — **or** the infeasibility finding is in hand before the build is ever authorized.

### Binding conditions on this authorization

1. **Sidecar is non-negotiable.** The 2b non-perturbing verdict is conditional on separate-process. The authorization is for the sidecar implementation ONLY. If for any reason it cannot be done as a separate process, that is a **STOP-and-report**, not a judgment call — an embedded variant fails 2b and is not authorized.
2. **Path A (log-parse) only. Path B is NOT pre-authorized.** Get the per-trade entry/leg-capital data by log-parse (Path A — zero live-code touch). If A proves brittle, **STOP and report; the operator decides Path B then.** The fallback to B (the one-line live-execution-file write) is a fresh operator decision, NOT something this authorization triggers automatically. During a frozen experiment the bar for touching a live execution file is "necessary," not "safe" — A is sufficient for a validation pass, so B waits for an explicit, separate go.
3. **Mark-source-mismatch is a first-class finding (per the reframe above).** If the validator consistently disagrees and it traces to the mark-price source, report immediately and hold. Do not relax the tolerance (defeats the gate) and do not spec-revise around it.

**Same overarching guardrail:** if implementing this surfaces a need to build any harness component (entry generation, order path, position state machine, run-to-N, cost model), STOP and report rather than proceeding into the build. The query-3 full build remains HELD on its unchanged trigger.

---

## What stays HELD / unchanged (do NOT do)

- **Query-3 full shadow harness build: HELD.** The offline-gate failure changed the build's *prerequisite*, not its *trigger*. The trigger is still the §4 ≥8-eligible / E4 condition. Do not build the harness on the back of this brief.
- **No frozen-variable changes.** Notional, z-thresholds, coint window, max_break_risk, circuit breaker, slope_max, MR-escape, ML-live, router-activation — all frozen, untouched.
- **No order-path or execution changes.** This brief is read-only on live; the only live contact is a read-only mark-price tap *if* Task 3 is authorized.

---

## Commit (separate, your call on timing)

Pending uncommitted docs are safe to land together, all documentation, none touch the running bot (run 137 unaffected): the T9 audit + CURRENT_STATE + memory updates, the structural-review template v1.3, and the Task-1 §5 re-spec edit once made. Include the earlier path-hygiene fix (|Δz|≥0.5 mirror into the Downloads spec copy; spec under `docs/diagnostics/`).

---

## Report back

After Task 1: confirm the §5 re-spec landed.
During/after Task 3: report per-trade validation results against the Task-1 criterion. Two terminal outcomes route differently:
- **Clean pass** → x-axis prerequisite cleared; query-3 build's marking concern is resolved (build still held on its own ≥8-eligible / E4 trigger).
- **Mark-source-mismatch disagreement** → report as the structural feasibility finding (per Task-3 reframe) and HOLD; this becomes input to whether query 3 is built at all.
Either way, honor the binding conditions (sidecar-only; Path A only, B is a fresh decision; stop-and-report on any harness-component need).

**Status at brief time:** 9/20, 5 eligible, E4 watch (44.4%, one trade from evaluability at T10), frozen, run 137 next.
