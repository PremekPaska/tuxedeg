import decimal
from decimal import Decimal
from typing import List, Callable

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
    if t is None:
        raise ValueError("Transaction parameter 't' must not be None!")
    if buy_t is None:
        return True
    day_diff = abs((buy_t.time - t.time).days)
    return (day_diff < 20 and t.share_price > buy_t.share_price * Decimal('1.02')) \
        or (day_diff < 75 and t.share_price > buy_t.share_price * Decimal('1.08')) \
        or t.share_price > buy_t.share_price * Decimal('1.15')


def is_lower_cost_pair(buy_t: Transaction, t: Transaction) -> bool:
    if t is None:
        raise ValueError("Transaction parameter 't' must not be None!")
    if buy_t is None:
        return True
    day_diff = abs((buy_t.time - t.time).days)
    return (day_diff < 20 and t.share_price < buy_t.share_price * Decimal('0.97')) \
        or (day_diff < 75 and t.share_price < buy_t.share_price * Decimal('0.90')) \
        or t.share_price < buy_t.share_price * Decimal('0.75')


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
        # Only apply break-even price calculations to normal long positions
        if not tx.is_sale and not tx.is_short_position:
            total_cost += tx.count * tx.share_price
            quantity += tx.count
            tx.set_bep(total_cost / quantity)
        elif tx.is_sale and not tx.is_short_position:
            if quantity > 0:  # Only calculate if we have a long position
                bep = total_cost / quantity
                tx.set_bep(bep)
                total_cost += tx.count * bep  # Count is negative for sales
                quantity += tx.count
        

def warn_about_default_strategy(trans: List[Transaction], strategies: dict[int,str]) -> None:
    for sale_t in [t for t in trans if t.is_sale]:
        if sale_t.time.year < min(strategies.keys()):
            print(f"Warning: No strategy specified for {sale_t.time.year}, using FIFO.")
            return


def find_buys_for_short_cover(buy_t: Transaction, trans: List[Transaction]) -> List[BuyRecord]:
    """Find short positions to cover using FIFO for a buy transaction.
    When covering shorts, buy transactions reduce the short position.
    """
    remaining_buy_count = buy_t.count
    
    buy_records = []
    # Find short positions to cover (short sales have negative count but are marked as is_short_position)
    for short_t in [t for t in trans if t.is_sale and t.is_short_position and t.remaining_count > 0 and t.time < buy_t.time]:
        if remaining_buy_count <= 0:
            break
            
        count_used = min(remaining_buy_count, short_t.remaining_count)
        remaining_buy_count -= count_used
        did_consume_fee = short_t.consume_shares(count_used)
        
        buy_records.append(BuyRecord(short_t, count_used, did_consume_fee))
    
    if remaining_buy_count > 0:
        print(f"Still remaining buy count to pair: {remaining_buy_count} for {buy_t}")
        raise ValueError("Could not pair all shares for short cover!")
    
    return buy_records


def process_transactions_chronologically(trans: List[Transaction], strategies: dict[int,str]) -> List[SaleRecord]:
    """Process transactions chronologically to properly handle both long and short positions."""
    warn_about_default_strategy(trans, strategies)
    
    # Sort transactions by time
    sorted_trans = sorted(trans, key=lambda t: t.time)
    sale_records = []
    
    # Track current position
    current_position = 0
    
    for tx in sorted_trans:
        if not tx.is_sale:  # Buy transaction
            if current_position < 0:  # We have a short position
                # This buy will cover some or all of the short position
                cover_count = min(-current_position, tx.count)
                if cover_count > 0:
                    # Create a transaction for covering the short position
                    covering_tx = tx  # The buy transaction is covering shorts
                    
                    # Find short positions to cover using FIFO
                    buy_records = find_buys_for_short_cover(covering_tx, sorted_trans[:sorted_trans.index(tx)])
                    
                    # Create a sale record for this short cover
                    if buy_records:
                        sale_record = SaleRecord(covering_tx, buy_records)
                        sale_records.append(sale_record)
                    
                    # Update position
                    current_position += cover_count
            else:
                # Normal buy adding to long position
                current_position += tx.count
        else:  # Sell transaction
            if current_position <= 0:  # No long position or already short
                # This is a short sale, mark it as such
                tx.set_short_position(True)
                current_position += tx.count  # Remember, tx.count is negative
            else:  # We have a long position
                # This sell will close some or all of the long position
                close_count = min(current_position, -tx.count)
                if close_count > 0:
                    # Use original pairing functions for closing long positions
                    buy_records = find_buys(tx, sorted_trans[:sorted_trans.index(tx)], strategies)
                    
                    # Create a sale record
                    sale_record = SaleRecord(tx, buy_records)
                    sale_records.append(sale_record)
                    
                    # Update position
                    current_position += tx.count
                    
                    # If we've gone short, mark the remaining part as a short position
                    if current_position < 0:
                        # This is a bit tricky as we'd need to split the transaction
                        # For now, we'll just mark it as a short if the final position is short
                        if tx.remaining_count > 0:
                            tx.set_short_position(True)
    
    return sale_records


def optimize_transaction_pairing(trans: List[Transaction], strategies: dict[int,str]) -> List[SaleRecord]:
    """Main entry point for transaction pairing that handles both long and short positions."""
    return process_transactions_chronologically(trans, strategies)


def calculate_tax(sale_records: List[SaleRecord], tax_year: int, enable_bep: bool = False, enable_ttest: bool = False):
    for sale in [sale for sale in sale_records if sale.sale_t.time.year == tax_year]:
        sale.calculate_income_and_cost(enable_bep, enable_ttest)


def optimize_product(txs: List[Transaction], tax_year: int, strategies: dict[int,str] = None, enable_bep: bool = False, enable_ttest: bool = False) -> List[SaleRecord]:
    if enable_bep:
        calculate_break_even_prices(txs)
    sale_records = optimize_transaction_pairing(txs, strategies)
    calculate_tax(sale_records, tax_year, enable_bep, enable_ttest)
    return sale_records


def calculate_totals(sale_records: List[SaleRecord], tax_year: int) -> (decimal, decimal):
    total_income = Decimal(0)
    total_cost = Decimal(0)
    total_fees = Decimal(0)

    for sale in [s for s in sale_records if s.sale_t.time.year == tax_year]:
        total_income += sale.income_tc
        total_cost += sale.cost_tc
        total_fees += sale.fees_tc

    precision = Decimal('0.0001')
    return total_income.quantize(precision), total_cost.quantize(precision), total_fees.quantize(precision)


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
