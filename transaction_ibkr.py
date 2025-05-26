from transaction import Transaction
from pandas import DataFrame
from typing import List

def convert_to_transactions_ibkr(
    df_trans: DataFrame,
    symbol: str,
    tax_year: int,
    *,
    options: bool,
) -> List[Transaction]:
    df_sym = (
        df_trans[df_trans["Symbol"] == symbol]
        .sort_values("Date/Time")
        .reset_index(drop=True)
    )

    print(f"Filtered {len(df_sym)} transaction(s) for symbol: {symbol}")

    txs: List[Transaction] = []
    for _, row in df_sym.iterrows():
        # stop when past year
        if row["Date/Time"].year > tax_year:
            break

        fee = -row["Comm/Fee"]
        if fee < 0:
            raise ValueError("Unexpected negative fee!")

        txs.append(Transaction(
            time=row["Date/Time"],
            product_name=symbol,  # For now use symbol as product name
            isin=symbol,          # For now use symbol as ISIN
            count=row["Quantity"],
            share_price=row["T. Price"],
            currency=row["Currency"],
            fee=fee,
            fee_currency=row["Currency"],
            option_contract=options,
        ))

    return txs
