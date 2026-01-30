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


DEFAULT_LIQUIDITY_PCT = 0.3
FALLBACK_LIQUIDITY_PCT = 0.2


def _safe_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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

    price_path = output_dir / "1_price_list.json"
    coint_path = output_dir / "2_cointegrated_pairs.csv"
    env_path = base_dir / ".env"

    # STEP 1: Get tradeable symbols with maker fees
    result = get_symbols_by_maker_fees(
        inst_type="SWAP",  # SWAP = Perpetual, FUTURES = Expiry, SPOT = Spot
        max_maker_fee=0.0002,  # Less than 0.02%
    )

    # Combine all qualifying symbols
    all_symbols = result.get('low_fee_symbols', []) + result.get('negative_fee_symbols', [])

    # STEP 2: Construct and save price history
    if len(all_symbols) > 0:
        print(f"\nFound {len(all_symbols)} symbols qualifying for trading")
        store_price_history(all_symbols)
    else:
        print("No symbols found matching criteria")
        return 1

    # STEP 3: Find co-integrated pairs
    print("\n" + "=" * 60)
    print("STEP 3: Calculating co-integration...")
    print("=" * 60)

    if not price_path.exists():
        print("WARNING: No price data available")
        return 1

    with price_path.open("r", encoding="utf-8") as json_file:
        price_data = json.load(json_file)

    if len(price_data) == 0:
        print("WARNING: No price data available")
        return 1

    current_liquidity_pct = _safe_float(
        os.getenv("STATBOT_STRATEGY_LIQUIDITY_PCT"),
        DEFAULT_LIQUIDITY_PCT,
    )
    df_coint = get_cointegrated_pairs(price_data, liquidity_pct_override=current_liquidity_pct)
    if len(df_coint) == 0 and current_liquidity_pct > FALLBACK_LIQUIDITY_PCT:
        print(
            "No cointegrated pairs found. "
            "Lowering STATBOT_STRATEGY_LIQUIDITY_PCT to 0.2 for the next scan."
        )
        _update_env_value(env_path, "STATBOT_STRATEGY_LIQUIDITY_PCT", FALLBACK_LIQUIDITY_PCT)
        df_coint = get_cointegrated_pairs(price_data, liquidity_pct_override=FALLBACK_LIQUIDITY_PCT)
        if len(df_coint) == 0:
            print("WARNING: No cointegrated pairs found after liquidity fallback.")
            return 1
        _update_env_value(env_path, "STATBOT_STRATEGY_LIQUIDITY_PCT", DEFAULT_LIQUIDITY_PCT)
    elif len(df_coint) > 0 and current_liquidity_pct != DEFAULT_LIQUIDITY_PCT:
        _update_env_value(env_path, "STATBOT_STRATEGY_LIQUIDITY_PCT", DEFAULT_LIQUIDITY_PCT)

    if len(df_coint) > 0:
        print(f"OK: Found {len(df_coint)} cointegrated pairs")
        try:
            rel_coint_path = coint_path.relative_to(base_dir)
        except ValueError:
            rel_coint_path = coint_path
        print(f"OK: Saved to {rel_coint_path}")
    else:
        print("WARNING: No cointegrated pairs found")
        return 1

    # STEP 4: Plot trends and save for back testing
    print("\n" + "=" * 60)
    print("STEP 4: Plotting trends and saving for backtesting...")
    print("=" * 60)

    # Get the best pair (highest zero crossings = most trading opportunities)
    if len(df_coint) > 0:
        best_pair = df_coint.iloc[0]
        symbol_1 = best_pair['sym_1']
        symbol_2 = best_pair['sym_2']

        print("\nAnalyzing best pair:")
        print(f"  Symbol 1: {symbol_1}")
        print(f"  Symbol 2: {symbol_2}")
        print(f"  P-value: {best_pair['p_value']}")
        print(f"  Zero Crossings: {int(best_pair['zero_crossing'])}")

        plot_trends(symbol_1, symbol_2, price_data)
    else:
        print("WARNING: No cointegrated pairs available for plotting")

    # STEP 5: Generate a summary report
    print("\n" + "=" * 60)
    print("STEP 5: Generating comprehensive summary report...")
    print("=" * 60)

    report_file = generate_summary_report(top_n=3)

    print("\n" + "=" * 60)
    print("STRATEGY ANALYSIS COMPLETE")
    print("=" * 60)
    print("\nGenerated Files:")
    try:
        rel_output = output_dir.relative_to(base_dir)
    except ValueError:
        rel_output = output_dir
    print(f"  Output folder: {rel_output}")
    print("  1. 1_price_list.json         - Historical price data")
    print("  2. 2_cointegrated_pairs.csv  - All cointegrated pairs")
    print("  3. 3_backtest_file.csv       - Best pair backtest data")
    if report_file:
        print(f"  4. {report_file}      - CSV summary report")
    print("\nNext Steps:")
    print("  - Review the CSV summary report")
    print("  - Analyze the top pairs for trading opportunities")
    print("  - Use backtest file to simulate trading strategies")
    print("  - Monitor Z-scores for entry/exit signals")
    print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
