import os
import decimal
from decimal import Decimal
import argparse
import os

import pandas as pd
from pandas import DataFrame

from import_deg import convert_to_transactions, import_transactions, get_unique_product_ids_old, get_isin
from import_ibkr import import_ibkr_stock_transactions
from transaction_ibkr import convert_to_transactions_ibkr
from corporate_action import apply_stock_splits_for_symbol
from optimizer import optimize_product, print_report, calculate_totals, get_product_name
from transaction import SaleRecord, Transaction

def get_unique_product_ids(
    df_trans: DataFrame,
    tax_year: int,
    *,
    id_col: str,
    date_col: str,
) -> pd.Series:
    """Return the unique product identifiers (ISIN or Symbol) for *tax_year*."""
    df = df_trans.copy()
    df["TaxYear"] = df[date_col].dt.year
    return df.loc[df["TaxYear"] == tax_year, id_col].unique()


def get_product_id_by_prefix(
    df_trans: DataFrame,
    prefix: str,
    *,
    id_col: str,
) -> str:
    col = "Product" if "Product" in df_trans.columns else id_col
    df = df_trans[df[col].str.startswith(prefix)]
    if df.empty:
        raise ValueError(f"No product starting with {prefix!r}")
    return df.iloc[0][id_col]


def _detect_id_and_date_cols(df: DataFrame) -> tuple[str, str]:
    """Return (id_col, date_col) for the given frame."""
    if "ISIN" in df.columns:
        return "ISIN", "DateTime"
    if "Symbol" in df.columns:
        return "Symbol", "Date/Time"
    raise ValueError("Unknown dataframe format: no ISIN or Symbol column")


def load_stock_splits(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, parse_dates=["Date/Time"])
        return df[["Symbol", "Date/Time", "Numerator", "Denominator"]]
    except FileNotFoundError:
        print("No stock_splits.csv – split adjustment skipped.")
        return pd.DataFrame(columns=["Symbol", "Date/Time", "Numerator", "Denominator"])


def build_transactions(
    df_trans: DataFrame,
    product_id: str,
    tax_year: int,
    splits_df: DataFrame,
    *,
    id_col: str,
) -> list[Transaction]:
    """Convert one product’s rows to Transaction objects and apply splits."""

    if id_col == "ISIN":
        txs = convert_to_transactions(df_trans, product_id, tax_year)
        return txs                                    # Degiro – nothing to scale

    txs = convert_to_transactions_ibkr(df_trans, product_id, tax_year)
    apply_stock_splits_for_symbol(txs, splits_df, product_id)
    return txs


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


def optimize_all_old(df_trans: DataFrame, tax_year: int, strategies: dict[int,str], account_code: str) -> decimal:
    products = get_unique_product_ids_old(df_trans, tax_year)
    print(f"Found {products.shape[0]} products with some transactions in {tax_year}.")

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


def optimize_all(
    df_trans: DataFrame,
    tax_year: int,
    strategies: dict[int, str],
    account_code: str,
    splits_df: DataFrame,
) -> decimal:
    id_col, date_col = _detect_id_and_date_cols(df_trans)

    products = get_unique_product_ids(
        df_trans, tax_year, id_col=id_col, date_col=date_col
    )
    print(f"Found {len(products)} products with some transactions in {tax_year}.")

    df_results = DataFrame(columns=["Product", id_col, "Income", "Cost", "Profit", "Fees"])
    total_income = total_cost = total_fees = Decimal(0)

    for pid in products:
        if id_col == "ISIN" and pid in ("CA88035N1033",):  # skip-list stays Degiro-only
            pname = df_trans.query(f"ISIN == '{pid}'").iloc[0]["Product"]
            print(f"Skipping product {pid}: {pname}")
            continue
        elif id_col == "Symbol" and pid in ("CNDX", "CSPX", "VOW3d", "AMD", "CRWD", "NVDA", "PLTR", "TM"):
            print(f"Skipping product {pid}, shorting not (yet) supported.")
            continue

        txs = build_transactions(df_trans, pid, tax_year, splits_df, id_col=id_col)
        report = optimize_product(txs, tax_year, strategies)

        income, cost, fees = calculate_totals(report, tax_year)
        print(f"income: {income}, cost: {cost}, profit: {income - cost}, fees: {fees}")

        row = {
            "Product": get_product_name(report),   # = symbol for IBKR
            id_col: pid,
            "Income": income,
            "Cost": cost,
            "Profit": income - cost,
            "Fees": fees,
        }
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


def detect_account_code(args) -> str:
    # Determine account code based on flags and filename
    if args.ibkr:
        code = "ibkr"
    else:
        file_name = os.path.basename(args.files[0]).lower()
        if "cz" in file_name:
            code = "cz"
        elif "ie" in file_name:
            code = "ie"
        else:
            code = "deg"
    print(f"Using account code: {code}")
    return code


def main():
    parser = argparse.ArgumentParser(description='Process transactions from Degiro or IBKR')
    parser.add_argument('--deg', action='store_true', help='Use Degiro data')
    parser.add_argument('--ibkr', action='store_true', help='Use IBKR data')
    parser.add_argument('files', nargs='+', help='Files to process')
    args = parser.parse_args()

    if not (args.deg or args.ibkr):
        parser.error('At least one of --deg or --ibkr must be specified')
    if args.deg and args.ibkr:
        parser.error('Only one of --deg or --ibkr can be specified')

    os.chdir(os.path.dirname(__file__))
    account_code = detect_account_code(args)  # Used in output file names.
    if args.deg:
        # Import from one or more Degiro CSV files
        df_list = [import_transactions(f) for f in args.files]
        df_transactions = pd.concat(df_list, ignore_index=True)
    else:
        # Import from one or more IBKR CSV files
        df_transactions = import_ibkr_stock_transactions(args.files)

    # manual_debug(df_transactions)

    # pairing strategies for each tax year
    strategies = {
        2021: 'max_cost',
        2022: 'min_cost',
        2023: 'min_cost',
        2024: 'max_cost'
    }

    # TODO: corporate actions for Degiro; unify the code; detect tax year automatically
    if args.ibkr:
        splits_df = load_stock_splits("config/corporate_actions.csv")             # default path; can be empty
        optimize_all(df_transactions, 2024, strategies, account_code, splits_df)
    else:
        optimize_all_old(df_transactions, 2024, strategies, account_code)


if __name__ == '__main__':
    main()
