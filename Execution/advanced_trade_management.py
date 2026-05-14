"""Advanced trade management with dynamic exit logic."""

import logging
import time
import numpy as np
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ExitReason(Enum):
    """Exit reason enumeration"""
    TAKE_PROFIT = "take_profit"
    PARTIAL_PROFIT = "partial_profit"
    TRAILING_STOP = "trailing_stop"
    MEAN_REVERSION_ESCAPE = "mean_reversion_escape"
    PNL_PROFIT_LOCK = "pnl_profit_lock"
    STALL = "stall"
    REGIME_BREAK = "regime_break"
    MAX_HOLD_TIME = "max_hold_time"
    DIVERGING = "diverging"
    MANUAL = "manual"


@dataclass
class TradeState:
    """Track state of open trade"""
    entry_z: float
    entry_time: float
    entry_direction: str  # 'long_spread' or 'short_spread'
    
    # Position tracking
    initial_position_size: float
    current_position_size: float
    
    # Performance tracking
    best_z: float  # Best (closest to mean) Z-score seen
    worst_z: float  # Worst Z-score seen
    
    # History
    z_history: List[Tuple[float, float]]  # [(timestamp, z_score), ...]
    
    # Partial exit tracking
    partial_exits: List[Dict]  # [{time, z_score, size, pnl}, ...]
    
    # Trailing stop
    trailing_stop_active: bool = False
    trailing_stop_level: float = None
    max_favorable_pnl_usdt: Optional[float] = None
    pnl_profit_lock_active: bool = False
    pnl_profit_lock_floor: Optional[float] = None


class AdvancedTradeManager:
    """Comprehensive trade management with dynamic exits"""
    
    def __init__(self, config: Dict = None):
        """Initialize trade manager"""
        
        # Default configuration
        self.config = {
            # Dynamic stall detection
            'base_window_seconds': 3600,  # 60 min baseline
            'base_epsilon': 0.3,  # 0.3 sigma baseline improvement
            
            # Entry Z thresholds for adaptive window
            'mild_entry_threshold': 2.5,
            'normal_entry_threshold': 3.5,
            'extreme_entry_threshold': 4.5,
            
            # Window scaling
            'mild_window': 1800,    # 30 min for mild entries
            'normal_window': 3600,  # 60 min for normal entries
            'extreme_window': 5400, # 90 min for extreme entries
            'very_extreme_window': 7200,  # 120 min for very extreme
            
            # Volatility thresholds
            'high_volatility_threshold': 1.0,
            'medium_volatility_threshold': 0.5,
            
            # Epsilon scaling
            'high_vol_epsilon': 0.5,
            'medium_vol_epsilon': 0.3,
            'low_vol_epsilon': 0.2,
            
            # Partial exit thresholds
            'partial_exit_enabled': True,
            'partial_exit_z_threshold': 1.0,  # Take 50% at Z < 1.0
            'partial_exit_percentage': 0.5,   # Exit 50% of position
            
            # Trailing stop
            'trailing_stop_enabled': True,
            'trailing_stop_activation': 0.8,  # Activate at Z < 0.8
            'trailing_stop_distance': 0.5,    # Fallback distance
            'trailing_stop_min_hold_seconds': 120,
            'trailing_stop_tight_progress': 1.5,
            'trailing_stop_mid_progress': 1.0,
            'trailing_stop_tight_distance': 0.3,
            'trailing_stop_mid_distance': 0.4,
            'trailing_stop_loose_distance': 0.5,
            
            # Maximum hold time
            'max_hold_hours': 6,  # 6 hours maximum
            'max_hold_warning_hours': 4,  # Warning at 4 hours
            
            # Mean-reversion target (legacy key name kept for compatibility)
            'take_profit_z': 0.5,  # Exit at |Z| < 0.5
            'net_profit_guard_enabled': True,
            'net_profit_guard_require_pnl': True,
            'full_tp_guard_multiplier': 1.0,
            'partial_tp_guard_multiplier': 1.0,
            'trailing_stop_guard_multiplier': 1.0,
            'mean_reversion_escape_enabled': False,
            'mean_reversion_escape_z': 0.25,
            'mean_reversion_escape_min_pnl_usdt': 0.0,
            'mean_reversion_escape_requires_risk_rising': True,
            'pnl_profit_lock_enabled': False,
            'pnl_profit_lock_activation_buffer_usdt': 0.05,
            'pnl_profit_lock_giveback_pct': 0.50,
            'pnl_profit_lock_min_lock_usdt': 0.0,
            
            # Stall detection
            'stall_z_threshold': 1.5,  # Exit if Z > 1.5 and stalled
            'warning_z_threshold': 1.0,  # Warning if Z > 1.0 and stalled
        }
        
        # Override with provided config
        if config:
            self.config.update(config)
        
        # Trade state
        self.trade_state: Optional[TradeState] = None
    
    
    def open_position(self, entry_z: float, position_size: float, entry_time: float = None):
        """Initialize trade state when position opens"""
        
        direction = 'long_spread' if entry_z < 0 else 'short_spread'
        entry_ts = entry_time if entry_time is not None else time.time()
        
        self.trade_state = TradeState(
            entry_z=entry_z,
            entry_time=entry_ts,
            entry_direction=direction,
            initial_position_size=position_size,
            current_position_size=position_size,
            best_z=entry_z,
            worst_z=entry_z,
            z_history=[(entry_ts, entry_z)],
            partial_exits=[]
        )
        
        logger.info(
            "Position opened: entry_z=%.2f sigma direction=%s size=%.2f expected_hold=%.0f min max_hold=%.0f h",
            entry_z,
            direction,
            position_size,
            self._get_expected_hold_time(entry_z) / 60,
            self.config["max_hold_hours"],
        )
    
    
    def update(
        self,
        current_z: float,
        floating_pnl_usdt: Optional[float] = None,
        min_profit_usdt: float = 0.0,
    ) -> Dict:
        """Update trade state and check all exit conditions"""
        
        if self.trade_state is None:
            return {'action': 'NO_POSITION', 'reason': 'No open position'}
        
        # Update history
        current_time = time.time()
        self.trade_state.z_history.append((current_time, current_z))
        
        # Update best/worst Z
        abs_current = abs(current_z)
        abs_best = abs(self.trade_state.best_z)
        abs_worst = abs(self.trade_state.worst_z)
        
        if abs_current < abs_best:
            self.trade_state.best_z = current_z
        if abs_current > abs_worst:
            self.trade_state.worst_z = current_z

        pnl_value = self._finite_float(floating_pnl_usdt)
        if pnl_value is not None:
            if (
                self.trade_state.max_favorable_pnl_usdt is None
                or pnl_value > self.trade_state.max_favorable_pnl_usdt
            ):
                self.trade_state.max_favorable_pnl_usdt = pnl_value
        
        # Trim history (keep last 2 hours)
        cutoff_time = current_time - 7200
        self.trade_state.z_history = [
            (t, z) for (t, z) in self.trade_state.z_history
            if t >= cutoff_time
        ]
        
        # CHECK EXIT CONDITIONS (in priority order)
        
        # 1. MAXIMUM HOLD TIME (highest priority)
        max_hold_result = self._check_max_hold_time()
        if max_hold_result['action'] == 'EXIT':
            return max_hold_result
        elif max_hold_result['action'] == 'WARNING':
            logger.warning("Max hold warning: %s", max_hold_result["reason"])
        
        # 2. REGIME BREAK (second priority)
        regime_result = self._check_regime_break(current_z)
        if regime_result['action'] == 'EXIT':
            return regime_result
        
        # 3. MEAN-REVERSION TARGET HIT (full exit)
        if abs(current_z) <= self.config['take_profit_z']:
            take_profit_min_profit, take_profit_multiplier, take_profit_base = self._guard_threshold(
                ExitReason.TAKE_PROFIT,
                min_profit_usdt,
            )
            if not self._profit_exit_allowed(floating_pnl_usdt, take_profit_min_profit):
                escape_result = self._check_mean_reversion_escape(current_z, floating_pnl_usdt)
                if escape_result['action'] == 'EXIT':
                    return escape_result
                return self._net_profit_guard_hold(
                    ExitReason.TAKE_PROFIT,
                    floating_pnl_usdt,
                    take_profit_base,
                    take_profit_min_profit,
                    take_profit_multiplier,
                    current_z=current_z,
                )
            return self._create_exit_result(
                action='EXIT',
                reason=ExitReason.TAKE_PROFIT,
                message=f"Mean-reversion target hit: Z={current_z:+.2f} sigma (target: {self.config['take_profit_z']:.2f} sigma)",
                percentage=1.0,
                guard_diagnostics={
                    'base_min_profit_usdt': take_profit_base,
                    'effective_min_profit_usdt': take_profit_min_profit,
                    'guard_multiplier': take_profit_multiplier,
                    'current_z': current_z,
                },
            )

        # 4. PNL PROFIT LOCK (optional giveback protection)
        pnl_lock_result = self._check_pnl_profit_lock(current_z, floating_pnl_usdt, min_profit_usdt)
        if pnl_lock_result['action'] == 'EXIT':
            return pnl_lock_result

        # 5. TRAILING STOP
        trailing_result = self._check_trailing_stop(current_z)
        if trailing_result['action'] == 'EXIT':
            trailing_min_profit, trailing_multiplier, trailing_base = self._guard_threshold(
                ExitReason.TRAILING_STOP,
                min_profit_usdt,
            )
            if not self._profit_exit_allowed(floating_pnl_usdt, trailing_min_profit):
                return self._net_profit_guard_hold(
                    ExitReason.TRAILING_STOP,
                    floating_pnl_usdt,
                    trailing_base,
                    trailing_min_profit,
                    trailing_multiplier,
                    current_z=current_z,
                )
            trailing_result.update(
                {
                    'base_min_profit_usdt': trailing_base,
                    'effective_min_profit_usdt': trailing_min_profit,
                    'guard_multiplier': trailing_multiplier,
                    'current_z': current_z,
                    'exit_type': ExitReason.TRAILING_STOP.value,
                }
            )
            return trailing_result

        # 6. PARTIAL EXIT
        partial_result = self._check_partial_exit(current_z)
        if partial_result['action'] == 'PARTIAL_EXIT':
            partial_min_profit, partial_multiplier, partial_base = self._guard_threshold(
                ExitReason.PARTIAL_PROFIT,
                min_profit_usdt,
            )
            if not self._profit_exit_allowed(floating_pnl_usdt, partial_min_profit):
                return self._net_profit_guard_hold(
                    ExitReason.PARTIAL_PROFIT,
                    floating_pnl_usdt,
                    partial_base,
                    partial_min_profit,
                    partial_multiplier,
                    current_z=current_z,
                )
            partial_result.update(
                {
                    'base_min_profit_usdt': partial_base,
                    'effective_min_profit_usdt': partial_min_profit,
                    'guard_multiplier': partial_multiplier,
                    'current_z': current_z,
                    'exit_type': ExitReason.PARTIAL_PROFIT.value,
                }
            )
            return partial_result
        
        # 7. STALL DETECTION (dynamic)
        stall_result = self._check_stall_dynamic(current_z)
        if stall_result['action'] == 'EXIT':
            return stall_result
        elif stall_result['action'] == 'WARNING':
            logger.warning("Stall warning: %s", stall_result["reason"])
        
        # 8. NO EXIT - HOLD POSITION
        time_in_trade = current_time - self.trade_state.entry_time
        return {
            'action': 'HOLD',
            'reason': f"Monitoring: Z={current_z:+.2f} sigma (best: {self.trade_state.best_z:+.2f} sigma, time: {time_in_trade/60:.0f}m)",
            'details': {
                'current_z': current_z,
                'best_z': self.trade_state.best_z,
                'worst_z': self.trade_state.worst_z,
                'time_in_trade': time_in_trade,
                'trailing_stop_active': self.trade_state.trailing_stop_active,
                'trailing_stop_level': self.trade_state.trailing_stop_level
            }
        }
    

    def _guard_threshold(self, reason: ExitReason, min_profit_usdt: float) -> Tuple[float, float, float]:
        try:
            base_required = max(float(min_profit_usdt or 0.0), 0.0)
        except (TypeError, ValueError):
            base_required = 0.0

        key_by_reason = {
            ExitReason.TAKE_PROFIT: 'full_tp_guard_multiplier',
            ExitReason.PARTIAL_PROFIT: 'partial_tp_guard_multiplier',
            ExitReason.TRAILING_STOP: 'trailing_stop_guard_multiplier',
        }
        key = key_by_reason.get(reason)
        try:
            multiplier = float(self.config.get(key, 1.0)) if key else 1.0
        except (TypeError, ValueError):
            multiplier = 1.0
        if multiplier < 0:
            multiplier = 1.0

        return base_required * multiplier, multiplier, base_required


    def _profit_exit_allowed(self, floating_pnl_usdt: Optional[float], min_profit_usdt: float) -> bool:
        if not self.config.get('net_profit_guard_enabled', True):
            return True
        try:
            required = max(float(min_profit_usdt or 0.0), 0.0)
        except (TypeError, ValueError):
            required = 0.0
        if floating_pnl_usdt is None:
            return not bool(self.config.get('net_profit_guard_require_pnl', True))
        try:
            pnl = float(floating_pnl_usdt)
        except (TypeError, ValueError):
            return not bool(self.config.get('net_profit_guard_require_pnl', True))
        return pnl >= required


    def _finite_float(self, value, default=None):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not np.isfinite(parsed):
            return default
        return parsed


    def _config_float(self, key: str, default: float, minimum: Optional[float] = None, maximum: Optional[float] = None):
        value = self._finite_float(self.config.get(key), default)
        if value is None:
            value = default
        if minimum is not None and value < minimum:
            value = minimum
        if maximum is not None and value > maximum:
            value = maximum
        return value


    def _check_pnl_profit_lock(
        self,
        current_z: float,
        floating_pnl_usdt: Optional[float],
        min_profit_usdt: float,
    ) -> Dict:
        if not self.config.get('pnl_profit_lock_enabled', False):
            if self.trade_state:
                self.trade_state.pnl_profit_lock_active = False
                self.trade_state.pnl_profit_lock_floor = None
            return {'action': 'HOLD', 'reason': 'PnL profit lock disabled'}
        if not self.trade_state:
            return {'action': 'HOLD', 'reason': 'No trade state for PnL profit lock'}

        pnl = self._finite_float(floating_pnl_usdt)
        max_favorable = self._finite_float(self.trade_state.max_favorable_pnl_usdt)
        if pnl is None or max_favorable is None:
            self.trade_state.pnl_profit_lock_active = False
            self.trade_state.pnl_profit_lock_floor = None
            return {'action': 'HOLD', 'reason': 'PnL profit lock PnL unavailable'}

        effective_min_profit, guard_multiplier, base_min_profit = self._guard_threshold(
            ExitReason.TAKE_PROFIT,
            min_profit_usdt,
        )
        activation_buffer = self._config_float(
            'pnl_profit_lock_activation_buffer_usdt',
            0.05,
            minimum=0.0,
        )
        giveback_pct = self._config_float(
            'pnl_profit_lock_giveback_pct',
            0.50,
            minimum=0.0,
            maximum=1.0,
        )
        min_lock_usdt = self._config_float(
            'pnl_profit_lock_min_lock_usdt',
            0.0,
        )
        activation_floor = effective_min_profit + activation_buffer
        if max_favorable < activation_floor:
            self.trade_state.pnl_profit_lock_active = False
            self.trade_state.pnl_profit_lock_floor = None
            return {
                'action': 'HOLD',
                'reason': 'PnL profit lock not active',
                'pnl_profit_lock_active': False,
                'max_favorable_pnl_usdt': max_favorable,
                'effective_min_profit_usdt': effective_min_profit,
                'pnl_profit_lock_activation_floor': activation_floor,
            }

        giveback_floor = max(
            effective_min_profit,
            min_lock_usdt,
            max_favorable * (1.0 - giveback_pct),
        )
        self.trade_state.pnl_profit_lock_active = True
        self.trade_state.pnl_profit_lock_floor = giveback_floor
        if pnl <= giveback_floor:
            return self._create_exit_result(
                action='EXIT',
                reason=ExitReason.PNL_PROFIT_LOCK,
                message=(
                    f"PnL profit lock: pnl={pnl:.4f} <= floor={giveback_floor:.4f} USDT "
                    f"(MFE={max_favorable:.4f}, giveback={giveback_pct:.2f})"
                ),
                percentage=1.0,
                guard_diagnostics={
                    'base_min_profit_usdt': base_min_profit,
                    'effective_min_profit_usdt': effective_min_profit,
                    'guard_multiplier': guard_multiplier,
                    'current_z': current_z,
                    'max_favorable_pnl_usdt': max_favorable,
                    'pnl_profit_lock_floor': giveback_floor,
                    'pnl_profit_lock_giveback_pct': giveback_pct,
                    'pnl_profit_lock_active': True,
                },
            )
        return {
            'action': 'HOLD',
            'reason': 'PnL profit lock active but not hit',
            'pnl_profit_lock_active': True,
            'max_favorable_pnl_usdt': max_favorable,
            'pnl_profit_lock_floor': giveback_floor,
            'pnl_profit_lock_giveback_pct': giveback_pct,
            'effective_min_profit_usdt': effective_min_profit,
            'guard_multiplier': guard_multiplier,
        }


    def _net_profit_guard_hold(
        self,
        reason: ExitReason,
        floating_pnl_usdt: Optional[float],
        base_min_profit_usdt: float,
        effective_min_profit_usdt: Optional[float] = None,
        guard_multiplier: float = 1.0,
        current_z: Optional[float] = None,
    ) -> Dict:
        try:
            base_required = max(float(base_min_profit_usdt or 0.0), 0.0)
        except (TypeError, ValueError):
            base_required = 0.0
        if effective_min_profit_usdt is None:
            effective_required = base_required
        else:
            try:
                effective_required = max(float(effective_min_profit_usdt or 0.0), 0.0)
            except (TypeError, ValueError):
                effective_required = base_required
        if floating_pnl_usdt is None:
            pnl_text = "unknown"
        else:
            try:
                pnl_text = f"{float(floating_pnl_usdt):.4f}"
            except (TypeError, ValueError):
                pnl_text = "unknown"
        return {
            'action': 'HOLD',
            'reason': (
                f"Net profit guard blocked {reason.value}: "
                f"floating_pnl={pnl_text} < required={effective_required:.4f} USDT "
                f"(base={base_required:.4f}, multiplier={guard_multiplier:.3f})"
            ),
            'blocked_exit_reason': reason.value,
            'floating_pnl_usdt': floating_pnl_usdt,
            'min_profit_usdt': effective_required,
            'base_min_profit_usdt': base_required,
            'effective_min_profit_usdt': effective_required,
            'guard_multiplier': guard_multiplier,
            **({'current_z': current_z} if current_z is not None else {}),
            **({'take_profit_z': self.config.get('take_profit_z')} if reason == ExitReason.TAKE_PROFIT else {}),
        }


    def _check_mean_reversion_escape(
        self,
        current_z: float,
        floating_pnl_usdt: Optional[float],
    ) -> Dict:
        if not self.config.get('mean_reversion_escape_enabled', False):
            return {'action': 'HOLD', 'reason': 'Mean-reversion escape disabled'}

        try:
            escape_z = max(float(self.config.get('mean_reversion_escape_z', 0.25) or 0.0), 0.0)
        except (TypeError, ValueError):
            escape_z = 0.25
        if abs(current_z) > escape_z:
            return {'action': 'HOLD', 'reason': 'Outside mean-reversion escape zone'}

        try:
            min_pnl = float(self.config.get('mean_reversion_escape_min_pnl_usdt', 0.0) or 0.0)
        except (TypeError, ValueError):
            min_pnl = 0.0
        try:
            pnl = float(floating_pnl_usdt)
        except (TypeError, ValueError):
            return {'action': 'HOLD', 'reason': 'Mean-reversion escape PnL unavailable'}
        if pnl < min_pnl:
            return {'action': 'HOLD', 'reason': 'Mean-reversion escape PnL below floor'}

        if self.config.get('mean_reversion_escape_requires_risk_rising', True):
            if not self._mean_reversion_escape_risk_rising(current_z):
                return {'action': 'HOLD', 'reason': 'Mean-reversion escape risk condition not met'}

        return self._create_exit_result(
            action='EXIT',
            reason=ExitReason.MEAN_REVERSION_ESCAPE,
            message=(
                f"Mean-reversion escape: Z={current_z:+.2f} sigma within "
                f"{escape_z:.2f} sigma and pnl={pnl:.4f} USDT"
            ),
            percentage=1.0,
        )


    def _mean_reversion_escape_risk_rising(self, current_z: float) -> bool:
        if not self.trade_state:
            return False
        if self.trade_state.trailing_stop_active:
            return True
        return abs(current_z) > abs(self.trade_state.best_z)

    
    def _check_max_hold_time(self) -> Dict:
        """Check if maximum hold time exceeded"""
        
        time_in_trade = time.time() - self.trade_state.entry_time
        hours_in_trade = time_in_trade / 3600
        max_hours = self.config['max_hold_hours']
        warning_hours = self.config['max_hold_warning_hours']
        
        if hours_in_trade >= max_hours:
            return self._create_exit_result(
                action='EXIT',
                reason=ExitReason.MAX_HOLD_TIME,
                message=f"Max hold time exceeded: {hours_in_trade:.1f}h / {max_hours:.1f}h",
                percentage=1.0
            )
        
        if hours_in_trade >= warning_hours:
            return {
                'action': 'WARNING',
                'reason': f"Approaching max hold time: {hours_in_trade:.1f}h / {max_hours:.1f}h"
            }
        
        return {'action': 'HOLD', 'reason': 'Within time limit'}


    def _z_at_or_before(self, target_ts: float) -> Optional[float]:
        """Return the last Z-score at or before target timestamp."""
        if not self.trade_state or not self.trade_state.z_history:
            return None

        z_val = None
        for ts, z_score in self.trade_state.z_history:
            if ts <= target_ts:
                z_val = z_score
            else:
                break
        return z_val


    def _check_sign_flip_sustained(self, current_z: float) -> bool:
        """Detect a sustained sign flip:"""
        if not self.trade_state:
            return False

        entry_z = self.trade_state.entry_z
        time_in_trade = time.time() - self.trade_state.entry_time
        if time_in_trade < 300:
            return False

        window_start = time.time() - 300
        recent = [(t, z) for (t, z) in self.trade_state.z_history if t >= window_start]
        if len(recent) < 5:
            return False

        opposite_count = 0
        for _, z in recent:
            if entry_z < 0 and z > 1.5:
                opposite_count += 1
            elif entry_z > 0 and z < -1.5:
                opposite_count += 1

        if opposite_count / len(recent) < 0.8:
            return False

        z_5min_ago = self._z_at_or_before(window_start)
        if z_5min_ago is None:
            z_5min_ago = entry_z

        return abs(current_z) > abs(z_5min_ago)
    
    
    def _check_regime_break(self, current_z: float) -> Dict:
        """Check for regime break (sign flip or extreme divergence)"""
        
        entry_z = self.trade_state.entry_z
        abs_entry = abs(entry_z)
        abs_current = abs(current_z)
        

        # Check for sustained sign flip (avoid exiting on brief oscillations)
        if self._check_sign_flip_sustained(current_z):
            return self._create_exit_result(
                action='EXIT',
                reason=ExitReason.REGIME_BREAK,
                message=f"Regime flip (sustained): entry {entry_z:+.2f}, now {current_z:+.2f}",
                percentage=1.0
            )

        # Check for extreme divergence (getting much worse)
        if abs_current > abs_entry + 1.5:
            return self._create_exit_result(
                action='EXIT',
                reason=ExitReason.DIVERGING,
                message=f"Diverging: {abs_entry:.2f} sigma -> {abs_current:.2f} sigma (+{abs_current - abs_entry:.2f} sigma)",
                percentage=1.0
            )
        
        return {'action': 'HOLD', 'reason': 'No regime break'}
    
    
    def _check_partial_exit(self, current_z: float) -> Dict:
        """Check if partial exit threshold reached"""
        
        if not self.config['partial_exit_enabled']:
            return {'action': 'HOLD', 'reason': 'Partial exits disabled'}
        
        # Check if already did partial exit
        if len(self.trade_state.partial_exits) > 0:
            return {'action': 'HOLD', 'reason': 'Already did partial exit'}
        
        # Check if Z reached partial exit threshold
        abs_current = abs(current_z)
        threshold = self.config['partial_exit_z_threshold']
        
        if abs_current < threshold:
            percentage = self.config['partial_exit_percentage']
            
            return self._create_exit_result(
                action='PARTIAL_EXIT',
                reason=ExitReason.PARTIAL_PROFIT,
                message=f"Partial exit: Z={current_z:+.2f} sigma < {threshold:.2f} sigma (taking {percentage*100:.0f}% profit)",
                percentage=percentage
            )
        
        return {'action': 'HOLD', 'reason': f'Z={abs_current:.2f} sigma > {threshold:.2f} sigma'}
    
    
    def _check_trailing_stop(self, current_z: float) -> Dict:
        """Check trailing stop (lock in profits as Z approaches mean)"""
        
        if not self.config['trailing_stop_enabled']:
            return {'action': 'HOLD', 'reason': 'Trailing stop disabled'}

        time_in_trade = time.time() - self.trade_state.entry_time
        min_hold_seconds = self.config.get('trailing_stop_min_hold_seconds', 0)
        if min_hold_seconds and time_in_trade < min_hold_seconds:
            return {
                'action': 'HOLD',
                'reason': 'Trailing stop grace period'
            }

        abs_current = abs(current_z)
        abs_best = abs(self.trade_state.best_z)
        abs_entry = abs(self.trade_state.entry_z)
        activation_threshold = self.config['trailing_stop_activation']
        progress = max(0.0, abs_entry - abs_best)
        tight_progress = self.config.get('trailing_stop_tight_progress', 1.5)
        mid_progress = self.config.get('trailing_stop_mid_progress', 1.0)
        tight_distance = self.config.get('trailing_stop_tight_distance', 0.3)
        mid_distance = self.config.get('trailing_stop_mid_distance', 0.4)
        loose_distance = self.config.get('trailing_stop_loose_distance', self.config['trailing_stop_distance'])
        if progress >= tight_progress:
            trail_distance = tight_distance
        elif progress >= mid_progress:
            trail_distance = mid_distance
        else:
            trail_distance = loose_distance
        
        # Activate trailing stop when Z gets close to mean
        if not self.trade_state.trailing_stop_active:
            if abs_current < activation_threshold:
                self.trade_state.trailing_stop_active = True
                self.trade_state.trailing_stop_level = abs_current + trail_distance
                
                logger.info(
                    "Trailing stop activated: current_z=%.2f sigma stop=%.2f sigma distance=%.2f sigma",
                    abs_current,
                    self.trade_state.trailing_stop_level,
                    trail_distance,
                )
        
        # Update trailing stop level (follow best Z)
        if self.trade_state.trailing_stop_active:
            new_stop_level = abs_best + trail_distance
            
            # Only move stop down (tighter), never up
            if new_stop_level < self.trade_state.trailing_stop_level:
                logger.info(
                    "Trailing stop tightened: %.2f -> %.2f sigma",
                    self.trade_state.trailing_stop_level,
                    new_stop_level,
                )
                self.trade_state.trailing_stop_level = new_stop_level
            
            # Check if stop hit
            if abs_current > self.trade_state.trailing_stop_level:
                return self._create_exit_result(
                    action='EXIT',
                    reason=ExitReason.TRAILING_STOP,
                    message=f"Trailing stop hit: Z={current_z:+.2f} sigma > {self.trade_state.trailing_stop_level:.2f} sigma (best was {self.trade_state.best_z:+.2f} sigma)",
                    percentage=1.0
                )
        
        return {'action': 'HOLD', 'reason': 'Trailing stop not hit'}
    
    
    def _check_stall_dynamic(self, current_z: float) -> Dict:
        """Dynamic stall detection with adaptive parameters"""
        
        time_in_trade = time.time() - self.trade_state.entry_time
        entry_z = self.trade_state.entry_z
        abs_entry = abs(entry_z)
        abs_current = abs(current_z)
        
        # Get adaptive parameters
        window = self._get_adaptive_window(entry_z)
        volatility = self._calculate_recent_volatility()
        epsilon = self._get_adaptive_epsilon(volatility, time_in_trade)
        
        # Check if window time has passed
        if time_in_trade < window:
            minutes_elapsed = time_in_trade / 60
            minutes_needed = window / 60
            return {
                'action': 'HOLD',
                'reason': f'Stall check in {minutes_needed - minutes_elapsed:.0f} min (volatility: {volatility:.2f} sigma)'
            }
        
        # Get Z from window ago
        window_start_time = time.time() - window
        z_at_window_start = None
        
        for (timestamp, z_score) in self.trade_state.z_history:
            if timestamp >= window_start_time:
                z_at_window_start = z_score
                break
        
        if z_at_window_start is None:
            z_at_window_start = entry_z
        
        # Calculate improvement
        abs_window_start = abs(z_at_window_start)
        improvement = abs_window_start - abs_current
        
        # DECISION LOGIC
        
        # Good progress
        if improvement >= epsilon:
            return {
                'action': 'HOLD',
                'reason': f'Improving: {abs_window_start:.2f} sigma -> {abs_current:.2f} sigma ({improvement:+.2f} sigma / {epsilon:.2f} sigma needed)'
            }
        
        # Diverging significantly
        if improvement < -epsilon:
            return self._create_exit_result(
                action='EXIT',
                reason=ExitReason.DIVERGING,
                message=f"Diverging: {abs_window_start:.2f} sigma -> {abs_current:.2f} sigma ({improvement:+.2f} sigma in {window/60:.0f} min)",
                percentage=1.0
            )
        
        # Stalled at extreme Z
        if abs_current > self.config['stall_z_threshold']:
            return self._create_exit_result(
                action='EXIT',
                reason=ExitReason.STALL,
                message=f"Stalled: {abs_window_start:.2f} sigma -> {abs_current:.2f} sigma ({improvement:+.2f} sigma in {window/60:.0f} min, need {epsilon:.2f} sigma)",
                percentage=1.0
            )
        
        # Warning: slow progress
        if abs_current > self.config['warning_z_threshold']:
            return {
                'action': 'WARNING',
                'reason': f'Slow: {abs_window_start:.2f} sigma -> {abs_current:.2f} sigma ({improvement:+.2f} sigma, need {epsilon:.2f} sigma)'
            }
        
        # Near mean, be patient
        return {
            'action': 'HOLD',
            'reason': f'Near mean: Z={abs_current:.2f} sigma (acceptable progress)'
        }
    
    
    def _get_adaptive_window(self, entry_z: float) -> int:
        """Calculate adaptive window based on entry extremity"""
        
        abs_entry = abs(entry_z)
        
        if abs_entry < self.config['mild_entry_threshold']:
            return self.config['mild_window']
        elif abs_entry < self.config['normal_entry_threshold']:
            return self.config['normal_window']
        elif abs_entry < self.config['extreme_entry_threshold']:
            return self.config['extreme_window']
        else:
            return self.config['very_extreme_window']
    
    
    def _get_expected_hold_time(self, entry_z: float) -> int:
        """Get expected hold time for logging"""
        return self._get_adaptive_window(entry_z)
    
    
    def _calculate_recent_volatility(self) -> float:
        """Calculate recent Z-score volatility"""
        
        if len(self.trade_state.z_history) < 10:
            return 0.5  # Default medium volatility
        
        recent_z = [z for (t, z) in self.trade_state.z_history[-20:]]
        volatility = np.std(recent_z)
        
        return volatility
    
    
    def _get_adaptive_epsilon(self, volatility: float, time_in_trade: float) -> float:
        """Calculate adaptive epsilon based on volatility and time"""
        
        # Base epsilon on volatility
        if volatility > self.config['high_volatility_threshold']:
            epsilon = self.config['high_vol_epsilon']
        elif volatility > self.config['medium_volatility_threshold']:
            epsilon = self.config['medium_vol_epsilon']
        else:
            epsilon = self.config['low_vol_epsilon']
        
        # Scale by time in trade
        hours = time_in_trade / 3600
        
        if hours < 0.5:
            # Very early - don't check
            epsilon = float('inf')
        elif hours < 1.0:
            # Early - be lenient
            epsilon *= 0.7
        elif hours > 2.0:
            # Late - be stricter
            epsilon *= 1.3
        
        return epsilon
    
    
    def _create_exit_result(
        self,
        action: str,
        reason: ExitReason,
        message: str,
        percentage: float,
        guard_diagnostics: Optional[Dict] = None,
    ) -> Dict:
        """Create standardized exit result"""
        
        time_in_trade = time.time() - self.trade_state.entry_time
        
        result = {
            'action': action,
            'reason': reason.value,
            'message': message,
            'percentage': percentage,
            'details': {
                'entry_z': self.trade_state.entry_z,
                'best_z': self.trade_state.best_z,
                'worst_z': self.trade_state.worst_z,
                'time_in_trade': time_in_trade,
                'partial_exits': len(self.trade_state.partial_exits),
                'position_size_remaining': self.trade_state.current_position_size,
                'initial_position_size': self.trade_state.initial_position_size
            }
        }
        if guard_diagnostics:
            result.update(
                {
                    'base_min_profit_usdt': guard_diagnostics.get('base_min_profit_usdt'),
                    'effective_min_profit_usdt': guard_diagnostics.get('effective_min_profit_usdt'),
                    'guard_multiplier': guard_diagnostics.get('guard_multiplier'),
                    'exit_type': reason.value,
                }
            )
            for key in (
                'current_z',
                'max_favorable_pnl_usdt',
                'pnl_profit_lock_floor',
                'pnl_profit_lock_giveback_pct',
                'pnl_profit_lock_active',
            ):
                if guard_diagnostics.get(key) is not None:
                    result[key] = guard_diagnostics.get(key)
            if reason == ExitReason.TAKE_PROFIT:
                result['take_profit_z'] = self.config.get('take_profit_z')
        return result
    
    
    def execute_partial_exit(self, pnl: float):
        """Record partial exit"""
        
        current_time = time.time()
        current_z = self.trade_state.z_history[-1][1]
        percentage = self.config['partial_exit_percentage']
        
        exit_record = {
            'time': current_time,
            'z_score': current_z,
            'percentage': percentage,
            'pnl': pnl
        }
        
        self.trade_state.partial_exits.append(exit_record)
        self.trade_state.current_position_size *= (1 - percentage)
        
        logger.info(
            "Partial exit: percent=%.0f%% z=%.2f sigma pnl=%.2f remaining=%.2f",
            percentage * 100,
            current_z,
            pnl,
            self.trade_state.current_position_size,
        )
    
    
    def close_position(self):
        """Close position and reset state"""
        
        if self.trade_state is None:
            return
        
        time_in_trade = time.time() - self.trade_state.entry_time
        
        logger.info(
            "Position closed: time=%.1f min entry_z=%.2f sigma best=%.2f sigma worst=%.2f sigma partial_exits=%d",
            time_in_trade / 60,
            self.trade_state.entry_z,
            self.trade_state.best_z,
            self.trade_state.worst_z,
            len(self.trade_state.partial_exits),
        )
        
        # Reset state
        self.trade_state = None
    
    
    def get_status_summary(self) -> Dict:
        """Get comprehensive status summary"""
        
        if self.trade_state is None:
            return {'in_position': False}
        
        current_time = time.time()
        time_in_trade = current_time - self.trade_state.entry_time
        current_z = self.trade_state.z_history[-1][1]
        
        return {
            'in_position': True,
            'entry_z': self.trade_state.entry_z,
            'current_z': current_z,
            'best_z': self.trade_state.best_z,
            'worst_z': self.trade_state.worst_z,
            'time_in_trade_seconds': time_in_trade,
            'time_in_trade_hours': time_in_trade / 3600,
            'direction': self.trade_state.entry_direction,
            'position_size_initial': self.trade_state.initial_position_size,
            'position_size_current': self.trade_state.current_position_size,
            'partial_exits': len(self.trade_state.partial_exits),
            'trailing_stop_active': self.trade_state.trailing_stop_active,
            'trailing_stop_level': self.trade_state.trailing_stop_level,
            'max_hold_hours': self.config['max_hold_hours'],
            'hours_until_max': self.config['max_hold_hours'] - (time_in_trade / 3600)
        }


