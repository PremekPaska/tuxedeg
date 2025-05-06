from pandas import DataFrame
from typing import List
from transaction import Transaction
from decimal import Decimal

import pandas as pd


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

    first_tx_time = min(t.time for t in tx_list if t.isin == product_id)

    s = (
        splits_df[splits_df[id_col] == product_id]
        .copy()
        .assign(ts=lambda d: pd.to_datetime(d["Date/Time"]))
        .query("ts >= @first_tx_time")
        .sort_values("ts")
    )

    for _, split in s.iterrows():
        numerator, denominator = int(split["Numerator"]), int(split["Denominator"])
        cut_off = split["ts"]
        for tx in tx_list:
            if tx.isin == product_id and tx.time < cut_off:
                tx.apply_split(numerator, denominator)
