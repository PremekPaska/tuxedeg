from pandas import DataFrame
from typing import List
from transaction import Transaction
from decimal import Decimal
from datetime import datetime

import pandas as pd


def load_stock_splits(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, parse_dates=["Report Date"])
        return df[["Symbol", "ISIN", "Report Date", "Numerator", "Denominator"]]
    except FileNotFoundError:
        raise SystemExit("Stock split file, " + path + " not found.")


def apply_stock_splits_for_product(
    tx_list: List[Transaction],
    splits_df: DataFrame,
    product_id: str,
    *,
    id_col: str,
) -> None:
    """Mutates *tx_list* in-place, adjusting quantities and prices."""
    if not tx_list:
        return
    
    if splits_df is None or splits_df.empty:
        print("Skipping stock split application.")
        return

    first_tx_time = min(t.time for t in tx_list if t.isin == product_id)

    s = (
        splits_df[splits_df[id_col] == product_id]
        .copy()
        .assign(ts=lambda d: pd.to_datetime(d["Report Date"]))
        .query("ts > @first_tx_time")
        .sort_values("ts")
    )

    # Collapse duplicates for the same ISIN and Date/Time
    # there can be duplicate records because multiple symbols (TESLA, TL0) map to the same ISIN
    if id_col == "ISIN":
        s = s.drop_duplicates(subset=[id_col, "Report Date"])

    # Check that we have multiple splits for TSLA
    if (product_id == "TSLA" or product_id == "US88160R1014"):
        if (first_tx_time.date() < datetime(2022, 8, 25).date() and len(s) < 1) \
            or (first_tx_time.date() < datetime(2020, 8, 31).date() and len(s) < 2):
            print("! Heads up ! Potentially missing stock split data for %s" % (product_id))
            print("  First transaction time: %s (last split 2022-08-25)" % first_tx_time)
            raise ValueError("Missing stock split data for %s" % (product_id))

    for _, split in s.iterrows():
        print("Applying stock split %d:%d, product id %s, cut off %s"
              % (split["Numerator"], split["Denominator"], product_id, split["ts"]))

        numerator, denominator = int(split["Numerator"]), int(split["Denominator"])
        cut_off = split["ts"]
        for tx in tx_list:
            if tx.isin == product_id and tx.time.date() < cut_off.date():
                tx.apply_split(numerator, denominator)
