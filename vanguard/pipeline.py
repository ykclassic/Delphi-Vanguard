"""Reference orchestration for the safe Vanguard control path."""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from typing import Callable

from vanguard.approval import ApprovalDecision, ApprovalStore
from vanguard.interfaces import BrokerGateway, ExecutionMode, Ledger, OrderRequest, RiskContext, RiskDecision, SignalProposal
from vanguard.risk_engine import RiskEngine
from vanguard.state_machine import TradeState, TradeStateMachine


class VanguardPipeline:
    def __init__(self, broker: BrokerGateway, risk_engine: RiskEngine, approvals: ApprovalStore, ledger: Ledger, risk_context_provider: Callable[[], RiskContext] | None = None) -> None:
        self.broker = broker
        self.risk_engine = risk_engine
        self.approvals = approvals
        self.ledger = ledger
        self.risk_context_provider = risk_context_provider

    def evaluate(self, proposal: SignalProposal, open_positions: int = 0, daily_loss_percent: float = 0.0, drawdown_percent: float = 0.0, value_per_price_unit: float = 100_000.0):
        sm = self._approval_state(start=True)
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
        self.ledger.append("APPROVAL_REQUESTED", proposal.signal_id, {"approval_id": approval.approval_id, "signal_id": approval.signal_id, "expires_at": approval.expires_at, "risk": asdict(approval.risk)})
        return sm, risk, approval

    @staticmethod
    def client_order_id(approval_id: str, signal_id: str) -> str:
        return "VAN-" + sha256(f"{approval_id}:{signal_id}".encode()).hexdigest()[:28]

    def execute_after_approval(self, proposal: SignalProposal, approval_id: str, approver: str, risk: RiskDecision | None = None, approve: bool = True):
        sm = self._approval_state()
        approval = self.approvals.get(approval_id)
        if approval.signal_id != proposal.signal_id:
            raise ValueError("approval does not belong to proposal")
        if risk is not None and risk != approval.risk:
            raise ValueError("supplied risk decision does not match approved risk decision")
        decision = self.approvals.decide(approval_id, approver, approve)
        self.ledger.append("HUMAN_DECISION", proposal.signal_id, asdict(decision))
        if not decision.approved:
            sm.transition(TradeState.REJECTED)
            return sm, None
        return self._execute_approved(sm, proposal, approval_id, approval.risk)

    def recover_execution(self, proposal: SignalProposal, approval_id: str):
        """Recover an approved execution after a worker/process interruption."""
        decision = self.approvals.get_decision(approval_id)
        record = self.approvals.get_decision_record(approval_id)
        if record.signal_id != proposal.signal_id:
            raise ValueError("approval does not belong to proposal")
        sm = self._approval_state()
        if not decision.approved:
            sm.transition(TradeState.REJECTED)
            return sm, None
        sm.transition(TradeState.APPROVED)
        sm.transition(TradeState.EXECUTION_PENDING)
        client_id = self.client_order_id(approval_id, proposal.signal_id)
        lookup = getattr(self.broker, "lookup_order", None)
        if lookup is None:
            sm.transition(TradeState.FAILED)
            self.ledger.append("RECOVERY_FAILED", proposal.signal_id, {"reason": "BROKER_LOOKUP_UNAVAILABLE", "client_order_id": client_id})
            return sm, None
        try:
            existing = lookup(client_id)
        except Exception as exc:
            sm.transition(TradeState.FAILED)
            self.ledger.append("RECOVERY_FAILED", proposal.signal_id, {"reason": "BROKER_LOOKUP_ERROR", "error": str(exc), "client_order_id": client_id})
            return sm, None
        if existing is not None:
            sm.transition(TradeState.PRE_EXECUTION_REVALIDATION)
            sm.transition(TradeState.ORDER_SUBMITTED)
            sm.transition(TradeState.ORDER_CONFIRMED)
            sm.transition(TradeState.POSITION_OPEN)
            self.ledger.append("ORDER_RECOVERED", proposal.signal_id, asdict(existing))
            return sm, existing
        return self._execute_approved(sm, proposal, approval_id, record.risk, already_pending=True)

    def _execute_approved(self, sm: TradeStateMachine, proposal: SignalProposal, approval_id: str, approved_risk: RiskDecision, already_pending: bool = False):
        if not already_pending:
            sm.transition(TradeState.APPROVED)
            sm.transition(TradeState.EXECUTION_PENDING)
        sm.transition(TradeState.PRE_EXECUTION_REVALIDATION)
        try:
            fresh_quote = self.broker.quote(proposal.symbol)
            account = self.broker.account()
            if self.risk_context_provider is None:
                raise RuntimeError("RISK_CONTEXT_UNAVAILABLE")
            context = self.risk_context_provider()
            fresh_risk = self.risk_engine.evaluate(proposal, fresh_quote, account, context.open_positions, context.daily_loss_percent, context.drawdown_percent, context.value_per_price_unit)
        except Exception as exc:
            sm.transition(TradeState.REJECTED)
            self.ledger.append("PRE_EXECUTION_REJECTED", proposal.signal_id, {"reasons": ("PRE_EXECUTION_CHECK_FAILED",), "error": str(exc)})
            return sm, None
        if not fresh_risk.approved:
            sm.transition(TradeState.REJECTED)
            self.ledger.append("PRE_EXECUTION_REJECTED", proposal.signal_id, {"reasons": fresh_risk.reason_codes, "context": asdict(context)})
            return sm, None
        if fresh_risk.volume != approved_risk.volume:
            sm.transition(TradeState.REJECTED)
            self.ledger.append("PRE_EXECUTION_REJECTED", proposal.signal_id, {"reasons": ("APPROVED_VOLUME_CHANGED",), "approved_volume": approved_risk.volume, "fresh_volume": fresh_risk.volume, "context": asdict(context)})
            return sm, None

        request = OrderRequest(self.client_order_id(approval_id, proposal.signal_id), proposal.signal_id, proposal.symbol, proposal.side, fresh_risk.volume, proposal.stop_loss, proposal.take_profit, self.broker_mode())
        if hasattr(self.ledger, "append_once"):
            self.ledger.append_once("ORDER_SUBMIT_INTENT", proposal.signal_id, asdict(request), request.client_order_id)
        else:
            self.ledger.append("ORDER_SUBMIT_INTENT", proposal.signal_id, asdict(request))
        sm.transition(TradeState.ORDER_SUBMITTED)
        try:
            result = self.broker.submit(request)
        except Exception as exc:
            sm.transition(TradeState.FAILED)
            self.ledger.append("ORDER_SUBMIT_UNKNOWN", proposal.signal_id, {"client_order_id": request.client_order_id, "error": str(exc)})
            return sm, None
        if not result.accepted:
            sm.transition(TradeState.FAILED)
            self.ledger.append("ORDER_REJECTED", proposal.signal_id, asdict(result))
            return sm, result
        sm.transition(TradeState.ORDER_CONFIRMED)
        sm.transition(TradeState.POSITION_OPEN)
        self.ledger.append("ORDER_CONFIRMED", proposal.signal_id, asdict(result))
        return sm, result

    def _approval_state(self, start: bool = False) -> TradeStateMachine:
        sm = TradeStateMachine()
        if start:
            sm.transition(TradeState.SIGNAL_DETECTED)
        else:
            sm.transition(TradeState.SIGNAL_DETECTED)
            sm.transition(TradeState.RISK_VALIDATED)
            sm.transition(TradeState.PENDING_HUMAN_APPROVAL)
        return sm

    def broker_mode(self):
        return getattr(self.broker, "mode", ExecutionMode.PAPER)
