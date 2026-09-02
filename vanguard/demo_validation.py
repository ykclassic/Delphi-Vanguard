"""Offline end-to-end demo validation. No broker credentials or live network required."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory

from vanguard.approval import ApprovalStore
from vanguard.interfaces import AccountSnapshot, Quote, SignalProposal, Side
from vanguard.ledger import SQLiteLedger
from vanguard.market_data import PaperMarketData
from vanguard.paper import PaperBroker
from vanguard.pipeline import VanguardPipeline
from vanguard.risk_engine import RiskEngine, RiskLimits


def run() -> str:
    now = datetime.now(timezone.utc)
    quote = Quote("EURUSD", 1.0999, 1.1001, "PAPER", now)
    market = PaperMarketData({"EURUSD": quote})
    broker = PaperBroker(market)
    proposal = SignalProposal("demo-signal-1", "EURUSD", Side.BUY, "demo", "1.0", now, now + timedelta(seconds=30), 1.1000, 1.0980, 1.1045, .9, "deterministic demo", {"demo": 1.0})
    with TemporaryDirectory() as tmp:
        ledger = SQLiteLedger(f"{tmp}/demo.db")
        pipeline = VanguardPipeline(broker, RiskEngine(RiskLimits(max_spread=.001)), ApprovalStore(), ledger)
        sm, risk, approval = pipeline.evaluate(proposal, value_per_price_unit=100_000)
        if approval is None or not risk.approved:
            raise AssertionError(f"demo risk gate failed: {risk}")
        sm, result = pipeline.execute_after_approval(proposal, approval.approval_id, "demo-operator", risk)
        if result is None or not result.accepted:
            raise AssertionError("demo order was not accepted")
        return sm.state.value


if __name__ == "__main__":
    print(f"DEMO VALIDATION: {run()}")
