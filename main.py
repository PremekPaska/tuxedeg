# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
from datetime import datetime

import pandas as pd
from pandas import DataFrame


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


def calculate_current_count(transactions: DataFrame, product_prefix: str) -> int:

    df_product = transactions[transactions['Produkt'].str.startswith(product_prefix)]

    print(product_prefix)
    print(df_product.shape[0])

    df_sorted = df_product.sort_values('DateTime').reset_index()
    print(df_sorted.head(5))

    count = 0
    for i, row in df_sorted.iterrows():
        count += row['Počet']

    return count


def main():
    transactions = import_transactions("Transactions.csv")

    count = calculate_current_count(transactions, "ROKU")
    print(f"Roku current count: {count}")


if __name__ == '__main__':
    main()
