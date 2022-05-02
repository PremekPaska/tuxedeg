import math
from datetime import datetime
from typing import List

import pandas as pd
from pandas import DataFrame

from transaction import Transaction, SaleRecord, BuyRecord


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
    df_nan = df[df['Datum'].isnull()]
    print(f"*** Dropping {df_nan.shape[0]} records with null/NaN 'Datum'. ***")
    print(df_nan)
    df = df[df['Datum'].notnull()]

    df['DateTime'] = df.apply(lambda row: merge_date_time(row['Datum'], row['Čas']), axis=1)

    return df


# maybe take ISIN as product selector
def convert_to_transactions(df_trans: DataFrame, product_isin: str, tax_year: int) -> List[Transaction]:
    df_product = df_trans[df_trans['ISIN'] == product_isin].sort_values('DateTime')
    product_names = df_product['Produkt'].unique()
    if product_names.size == 0:
        raise ValueError(f"Could not find ISIN: {product_isin}")
    elif product_names.size != 1:
        print("*** Different product names under the ISIN! ***")
        for product in product_names:
            print(product)

    print(f"Filtered {df_product.shape[0]} transaction(s) of product {product_names[0]}, based on ISIN: {product_isin}")

    currency_idx = df_product.columns.get_loc('Cena') + 2  # row has one more column ("index") at the beginning
    fee_curr_idx = df_product.columns.get_loc('Transaction and/or third') + 2
    transactions = []
    for _, row in df_product.reset_index().iterrows():
        if row['DateTime'].year > tax_year:
            break
        if row[fee_curr_idx] != 'EUR' and not math.isnan(row[fee_curr_idx]):
            raise ValueError("Unexpected fee currency!")
        transactions.append(Transaction(
            time=row['DateTime'],
            product=row['Produkt'],
            isin=row['ISIN'],
            count=row['Počet'],
            share_price=row['Cena'],  # Local currency
            currency=row[currency_idx],
            fee_eur=row['Transaction and/or third']
        ))

    return transactions
