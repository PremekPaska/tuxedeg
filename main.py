# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import decimal
from decimal import Decimal
from typing import List

import pandas as pd
from pandas import DataFrame

from import_deg import convert_to_transactions, import_transactions
from optimizer import optimize_transaction_pairing, optimize_product, print_report, calculate_totals


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


def optimize_all(df_trans: DataFrame, tax_year: int) -> decimal:
    products = get_unique_products(df_trans, tax_year)
    print(f"Found {products.shape[0]} products with some transactions in {tax_year}.")

    total_income = Decimal(0)
    total_cost = Decimal(0)
    for product in products:
        print()
        report = filter_and_optimize_product(df_trans, product, tax_year)
        # print_report(report)

        income, cost = calculate_totals(report, tax_year)
        print(f"income: {income}, cost: {cost}, profit: {income - cost}")

        total_income += income
        total_cost += cost

    print(f"\nTotal income: {total_income}")
    print(f"Total cost  : {total_cost}")
    print(f"! Profit !  : {total_income - total_cost}")
    print(f"(tax)       : {(total_income - total_cost) * Decimal('0.15')}")



def get_unique_products(df_trans, tax_year):
    df_products = df_trans
    df_products['TaxYear'] = df_products.apply(lambda row: row['DateTime'].year, axis=1)
    products = df_trans[df_trans['TaxYear'] == tax_year]['Produkt'].unique()
    products.sort()
    return products


def manual_debug(df_transactions: DataFrame):
    df_transactions = import_transactions("Transactions.csv")

    product = "SEA"
    count = calculate_current_count(df_transactions, product)
    print(f"{product} current count: {count}")

    report = filter_and_optimize_product(df_transactions, "ROKU", 2021)
    print(len(report))

    print_report(report)

    income, cost = calculate_totals(report, 2021)
    print(f"income: {income}, cost: {cost}, profit: {income - cost}")


def main():
    df_transactions = import_transactions("Transactions.csv")

    # manual_debug(df_transactions)

    optimize_all(df_transactions, 2021)


if __name__ == '__main__':
    main()
