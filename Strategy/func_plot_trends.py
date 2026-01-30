from func_cointegration import extract_close_prices
from func_cointegration import calculate_cointegration
from func_cointegration import calculate_spread
from func_cointegration import calculate_zscore
from func_strategy_log import get_strategy_logger
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np


# Plot prices and trends
def plot_trends(sym_1, sym_2, price_data):
    """
    Plot price trends, spread, and z-score for a cointegrated pair

    Args:
        sym_1: First symbol
        sym_2: Second symbol
        price_data: Dictionary containing klines data
    """

    logger = get_strategy_logger()
    # Extract close prices
    prices_1 = extract_close_prices(price_data[sym_1]['klines'])
    prices_2 = extract_close_prices(price_data[sym_2]['klines'])

    # Remove NaNs
    prices_1 = [p for p in prices_1 if not np.isnan(p)]
    prices_2 = [p for p in prices_2 if not np.isnan(p)]

    # Check if price extraction was successful
    if len(prices_1) == 0:
        logger.warning("Skipping pair %s: invalid price data", sym_1)
        print(f"WARNING: Skipping plot for {sym_1} (invalid data).")
        return
    if len(prices_2) == 0:
        logger.warning("Skipping pair %s: invalid price data", sym_2)
        print(f"WARNING: Skipping plot for {sym_2} (invalid data).")
        return

    # Check for zero variance
    if len(set(prices_1)) == 1:
        logger.warning("Skipping pair %s: zero variance", sym_1)
        print(f"WARNING: Skipping plot for {sym_1} (zero variance).")
        return
    if len(set(prices_2)) == 1:
        logger.warning("Skipping pair %s: zero variance", sym_2)
        print(f"WARNING: Skipping plot for {sym_2} (zero variance).")
        return

    # Align lengths to avoid broadcast errors when one series has a missing candle
    if len(prices_1) != len(prices_2):
        min_len = min(len(prices_1), len(prices_2))
        logger.warning(
            "Length mismatch for %s/%s (%d vs %d). Trimming to %d.",
            sym_1,
            sym_2,
            len(prices_1),
            len(prices_2),
            min_len,
        )
        prices_1 = prices_1[-min_len:]
        prices_2 = prices_2[-min_len:]

    # Convert to numpy arrays
    prices_1 = np.array(prices_1, dtype=float)
    prices_2 = np.array(prices_2, dtype=float)

    # Get cointegration statistics
    coint_flag, p_value, adf_statistic, critical_value, hedge_ratio, zero_crossings = calculate_cointegration(
        prices_1, prices_2
    )
    logger.info(
        "Cointegration analysis %s/%s: flag=%s p=%.6f adf=%.6f crit=%.6f hedge=%.6f zero=%s",
        sym_1,
        sym_2,
        coint_flag,
        p_value if p_value is not None else float("nan"),
        adf_statistic if adf_statistic is not None else float("nan"),
        critical_value if critical_value is not None else float("nan"),
        hedge_ratio if hedge_ratio is not None else float("nan"),
        zero_crossings,
    )

    if hedge_ratio is None or not np.isfinite(hedge_ratio):
        logger.warning("Skipping spread/zscore for %s/%s: invalid hedge ratio", sym_1, sym_2)
        print(f"WARNING: Skipping plot for {sym_1}/{sym_2} (invalid hedge ratio).")
        return

    # Log transform prices BEFORE calculating spread
    log_prices_1 = np.log(prices_1)
    log_prices_2 = np.log(prices_2)

    # Calculate spread using logged prices
    spread = calculate_spread(log_prices_1, log_prices_2, hedge_ratio)
    zscore = calculate_zscore(spread)

    # Calculate percentage changes for normalized plotting
    df = pd.DataFrame(columns=[sym_1, sym_2])
    df[sym_1] = prices_1
    df[sym_2] = prices_2
    df[f"{sym_1}_pct"] = df[sym_1] / prices_1[0]
    df[f"{sym_2}_pct"] = df[sym_2] / prices_2[0]
    series_1 = df[f"{sym_1}_pct"].astype(float).values
    series_2 = df[f"{sym_2}_pct"].astype(float).values

    # Save results for backtesting
    df_2 = pd.DataFrame()
    df_2[sym_1] = prices_1  # Raw prices
    df_2[sym_2] = prices_2  # Raw prices
    df_2[f"{sym_1}_log"] = log_prices_1  # Log prices
    df_2[f"{sym_2}_log"] = log_prices_2  # Log prices
    df_2["Spread"] = spread
    df_2["ZScore"] = zscore
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "3_backtest_file.csv"
    df_2.to_csv(output_path, index=False)
    try:
        rel_path = output_path.relative_to(Path(__file__).resolve().parent)
    except ValueError:
        rel_path = output_path
    print(f"Backtest saved: {rel_path}")
    logger.info("Backtest file saved: %s", rel_path)

    # Spread statistics (log only)
    logger.info(
        "Spread stats %s/%s: mean=%.6f std=%.6f min=%.6f max=%.6f current=%.6f",
        sym_1,
        sym_2,
        float(np.mean(spread)),
        float(np.std(spread)),
        float(np.min(spread)),
        float(np.max(spread)),
        float(spread[-1]),
    )

    # Z-score statistics (log only)
    zscore_clean = zscore[~np.isnan(zscore)]
    if len(zscore_clean) > 0:
        logger.info(
            "Zscore stats %s/%s: mean=%.4f std=%.4f min=%.4f max=%.4f current=%.4f",
            sym_1,
            sym_2,
            float(np.mean(zscore_clean)),
            float(np.std(zscore_clean)),
            float(np.min(zscore_clean)),
            float(np.max(zscore_clean)),
            float(zscore_clean[-1]),
        )

    # Plot chart
    fig, axs = plt.subplots(3, figsize=(16, 10), sharex=True)
    fig.suptitle(f"Price and Spread Analysis - {sym_1} vs {sym_2}", fontsize=16, fontweight='bold')

    # Top Plot: Normalized Prices
    axs[0].plot(series_1, label=f"{sym_1} (Scaled)", linewidth=2, color='blue')
    axs[0].plot(series_2, label=f"{sym_2} (Scaled)", linewidth=2, color='orange')
    axs[0].set_ylabel("Price Index (Normalized)", fontsize=12)
    axs[0].legend(loc="upper left", fontsize=10)
    axs[0].grid(True, alpha=0.3)
    axs[0].set_title("Normalized Price Movement", fontsize=12, loc='left')

    # Middle Plot: Spread
    axs[1].plot(spread, color='purple', linewidth=2, label='Spread')
    axs[1].axhline(np.mean(spread), color='black', linestyle='--', linewidth=1, label='Mean')
    axs[1].axhline(np.mean(spread) + 2 * np.std(spread), color='red', linestyle=':', alpha=0.5, label='+2 std')
    axs[1].axhline(np.mean(spread) - 2 * np.std(spread), color='green', linestyle=':', alpha=0.5, label='-2 std')
    axs[1].fill_between(range(len(spread)),
                        np.mean(spread) - 2 * np.std(spread),
                        np.mean(spread) + 2 * np.std(spread),
                        alpha=0.1, color='gray')
    axs[1].set_ylabel("Log Spread", fontsize=12)
    axs[1].legend(loc="upper left", fontsize=8)
    axs[1].grid(True, alpha=0.3)
    axs[1].set_title("Spread (Mean Reversion)", fontsize=12, loc='left')

    # Bottom Plot: Z-Score
    axs[2].plot(zscore, color='teal', linewidth=2, label='Z-Score')
    axs[2].axhline(0, color="black", linewidth=1)
    axs[2].axhline(2, color="red", linestyle="--", linewidth=1, label="Overbought (+2)")
    axs[2].axhline(-2, color="green", linestyle="--", linewidth=1, label="Oversold (-2)")
    axs[2].fill_between(range(len(zscore)), -2, 2, alpha=0.1, color='gray')
    axs[2].set_ylabel("Z-Score", fontsize=12)
    axs[2].set_xlabel("Time Period", fontsize=12)
    axs[2].legend(loc="upper left", fontsize=8)
    axs[2].grid(True, alpha=0.3)
    axs[2].set_title("Z-Score (Trading Signals)", fontsize=12, loc='left')

    plt.tight_layout(rect=[0, 0.03, 1, 0.97])
    plt.show()
    print("Plot displayed.")
