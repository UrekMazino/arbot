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

    def _run_fallback(pass_label, corr_override):
        nonlocal df_coint, coint_summary, used_liquidity_pct
        for attempt, pct in enumerate(fallback_steps, start=1):
            label = f"Attempt {attempt}/{len(fallback_steps)}"
            corr_label = f"corr_min={corr_override:.2f}" if corr_override is not None else "corr_min=default"
            print(f"Cointegration {label}: liquidity pct {pct:.2f} ({corr_label})")
            if pct != base_liquidity_pct:
                _update_env_value(env_path, "STATBOT_STRATEGY_LIQUIDITY_PCT", pct)
                logger.warning(
                    "Strategy %s attempt %d/%d: liquidity pct %.2f corr_min=%s",
                    pass_label,
                    attempt,
                    len(fallback_steps),
                    pct,
                    "default" if corr_override is None else f"{corr_override:.2f}",
                )
            else:
                logger.info(
                    "Strategy %s attempt %d/%d: liquidity pct %.2f corr_min=%s",
                    pass_label,
                    attempt,
                    len(fallback_steps),
                    pct,
                    "default" if corr_override is None else f"{corr_override:.2f}",
                )

            df_coint, coint_summary = get_cointegrated_pairs(
                price_data,
                liquidity_pct_override=pct,
                corr_min_override=corr_override,
            )
            if len(df_coint) > 0:
                used_liquidity_pct = pct
                if pct != base_liquidity_pct:
                    print(f"Cointegration: found pairs at liquidity pct {pct:.2f}")
                return True

            print(f"Cointegration: no pairs at liquidity pct {pct:.2f}, relaxing...")
            logger.info("No pairs at liquidity pct %.2f", pct)
        return False

    if not _run_fallback("liquidity", None) and corr_min_filter > 0:
        print("Cointegration: disabling correlation filter and retrying.")
        logger.warning("Strategy fallback: disabling corr_min filter after no pairs.")
        corr_override = 0.0
        _run_fallback("corr_disable", corr_override)

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
            print(
                "Cointegration: pairs_kept={0} total_pairs={1} crossings={2} liquidity_pct={3:.2f}".format(
                    len(df_coint),
                    coint_summary.get("total_pairs", 0),
                    coint_summary.get("pairs_with_crossings", 0),
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
