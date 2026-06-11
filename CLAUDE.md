# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Czech tax reporting tool for investment transactions from Degiro and Interactive Brokers. Pairs buy/sell lots using configurable strategies (fifo, lifo, max_cost, min_cost, micol) and outputs results/pairings CSVs.

## Code map

Flow: `main.py:main()` parses args → imports a DataFrame → `optimize_all()` (main.py:145)
loops over products, calling `optimize_product()` per product, then builds the results
table + CSV and the console summary.

- **`main.py`** — entry point and orchestration. `main()` (argparse, mode validation,
  import dispatch); `optimize_all()` (per-product loop, results DataFrame, both CSV exports,
  console summary, output filename); `build_transactions()` (DataFrame→`Transaction`s, applies
  splits); `build_pairing_rows()` (detailed pairings CSV); `setup_strategies()`/
  `load_strategies()` (year→strategy map); `detect_account_code()`.
- **`optimizer.py`** — pairing + aggregation. `optimize_product()` = `optimize_transaction_pairing()`
  (matches buys to sells via the selected strategy) + `calculate_tax()` (which calls
  `SaleRecord.calculate_income_and_cost`). Every `SaleRecord` closes within a single
  year: short covers from a later year than the sale go into per-year *spillover*
  records (`is_spillover`), and the earliest non-empty record per sale owns the sale
  fee (`owns_sale_fee`) so it is counted exactly once. Strategies live in `find_buys_*` (fifo, lifo,
  max_cost, min_cost, micol), dispatched by `find_buys()`. Per-product aggregators that read
  a `List[SaleRecord]` and filter on `close_time.year == tax_year`: `calculate_totals`
  (income/cost/fees), `calculate_expired_long_totals`, `calculate_untaxed_totals`,
  `calculate_ttc_totals` (shares held > N months). Add new result columns by following this
  aggregator pattern + threading through `optimize_all`.
- **`transaction.py`** — domain model. `Transaction` (`_multiplier` = 100 for options, else 1);
  `BuyRecord` (one matched buy lot, `_count_consumed`, `_is_short_cover`, `calculate_cost`);
  `SaleRecord` (a sale + its `buys`, `close_time` = max(sale time, cover times)). **The time
  test lives in `SaleRecord.calculate_income_and_cost` (transaction.py:249):**
  `(sale_t.time - buy_t.time).days > 3*365`.
- **Imports** — `import_deg.py:import_transactions` (Degiro); `import_ibkr.py:import_ibkr_stock_transactions`
  / `import_ibkr_option_transactions` (IBKR); `import_ibkr.py:import_corporate_actions` (splits).
  `import_utils.py` shared helpers. `currency.py:unified_fx_rate(year, currency)` → CZK rate.
- **Shares vs options is per-run, not per-transaction** — fixed by `--options` at import time;
  the whole report is one or the other. `option_contract` flows into each `Transaction`.
- **Tests** — `tests/`. `tests/test_transaction.py:create_t(count, price, ..., year_offset)`
  is the shared transaction builder; `test_optimizer.py` has `scenario_*` helpers.

## Commands

Run:
```
python main.py --deg --year 2024 transactions.csv
python main.py --ibkr --year 2024 trades.csv
python main.py --ibkr --options --year 2024 trades.csv
```

Test:
```
.venv/bin/python -m pytest tests/ -x -q
```

No linter is configured.

## Key gotchas

- **Strategies config**: `config/strategies.json` maps year → strategy for all prior years. `--strategy` overrides only the target year; prior years still use the config.
- **Time test**: Enabled by default. Filters P&L from sales >3 years after purchase (Czech tax rule). Disable with `--no-ttest`.
- **Stock splits**: Loaded from `config/corporate_actions.csv` and applied before pairing. Skipped with `--no-split`.
- **Output**: Written to `outputs/` with format `YYYY-MM-DD-results-{account}-{year}-{strategy}.csv`.
- **Working directory**: `main.py` does `os.chdir` to repo root at startup; all relative paths resolve from there.

## Known issues (found in reviews 2026-06, not yet fixed)

Ordered by severity:

1. **Duplicate split rows are applied twice on IBKR runs.** `apply_stock_splits_for_product`
   dedupes only when `id_col == "ISIN"` (corporate_action.py:45); Symbol-based (IBKR) runs
   don't dedup. The shipped `config/corporate_actions.csv` has two IAU rows (parsed from
   "IAU" and "IAU.OLD", same date) → the 1:2 reverse split applies twice: fractional-share
   ValueError (ERROR row) or a silently halved-again basis + phantom short on the later sell.
   Dedup should key on `(id_col, "Report Date")` unconditionally.
2. **Fractional IBKR quantities are silently truncated.** `Transaction.__init__` does
   `int(count)` (transaction.py:21) on the float Quantity the importer deliberately reads.
   Buy 10.5 → 10; a pure fractional sell of −0.5 becomes count 0, `is_sale` False — the
   sale silently vanishes. Should raise on non-integral counts.
3. **Degiro split rows are dropped with no config cross-check.** `import_deg.py:137` drops
   the broker's split-adjustment rows, trusting `config/corporate_actions.csv` (generated
   from *IBKR* statements) to supply the ratio. A Degiro product not also held at IBKR gets
   no adjustment: full post-split sell raises (ERROR row), partial sell silently pairs at
   pre-split prices (cost overstated by the split factor). Only TSLA has a hardcoded guard
   (corporate_action.py:49). The dropped rows carry quantity deltas that could verify a
   config entry exists.
4. **Same-timestamp buy/sell pairing is unstable.** `find_buys_*` use strict
   `t.time < sale_t.time`, so a buy with the same timestamp as a sale can never pair
   with it; the chronological sort in `optimize_transaction_pairing` breaks ties by
   input order. A sale preceding its same-timestamp buy raises (Degiro) or silently
   opens a phantom short (IBKR).
5. **Strategies config fails late.** Only `year-1`/`year` are validated; a sale in an
   unconfigured middle year (KeyError) or an invalid strategy name in the JSON is
   swallowed per-product as an ERROR row with zero income instead of stopping the run.
6. **Time test off-by-a-leap-day.** `(sale - buy).days > 3*365` is 1095 days, but 3
   calendar years usually span 1096 — a lot sold a day short of 3 years can wrongly
   pass. Should compare calendar dates.
7. **Uncovered shorts' income is never taxed.** A short opened but never covered in
   the data yields zero income with only a console warning; Czech cash-basis rules
   would likely tax the proceeds in the sale year.
8. **Placeholder FX rates are used silently.** `currency.py` ships made-up rates for
   the last configured year (marked TODO); running that tax year produces a confident
   report with fake numbers. Placeholder years should raise.
9. **Buy fees go whole-lot to the first consuming pair** (`consume_shares` one-shot flag,
   transaction.py:103). A lot sold across two years deducts its full buy fee in the earlier
   year; and the time-test `continue` (transaction.py:261) runs before fees are summed, so
   if the fee-carrying pair is the time-test-excluded one, the fee is lost for the taxable
   remainder. Pinned by `test_time_test_flag_enabled` — change the test if fixing.
10. **Splits dated after the tax year are still applied.** The filter only checks
    `ts > first_tx_time` (corporate_action.py:39) with no upper bound, so e.g. ACB's 2024
    reverse split applies to a `--year 2023` run; non-divisible counts raise → ERROR row
    for a year in which the split hadn't happened. Otherwise P&L-neutral but reports
    not-yet-effective units.
11. **IBKR rows with field-count mismatch are silently dropped trades** (import_ibkr.py:53)
    — only an unconfigured `logging.warning` to stderr, easily lost; happens with
    multi-section combined statements (header locks after first match). Should be fatal.
    Also: `usecols` hard-requires a `Code` column, so older exports fail opaquely.
12. **Options multiplier hardcoded to 100** (transaction.py:32); the importer doesn't read
    IBKR's Multiplier column, so non-standard contracts (minis, split-adjusted deliverables)
    are silently mis-scaled.
13. **Pairings CSV audit gaps**: rows from *all* years are exported with nothing marking
    which contributed to the tax-year totals (double-count risk when filing); `PairID`
    collides across products (`{timestamp}_{idx}`, idx restarts per product); ERROR
    products can still export rows (`current_pairing_rows` assigned before aggregators run).
14. **`--bep` is unreliable** (low priority): `calculate_break_even_prices` divides by
    running quantity — data starting with a short raises ZeroDivisionError, flat-then-short
    gives nonsense BEPs; and `calculate_income_and_cost` overwrites `buy_t._share_price`
    with the BEP, so the pairings CSV exports synthetic prices as `SharePrice`.
15. **Fragile plumbing / hygiene**: Degiro currency read positionally via
    `get_loc('Price') + 2` (import_deg.py:182 — depends on the unnamed column layout and
    `reset_index()` adding exactly one column); `os.chdir` to repo root happens *before*
    input files are read, so relative input paths resolve against the repo (resolve
    `args.files` first); `manual_debug` is broken (undefined `get_isin`, stale signature);
    `--options` without `--ibkr` mislabels the account code (and `detect_account_code`
    matches "cz"/"ie" as substrings anywhere in the filename); shadowed `datetime`
    import; unused imports; quadratic per-row `pd_concat` in `optimize_all`; two test
    classes `os.chdir` inside tests (order-coupled suite).

## Design decisions (intentional — don't re-flag as bugs)

- **Cross-year short income is valued at the sale-year FX rate** even though it's taxed
  in the cover year (transaction.py:226). Deliberate and pinned by
  `test_short_covered_across_years`; revisit only as a tax-methodology question.
- **Short covers always pair FIFO**, regardless of the configured strategy
  (optimizer.py:267).
- **Degiro is long-only** (`allow_partial=False`): an unpairable sell raises rather than
  opening a short; IBKR allows partial fills/shorts.

## Architecture debt (review 2026-06)

Top maintainability problems, in rough order of leverage:

1. **Mutable shared state with order-dependent correctness.** `Transaction` is at once the
   imported fact, the pairing ledger, and a scratchpad: splits rewrite count/price in
   place, pairing consumes `_remaining_count` and a one-shot fee flag, BEP overwrites
   `_share_price`. Several known issues (BEP export, ERROR-product pairing rows, fee
   placement) are symptoms. Separate immutable trade data from pairing/tax result objects.
2. **The console is the API.** `optimize_all` returns `None`; outputs are CSVs plus
   interleaved prints. Money-critical signals (partial fills, uncovered shorts, dropped
   rows, ERROR products) look like debug noise, and a run with swallowed errors still
   prints a confident profit line and exits 0. Return a result object, separate
   diagnostics by severity, exit nonzero on any product error.
3. **World knowledge hardcoded in source.** FX tables as positional arrays with silent
   placeholder years; TENET skip-list in `optimize_all`; 2021-only product-name exceptions
   in `import_deg`; TSLA-only split guard; multiplier=100; fee currency=EUR. Move to
   validated config with fail-loud expiry.
4. **The Degiro/IBKR duality leaks everywhere instead of being normalized at import.**
   `isin` doubles as symbol; `id_col` if-branches in main/corporate_action/export; broker
   semantics inferred from a column name (`allow_partial = id_col != "ISIN"`). One
   normalized schema with explicit `broker`/`allows_shorts` attributes would delete most
   branching (including the split-dedup gap, issue 1).
5. **`optimize_all` is a ~200-line god function guarded by golden-value tests.**
   Orchestration, aggregation, formatting, filename policy, and export in one function
   with ten flags; integration tests pin 4-decimal CZK totals from committed real exports,
   so any rounding/order change reads as a failure — which discourages the refactoring the
   module needs. Split computation (returning data) from presentation.
