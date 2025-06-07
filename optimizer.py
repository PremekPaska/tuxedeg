import decimal
from decimal import Decimal
from typing import List, Callable, Dict
from collections import deque
from dataclasses import dataclass

from transaction import Transaction, BuyRecord, SaleRecord


def list_strategies() -> List[str]:
    return ["fifo", "lifo", "max_cost", "min_cost"]


def find_buys_fifo(sale_t: Transaction, trans: List[Transaction]) -> List[BuyRecord]:
    remaining_sold_count = -sale_t.count

    buy_records = []
    for buy_t in [t for t in trans if not t.is_sale and t.remaining_count > 0 and t.time < sale_t.time]:
        remaining_sold_count = add_buy_record(buy_records, buy_t, remaining_sold_count)
        if remaining_sold_count == 0:
            break

    if remaining_sold_count != 0:
        print(f"Still remaining sold count to pair: {remaining_sold_count} for {sale_t}")
        raise ValueError("Could not pair transactions!")

    return buy_records


def find_buys_lifo(sale_t: Transaction, trans: List[Transaction]) -> List[BuyRecord]:
    remaining_sold_count = -sale_t.count

    buy_records = []
    for buy_t in reversed([t for t in trans if not t.is_sale and t.remaining_count > 0 and t.time < sale_t.time]):
        remaining_sold_count = add_buy_record(buy_records, buy_t, remaining_sold_count)
        if remaining_sold_count == 0:
            break

    if remaining_sold_count != 0:
        raise ValueError("Could not pair transactions!")

    return buy_records


def is_better_cost_pair(buy_t: Transaction, t: Transaction) -> bool:
    if buy_t is None:
        return True
    day_diff = abs((buy_t.time - t.time).days)
    return (day_diff < 20 and t.share_price > buy_t.share_price * Decimal('1.02')) \
        or (day_diff < 75 and t.share_price > buy_t.share_price * Decimal('1.08')) \
        or t.share_price > buy_t.share_price * Decimal('1.15')


def is_lower_cost_pair_orig(buy_t: Transaction, t: Transaction) -> bool:
    if buy_t is None:
        return True
    day_diff = abs((buy_t.time - t.time).days)
    return (day_diff < 20 and t.share_price < buy_t.share_price * Decimal('0.97')) \
        or (day_diff < 75 and t.share_price < buy_t.share_price * Decimal('0.90')) \
        or t.share_price < buy_t.share_price * Decimal('0.75')


# This version of min_cost eats much less shares eligible for ttest
def is_lower_cost_pair(buy_t: Transaction, t: Transaction) -> bool:
    if buy_t is None:
        return True
    day_diff = abs((buy_t.time - t.time).days)
    return (day_diff < 20 and t.share_price < buy_t.share_price * Decimal('0.97')) \
        or (day_diff < 75 and t.share_price < buy_t.share_price * Decimal('0.75')) \
        or t.share_price < buy_t.share_price * Decimal('0.085')


# Take cost function as a parameter.
def find_buys_generic_lifo(sale_t: Transaction, trans: List[Transaction],
                           is_better_pair: Callable[[Transaction, Transaction], bool]) -> List[BuyRecord]:
    remaining_sold_count = -sale_t.count

    buy_records = []
    while remaining_sold_count > 0:
        buy_t = None
        for t in reversed([t for t in trans if not t.is_sale and t.remaining_count > 0 and t.time < sale_t.time]):
            if is_better_pair(buy_t, t):
                buy_t = t

        if buy_t is None:
            print(f"Could not find a buy transaction for {sale_t}")
            raise ValueError("Could not pair transactions!")

        remaining_sold_count = add_buy_record(buy_records, buy_t, remaining_sold_count)
        if remaining_sold_count == 0:
            break

    if remaining_sold_count != 0:
        raise ValueError("Could not pair transactions!")

    return buy_records


def find_buys_max_cost(sale_t: Transaction, trans: List[Transaction]) -> List[BuyRecord]:
    return find_buys_generic_lifo(sale_t, trans, is_better_cost_pair)


def find_buys_min_cost(sale_t: Transaction, trans: List[Transaction]) -> List[BuyRecord]:
    return find_buys_generic_lifo(sale_t, trans, is_lower_cost_pair)


def add_buy_record(buy_records, buy_t, remaining_sold_count):
    if buy_t is None:
        raise ValueError("No buy transaction found!")

    count_used = min(remaining_sold_count, buy_t.remaining_count)
    if count_used < 1:
        raise ValueError(f"Unexpected count_used: {count_used}")

    remaining_sold_count -= count_used
    did_consume_fee = buy_t.consume_shares(count_used)

    buy_records.append(BuyRecord(buy_t, count_used, did_consume_fee))

    return remaining_sold_count


def find_buys(sale_t: Transaction, trans: List[Transaction], strategies: dict[int, str]) -> List[BuyRecord]:
    # The strategy must be specified for every year since the first year is specified
    if sale_t.time.year > max(strategies.keys()):
        raise ValueError("No strategy specified for this year!")

    method_suffix = 'fifo' if sale_t.time.year < min(strategies.keys()) else \
                    strategies[sale_t.time.year]

    # use reflection to call the correct method
    method = globals()['find_buys_' + method_suffix]
    return method(sale_t, trans)


def calculate_break_even_prices(txs: List[Transaction]):
    quantity = 0
    total_cost = Decimal(0)

    for tx in txs:
        if not tx.is_sale:
            total_cost += tx.count * tx.share_price
            quantity += tx.count
            tx.set_bep(total_cost / quantity)
        else:
            bep = total_cost / quantity
            tx.set_bep(bep)
            total_cost += tx.count * bep  # Count is negative for sales
            quantity += tx.count
        

def warn_about_default_strategy(trans: List[Transaction], strategies: dict[int,str]) -> None:
    for sale_t in [t for t in trans if t.is_sale]:
        if sale_t.time.year < min(strategies.keys()):
            print(f"Warning: No strategy specified for {sale_t.time.year}, using FIFO.")
            return


@dataclass
class _OpenShort:
    """One still-uncovered short lot."""
    tx: Transaction        # original short-sale transaction
    remaining: int         # positive number of shares still open


def optimize_transaction_pairing(
    trans: List[Transaction],
    strategies: Dict[int, str],
) -> List[SaleRecord]:
    """
    • When a SELL closes an existing long, use the legacy find_buys logic.
      Any excess quantity becomes a new short lot.

    • When a BUY covers a short, consume open shorts in strict FIFO order.
      Any excess quantity opens (or enlarges) a long lot and will later be
      matched by find_buys when a SELL occurs.

    Long-only results remain byte-for-byte identical to the historical
    implementation; short selling now works deterministically.

    Initially written by GPT o3.
    """
    warn_about_default_strategy(trans, strategies)

    sale_records: List[SaleRecord] = []
    sale_map: Dict[Transaction, SaleRecord] = {}
    open_shorts: deque[_OpenShort] = deque()        # FIFO queue of short lots

    # Process chronologically
    for t in sorted(trans, key=lambda x: x.time):

        # SELL: first close longs with the original machinery
        if t.is_sale:
            try:
                buy_records = find_buys(t, trans, strategies)   # unchanged call
            except ValueError:
                # TODO: Resolve this HACK. Add some status reporting.
                print(f"Could not find a buy transaction for {t}, openning short.")
                buy_records = []

            matched_qty = sum(br._count_consumed for br in buy_records)
            total_qty   = -t.count          # positive number of shares sold
            excess_qty  = total_qty - matched_qty  # may be zero

            # Record the long close (even if partially matched)
            sale_rec = SaleRecord(t, buy_records)
            sale_records.append(sale_rec)
            sale_map[t] = sale_rec

            # Any excess opens / enlarges a short position
            if excess_qty:
                open_shorts.append(_OpenShort(t, excess_qty))

        # BUY: cover outstanding shorts FIFO, then leave the rest as a long
        else:
            remaining = t.count

            while remaining and open_shorts:
                short_lot = open_shorts[0]  # Always FIFO for short covers.
                qty = min(remaining, short_lot.remaining)

                fee_used = t.consume_shares(qty)
                buy_rec = BuyRecord(t, qty, fee_used, is_short_cover=True)

                sale_rec = sale_map.get(short_lot.tx)
                if sale_rec is None:  # should not generally happen
                    sale_rec = SaleRecord(short_lot.tx, [])
                    sale_records.append(sale_rec)
                    sale_map[short_lot.tx] = sale_rec
                sale_rec.append_buy_record(buy_rec)

                short_lot.remaining -= qty
                remaining -= qty
                if short_lot.remaining == 0:
                    open_shorts.popleft()

            # Any *remaining* shares now form / enlarge a long position.
            # No extra action needed: they will be paired by find_buys later.

    if open_shorts:
        print("Warning: Unmatched open short positions remain after pairing.")
        # TODO: Add some status reporting.

    return sale_records

# Tax calculation: use the true closing year of each position
def calculate_tax(
    sale_records: List[SaleRecord],
    tax_year: int,
    enable_bep: bool = False,
    enable_ttest: bool = False,
) -> None:
    for sale in (s for s in sale_records if s.close_time.year == tax_year):
        sale.calculate_income_and_cost(tax_year, enable_bep, enable_ttest)


def optimize_product(txs: List[Transaction], tax_year: int, strategies: dict[int,str] = None, enable_bep: bool = False, enable_ttest: bool = False) -> List[SaleRecord]:
    if enable_bep:
        calculate_break_even_prices(txs)
    sale_records = optimize_transaction_pairing(txs, strategies)
    calculate_tax(sale_records, tax_year, enable_bep, enable_ttest)
    return sale_records


def calculate_totals(sale_records: List[SaleRecord], tax_year: int) -> (decimal, decimal, decimal):
    total_income = Decimal(0)
    total_cost = Decimal(0)
    total_fees = Decimal(0)

    for sale in [s for s in sale_records if s.close_time.year == tax_year]:
        total_income += sale.income_tc
        total_cost += sale.cost_tc
        total_fees += sale.fees_tc

    precision = Decimal('0.0001')
    return total_income.quantize(precision), total_cost.quantize(precision), total_fees.quantize(precision)


def calculate_untaxed_totals(sale_records: List[SaleRecord], tax_year: int) -> int:
    total_untaxed_count = 0

    for sale in [s for s in sale_records if s.close_time.year == tax_year]:
        total_untaxed_count += sale.untaxed_count

    return total_untaxed_count


def print_report(sale_records: List[SaleRecord]):
    total_income = Decimal(0)
    total_cost = Decimal(0)
    total_fees = Decimal(0)
    for sale in sale_records:
        print(sale.sale_t)

        for buy_record in sale.buys:
            print(f"-  {buy_record.buy_t}, consumed: {buy_record._count_consumed}, fee con.: {buy_record._fee_consumed}")

        if sale.income_tc is None:
            continue

        print(f"  income: {sale.income_tc}")
        print(f"  cost  : {sale.cost_tc}")
        print(f"  profit: {sale.profit_tc}")
        print(f"  fees  : {sale.fees_tc}")

        total_income += sale.income_tc
        total_cost += sale.cost_tc
        total_fees += sale.fees_tc

    print(f"*** total income: {total_income}")
    print(f"*** total cost : {total_cost}")
    print(f"*** total fees : {total_fees}")
    print(f"*** total profit: {total_income - total_cost}, after fees: {total_income - total_cost - total_fees}")


def get_product_name(report: List[SaleRecord]):
    if len(report) == 0:
        return '<no sale records>'

    return report[0].sale_t.product_name
