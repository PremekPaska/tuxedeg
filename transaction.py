import decimal
from collections import namedtuple
from datetime import datetime
from typing import List


class Transaction:
    def __init__(self, time: datetime, product: str, isin: str, count: int, share_price: decimal):
        self._time = time
        self.product = product
        self.isin = isin
        self._count = int(count)
        self._remaining_count = self._count  # This is only valid for buy transactions.
        self.share_price = share_price  # TODO: use decimal!
        # TODO: add currency, fees, etc.

    def __str__(self):
        return f"{self._time}, {self.product}, {self._count}, {self.isin}, {self.share_price}"

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

    def consume_shares(self, number_sold: int) -> None:
        if number_sold < 1:
            raise ValueError(f"Number sold < 1: {number_sold}")

        if self._remaining_count < 1:
            raise ValueError(f"Remaining count is 0 (or less): {self._remaining_count}")

        if number_sold > self._remaining_count:
            raise ValueError(f"Cannot mark {number_sold} shares as sold, only {self._remaining_count} remaining!")

        self._remaining_count -= number_sold


Buy = namedtuple('Buy', 'trans count_consumed')


class Sale:
    def __init__(self, sale_t: Transaction, buy_trans: List[Buy]):
        self.sale_t = sale_t
        self.buys = buy_trans
