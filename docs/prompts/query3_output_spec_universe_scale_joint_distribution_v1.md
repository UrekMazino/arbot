# Query-3 Output Spec — Universe-Scale Joint (In-Zone-Edge, Cost) Distribution
## Resolves the E4 rate AND the cost-too-high vs edge-too-thin fork. One instrument, two questions.

**Task class:** DIAGNOSTICS-ONLY build (shadow pipeline; order placement stubbed). No live order ever placed. No frozen variable changed. Live collection (exp_beta_aware_sizing_v1) continues in parallel and is unaffected. **Gated on operator go-ahead** (real engineering cost) — this spec is what gets built *if* authorized.

**Drafted:** 2026-05-29, after T6 (run 132) + premise-check. Counter 6/20, 3 $/σ-eligible.
**Owner split:** Strategist specifies (this doc). Code assistant builds the shadow harness + instrumentation and runs it. Operator authorizes the build and the run.

---

## 0. Why this instrument, and what the premise-check corrected

The cost-too-high vs edge-too-thin fork (structural-review template §6/§7) was to be resolved by the refined §7 cost diagnostic (residual vs effective half-spread). **§7-as-specified is dead without new data plumbing** — effective half-spread is not in any telemetry (only depth in `liquidity_checks.csv`; no orderbook snapshot; OHLC klines have no bid/ask). And the cheap fallbacks do not resolve the fork:

- **Premise-check result (2026-05-29, DECISIVE):** the hypothesis "eligible trades are the liquid-major cost floor, and still don't clear → edge-too-thin" is **FALSE.** Sorted by `real_cost` over 19 reliable trades, the 3 eligible trades rank **#3 ($0.100 AVAX/DOT), #15 ($0.194 SOL/AVAX), #17 ($0.251 LTC/KSM)** — two in the expensive half, one near the top (3rd-priciest overall, behind only meme pairs FIL/ICP $0.395 and JUP/YGG $0.534). The cheapest trade in the set is **T9c LINEA/ZRO $0.067 — a thin-leg pair, not a pure-major** (Item-12 counterexample re-confirmed). **Cost is pair-specific, NOT liquidity-tier-ordered** (has-thin-leg pairs appear at both ends $0.067 and $0.395; pure-majors cluster $0.10–$0.19).
- **What survives (weaker, two-sided):** the cheapest *observed* execution ($0.067) still exceeds the ~$0.03 in-zone thesis edge — but that is an **N=3 claim about the edge**, and eligible costs span 2.5× ($0.10→$0.25), so there is **real headroom to push costs toward the floor.** Cost-too-high is **not** dead.

**Therefore the fork is genuinely unresolvable from N=3** (costs pair-specific with headroom; in-zone edge under-sampled at 3 trades). It needs the **joint distribution of (in-zone dollar-capture, real cost) at scale** — which is precisely what a shadow run produces if it logs `pnl_at_mean` + cost components per shadow entry on the real universe the bot actually selects. This spec specifies that.

**Held honestly:** the strategist's edge-too-thin lean is **retracted** as a near-verdict (its clean argument failed at the premise-check). This study is built to let N=hundreds overrule the N=3 lean **in either direction** — if a meaningful subset shows in-zone capture clearing costs, it is cost-too-high after all.

---

## 1. The two questions this instrument answers

**Q-A — E4 universe rate (the §4 kill-criterion question, at scale).**
Is the live 50–75% coint-failure rate the true universe rate, or small-sample noise off the ~40% baseline? E4 currently can't evaluate until 10 live closes (~weeks at one-trade-per-session). The shadow run reaches N=hundreds in days.
→ Output: coint-failure rate with CI; rate by structural category; trend vs the 40% baseline.

**Q-B — cost-too-high vs edge-too-thin (the Branch-2 sub-lever fork).**
Across many entries, what is the joint distribution of **in-zone dollar-capture** vs **real cost**? Three mutually exclusive outcomes, pre-committed:
- **EDGE-TOO-THIN** — in-zone capture distribution sits below *even the cheapest achievable* cost across essentially all pairs → no cost lever closes the gap → **§5 negative-result bar.** Next move: hold-horizon rethink, strategy-class change, or stop. NOT a cost intervention.
- **COST-TOO-HIGH** — a meaningful subset shows in-zone capture that *would* clear cost if execution were pushed toward the observed floor (~$0.067) → **Branch 2 cost levers (maker §8, spread/pair gating).** Next move: cost-reduction experiment on the qualifying subset.
- **MIXED / SUBSET-VIABLE** — a specific identifiable subset (by structural category, β band, or volatility-to-cost ratio) clears; the rest doesn't → universe-restriction finding (the graveyarding on measured footing). Next move: gate the universe to the viable subset, re-test.

→ Output: the joint scatter + the pre-committed classification.

**Both from one run.** Q-A and Q-B share every shadow entry; the instrumentation below serves both.

---

## 2. Build: shadow pipeline (3b), not historical replay (3a)

**Decision: 3b shadow, locked** (operator may override). Rationale: the fork resolution depends on `pnl_at_mean` and in-zone capture computed from the *actual* z-trajectory the live signal logic produces. A historical replay re-implements that signal logic and reintroduces exactly the divergence risk Query 2 hit (bar-close z couldn't reproduce live intrabar z — the price-vs-mean attribution % was unreliable as a result). The shadow path runs the **real discovery/signal/monitoring pipeline** with only order placement stubbed → no re-implementation, no look-ahead, no z-reconstruction error. Slower per-entry than replay but faithful, and freed from `max_session_trades=1` and the circuit breaker it generates entries fast enough.

**Stub boundary (critical — defines "no live order ever"):**
- Replace the order-placement calls (`place_market_order` / `initialise_order_execution` order legs) with a **stub** that records intended legs (ticker, side, notional from β-sizing) and returns a synthetic fill at the current mark, **without touching the exchange.**
- Everything *upstream* of placement runs live and real: pair discovery, all hard-validation gates (cointegration, ADF, zero-crossings, hedge-ratio sanity, liquidity freshness, order capacity), β-sizing, the entry safety gate, the monitoring loop, z computation, and the exit logic (coint-watch, full_tp guard, profit-lock, regime-break).
- **The position is virtual**: PnL is marked from live klines/marks over the virtual hold; exits fire from the real exit logic against the virtual position.
- **No `.env` live-trading flag, no notional change, no credential with trade permissions** in the shadow process. Read-only market-data access only. Confirm the shadow process literally cannot place an order (separate key / explicit stub assertion).

**Frozen-config integrity:** the shadow run uses the **same frozen config** as live (same gates, thresholds, window, β-sizing, $200 notional). It is an observation harness over the existing strategy, not a parameter search. **No fitting** (see §5).

---

## 3. Instrumentation — per shadow entry (this is what resolves the fork)

For **every** shadow entry that clears the gates and "fills" (virtually), log a row. The in-zone-capture fields are the fork-resolving additions beyond a plain rate study:

| Field | Definition | Serves |
|---|---|---|
| `shadow_entry_id`, `pair`, `entry_ts` | identity | both |
| `beta`, `leg1_notional`, `leg2_notional` | β-sizing output (gross=$200 conserved) | Q-B (β-band analysis) |
| `entry_z` | z at virtual fill | both |
| `structural_category` | {liquid-major, thin-alt, meme/reflexive} — tag by the same rule used in the audit | both |
| **`pnl_at_mean`** | **virtual unrealized PnL at the snapshot where \|z\| is minimal; interpolate to z=0 if the trajectory straddles it** | **Q-B (THE fork number)** |
| **`pnl_at_zone_entry`** | **virtual PnL at the FIRST snapshot with \|z\|<0.35 (what a disciplined mean-exit captures)** | **Q-B** |
| **`max_in_zone_capture`** | **max virtual PnL over all snapshots with \|z\|<0.35** | **Q-B (the +$0.0067 analogue — sharpest in-zone number)** |
| `mfe`, `z_at_mfe` | max virtual PnL and the z at which it occurred (flags overshoot profit) | Q-B (overshoot vs thesis discrimination) |
| `pnl_at_exit` | virtual PnL at the exit snapshot (≈ realized gross, virtual) | both |
| `exit_reason` | from the real exit logic (normal / trailing_stop / profit_lock / cointegration_lost / cointegration_watch_timeout / regime_break) | both |
| `delta_z` | \|entry_z − z_at_exit\| | eligibility (apply \|Δz\|≥0.5 per Classification-A rule) |
| `hold_duration_s`, `n_snapshots` | trajectory completeness | QC |
| **`est_real_cost`** | **modeled cost for this pair (see §3.1) — the cost axis of the joint distribution** | **Q-B (THE cost axis)** |
| `cost_basis` | how `est_real_cost` was derived (model vs per-category empirical) | Q-B honesty |

**Eligibility for the Q-B distribution (mechanical, inherits Rule v1.2 + the |Δz| precondition):** a shadow entry enters the in-zone-capture distribution only if `exit_reason ∈ {normal, trailing_stop, profit_lock}` AND `mfe > 0` AND `|Δz| ≥ 0.5`. Coint-failure shadow exits go to the **Q-A rate tally**, never the Q-B distribution (same reason as live: β ceased to be the right hedge mid-hold; no exit captures an absent in-zone edge). This keeps the two questions cleanly separated on one run.

### 3.1 The cost axis — the honest limitation, and how to handle it

The shadow run **cannot measure real taker fills** — that is a live-only truth (the 1.0×–1.8×–3.8× overruns come from real execution). So `est_real_cost` is *modeled*, and the joint distribution's cost axis is an estimate, not ground truth. Handle it explicitly:

- **Primary cost model:** per-structural-category empirical cost, calibrated from the **19 real live trades' `real_cost`** (the premise-check data): e.g. liquid-major ≈ $0.10–0.19 band, thin-alt and meme wider and higher. Apply the category's empirical distribution (not a flat $0.14) to each shadow entry by its category.
- **Sensitivity bands:** report Q-B under three cost assumptions — (i) category-empirical median, (ii) the observed **floor $0.067** (best achievable), (iii) category-empirical 75th percentile (conservative). The fork's answer may be robust across bands (decisive) or flip between them (then the answer is "depends on achievable cost" → cost-too-high is live and the §8 maker test matters).
- **This is why the §2 forward-spread-logging rider matters:** if it's added to live, future real trades sharpen the cost model and tighten these bands. Opportunistic, not blocking.

**Stated plainly in the output:** "the in-zone-capture (x) is faithfully simulated from real signal logic; the cost (y) is modeled from live-trade empirics with sensitivity bands — the x-axis is solid, the y-axis is an estimate with stated uncertainty." Do not present the cost axis as measured.

---

## 4. Analysis & outputs

**Q-A (rate):**
- Coint-failure rate over all shadow entries, with binomial CI; N stated.
- Rate by structural category and by β band.
- Comparison to the 40% lifetime baseline and the live 50–75% window — is the live rate within the shadow CI (→ small-sample, E4 unlikely to fire on a true-rate basis) or genuinely elevated (→ universe fragility is real)?

**Q-B (fork) — the joint distribution:**
- Scatter: **x = `max_in_zone_capture` (and `pnl_at_mean`), y = `est_real_cost`** (with the three cost bands), one point per Q-B-eligible shadow entry, colored by structural category.
- The **diagonal** `in_zone_capture = cost` is the viability line. Points above clear costs; points below don't.
- **Pre-committed classification (which outcome §1 Q-B):**
  - essentially all points below the line **even at the $0.067 floor band** → **EDGE-TOO-THIN** → §5 negative bar.
  - a meaningful mass above the line **at achievable (floor/median) cost** → **COST-TOO-HIGH** → Branch-2 cost levers.
  - a category/β-identifiable subset above, rest below → **SUBSET-VIABLE** → universe restriction; name the subset.
- Report the **fraction of eligible entries clearing cost** under each band, with CI.
- **Overshoot check:** fraction of `mfe` occurring at `|z_at_mfe| > 0.35` (anti-thesis momentum) vs in-zone — confirms or refutes at scale the N=3 finding that the profit lives in the overshoot. If most MFE is overshoot, that independently reinforces edge-too-thin *for the thesis exit* regardless of cost.

**Joint read:** Q-A and Q-B together answer the experiment's central question — *does any tradeable subset of this universe hold relationships stably enough (Q-A) AND traverse enough in-zone dollar-spread to clear achievable costs (Q-B)?* If both come back negative, that is a clean, fast, money-saving **negative result** (change horizon/universe/strategy-class or stop — do NOT keep collecting live). If either identifies a viable subset, that subset is the next experiment's universe, on measured footing.

---

## 5. Discipline guardrails

- **Measure, do not fit.** This is an observation harness over the **frozen** strategy on the **real** universe. It does **not** search pairs/parameters for what worked. The subset identification in Q-B is descriptive (which categories/β-bands clear), validated out-of-sample before any universe-restriction decision — selecting the historically-best pairs is the overfit trap this project avoids.
- **Cost axis is modeled, not measured** (§3.1). Real costs stay a live-only instrument; live collection continues in parallel as that instrument. The sensitivity bands carry the uncertainty honestly.
- **Refuted-lever guardrail.** Any stability/selection signal that emerges must **not** be an entry-time cointegration metric (slope or level) — both refuted (exp_coint_stability Verdict 10B; T1/T3/T4 entered benign and failed). Surviving levers are post-entry (exit-speed), structural (universe/horizon), architectural (re-hedge — though Query 2 ruled β-drift out on the 2 clean holds).
- **N-discipline carries forward.** The shadow run gives large N, but the **cost axis uncertainty** and the **survivorship caveat** (today's universe ≠ a historical one — though shadow-forward mitigates this vs replay) bound the conclusion. State CIs; state which cost band drives the classification.
- **Stub integrity is a safety property.** The shadow process must be provably incapable of placing a live order (separate read-only market-data key; explicit stub assertion; no trade-permissioned credential). Verify before the first run.

---

## 6. What this feeds / decision wiring

- **§4 E4:** Q-A resolves the universe-rate question at scale — potentially settling whether E4 would fire on a *true-rate* basis before the live counter reaches 10 closes.
- **§6 Branch selection:** Q-B resolves the cost-too-high vs edge-too-thin fork → picks the Branch-2 sub-lever (cost experiment) OR routes to the §5 negative-result bar OR identifies a viable subset.
- **§7 cost diagnostic:** superseded for fork-resolution by Q-B's joint distribution (since §7-precise is data-blocked); the §2 forward-spread-logging rider revives §7-precise *later* only if Q-B is cost-band-sensitive.
- **§8 maker experiment:** authorized only if Q-B returns COST-TOO-HIGH or SUBSET-VIABLE *and* the cost band shows real headroom — i.e., only if reducing cost plausibly crosses the viability line. If Q-B returns EDGE-TOO-THIN, the maker build is **not** pursued (it can't save an edge that isn't there).

---

## 7. Action items

**Operator:**
- [ ] Authorize the query-3 shadow build (engineering cost) and the run. **[GO/NO-GO — this is the gate.]**
- [ ] Confirm 3b shadow over 3a replay (or override).
- [ ] Decide whether to add the §2 forward orderbook-spread-at-entry logging rider to live (cheap, logging-only, frozen-safe; sharpens the cost model for future trades). Opportunistic.

**Code assistant (if authorized):**
- [ ] Build the shadow harness: stub the order-placement boundary (§2), verify the process cannot place a live order (§5 stub integrity).
- [ ] Wire the §3 per-entry instrumentation, including the in-zone-capture fields (`pnl_at_mean`, `pnl_at_zone_entry`, `max_in_zone_capture`, `mfe`/`z_at_mfe`) and `est_real_cost` from the §3.1 category model.
- [ ] Calibrate the §3.1 cost model from the 19 live trades' `real_cost` (premise-check data).
- [ ] Run to N≥ [several hundred] eligible entries; emit Q-A (rate + CI) and Q-B (joint scatter + pre-committed classification + cost-band sensitivity).
- [ ] (rider, if operator opts in) add forward spread-at-entry logging to live.

**Strategist:**
- [ ] Read Q-A + Q-B; update the structural-review template — resolve §6 to a branch (or to §5 negative bar), and record the E4 universe-rate finding. Produce the branch-specific next-experiment spec.

---

*Query-3 output spec v1.0. Diagnostics-only (shadow; no live order). No frozen variable changed; live collection unaffected. Incorporates the 2026-05-29 premise-check correction (eligible set is NOT the cost floor; cost is pair-specific, not tier-ordered; edge-too-thin lean retracted as a near-verdict). Resolves Q-A (E4 rate) and Q-B (cost-vs-edge fork) on one instrument. Inputs: per-run audit runs 125–132 (T1–T6); analysis_spec_pnl_vs_z_decoupling_v1; structural_review_exp_beta_aware_sizing_v1_template_v1 v1.2; premise-check (real_cost ranks over 19 reliable trades).*
