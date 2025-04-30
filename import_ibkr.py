#!/usr/bin/env python3
"""
Import Interactive Brokers STOCK trades from one or more CSV files
into a single Pandas DataFrame, keeping only:

    Currency, Symbol, Date/Time, Quantity, T. Price, Comm/Fee
"""
from __future__ import annotations

import argparse
import csv
import io
import logging
from pathlib import Path
from typing import Iterable, Final

import pandas as pd

# === constants ===
HEADER_PREFIX: Final[str] = "Trades,Header,"
IMPORT_PREFIX: Final[str] = "Trades,Data,Order,Stocks"
KEEP_COLS: Final[list[str]] = [
    "Currency",
    "Symbol",
    "Date/Time",
    "Quantity",
    "T. Price",
    "Comm/Fee",
]

# === helper functions ===
def _scan_csv(path: Path) -> tuple[list[str], list[str]]:
    """Return (header, data_rows) from *path* or raise ValueError."""
    current_header: list[str] | None = None
    header_locked = False
    data_rows: list[str] = []

    with path.open(encoding="utf-8") as fh:
        for raw in fh:
            if raw.startswith(HEADER_PREFIX) and not header_locked:
                current_header = [h.strip() for h in raw.rstrip("\n").split(",")]
                continue

            if raw.startswith(IMPORT_PREFIX):
                if current_header is None:
                    raise ValueError(f"{path.name}: data before header")
                
                # verify field count
                fields = next(csv.reader([raw]))
                if len(fields) != len(current_header):
                    logging.warning("%s: field-count mismatch (expected:%d, actual:%d)  – row skipped",
                        path.name, len(current_header), len(fields))
                    if not header_locked:
                        raise ValueError(f"{path.name}: field-count mismatch")
                    else:
                        continue

                header_locked = True
                data_rows.append(raw)

    if current_header is None:
        raise ValueError(f"{path.name}: no header found")
    return current_header, data_rows


def _parse_one_csv(path: Path) -> pd.DataFrame:
    header, rows = _scan_csv(path)
    if not rows:
        logging.info("%s: no stock trades", path.name)
        return pd.DataFrame(columns=KEEP_COLS)

    buf = io.StringIO()
    buf.write(",".join(header) + "\n")
    buf.writelines(rows)
    buf.seek(0)

    df = pd.read_csv(
        buf,
        header=0,
        usecols=KEEP_COLS,
        thousands=",",
        dtype={
            "Quantity": "float64",  # Could be Int64, but this would handle franctional shares.
            "T. Price": "float64",
            "Comm/Fee": "float64"},
    )
    df["Date/Time"] = pd.to_datetime(
        df["Date/Time"], format="%Y-%m-%d, %H:%M:%S", errors="coerce"
    )
    return df


def load_stock_transactions(paths: Iterable[str | Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for p in paths:
        path = Path(p).expanduser()
        logging.info("Importing %s", path)
        frames.append(_parse_one_csv(path))
    return pd.concat(frames, ignore_index=True)[KEEP_COLS]


# === CLI ===
def _cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import IBKR stock trades")
    p.add_argument("csv", nargs="+", help="CSV file(s) or glob(s)")
    return p.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _cli()

    files: list[Path] = []
    for pattern in args.csv:
        matches = list(Path().glob(pattern))
        if not matches:
            logging.error("no match for %s", pattern)
        files.extend(matches)

    if not files:
        raise SystemExit("nothing to import")

    try:
        df = load_stock_transactions(files)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    logging.info("imported %d trades from %d file(s)", len(df), len(files))
    logging.info("First n trades:\n%s", df.head(10).to_markdown(index=False))
    logging.info("Last m trades:\n%s", df.tail(10).to_markdown(index=False))
    
#    df.to_parquet("ibkr_trades.parquet", index=False)
#    logging.info("saved ibkr_trades.parquet")


if __name__ == "__main__":
    main()
