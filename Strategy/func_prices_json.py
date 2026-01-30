"""
    Store price history for all available trading pairs
    Fetches candlestick data and saves to JSON file
"""

from func_price_klines import get_price_klines
from pathlib import Path
import json
import time


def store_price_history(symbols):
    """
    Fetch and store price history for all symbols

    Args:
        symbols: List of symbol dictionaries with 'symbol' key

    Returns:
        None (saves to output/1_price_list.json)
    """
    # Get prices and store in dictionary
    count = 0
    price_history_dict = {}

    print(f"\n{'='*60}")
    print(f"Fetching price history for {len(symbols)} symbols...")
    print(f"{'='*60}\n")

    for idx, symbol in enumerate(symbols, 1):
        klines = []  # Reset klines for each symbol
        symbol_name = symbol['symbol']

        try:
            print(f"[{idx}/{len(symbols)}] Fetching {symbol_name}...")
            price_history = get_price_klines(symbol_name)

            # Small delay to respect rate limits
            time.sleep(0.1)

        except Exception as e:
            print(f"  Error fetching {symbol_name}: {e}")
            continue

        # Extract kline data from OKX API response
        # OKX format: [timestamp, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
        # CRITICAL: OKX returns data in REVERSE chronological order (newest first)
        # We MUST reverse it to get oldest first for time series analysis
        if price_history['code'] == '0' and price_history['data']:
            for kline in reversed(price_history['data']):
                kline_data = {
                    'timestamp': kline[0],  # Unix timestamp in milliseconds
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5]) if len(kline) > 5 else 0,
                    'volume_ccy': float(kline[6]) if len(kline) > 6 else 0,
                }
                klines.append(kline_data)

            symbol['total_klines'] = len(klines)

            if len(klines) > 0:
                price_history_dict[symbol_name] = {
                    'symbol_info': symbol,
                    'klines': klines
                }
                count += 1
                print(f"  ✓ Stored {len(klines)} candles ({count} symbols total)")
            else:
                print(f"  ✗ No klines available")

        else:
            print(f"  ✗ Failed: {price_history.get('msg', 'Unknown error')}")
    # Output prices to JSON
    if len(price_history_dict) > 0:
        base_dir = Path(__file__).resolve().parent
        output_dir = base_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "1_price_list.json"
        print("\n" + "=" * 60)
        try:
            rel_path = output_path.relative_to(base_dir)
        except ValueError:
            rel_path = output_path
        print(f"Saving {len(price_history_dict)} symbols to {rel_path}...")
        with output_path.open("w") as fp:
            json.dump(price_history_dict, fp, indent=4)
        print("Prices saved successfully!")
        print("=" * 60 + "\n")
    else:
        print("\nNo price data to save")

    return
