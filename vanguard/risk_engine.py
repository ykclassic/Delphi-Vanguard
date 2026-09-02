"""Independent, fail-closed pre-trade risk engine."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from vanguard.interfaces import AccountSnapshot, Quote, RiskDecision, Side, SignalProposal


@dataclass(frozen=True)
class RiskLimits:
    risk_percent: float = 1.0
    max_spread: float = 0.0005
    max_positions: int = 3
    max_daily_loss_percent: float = 3.0
    max_drawdown_percent: float = 10.0
    max_volume: float = 100.0
    min_volume: float = 0.01
    volume_step: float = 0.01


class RiskEngine:
    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def evaluate(self, proposal: SignalProposal, quote: Quote, account: AccountSnapshot, open_positions: int, daily_loss_percent: float, drawdown_percent: float, value_per_price_unit: float) -> RiskDecision:
        reasons: list[str] = []
        if proposal.expires_at <= quote.timestamp:
            reasons.append("SIGNAL_EXPIRED")
        executable = quote.executable_price(proposal.side)
        if proposal.side is Side.BUY and proposal.stop_loss >= executable:
            reasons.append("INVALID_BUY_STOP")
        if proposal.side is Side.SELL and proposal.stop_loss <= executable:
            reasons.append("INVALID_SELL_STOP")
        if proposal.side is Side.BUY and proposal.take_profit <= executable:
            reasons.append("INVALID_BUY_TARGET")
        if proposal.side is Side.SELL and proposal.take_profit >= executable:
            reasons.append("INVALID_SELL_TARGET")
        if quote.spread > self.limits.max_spread:
            reasons.append("SPREAD_TOO_WIDE")
        if open_positions >= self.limits.max_positions:
            reasons.append("MAX_POSITIONS")
        if daily_loss_percent >= self.limits.max_daily_loss_percent:
            reasons.append("DAILY_LOSS_LIMIT")
        if drawdown_percent >= self.limits.max_drawdown_percent:
            reasons.append("DRAWDOWN_LIMIT")
        if account.free_margin <= 0 or account.equity <= 0:
            reasons.append("INSUFFICIENT_MARGIN")

        stop_distance = abs(executable - proposal.stop_loss)
        reward_distance = abs(proposal.take_profit - executable)
        rr = reward_distance / stop_distance if stop_distance else 0.0
        if stop_distance <= 0:
            reasons.append("ZERO_STOP_DISTANCE")
        if rr < 2.0:
            reasons.append("MIN_RR_NOT_MET")
        risk_amount = account.equity * self.limits.risk_percent / 100.0
        raw_volume = risk_amount / (stop_distance * value_per_price_unit) if stop_distance and value_per_price_unit > 0 else 0.0
        if not isfinite(raw_volume) or raw_volume <= 0:
            reasons.append("POSITION_SIZE_UNAVAILABLE")
            volume = 0.0
        else:
            volume = min(self.limits.max_volume, raw_volume)
            volume = (volume // self.limits.volume_step) * self.limits.volume_step
            if volume < self.limits.min_volume:
                reasons.append("MIN_VOLUME_NOT_MET")
                volume = 0.0
        return RiskDecision(not reasons, tuple(reasons), round(volume, 8), risk_amount, stop_distance, reward_distance, rr, quote.timestamp)
