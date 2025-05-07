import pandas as pd
from pandas import DataFrame


def get_product_id_by_prefix(
    df_trans: DataFrame,
    prefix: str,
    *,
    id_col: str,
) -> str:
    product_col = "Product" if "Product" in df_trans.columns else id_col
    df = df_trans[df_trans[product_col].str.startswith(prefix)]
    if df.empty:
        raise ValueError(f"No product starting with {prefix!r}")
    return df.iloc[0][id_col]


def detect_columns(df: DataFrame) -> tuple[str, str, str]:
    if "ISIN" in df.columns:
        return "ISIN", "DateTime", "Product"
    if "Symbol" in df.columns:
        return "Symbol", "Date/Time", "Symbol"
    raise ValueError("Unknown dataframe format: no ISIN or Symbol column")