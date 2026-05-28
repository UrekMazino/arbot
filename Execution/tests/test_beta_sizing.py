"""Tests for gross-normalized-beta sizing (exp_beta_aware_sizing_v1).

Tests the pure calculation helpers in core.chart_audit.hedge_ratio_sizing_audit.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.chart_audit.hedge_ratio_sizing_audit import (  # noqa: E402
    gross_normalized_beta_sizing,
    validate_hedge_ratio,
    HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA,
)


# ---------------------------------------------------------------------------
# validate_hedge_ratio — out-of-bounds rejection
# ---------------------------------------------------------------------------

def test_validate_hedge_ratio_rejects_below_min():
    cfg = {"min_hedge_ratio": 0.20, "max_hedge_ratio": 5.00}
    result = validate_hedge_ratio(0.10, cfg)
    assert not result.valid, "β=0.10 is below min=0.20 and should be rejected"
    assert result.beta == 0.10


def test_validate_hedge_ratio_rejects_above_max():
    cfg = {"min_hedge_ratio": 0.20, "max_hedge_ratio": 5.00}
    result = validate_hedge_ratio(6.00, cfg)
    assert not result.valid, "β=6.00 is above max=5.00 and should be rejected"


def test_validate_hedge_ratio_accepts_boundary_values():
    cfg = {"min_hedge_ratio": 0.20, "max_hedge_ratio": 5.00}
    assert validate_hedge_ratio(0.20, cfg).valid
    assert validate_hedge_ratio(5.00, cfg).valid


# ---------------------------------------------------------------------------
# gross_normalized_beta_sizing — β < 1 (most T5–T14 trades)
# ---------------------------------------------------------------------------

def test_gross_normalized_beta_lt1_conserves_gross():
    """β=0.471 (T13 BNB/COMP): leg1 + leg2 should equal gross exactly."""
    beta = 0.471
    gross = 200.0
    plan = gross_normalized_beta_sizing(gross, beta)
    assert plan.mode == HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA
    assert abs(plan.leg1_notional_usdt + plan.leg2_notional_usdt - gross) < 1e-8, (
        f"leg1={plan.leg1_notional_usdt:.6f} + leg2={plan.leg2_notional_usdt:.6f} != gross={gross}"
    )


def test_gross_normalized_beta_lt1_leg_sizes():
    """β=0.471: leg1 (inst_1) > leg2 (inst_2) when β < 1."""
    beta = 0.471
    gross = 200.0
    plan = gross_normalized_beta_sizing(gross, beta)
    expected_leg1 = gross / (1.0 + beta)   # ≈ 135.93
    expected_leg2 = gross * beta / (1.0 + beta)  # ≈ 64.07
    assert abs(plan.leg1_notional_usdt - expected_leg1) < 1e-6
    assert abs(plan.leg2_notional_usdt - expected_leg2) < 1e-6
    assert plan.leg1_notional_usdt > plan.leg2_notional_usdt, "When β<1, leg1 > leg2"


# ---------------------------------------------------------------------------
# gross_normalized_beta_sizing — β > 1
# ---------------------------------------------------------------------------

def test_gross_normalized_beta_gt1_conserves_gross():
    """β=1.433 (T12 SOL/BTC): leg1 + leg2 should equal gross exactly."""
    beta = 1.433
    gross = 200.0
    plan = gross_normalized_beta_sizing(gross, beta)
    assert abs(plan.leg1_notional_usdt + plan.leg2_notional_usdt - gross) < 1e-8


def test_gross_normalized_beta_gt1_leg_sizes():
    """β=1.433: leg2 (inst_2) > leg1 (inst_1) when β > 1."""
    beta = 1.433
    gross = 200.0
    plan = gross_normalized_beta_sizing(gross, beta)
    expected_leg1 = gross / (1.0 + beta)   # ≈ 82.23
    expected_leg2 = gross * beta / (1.0 + beta)  # ≈ 117.77
    assert abs(plan.leg1_notional_usdt - expected_leg1) < 1e-6
    assert abs(plan.leg2_notional_usdt - expected_leg2) < 1e-6
    assert plan.leg2_notional_usdt > plan.leg1_notional_usdt, "When β>1, leg2 > leg1"


def test_gross_normalized_beta_unity_is_equal_notional():
    """β=1.0 should give exactly equal 50/50 split (special case)."""
    plan = gross_normalized_beta_sizing(200.0, 1.0)
    assert abs(plan.leg1_notional_usdt - 100.0) < 1e-8
    assert abs(plan.leg2_notional_usdt - 100.0) < 1e-8
