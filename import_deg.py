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


# English: Date,Time,Product,ISIN,Reference,Venue,Quantity,Price,,Local value,,Value,,Exchange rate,
#   Transaction and/or third,,Total,,Order ID
# Czech: Datum,Čas,Produkt,ISIN,Reference,Venue,Počet,Cena,,Hodnota v domácí měně,,Hodnota,,Směnný kurz,
#   Transaction and/or third,,Celkem,,ID objednávky
def rename_columns_to_english(df: DataFrame):
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
            'Hodnota': 'Value',
            'Směnný kurz': 'Exchange rate',
            'Celkem': 'Total',
            'ID objednávky': 'Order ID'
        }, inplace=True)


def import_transactions(file_name: str):
    df = pd.read_csv(file_name, encoding="utf8")
    print(df.columns)
    print(df.shape[0])
    # print(df.dtypes)
    # print(df.head())

    pd.set_option('display.max_columns', 12)
    pd.set_option('display.width', 200)

    rename_columns_to_english(df)

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


def get_unique_product_ids(df_trans, tax_year):
    df_products = df_trans
    df_products['TaxYear'] = df_products.apply(lambda row: row['DateTime'].year, axis=1)
    df_tax_year_products = df_products[df_products['TaxYear'] == tax_year].sort_values('Product')
    product_ids = df_tax_year_products['ISIN'].unique()
    return product_ids


def get_isin(transactions: DataFrame, product_prefix: str) -> str:
    df_product = transactions[transactions['Product'].str.startswith(product_prefix)]
    if df_product.shape[0] == 0:
        raise ValueError(f"Didn't find product with prefix {product_prefix}")
    return df_product.iloc[0]['ISIN']
