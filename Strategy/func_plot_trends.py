from func_cointegration import extract_close_prices
from func_cointegration import calculate_cointegration
from func_cointegration import calculate_spread
from func_cointegration import calculate_zscore
from func_strategy_log import get_strategy_logger
from pathlib import Path

# matplotlib is optional - plotting won't work without it
try:
    import matplotlib.pyplot as plt
    import pandas as pd
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None
    pd = None
    np = None


# Plot prices and trends
def plot_trends(sym_1, sym_2, price_data):
    """
    Plot price trends, spread, and z-score for a cointegrated pair
    """
    if not MATPLOTLIB_AVAILABLE:
        return None
