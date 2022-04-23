import decimal
from decimal import Decimal
import unittest
from datetime import datetime

from transaction import Transaction, BuyRecord

TAX_YEAR = 2021


def create_t(count: int, price: decimal, day: int = 1, month: int = 3, year_offset: int = 0) -> Transaction:
    return Transaction(
        datetime(TAX_YEAR + year_offset, month, day),
        "Foo",
        "X123",
        count=count,
        share_price=price,
        currency='USD'
    )


class TransactionTestCase(unittest.TestCase):
    def test_buy_cost_calculation(self):
        buy_t = create_t(20, 100.0)
        self.assertEqual(Decimal('100.0'), buy_t.share_price)

        buy_record = BuyRecord(buy_t, 10)
        self.assertEqual(None, buy_record.cost_tc)

        buy_record.calculate_cost()
        self.assertEqual(Decimal('21.72'), buy_record.fx_rate)
        self.assertEqual(Decimal('21720.0'), buy_record.cost_tc)

