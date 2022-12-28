# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import decimal
from decimal import Decimal
from typing import List

import pandas as pd
from pandas import DataFrame

from import_deg import convert_to_transactions, import_transactions
from optimizer import optimize_product, print_report, calculate_totals


def calculate_current_count(transactions: DataFrame, product_prefix: str) -> int:
    df_product = transactions[transactions['Product'].str.startswith(product_prefix)]

    print(product_prefix)
    print(df_product.shape[0])

    df_sorted = df_product.sort_values('DateTime').reset_index()
    print(df_sorted.head(5))

    count = 0
    for i, row in df_sorted.iterrows():
        count += row['Quantity']

    return count


def filter_and_optimize_product(df_trans: DataFrame, product_prefix: str, tax_year: int):

    return optimize_product(convert_to_transactions(df_trans, product_prefix, tax_year), tax_year)


def optimize_all(df_trans: DataFrame, tax_year: int) -> decimal:
    products = get_unique_product_ids(df_trans, tax_year)
    print(f"Found {products.shape[0]} products with some transactions in {tax_year}.")

    total_income = Decimal(0)
    total_cost = Decimal(0)
    total_fees = Decimal(0)
    for product in products:
        print()
        if product in ('IE00B53SZB19', 'US9344231041'):
            print(f"Skipping {product}")
            continue
        report = filter_and_optimize_product(df_trans, product, tax_year)
        # print_report(report)

        income, cost, fees = calculate_totals(report, tax_year)
        print(f"income: {income}, cost: {cost}, profit: {income - cost}, fees: {fees}")

        total_income += income
        total_cost += cost
        total_fees += fees

    print()
    print(f"Total income: {total_income}")
    print(f"Total cost  : {total_cost}")
    print(f"Total fees  : {total_fees}")

    total_profit = total_income - total_cost - total_fees
    print(f"! Profit !  : {total_income - total_cost}, after fees: {total_profit}")
    print(f"(tax est.)  : {total_profit * Decimal('0.15')}")


def get_unique_product_ids(df_trans, tax_year):
    df_products = df_trans
    df_products['TaxYear'] = df_products.apply(lambda row: row['DateTime'].year, axis=1)
    product_ids = df_trans[df_trans['TaxYear'] == tax_year]['ISIN'].unique()
    product_ids.sort()
    return product_ids


def get_isin(transactions: DataFrame, product_prefix: str) -> str:
    df_product = transactions[transactions['Product'].str.startswith(product_prefix)]
    if df_product.shape[0] == 0:
        raise ValueError(f"Didn't find product with prefix {product_prefix}")
    return df_product.iloc[0]['ISIN']


def manual_debug(df_transactions: DataFrame):
    product = "SEA"
    count = calculate_current_count(df_transactions, product)
    print(f"{product} current count: {count}")

    report = filter_and_optimize_product(df_transactions, get_isin(df_transactions, "ROKU"), 2021)
    print(len(report))

    print_report(report)
    income, cost, fees = calculate_totals(report, 2021)
    print(f"income: {income}, cost: {cost}, profit: {income - cost}")

    products = get_unique_product_ids(df_transactions, 2021)
    # print(products)
    print(f"Found {products.shape[0]} unique ISINs.")


def main():
    df_transactions = import_transactions("data/deg1-en.csv")

    # manual_debug(df_transactions)

    optimize_all(df_transactions, 2022)


if __name__ == '__main__':
    main()
