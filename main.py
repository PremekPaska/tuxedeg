import os
import decimal
from decimal import Decimal

import pandas as pd
from pandas import DataFrame

from import_deg import convert_to_transactions, import_transactions, get_unique_product_ids, get_isin
from optimizer import optimize_product, print_report, calculate_totals, get_product_name
from transaction import SaleRecord


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


def filter_and_optimize_product(df_trans: DataFrame, product_isin: str, tax_year: int,
                                strategies: dict[int,str] = None) -> list[SaleRecord]:

    return optimize_product(convert_to_transactions(df_trans, product_isin, tax_year), tax_year, strategies)


def optimize_all(df_trans: DataFrame, tax_year: int, strategies: dict[int,str], account_code: str) -> decimal:
    products = get_unique_product_ids(df_trans, tax_year)
    print(f"Found {products.shape[0]} products with some transactions in {tax_year}.")

    # Create new dataframe with products and their income, cost, profit, and fees
    df_results = DataFrame(columns=['Product', 'ISIN', 'Income', 'Cost', 'Profit', 'Fees'])

    total_income = Decimal(0)
    total_cost = Decimal(0)
    total_fees = Decimal(0)
    for product_isin in products:
        print()
        if product_isin in ('CA88035N1033'):
            # IE: ('IE00B53SZB19', 'US9344231041'):
            # CZ: ('IE00B53SZB19', 'US9344231041', 'BMG9525W1091', 'CA88035N1033', 'CA92919V4055', 'KYG851581069', 'US37611X1000'):
            # 'CA88035N1033' is TENET FINTECH
            product_name = df_trans.query(f"ISIN == '{product_isin}'").head(1)['Product'].iloc[0]
            print(f"Skipping product {product_isin}: {product_name}")
            continue
        report = filter_and_optimize_product(df_trans, product_isin, tax_year, strategies)
        # print_report(report)

        income, cost, fees = calculate_totals(report, tax_year)
        print(f"income: {income}, cost: {cost}, profit: {income - cost}, fees: {fees}")

        # Add to dataframe
        row = {'Product': get_product_name(report), 'ISIN': product_isin, 'Income': income, 'Cost': cost,
               'Profit': income - cost, 'Fees': fees}
        df_results = pd.concat([df_results, DataFrame(row, index=[0])], ignore_index=True)

        total_income += income
        total_cost += cost
        total_fees += fees

    print()
    print(df_results)

    # Export df_results to CSV
    output_path = f"outputs/"
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    df_results.to_csv(
        f"{output_path}results-{account_code}-{tax_year}-{strategies[tax_year-1]}-{strategies[tax_year]}.csv",
        index=False)

    print()
    print(f"Pairing strategies: {strategies}")
    print()
    print(f"Total income: {total_income}")
    print(f"Total cost  : {total_cost}")
    print(f"Total fees  : {total_fees}")

    total_profit = total_income - total_cost - total_fees
    print(f"! Profit !  : {total_income - total_cost}, after fees: {total_profit}")
    print(f"(tax est.)  : {total_profit * Decimal('0.15')}")


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
    os.chdir(os.path.dirname(__file__))
    account_code = "cz"
    df_transactions = import_transactions(f"data/Transactions-{account_code}-to-12-2023-adj.csv")

    # manual_debug(df_transactions)

    # pairing strategies for each tax year
    strategies = {
        2021: 'max_cost',
        2022: 'min_cost',
        2023: 'min_cost'
    }

    optimize_all(df_transactions, 2023, strategies, account_code)


if __name__ == '__main__':
    main()
