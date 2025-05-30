from decimal import Decimal
import argparse
import os
import json
from pathlib import Path
import pandas as pd
from pandas import DataFrame, Series, read_csv, read_excel, concat as pd_concat
from datetime import datetime
from typing import Dict, List

from import_deg import convert_to_transactions_deg, import_transactions
from import_ibkr import import_ibkr_stock_transactions, import_ibkr_option_transactions
from import_utils import detect_columns
from transaction_ibkr import convert_to_transactions_ibkr
from corporate_action import load_stock_splits, apply_stock_splits_for_product
from optimizer import optimize_product, print_report, calculate_totals, get_product_name, list_strategies
from transaction import SaleRecord, Transaction


def get_unique_product_ids(
    df_trans: DataFrame,
    tax_year: int,
    *,
    id_col: str,
    date_col: str,
    product_col: str,
) -> pd.Series:
    """Return the unique product identifiers (ISIN or Symbol) for *tax_year*, sorted by *product_col*."""
    df = df_trans.copy()
    df["TaxYear"] = df[date_col].dt.year
    df_tax_year = df[df["TaxYear"] == tax_year]
    return df_tax_year.sort_values(product_col)[id_col].unique()


def build_transactions(
    df_trans: DataFrame,
    product_id: str,
    tax_year: int,
    splits_df: DataFrame,
    *,
    id_col: str,
    options: bool,
) -> list[Transaction]:
    """Convert one product's rows to Transaction objects and apply splits."""

    if id_col == "ISIN":
        txs = convert_to_transactions_deg(df_trans, product_id, tax_year)
    else:
        txs = convert_to_transactions_ibkr(df_trans, product_id, tax_year, options=options)

    apply_stock_splits_for_product(txs, splits_df, product_id, id_col=id_col)
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

    return optimize_product(convert_to_transactions_deg(df_trans, product_isin, tax_year), tax_year, strategies)


def build_pairing_rows(report: List[SaleRecord], id_col: str) -> list[dict]:
    """
    Flatten SaleRecord objects into dictionaries suitable for a CSV export.

    Each pairing is identified by a *PairID* and split into two logical sides:
    an **open** transaction (position opening) and a **close** transaction
    (position closing).  Using this neutral terminology future‑proofs the
    export for short selling, where a close might be a *buy*.
    """
    rows: list[dict] = []

    def _id_value(t: Transaction) -> str:
        return t.isin if id_col == "ISIN" else t.product_name

    for idx, sale in enumerate(report):
        close_t = sale.sale_t
        pair_id = f"{close_t.time.isoformat()}_{idx}"

        # Closing side
        rows.append({
            "PairID": pair_id,
            "Side": "close",
            "DateTime": close_t.time,
            "Product": close_t.product_name,
            id_col: _id_value(close_t),
            "Quantity": close_t.count,
            "SplitRatio": close_t.split_ratio,
            "SharePrice": close_t.share_price,
            "Currency": close_t.currency,
            "TimeTestPassed": "--",
            "ProfitPerShare": "--",
        })

        # Opening side(s)
        for br in sale.buys:
            open_t = br.buy_t
            rows.append({
                "PairID": pair_id,
                "Side": "open",
                "DateTime": open_t.time,
                "Product": open_t.product_name,
                id_col: _id_value(open_t),
                "Quantity": br._count_consumed,
                "SplitRatio": open_t.split_ratio,
                "SharePrice": open_t.share_price,
                "Currency": open_t.currency,
                "TimeTestPassed": "T" if br.time_test_passed else "",
                "ProfitPerShare": close_t.share_price - open_t.share_price,
            })
    return rows


def optimize_all(
    df_trans: DataFrame,
    tax_year: int,
    strategies: dict[int, str],
    account_code: str,
    splits_df: DataFrame,
    *,
    enable_bep: bool = False,
    enable_ttest: bool = False,
    options: bool = False,
    symbols_filter_str: str = None,
) -> None:
    id_col, date_col, product_col = detect_columns(df_trans)

    products = get_unique_product_ids(
        df_trans, tax_year, id_col=id_col, date_col=date_col, product_col=product_col
    )
    print(f"Found {len(products)} products with some transactions in {tax_year} to process.")

    if symbols_filter_str:
        selected_symbols = [s.strip() for s in symbols_filter_str.split(',')]
        products = [p for p in products if p in selected_symbols]
        print(f"Processing only specified symbols: {', '.join(selected_symbols)}")
        print(f"Selected {len(products)} products to process.")

    df_results = DataFrame(columns=["Product", id_col, "Status", "Income", "Cost", "Profit", "Fees"])
    total_income = total_cost = total_fees = Decimal(0)
    error_count = 0

    # Collect detailed pairing rows for audit purposes.
    pairing_rows: list[dict] = []

    for pid in products:
        pname = pid
        if id_col == "ISIN":
            pname = df_trans.query(f"ISIN == '{pid}'").iloc[0]["Product"]
            if pid in ("CA88035N1033",):  # skip-list for Degiro ('CA88035N1033' is TENET FINTECH)
                # IE: ('IE00B53SZB19', 'US9344231041'):
                # CZ: ('IE00B53SZB19', 'US9344231041', 'BMG9525W1091', 'CA88035N1033', 'CA92919V4055', 'KYG851581069', 'US37611X1000'):
                print(f"Skipping product {pid}: {pname}")
                continue

        print(f"Processing product {pname}")

        # Initialize variables for current product processing
        report: List[SaleRecord] = []
        current_pairing_rows: list[dict] = []
        income = Decimal(0)
        cost = Decimal(0)
        fees = Decimal(0)
        error_occurred_for_product = False

        try:
            txs = build_transactions(df_trans, pid, tax_year, splits_df, id_col=id_col, options=options)
            report = optimize_product(txs, tax_year, strategies, enable_bep, enable_ttest)

            current_pairing_rows = build_pairing_rows(report, id_col)
            income, cost, fees = calculate_totals(report, tax_year)

            print(f"  Income: {income}, Cost: {cost}, Profit: {income - cost}, Fees: {fees}\n")

        except Exception as e:
            print(f"ERROR processing product {pname}: {e}")
            print(f"  Recording zero income/cost for this product and continuing with others.\n")
            error_occurred_for_product = True
            error_count += 1

        # Accumulate pairing details (will be empty if an error occurred)
        pairing_rows.extend(current_pairing_rows)

        # Construct row for the results DataFrame
        status = "ERROR" 
        if not error_occurred_for_product:
            status = "OK" if report else "No sales"

        row = {
            "Product": pname,
            id_col: pid,
            "Status": status,
            "Income": income,
            "Cost": cost,
            "Profit": income - cost,
            "Fees": fees,
        }
        
        new_row_df = DataFrame([row]) 
        df_results = pd_concat([df_results, new_row_df], ignore_index=True) 

        total_income += income
        total_cost += cost
        total_fees += fees

    print()
    pd.set_option('display.max_rows', None)
    print(df_results)

    # Export aggregated results and detailed pairings to CSV
    output_path = "outputs/"
    os.makedirs(output_path, exist_ok=True)
    bep_suffix = "-bep" if enable_bep else ""
    ttest_suffix = "-ttest" if enable_ttest else ""
    output_filename_suffix = f"{account_code}-{tax_year}-{strategies[tax_year-1]}-{strategies[tax_year]}{bep_suffix}{ttest_suffix}.csv"

    df_results.to_csv(
        f"{output_path}results-{output_filename_suffix}",
        index=False)

    pairings_df = pd.DataFrame(pairing_rows)
    if not pairings_df.empty:
        pairings_df["DateTime"] = pairings_df["DateTime"].astype(str)
        pairings_df.to_csv(
            f"{output_path}pairings-{output_filename_suffix}",
            index=False)
        print(f"Exported {len(pairings_df)} pairing rows.")

    # Round to 2 decimal places
    total_income = Decimal(total_income).quantize(Decimal('0.01'))
    total_cost = Decimal(total_cost).quantize(Decimal('0.01'))
    total_fees = Decimal(total_fees).quantize(Decimal('0.01'))

    print()
    print(f"Pairing strategies: {strategies}")
    if enable_bep:
        print("BEP (break-even price) used for cost calculations.")
    print()
    print(f"Total income: {total_income}")
    print(f"Total cost  : {total_cost}")
    print(f"Total fees  : {total_fees}")

    total_profit = total_income - total_cost - total_fees
    print()
    if error_count > 0:
        print(f"!! Number of products with ERROR status: {error_count} (see above for details)\n")
    print(f"! Profit !  : {(total_income - total_cost):,.2f}, after fees: {total_profit:,.2f}")
    print(f"(tax est.)  : {(total_profit * Decimal('0.15')):,.2f}")


def manual_debug(df_transactions: DataFrame):
    product = "SEA"
    count = calculate_current_count(df_transactions, product)
    print(f"{product} current count: {count}")

    report = filter_and_optimize_product(df_transactions, get_isin(df_transactions, "ROKU"), 2021)
    print(len(report))

    print_report(report)
    income, cost, _ = calculate_totals(report, 2021)
    print(f"income: {income}, cost: {cost}, profit: {income - cost}")

    products = get_unique_product_ids(df_transactions, 2021)
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


def load_strategies(path: Path) -> Dict[int, str]:
    # Load strategies from JSON file
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # JSON keys are strings; convert them back to int
    return {int(year): strategy for year, strategy in data.items()}


def setup_strategies(args) -> Dict[int, str]:
    # Check that only one of the options was selected.
    if sum([bool(args.fifo), bool(args.strategy), bool(args.config)]) > 1:
        raise ValueError("Only one of --fifo, --strategy or --config can be specified")

    if args.fifo or args.strategy:
        if args.strategy and args.strategy not in list_strategies():
            print(f"Available strategies: {list_strategies()}")
            raise ValueError(f"Unknown strategy: {args.strategy}")

        strategies = {args.year: "fifo"} if args.fifo else {args.year: args.strategy}
        strategies[args.year - 1] = 'fifo'  # For the output filename; always fifo for previous years.
        return strategies
    elif args.config:
        print(f"Loading strategies from {args.config}")
        return load_strategies(Path(args.config))
    else:
        return load_strategies(Path("config/strategies.json"))


def main():
    parser = argparse.ArgumentParser(description='Process transactions from Degiro or IBKR')
    parser.add_argument('--deg', action='store_true', help='Use Degiro data')
    parser.add_argument('--ibkr', action='store_true', help='Use IBKR data')
    parser.add_argument('--year', type=int, help='Tax year')
    parser.add_argument('--strategy', type=str, help='Pairing strategy for target year (' + ', '.join(list_strategies()) + '), uses fifo for previous years. Defaults to config/strategies.json if not specified.')
    parser.add_argument('--fifo', action='store_true', help='Shortcut for --strategy fifo')
    parser.add_argument('--config', type=str, help='Path to strategies JSON file, default: config/strategies.json')
    parser.add_argument('--no-split', action='store_true', help='Disable loading and applying stock splits')
    parser.add_argument('--bep', action='store_true', help='Enable break-even prices calculation')
    parser.add_argument('--ttest', action='store_true', help='Skip profit (both income & cost) for sales after 3 years')
    parser.add_argument('-o', '--options', action='store_true', help='Import options trades')
    parser.add_argument('--symbols', type=str, help='Comma-separated list of symbols to process')
    parser.add_argument('files', nargs='+', help='Files to process')
    args = parser.parse_args()

    if not (args.deg or args.ibkr or args.options):
        parser.error('At least one of --deg, --ibkr or --options must be specified')
    if args.deg and args.ibkr:
        parser.error('Only one of --deg or --ibkr can be specified')
    if args.deg and args.options:
        parser.error('Only --ibkr can be used with --options')

    if not args.year:
        args.year = datetime.now().year - 1
        print(f"Using tax year: {args.year}")

    os.chdir(os.path.dirname(__file__))
    account_code = detect_account_code(args)  # Used in output file names.
    if args.deg:
        # Import from one or more Degiro CSV files
        df_list = [import_transactions(f) for f in args.files]
        df_transactions = pd.concat(df_list, ignore_index=True)
    elif args.options:
        # Import options from one or more IBKR CSV files
        df_transactions = import_ibkr_option_transactions(args.files)
    else:
        # Import stocks from one or more IBKR CSV files
        df_transactions = import_ibkr_stock_transactions(args.files)

    # pairing strategies for each tax year
    strategies = setup_strategies(args)

    # load corporate actions (stock splits)
    splits_df = load_stock_splits("config/corporate_actions.csv") if not args.no_split else None

    # *** main processing ***
    optimize_all(
        df_transactions, args.year, strategies, account_code, splits_df,
        enable_bep=args.bep,
        enable_ttest=args.ttest,
        options=args.options,
        symbols_filter_str=args.symbols)

    print()
    print("Processed file(s):", args.files)
    print("Done.")


if __name__ == '__main__':
    main()
