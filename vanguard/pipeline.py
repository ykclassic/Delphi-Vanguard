"""Reference orchestration for the safe Vanguard control path."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from vanguard.approval import ApprovalStore
from vanguard.interfaces import BrokerGateway, Ledger, OrderRequest, RiskDecision, SignalProposal
from vanguard.risk_engine import RiskEngine
from vanguard.state_machine import TradeState, TradeStateMachine


class VanguardPipeline:
    def __init__(self, broker: BrokerGateway, risk_engine: RiskEngine, approvals: ApprovalStore, ledger: Ledger) -> None:
        self.broker = broker
        self.risk_engine = risk_engine
        self.approvals = approvals
        self.ledger = ledger

    def evaluate(self, proposal: SignalProposal, open_positions: int = 0, daily_loss_percent: float = 0.0, drawdown_percent: float = 0.0, value_per_price_unit: float = 100_000.0):
        sm = TradeStateMachine()
        sm.transition(TradeState.SIGNAL_DETECTED)
        self.ledger.append("SIGNAL_DETECTED", proposal.signal_id, asdict(proposal))
        quote = self.broker.quote(proposal.symbol)
        account = self.broker.account()
        risk = self.risk_engine.evaluate(proposal, quote, account, open_positions, daily_loss_percent, drawdown_percent, value_per_price_unit)
        if not risk.approved:
            sm.transition(TradeState.REJECTED)
            self.ledger.append("RISK_REJECTED", proposal.signal_id, {"reasons": risk.reason_codes})
            return sm, risk, None
        sm.transition(TradeState.RISK_VALIDATED)
        sm.transition(TradeState.PENDING_HUMAN_APPROVAL)
        approval = self.approvals.create(proposal, risk)
        self.ledger.append("APPROVAL_REQUESTED", proposal.signal_id, asdict(approval))
        return sm, risk, approval

    def execute_after_approval(self, proposal: SignalProposal, approval_id: str, approver: str, risk: RiskDecision, approve: bool = True):
        sm = TradeStateMachine()
        sm.transition(TradeState.SIGNAL_DETECTED)
        sm.transition(TradeState.RISK_VALIDATED)
        sm.transition(TradeState.PENDING_HUMAN_APPROVAL)
        decision = self.approvals.decide(approval_id, approver, approve)
        self.ledger.append("HUMAN_DECISION", proposal.signal_id, asdict(decision))
        if not decision.approved:
            sm.transition(TradeState.REJECTED)
            return sm, None
        sm.transition(TradeState.APPROVED)
        sm.transition(TradeState.EXECUTION_PENDING)
        sm.transition(TradeState.PRE_EXECUTION_REVALIDATION)
        fresh_quote = self.broker.quote(proposal.symbol)
        account = self.broker.account()
        fresh_risk = self.risk_engine.evaluate(proposal, fresh_quote, account, 0, 0.0, 0.0, 100_000.0)
        if not fresh_risk.approved or fresh_risk.volume != risk.volume:
            sm.transition(TradeState.REJECTED)
            self.ledger.append("PRE_EXECUTION_REJECTED", proposal.signal_id, {"reasons": fresh_risk.reason_codes})
            return sm, None
        request = OrderRequest(str(uuid4()), proposal.signal_id, proposal.symbol, proposal.side, fresh_risk.volume, proposal.stop_loss, proposal.take_profit, self.broker_mode())
        self.ledger.append("ORDER_SUBMIT_INTENT", proposal.signal_id, asdict(request))
        sm.transition(TradeState.ORDER_SUBMITTED)
        result = self.broker.submit(request)
        if not result.accepted:
            sm.transition(TradeState.FAILED)
            self.ledger.append("ORDER_REJECTED", proposal.signal_id, asdict(result))
            return sm, result
        sm.transition(TradeState.ORDER_CONFIRMED)
        sm.transition(TradeState.POSITION_OPEN)
        self.ledger.append("ORDER_CONFIRMED", proposal.signal_id, asdict(result))
        return sm, result

    def broker_mode(self):
        return getattr(self.broker, "mode", "PAPER")
