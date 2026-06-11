# D3 Daily-Bar Cointegration Pre-Test — Verdict 2026-06-11

*Run per work item `docs/prompts/work_item_d3_daily_coint_pretest.md` (v1.0, verdicts LOCKED at commit `77b3dee` before any 1D bar was pulled). Tool: `tools/observation_mode/d3_daily_coint_pretest.py`. Read-only, public 1D klines, no bot contact. The first positive verdict in the program — which is exactly why it received the skeptical pass documented in §3 before being persisted.*

---

## Verdict: **D3-PREMISE-SUPPORTED**

| Locked gate | Bar | Result |
|---|---|---|
| Frozen-β survival @ +10d | ≥ 70% | **82.4%** (1,410 / 1,711) |
| Frozen-β survival @ +20d | ≥ 50% | **66.1%** (1,131 / 1,711) |
| N-guard: observations @ +10d | ≥ 30 | **1,711** |
| N-guard: distinct pairs | ≥ 8 | **672** |
| Part B: median 2σ dollar edge of survivors | ≥ $2.22 | **$24.17** |
| DEAD trigger: survival @ +10d | ≤ 40% | not fired (82.4%) |

**Survival decay curve (pooled, frozen-β, p ≤ 0.20):** +5d: 90.2% → +10d: 82.4% → +20d: 66.1%. Monotone decay — the internal-consistency signature of real persistence eroding with horizon, not a flat artifact.

**Edge vs cost stacks (Part B):** median 2σ reversion edge $24.17 at $200 gross vs 10-day stacks of $0.44 / $0.74 / $1.94 (funding at 0.005% / 0.01% / 0.03% per 8h) → **54.9× / 32.7× / 12.5×**. At daily scale the edge/cost ratio structurally inverts the minute-scale problem: minute-scale edges (~$0.10) sat *below* the ~$0.14 stack; daily-scale edges sit 12–55× *above* it.

**Context (reported, not gated):** refit-β survival @ +10d = 76.7%; median |β drift| @ +10d = 4.9% (small — Query 2's minute-scale β-stability finding extends to daily scale).

---

## 1. What was run

- **Universe:** 46 instruments from the bot's monitored pairs during the exp_beta window; 2 dropped for insufficient 1D history (CAT: 0 bars, CRCL: 105) → 44 qualified, 946 pairs with sufficient overlap.
- **Data:** up to 400 confirmed 1D bars per instrument (≈ May 2025 → 2026-06-10), cached at `tools/observation_mode/output/kline_cache_1d/`.
- **Walk-forward:** 120-bar discovery windows stepping every 20 days; **15,683 total (pair, fold) cointegration tests**; 1,711 discovery passes (EG p ≤ 0.05).
- **Gated quantity:** frozen-β survival — discovery β and intercept held fixed (a held position's hedge is frozen; this is the daily-scale analogue of the mean-shift exposure that killed MR), spread re-tested by plain ADF (p ≤ 0.20 = not-broken, mirroring the monitor's broken threshold) on the 120-bar window ending +H days later.

## 2. Honesty notes on the discovery population

- **Discovery pass rate: 10.9% (1,711 / 15,683) vs 5.0% null-expected.** Roughly 2.2× the null rate — meaning under a worst-case reading, up to ~half of marginal discoveries could be spurious. The survival metric is the protection, and §3's null-baseline check confirms it discriminates.
- **Survival is flat across discovery strength:** p ≤ 0.01 discoveries survive at 82.3%, marginal (0.01 < p ≤ 0.05) at 82.5%. Raised as a concern (could have indicated the survival test was insensitive); resolved by the null baseline below — the honest residual reading is that discovered relationships are roughly equally persistent regardless of marginal discovery-p.

## 3. The skeptical pass (run before persisting — this was the program's first wanted answer)

**Concern: window overlap could make survival mechanical.** The +10d survival window shares 110/120 bars with the discovery window (92%); +20d shares 100/120. A spurious discovery might "survive" simply because the re-test window is nearly the same data.

**Discriminating check — null baseline:** the identical frozen-β procedure run on the **discovery-FAILING population** (p > 0.05 at discovery; same windows, same OLS β, same ADF, same threshold; 35% deterministic fold sample, n = 4,934):

| Population | Survival @ +10d |
|---|---|
| Discovery-passing pairs (the gated result) | **82.4%** |
| Discovery-failing pairs (null baseline) | **39.0%** |

**43-point separation.** If the 82.4% were window mechanics, the null population would shadow it — instead it lands at 39%, almost exactly the 40% DEAD bar (the minute-scale analogue). Two readings stack: (a) the survival signal is real, not overlap artifact; (b) non-cointegrated daily pairs behave like the minute-scale universe did, while discovered daily pairs more than double that persistence — the timescale hypothesis's claim in one comparison.

**Remaining methodological note (carried, not resolved):** the gated quantity is *rolling persistence* (windows overlap, as the bot's live monitor's windows do), not disjoint out-of-sample persistence. For a 5–20 day hold this is the deployment-relevant quantity — a swing position experiences exactly this rolling re-test. A fully disjoint test (+120d) would answer a different, stronger question (long-run relationship stability) and belongs to the design phase if wanted.

## 4. Mandatory caveats (locked into the SUPPORTED verdict)

1. **Funding is assumption-based** ({0.005, 0.01, 0.03}%/8h grid, not pulled funding history; real rates vary and can be received). Even at the harshest assumption the edge multiple is 12.5×, which is why the gate clears robustly — but a design phase should pull real funding history.
2. **Survival ≠ profitability.** 82.4% of relationships staying un-broken says nothing about entry timing, reversion capture rate, slippage at daily-scale order sizes, or how often |z| ≥ 2 entries materialize.
3. **The 2σ edge proxy is an upper bound on per-trade capture** — no strategy captures a full 2σ→mean reversion. The 12–55× headroom is what makes the premise robust to realistic capture fractions (even 20% capture leaves 2.5–11×).
4. **This is premise-support, not a backtest.** No entries, exits, position management, or cost realism were simulated.

## 5. What SUPPORTED routes to (per the locked work item)

**D3 experiment design scoping** — a new, separate decision for the operator. The design phase would need: entry/exit spec at daily scale, paper-vs-live call, real funding-history pull, slippage realism at daily order sizes, the sample-accumulation timeline (multi-day holds ⇒ weeks-to-months per 15–20 trades), the full pre-commit apparatus (success/null criteria, kill-criterion, negative-result bar), and the hygiene carryovers from the closed experiment (basis alignment N/A at daily scale by construction; H1 β-sizing transfers; circuit-breaker scale-up note applies if sessions become multi-trade).

**What this verdict does NOT do:** authorize any live or paper trading; validate a specific strategy design; estimate realistic per-trade PnL; or override the operator's standing options (design D3 / pivot class / stop — all remain open; this verdict moves D3 from "premise untested" to "premise supported at the pre-test level").

---

*D3 pre-test artifact, 2026-06-11. Verdict SUPPORTED per locked gates (commit `77b3dee`); skeptical pass passed (null-baseline separation 82.4% vs 39.0%). Data: `tools/observation_mode/output/d3_pair_fold_results.csv` (1,711 observations; regenerable) + `kline_cache_1d/` (gitignored). The lock direction said borderline resolves down; this was not borderline — every gate cleared with multiples to spare, and the one wanted-answer risk (overlap mechanics) was tested and excluded.*
