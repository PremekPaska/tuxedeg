import math
import numbers
from datetime import datetime
from typing import List

import pandas as pd
from pandas import DataFrame

from transaction import Transaction


def eu_str_to_date(date_string: str) -> datetime:
    return datetime.strptime(date_string, '%d-%m-%Y')


def merge_date_time(date_string: str, time_string: str) -> datetime:
    return datetime.strptime(date_string + ' ' + time_string, '%d-%m-%Y %H:%M')


def import_transactions(file_name: str):
    df = pd.read_csv(file_name, encoding="utf8")
    print(df.columns)
    print(df.shape[0])
    # print(df.dtypes)
    # print(df.head())

    pd.set_option('display.max_columns', 12)
    pd.set_option('display.width', 200)

    # To be dropped
    df_nan = df[df['Date'].isnull()]
    print(f"*** Dropping {df_nan.shape[0]} records with null/NaN 'Date'. ***")
    print(df_nan)
    df = df[df['Date'].notnull()]

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


# maybe take ISIN as product selector
def convert_to_transactions(df_trans: DataFrame, product_isin: str, tax_year: int) -> List[Transaction]:
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
    fee_curr_idx = df_product.columns.get_loc('Transaction and/or third') + 2
    transactions = []
    for _, row in df_product.reset_index().iterrows():
        if row['DateTime'].year > tax_year:
            break

        if do_skip_transaction(row):
            print(f"!! Skipping transaction: {row['DateTime']}, {row['Product']}, {row['ISIN']}")
            continue

        if row[fee_curr_idx] != 'EUR' and not math.isnan(row[fee_curr_idx]):
            raise ValueError("Unexpected fee currency!")

        transactions.append(Transaction(
            time=row['DateTime'],
            product=row['Product'],
            isin=row['ISIN'],
            count=row['Quantity'],
            share_price=row['Price'],  # Local currency
            currency=row[currency_idx],
            fee_eur=row['Transaction and/or third']
        ))

    return transactions
