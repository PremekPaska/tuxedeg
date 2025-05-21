import decimal
import math
from decimal import Decimal
from datetime import datetime
from typing import List

from currency import unified_fx_rate, check_currency

IMPORT_PRECISION = Decimal('0.000001')  # Prices have up to 4 decimal digits, plus some extra.

TSLA_SPLIT = datetime(2022, 8, 25)


class Transaction:
    def __init__(self, time: datetime, product_name: str, isin: str, count: int, share_price: decimal, currency: str,
                 fee: decimal, fee_currency: str):
        self._time = time
        self._product_name = product_name
        self.isin = isin  # TODO: rename to product_id
        self._count = int(count)  # count is negative for sales
        self._remaining_count = self._count  # This is only valid for buy transactions.
        self._share_price = Decimal(share_price).quantize(IMPORT_PRECISION)  # 'cause pandas stores it in doubles (TODO)
        self._currency = check_currency(currency)
        self._fee_currency = check_currency(fee_currency)
        self._fee = Decimal(fee).quantize(IMPORT_PRECISION) if not math.isnan(fee) else Decimal(0)

        self._fee_available = True  # Not used for sale transactions
        self._split_ratio = Decimal(1)
        self._bep = None

    def __str__(self):
        return f"{self._time}, {self._product_name}, {self._count}, {self.isin}, {self._share_price}, fee: {self._fee}"

    @property
    def product_name(self) -> str:
        return self._product_name

    @property
    def is_sale(self) -> bool:
        return self._count < 0

    @property
    def count(self) -> int:
        return self._count

    @property
    def remaining_count(self) -> int:
        if self.is_sale:
            raise ValueError("Remaining count not applicable to sell transactions.")
        return self._remaining_count

    @property
    def time(self) -> datetime:
        return self._time

    @property
    def share_price(self) -> decimal:
        return self._share_price

    @property
    def currency(self) -> str:
        return self._currency

    @property
    def fee_currency(self) -> str:
        return self._fee_currency

    @property
    def fee(self) -> decimal:
        return self._fee

    @property
    def split_ratio(self) -> decimal:
        return self._split_ratio

    @property
    def bep(self) -> decimal:
        return self._bep
    
    def set_bep(self, bep: decimal):
        self._bep = bep

    def consume_shares(self, number_sold: int) -> bool:
        if number_sold < 1:
            raise ValueError(f"Number sold < 1: {number_sold}")

        if self._remaining_count < 1:
            raise ValueError(f"Remaining count is 0 (or less): {self._remaining_count}")

        if number_sold > self._remaining_count:
            raise ValueError(f"Cannot mark {number_sold} shares as sold, only {self._remaining_count} remaining!")

        self._remaining_count -= number_sold

        if self._fee_available:
            self._fee_available = False
            return True
        else:
            return False

    def apply_split(self, numerator: int, denominator: int) -> None:
        """Scale share count / price by *numerator/denominator* (in-place)."""
        if numerator == denominator:
            return
        
        # must stay integral
        if (self._count * numerator) % denominator:
            raise ValueError(f"split leaves fractional share in {self}")
        
        self._count = self._count * numerator // denominator
        self._split_ratio = self._split_ratio * numerator / denominator
        
        if not self.is_sale:
            self._remaining_count = self._remaining_count * numerator // denominator
        
        factor = Decimal(denominator) / Decimal(numerator)
        self._share_price = (self._share_price * factor).quantize(IMPORT_PRECISION)


class BuyRecord:
    def __init__(self, buy_t: Transaction, count_consumed: int, fee_consumed: bool):
        self.buy_t = buy_t
        self._count_consumed = count_consumed
        self._fee_consumed = fee_consumed

        self._fx_rate = None
        self._cost_tc = None  # In the target currency (CZK).
        self._fees_tc = None
        self._time_test_passed = False

    @property
    def trans(self):
        return self.buy_t

    @property
    def fx_rate(self):
        return self._fx_rate

    @property
    def cost_tc(self):
        return self._cost_tc

    @property
    def fees_tc(self):
        return self._fees_tc

    @property
    def time_test_passed(self):
        return self._time_test_passed

    def pass_time_test(self):
        self._time_test_passed = True

    def calculate_cost(self):
        self._fx_rate = unified_fx_rate(self.buy_t.time.year, self.buy_t.currency)
        self._cost_tc = self.buy_t.share_price * self._fx_rate * self._count_consumed

        self._fees_tc = self.buy_t.fee * unified_fx_rate(self.buy_t.time.year, self.buy_t.fee_currency) if self._fee_consumed \
            else Decimal(0)


class SaleRecord:
    def __init__(self, sale_t: Transaction, buy_records: List[BuyRecord]):
        self.sale_t = sale_t
        self.buys = buy_records
        self._fx_rate = None
        self._income_tc = None
        self._cost_tc = None
        self._fees_tc = None

    @property
    def fx_rate(self) -> decimal:
        return self._fx_rate

    @property
    def income_tc(self) -> decimal:
        return self._income_tc

    @property
    def cost_tc(self) -> decimal:
        return self._cost_tc

    @property
    def profit_tc(self) -> decimal:
        if self._income_tc is None or self._cost_tc is None:
            return None
        return self._income_tc - self._cost_tc

    @property
    def fees_tc(self) -> decimal:
        return self._fees_tc
    
    def _calculate_income_for_buy_sell_pair(self, buy_record: BuyRecord):
        sale_fx_rate = unified_fx_rate(self.sale_t.time.year, self.sale_t.currency)
        return buy_record._count_consumed * self.sale_t.share_price * sale_fx_rate

    def _calculate_income(self) -> decimal:
        self._fx_rate = unified_fx_rate(self.sale_t.time.year, self.sale_t.currency)
        if not self.sale_t.is_sale:
            raise ValueError("Expected a sale transaction.")
        
        # Calculate income for each buy record individually
        total_income = Decimal(0)
        for buy_record in self.buys:
            total_income += self._calculate_income_for_buy_sell_pair(buy_record)
            
        self._income_tc = total_income
        return self._income_tc

    def _calculate_cost_and_fees(self, use_bep: bool = False) -> None:
        cost = Decimal(0)
        fees = Decimal(0)
        for buy_record in self.buys:
            if use_bep:
                buy_record.buy_t._share_price = self.sale_t.bep  # Hack

            buy_record.calculate_cost()
            cost += buy_record.cost_tc
            fees += buy_record.fees_tc
            if (self.sale_t.time - buy_record.buy_t.time).days > 3 * 365:
                buy_record.pass_time_test()

        self._cost_tc = cost

        sale_fee = self.sale_t.fee * unified_fx_rate(self.sale_t.time.year, self.sale_t.fee_currency)
        self._fees_tc = fees + sale_fee

    def calculate_profit(self, enable_bep: bool = False) -> None:
        self._calculate_income()
        self._calculate_cost_and_fees(use_bep=enable_bep)
