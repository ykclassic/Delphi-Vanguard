# Phase 0 — Delphi Oracle Audit

## Verdict

**NOT READY FOR PRODUCTION TRADING.** Delphi Oracle is a useful signal-generation prototype, but it does not provide the controls required for live order execution.

## Critical findings carried into the baseline

1. **No MT5 execution gateway.** Discord is a notification channel, not a broker execution interface.
2. **No human approval layer.** A generated signal has no explicit approval, expiry, authorization, or replay protection.
3. **Market data is not broker-authoritative.** The baseline uses Yahoo Finance; `XAUUSD` is mapped to `GC=F` gold futures rather than broker spot gold.
4. **Entry price is not executable bid/ask.** There is no authoritative quote, spread, slippage, or fill model.
5. **Position sizing is incomplete.** The baseline calculates SL/TP but does not derive broker volume from account equity, tick value, contract size, and risk budget.
6. **Portfolio risk controls are absent.** No equity, margin, exposure, drawdown, daily-loss, correlation, max-position, or currency-exposure guards exist.
7. **Risk/reward configuration is inconsistent.** SL uses 1.5 ATR while TP uses 2 ATR, producing approximately 1.33:1 R:R despite the configuration wording suggesting 2x stop distance.
8. **News protection fails open.** Provider failures return `False`, allowing trading to continue without validated news protection.
9. **Outcome monitoring is not broker reconciliation.** The original monitor mixed a reset DataFrame index with timestamp filtering and evaluates hypothetical candle hits rather than actual orders/fills.
10. **CSV is used as mutable trading state.** There are no immutable event IDs, transactional writes, durable database semantics, or reconciliation records.
11. **No automated tests existed.** CI therefore did not provide a meaningful correctness gate.
12. **GitHub Actions were used as the trading scheduler.** Scheduled workflows wrote mutable trading logs back to `main`, creating race conditions and excessive repository permissions.
13. **Dependencies were not reproducibly pinned.** The original requirements left `scikit-learn` unconstrained and included unused dependencies.
14. **The original weekly report path had a missing pandas import in `main.py`.** The exception could be swallowed, masking failure.

## Required target control path

`Strategy Engine → Risk Engine → Human Approval Layer → MT5 Execution Gateway`

Only the isolated execution gateway may submit orders. Every execution must be revalidated against a fresh broker quote and current risk state immediately before submission.

## Migration rule

The source repository `ykclassic/Delphi-Oracle` remains unchanged. This repository is the rebuild target and contains the audited baseline for traceability. The historical `logs/trade_log.csv` was intentionally **not copied** because it is mutable, non-authoritative state and must not be treated as a verified trading ledger.

## Next phases

- Establish testable interfaces and CI quality gates.
- Introduce authoritative market-data and broker abstractions.
- Build an independent risk engine.
- Build human approval and expiry/revalidation controls.
- Implement the MT5 execution worker.
- Replace CSV state with durable event/transaction storage.
- Add broker reconciliation and observability.
- Validate in paper/demo mode before any live capability.
