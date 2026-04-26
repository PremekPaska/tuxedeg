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
            print(f"Warning: Negative fee: {fee}, Symbol: {symbol}, Date/Time: {row['Date/Time']}, Price: {row['T. Price']}")
            # raise ValueError("Unexpected negative fee!")

        code = row["Code"] if "Code" in row else ""
        code_tokens = str(code).split(";") if code is not None else []
        expired_worthless = "Ep" in code_tokens

        tx = Transaction(
            time=row["Date/Time"],
            product_name=symbol,  # For now use symbol as product name
            isin=symbol,          # For now use symbol as ISIN
            count=row["Quantity"],
            share_price=row["T. Price"],
            currency=row["Currency"],
            fee=fee,
            fee_currency=row["Currency"],
            option_contract=options,
            expired_worthless=expired_worthless,
        )
        txs.append(tx)

        if expired_worthless and tx.is_sale:
            print(f"  EXPIRED LONG OPTION: {symbol}, {row['Date/Time']}, qty={tx.count}, price={tx.share_price}")

    return txs
