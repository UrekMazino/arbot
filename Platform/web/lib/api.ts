export type MessageResponse = {
  message: string;
};

export type ForgotPasswordResponse = {
  message: string;
  reset_token?: string;
};

export type RoleRecord = {
  id: string;
  name: string;
  description: string | null;
  permissions: string[];
};

export type UserRecord = {
  id: string;
  email: string;
  is_active: boolean;
  permissions: string[];
  roles: RoleRecord[];
  created_at: string;
  updated_at: string;
};

export type RunSummary = {
  id: string;
  bot_instance_id: string;
  run_key: string;
  status: string;
  start_ts: string;
  end_ts: string | null;
  start_equity: number | null;
  end_equity: number | null;
  session_pnl: number | null;
  max_drawdown: number | null;
};

export type RunEvent = {
  id: string;
  event_id: string;
  run_id: string;
  ts: string;
  event_type: string;
  severity: string;
  payload_json: Record<string, unknown>;
};

export type Trade = {
  id: string;
  run_id: string;
  pair_key: string;
  entry_ts: string | null;
  exit_ts: string | null;
  side: string | null;
  entry_z: number | null;
  exit_z: number | null;
  pnl_usdt: number | null;
  hold_minutes: number | null;
  strategy: string | null;
  regime: string | null;
  exit_reason: string | null;
};

export type RunPairSegment = {
  id: string;
  run_id: string;
  pair: string;
  sequence_no: number;
  started_at: string | null;
  ended_at: string | null;
  switch_reason: string | null;
  duration_seconds: number;
};

export type WalkForwardPoint = {
  exit_ts: string;
  pnl_usdt: number;
};

export type PortfolioEquityRange = "24h" | "7d" | "30d" | "90d" | "all";

export type PortfolioEquityBucket = "auto" | "raw" | "hour" | "day" | "week";
export type PortfolioEquityBasis = "realized" | "live";

export type PortfolioEquityPoint = {
  ts: string;
  bucket_start: string | null;
  equity: number;
  pnl_usdt: number;
  pnl_pct: number | null;
  drawdown: number;
  drawdown_pct: number | null;
  run_id: string | null;
  run_key: string | null;
  source: string | null;
  samples: number;
};

export type PortfolioEquityStats = {
  start_ts: string | null;
  end_ts: string | null;
  start_equity: number | null;
  end_equity: number | null;
  change_usdt: number | null;
  change_pct: number | null;
  min_equity: number | null;
  max_equity: number | null;
  max_drawdown: number | null;
  max_drawdown_pct: number | null;
  point_count: number;
  raw_point_count: number;
  run_count: number;
  latest_pnl_usdt: number | null;
  closed_trade_count?: number;
};

export type PortfolioEquityCurve = {
  range: PortfolioEquityRange;
  bucket: Exclude<PortfolioEquityBucket, "auto">;
  requested_bucket: PortfolioEquityBucket;
  basis: PortfolioEquityBasis;
  source: "realized_trades" | "equity_snapshots" | "event_fallback";
  generated_at: string;
  points: PortfolioEquityPoint[];
  stats: PortfolioEquityStats;
};

export type ScorecardCell = {
  entry_strategy: string | null;
  entry_regime: string | null;
  trades: number;
  wins: number;
  win_rate_pct: number | null;
  avg_pnl_usdt: number | null;
  sum_pnl_usdt: number | null;
};

export type PerformanceSummaryRow = {
  strategy: string;
  regime?: string;
  trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  missing_pnl: number;
  win_rate_pct: number | null;
  pnl_usdt: number;
  avg_pnl_usdt: number | null;
  avg_hold_minutes: number | null;
  avg_size_multiplier: number | null;
  profit_factor: number | null;
  run_count: number;
  best_pnl_usdt: number | null;
  worst_pnl_usdt: number | null;
  first_exit_ts: string | null;
  last_exit_ts: string | null;
};

export type PerformanceTradeRow = {
  id: string;
  run_id: string;
  run_key: string;
  pair_key: string;
  strategy: string;
  regime: string;
  side: string | null;
  entry_ts: string | null;
  exit_ts: string | null;
  pnl_usdt: number | null;
  hold_minutes: number | null;
  entry_z: number | null;
  exit_z: number | null;
  exit_reason: string | null;
  size_multiplier_used: number | null;
  cumulative_pnl_usdt: number;
};

export type PerformanceHistory = {
  range: string;
  generated_at: string;
  closed_trades: number;
  closed_trades_with_pnl: number;
  run_count: number;
  total_pnl_usdt: number;
  strategy_summary: PerformanceSummaryRow[];
  strategy_regime_summary: PerformanceSummaryRow[];
  recent_trades: PerformanceTradeRow[];
};

export type DashboardTag =
  | "elite"
  | "stable"
  | "warning"
  | "hospital"
  | "graveyard"
  | "high_drift"
  | "high_slippage"
  | "good_reverter"
  | "bad_executor"
  | "high_break_risk"
  | "profitable"
  | "losing";

export type DashboardCacheMeta = {
  cache_hit: boolean;
  generated_at: number | null;
  ttl_seconds: number | null;
  refresh_supported: boolean;
};

export type TradeSummary = {
  trade_id: string;
  pair: string;
  side: string | null;
  entry_time: number | null;
  exit_time: number | null;
  entry_z: number | null;
  exit_z: number | null;
  hold_seconds: number | null;
  pnl_usdt: number | null;
  fees_usdt: number | null;
  slippage_usdt: number | null;
  exit_reason: string | null;
  entry_hedge_ratio: number | null;
  exit_hedge_ratio: number | null;
  hedge_ratio_drift_pct: number | null;
  regime_at_entry: string | null;
  final_rank_score_at_entry: number | null;
  bayesian_posterior_at_entry: number | null;
};

export type PairSummary = {
  pair: string;
  status: string | null;
  total_trades: number | null;
  net_pnl_usdt: number | null;
  realized_pnl_usdt: number | null;
  unrealized_pnl_usdt: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown_usdt: number | null;
  avg_hold_seconds: number | null;
  avg_entry_z: number | null;
  avg_exit_z: number | null;
  avg_hedge_ratio: number | null;
  avg_hedge_drift_pct: number | null;
  hospital_count: number | null;
  graveyard_count: number | null;
  block_reason_counts: Record<string, number>;
  best_trade: TradeSummary | null;
  worst_trade: TradeSummary | null;
  last_traded_at: number | null;
  tags: DashboardTag[] | string[];
};

export type PairHistoryMeta = {
  page: number;
  page_size: number;
  total_rows: number;
  total_pages: number;
  sort_by: string;
  sort_dir: "asc" | "desc" | string;
};

export type PairHistoryKpis = {
  total_pairs: number;
  tradable_pairs: number;
  profitable_pairs: number;
  losing_pairs: number;
  hospital_pairs: number;
  graveyard_pairs: number;
};

export type PairHistoryResponse = {
  rows: PairSummary[];
  meta: PairHistoryMeta;
  kpis: PairHistoryKpis;
  cache: DashboardCacheMeta;
};

export type PairDetailSummaryResponse = {
  pair: string;
  timeframe: string;
  status: string | null;
  summary: {
    total_pnl_usdt: number | null;
    total_trades: number | null;
    win_rate: number | null;
    profit_factor: number | null;
    avg_reversion_time_seconds: number | null;
    avg_hedge_ratio: number | null;
    current_hedge_ratio: number | null;
    avg_hedge_drift_pct: number | null;
    current_regime: string | null;
    current_bayesian_posterior: number | null;
    current_final_rank_score: number | null;
  };
  best_trade: TradeSummary | null;
  worst_trade: TradeSummary | null;
  latest_trade: TradeSummary | null;
  block_reason_counts: Record<string, number>;
  counterfactual_summary: {
    best_exit_policy: string | null;
    avg_missed_profit_usdt: number | null;
    avg_avoided_loss_usdt: number | null;
    actual_exit_efficiency: number | null;
  };
  hedge_summary: {
    avg_entry_hedge_ratio: number | null;
    avg_exit_hedge_ratio: number | null;
    avg_hedge_drift_pct: number | null;
    equal_notional_total_pnl: number | null;
    hedge_ratio_sized_total_pnl: number | null;
    sizing_pnl_delta_usdt: number | null;
  };
  cache: DashboardCacheMeta;
};

export type PairPerformanceSummary = {
  pair: string | null;
  total_trades: number | null;
  net_pnl_usdt: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown_usdt: number | null;
  avg_hold_seconds: number | null;
  best_trade: TradeSummary | null;
  worst_trade: TradeSummary | null;
  tags: DashboardTag[] | string[];
  metadata: Record<string, unknown>;
};

export type ReplaySignalSummary = {
  pair: string | null;
  total_markers: number | null;
  entry_candidates: number | null;
  exit_candidates: number | null;
  blocked_signals: number | null;
  valid_candidates: number | null;
  blocked_candidates: number | null;
  candidate_to_actual_conversion_rate: number | null;
  block_reason_counts: Record<string, number>;
  latest_signal_at: number | null;
  metadata: Record<string, unknown>;
};

export type CounterfactualSummary = {
  best_exit_policy: string | null;
  avg_missed_profit_usdt: number | null;
  avg_avoided_loss_usdt: number | null;
  studies_count: number | null;
  policy_win_counts: Record<string, number>;
  metadata: Record<string, unknown>;
};

export type DecisionScoreSummary = {
  score_source: string | null;
  avg_regime_confidence: number | null;
  avg_break_risk: number | null;
  avg_bayesian_posterior: number | null;
  avg_final_rank_score: number | null;
  avg_liquidity_score: number | null;
  avg_microstructure_risk: number | null;
  avg_ev_hold_value_usdt: number | null;
  avg_exit_score: number | null;
  quality_gate_pass_rate: number | null;
  unavailable_count: number | null;
  metadata: Record<string, unknown>;
};

export type HedgeRatioSummary = {
  avg_hedge_ratio: number | null;
  avg_hedge_drift_pct: number | null;
  max_hedge_drift_pct: number | null;
  high_drift_count: number | null;
  sizing_pnl_delta_usdt: number | null;
  metadata: Record<string, unknown>;
};

export type RiskEventSummary = {
  severity: string | null;
  type: string | null;
  message: string | null;
  pair: string | null;
  latest_timestamp: number | null;
  occurrence_count: number | null;
  metadata: Record<string, unknown>;
};

export type PortfolioSummary = {
  total_equity_usdt: number | null;
  session_pnl_usdt: number | null;
  realized_pnl_usdt: number | null;
  unrealized_pnl_usdt: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  max_drawdown_usdt: number | null;
  open_positions: Array<Record<string, unknown>> | null;
  active_pair: string | null;
  bot_status: string | null;
  open_exposure_usdt: number | null;
  cache: DashboardCacheMeta;
};

export type PortfolioDashboardSummary = Omit<PortfolioSummary, "cache">;

export type PortfolioDashboardEquityPoint = {
  timestamp: number;
  equity_usdt: number;
  session_pnl_usdt?: number | null;
  source?: string | null;
  run_id?: string | null;
  current_pair?: string | null;
};

export type PortfolioDashboardDailyPnlPoint = {
  date: string;
  pnl_usdt: number;
  trade_count: number;
};

export type PortfolioDashboardDrawdownPoint = {
  timestamp: number;
  equity_usdt: number;
  peak_equity_usdt: number;
  drawdown_usdt: number;
  drawdown_pct: number | null;
};

export type PortfolioDashboardOpenExposurePoint = {
  timestamp: number;
  pair?: string | null;
  open_exposure_usdt: number;
  unrealized_pnl_usdt?: number | null;
};

export type PortfolioDashboardHighlights = {
  best_performing_pair: string | null;
  worst_performing_pair: string | null;
  most_traded_pair: string | null;
  highest_drawdown_pair: string | null;
  current_regime_state: string | null;
  current_risk_level: string | null;
};

export type PortfolioDashboardResponse = {
  summary: PortfolioDashboardSummary;
  charts: {
    equity_curve: PortfolioDashboardEquityPoint[];
    daily_pnl: PortfolioDashboardDailyPnlPoint[];
    drawdown_curve: PortfolioDashboardDrawdownPoint[];
    open_exposure: PortfolioDashboardOpenExposurePoint[];
  };
  highlights: PortfolioDashboardHighlights;
  cache: DashboardCacheMeta;
};

export type AnalyticsSummary = {
  performance: Record<string, unknown>;
  pnl_timeseries: Array<Record<string, unknown>>;
  pair_leaderboards: PairPerformanceSummary[];
  exit_analysis: CounterfactualSummary | Record<string, unknown> | null;
  ml_analysis: DecisionScoreSummary | Record<string, unknown> | null;
  hedge_analysis: HedgeRatioSummary | Record<string, unknown> | null;
  cache: DashboardCacheMeta;
};

export type AnalyticsDashboardPerformance = {
  total_pnl_usdt: number | null;
  realized_pnl_usdt: number | null;
  unrealized_pnl_usdt: number | null;
  win_rate: number | null;
  profit_factor: number | null;
  average_win_usdt: number | null;
  average_loss_usdt: number | null;
  max_drawdown_usdt: number | null;
  trade_count: number | null;
  avg_hold_seconds: number | null;
};

export type AnalyticsDashboardResponse = {
  performance: AnalyticsDashboardPerformance;
  pnl_timeseries: {
    daily_pnl: Array<Record<string, unknown>>;
    equity_curve: Array<Record<string, unknown>>;
    drawdown_curve: Array<Record<string, unknown>>;
  };
  pair_leaderboards: {
    top_pairs_by_pnl: PairSummary[];
    bottom_pairs_by_pnl: PairSummary[];
    top_pairs_by_win_rate: PairSummary[];
    worst_pairs_by_drawdown: PairSummary[];
    pairs_with_high_hedge_drift: PairSummary[];
    pairs_with_frequent_blocks: Array<PairSummary & { block_count?: number | null }>;
  };
  exit_analysis: {
    best_counterfactual_exit_policy: string | null;
    actual_exit_efficiency: number | null;
    avg_missed_profit_usdt: number | null;
    avg_avoided_loss_usdt: number | null;
    exit_policy_distribution: Record<string, number>;
  };
  ml_analysis: {
    pnl_by_regime: Array<Record<string, unknown>>;
    win_rate_by_regime: Array<Record<string, unknown>>;
    bayesian_posterior_vs_outcome: Array<Record<string, unknown>>;
    final_rank_score_vs_outcome: Array<Record<string, unknown>>;
    break_risk_before_losses: number | null;
    microstructure_risk_vs_slippage: Array<Record<string, unknown>>;
  };
  hedge_analysis: {
    equal_notional_total_pnl: number | null;
    hedge_ratio_sized_total_pnl: number | null;
    sizing_pnl_delta_usdt: number | null;
    high_drift_trade_count: number | null;
  };
  cache: DashboardCacheMeta;
};

export type RiskHealthDashboardResponse = {
  bot_status: Record<string, unknown>;
  risk_kpis: {
    current_drawdown_usdt: number | null;
    daily_loss_limit_usage_pct: number | null;
    open_exposure_usdt: number | null;
    open_positions: number | null;
    orphan_desync_status: string | null;
    api_latency_ms: number | null;
    order_failure_count: number | null;
    orderbook_stale_count: number | null;
  };
  pair_health: {
    hospital_pairs: Array<string | Record<string, unknown>>;
    graveyard_pairs: Array<string | Record<string, unknown>>;
    high_break_risk_pairs: Array<Record<string, unknown>>;
    high_hedge_drift_positions: Array<Record<string, unknown>>;
    liquidity_stress_pairs: Array<Record<string, unknown>>;
  };
  alerts: RiskEventSummary[];
  cache: DashboardCacheMeta;
};

export type DataQualityIssue = {
  event_id: string;
  ts: string;
  event_type: string;
  severity: string;
  message: string;
};

export type DataQualitySummary = {
  run_id: string;
  generated_at: string;
  overall_status: string;
  event_health: {
    total: number;
    warn: number;
    error: number;
    critical: number;
    typed_warning_events: Record<string, number>;
  };
  trade_integrity: {
    status: string;
    total_rows: number;
    closed_rows: number;
    open_rows: number;
    closed_missing_pnl: number;
    closed_missing_exit_reason: number;
  };
  reconciliation: {
    status: string;
    run_session_pnl_usdt: number | null;
    trade_pnl_sum_usdt: number;
    delta_usdt: number | null;
    delta_pct_of_session: number | null;
    threshold_pass_usdt: number;
    threshold_warn_usdt: number;
  };
  top_alerts: Array<{
    alert_type: string;
    count: number;
    last_seen: string | null;
  }>;
  recent_issues: DataQualityIssue[];
};

export type AdvancedMLAnalyticsEvent = {
  event_id: string;
  ts: string | null;
  event_type: string;
  severity: string;
  payload: Record<string, unknown>;
};

export type AdvancedMLAnalytics = {
  run_id: string;
  generated_at: string;
  event_counts: Record<string, number>;
  strategy_level: {
    advanced_policy_mode: string;
    learning_updates: number;
    learning_skips: number;
    bayes_updates: number;
    linucb_updates: number;
    live_exit_events: number;
    live_exit_allowed: number;
    rollout_blocked: number;
    shadow_agreement_rate: number | null;
    avg_exit_score: number | null;
    avg_break_risk: number | null;
  };
  latest_regime: AdvancedMLAnalyticsEvent | null;
  latest_exit: AdvancedMLAnalyticsEvent | null;
  latest_learning: AdvancedMLAnalyticsEvent | null;
  recent_events: AdvancedMLAnalyticsEvent[];
};

export type ConfigSnapshotResponse = {
  run_id: string;
  source: string;
  created_at: string | null;
  report_id: string | null;
  file_id: string | null;
  path: string | null;
  config_snapshot: Record<string, unknown> | null;
  error?: string;
};

export type ReportArtifactFile = {
  id: string;
  name: string;
  path: string;
  mime_type: string | null;
  size_bytes: number | null;
  checksum: string | null;
  created_at: string | null;
  download_url: string;
};

export type RunReportArtifact = {
  id: string;
  run_id: string;
  status: string;
  requested_by: string | null;
  requested_at: string | null;
  finished_at: string | null;
  error_text: string | null;
  files: ReportArtifactFile[];
};

export type AdminBotRuntimeStatus = {
  state: string;
  label: string;
  detail: string;
  current_pair: string | null;
  current_z: number | null;
  in_position: boolean | null;
  entry_z: number | null;
  hold_minutes: number | null;
  unrealized_pnl_usdt: number | null;
  entry_notional_usdt: number | null;
  regime: string | null;
  strategy: string | null;
  run_key: string | null;
  updated_at: string | null;
  source: string;
};

export type AdminBotStatus = {
  running: boolean;
  pid: number;
  desired_running?: boolean;
  started_at?: string | null;
  stopped_at?: string | null;
  detail?: string;
  command?: string[];
  cwd?: string;
  requested_by?: string;
  process_mode?: string;
  process_owner?: string;
  request_updated_at?: string | null;
  runner_owner?: string | null;
  runner_heartbeat_at?: string | null;
  run_key?: string | null;
  run_log_file?: string | null;
  latest_run_key?: string | null;
  latest_log_file?: string | null;
  workspace_root?: string;
  control_log_file?: string | null;
  runtime_status?: AdminBotRuntimeStatus | null;
};

export type AdminLogTail = {
  run_key: string | null;
  log_file: string | null;
  line_count: number;
  lines: string[];
  updated_at: string;
  detail: string;
  equity: number | null;
  starting_equity: number | null;
  session_pnl: number | null;
  session_pnl_pct: number | null;
  run_start_time: number | null;
  pair_history: Array<{ pair: string; duration_seconds: number }>;
  pair_count: number;
};

export type AdminRunRuntime = {
  run_id: string | null;
  run_key: string | null;
  status: string;
  running: boolean;
  detail: string;
  started_at: string | null;
  stopped_at: string | null;
  updated_at: string | null;
  duration_seconds: number;
  starting_equity: number | null;
  equity: number | null;
  session_pnl: number | null;
  session_pnl_pct: number | null;
  run_start_time: number | null;
  pair_history: Array<{ pair: string; duration_seconds: number }>;
  pair_count: number;
  current_pair: string | null;
  latest_regime: string | null;
  latest_strategy: string | null;
  source: string;
};

export type AdminLogRun = {
  run_key: string;
  log_file: string;
  size_bytes: number;
  mtime_ts: number;
};

export type AdminLogFile = {
  run_key: string;
  log_file: string;
  content: string;
  size_bytes: number;
  line_count: number;
  updated_at: string;
};

export type AdminReportRun = {
  run_key: string;
  path: string;
  file_count: number;
  summary_json: boolean;
  mtime_ts: number;
};

export type AdminReportArtifactFile = {
  name: string;
  format: string | null;
  rows: number | null;
  size_bytes: number | null;
  mtime_ts: number | null;
  mime_type: string | null;
};

export type AdminReportSummary = {
  run_key: string;
  run_id: string | null;
  path: string;
  refreshed: boolean;
  summary_available: boolean;
  generated_at: string | null;
  report_version: string | null;
  report_source: string | null;
  summary: Record<string, unknown> | null;
  manifest: Record<string, unknown> | null;
  files: AdminReportArtifactFile[];
};

export type AdminEnvSettings = {
  path: string;
  values: Record<string, string>;
};

export type PairHealthEntry = {
  pair: string;
  reason: string;
  added_at: number;
  cooldown_seconds?: number;
  elapsed_seconds?: number;
  remaining_seconds?: number;
  is_ready?: boolean;
  visits?: number;
  ttl_days?: number | null;
};

export type RestrictedTickerEntry = {
  ticker: string;
  reason: string;
  message: string;
  code: string;
  added_at: number;
  ttl_days?: number | null;
  source: string;
};

export type AdminPairsHealth = {
  hospital: PairHealthEntry[];
  graveyard: PairHealthEntry[];
  restricted_tickers: RestrictedTickerEntry[];
  active_pair: Record<string, unknown> | null;
};

export type RemovePairGraveyardResult = {
  ok: boolean;
  removed: boolean;
  pair_key: string;
  removed_keys: string[];
  status: string;
  requested_by: string;
  health: AdminPairsHealth;
};

export type ManualPairSwitchResult = {
  ok: boolean;
  allowed: boolean;
  status: string;
  pending?: boolean;
  detail: string;
  requested_by: string;
  previous_active_pair: Record<string, string> | null;
  active_pair?: Record<string, string> | null;
  target_pair: Record<string, string>;
  running: boolean;
  request_id: string;
  force_available?: boolean;
  blockers?: string[];
};

export type CointegratedPair = {
  id: string;
  rank: number;
  sym_1: string;
  sym_2: string;
  pair: string;
  p_value: number | null;
  adf_stat: number | null;
  hedge_ratio: number | null;
  zero_crossing: number | null;
  min_capital_per_leg: number | null;
  min_equity_recommended: number | null;
  pair_liquidity_min: number | null;
  pair_order_capacity_usdt: number | null;
  curator_score?: number | null;
  curator_status?: string | null;
  curator_recommendation?: string | null;
  curator_reasons?: string[];
  curator_priority_rank?: number | null;
  curator_checked_at?: string | null;
};

export type CointegratedPairsResponse = {
  source_path: string;
  price_path: string;
  curator_path?: string;
  updated_at: string | null;
  price_updated_at: string | null;
  curator_updated_at?: string | null;
  pair_doctor_ui_refresh_seconds?: number;
  status: Record<string, unknown>;
  curator?: {
    enabled?: boolean;
    running?: boolean;
    desired_running?: boolean;
    pair_count?: number;
    status_counts?: Record<string, number>;
  };
  pair_count: number;
  excluded_pair_count?: number;
  unusable_liquidity_pair_count?: number;
  pairs: CointegratedPair[];
};

export type RemoveCointegratedPairResult = {
  ok: boolean;
  removed: boolean;
  removed_rows: number;
  pair_key: string;
  status: string;
  reason: string;
  ttl_days: number | null;
  pair_count: number;
  requested_by: string;
};

export type CointegratedPairPoint = {
  idx: number;
  ts: string;
  price_1: number;
  price_2: number;
  price_1_norm: number;
  price_2_norm: number;
  spread: number;
  spread_mean: number;
  zscore: number | null;
  crossing_spread?: number | null;
  crossing_label?: string | null;
  replay_entry_z?: number | null;
  replay_entry_label?: string | null;
  replay_entry_count?: number;
  replay_entry_side?: string | null;
  replay_exit_z?: number | null;
  replay_exit_label?: string | null;
  replay_exit_count?: number;
  replay_buy_entry_z?: number | null;
  replay_buy_entry_label?: string | null;
  replay_buy_entry_count?: number;
  replay_sell_entry_z?: number | null;
  replay_sell_entry_label?: string | null;
  replay_sell_entry_count?: number;
  replay_exit_candidate_z?: number | null;
  replay_exit_candidate_label?: string | null;
  replay_exit_candidate_count?: number;
  replay_blocked_signal_z?: number | null;
  replay_blocked_signal_label?: string | null;
  replay_blocked_signal_count?: number;
  replay_markers?: ChartAuditReplayMarker[];
  blocked_entry_z?: number | null;
  blocked_entry_label?: string | null;
  blocked_entry_count?: number;
  blocked_entry_reason?: string | null;
  actual_entry_z?: number | null;
  actual_entry_label?: string | null;
  actual_entry_count?: number;
  actual_exit_z?: number | null;
  actual_exit_label?: string | null;
  actual_exit_count?: number;
  actual_exit_pnl_usdt?: number | null;
  actual_markers?: ChartAuditActualMarker[];
  z_upper: number;
  z_lower: number;
  z_mid: number;
};

export type CointegratedPairDetail = {
  pair: CointegratedPair;
  updated_at: string | null;
  price_updated_at: string | null;
  points: CointegratedPairPoint[];
  stats: {
    point_count: number;
    spread_mean: number | null;
    spread_std: number | null;
    zscore_current: number | null;
    zscore_window?: number | null;
    zero_crossing_window?: number | null;
    price_1_current: number | null;
    price_2_current: number | null;
    markers?: {
      replay_entries?: number;
      replay_exits?: number;
      blocked_entries?: number;
      actual_entries?: number;
      actual_exits?: number;
      legend?: Record<string, string>;
    };
  };
};

export type ChartAuditActualMarkerType =
  | "actual_entry"
  | "actual_exit"
  | "actual_partial_exit"
  | "actual_blocked_signal"
  | "actual_regime_exit"
  | "actual_manual_exit"
  | "actual_advanced_ml_shadow_recommendation";

export type ChartAuditActualMarker = {
  timestamp: number | string;
  original_event_timestamp?: number | string | null;
  timestamp_alignment?: "exact" | "snapped_to_nearest_candle" | string;
  marker_category?: "actual" | string;
  marker_type: ChartAuditActualMarkerType;
  trade_id?: string | null;
  entry_id?: string | null;
  side?: string | null;
  z_score?: number | null;
  spread?: number | null;
  pnl_usdt?: number | null;
  fees_usdt?: number | null;
  slippage_usdt?: number | null;
  reason?: string | null;
  block_reasons?: string[];
  metadata?: Record<string, unknown>;
};

export type ChartAuditReplayMarkerType =
  | "replay_entry_candidate"
  | "replay_exit_candidate"
  | "replay_blocked_signal";

export type ChartAuditReplayMarkerMetadata = Record<string, unknown> & {
  score_source?: "stored_live" | "recomputed_point_in_time" | "current_approximate" | "unavailable" | string | null;
  hard_validation_valid?: boolean | null;
  regime_name?: string | null;
  regime_confidence?: number | null;
  break_risk?: number | null;
  bayesian_posterior?: number | null;
  bayesian_quality_grade?: string | null;
  final_rank_score?: number | null;
  microstructure_risk?: number | null;
  liquidity_score?: number | null;
  ev_hold_value_usdt?: number | null;
  exit_score?: number | null;
  quality_gate_passed?: boolean | null;
};

export type ChartAuditReplayMarker = {
  timestamp: number | string;
  marker_category?: "replay" | string;
  marker_type: ChartAuditReplayMarkerType;
  entry_id?: string | null;
  side?: string | null;
  z_score?: number | null;
  spread?: number | null;
  status?: string | null;
  curator_state?: string | null;
  curator_state_source?: string | null;
  config_source?: string | null;
  passed?: boolean | null;
  block_reasons?: string[];
  reason?: string | null;
  metadata?: ChartAuditReplayMarkerMetadata;
};

export type ChartAuditStatisticalMarker = {
  timestamp: number | string;
  marker_category?: "statistical" | string;
  marker_type: string;
  spread?: number | null;
  zscore?: number | null;
  label?: string | null;
  metadata?: Record<string, unknown>;
};

export type PairDecisionAuditChart = {
  pair: string;
  timeframe: string | null;
  start_ts: number | null;
  end_ts: number | null;
  zscore_series: Array<Record<string, unknown>>;
  statistical_markers: ChartAuditStatisticalMarker[];
  replay_markers: ChartAuditReplayMarker[];
  actual_markers: ChartAuditActualMarker[];
  counterfactual_exit_studies: Array<Record<string, unknown>>;
  counterfactuals_lazy_load: boolean;
  decision_score_timeline: DecisionScoreTimelinePoint[];
  decision_timeline_meta?: DecisionScoreTimelineMeta;
};

export type DecisionScoreTimelinePoint = {
  timestamp: number | string;
  score_source: "stored_live" | "recomputed_point_in_time" | "current_approximate" | "unavailable" | string;
  curator_state?: string | null;
  curator_state_source?: string | null;
  regime?: string | null;
  regime_confidence?: number | null;
  break_risk?: number | null;
  bayesian_posterior?: number | null;
  bayesian_quality_grade?: string | null;
  final_rank_score?: number | null;
  linucb_score?: number | null;
  trade_quality_score?: number | null;
  liquidity_score?: number | null;
  microstructure_risk?: number | null;
  ev_hold_value_usdt?: number | null;
  exit_score?: number | null;
  quality_gate_passed?: boolean | null;
  hedge_ratio_at_t?: number | null;
  hedge_ratio_drift_pct?: number | null;
  config_source?: string | null;
  warning?: string | null;
  metadata?: Record<string, unknown>;
};

export type DecisionScoreTimelineMeta = {
  timeline_resolution: string | null;
  timeline_downsample_method: "last" | "mean" | "none" | string;
  timeline_original_points: number;
  timeline_returned_points: number;
  score_source_summary: Record<string, number>;
  unavailable_count: number;
  stored_live_count: number;
  recomputed_point_in_time_count: number;
  current_approximate_count: number;
};

export type PairDecisionAuditChartOptions = {
  includeDecisionTimeline?: boolean;
  maxTimelinePoints?: number;
  downsampleMethod?: "last" | "mean" | "none";
  resolution?: string | null;
};

export type CounterfactualExitResult = {
  entry_id: string;
  exit_strategy: string;
  status: "triggered" | "not_triggered" | "forced_close_at_window_end" | "unavailable" | string;
  entry_timestamp: number | string;
  entry_side: string | null;
  entry_z: number | null;
  entry_spread: number | null;
  hypothetical_exit_timestamp: number | string | null;
  hypothetical_exit_z: number | null;
  hypothetical_exit_spread: number | null;
  hypothetical_gross_pnl_usdt: number | null;
  hypothetical_fees_usdt: number | null;
  hypothetical_slippage_usdt: number | null;
  hypothetical_net_pnl_usdt: number | null;
  hold_seconds: number | null;
  max_adverse_excursion_z: number | null;
  max_favorable_excursion_z: number | null;
  max_adverse_excursion_usdt: number | null;
  max_favorable_excursion_usdt: number | null;
  equal_notional_pnl_usdt: number | null;
  hedge_ratio_sized_pnl_usdt: number | null;
  pnl_delta_usdt: number | null;
  pnl_delta_pct: number | null;
  note: string | null;
  metadata?: Record<string, unknown>;
};

export type CounterfactualExitStudy = {
  entry_id: string;
  entry_marker_type: "actual_entry" | "replay_entry_candidate" | string;
  pair: string;
  timeframe: string | null;
  entry_timestamp: number | string;
  entry_side: string | null;
  entry_z: number | null;
  entry_spread: number | null;
  actual_exit_timestamp: number | string | null;
  actual_exit_z: number | null;
  actual_pnl_usdt: number | null;
  results: CounterfactualExitResult[];
  best_policy_by_pnl: string | null;
  best_policy_by_risk_adjusted_return: string | null;
  warnings: string[];
};

export type PairSupplyStatus = {
  running: boolean;
  pid: number;
  desired_running?: boolean;
  started_at?: string | null;
  stopped_at?: string | null;
  detail?: string;
  command?: string[];
  cwd?: string;
  requested_by?: string;
  process_mode?: string;
  process_owner?: string;
  request_updated_at?: string | null;
  runner_owner?: string | null;
  runner_heartbeat_at?: string | null;
  interval_seconds?: number;
  log_file?: string;
  status?: Record<string, unknown>;
};

export type PairCuratorStatus = {
  enabled: boolean;
  running: boolean;
  desired_running?: boolean;
  pid: number;
  detail?: string;
  updated_at?: string | null;
  last_run_at?: string | null;
  stopped_at?: string | null;
  interval_seconds?: number | null;
  pair_count?: number;
  status_counts?: Record<string, number>;
};

function resolveApiBase(): string {
  const configured = String(process.env.NEXT_PUBLIC_API_BASE || "").trim();
  if (!configured || configured.toLowerCase() === "same-origin") {
    return "/api/v2";
  }
  return configured;
}

function resolveWsBase(): string {
  const configured = String(process.env.NEXT_PUBLIC_WS_BASE || "").trim();
  if (configured && configured.toLowerCase() !== "same-origin") {
    return configured;
  }
  if (typeof window === "undefined") {
    return "ws://127.0.0.1:8082";
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}`;
}

const API_BASE = resolveApiBase();

export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(status: number, message: string, payload?: unknown) {
    super(`HTTP ${status}: ${message}`);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function apiRequest<T>(
  path: string,
  options: RequestInit,
  retry = false,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (options.headers && typeof options.headers === "object" && !Array.isArray(options.headers)) {
    Object.assign(headers, options.headers as Record<string, string>);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store",
    credentials: "include",
  });

  if (!response.ok) {
    if (
      response.status === 401 &&
      !retry &&
      !path.startsWith("/auth/login") &&
      !path.startsWith("/auth/refresh")
    ) {
      try {
        await refreshSession();
        return apiRequest<T>(path, options, true);
      } catch {
        // ignore refresh failure and return original error
      }
    }

    const text = await response.text();
    let message = text;
    let payload: unknown = text;
    try {
      const parsed = JSON.parse(text);
      payload = parsed;
      if (parsed && typeof parsed === "object") {
        const parsedRecord = parsed as Record<string, unknown>;
        if (parsedRecord.detail && typeof parsedRecord.detail === "object") {
          payload = parsedRecord.detail;
          const detailRecord = parsedRecord.detail as Record<string, unknown>;
          if (typeof detailRecord.detail === "string") {
            message = detailRecord.detail;
          } else if (typeof detailRecord.message === "string") {
            message = detailRecord.message;
          }
        }
        if (response.status === 400 || response.status === 422) {
          message = "Invalid request. Please check your input and try again.";
        } else if (typeof parsedRecord.detail === "string") {
          message = parsedRecord.detail;
        } else if (typeof parsedRecord.message === "string") {
          message = parsedRecord.message;
        }
      }
    } catch {
      // ignore parse errors and keep raw text
    }
    throw new ApiError(response.status, message, payload);
  }

  return (await response.json()) as T;
}

function parseContentDispositionFilename(value: string | null): string | null {
  if (!value) return null;
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const basicMatch = value.match(/filename="?([^"]+)"?/i);
  return basicMatch?.[1] ?? null;
}

async function downloadApiFile(path: string, fallbackFilename: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    cache: "no-store",
    credentials: "include",
  });

  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object") {
        const parsedRecord = parsed as Record<string, unknown>;
        if (typeof parsedRecord.detail === "string") {
          message = parsedRecord.detail;
        } else if (typeof parsedRecord.message === "string") {
          message = parsedRecord.message;
        }
      }
    } catch {
      // ignore parse errors and keep raw text
    }
    throw new Error(`HTTP ${response.status}: ${message}`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const filename = parseContentDispositionFilename(response.headers.get("Content-Disposition")) || fallbackFilename;
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

export async function login(email: string, password: string, rememberMe = true): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password, remember_me: rememberMe }),
  });
}

export async function refreshSession(): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/refresh", { method: "POST" });
}

export async function logout(): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/logout", { method: "POST" });
}

export async function forgotPassword(email: string): Promise<ForgotPasswordResponse> {
  return apiRequest<ForgotPasswordResponse>("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(resetToken: string, password: string): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ reset_token: resetToken, password }),
  });
}

export async function getMe(): Promise<UserRecord> {
  return apiRequest<UserRecord>("/auth/me", { method: "GET" });
}

export async function getRuns(): Promise<RunSummary[]> {
  return apiRequest<RunSummary[]>("/runs?limit=100", { method: "GET" });
}

export async function getRunEvents(runId: string): Promise<RunEvent[]> {
  return apiRequest<RunEvent[]>(`/runs/${runId}/events?limit=200`, { method: "GET" });
}

export async function getRunTrades(runId: string): Promise<Trade[]> {
  return apiRequest<Trade[]>(`/runs/${runId}/trades?limit=300`, { method: "GET" });
}

export async function getRunPairSegments(runId: string): Promise<RunPairSegment[]> {
  return apiRequest<RunPairSegment[]>(`/runs/${runId}/pair-segments`, { method: "GET" });
}

export async function getRunWalkForward(runId: string): Promise<WalkForwardPoint[]> {
  return apiRequest<WalkForwardPoint[]>(`/runs/${runId}/analytics/walk-forward`, { method: "GET" });
}

export async function getPortfolioEquityCurve(
  range: PortfolioEquityRange = "7d",
  bucket: PortfolioEquityBucket = "auto",
  basis: PortfolioEquityBasis = "realized",
): Promise<PortfolioEquityCurve> {
  const params = new URLSearchParams({ range, bucket, basis });
  return apiRequest<PortfolioEquityCurve>(`/runs/portfolio/equity-curve?${params.toString()}`, { method: "GET" });
}

export async function getPortfolioDashboard(params?: {
  startTs?: number;
  endTs?: number;
  refresh?: boolean;
}): Promise<PortfolioDashboardResponse> {
  const query = new URLSearchParams();
  if (params?.startTs !== undefined) {
    query.set("start_ts", String(params.startTs));
  }
  if (params?.endTs !== undefined) {
    query.set("end_ts", String(params.endTs));
  }
  if (params?.refresh !== undefined) {
    query.set("refresh", params.refresh ? "true" : "false");
  }
  const suffix = query.toString();
  return apiRequest<PortfolioDashboardResponse>(
    `/admin/dashboard/portfolio${suffix ? `?${suffix}` : ""}`,
    { method: "GET" },
  );
}

export async function getAnalyticsDashboard(params?: {
  startTs?: number;
  endTs?: number;
  refresh?: boolean;
}): Promise<AnalyticsDashboardResponse> {
  const query = new URLSearchParams();
  if (params?.startTs !== undefined) {
    query.set("start_ts", String(params.startTs));
  }
  if (params?.endTs !== undefined) {
    query.set("end_ts", String(params.endTs));
  }
  if (params?.refresh !== undefined) {
    query.set("refresh", params.refresh ? "true" : "false");
  }
  const suffix = query.toString();
  return apiRequest<AnalyticsDashboardResponse>(
    `/admin/dashboard/analytics${suffix ? `?${suffix}` : ""}`,
    { method: "GET" },
  );
}

export async function getRiskHealthDashboard(params?: {
  startTs?: number;
  endTs?: number;
  refresh?: boolean;
}): Promise<RiskHealthDashboardResponse> {
  const query = new URLSearchParams();
  if (params?.startTs !== undefined) {
    query.set("start_ts", String(params.startTs));
  }
  if (params?.endTs !== undefined) {
    query.set("end_ts", String(params.endTs));
  }
  if (params?.refresh !== undefined) {
    query.set("refresh", params.refresh ? "true" : "false");
  }
  const suffix = query.toString();
  return apiRequest<RiskHealthDashboardResponse>(
    `/admin/dashboard/risk-health${suffix ? `?${suffix}` : ""}`,
    { method: "GET" },
  );
}

export async function getPairHistory(params?: {
  startTs?: number;
  endTs?: number;
  status?: string;
  pnlFilter?: "all" | "winners" | "losers";
  minTradeCount?: number;
  minWinRate?: number;
  maxWinRate?: number;
  regime?: string;
  hedgeDriftFilter?: "all" | "high_drift";
  significantOnly?: boolean;
  search?: string;
  sortBy?: string;
  sortDir?: "asc" | "desc";
  page?: number;
  pageSize?: number;
  refresh?: boolean;
}): Promise<PairHistoryResponse> {
  const query = new URLSearchParams();
  if (params?.startTs !== undefined) query.set("start_ts", String(params.startTs));
  if (params?.endTs !== undefined) query.set("end_ts", String(params.endTs));
  if (params?.status) query.set("status", params.status);
  if (params?.pnlFilter) query.set("pnl_filter", params.pnlFilter);
  if (params?.minTradeCount !== undefined) query.set("min_trade_count", String(params.minTradeCount));
  if (params?.minWinRate !== undefined) query.set("min_win_rate", String(params.minWinRate));
  if (params?.maxWinRate !== undefined) query.set("max_win_rate", String(params.maxWinRate));
  if (params?.regime) query.set("regime", params.regime);
  if (params?.hedgeDriftFilter) query.set("hedge_drift_filter", params.hedgeDriftFilter);
  if (params?.significantOnly !== undefined) query.set("significant_only", params.significantOnly ? "true" : "false");
  if (params?.search) query.set("search", params.search);
  if (params?.sortBy) query.set("sort_by", params.sortBy);
  if (params?.sortDir) query.set("sort_dir", params.sortDir);
  if (params?.page !== undefined) query.set("page", String(params.page));
  if (params?.pageSize !== undefined) query.set("page_size", String(params.pageSize));
  if (params?.refresh !== undefined) query.set("refresh", params.refresh ? "true" : "false");
  const suffix = query.toString();
  return apiRequest<PairHistoryResponse>(
    `/admin/pairs/history${suffix ? `?${suffix}` : ""}`,
    { method: "GET" },
  );
}

export async function getPairDetailSummary(params: {
  pair: string;
  timeframe?: string;
  startTs?: number;
  endTs?: number;
  refresh?: boolean;
}): Promise<PairDetailSummaryResponse> {
  const query = new URLSearchParams({
    pair: params.pair,
    timeframe: params.timeframe || "1m",
  });
  if (params.startTs !== undefined) query.set("start_ts", String(params.startTs));
  if (params.endTs !== undefined) query.set("end_ts", String(params.endTs));
  if (params.refresh !== undefined) query.set("refresh", params.refresh ? "true" : "false");
  return apiRequest<PairDetailSummaryResponse>(
    `/admin/pairs/detail-summary?${query.toString()}`,
    { method: "GET" },
  );
}

export async function getRunScorecard(runId: string): Promise<ScorecardCell[]> {
  return apiRequest<ScorecardCell[]>(`/runs/${runId}/analytics/scorecard`, { method: "GET" });
}

export async function getPerformanceHistory(range = "30d", limit = 5000): Promise<PerformanceHistory> {
  const params = new URLSearchParams({ range, limit: String(limit) });
  return apiRequest<PerformanceHistory>(`/runs/analytics/performance-history?${params.toString()}`, { method: "GET" });
}

export async function getRunDataQuality(runId: string): Promise<DataQualitySummary> {
  return apiRequest<DataQualitySummary>(`/runs/${runId}/analytics/data-quality`, { method: "GET" });
}

export async function getRunAdvancedMLAnalytics(runId: string): Promise<AdvancedMLAnalytics> {
  return apiRequest<AdvancedMLAnalytics>(`/runs/${runId}/analytics/advanced-ml`, { method: "GET" });
}

export async function getRunConfigSnapshot(runId: string): Promise<ConfigSnapshotResponse> {
  return apiRequest<ConfigSnapshotResponse>(`/runs/${runId}/config-snapshot`, { method: "GET" });
}

export async function getRunReportArtifacts(runId: string): Promise<RunReportArtifact[]> {
  return apiRequest<RunReportArtifact[]>(`/runs/${runId}/report-artifacts?limit=10`, { method: "GET" });
}

export async function getAdminBotStatus(): Promise<AdminBotStatus> {
  return apiRequest<AdminBotStatus>("/admin/bot/status", { method: "GET" });
}

export async function startAdminBot(): Promise<AdminBotStatus> {
  return apiRequest<AdminBotStatus>("/admin/bot/start", { method: "POST", body: JSON.stringify({}) });
}

export async function stopAdminBot(): Promise<AdminBotStatus> {
  return apiRequest<AdminBotStatus>("/admin/bot/stop", { method: "POST", body: JSON.stringify({}) });
}

export async function getAdminBotLogTail(
  runKey: string,
  lines = 300,
): Promise<AdminLogTail> {
  const key = encodeURIComponent(runKey || "latest");
  return apiRequest<AdminLogTail>(`/admin/bot/logs/tail?run_key=${key}&lines=${lines}`, { method: "GET" });
}

export async function getAdminRunRuntime(runKey: string): Promise<AdminRunRuntime> {
  const key = encodeURIComponent(runKey || "latest");
  return apiRequest<AdminRunRuntime>(`/admin/runs/runtime?run_key=${key}`, { method: "GET" });
}

export async function getAdminLogRuns(limit = 100): Promise<AdminLogRun[]> {
  return apiRequest<AdminLogRun[]>(`/admin/logs/runs?limit=${limit}`, { method: "GET" });
}

export async function getAdminLogFile(runKey: string): Promise<AdminLogFile> {
  const key = encodeURIComponent(runKey);
  return apiRequest<AdminLogFile>(`/admin/logs/runs/${key}`, { method: "GET" });
}

export async function deleteAdminLogRun(runKey: string): Promise<{ deleted: boolean; run_key: string; log_file: string | null; removed_files: number; removed_report_files?: number; deleted_report_dir?: boolean }> {
  const key = encodeURIComponent(runKey);
  return apiRequest<{ deleted: boolean; run_key: string; log_file: string | null; removed_files: number; removed_report_files?: number; deleted_report_dir?: boolean }>(`/admin/logs/runs/${key}`, { method: "DELETE" });
}

export async function getAdminReportRuns(limit = 100): Promise<AdminReportRun[]> {
  return apiRequest<AdminReportRun[]>(`/admin/reports/runs?limit=${limit}`, { method: "GET" });
}

export async function getAdminReportRunSummary(runKey: string): Promise<AdminReportSummary> {
  const key = encodeURIComponent(runKey);
  return apiRequest<AdminReportSummary>(`/admin/reports/runs/${key}/summary`, { method: "GET" });
}

export async function downloadAdminReportFile(runKey: string, fileName: string): Promise<void> {
  const key = encodeURIComponent(runKey);
  const name = encodeURIComponent(fileName);
  await downloadApiFile(`/admin/reports/runs/${key}/files/${name}/download`, fileName);
}

export async function downloadAdminReportZip(runKey: string): Promise<void> {
  const key = encodeURIComponent(runKey);
  await downloadApiFile(`/admin/reports/runs/${key}/download`, `${runKey}_report.zip`);
}

export async function getAdminEnvSettings(): Promise<AdminEnvSettings> {
  return apiRequest<AdminEnvSettings>("/admin/settings/env", { method: "GET" });
}

export async function updateAdminEnvSetting(key: string, value: string): Promise<AdminEnvSettings> {
  const encodedKey = encodeURIComponent(key);
  const res = await apiRequest<{ values: Record<string, string> }>(
    `/admin/settings/env/${encodedKey}`,
    {
      method: "PUT",
      body: JSON.stringify({ value }),
    },
  );
  return { path: "Execution/.env", values: res.values || {} };
}

export async function getAdminPairsHealth(): Promise<AdminPairsHealth> {
  return apiRequest<AdminPairsHealth>("/admin/pairs/health", { method: "GET" });
}

export async function removePairFromGraveyard(pair: string): Promise<RemovePairGraveyardResult> {
  return apiRequest<RemovePairGraveyardResult>("/admin/pairs/health/graveyard", {
    method: "DELETE",
    body: JSON.stringify({ pair }),
  });
}

export async function addPairToHospital(
  pair: string,
  cooldownSeconds: number,
  reason = "manual",
): Promise<{ ok: boolean; pair_key: string; cooldown_seconds: number; health: AdminPairsHealth }> {
  return apiRequest("/admin/pairs/health/hospital", {
    method: "POST",
    body: JSON.stringify({ pair, cooldown_seconds: cooldownSeconds, reason }),
  });
}

export async function addPairToGraveyard(
  pair: string,
  ttlDays: number | null,
): Promise<{ ok: boolean; pair_key: string; ttl_days: number | null; reason: string; health: AdminPairsHealth }> {
  return apiRequest("/admin/pairs/health/graveyard", {
    method: "POST",
    body: JSON.stringify({ pair, ttl_days: ttlDays }),
  });
}

export async function getCointegratedPairs(limit = 500): Promise<CointegratedPairsResponse> {
  return apiRequest<CointegratedPairsResponse>(`/admin/cointegrated-pairs?limit=${limit}`, { method: "GET" });
}

export async function getCointegratedPairDetail(
  sym1: string,
  sym2: string,
  limit = 720,
): Promise<CointegratedPairDetail> {
  const params = new URLSearchParams({ sym_1: sym1, sym_2: sym2, limit: String(limit) });
  return apiRequest<CointegratedPairDetail>(`/admin/cointegrated-pairs/detail?${params.toString()}`, { method: "GET" });
}

export async function getPairDecisionAuditChart(
  pair: string,
  timeframe = "1m",
  startTs?: string | number | null,
  endTs?: string | number | null,
  options: PairDecisionAuditChartOptions = {},
): Promise<PairDecisionAuditChart> {
  const params = new URLSearchParams({ pair, timeframe });
  if (startTs !== null && startTs !== undefined && String(startTs).trim()) {
    params.set("start_ts", String(startTs));
  }
  if (endTs !== null && endTs !== undefined && String(endTs).trim()) {
    params.set("end_ts", String(endTs));
  }
  if (options.includeDecisionTimeline !== undefined) {
    params.set("include_decision_timeline", options.includeDecisionTimeline ? "true" : "false");
  }
  if (options.maxTimelinePoints !== undefined) {
    params.set("max_timeline_points", String(options.maxTimelinePoints));
  }
  if (options.downsampleMethod) {
    params.set("downsample_method", options.downsampleMethod);
  }
  if (options.resolution !== null && options.resolution !== undefined && String(options.resolution).trim()) {
    params.set("resolution", String(options.resolution));
  }
  return apiRequest<PairDecisionAuditChart>(`/admin/cointegrated-pairs/decision-audit?${params.toString()}`, { method: "GET" });
}

export async function getCounterfactualExitStudy(
  entryId: string,
  pair: string,
  timeframe = "1m",
  startTs?: string | number | null,
  endTs?: string | number | null,
): Promise<CounterfactualExitStudy> {
  const params = new URLSearchParams({ entry_id: entryId, pair, timeframe });
  if (startTs !== null && startTs !== undefined && String(startTs).trim()) {
    params.set("start_ts", String(startTs));
  }
  if (endTs !== null && endTs !== undefined && String(endTs).trim()) {
    params.set("end_ts", String(endTs));
  }
  return apiRequest<CounterfactualExitStudy>(`/admin/cointegrated-pairs/decision-audit/counterfactual?${params.toString()}`, { method: "GET" });
}

export async function removeCointegratedPair(sym1: string, sym2: string): Promise<RemoveCointegratedPairResult> {
  return apiRequest<RemoveCointegratedPairResult>("/admin/cointegrated-pairs", {
    method: "DELETE",
    body: JSON.stringify({ sym_1: sym1, sym_2: sym2 }),
  });
}

export async function getPairSupplyStatus(): Promise<PairSupplyStatus> {
  return apiRequest<PairSupplyStatus>("/admin/cointegrated-pairs/supply/status", { method: "GET" });
}

export async function setPairCuratorEnabled(enabled: boolean): Promise<PairCuratorStatus> {
  return apiRequest<PairCuratorStatus>("/admin/cointegrated-pairs/curator/enabled", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

export async function startPairSupply(): Promise<PairSupplyStatus> {
  return apiRequest<PairSupplyStatus>("/admin/cointegrated-pairs/supply/start", { method: "POST", body: JSON.stringify({}) });
}

export async function stopPairSupply(): Promise<PairSupplyStatus> {
  return apiRequest<PairSupplyStatus>("/admin/cointegrated-pairs/supply/stop", { method: "POST", body: JSON.stringify({}) });
}

export async function clearAdminActivePair(): Promise<{
  ok: boolean;
  cleared: boolean;
  file_existed: boolean;
  running: boolean;
  detail: string;
  requested_by: string;
  previous_active_pair: Record<string, string> | null;
  active_pair: null | Record<string, unknown>;
}> {
  return apiRequest("/admin/pairs/active/clear", { method: "POST", body: JSON.stringify({}) });
}

export async function switchAdminActivePair(sym1: string, sym2: string, force: boolean = false): Promise<ManualPairSwitchResult> {
  return apiRequest<ManualPairSwitchResult>("/admin/pairs/active/switch", {
    method: "POST",
    body: JSON.stringify({ sym_1: sym1, sym_2: sym2, force }),
  });
}

export interface ClearLogsResult {
  deleted_logs: number;
  deleted_reports: number;
  deleted_log_files: number;
  deleted_run_rows?: number;
  deleted_run_events?: number;
  deleted_pair_segments?: number;
  deleted_trades?: number;
  deleted_strategy_metrics?: number;
  deleted_regime_metrics?: number;
  deleted_bot_configs?: number;
  deleted_alerts?: number;
  deleted_equity_snapshots?: number;
  deleted_position_snapshots?: number;
  deleted_report_rows: number;
  deleted_report_files: number;
  deleted_indexes: number;
  kept_latest: boolean;
  errors: string[];
}

export async function clearAdminLogs(keepLatest = false): Promise<ClearLogsResult> {
  return apiRequest<ClearLogsResult>(`/admin/logs/clear?keep_latest=${keepLatest}`, { method: "POST" });
}

export async function listUsers(): Promise<UserRecord[]> {
  return apiRequest<UserRecord[]>("/users", { method: "GET" });
}

export async function listRoles(): Promise<RoleRecord[]> {
  return apiRequest<RoleRecord[]>("/users/roles", { method: "GET" });
}

export async function createUser(
  body: { email: string; password: string; is_active?: boolean },
): Promise<UserRecord> {
  return apiRequest<UserRecord>(
    "/users",
    {
      method: "POST",
      body: JSON.stringify({
        email: body.email,
        password: body.password,
        is_active: body.is_active ?? true,
      }),
    },
  );
}

export async function assignUserRole(userId: string, role: string): Promise<{ message: string }> {
  const encodedUser = encodeURIComponent(userId);
  return apiRequest<{ message: string }>(
    `/users/${encodedUser}/roles`,
    { method: "POST", body: JSON.stringify({ role }) },
  );
}

export async function removeUserRole(userId: string, role: string): Promise<{ message: string }> {
  const encodedUser = encodeURIComponent(userId);
  const encodedRole = encodeURIComponent(role);
  return apiRequest<{ message: string }>(`/users/${encodedUser}/roles/${encodedRole}`, { method: "DELETE" });
}

export async function deleteUser(userId: string): Promise<{ message: string }> {
  const encodedUser = encodeURIComponent(userId);
  return apiRequest<{ message: string }>(`/users/${encodedUser}`, { method: "DELETE" });
}

export async function updateUserPermissions(
  userId: string,
  permissions: string[],
): Promise<UserRecord> {
  const encodedUser = encodeURIComponent(userId);
  return apiRequest<UserRecord>(
    `/users/${encodedUser}/permissions`,
    {
      method: "PUT",
      body: JSON.stringify({ permissions }),
    },
  );
}

export async function createRole(
  body: { name: string; description?: string | null; permissions?: string[] },
): Promise<RoleRecord> {
  return apiRequest<RoleRecord>(
    "/users/roles",
    {
      method: "POST",
      body: JSON.stringify({
        name: body.name,
        description: body.description || null,
        permissions: body.permissions || [],
      }),
    },
  );
}

export async function updateRole(
  roleId: string,
  body: { name?: string; description?: string | null; permissions?: string[] },
): Promise<RoleRecord> {
  const encodedRoleId = encodeURIComponent(roleId);
  return apiRequest<RoleRecord>(
    `/users/roles/${encodedRoleId}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
}

export async function deleteRole(roleId: string): Promise<{ message: string }> {
  const encodedRoleId = encodeURIComponent(roleId);
  return apiRequest<{ message: string }>(`/users/roles/${encodedRoleId}`, { method: "DELETE" });
}

export function apiBaseUrl(): string {
  return API_BASE;
}

export function apiRootUrl(): string {
  return API_BASE.replace(/\/api\/v2\/?$/, "");
}

export function wsDashboardUrl(botInstanceId: string): string {
  const wsBase = resolveWsBase();
  const encoded = encodeURIComponent(botInstanceId);
  return `${wsBase}/ws/dashboard?bot_instance_id=${encoded}`;
}

export function isUnauthorizedError(err: unknown): boolean {
  return (err instanceof ApiError && err.status === 401) || (err instanceof Error && err.message.includes("HTTP 401"));
}

export function isForbiddenError(err: unknown): boolean {
  return (err instanceof ApiError && err.status === 403) || (err instanceof Error && err.message.includes("HTTP 403"));
}
