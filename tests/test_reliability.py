from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory

import pytest

from vanguard.approval import ApprovalStore
from vanguard.interfaces import AccountSnapshot, ExecutionMode, OrderRequest, Quote, SignalProposal, Side
from vanguard.ledger import SQLiteLedger
from vanguard.market_data import PaperMarketData, StaleQuote, validate_quote
from vanguard.paper import PaperBroker
from vanguard.reconciliation import reconcile
from vanguard.risk_engine import RiskEngine, RiskLimits
from vanguard.state_machine import InvalidTransition, TradeState, TradeStateMachine


NOW = datetime.now(timezone.utc)


def proposal(side=Side.BUY, expires=None):
    return SignalProposal("sig-1", "EURUSD", side, "trend", "1.0", NOW, expires or NOW + timedelta(seconds=30), 1.1000, 1.0980, 1.1045, .8, "test", {"x": 1.0})


def quote():
    return Quote("EURUSD", 1.0999, 1.1001, "PAPER", NOW)


def account():
    return AccountSnapshot(10_000, 10_000, 0, 10_000, "USD", NOW)


def test_state_machine_rejects_skipped_gate():
    sm = TradeStateMachine()
    with pytest.raises(InvalidTransition):
        sm.transition(TradeState.APPROVED)


def test_quote_freshness_is_fail_closed():
    with pytest.raises(StaleQuote):
        validate_quote(Quote("EURUSD", 1.1, 1.1002, "PAPER", NOW - timedelta(seconds=10)), NOW)


def test_risk_engine_requires_two_to_one_rr_and_sizes_volume():
    engine = RiskEngine(RiskLimits(max_spread=.001))
    decision = engine.evaluate(proposal(), quote(), account(), 0, 0, 0, 100_000)
    assert decision.approved
    assert decision.risk_reward >= 2
    assert decision.volume > 0


def test_risk_engine_rejects_wide_spread():
    engine = RiskEngine(RiskLimits(max_spread=.00005))
    decision = engine.evaluate(proposal(), quote(), account(), 0, 0, 0, 100_000)
    assert not decision.approved
    assert "SPREAD_TOO_WIDE" in decision.reason_codes


def test_approval_is_single_use_and_requires_identity():
    store = ApprovalStore()
    risk = RiskEngine(RiskLimits(max_spread=.001)).evaluate(proposal(), quote(), account(), 0, 0, 0, 100_000)
    request = store.create(proposal(), risk)
    with pytest.raises(ValueError):
        store.decide(request.approval_id, "", True)
    decision = store.decide(request.approval_id, "operator", True)
    assert decision.approved
    with pytest.raises(ValueError):
        store.decide(request.approval_id, "operator", True)


def test_sqlite_ledger_is_durable_and_hashes_events():
    with TemporaryDirectory() as tmp:
        path = f"{tmp}/vanguard.db"
        ledger = SQLiteLedger(path)
        event_id = ledger.append("SIGNAL_DETECTED", "sig-1", {"symbol": "EURUSD"})
        ledger.close()
        reopened = SQLiteLedger(path)
        events = reopened.events("sig-1")
        assert events[0]["event_id"] == event_id
        assert events[0]["payload_hash"]
        reopened.close()


def test_paper_broker_is_idempotent():
    md = PaperMarketData({"EURUSD": quote()})
    broker = PaperBroker(md)
    request = OrderRequest("o1", "sig-1", "EURUSD", Side.BUY, .1, 1.098, 1.1045, ExecutionMode.PAPER)
    first = broker.submit(request)
    second = broker.submit(request)
    assert first == second


def test_reconciliation_detects_missing_and_unexpected():
    result = reconcile(["a", "b"], ["b", "c"])
    assert result.matched == ("b",)
    assert result.missing_on_broker == ("a",)
    assert result.unexpected_on_broker == ("c",)
