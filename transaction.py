import decimal
from collections import namedtuple
from datetime import datetime


class Transaction:
    def __init__(self, time: datetime, product: str, isin: str, count: int, share_price: decimal):
        self._time = time
        self.product = product
        self.isin = isin
        self._count = int(count)
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
    def time(self) -> datetime:
        return self._time


Buy = namedtuple('trans', 'count_consumed')


class Sale:
    def __init__(self, sale_t: Transaction):
        self.sale_t = sale_t
        self.buys = []  # pairs of buy transaction and how many shares are consumed as cost for this sale (named tuple?)
