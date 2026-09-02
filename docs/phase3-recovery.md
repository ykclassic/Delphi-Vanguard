# Phase 3 — Durable Approval & Recovery

## Guarantees

- Human approvals are persisted in SQLite and survive process/worker restarts.
- The exact approved `RiskDecision`, including its immutable `RiskContext`, is persisted with the approval.
- Approval consumption is atomic and single-use.
- Execution intent uses a deterministic client order ID derived from the approval and signal IDs.
- Execution intent is written before broker submission and is idempotent in the ledger.
- Recovery first asks the broker for the deterministic client order ID before attempting another submission.
- If broker lookup is unavailable or errors, recovery fails closed rather than risking a duplicate order.
- Live execution remains disabled.
