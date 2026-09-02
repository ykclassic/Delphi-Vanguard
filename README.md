# Delphi Vanguard

Production-oriented rebuild of **Delphi Oracle** for controlled FX research, signal generation, risk validation, human approval, and broker execution.

## Baseline provenance

This repository is populated from the audited `ykclassic/Delphi-Oracle` baseline at commit `71c606b54215bcbda21a91c84d4e0f0959e5c82b`.

The original Delphi Oracle repository is preserved unchanged. This repository is the canonical rebuild target.

## Phase 0 status

The Delphi Oracle baseline was audited before migration. It is **not production-ready for live trading**. Known issues include:

- no MT5 execution gateway or broker abstraction
- no human approval layer
- non-authoritative Yahoo Finance market data and an incorrect XAUUSD futures mapping
- no broker executable bid/ask or fill-price model
- position sizing is not actually calculated from account risk
- missing equity, margin, exposure, drawdown and daily-loss controls
- configured take-profit ratio does not match the actual stop-distance ratio
- news protection fails open
- broken timestamp/index handling in the outcome monitor
- CSV/Git used as mutable trading state
- no automated test suite
- GitHub Actions used as the trading scheduler and granted write access to repository contents
- unpinned dependencies and no reproducible build lock

## Safety boundary

Delphi Vanguard must not execute live orders merely because CI passes. The intended control path is:

**Strategy Engine → Risk Engine → Human Approval → MT5 Execution Gateway**

Live execution remains disabled until the risk, approval, execution, persistence, reconciliation, security, and paper/demo validation phases are complete.

## Repository direction

The migrated Oracle modules are retained as a traceable research baseline. Subsequent phases will replace unsafe production behavior with explicit interfaces, durable state, authoritative broker data, independent risk controls, human approval, and an isolated MT5 execution worker.
