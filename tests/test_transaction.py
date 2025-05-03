import decimal
from decimal import Decimal
import unittest
from datetime import datetime

from transaction import Transaction, BuyRecord, SaleRecord

TAX_YEAR = 2021


def create_t(count: int, price: decimal, day: int = 1, month: int = 3, year_offset: int = 0) -> Transaction:
    return Transaction(
        datetime(TAX_YEAR + year_offset, month, day),
        "Foo",
        "X123",
        count=count,
        share_price=price,
        currency='USD',
        fee=0.5,
        fee_currency='EUR'
    )


class TransactionTestCase(unittest.TestCase):
    def test_precision(self):
        price = Decimal(2).sqrt()
        t = create_t(1, price)
        self.assertEqual(Decimal('1.414214'), t.share_price)

    def test_precision_double(self):
        price = 2.0 ** 0.5
        t = create_t(1, price)
        self.assertEqual(Decimal('1.414214'), t.share_price)

    def test_buy_cost_calculation(self):
        buy_t = create_t(20, 100.0)
        self.assertEqual(Decimal('100.0'), buy_t.share_price)

        buy_record = BuyRecord(buy_t, 10, fee_consumed=True)
        self.assertEqual(None, buy_record.cost_tc)

        buy_record.calculate_cost()
        self.assertEqual(Decimal('21.72'), buy_record.fx_rate)
        self.assertEqual(Decimal('21720.0'), buy_record.cost_tc)

    def test_sale_income_calculation(self):
        sale_t = create_t(-10, 100.0)
        sale_record = SaleRecord(sale_t, [])
        sale_record._calculate_income()

        self.assertEqual(Decimal('21.72'), sale_record.fx_rate)
        self.assertEqual(Decimal('21720.0'), sale_record.income_tc)





