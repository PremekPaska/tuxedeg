import decimal
from decimal import Decimal
from datetime import datetime
from typing import List

from currency import unified_fx_rate

IMPORT_PRECISION = Decimal('0.000001')  # Prices have up to 4 decimal digits, plus some extra.


class Transaction:
    def __init__(self, time: datetime, product: str, isin: str, count: int, share_price: decimal, currency: str):
        self._time = time
        self.product = product
        self.isin = isin
        self._count = int(count)
        self._remaining_count = self._count  # This is only valid for buy transactions.
        self._share_price = Decimal(share_price).quantize(IMPORT_PRECISION)  # 'cause pandas stores it in doubles (TODO)
        if currency not in ['USD', 'EUR']:
            raise ValueError(f"Unexpected currency: {currency}")
        self._currency = currency
        # TODO: fees, etc.

    def __str__(self):
        return f"{self._time}, {self.product}, {self._count}, {self.isin}, {self._share_price}"

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

    def consume_shares(self, number_sold: int) -> None:
        if number_sold < 1:
            raise ValueError(f"Number sold < 1: {number_sold}")

        if self._remaining_count < 1:
            raise ValueError(f"Remaining count is 0 (or less): {self._remaining_count}")

        if number_sold > self._remaining_count:
            raise ValueError(f"Cannot mark {number_sold} shares as sold, only {self._remaining_count} remaining!")

        self._remaining_count -= number_sold


class BuyRecord:
    def __init__(self, buy_t: Transaction, count_consumed: int):
        self.buy_t = buy_t
        self.count_consumed = count_consumed

        self._fx_rate = None
        self._cost_tc = None  # In the target currency (CZK).

    @property
    def trans(self):
        return self.buy_t

    @property
    def fx_rate(self):
        return self._fx_rate

    @property
    def cost_tc(self):
        return self._cost_tc

    def calculate_cost(self):
        self._fx_rate = unified_fx_rate(self.buy_t.time.year, self.buy_t.currency)
        self._cost_tc = self.buy_t.share_price * self._fx_rate * self.count_consumed


class SaleRecord:
    def __init__(self, sale_t: Transaction, buy_records: List[BuyRecord]):
        self.sale_t = sale_t
        self.buys = buy_records
        self._fx_rate = None
        self._income_tc = None

    @property
    def fx_rate(self) -> decimal:
        return self._fx_rate

    @property
    def income_tc(self) -> decimal:
        return self._income_tc

    def calculate_income(self) -> None:
        self._fx_rate = unified_fx_rate(self.sale_t.time.year, self.sale_t.currency)
        if not self.sale_t.is_sale:
            raise ValueError("Expected a sale transaction.")
        self._income_tc = (-self.sale_t.count) * self.sale_t.share_price * self._fx_rate

