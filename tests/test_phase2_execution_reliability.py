from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory

import pytest

from vanguard.approval import ApprovalStore
from vanguard.interfaces import AccountSnapshot, ExecutionMode, OrderRequest, Quote, RiskContext, SignalProposal, Side
from vanguard.ledger import SQLiteLedger
from vanguard.market_data import PaperMarketData
from vanguard.paper import PaperBroker
from vanguard.pipeline import VanguardPipeline
from vanguard.risk_engine import RiskEngine, RiskLimits


NOW = datetime.now(timezone.utc)


def make_proposal():
    return SignalProposal("phase2-signal", "EURUSD", Side.BUY, "test", "1.0", NOW, NOW + timedelta(seconds=30), 1.1000, 1.0980, 1.1045, .9, "phase2", {"x": 1.0})


def make_pipeline(context_provider):
    quote = Quote("EURUSD", 1.0999, 1.1001, "PAPER", NOW)
    broker = PaperBroker(PaperMarketData({"EURUSD": quote}))
    ledger = SQLiteLedger(":memory:")
    return VanguardPipeline(broker, RiskEngine(RiskLimits(max_spread=.001)), ApprovalStore(), ledger, context_provider), broker


def test_paper_broker_declares_paper_mode_and_rejects_non_paper_orders():
    quote = Quote("EURUSD", 1.0999, 1.1001, "PAPER", NOW)
    broker = PaperBroker(PaperMarketData({"EURUSD": quote}))
    assert broker.mode is ExecutionMode.PAPER
    request = OrderRequest("mode-test", "sig", "EURUSD", Side.BUY, .1, 1.098, 1.1045, ExecutionMode.DEMO)
    with pytest.raises(ValueError, match="PAPER execution mode only"):
        broker.submit(request)


def test_execution_uses_current_risk_context_and_rejects_position_limit_change():
    initial = RiskContext(0, 0.0, 0.0, 100_000.0)
    current = {"value": initial}
    pipeline, _ = make_pipeline(lambda: current["value"])
    proposal = make_proposal()
    _, risk, approval = pipeline.evaluate(proposal, value_per_price_unit=100_000.0)
    assert risk.approved and approval is not None
    current["value"] = RiskContext(3, 0.0, 0.0, 100_000.0)
    sm, result = pipeline.execute_after_approval(proposal, approval.approval_id, "operator", risk)
    assert result is None
    assert sm.state.value == "REJECTED"


def test_execution_rejects_volume_drift_after_approval():
    initial = RiskContext(0, 0.0, 0.0, 100_000.0)
    current = {"value": initial}
    pipeline, _ = make_pipeline(lambda: current["value"])
    proposal = make_proposal()
    _, risk, approval = pipeline.evaluate(proposal, value_per_price_unit=100_000.0)
    assert risk.approved and approval is not None
    current["value"] = RiskContext(0, 0.0, 0.0, 120_000.0)
    sm, result = pipeline.execute_after_approval(proposal, approval.approval_id, "operator", risk)
    assert result is None
    assert sm.state.value == "REJECTED"


def test_execution_fails_closed_when_live_risk_context_is_unavailable():
    pipeline, _ = make_pipeline(None)
    proposal = make_proposal()
    _, risk, approval = pipeline.evaluate(proposal, value_per_price_unit=100_000.0)
    assert risk.approved and approval is not None
    sm, result = pipeline.execute_after_approval(proposal, approval.approval_id, "operator", risk)
    assert result is None
    assert sm.state.value == "REJECTED"
