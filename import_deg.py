import math
import numbers
from datetime import datetime
from typing import List

import pandas as pd
from pandas import DataFrame

from transaction import Transaction


FEE_CURRENCY = 'EUR'
TRANSACTION_FEE_COLUMN = 'Transaction and/or third party fees EUR'
AUTO_FX_FEE_COLUMN = 'AutoFX Fee'


def eu_str_to_date(date_string: str) -> datetime:
    return datetime.strptime(date_string, '%d-%m-%Y')


def merge_date_time(date_string: str, time_string: str) -> datetime:
    return datetime.strptime(date_string + ' ' + time_string, '%d-%m-%Y %H:%M')


# Current English: Date,Time,Product,ISIN,Reference exchange,Venue,Quantity,Price,,Local value,,Value EUR,
#   Exchange rate,AutoFX Fee,Transaction and/or third party fees EUR,Total EUR,Order ID
# Old Czech: Datum,Čas,Produkt,ISIN,Reference,Venue,Počet,Cena,,Hodnota v domácí měně,,Hodnota,,Směnný kurz,
#   Transaction and/or third,,Celkem,,ID objednávky

_OLD_TO_NEW_COLUMN_NAMES = {
    'Transaction and/or third': TRANSACTION_FEE_COLUMN,
    'Value': 'Value EUR',
    'Total': 'Total EUR',
    'Reference': 'Reference exchange',
}


def normalize_column_names(df: DataFrame):
    # Detect language, rename all columns to English
    if 'Datum' in df.columns:
        print("Renaming Czech columns to English.")
        df.rename(columns={
            'Datum': 'Date',
            'Čas': 'Time',
            'Produkt': 'Product',
            'Venue': 'Venue',
            'Počet': 'Quantity',
            'Cena': 'Price',
            'Hodnota v domácí měně': 'Local value',
            'Hodnota': 'Value EUR',
            'Směnný kurz': 'Exchange rate',
            'Celkem': 'Total EUR',
            'ID objednávky': 'Order ID'
        }, inplace=True)
    # Normalize old English names to current names (handles old exports)
    df.rename(columns=_OLD_TO_NEW_COLUMN_NAMES, inplace=True)


REQUIRED_COLUMNS = [
    'Date', 'Time', 'Product', 'ISIN', 'Order ID',
    TRANSACTION_FEE_COLUMN, 'Quantity', 'Price',
]


def validate_columns(df: DataFrame, file_name: str):
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(
            f"Column(s) not found in '{file_name}': {missing}\n\n"
            f"Check column names in the input CSV file. Available columns: {list(df.columns)}"
        )


def detect_decimal_separator(file_name: str) -> str:
    """Sniff the decimal separator ('.' or ',') from the data itself.

    The column *names* don't tell us: Degiro uses the same English headers for
    both the comma-decimal locale (e.g. Czech: "57,6000", "-2,00") and the
    period-decimal locale (e.g. Irish: "31.3400", "-2.00", with "," as the
    thousands separator). We read the 'Exchange rate' column, which is always a
    plain ratio (~1.x, never a thousands separator), and look at its punctuation.
    Falls back to 'Price' and finally to '.'.
    """
    sample = pd.read_csv(file_name, encoding="utf8", nrows=50, dtype=str)
    normalize_column_names(sample)
    for col in ('Exchange rate', 'Price'):
        if col not in sample.columns:
            continue
        for value in sample[col].dropna():
            text = str(value).strip()
            has_comma, has_dot = ',' in text, '.' in text
            if has_comma and has_dot:
                # Both present (thousands + decimal): the rightmost is the decimal.
                return ',' if text.rfind(',') > text.rfind('.') else '.'
            if has_comma:
                return ','
            if has_dot:
                return '.'
    return '.'


def import_transactions(file_name: str):
    print(f"Importing Degiro file: {file_name}")

    # The decimal separator depends on the export's locale, not on the column
    # naming, so sniff it from the data. Whichever char is the decimal point, the
    # other one is the thousands separator (e.g. "-8,103.06" / "1.152,00").
    header_cols = pd.read_csv(file_name, encoding="utf8", nrows=0).columns
    is_new_format = TRANSACTION_FEE_COLUMN in header_cols
    decimal_sep = detect_decimal_separator(file_name)
    thousands_sep = '.' if decimal_sep == ',' else ','
    print(f"Detected decimal separator '{decimal_sep}', thousands separator '{thousands_sep}'.")

    df = pd.read_csv(file_name, encoding="utf8", decimal=decimal_sep, thousands=thousands_sep)
    print(df.columns)
    print(df.shape[0])

    pd.set_option('display.max_columns', 12)
    pd.set_option('display.width', 200)

    normalize_column_names(df)
    validate_columns(df, file_name)
    if is_new_format and AUTO_FX_FEE_COLUMN not in df.columns:
        raise ValueError(f"'{AUTO_FX_FEE_COLUMN}' column missing in new-format file '{file_name}'.")

    print(f"Imported transactions before filtering: {df.shape[0]}")

    # To be dropped
    df_nan = df[df['Date'].isnull()]
    if df_nan.shape[0] > 0:
        print(f"*** Dropping {df_nan.shape[0]} records with null/NaN 'Date'. ***")
        print(df_nan)
        df = df.drop(df_nan.index)
        print(f"Transactions after dropping null Date: {df.shape[0]}\n")

    # Drop also stock split transactions
    df_split = df[(df['Order ID'].isnull() & df[TRANSACTION_FEE_COLUMN].isnull())]
    if df_split.shape[0] > 0:
        print(f"*** Dropping {df_split.shape[0]} transactions without Order ID & Fee (stock splits). ***")
        df = df.drop(df_split.index)  # Drop the exact same rows that were identified in df_split
        print(f"Transactions after filtering stock splits: {df.shape[0]}\n")
        print("Dropped transactions:")
        df_to_print = df_split.copy()
        df_to_print['Product'] = df_to_print['Product'].apply(lambda x: (x[:30] + '~') if len(str(x)) > 30 else x)
        columns_to_show = ['Date', 'Time', 'Product', 'ISIN', 'Quantity', 'Price']
        print(df_to_print[columns_to_show], "\n")

    df['DateTime'] = df.apply(lambda row: merge_date_time(row['Date'], row['Time']), axis=1)

    return df


def do_skip_transaction(row: object) -> bool:
    if row['DateTime'].year != 2021:  # These exceptions are intended just for the tax year 2021 (check them otherwise)
        return False

    # Empty order ID usually means some SPAC merger, acquisition, or a move to another exchange
    order_id = row['Order ID']
    if isinstance(order_id, numbers.Real) and math.isnan(order_id):  # Empty values represented as NaN in Pandas
        product = row['Product']
        if product.startswith('NANOXPLORE') \
                or product.startswith('VOYAGER DIGITAL') \
                or product.startswith('VIRTUOSO ACQUISITION') or product.startswith('WEJO') \
                or product.startswith('PEAK FINTECH GROUP') or product.startswith('TENET FINTECH GROUP'):
            return True

    return False


def convert_to_transactions_deg(df_trans: DataFrame, product_isin: str, tax_year: int) -> List[Transaction]:
    df_product = df_trans[df_trans['ISIN'] == product_isin].sort_values('DateTime')
    product_names = df_product['Product'].unique()
    if product_names.size == 0:
        raise ValueError(f"Could not find ISIN: {product_isin}")
    elif product_names.size != 1:
        print("*** Different product names under the ISIN! ***")
        for product in product_names:
            print(product)

    print(f"Filtered {df_product.shape[0]} transaction(s) of product {product_names[0]}, based on ISIN: {product_isin}")

    currency_idx = df_product.columns.get_loc('Price') + 2  # row has one more column ("index") at the beginning
    transactions = []
    total_transaction_fees = 0.0
    total_autofx_fees = 0.0
    for _, row in df_product.reset_index().iterrows():
        if row['DateTime'].year > tax_year:
            break

        if do_skip_transaction(row):
            print(f"!! Skipping transaction: {row['DateTime']}, {row['Product']}, {row['ISIN']}")
            continue

        raw_fee = row[TRANSACTION_FEE_COLUMN]
        fee = 0.0 if pd.isna(raw_fee) else -raw_fee  # Fee is negative in Degiro exports
        if fee < 0:
            raise ValueError("Unexpected negative fee!")
        total_transaction_fees += fee
        if AUTO_FX_FEE_COLUMN in df_product.columns:
            autofx_fee = row[AUTO_FX_FEE_COLUMN]
            if pd.notna(autofx_fee):
                if autofx_fee > 0:
                    raise ValueError(f"Unexpected positive AutoFX Fee: {autofx_fee}")
                total_autofx_fees += -autofx_fee
                fee += -autofx_fee

        transactions.append(Transaction(
            time=row['DateTime'],
            product_name=row['Product'],
            isin=row['ISIN'],
            count=row['Quantity'],
            share_price=row['Price'],  # Local currency
            currency=row.iloc[currency_idx],
            fee=fee,
            fee_currency=FEE_CURRENCY
        ))

    print(
        f"Total {total_transaction_fees:.2f} {FEE_CURRENCY} transaction fees and "
        f"{total_autofx_fees:.2f} {FEE_CURRENCY} AutoFX fees recorded for {product_names[0]}."
    )
    return transactions
