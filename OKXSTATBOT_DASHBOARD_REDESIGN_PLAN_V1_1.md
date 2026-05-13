OKXStatBot Dashboard Redesign Implementation Plan v1.1
Portfolio + Analytics + Pair History + Pair Detail + Risk & Health

================================================================================
PURPOSE
================================================================================

This document is a step-by-step Codex implementation plan for redesigning the
OKXStatBot dashboard area into focused analytics and review pages.

Current completed foundation:

- Chart Decision Audit Phase 1: Actual Bot Decision Overlay
- Chart Decision Audit Phase 2: Curator-Aware Point-In-Time Replay
- Chart Decision Audit Phase 2.25: Hedge-Ratio Exposure Alignment
- Chart Decision Audit Phase 2.5: Advanced ML Replay Integration
- Chart Decision Audit Phase 3: Counterfactual Exit Study
- Chart Decision Audit Phase 4: Decision Score Timeline

Goal:

Build dashboard pages that answer:

- Is the bot profitable?
- Which pairs work?
- Which pairs fail?
- Why did the bot enter?
- Why did the bot block?
- Was the exit good?
- Did hedge-ratio sizing help?
- Did ML scores actually predict outcomes?
- Is the bot safe right now?

Target pages:

1. Portfolio Dashboard
2. Analytics Dashboard
3. Pair History / Pair Review Page
4. Pair Detail / Chart Audit Page
5. Risk & Health Dashboard
6. Trade Review Page, optional
7. Navigation/sidebar updates

Core implementation rule:

Dashboard work must be read-only analytics and visualization only.

Do not:
- change live trading behavior
- submit orders
- modify order execution
- modify strategy logic
- introduce new ML logic
- infer fake data when unavailable

Unavailable metrics should return null or empty arrays, not guessed values.

================================================================================
V1.1 PATCH NOTES — REVIEWER IMPROVEMENTS APPLIED
================================================================================

This v1.1 version applies the requested reviewer improvements:

1. Chart Audit Contract Verification

The Chart Audit v1.4 system is already implemented, so no stub is needed.
Instead, add a verification prompt that confirms dashboard pages can consume:

- actual_markers
- replay_markers
- counterfactual lazy endpoint
- decision_score_timeline
- decision_timeline_meta
- hedge-ratio metadata

2. Portfolio Dashboard Prompts Added

The previous plan referenced PortfolioSummary and navigation to Portfolio, but
did not include backend/frontend prompts.

Added:

- Prompt 1.5 — Portfolio Dashboard Backend
- Prompt 1.6 — Portfolio Dashboard Frontend

3. Caching / Refresh Rules Added

Pair History and Analytics aggregations can become expensive.

Added:

- Pair History cache TTL: 5 minutes
- Analytics cache TTL: 15 minutes
- Portfolio cache TTL: 30 to 60 seconds
- Risk & Health cache TTL: 15 to 30 seconds
- refresh=true to force recompute

4. significant_only Definition Added

Pairs are significant if they meet any configured threshold:

- abs(net_pnl_usdt) >= significant_pnl_threshold
- total_trades >= significant_trade_count_threshold
- abs(max_drawdown_usdt) >= significant_drawdown_threshold
- best_trade.pnl_usdt >= significant_trade_threshold
- worst_trade.pnl_usdt <= -significant_trade_threshold

Default thresholds:

- significant_pnl_threshold = 5.0
- significant_trade_count_threshold = 5
- significant_drawdown_threshold = 5.0
- significant_trade_threshold = 2.0

5. ExitOrchestratorEvent Availability Fallback Added

Some analytics metrics require Exit Orchestrator logs.

If ExitOrchestratorEvent logs are unavailable:

- return null or empty exit_analysis fields
- do not invent exit policy distribution from unstructured logs

6. ML Field Availability Warning Added

Fields such as:

- regime_at_entry
- final_rank_score_at_entry
- bayesian_posterior_at_entry

are nullable and may remain null until the advanced ML pipeline has stored enough
historical score data.

7. Risk Alert Deduplication Added

Risk & Health alerts should be deduplicated by:

(type, pair)

within a configurable window:

default_alert_dedup_window_minutes = 30

Show:

- latest_timestamp
- occurrence_count

8. Prompt Prerequisite Checklists Added

Each major prompt includes prerequisites so Codex does not assume missing systems exist.

================================================================================
RECOMMENDED IMPLEMENTATION ORDER
================================================================================

Use this order:

1. Prompt 0 — Read-only dashboard architecture audit
2. Prompt 0.5 — Verify Chart Audit endpoint contracts
3. Prompt 1 — Shared dashboard DTO/contracts
4. Prompt 1.5 — Portfolio Dashboard backend
5. Prompt 1.6 — Portfolio Dashboard frontend
6. Prompt 2 — Pair History backend
7. Prompt 3 — Pair History API endpoint
8. Prompt 4 — Pair History frontend
9. Prompt 5 — Pair Detail backend
10. Prompt 6 — Pair Detail / Chart Audit page
11. Prompt 7 — Analytics backend
12. Prompt 8 — Analytics frontend
13. Prompt 9 — Risk & Health backend
14. Prompt 10 — Risk & Health frontend
15. Prompt 11 — Navigation/sidebar update
16. Prompt 12 — Final integration and regression check

Do not start with the Analytics Dashboard first.

Start with Pair History after shared contracts and Portfolio because Pair History
becomes the main doorway into the Chart Audit system.

================================================================================
PROMPT 0 — READ-ONLY DASHBOARD ARCHITECTURE AUDIT
================================================================================

Read the current repository.

Context:
The Chart Decision Audit system is complete through:

- Phase 1: Actual Bot Decision Overlay
- Phase 2: Curator-Aware Point-In-Time Replay
- Phase 2.25: Hedge-Ratio Exposure Alignment
- Phase 2.5: Advanced ML Replay Integration
- Phase 3: Counterfactual Exit Study
- Phase 4: Decision Score Timeline

Goal:
Redesign the analytics area into focused dashboards/pages.

Target pages:

1. Portfolio Dashboard
2. Analytics Dashboard
3. Pair History / Pair Review Page
4. Pair Detail / Chart Audit Page
5. Risk & Health Dashboard
6. Trade Review Page, optional
7. Navigation/sidebar updates

Do not write code yet.

Audit the existing codebase and return:

1. Existing dashboard pages and routes
2. Existing API endpoints related to:
   - bot status
   - trades
   - pairs
   - logs
   - chart audit
   - counterfactuals
   - decision timeline
   - risk/health
3. Existing reusable frontend components:
   - cards
   - tables
   - charts
   - filters
   - badges
   - tabs
   - modals/drawers
4. Existing backend data sources for:
   - actual trades
   - pair stats
   - pair health
   - hospital/graveyard
   - PnL
   - hedge ratio
   - counterfactual exit studies
   - replay markers
   - decision score timeline
5. Existing route list that must be preserved
6. Existing permission/access-control patterns
7. Recommended implementation order
8. Files to create
9. Files to modify
10. Risks
11. Tests to add

Strict rules:
- Do not change live trading behavior.
- Do not touch order execution.
- Do not modify bot strategy logic.
- Do not introduce new ML logic.
- Dashboard work must be read-only analytics/visualization only.

================================================================================
PROMPT 0.5 — VERIFY CHART AUDIT ENDPOINT CONTRACTS
================================================================================

Prerequisites:
- Prompt 0 complete
- Chart Decision Audit through Phase 4 already implemented

Read the completed Chart Decision Audit implementation.

This is not a stub prompt. The Chart Audit v1.4 system should already exist.

Do not write code unless fixing a clearly identified contract mismatch.

Verify that the dashboard pages can consume the following contracts:

1. Pair chart audit endpoint returns:
   - zscore_series
   - statistical_markers
   - replay_markers
   - actual_markers
   - counterfactual_exit_studies = [] on initial load
   - counterfactuals_lazy_load = true
   - decision_score_timeline when requested
   - decision_timeline_meta

2. Replay markers include:
   - replay marker status
   - block reasons
   - curator state/source
   - config source
   - ML metadata
   - hedge-ratio metadata

3. Actual markers include:
   - trade_id
   - side
   - z_score
   - spread
   - PnL
   - fees
   - slippage
   - reason
   - hedge-ratio sizing metadata when available

4. Counterfactual lazy endpoint supports:
   - entry_id
   - pair
   - timeframe
   - start_ts
   - end_ts

5. Decision timeline supports:
   - include_decision_timeline
   - max_timeline_points
   - downsample_method
   - resolution

6. Frontend API types exist or need updates.

Return:

- verified endpoints
- missing or mismatched fields
- files to adjust, if any
- whether Pair Detail page can safely reuse existing chart audit components

Strict rules:
- Do not create stub data.
- Do not invent chart audit fields.
- Do not change live trading behavior.
- Do not modify order execution.

================================================================================
PROMPT 1 — SHARED DASHBOARD DATA CONTRACTS
================================================================================

Prerequisites:

- Prompt 0 complete
- Prompt 0.5 complete
- Existing route/API/component inventory known

Implement shared dashboard data contracts only.

Do not build pages yet.
Do not modify live trading behavior.
Do not touch order execution.

Create or update backend DTOs/types for:

1. PairSummary
2. TradeSummary
3. PairPerformanceSummary
4. ReplaySignalSummary
5. CounterfactualSummary
6. DecisionScoreSummary
7. HedgeRatioSummary
8. RiskEventSummary
9. PortfolioSummary
10. AnalyticsSummary
11. DashboardCacheMeta

Each PairSummary should include:

- pair
- status
- total_trades
- net_pnl_usdt
- realized_pnl_usdt
- unrealized_pnl_usdt
- win_rate
- profit_factor
- max_drawdown_usdt
- avg_hold_seconds
- avg_entry_z
- avg_exit_z
- avg_hedge_ratio
- avg_hedge_drift_pct
- hospital_count
- graveyard_count
- block_reason_counts
- best_trade
- worst_trade
- last_traded_at
- tags

Each TradeSummary should include:

- trade_id
- pair
- side
- entry_time
- exit_time
- entry_z
- exit_z
- hold_seconds
- pnl_usdt
- fees_usdt
- slippage_usdt
- exit_reason
- entry_hedge_ratio
- exit_hedge_ratio
- hedge_ratio_drift_pct
- regime_at_entry
- final_rank_score_at_entry
- bayesian_posterior_at_entry

Important:
ML score fields are nullable and may remain null until the advanced ML pipeline
has stored enough historical score data.

Tags should support:

- elite
- stable
- warning
- hospital
- graveyard
- high_drift
- high_slippage
- good_reverter
- bad_executor
- high_break_risk
- profitable
- losing

Frontend TypeScript types should mirror backend response shapes.

Files to consider:
- core/dashboard/
- core/chart_audit/
- Platform/web/lib/api.ts

Add tests for:
- DTO serialization
- default/null handling
- tag enum/string consistency
- cache metadata serialization

Run:
python -m compileall core
npm run lint

================================================================================
PROMPT 1.5 — PORTFOLIO DASHBOARD BACKEND
================================================================================

Prerequisites:

- Prompt 1 complete
- PortfolioSummary DTO exists
- Bot status / open positions / PnL sources identified by Prompt 0

Implement Portfolio Dashboard backend service.

Goal:
Create the high-level monitoring summary page data.

Create:

core/dashboard/portfolio_service.py

Add function:

get_portfolio_dashboard(
    start_ts=None,
    end_ts=None,
    refresh=False,
)

Return:

{
  "summary": {
    "total_equity_usdt": null,
    "session_pnl_usdt": null,
    "realized_pnl_usdt": null,
    "unrealized_pnl_usdt": null,
    "win_rate": null,
    "profit_factor": null,
    "max_drawdown_usdt": null,
    "open_positions": null,
    "active_pair": null,
    "bot_status": null,
    "open_exposure_usdt": null
  },
  "charts": {
    "equity_curve": [],
    "daily_pnl": [],
    "drawdown_curve": [],
    "open_exposure": []
  },
  "highlights": {
    "best_performing_pair": null,
    "worst_performing_pair": null,
    "most_traded_pair": null,
    "highest_drawdown_pair": null,
    "current_regime_state": null,
    "current_risk_level": null
  },
  "cache": {
    "cache_hit": false,
    "generated_at": 0,
    "ttl_seconds": 60
  }
}

Caching:
- cache results for 30 to 60 seconds
- support refresh=true to force recompute

Rules:
- Return null for unavailable metrics.
- Read-only only.
- Do not touch order execution.
- Do not change bot behavior.

Tests:
- summary aggregation
- missing data returns null
- cache hit/miss
- refresh=true bypasses cache

Run:
python -m compileall core

================================================================================
PROMPT 1.6 — PORTFOLIO DASHBOARD FRONTEND
================================================================================

Prerequisites:

- Prompt 1.5 complete
- Portfolio Dashboard backend endpoint available or service route known
- Existing dashboard route conventions known

Implement Portfolio Dashboard frontend page.

Route example:

Platform/web/app/admin/dashboard/portfolio/page.tsx

or use the existing admin route convention.

Goal:
Show the high-level bot status and portfolio performance.

Top KPI cards:

- Total Equity
- Session PnL
- Realized PnL
- Unrealized PnL
- Win Rate
- Profit Factor
- Max Drawdown
- Open Positions
- Active Pair
- Bot Status

Charts:

- Equity curve
- Daily/session PnL
- Drawdown curve
- Open exposure

Highlights:

- Best performing pair
- Worst performing pair
- Most traded pair
- Highest drawdown pair
- Current regime state
- Current risk level

Rules:
- Use existing UI components where possible.
- Handle null/unavailable metrics cleanly.
- Add loading/empty/error states.
- Do not change live trading behavior.

Update Platform/web/lib/api.ts with:
- PortfolioDashboardResponse type
- getPortfolioDashboard(params)

Run:
npm run lint
npm run build

================================================================================
PROMPT 2 — BACKEND SERVICE FOR PAIR HISTORY
================================================================================

Prerequisites:

- Prompt 1 complete
- PairSummary DTO exists
- Trade/pair data sources identified
- significant_only thresholds confirmed

Implement backend service for Pair History / Pair Review.

Goal:
Create a service that aggregates pair-level performance so the user can review
pairs with significant wins/losses.

Do not build frontend page yet.
Do not modify live trading behavior.

Create:

core/dashboard/pair_history_service.py

Add function:

get_pair_history_summary(
    start_ts=None,
    end_ts=None,
    status=None,
    pnl_filter=None,
    min_trade_count=None,
    min_win_rate=None,
    max_win_rate=None,
    regime=None,
    hedge_drift_filter=None,
    significant_only=False,
    search=None,
    sort_by="net_pnl_usdt",
    sort_dir="desc",
    page=1,
    page_size=50,
    refresh=False,
)

Return:

{
  "rows": [PairSummary],
  "meta": {
    "page": 1,
    "page_size": 50,
    "total_rows": 123,
    "total_pages": 3,
    "sort_by": "net_pnl_usdt",
    "sort_dir": "desc"
  },
  "kpis": {
    "total_pairs": 0,
    "tradable_pairs": 0,
    "profitable_pairs": 0,
    "losing_pairs": 0,
    "hospital_pairs": 0,
    "graveyard_pairs": 0
  },
  "cache": {
    "cache_hit": false,
    "generated_at": 0,
    "ttl_seconds": 300
  }
}

Must aggregate:

- total trades
- net PnL
- win rate
- profit factor
- max drawdown
- best trade
- worst trade
- average hold time
- average entry/exit Z
- average hedge ratio
- hedge drift events
- hospital/graveyard counts
- most common block reason
- last traded timestamp

significant_only definition:

A pair is significant if any of these are true:

- abs(net_pnl_usdt) >= significant_pnl_threshold
- total_trades >= significant_trade_count_threshold
- abs(max_drawdown_usdt) >= significant_drawdown_threshold
- best_trade.pnl_usdt >= significant_trade_threshold
- worst_trade.pnl_usdt <= -significant_trade_threshold

Default thresholds:

- significant_pnl_threshold = 5.0
- significant_trade_count_threshold = 5
- significant_drawdown_threshold = 5.0
- significant_trade_threshold = 2.0

Caching:
- cache Pair History results for 5 minutes
- support refresh=true to force recompute
- cache key should include filters/sort/page/page_size

Use existing trade/event data only.
If a metric is unavailable, return null, not guessed.

Add tests:

- pair aggregation
- date filtering
- status filtering
- PnL winners/losers filtering
- significant_only filtering
- significant threshold config
- sorting
- pagination
- cache hit/miss
- refresh=true bypasses cache
- missing data returns null safely

Do not touch frontend yet.

================================================================================
PROMPT 3 — API ENDPOINT FOR PAIR HISTORY
================================================================================

Prerequisites:

- Prompt 2 complete
- Pair History service tests passing
- Admin API route conventions known

Add API endpoint for Pair History.

Use the backend service from core/dashboard/pair_history_service.py.

Add route under the admin API, for example:

GET /admin/pairs/history

Query params:

- start_ts
- end_ts
- status
- pnl_filter
- min_trade_count
- min_win_rate
- max_win_rate
- regime
- hedge_drift_filter
- significant_only
- search
- sort_by
- sort_dir
- page
- page_size
- refresh

Return:
Pair history response with rows, meta, kpis, and cache metadata.

Rules:
- Read-only endpoint only.
- No order execution.
- No live trading changes.
- Handle missing data safely.

Update Platform/web/lib/api.ts with:

- PairSummary type
- PairHistoryResponse type
- getPairHistory(params)

Add backend/API tests if the project has router tests.

Run:
python -m compileall core Platform
npm run lint

================================================================================
PROMPT 4 — FRONTEND PAIR HISTORY PAGE
================================================================================

Prerequisites:

- Prompt 3 complete
- getPairHistory(params) available in Platform/web/lib/api.ts
- Admin routing and auth patterns known

Implement the Pair History / Pair Review page.

Goal:
Create a searchable, filterable page where the user can review pairs with significant wins or losses.

Create route/page:

Platform/web/app/admin/dashboard/pairs/history/page.tsx

or use the existing admin routing convention.

UI layout:

Header:
- Title: Pair History
- Subtitle: Review historical pair performance, significant wins/losses, hedge drift, and pair health.

KPI cards:
- Total Pairs
- Tradable Pairs
- Profitable Pairs
- Losing Pairs
- Hospital Pairs
- Graveyard Pairs

Filters:
- Date Range
- Status: all / stable / warning / hospital / graveyard
- PnL: all / winners / losers
- Trade count minimum
- Win rate range
- Regime
- Hedge drift: all / high drift only
- Significant only
- Search pair

Main table columns:
- Pair
- Net PnL
- Trades
- Win Rate
- Profit Factor
- Max Drawdown
- Best Trade
- Worst Trade
- Avg Hold
- Avg Entry Z
- Avg Exit Z
- Avg Hedge Ratio
- Hedge Drift Events
- Status
- Last Trade

Badges:
- Elite
- Stable
- Warning
- Hospital
- Graveyard
- High Drift
- High Slippage
- Good Reverter
- Bad Executor

Row click:
- Navigate to Pair Detail / Chart Audit page for that pair.

Right-side drawer or expandable row:
- Mini pair summary
- Top 3 trades
- Most common block reason
- Open Pair Detail button

Rules:
- Preserve existing UI style.
- Use existing PanelCard/TableFrame/UI classes if available.
- Handle loading/empty/error states.
- Show cache timestamp if useful.
- Do not modify live trading behavior.

Run:
npm run lint
npm run build

================================================================================
PROMPT 5 — BACKEND PAIR DETAIL SUMMARY SERVICE
================================================================================

Prerequisites:

- Prompt 2 complete
- Pair History aggregation working
- Chart Audit endpoint contract verified
- Counterfactual lazy endpoint available
- Decision score timeline available

Implement backend Pair Detail Summary service.

Goal:
For one selected pair, return all summary data needed by the Pair Detail / Chart Audit page.

Create:

core/dashboard/pair_detail_service.py

Add function:

get_pair_detail_summary(pair, timeframe, start_ts=None, end_ts=None)

Return:

{
  "pair": "...",
  "status": "...",
  "summary": {
    "total_pnl_usdt": null,
    "total_trades": null,
    "win_rate": null,
    "profit_factor": null,
    "avg_reversion_time_seconds": null,
    "avg_hedge_ratio": null,
    "current_hedge_ratio": null,
    "avg_hedge_drift_pct": null,
    "current_regime": null,
    "current_bayesian_posterior": null,
    "current_final_rank_score": null
  },
  "best_trade": TradeSummary | null,
  "worst_trade": TradeSummary | null,
  "latest_trade": TradeSummary | null,
  "block_reason_counts": {},
  "counterfactual_summary": {
    "best_exit_policy": null,
    "avg_missed_profit_usdt": null,
    "avg_avoided_loss_usdt": null,
    "actual_exit_efficiency": null
  },
  "hedge_summary": {
    "avg_entry_hedge_ratio": null,
    "avg_exit_hedge_ratio": null,
    "avg_hedge_drift_pct": null,
    "equal_notional_total_pnl": null,
    "hedge_ratio_sized_total_pnl": null,
    "sizing_pnl_delta_usdt": null
  }
}

Data source note:

- equal_notional_total_pnl
- hedge_ratio_sized_total_pnl
- sizing_pnl_delta_usdt

should come from counterfactual sizing comparison results populated by Phase 2.25 / Phase 3.

If those records are unavailable, return null.
Do not invent these values.

Use existing chart audit/counterfactual/trade data where available.
Return null for unavailable values.

Tests:
- pair summary aggregation
- best/worst trade selection
- hedge summary calculation
- counterfactual summary missing-data behavior
- missing data safe response

================================================================================
PROMPT 6 — PAIR DETAIL / CHART AUDIT PAGE
================================================================================

Prerequisites:

- Prompt 5 complete
- Chart Audit v1.4 endpoints verified by Prompt 0.5
- Pair Detail Summary endpoint available
- Counterfactual lazy endpoint available
- Decision timeline endpoint/params available

Implement Pair Detail / Chart Audit page.

Goal:
Create a detailed page for one pair that combines pair summary, chart audit, trades, counterfactuals, hedge ratio, ML scores, and liquidity.

Route example:

Platform/web/app/admin/dashboard/pairs/[pair]/page.tsx

or use the current routing convention.

Page structure:

Top summary cards:
- Pair
- Current Status
- Total PnL
- Total Trades
- Win Rate
- Profit Factor
- Avg Reversion Time
- Avg Hedge Ratio
- Current Hedge Ratio
- Avg Hedge Drift
- Current Regime
- Bayesian Score
- Final Rank Score

Main chart:
Use the existing completed chart audit system:
- Z-score line
- Threshold lines
- Historical mean crossings
- Replay markers
- Actual markers
- Blocked markers
- Counterfactual lazy loading
- Decision score timeline
- Hedge-ratio metadata

Tabs below chart:

1. Overview
2. Trades
3. Replay Audit
4. Counterfactual Exits
5. Hedge Ratio
6. ML Scores
7. Orderbook / Liquidity
8. Logs

Overview tab:
- Pair performance summary
- Latest state
- Last trade result
- Best/worst trade
- Current quality score
- Why pair is tradable/hospital/graveyard

Trades tab:
Table columns:
- Trade ID
- Entry Time
- Exit Time
- Side
- Entry Z
- Exit Z
- Hold Time
- PnL
- Fees
- Slippage
- Exit Reason
- Hedge Ratio
- Hedge Drift
- Regime

Each row actions:
- View Chart
- Compare Exits
- View Logs

Replay Audit tab:
- Replay candidates
- Actual executed trades
- Blocked signals
- Most common block reasons
- Candidate-to-trade conversion rate

Counterfactual Exits tab:
- Actual Exit PnL
- Exit at Z=0.50
- Exit at Z=0.35
- Exit at Z=0.00
- Exit on Mean Crossing
- Exit on Max Hold
- Best Policy
- PnL Delta vs Actual

Hedge Ratio tab:
- Entry hedge ratio
- Current hedge ratio
- Hedge ratio over time
- Hedge drift %
- Equal-notional PnL
- Hedge-ratio-sized PnL
- Sizing delta
- Hedge sizing error %

ML Scores tab:
- Regime timeline
- Break risk timeline
- Bayesian posterior timeline
- Final rank score timeline
- Microstructure risk timeline
- EV hold/exit score timeline

Orderbook / Liquidity tab:
- Spread bps
- Bid depth
- Ask depth
- Depth imbalance
- Estimated slippage
- Orderbook freshness
- Liquidity score

Rules:
- Use existing chart audit endpoints.
- Use lazy counterfactual loading.
- Do not compute expensive data unless tab/section is opened where possible.
- Preserve existing UI style.
- No live trading changes.

Run:
npm run lint
npm run build

================================================================================
PROMPT 7 — BACKEND ANALYTICS DASHBOARD SERVICE
================================================================================

Prerequisites:

- Pair History service complete
- Pair Detail summary service complete
- Counterfactual summaries available or null-safe
- Decision score history available or null-safe
- ExitOrchestratorEvent availability known

Implement backend Analytics Dashboard service.

Goal:
Aggregate strategy-wide performance and learning metrics.

Create:

core/dashboard/analytics_service.py

Add function:

get_analytics_dashboard(start_ts=None, end_ts=None, refresh=False)

Return sections:

1. performance:
- total_pnl_usdt
- realized_pnl_usdt
- unrealized_pnl_usdt
- win_rate
- profit_factor
- average_win_usdt
- average_loss_usdt
- max_drawdown_usdt
- trade_count
- avg_hold_seconds

2. pnl_timeseries:
- daily/session PnL
- equity curve if available
- drawdown curve

3. pair_leaderboards:
- top_pairs_by_pnl
- bottom_pairs_by_pnl
- top_pairs_by_win_rate
- worst_pairs_by_drawdown
- pairs_with_high_hedge_drift
- pairs_with_frequent_blocks

4. exit_analysis:
- best_counterfactual_exit_policy
- actual_exit_efficiency
- avg_missed_profit_usdt
- avg_avoided_loss_usdt
- exit_policy_distribution

Important:
exit_policy_distribution and some exit_analysis fields require ExitOrchestratorEvent logs.

If ExitOrchestratorEvent logs are unavailable:
- return null or empty exit_analysis fields
- do not invent exit policy distribution from unstructured logs

5. ml_analysis:
- pnl_by_regime
- win_rate_by_regime
- bayesian_posterior_vs_outcome
- final_rank_score_vs_outcome
- break_risk_before_losses
- microstructure_risk_vs_slippage

ML fields may be null until enough stored score history exists.

6. hedge_analysis:
- equal_notional_total_pnl
- hedge_ratio_sized_total_pnl
- sizing_pnl_delta_usdt
- high_drift_trade_count

Caching:
- cache Analytics Dashboard results for 15 minutes
- support refresh=true to force recompute
- cache key should include start_ts/end_ts and filters

Return null or empty arrays for unavailable data.

Tests:
- dashboard aggregation
- cache hit/miss
- refresh=true bypasses cache
- pair leaderboards
- exit analysis with missing ExitOrchestratorEvent logs
- exit analysis with missing counterfactuals
- ML analysis with missing scores
- hedge analysis

================================================================================
PROMPT 8 — ANALYTICS DASHBOARD PAGE
================================================================================

Prerequisites:

- Prompt 7 complete
- Analytics API endpoint available
- Frontend chart/table components identified

Implement Analytics Dashboard page.

Route example:

Platform/web/app/admin/dashboard/analytics/page.tsx

Goal:
Show strategy-wide analytics and patterns.

Layout:

Top KPI cards:
- Total PnL
- Win Rate
- Profit Factor
- Max Drawdown
- Trade Count
- Avg Hold Time

Performance charts:
- Equity curve
- Daily/session PnL
- Drawdown curve
- PnL distribution
- Trade duration distribution

Pair leaderboards:
- Top 10 pairs by PnL
- Bottom 10 pairs by PnL
- Best win rate pairs
- Worst drawdown pairs
- High hedge-drift pairs
- Frequent blocked pairs

Exit policy analysis:
- Actual exit vs best counterfactual exit
- Best exit policy by average delta
- Actual exit efficiency
- Missed profit / avoided loss

ML analysis:
- PnL by regime
- Win rate by regime
- Bayesian posterior vs outcome
- Final rank score vs outcome
- Break risk before losses
- Microstructure risk vs slippage

Hedge-ratio analysis:
- Equal-notional vs hedge-ratio-sized total PnL
- Sizing impact
- High-drift trade count

Rules:
- Use backend analytics service.
- Use existing chart components if available.
- Keep page readable; avoid too many charts above the fold.
- Add loading/empty/error states.
- Display unavailable/null metrics cleanly.
- No live trading behavior changes.

Run:
npm run lint
npm run build

================================================================================
PROMPT 9 — RISK & HEALTH DASHBOARD BACKEND
================================================================================

Prerequisites:

- Pair health/hospital/graveyard data sources known
- Bot status/log sources known
- Hedge-drift and orderbook freshness sources known

Implement Risk & Health backend service.

Create:

core/dashboard/risk_health_service.py

Goal:
Show whether the bot is safe to keep running.

Return:

{
  "bot_status": {},
  "risk_kpis": {
    "current_drawdown_usdt": null,
    "daily_loss_limit_usage_pct": null,
    "open_exposure_usdt": null,
    "open_positions": null,
    "orphan_desync_status": null,
    "api_latency_ms": null,
    "order_failure_count": null,
    "orderbook_stale_count": null
  },
  "pair_health": {
    "hospital_pairs": [],
    "graveyard_pairs": [],
    "high_break_risk_pairs": [],
    "high_hedge_drift_positions": [],
    "liquidity_stress_pairs": []
  },
  "alerts": [
    {
      "severity": "warning",
      "type": "hedge_ratio_drift",
      "message": "...",
      "pair": "...",
      "latest_timestamp": 0,
      "occurrence_count": 1
    }
  ],
  "cache": {
    "cache_hit": false,
    "generated_at": 0,
    "ttl_seconds": 30
  }
}

Alert types:
- hedge_ratio_drift_exceeded
- orderbook_stale
- liquidity_stress
- regime_break_risk_high
- pair_moved_to_hospital
- pair_moved_to_graveyard
- consecutive_losses
- drawdown_threshold_near
- orphan_position
- leg_desync
- API_error_spike

Alert deduplication:

Deduplicate alerts by:

(type, pair)

within a configurable window:

default_alert_dedup_window_minutes = 30

For duplicates:
- keep latest_timestamp
- increment occurrence_count
- show the latest message or a summary message

Caching:
- cache Risk & Health results for 15 to 30 seconds
- support refresh=true to force recompute

Read-only only.
No live trading changes.

Add tests for:
- alert generation
- alert deduplication
- cache behavior
- missing data handling

================================================================================
PROMPT 10 — RISK & HEALTH DASHBOARD PAGE
================================================================================

Prerequisites:

- Prompt 9 complete
- Risk & Health API available
- Admin UI components available

Implement Risk & Health Dashboard page.

Route example:

Platform/web/app/admin/dashboard/risk-health/page.tsx

Purpose:
Answer: Is the bot safe to keep running?

Top KPI cards:
- Current Drawdown
- Daily Loss Limit Usage
- Open Exposure
- Open Positions
- Orphan/Desync Status
- API Latency
- Order Failures
- Stale Orderbooks

Sections:

1. Active alerts
Table:
- Severity
- Type
- Pair
- Message
- Latest Timestamp
- Occurrence Count

2. Pair health
Tables:
- Hospital pairs
- Graveyard pairs
- High break-risk pairs
- High hedge-drift positions
- Liquidity stress pairs

3. Execution health
- API latency
- order failures
- orderbook freshness
- slippage spikes

4. Risk trend
- drawdown over time
- exposure over time
- consecutive losses

Rules:
- Read-only.
- No live trading behavior changes.
- Use warning/error visual states.
- Add loading/empty/error states.
- Display deduplicated alerts.

Run:
npm run lint
npm run build

================================================================================
PROMPT 11 — NAVIGATION / SIDEBAR UPDATE
================================================================================

Prerequisites:

- Prompt 0 returned existing route list
- Portfolio, Analytics, Pair History, Pair Detail, and Risk & Health routes known
- Permission/access-control helpers known

Update dashboard navigation/sidebar.

Use the existing route list from Prompt 0.

Preserve all existing routes unless explicitly obsolete and confirmed.

Add or organize routes:

Dashboard:
- Portfolio
- Analytics
- Risk & Health

Pairs:
- Pair History
- Pair Detail is accessed from Pair History rows

Trades:
- Trade History
- Trade Review if implemented

Audit:
- Chart Decision Audit
- Counterfactual Exits if separate
- Replay Signals if separate

Bot:
- Console
- Settings

Rules:
- Preserve existing permissions/access control.
- Use existing admin nav helpers.
- Do not expose pages to users without proper permission.
- Keep active route highlighting working.
- Do not remove existing routes unless obsolete and confirmed.
- Avoid duplicate navigation entries for existing pages.

Run:
npm run lint
npm run build

================================================================================
PROMPT 12 — FINAL INTEGRATION AND REGRESSION CHECK
================================================================================

Prerequisites:

- All dashboard pages implemented
- API endpoints wired
- Navigation updated

Run a full integration review of the redesigned dashboard system.

Do not write code unless fixing clearly identified bugs.

Verify:

1. Portfolio Dashboard loads.
2. Analytics Dashboard loads.
3. Pair History loads and filters.
4. Pair Detail opens from Pair History.
5. Chart Audit still renders:
   - statistical markers
   - replay markers
   - actual markers
   - counterfactual lazy loading
   - decision score timeline
6. Risk & Health loads.
7. Navigation works.
8. Permissions still apply.
9. No live trading behavior changed.
10. No order execution files were modified unless explicitly expected.
11. Backend tests pass.
12. Frontend lint/build passes.
13. Caching does not return stale data when refresh=true.
14. Null/unavailable metrics render cleanly.
15. Expensive analytics are cached or optional.

Run:

pytest -q
python -m compileall core
npm run lint
npm run build

Return:
- summary of implemented pages
- any known missing metrics
- any TODOs
- any performance risks
- confirmation that live trading/order execution behavior was not changed
