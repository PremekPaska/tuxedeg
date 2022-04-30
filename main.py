# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
from typing import List

import pandas as pd
from pandas import DataFrame

from import_deg import convert_to_transactions, import_transactions
from optimizer import optimize_transaction_pairing, optimize_product, print_report


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


def filter_and_optimize_product(df_trans: DataFrame, product_prefix: str, tax_year: int):

    return optimize_product(convert_to_transactions(df_trans, product_prefix, tax_year), tax_year)


def main():
    df_transactions = import_transactions("Transactions.csv")

    product = "SEA"
    count = calculate_current_count(df_transactions, product)
    print(f"{product} current count: {count}")

    report = filter_and_optimize_product(df_transactions, "ROKU", 2021)
    print(len(report))

    print_report(report)


if __name__ == '__main__':
    main()
