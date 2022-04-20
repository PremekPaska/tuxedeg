from typing import List

from transaction import Transaction, Buy, Sale


def find_buys_fifo(sale_t: Transaction, trans: List[Transaction]) -> List[Buy]:
    remaining_sold_count = -sale_t.count

    buy_records = []
    for buy_t in [t for t in trans if not t.is_sale and t.remaining_count > 0 and t.time < sale_t.time]:
        count_used = min(remaining_sold_count, buy_t.remaining_count)
        if count_used < 1:
            raise ValueError(f"Unexpected count_used: {count_used}")

        remaining_sold_count -= count_used
        buy_t.consume_shares(count_used)

        buy_records.append(Buy(buy_t, count_used))

        if remaining_sold_count == 0:
            break

    return buy_records


def optimize_product(trans: List[Transaction]) -> List[Sale]:

    report = []
    for sale_t in [t for t in trans if t.is_sale]:
        buy_records = find_buys_fifo(sale_t, trans)
        sale_record = Sale(sale_t, buy_records)
        report.append(sale_record)

    return report