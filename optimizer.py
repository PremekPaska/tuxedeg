import decimal
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

    if remaining_sold_count != 0:
        raise ValueError("Could not pair transactions!")

    return buy_records


def find_buys_lifo(sale_t: Transaction, trans: List[Transaction]) -> List[BuyRecord]:
    remaining_sold_count = -sale_t.count

    buy_records = []
    for buy_t in reversed([t for t in trans if not t.is_sale and t.remaining_count > 0 and t.time < sale_t.time]):
        count_used = min(remaining_sold_count, buy_t.remaining_count)
        if count_used < 1:
            raise ValueError(f"Unexpected count_used: {count_used}")

        remaining_sold_count -= count_used
        buy_t.consume_shares(count_used)

        buy_records.append(BuyRecord(buy_t, count_used))

        if remaining_sold_count == 0:
            break

    if remaining_sold_count != 0:
        raise ValueError("Could not pair transactions!")

    return buy_records


def find_buys_max_cost(sale_t: Transaction, trans: List[Transaction]) -> List[BuyRecord]:
    remaining_sold_count = -sale_t.count

    buy_records = []
    while remaining_sold_count > 0:
        buy_t = None
        max_price = Decimal(0)
        # TODO: this is slow and dumb (but works!)
        for t in reversed([t for t in trans if not t.is_sale and t.remaining_count > 0 and t.time < sale_t.time]):
            if t.share_price > max_price * Decimal('1.15'):  # TODO: check this param, only apply with time diff > T?
                max_price = t.share_price
                buy_t = t
        if buy_t is None:
            raise ValueError("No buy transaction found!")

        count_used = min(remaining_sold_count, buy_t.remaining_count)
        if count_used < 1:
            raise ValueError(f"Unexpected count_used: {count_used}")

        remaining_sold_count -= count_used
        buy_t.consume_shares(count_used)

        buy_records.append(BuyRecord(buy_t, count_used))

        if remaining_sold_count == 0:
            break

    if remaining_sold_count != 0:
        raise ValueError("Could not pair transactions!")

    return buy_records


def optimize_transaction_pairing(trans: List[Transaction], tax_year: int) -> List[SaleRecord]:
    sale_records = []
    for sale_t in [t for t in trans if t.is_sale]:
        buy_records = find_buys_fifo(sale_t, trans) if sale_t.time.year < tax_year else \
                      find_buys_max_cost(sale_t, trans)
        sale_record = SaleRecord(sale_t, buy_records)
        sale_records.append(sale_record)

    return sale_records


def calculate_tax(sale_records: List[SaleRecord], tax_year: int):
    for sale in [sale for sale in sale_records if sale.sale_t.time.year == tax_year]:
        sale.calculate_profit()


def optimize_product(trans: List[Transaction], tax_year: int) -> List[SaleRecord]:
    sale_records = optimize_transaction_pairing(trans, tax_year)
    calculate_tax(sale_records, tax_year)

    return sale_records


def calculate_totals(sale_records: List[SaleRecord], tax_year: int) -> (decimal, decimal):
    total_income = Decimal(0)
    total_cost = Decimal(0)

    for sale in [s for s in sale_records if s.sale_t.time.year == tax_year]:
        total_income += sale.income_tc
        total_cost += sale.cost_tc

    return total_income, total_cost


def print_report(sale_records: List[SaleRecord]):
    total_income = Decimal(0)
    total_cost = Decimal(0)
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
