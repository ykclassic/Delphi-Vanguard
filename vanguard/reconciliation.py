"""Reconcile durable intent/execution records against broker state."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ReconciliationResult:
    matched: tuple[str, ...]
    missing_on_broker: tuple[str, ...]
    unexpected_on_broker: tuple[str, ...]


def reconcile(expected_order_ids: Iterable[str], broker_order_ids: Iterable[str]) -> ReconciliationResult:
    expected = set(expected_order_ids)
    actual = set(broker_order_ids)
    return ReconciliationResult(tuple(sorted(expected & actual)), tuple(sorted(expected - actual)), tuple(sorted(actual - expected)))


class ReconciliationService:
    """Pure reconciliation logic; persistence/alerting stays outside the broker adapter."""

    def compare(self, ledger_orders: Mapping[str, object], broker_orders: Mapping[str, object]) -> ReconciliationResult:
        return reconcile(ledger_orders.keys(), broker_orders.keys())
