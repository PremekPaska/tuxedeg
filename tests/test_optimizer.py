import datetime
import decimal
import unittest

from optimizer import optimize_transaction_pairing
from transaction import Transaction


class OptimizerTestCase(unittest.TestCase):
    TAX_YEAR = 2021

    def create_t(self, count: int, price: decimal, day: int, month: int = 3, year_offset: int = 0) -> Transaction:
        return Transaction(
            datetime.datetime(self.TAX_YEAR + year_offset, month, day),
            "Foo",
            "X123",
            count=count,
            share_price=price,
            currency='USD'
        )

    def test_empty_report_for_buys_only(self):
        trans = [self.create_t(count=5, price=420.0, day=2)]
        report = optimize_transaction_pairing(trans)
        self.assertEqual(0, len(report))  # add assertion here

    def test_sell_in_two_parts(self):
        trans = [
            self.create_t(10, price=100.0, day=1),
            self.create_t(-2, price=150.0, day=10),
            self.create_t(-8, price=150.0, day=20, month=11)
        ]
        report = optimize_transaction_pairing(trans)

        self.assertEqual(2, len(report))
        self.assertEqual(0, trans[0].remaining_count)

        self.assertEqual(-2, report[0].sale_t.count)
        self.assertEqual(2, report[0].buys[0].count_consumed)
        self.assertEqual(-8, report[1].sale_t.count)

    def test_sell_multiple_buys(self):
        trans = [
            self.create_t(5, price=100.0, day=1),
            self.create_t(4, price=110.0, day=2),
            self.create_t(3, price=120.0, day=3),
            self.create_t(-10, price=200.0, day=10)
        ]
        report = optimize_transaction_pairing(trans)

        self.assertEqual(1, len(report))
        self.assertEqual(3, len(report[0].buys))
        self.assertEqual(2, sum([buy.trans.remaining_count for buy in report[0].buys]))


if __name__ == '__main__':
    unittest.main()
