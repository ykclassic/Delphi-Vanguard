from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory

from vanguard.approval import ApprovalStore
from vanguard.interfaces import RiskContext, SignalProposal, Side
from vanguard.ledger import SQLiteLedger
from vanguard.market_data import PaperMarketData
from vanguard.paper import PaperBroker
from vanguard.pipeline import VanguardPipeline
from vanguard.risk_engine import RiskEngine, RiskLimits


def make_proposal():
    now = datetime.now(timezone.utc)
    return SignalProposal("phase3-signal", "EURUSD", Side.BUY, "test", "1.0", now, now + timedelta(minutes=2), 1.1000, 1.0980, 1.1045, .9, "phase3", {"x": 1.0})


def make_components(path):
    now = datetime.now(timezone.utc)
    quote = __import__("vanguard.interfaces", fromlist=["Quote"]).Quote("EURUSD", 1.0999, 1.1001, "PAPER", now)
    broker = PaperBroker(PaperMarketData({"EURUSD": quote}))
    ledger = SQLiteLedger(path)
    approvals = ApprovalStore(path)
    context = RiskContext(0, 0.0, 0.0, 100_000.0)
    pipeline = VanguardPipeline(broker, RiskEngine(RiskLimits(max_spread=.001)), approvals, ledger, lambda: context)
    return pipeline, broker, approvals, ledger


def test_approval_survives_store_restart():
    with TemporaryDirectory() as tmp:
        path = f"{tmp}/vanguard.db"
        pipeline, _, approvals, ledger = make_components(path)
        proposal = make_proposal()
        _, risk, request = pipeline.evaluate(proposal, value_per_price_unit=100_000.0)
        assert risk.approved
        assert request is not None
        approvals.close()
        ledger.close()

        reopened = ApprovalStore(path)
        restored = reopened.get(request.approval_id)
        assert restored.signal_id == proposal.signal_id
        assert restored.risk == risk
        reopened.close()


def test_approved_execution_recovers_after_interruption_without_new_order_id():
    with TemporaryDirectory() as tmp:
        path = f"{tmp}/vanguard.db"
        pipeline, broker, approvals, ledger = make_components(path)
        proposal = make_proposal()
        _, risk, request = pipeline.evaluate(proposal, value_per_price_unit=100_000.0)
        assert risk.approved and request is not None
        decision = approvals.decide(request.approval_id, "operator", True)
        ledger.append("HUMAN_DECISION", proposal.signal_id, {"approval_id": decision.approval_id, "approved": True})

        recovered_pipeline = VanguardPipeline(broker, pipeline.risk_engine, approvals, ledger, pipeline.risk_context_provider)
        sm, result = recovered_pipeline.recover_execution(proposal, request.approval_id)
        assert result is not None
        assert sm.state.value == "POSITION_OPEN"
        client_id = recovered_pipeline.client_order_id(request.approval_id, proposal.signal_id)
        assert result.client_order_id == client_id
        assert len(broker.orders) == 1

        sm2, result2 = recovered_pipeline.recover_execution(proposal, request.approval_id)
        assert sm2.state.value == "POSITION_OPEN"
        assert result2 == result
        assert len(broker.orders) == 1


def test_ledger_append_once_is_idempotent():
    with TemporaryDirectory() as tmp:
        ledger = SQLiteLedger(f"{tmp}/vanguard.db")
        first = ledger.append_once("ORDER_SUBMIT_INTENT", "sig", {"client_order_id": "VAN-1"}, "VAN-1")
        second = ledger.append_once("ORDER_SUBMIT_INTENT", "sig", {"client_order_id": "VAN-1"}, "VAN-1")
        assert first == second
        assert len(ledger.events("sig")) == 1
        ledger.close()
