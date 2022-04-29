from decimal import Decimal
from typing import List

from transaction import Transaction, BuyRecord, SaleRecord


def find_buys_fifo(sale_t: Transaction, trans: List[Transaction]) -> List[BuyRecord]:
    remaining_sold_count = -sale_t.count

    buy_records = []
    for buy_t in [t for t in trans if not t.is_sale and t.remaining_count > 0 and t.time < sale_t.time]:
        count_used = min(remaining_sold_count, buy_t.remaining_count)
        if count_used < 1:
            raise ValueError(f"Unexpected count_used: {count_used}")

        remaining_sold_count -= count_used
        buy_t.consume_shares(count_used)

        buy_records.append(BuyRecord(buy_t, count_used))

        if remaining_sold_count == 0:
            break

    return buy_records


def optimize_transaction_pairing(trans: List[Transaction]) -> List[SaleRecord]:
    sale_records = []
    for sale_t in [t for t in trans if t.is_sale]:
        buy_records = find_buys_fifo(sale_t, trans)
        sale_record = SaleRecord(sale_t, buy_records)
        sale_records.append(sale_record)

    return sale_records


def calculate_tax(sale_records: List[SaleRecord], tax_year: int):
    for sale in [sale for sale in sale_records if sale.sale_t.time.year == tax_year]:
        sale.calculate_profit()


def optimize_product(trans: List[Transaction], tax_year: int) -> List[SaleRecord]:
    sale_records = optimize_transaction_pairing(trans)
    calculate_tax(sale_records, tax_year)

    return sale_records


def print_report(sale_records: List[SaleRecord], tax_year: int = 2021):
    total_income = 0
    total_cost = 0
#    for sale in [sale for sale in sale_records if sale.sale_t.time.year == tax_year]:
    for sale in sale_records:
        print(sale.sale_t)

        for buy_record in sale.buys:
            print(f"-  {buy_record.buy_t}, consumed: {buy_record.count_consumed}")

        if sale.income_tc is None:
            continue

        print(f"  income: {sale.income_tc}")
        print(f"    cost: {sale.cost_tc}")
        print(f"  profit: {sale.profit_tc}")

        total_income += sale.income_tc
        total_cost += sale.cost_tc

    print(f"*** total income: {total_income}")
    print(f"***   total cost: {total_cost}")
    print(f"*** total profit: {total_income - total_cost}")
