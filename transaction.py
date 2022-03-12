import decimal
from datetime import datetime


class Transaction:
    def __init__(self, date: datetime, product: str, isin: str, count: int, share_price: decimal):
        self.date = date
        self.product = product
        self.isin = isin
        self.count = count
        self.share_price = share_price
