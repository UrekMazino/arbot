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
            'trailing_stop_distance': 0.5,    # Trail by 0.5 sigma
            
            # Maximum hold time
            'max_hold_hours': 6,  # 6 hours maximum
            'max_hold_warning_hours': 4,  # Warning at 4 hours
            
            # Take profit
            'take_profit_z': 0.5,  # Exit at Z < 0.5
            
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
    
    
    def update(self, current_z: float) -> Dict:
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
        
        # 3. TRAILING STOP
        trailing_result = self._check_trailing_stop(current_z)
        if trailing_result['action'] == 'EXIT':
            return trailing_result
        
        # 4. PARTIAL EXIT
        partial_result = self._check_partial_exit(current_z)
        if partial_result['action'] == 'PARTIAL_EXIT':
            return partial_result
        
        # 5. TAKE PROFIT (full exit)
        if abs(current_z) < self.config['take_profit_z']:
            return self._create_exit_result(
                action='EXIT',
                reason=ExitReason.TAKE_PROFIT,
                message=f"Take profit: Z={current_z:+.2f} sigma (target: {self.config['take_profit_z']:.2f} sigma)",
                percentage=1.0
            )
        
        # 6. STALL DETECTION (dynamic)
        stall_result = self._check_stall_dynamic(current_z)
        if stall_result['action'] == 'EXIT':
            return stall_result
        elif stall_result['action'] == 'WARNING':
            logger.warning("Stall warning: %s", stall_result["reason"])
        
        # 7. NO EXIT - HOLD POSITION
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
        
        abs_current = abs(current_z)
        abs_best = abs(self.trade_state.best_z)
        activation_threshold = self.config['trailing_stop_activation']
        trail_distance = self.config['trailing_stop_distance']
        
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
    
    
    def _create_exit_result(self, action: str, reason: ExitReason, 
                           message: str, percentage: float) -> Dict:
        """Create standardized exit result"""
        
        time_in_trade = time.time() - self.trade_state.entry_time
        
        return {
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


