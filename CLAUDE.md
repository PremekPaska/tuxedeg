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
  `SaleRecord.calculate_income_and_cost`). Strategies live in `find_buys_*` (fifo, lifo,
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
