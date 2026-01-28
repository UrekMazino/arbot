"""
Generate comprehensive summary report with top cointegrated pairs
Includes charts, statistics, and trading recommendations
"""

import pandas as pd
import numpy as np
import json
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from func_cointegration import extract_close_prices, calculate_cointegration, calculate_spread, calculate_zscore
from datetime import datetime


def plot_pair_analysis(sym_1, sym_2, price_data, ax_prices, ax_spread, ax_zscore):
    """
    Plot analysis for a single pair on provided axes

    Args:
        sym_1: First symbol
        sym_2: Second symbol
        price_data: Dictionary containing klines data
        ax_prices, ax_spread, ax_zscore: Matplotlib axes

    Returns:
        dict: Statistics for this pair
    """
    # Extract close prices
    prices_1 = np.array(extract_close_prices(price_data[sym_1]['klines']), dtype=float)
    prices_2 = np.array(extract_close_prices(price_data[sym_2]['klines']), dtype=float)

    if len(prices_1) == 0 or len(prices_2) == 0:
        return None

    min_len = min(len(prices_1), len(prices_2))
    if min_len < 2:
        return None
    if len(prices_1) != len(prices_2):
        prices_1 = prices_1[-min_len:]
        prices_2 = prices_2[-min_len:]

    # Get cointegration statistics
    coint_flag, p_value, adf_stat, crit_val, hedge_ratio, zero_crossings = calculate_cointegration(
        prices_1, prices_2
    )

    if hedge_ratio is None or not np.isfinite(hedge_ratio):
        return None

    # Log transform and calculate spread
    log_prices_1 = np.log(prices_1)
    log_prices_2 = np.log(prices_2)
    spread = calculate_spread(log_prices_1, log_prices_2, hedge_ratio)
    zscore = calculate_zscore(spread)

    # Normalize prices for plotting
    norm_prices_1 = prices_1 / prices_1[0]
    norm_prices_2 = prices_2 / prices_2[0]

    # Plot normalized prices
    ax_prices.plot(norm_prices_1, label=sym_1, linewidth=2, color='blue')
    ax_prices.plot(norm_prices_2, label=sym_2, linewidth=2, color='orange')
    ax_prices.set_ylabel("Normalized Price", fontsize=10)
    ax_prices.legend(loc="upper left", fontsize=8)
    ax_prices.grid(True, alpha=0.3)
    ax_prices.set_title(f"{sym_1} vs {sym_2}", fontsize=11, fontweight='bold')

    # Plot spread
    ax_spread.plot(spread, color='purple', linewidth=2)
    ax_spread.axhline(np.mean(spread), color='black', linestyle='--', linewidth=1)
    ax_spread.axhline(np.mean(spread) + 2*np.std(spread), color='red', linestyle=':', alpha=0.5)
    ax_spread.axhline(np.mean(spread) - 2*np.std(spread), color='green', linestyle=':', alpha=0.5)
    ax_spread.fill_between(range(len(spread)),
                           np.mean(spread) - 2*np.std(spread),
                           np.mean(spread) + 2*np.std(spread),
                           alpha=0.1, color='gray')
    ax_spread.set_ylabel("Spread", fontsize=10)
    ax_spread.grid(True, alpha=0.3)

    # Plot z-score
    ax_zscore.plot(zscore, color='teal', linewidth=2)
    ax_zscore.axhline(0, color="black", linewidth=1)
    ax_zscore.axhline(2, color="red", linestyle="--", linewidth=1)
    ax_zscore.axhline(-2, color="green", linestyle="--", linewidth=1)
    ax_zscore.fill_between(range(len(zscore)), -2, 2, alpha=0.1, color='gray')
    ax_zscore.set_ylabel("Z-Score", fontsize=10)
    ax_zscore.set_xlabel("Time Period", fontsize=10)
    ax_zscore.grid(True, alpha=0.3)

    # Calculate statistics
    zscore_clean = zscore[~np.isnan(zscore)]
    overbought = (zscore_clean > 2).sum()
    oversold = (zscore_clean < -2).sum()

    stats = {
        'sym_1': sym_1,
        'sym_2': sym_2,
        'p_value': p_value,
        'adf_stat': adf_stat,
        'hedge_ratio': hedge_ratio,
        'zero_crossings': zero_crossings,
        'spread_mean': np.mean(spread),
        'spread_std': np.std(spread),
        'zscore_current': zscore_clean[-1] if len(zscore_clean) > 0 else np.nan,
        'overbought_signals': overbought,
        'oversold_signals': oversold,
        'price_1_current': prices_1[-1],
        'price_2_current': prices_2[-1],
    }

    return stats


def generate_summary_report(top_n=3):
    """
    Generate comprehensive PDF summary report

    Args:
        top_n: Number of top pairs to include (default: 3)
    """
    print("\n" + "="*60)
    print("STEP 5: Generating Summary Report")
    print("="*60)

    # Load data
    try:
        df_coint = pd.read_csv('2_cointegrated_pairs.csv')
        with open('1_price_list.json') as f:
            price_data = json.load(f)
    except FileNotFoundError as e:
        print(f"Error: Required file not found - {e}")
        return None

    if len(df_coint) == 0:
        print("No cointegrated pairs found. Cannot generate report.")
        return None

    first_symbol = next(iter(price_data.values()))

    # Get top N pairs
    top_pairs = df_coint.head(top_n)

    print(f"\nGenerating report for top {top_n} pairs...")
    print(f"Total cointegrated pairs available: {len(df_coint)}")

    # Create PDF
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f'4_summary_report_{timestamp}.pdf'

    with PdfPages(filename) as pdf:
        # Page 1: Title and Summary Statistics
        fig = plt.figure(figsize=(11, 8.5))
        fig.suptitle('OKX Statistical Arbitrage - Summary Report',
                     fontsize=16, fontweight='bold', y=0.98)

        # Add text summary
        ax = fig.add_subplot(111)
        ax.axis('off')

        summary_text = f"""
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

OVERALL STATISTICS
{'='*60}
Total Symbols Analyzed:        {len(price_data)}
Total Cointegrated Pairs:      {len(df_coint)}
Analysis Period:               {first_symbol['symbol_info'].get('total_klines', 200)} candles

TOP {top_n} PAIRS BY ZERO CROSSINGS
{'='*60}
"""

        for idx, row in top_pairs.reset_index(drop=True).iterrows():
            summary_text += f"""
Pair #{idx+1}: {row['sym_1']} / {row['sym_2']}
  - Zero Crossings:    {int(row['zero_crossing'])}
  - P-value:           {row['p_value']:.4f}
  - ADF Statistic:     {row['adf_stat']:.2f}
  - Hedge Ratio:       {row['hedge_ratio']:.2f}
"""

        summary_text += f"""

STATISTICAL CRITERIA
{'='*60}
P-value Threshold:       < 0.05 (95% confidence)
ADF Threshold:           < Critical Value
Zero Crossings:          Trading opportunities (mean reversions)
Z-Score Signals:         +/- 2 std (entry/exit points)

TRADING RECOMMENDATIONS
{'='*60}
1. Focus on pairs with highest zero crossings
2. Enter trades when |Z-score| > 2
3. Exit when Z-score crosses zero
4. Monitor spread volatility
5. Adjust position sizes based on hedge ratio
"""

        ax.text(0.05, 0.95, summary_text, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', fontfamily='monospace')

        pdf.savefig(fig, bbox_inches='tight')
        plt.close()

        # Pages 2+: Individual pair analysis
        all_stats = []

        for idx, row in top_pairs.reset_index(drop=True).iterrows():
            print(f"  Processing pair {idx+1}/{top_n}: {row['sym_1']} / {row['sym_2']}")

            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True)
            fig.suptitle(f"Pair #{idx+1}: {row['sym_1']} / {row['sym_2']}",
                        fontsize=14, fontweight='bold')

            stats = plot_pair_analysis(
                row['sym_1'],
                row['sym_2'],
                price_data,
                ax1, ax2, ax3
            )

            if stats:
                all_stats.append(stats)

                # Add statistics text box
                stats_text = f"""Statistics:
P-value: {stats['p_value']:.4f} | ADF: {stats['adf_stat']:.2f} | Hedge: {stats['hedge_ratio']:.2f}
Zero Crossings: {stats['zero_crossings']} | Spread std: {stats['spread_std']:.6f}
Current Z-Score: {stats['zscore_current']:.2f}
Trading Signals: {stats['overbought_signals']} overbought, {stats['oversold_signals']} oversold
Current Prices: {stats['sym_1']}: {stats['price_1_current']:.6f}, {stats['sym_2']}: {stats['price_2_current']:.6f}"""

                fig.text(0.5, 0.02, stats_text, ha='center', fontsize=9,
                        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))

            plt.tight_layout(rect=[0, 0.05, 1, 0.97])
            pdf.savefig(fig, bbox_inches='tight')
            plt.close()

        # Last Page: Comparison Table
        if all_stats:
            fig = plt.figure(figsize=(11, 8.5))
            ax = fig.add_subplot(111)
            ax.axis('off')
            fig.suptitle('Top Pairs Comparison', fontsize=14, fontweight='bold')

            # Create comparison table
            df_stats = pd.DataFrame(all_stats)

            # Format for display
            comparison_text = "\nCOMPARISON TABLE\n" + "="*80 + "\n\n"
            comparison_text += f"{'Rank':<6}{'Pair':<35}{'Z-Cross':<10}{'P-val':<10}{'Z-Score':<10}\n"
            comparison_text += "-"*80 + "\n"

            for idx, row in df_stats.iterrows():
                pair_name = f"{row['sym_1'][:10]} / {row['sym_2'][:10]}"
                comparison_text += f"{idx+1:<6}{pair_name:<35}{row['zero_crossings']:<10}{row['p_value']:<10.4f}{row['zscore_current']:<10.2f}\n"

            comparison_text += "\n\nTRADING SIGNALS SUMMARY\n" + "="*80 + "\n\n"
            comparison_text += f"Total Overbought Signals (Z>2):  {df_stats['overbought_signals'].sum()}\n"
            comparison_text += f"Total Oversold Signals (Z<-2):   {df_stats['oversold_signals'].sum()}\n"
            comparison_text += f"Average Zero Crossings:          {df_stats['zero_crossings'].mean():.1f}\n"
            comparison_text += f"Average Current Z-Score:         {df_stats['zscore_current'].mean():.2f}\n"

            ax.text(0.1, 0.9, comparison_text, transform=ax.transAxes,
                   fontsize=10, verticalalignment='top', fontfamily='monospace')

            pdf.savefig(fig, bbox_inches='tight')
            plt.close()

        # Set PDF metadata
        d = pdf.infodict()
        d['Title'] = 'OKX Statistical Arbitrage Summary Report'
        d['Author'] = 'OKX StatBot'
        d['Subject'] = 'Cointegrated Pairs Analysis'
        d['Keywords'] = 'Statistical Arbitrage, Pairs Trading, OKX'
        d['CreationDate'] = datetime.now()

    print(f"\nOK: Summary report generated: {filename}")
    print(f"   Pages: {top_n + 2} (1 summary + {top_n} pairs + 1 comparison)")
    print("="*60 + "\n")

    return filename


if __name__ == "__main__":
    generate_summary_report(top_n=3)
