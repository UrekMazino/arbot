# Work Item — Lever-B Offline Pre-Test (Hold-Cap Simulation)
## Read-only / analysis-only. No trades, no bot contact, no frozen-variable touch.

**From:** strategist (analysis/strategy role).
**Task class:** READ-ONLY ANALYSIS on existing telemetry. Operates on the 15 closed trades' `position_snapshots.csv` series (z + unrealized_pnl per ~1-min tick) already on disk. No new trades, no live API, no bot code, no marking-fidelity dependence (these are real positions with real OKX `upl` — the query-3 wall does not apply).
**Drafted:** 2026-05-31, post structural-review closure (Branch A ratified). exp_beta_aware_sizing_v1 is CLOSED; this is a *preparatory* analysis for a possible future experiment, not a re-opening.
**Owner split:** strategist specifies (this doc) + pre-commits verdicts. Code assistant runs the simulation on existing data. Operator reads the verdict; it routes whether Lever B is worth a live test.

---

## 0. The question, stated precisely

Lever B's hypothesis: **mean-shift drifts on a ~20–40 min timescale, so exiting within the first few minutes captures mean-reversion before the drift sets in.** The existence proof is T7 (1.1-min hold, only win, exited at zone edge with full MFE). The doubt: T7's edge cleared by +$0.015 (inside the ±$0.06 noise band) AND T7 happened to revert fast — a short cap on a *slow*-reverting trade exits before reversion completes, banking *smaller* edge, and edge is already the binding constraint (0/6 clear costs).

So the real question is **NOT** "is shorter better in aggregate." It is:

> **Across the 15 real trades, is there a sub-population that was positive-above-cost at an early hold-cap mark AND gave that edge back by the realized exit? If yes, how large is it, and does a hold-cap capture it robustly to the cost error bar?**

This is answerable *retrospectively* on data we already have, because every trade's per-minute PnL trajectory is logged. We simulate: "if the trade had been force-exited at minute M, what was its PnL at M?" and compare to costs.

---

## 1. Data preconditions (CONFIRM before running)

- [ ] **Per-trade snapshot series** `(timestamp, current_z, unrealized_pnl_usdt)` at ~1-min cadence, for all 15 trades (T1–T15), from `Reports/v1/run_*/position_snapshots.csv`. (Same source the §9.5 and cost diagnostics used — confirmed to exist.)
- [ ] **Per-trade real_costs** from `reconciliation_checks.csv` (the `|difference|` field). Inherit the recon-disposition rule: T8-class `basis=position_pnl` cost-unreliable trades flagged; T2/T10-class `basis=pre_close_equity_delta` included with costs marked approximate.
- [ ] **Per-trade entry timestamp** (to compute minute-offset M from entry per tick) and **realized exit PnL** (the trajectory endpoint, ≈ realized gross — sanity-check the simulation reproduces it at the realized-exit tick).
- [ ] **Snapshot PnL is unrealized mark-to-market `upl`** — real, cent-exact, no anchoring problem (this is the whole reason the pre-test is trustworthy where query-3 wasn't). Confirm.

If any trade has too few snapshots to evaluate an early cap (e.g. T7 had 1 snapshot, T10 had 1), report it as `INSUFFICIENT-TICKS` for that trade rather than imputing — see §3 handling.

---

## 2. The simulation

For a grid of candidate hold-caps **M ∈ {1, 2, 3, 5, 8} minutes** (and the realized exit as the baseline), for each of the 15 trades:

**2.1 Per-trade, per-cap quantities**
| Quantity | Definition |
|---|---|
| `pnl_at_cap(M)` | unrealized PnL at the last snapshot with minute-offset ≤ M (the value a force-exit at M would have realized, gross) |
| `pnl_at_realized_exit` | unrealized PnL at the final snapshot (≈ realized gross; sanity-check vs recorded) |
| `real_cost` | from recon telemetry |
| `cleared_at_cap(M)` | `pnl_at_cap(M) > real_cost` ? (point estimate) |
| `cleared_at_cap_generous(M)` | `pnl_at_cap(M) > real_cost − $0.06` ? (the same generous robustness test the cost diagnostic used) |
| `cleared_at_cap_adverse(M)` | `pnl_at_cap(M) > real_cost + $0.06` ? |
| `gave_back` | `pnl_at_cap(M) > pnl_at_realized_exit` ? (did the cap capture edge the realized hold lost?) |

**2.2 The two sub-questions, per cap M**
- **Capture question:** how many trades have `pnl_at_cap(M) > real_cost` (and how many robustly, i.e. clear even adverse)? This is "would a cap at M have produced cost-clearing exits?"
- **Give-back question:** of those, how many *also* had `pnl_at_realized_exit < real_cost` (i.e., the realized hold did NOT clear, but the cap would have)? This is the trades the cap *rescues* — the actual Lever-B value. A trade that cleared at the cap AND cleared at realized exit isn't rescued by the cap; it would have won anyway.

**2.3 Aggregate per cap M**
- `n_cleared_point(M)`, `n_cleared_adverse(M)` (out of evaluable trades)
- `n_rescued(M)` = trades that clear at cap but not at realized exit (robustly, adverse-cost)
- aggregate simulated PnL under cap M (sum of `pnl_at_cap(M) − real_cost` across all trades) vs aggregate realized PnL — does the cap improve the book?

---

## 3. Handling the subtleties (these determine whether the answer is trustworthy)

**3.1 Insufficient-ticks trades.** T7 (1 snapshot) and T10 (1 snapshot) can't be evaluated at multiple caps — there's no minute-2 or minute-3 data. **Do NOT impute.** Report them as `INSUFFICIENT-TICKS` and state the evaluable-N explicitly per cap. Note the irony to carry honestly: **T7, the existence proof for Lever B, has only 1 snapshot and therefore cannot itself be used to test the hold-cap hypothesis** — its 1.1-min hold means it was already effectively "capped" by fast reversion + exit, but we can't simulate alternative caps on it. So T7 motivates the hypothesis but contributes zero to the simulation. Evaluable-N is likely ~13, not 15. State it.

**3.2 The cost-comparison is the load-bearing subtlety, and it has a trap.** `real_cost` was the cost of the *realized* trade (its actual fills, hold, funding). A trade force-exited at minute 3 would have had **different costs** — possibly lower (less funding on a shorter hold) or different slippage (exiting at a different moment). So `pnl_at_cap(M) > real_cost` uses the *realized* cost as a proxy for the *capped* cost. This is imperfect. Two mitigations:
- The fee+slippage component is roughly hold-independent (entry+exit crossing happens regardless of hold length); the *funding* component scales with hold time, so a shorter hold has *less* funding cost → using realized (longer-hold) cost is **conservative** (the capped trade's real cost would be ≤ realized cost, so if it clears against realized cost it clears even more against its own lower cost). State this directionality: **using realized cost biases AGAINST Lever B, so a positive result is robust to it.**
- But flag: if funding was a large share of `real_cost` on long-hold trades, the proxy is loose. Report the funding share if `reconciliation_checks.csv` separates it; if it doesn't, note the proxy's looseness as a caveat.

**3.3 Survivorship / selection within the trade.** The simulation asks "what if we'd exited at M" but the *entry* was the realized entry — we're not re-selecting trades, just re-timing exits on the trades that happened. That's clean (no look-ahead in entry). But note: a hold-cap policy live would interact with the exit logic (full_tp, profit-lock, coint-watch) — the simulation is a *pure* time-cap, ignoring whether the other exits would have fired first. Report it as "pure time-cap simulation"; the live version would be more complex. This is a premise-test, not a live-policy-spec.

**3.4 The z-context matters and should be reported, not just PnL.** For each rescued trade, report `current_z at cap(M)` — was the position near the mean (reversion captured) or mid-overshoot (momentum, anti-thesis)? A "rescue" that happens because the position was at an overshoot extreme at minute 3 is the T5-pattern (overshoot luck), not thesis-capture. Distinguish rescued-at-mean (real) from rescued-at-overshoot (luck), same as the cost diagnostic distinguished pnl_at_mean from MFE.

---

## 4. Pre-committed verdicts (LOCKED before the run — anti-rationalization)

The strategist has flagged Lever B as the most promising dominant-mode lever. That is exactly the prior that must not leak into the read. Verdicts locked cold:

- **LEVER-B-HAS-PULSE** — at some cap M, `n_rescued(M) ≥ 3` robustly (clears adverse-cost, rescued-at-mean not overshoot), AND aggregate simulated PnL under that cap beats realized. → Lever B's premise is supported on real data: there is a fast-reverting sub-population a hold-cap would have rescued. **Routes to: a live hold-cap experiment is warranted** (designed with the §3.3 exit-interaction complexity, pre-committed criteria, and bundled with the E/C/D hygiene levers). NOT a decision to deploy — a decision that the live test is worth running.
- **LEVER-B-DEAD** — at no cap M does `n_rescued` clear a meaningful bar (e.g. ≤1 robustly-rescued, or aggregate simulated PnL doesn't beat realized at any cap). → The fast-reverting-sub-population hypothesis is **not supported on the data we have**. Shorter holds don't rescue the book; the edge that exists isn't capturable-early on these trades. **Routes to: Lever B is dead for free** — the most promising dominant-mode lever has no pulse, which substantially firms the negative result and pushes toward G (strategy-class pivot) or stop, now *earned*.
- **LEVER-B-AMBIGUOUS** — rescued count is in the noise (1–2, or sensitive to the cost-proxy looseness from §3.2, or rescued-at-overshoot not at-mean). → The data we have can't resolve it; evaluable-N (~13) is thin and the cost proxy is loose. **Routes to: Lever B is neither supported nor killed; a live test would be exploratory rather than evidence-backed**, and the operator weighs whether thin-positive-signal justifies the trading risk. Does NOT route to "collect more data at $200" (refuted) — routes to the operator's judgment on exploratory-vs-stop.

**Anti-rationalization lock (strategist binds self):** I have been advocating Lever B as the soundest dominant-mode lever. If this returns LEVER-B-DEAD, I write "the most promising lever has no pulse, the negative result firms, the honest move is pivot-or-stop" with the same readiness I'd write LEVER-B-HAS-PULSE. The simulation runs to answer whether the fast-reverting sub-population exists, not to vindicate the lever I argued for. Evaluable-N is ~13 with a loose cost proxy — if the signal is thin, AMBIGUOUS is the honest verdict, not a stretch to PULSE.

---

## 5. Discipline guardrails

- **Read-only, no trades, no bot contact, no frozen-variable touch.** Existing CSVs only. Same posture as the fidelity validator and the coint-fragility sampler.
- **No imputation on insufficient-ticks trades** (§3.1) — report evaluable-N honestly; T7 explicitly contributes zero despite being the motivating case.
- **Cost-proxy directionality stated** (§3.2) — realized cost biases against Lever B, so PULSE is robust to it; but funding-share looseness flagged.
- **Pure time-cap, not live-policy** (§3.3) — the simulation tests the *premise*, not a deployable exit rule; the live version is more complex and would need its own design.
- **Rescued-at-mean vs rescued-at-overshoot distinguished** (§3.4) — an overshoot rescue is luck (T5-pattern), not thesis-capture, and must not count toward PULSE.
- **Verdicts locked before the run** (§4) — whichever fires gets written cleanly, including DEAD.

---

## 6. What this pre-test does and does NOT do

**Does:** test, for free on real cent-exact data, whether a fast-reverting sub-population exists that a hold-cap would have rescued — i.e. whether Lever B's premise has empirical support before any live dollar is risked. Resolves the central uncertainty about the most promising dominant-mode lever.

**Does NOT:** prove a live hold-cap would be profitable (live has exit-interaction complexity, different costs, and only ~13 evaluable historical trades); resolve the cost-mechanism question (that's Lever H, separate); address mean-shift on slow-reverting trades (a cap doesn't help those by construction); or re-open the closed experiment (this is preparatory analysis for a *possible* next one).

**Sequencing note:** this is the strategist's recommended FIRST analysis (ahead of Lever H), because it tests the dominant-mode lever's premise, whereas H resolves a secondary (cost-mechanism) question. Both are free/no-trade. Running both before any live decision is the minimal-commitment / maximal-information path. Neither commits to anything.

---

## 7. Action items

**Code assistant:**
- [ ] Confirm §1 data preconditions (snapshot series + recon costs + entry timestamps for T1–T15; flag insufficient-ticks trades).
- [ ] Run the §2 simulation across caps M ∈ {1,2,3,5,8} min; emit per-trade × per-cap table + §2.3 aggregates.
- [ ] Apply §3 handling (no imputation; cost-proxy directionality; pure-time-cap label; z-context per rescued trade).
- [ ] Render one of the §4 pre-committed verdicts; persist as a `docs/audits/` artifact (institutional memory, same as the cost + basis-mismatch diagnostics).
- [ ] If the snapshot cadence is coarser than 1 min on some trades (affecting the M=1,2 caps), report the actual cadence and which caps are evaluable.

**Operator:**
- [ ] Read the verdict; decide whether it routes to a live Lever-B test (PULSE), pivot/stop (DEAD), or a judgment call on exploratory-vs-stop (AMBIGUOUS).

**Strategist:**
- [ ] Read the verdict; write it cleanly per the §4 lock; if PULSE, scope the live hold-cap experiment design (with exit-interaction complexity + hygiene-lever bundling); if DEAD/AMBIGUOUS, update the forward-options reading honestly.

---

*Lever-B offline pre-test work item v1.0. Read-only / analysis-only on existing 15-trade snapshot data. No trades, no bot contact, no frozen-variable touch. Verdicts pre-committed cold (§4) with strategist self-binding anti-rationalization lock. Tests the premise of the most promising dominant-mode lever (shorter hold horizon vs mean-shift) before any live dollar. Inputs: position_snapshots.csv (T1–T15), reconciliation_checks.csv; structural review v1.2 FINAL; the locked mean-shift finding. Sequenced ahead of Lever H per the forward-options synthesis.*
