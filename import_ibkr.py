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
import re

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
        for line in fh:
            if line.startswith(HEADER_PREFIX) and not header_locked:
                current_header = [h.strip() for h in line.rstrip("\n").split(",")]
                continue

            if line.startswith(IMPORT_PREFIX):
                if current_header is None:
                    raise ValueError(f"{path.name}: data before header")
                
                # verify field count
                fields = next(csv.reader([line]))
                if len(fields) != len(current_header):
                    logging.warning("%s: field-count mismatch (expected:%d, actual:%d)  – row skipped",
                        path.name, len(current_header), len(fields))
                    if not header_locked:
                        raise ValueError(f"{path.name}: field-count mismatch")
                    else:
                        continue

                header_locked = True
                data_rows.append(line)

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
            "Quantity": "float64",  # Could be Int64, but floats would handle fractional shares.
            "T. Price": "float64",
            "Comm/Fee": "float64"},
    )
    df["Date/Time"] = pd.to_datetime(
        df["Date/Time"], format="%Y-%m-%d, %H:%M:%S", errors="coerce"
    )
    return df


def import_ibkr_stock_transactions(paths: Iterable[str | Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for p in paths:
        path = Path(p).expanduser()
        logging.info("Importing %s", path)
        frames.append(_parse_one_csv(path))
    return pd.concat(frames, ignore_index=True)[KEEP_COLS]


def filter_by_symbol(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Filter trades DataFrame by symbol."""
    return df[df["Symbol"] == symbol]

# === corporate-actions import === #
CA_HEADER_PREFIX  = "Corporate Actions,Header,"
CA_DATA_PREFIX    = "Corporate Actions,Data,Stocks"
CA_KEEP_COLS      = [
    "Currency",
    "Report Date",
    "Date/Time",
    "Description",
    "Quantity",
]  # “Symbol” is added later


def _scan_corporate_actions(path: Path) -> tuple[list[str], list[str]]:
    header: list[str] | None = None
    header_locked = False
    rows: list[str] = []

    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.startswith(CA_HEADER_PREFIX) and not header_locked:
                header = [h.strip() for h in line.rstrip("\n").split(",")]
                continue

            if line.startswith(CA_DATA_PREFIX):  # only “Stocks” lines
                if header is None:
                    raise ValueError(f"{path.name}: CA-data before CA-header")

                fields = next(csv.reader([line]))
                if len(fields) != len(header):
                    logging.warning(
                        "%s: field-count mismatch (expected:%d, actual:%d) – row skipped",
                        path.name, len(header), len(fields)
                    )
                    if not header_locked:
                        raise ValueError(f"{path.name}: CA field-count mismatch")
                    continue

                header_locked = True
                rows.append(line)

    if header is None:
        logging.info("%s: no corporate actions", path.name)
        return [], []

    return header, rows


def _parse_ca_csv(path: Path) -> pd.DataFrame:
    header, rows = _scan_corporate_actions(path)
    if not rows:
        return pd.DataFrame(columns=CA_KEEP_COLS + ["Symbol"])

    buf = io.StringIO()
    buf.write(",".join(header) + "\n")
    buf.writelines(rows)
    buf.seek(0)

    df = pd.read_csv(
        buf,
        header=0,
        usecols=CA_KEEP_COLS,
        thousands=",",
        dtype={"Quantity": "float64"},
    )
    df["Date/Time"] = pd.to_datetime(
        df["Date/Time"], format="%Y-%m-%d, %H:%M:%S", errors="coerce"
    )

    # extract symbol before the first "(" in Description
    df["Symbol"] = df["Description"].str.split("(", n=1).str[0].str.strip()

    # skip CUSIP/ISIN Change records
    df = df[~df["Description"].str.contains("CUSIP/ISIN Change", na=False)]

    return df[CA_KEEP_COLS + ["Symbol"]]


def import_corporate_actions(csv_paths: Iterable[str | Path]) -> pd.DataFrame:
    """Collect corporate-action rows from all CSVs into one DataFrame."""
    frames = [_parse_ca_csv(Path(p).expanduser()) for p in csv_paths]
    return pd.concat(frames, ignore_index=True)[CA_KEEP_COLS + ["Symbol"]]


# === split ratio integer-only extractor ===
_split_rx = re.compile(r'\bSplit\s+(\d+)\s+for\s+(\d+)\b', flags=re.I)

def extract_split_ratio(text: str) -> tuple[int, int]:
    """
    Return (numerator, denominator) from “… Split N for M …”.
    Raises ValueError if pattern is absent or uses non-integers.
    """
    m = _split_rx.search(text or "")
    if not m:
        raise ValueError(f"No integer split ratio found in: {text!r}")
    return int(m.group(1)), int(m.group(2))


def process_corporate_actions(csv_paths: Iterable[str | Path]) -> pd.DataFrame:
    df = import_corporate_actions(csv_paths)
    df[["Numerator", "Denominator"]] = (
        df["Description"]
          .apply(lambda s: pd.Series(extract_split_ratio(s),
                                     index=["Numerator", "Denominator"]))
    )
    return df

# === CLI ===
def _cli() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Import IBKR stock trades")
    p.add_argument("csv", nargs="+", help="CSV file(s) or glob(s)")
    p.add_argument("-s", "--symbol", help="Filter trades by symbol", default=None)
    p.add_argument("-e", "--export-ca", help="Export corporate actions", action="store_true")
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
        df = import_ibkr_stock_transactions(files)
        if args.symbol:
            original_count = len(df)
            df = filter_by_symbol(df, args.symbol)
            logging.info("Filtered trades by symbol '%s': %d of %d trades retained", args.symbol, len(df), original_count)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    logging.info("imported %d trades from %d file(s)", len(df), len(files))
    n = 10
    logging.info("First %d trades:\n%s", n, df.head(n).to_markdown(index=False))
    logging.info("Last %d trades:\n%s", n, df.tail(n).to_markdown(index=False))
    
    # import and print corporate actions
    ca_df = process_corporate_actions(files)
    logging.info("imported %d corporate actions from %d file(s)", len(ca_df), len(files))
    logging.info("Corporate Actions:\n%s", ca_df.to_markdown(index=False))
    
    if args.export_ca:
        out_path = "corporate_actions.csv"
        ca_df.drop("Quantity", axis=1).to_csv(out_path, index=False)
        logging.info("exported corporate actions to %s", out_path)

if __name__ == "__main__":
    main()
