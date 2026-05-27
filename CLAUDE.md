# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Czech tax reporting tool for investment transactions from Degiro and Interactive Brokers. Pairs buy/sell lots using configurable strategies (fifo, lifo, max_cost, min_cost, micol) and outputs results/pairings CSVs.

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
