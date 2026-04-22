"""
     OKX STRATEGY CODE
"""

from pathlib import Path
import json
import os
import sys

from func_get_symbols import get_symbols_by_maker_fees
from func_prices_json import store_price_history
from func_cointegration import get_cointegrated_pairs
from func_plot_trends import plot_trends
from func_summary_report import generate_summary_report
from func_strategy_log import get_strategy_logger
from config_strategy_api import (
    time_frame,
    kline_limit,
    z_score_window,
    min_equity_filter_usdt,
    settle_ccy_filter,
    max_pairs_per_ticker,
    min_p_value_filter,
    max_p_value_filter,
    min_zero_crossings,
    min_hedge_ratio,
    max_hedge_ratio,
    min_capital_per_leg,
    liquidity_window,
    min_avg_quote_volume,
    is_demo,
    corr_min_filter,
    log_strategy_config,
)


DEFAULT_LIQUIDITY_PCT = 0.3
FALLBACK_LIQUIDITY_PCTS = [0.3, 0.25, 0.2, 0.15, 0.1, 0.0]


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _env_float_list(name, default_list):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return list(default_list)
    values = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(float(part))
        except (TypeError, ValueError):
            continue
    return values if values else list(default_list)


def _env_int_list(name, default_list):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return list(default_list)
    values = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(int(float(part)))
        except (TypeError, ValueError):
            continue
    return values if values else list(default_list)


def _build_relax_tiers(base_value, candidates, direction):
    tiers = []
    for value in candidates:
        if value is None:
            continue
        try:
            val = float(value)
        except (TypeError, ValueError):
            continue
        if direction == "down":
            if val <= base_value + 1e-9:
                tiers.append(val)
        else:
            if val >= base_value - 1e-9:
                tiers.append(val)
    if base_value not in tiers:
        tiers.append(base_value)
    reverse = True if direction == "down" else False
    tiers = sorted({round(v, 8) for v in tiers}, reverse=reverse)
    return tiers


def _build_liquidity_fallbacks(base_pct):
    try:
        base_pct = float(base_pct)
    except (TypeError, ValueError):
        base_pct = DEFAULT_LIQUIDITY_PCT

    if base_pct < 0:
        base_pct = 0.0
    if base_pct > 1:
        base_pct = 1.0

    steps = []
    for value in FALLBACK_LIQUIDITY_PCTS:
        try:
            pct = float(value)
        except (TypeError, ValueError):
            continue
        if pct < 0:
            pct = 0.0
        if pct > 1:
            pct = 1.0
        if pct not in steps:
            steps.append(pct)

    if base_pct not in steps:
        steps.insert(0, base_pct)

    steps = sorted(steps, reverse=True)
    return [pct for pct in steps if pct <= base_pct]


def _update_env_value(path, key, value):
    line_value = f"{key}={value}"
    if not path.exists():
        path.write_text(line_value + "\n", encoding="utf-8")
        return

    lines = path.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key_part, rest = stripped.split("=", 1)
        if key_part.strip() != key:
            new_lines.append(line)
            continue
        comment = ""
        if "#" in rest:
            _, comment = rest.split("#", 1)
            comment = " #" + comment.strip()
        new_lines.append(f"{line_value}{comment}")
        updated = True

    if not updated:
        new_lines.append(line_value)
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main():
    base_dir = Path(__file__).resolve().parent
    output_dir = base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(base_dir)
    logger = get_strategy_logger()

    price_path = output_dir / "1_price_list.json"
    coint_path = output_dir / "2_cointegrated_pairs.csv"
    env_path = base_dir / ".env"

    log_strategy_config(logger=logger, to_console=False)

    mode_label = "DEMO" if is_demo else "LIVE"
    settle_label = ",".join(settle_ccy_filter) if settle_ccy_filter else "ALL"
    min_equity_label = f"{min_equity_filter_usdt:.2f}" if min_equity_filter_usdt > 0 else "off"
    fallback_enabled = str(os.getenv("STATBOT_STRATEGY_INTERNAL_FALLBACK_ENABLED", "1")).strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    try:
        min_pairs_needed = int(float(os.getenv("STATBOT_STRATEGY_INTERNAL_MIN_PAIRS", "10")))
    except (TypeError, ValueError):
        min_pairs_needed = 3
    if min_pairs_needed < 1:
        min_pairs_needed = 1

    print("Strategy scan starting...")
    print(
        "Config: mode={0} tf={1} klines={2} z={3} liquidity_pct={4:.2f}".format(
            mode_label,
            time_frame,
            kline_limit,
            z_score_window,
            _safe_float(os.getenv("STATBOT_STRATEGY_LIQUIDITY_PCT"), DEFAULT_LIQUIDITY_PCT),
        )
    )
    print(
        "Filters: p_value=[{0}, {1}] zero_cross>={2} hedge_ratio=[{3}, {4}] "
        "min_cap_per_leg={5} min_equity<={6} settle={7}".format(
            min_p_value_filter,
            max_p_value_filter,
            min_zero_crossings,
            min_hedge_ratio,
            max_hedge_ratio,
            min_capital_per_leg,
            min_equity_label,
            settle_label,
        )
    )
    print(
        "Liquidity: window={0} min_avg_quote={1} percentile={2:.2f}".format(
            liquidity_window,
            min_avg_quote_volume,
            _safe_float(os.getenv("STATBOT_STRATEGY_LIQUIDITY_PCT"), DEFAULT_LIQUIDITY_PCT),
        )
    )
    print(
        "Fallback: enabled={0} min_pairs={1}".format(
            "yes" if fallback_enabled else "no",
            min_pairs_needed,
        )
    )

    # STEP 1: Get tradeable symbols with maker fees
    result = get_symbols_by_maker_fees(
        inst_type="SWAP",  # SWAP = Perpetual, FUTURES = Expiry, SPOT = Spot
        max_maker_fee=0.0002,  # Less than 0.02%
    )

    # Combine all qualifying symbols
    all_symbols = result.get('low_fee_symbols', []) + result.get('negative_fee_symbols', [])

    # STEP 2: Construct and save price history
    if len(all_symbols) > 0:
        print(f"Symbols qualifying for trading: {len(all_symbols)}")
        store_price_history(all_symbols)
    else:
        print("No symbols found matching criteria.")
        return 1

    # STEP 3: Find co-integrated pairs
    if not price_path.exists():
        print("WARNING: No price data available.")
        return 1

    with price_path.open("r", encoding="utf-8") as json_file:
        price_data = json.load(json_file)

    if len(price_data) == 0:
        print("WARNING: No price data available.")
        return 1

    base_liquidity_pct = _safe_float(
        os.getenv("STATBOT_STRATEGY_LIQUIDITY_PCT"),
        DEFAULT_LIQUIDITY_PCT,
    )
    fallback_steps = _build_liquidity_fallbacks(base_liquidity_pct)
    df_coint = None
    coint_summary = None
    used_liquidity_pct = None

    base_corr = corr_min_filter
    base_pvalue_max = max_p_value_filter
    base_zero_cross = min_zero_crossings
    base_min_equity = min_equity_filter_usdt
    base_min_capital = min_capital_per_leg

    corr_candidates = _env_float_list(
        "STATBOT_STRATEGY_INTERNAL_CORR_TIERS",
        [base_corr, 0.15, 0.10, 0.05, 0.0],
    )
    pvalue_candidates = _env_float_list(
        "STATBOT_STRATEGY_INTERNAL_PVALUE_MAX_TIERS",
        # [base_pvalue_max, 0.05, 0.10, 0.15, 0.20],
        [base_pvalue_max, 0.05, 0.10],
    )
    zero_cross_candidates = _env_int_list(
        "STATBOT_STRATEGY_INTERNAL_ZERO_CROSS_TIERS",
        [base_zero_cross, 7, 5, 3, 1],
    )
    equity_mults = _env_float_list(
        "STATBOT_STRATEGY_INTERNAL_MIN_EQUITY_MULTS",
        [1.0,0.8,0.6,0.4,0.2,0.0],
    )
    min_capital_mults = _env_float_list(
        "STATBOT_STRATEGY_INTERNAL_MIN_CAPITAL_MULTS",
        [1.0,0.75,0.5,0.25,0.0],
    )

    corr_tiers = _build_relax_tiers(base_corr, corr_candidates, "down")
    pvalue_tiers = _build_relax_tiers(base_pvalue_max, pvalue_candidates, "up")
    zero_cross_tiers = _build_relax_tiers(base_zero_cross, zero_cross_candidates, "down")
    if base_min_equity and base_min_equity > 0:
        equity_candidates = [base_min_equity * mult for mult in equity_mults if mult >= 0]
        equity_tiers = _build_relax_tiers(base_min_equity, equity_candidates, "up")
    else:
        equity_tiers = [0.0]
    if base_min_capital and base_min_capital > 0:
        min_cap_candidates = [base_min_capital * mult for mult in min_capital_mults if mult >= 0]
        min_capital_tiers = _build_relax_tiers(base_min_capital, min_cap_candidates, "down")
    else:
        min_capital_tiers = [0.0]

    def _attempt_filters(pct, corr_min, pvalue_max, zero_cross_min, min_equity, min_capital, label):
        df, summary = get_cointegrated_pairs(
            price_data,
            liquidity_pct_override=pct,
            corr_min_override=corr_min,
            max_p_value_override=pvalue_max,
            min_zero_crossings_override=zero_cross_min,
            min_equity_filter_override=min_equity,
            min_capital_per_leg_override=min_capital,
        )
        count = len(df)
        logger.info(
            "Strategy fallback %s: pairs=%d corr_min=%.3f pval_max=%.4f zc_min=%s min_eq=%.2f min_cap=%.4f",
            label,
            count,
            corr_min,
            pvalue_max,
            int(zero_cross_min),
            min_equity,
            min_capital,
        )
        return df, summary

    def _run_filter_fallbacks(pct):
        best_df = None
        best_summary = None
        best_settings = None
        best_count = -1

        def _record_best(df, summary, settings):
            nonlocal best_df, best_summary, best_settings, best_count
            count = len(df)
            if count > best_count:
                best_df = df
                best_summary = summary
                best_settings = settings
                best_count = count

        def _attempt(label, corr_min, pvalue_max, zero_cross_min, min_equity, min_capital):
            df, summary = _attempt_filters(
                pct,
                corr_min,
                pvalue_max,
                zero_cross_min,
                min_equity,
                min_capital,
                label,
            )
            settings = {
                "corr_min": corr_min,
                "pvalue_max": pvalue_max,
                "zero_cross_min": zero_cross_min,
                "min_equity": min_equity,
                "min_capital": min_capital,
            }
            _record_best(df, summary, settings)
            if len(df) >= min_pairs_needed:
                return df, summary, settings, True
            return None, None, None, False

        df, summary, settings, ok = _attempt(
            "base",
            base_corr,
            base_pvalue_max,
            base_zero_cross,
            base_min_equity,
            base_min_capital,
        )
        if ok:
            return df, summary, settings, True
        if not fallback_enabled:
            return best_df, best_summary, best_settings, False

        for min_equity in equity_tiers:
            for min_capital in min_capital_tiers:
                if min_equity == base_min_equity and min_capital == base_min_capital:
                    continue
                df, summary, settings, ok = _attempt(
                    "equity_cap",
                    base_corr,
                    base_pvalue_max,
                    base_zero_cross,
                    min_equity,
                    min_capital,
                )
                if ok:
                    return df, summary, settings, True

        relaxed_equity = equity_tiers[-1]
        relaxed_min_capital = min_capital_tiers[-1]

        for zero_cross_min in zero_cross_tiers:
            if zero_cross_min == base_zero_cross:
                continue
            df, summary, settings, ok = _attempt(
                "zero_cross",
                base_corr,
                base_pvalue_max,
                zero_cross_min,
                relaxed_equity,
                relaxed_min_capital,
            )
            if ok:
                return df, summary, settings, True

        relaxed_zero_cross = zero_cross_tiers[-1]
        for pvalue_max in pvalue_tiers:
            if pvalue_max == base_pvalue_max:
                continue
            df, summary, settings, ok = _attempt(
                "p_value",
                base_corr,
                pvalue_max,
                relaxed_zero_cross,
                relaxed_equity,
                relaxed_min_capital,
            )
            if ok:
                return df, summary, settings, True

        relaxed_pvalue = pvalue_tiers[-1]
        for corr_min in corr_tiers:
            if corr_min == base_corr:
                continue
            df, summary, settings, ok = _attempt(
                "corr",
                corr_min,
                relaxed_pvalue,
                relaxed_zero_cross,
                relaxed_equity,
                relaxed_min_capital,
            )
            if ok:
                return df, summary, settings, True

        return best_df, best_summary, best_settings, False

    used_settings = None
    best_overall_df = None
    best_overall_summary = None
    best_overall_settings = None
    best_overall_liquidity = None
    best_overall_count = -1
    for attempt, pct in enumerate(fallback_steps, start=1):
        label = f"Attempt {attempt}/{len(fallback_steps)}"
        print(f"Cointegration {label}: liquidity pct {pct:.2f}")
        if pct != base_liquidity_pct:
            _update_env_value(env_path, "STATBOT_STRATEGY_LIQUIDITY_PCT", pct)
            logger.warning(
                "Strategy liquidity attempt %d/%d: liquidity pct %.2f",
                attempt,
                len(fallback_steps),
                pct,
            )
        else:
            logger.info(
                "Strategy liquidity attempt %d/%d: liquidity pct %.2f",
                attempt,
                len(fallback_steps),
                pct,
            )

        df_coint, coint_summary, used_settings, meets_min_pairs = _run_filter_fallbacks(pct)
        if df_coint is not None and len(df_coint) > 0:
            if len(df_coint) > best_overall_count:
                best_overall_df = df_coint
                best_overall_summary = coint_summary
                best_overall_settings = used_settings
                best_overall_liquidity = pct
                best_overall_count = len(df_coint)
            used_liquidity_pct = pct
            if meets_min_pairs or attempt == len(fallback_steps):
                break
            print(
                "Cointegration: {0} pairs below min {1}, relaxing liquidity...".format(
                    len(df_coint),
                    min_pairs_needed,
                )
            )
            logger.info(
                "Cointegration pairs below min (%d < %d) at liquidity pct %.2f",
                len(df_coint),
                min_pairs_needed,
                pct,
            )
            continue

        print(f"Cointegration: no pairs at liquidity pct {pct:.2f}, relaxing...")
        logger.info("No pairs at liquidity pct %.2f", pct)

    if (df_coint is None or len(df_coint) == 0) and best_overall_df is not None:
        df_coint = best_overall_df
        coint_summary = best_overall_summary
        used_settings = best_overall_settings
        used_liquidity_pct = best_overall_liquidity

    if df_coint is None or len(df_coint) == 0:
        print("WARNING: No cointegrated pairs found after liquidity fallback.")
        logger.error("Strategy fallback failed: no cointegrated pairs.")
        return 1

    if used_liquidity_pct is not None and used_liquidity_pct != base_liquidity_pct:
        _update_env_value(env_path, "STATBOT_STRATEGY_LIQUIDITY_PCT", base_liquidity_pct)
        logger.info(
            "Strategy fallback restored STATBOT_STRATEGY_LIQUIDITY_PCT to %.2f.",
            base_liquidity_pct,
        )
    elif used_liquidity_pct is not None and base_liquidity_pct != DEFAULT_LIQUIDITY_PCT:
        _update_env_value(env_path, "STATBOT_STRATEGY_LIQUIDITY_PCT", base_liquidity_pct)
        logger.info(
            "Strategy reset STATBOT_STRATEGY_LIQUIDITY_PCT to %.2f.",
            base_liquidity_pct,
        )

    if len(df_coint) > 0:
        if coint_summary:
            usable_crossings = coint_summary.get(
                "usable_pairs_with_crossings",
                coint_summary.get("pairs_kept", len(df_coint)),
            )
            pre_filter_crossings = coint_summary.get(
                "pre_filter_pairs_with_crossings",
                coint_summary.get("pairs_with_crossings", usable_crossings),
            )
            print(
                "Cointegration: pairs_kept={0} usable_crossings={1} pre_filter_crossings={2} total_pairs={3} liquidity_pct={4:.2f}".format(
                    len(df_coint),
                    usable_crossings,
                    pre_filter_crossings,
                    coint_summary.get("total_pairs", 0),
                    coint_summary.get("liquidity_pct", base_liquidity_pct),
                )
            )
        else:
            print(f"Cointegration: pairs_kept={len(df_coint)}")
        try:
            rel_coint_path = coint_path.relative_to(base_dir)
        except ValueError:
            rel_coint_path = coint_path
        print(f"Cointegration output: {rel_coint_path}")
    else:
        print("WARNING: No cointegrated pairs found.")
        return 1

    # STEP 4: Plot trends and save for back testing
    # Get the best pair (highest zero crossings = most trading opportunities)
    if len(df_coint) > 0:
        best_pair = df_coint.iloc[0]
        symbol_1 = best_pair['sym_1']
        symbol_2 = best_pair['sym_2']

        print(
            "Best pair: {0}/{1} p_value={2} zero_crossings={3}".format(
                symbol_1,
                symbol_2,
                best_pair["p_value"],
                int(best_pair["zero_crossing"]),
            )
        )

        plot_trends(symbol_1, symbol_2, price_data)
    else:
        print("WARNING: No cointegrated pairs available for plotting.")

    # STEP 5: Generate a summary report
    report_file = generate_summary_report(top_n=3)

    print("Strategy analysis complete.")
    try:
        rel_output = output_dir.relative_to(base_dir)
    except ValueError:
        rel_output = output_dir
    print(f"Output folder: {rel_output}")
    print("Files: 1_price_list.json, 2_cointegrated_pairs.csv, 3_backtest_file.csv")
    if report_file:
        print(f"Summary report: {report_file}")
    print("Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
