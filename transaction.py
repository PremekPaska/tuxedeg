import decimal
from datetime import datetime


class Transaction:
    def __init__(self, date: datetime, product: str, isin: str, count: int, share_price: decimal):
        self.date = date
        self.product = product
        self.isin = isin
        self.count = int(count)
        self.share_price = share_price
        # TODO: add currency, fees, etc.

    def __str__(self):
        return f"{self.date}, {self.product}, {self.count}, {self.isin}, {self.share_price}"
