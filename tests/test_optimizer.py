import datetime
import decimal
from decimal import Decimal
import unittest

from currency import unified_fx_rate
from optimizer import optimize_transaction_pairing, is_better_cost_pair, calculate_tax
from tests.test_transaction import create_t
from transaction import Transaction


def scenario_sell_in_two_parts():
    return [
        create_t(10, price=100.0, day=1),
        create_t(-2, price=150.0, day=10),
        create_t(-8, price=150.0, day=20, month=11)
    ]


def scenario_sell_multiple_buys():
    return [
        create_t(5, price=100.0, day=1),
        create_t(4, price=110.0, day=2),
        create_t(3, price=120.0, day=3),
        create_t(-10, price=200.0, day=10)
    ]


class OptimizerTestCase(unittest.TestCase):
    TAX_YEAR = 2021

    @property
    def fx_rate(self) -> decimal:
        return unified_fx_rate(self.TAX_YEAR, 'USD')

    def test_empty_report_for_buys_only(self):
        trans = [create_t(count=5, price=420.0, day=2)]
        report = optimize_transaction_pairing(trans, self.TAX_YEAR)
        self.assertEqual(0, len(report))  # add assertion here

    def test_sell_in_two_parts(self):
        trans = scenario_sell_in_two_parts()
        report = optimize_transaction_pairing(trans, self.TAX_YEAR)

        self.assertEqual(2, len(report))
        self.assertEqual(0, trans[0].remaining_count)

        self.assertEqual(-2, report[0].sale_t.count)
        self.assertEqual(2, report[0].buys[0]._count_consumed)
        self.assertEqual(-8, report[1].sale_t.count)

    def test_greedy_fee_consumption(self):
        trans = scenario_sell_in_two_parts()
        report = optimize_transaction_pairing(trans, self.TAX_YEAR)

        self.assertTrue(report[0].buys[0]._fee_consumed)
        self.assertFalse(report[1].buys[0]._fee_consumed)

        calculate_tax(report, self.TAX_YEAR)
        # There's always the sale transaction fee
        self.assertEqual(Decimal('1.00') * unified_fx_rate(self.TAX_YEAR, 'EUR'), report[0].fees_tc)
        self.assertEqual(Decimal('0.50') * unified_fx_rate(self.TAX_YEAR, 'EUR'), report[1].fees_tc)

    def test_sell_multiple_buys(self):
        trans = scenario_sell_multiple_buys()
        report = optimize_transaction_pairing(trans, self.TAX_YEAR)

        self.assertEqual(1, len(report))
        self.assertEqual(3, len(report[0].buys))
        self.assertEqual(2, sum([buy.trans.remaining_count for buy in report[0].buys]))

    def test_calculate_profit(self):
        transactions = [
            create_t(10, 100.0, day=1),
            create_t(-3, 120.0, day=5)
        ]

        report = optimize_transaction_pairing(transactions, tax_year=self.TAX_YEAR)
        self.assertEqual(1, len(report))

        sale_record = report[0]
        sale_record.calculate_profit()

        self.assertEqual(Decimal('60.0') * self.fx_rate, sale_record.profit_tc)

    def test_calculate_profit_multiple_buys(self):
        trans = scenario_sell_multiple_buys()
        report = optimize_transaction_pairing(trans, tax_year=self.TAX_YEAR)

        sale_record = report[0]
        sale_record.calculate_profit()
        self.assertEqual(Decimal('900') * self.fx_rate, sale_record.profit_tc)  # FIFO would be $940

    def test_is_better_cost_pair(self):
        buy_t = create_t(1, 100.0, day=30, month=10)
        t_same = create_t(1, 100.0, day=5, month=10)
        self.assertFalse(is_better_cost_pair(buy_t=buy_t, t=t_same))
        self.assertTrue(is_better_cost_pair(buy_t, create_t(1, 135, day=29, month=10)))

        self.assertFalse(is_better_cost_pair(buy_t, create_t(1, 107, day=30, month=9)))
        self.assertTrue(is_better_cost_pair(buy_t, create_t(1, 110, day=30, month=9)))

        self.assertFalse(is_better_cost_pair(buy_t, create_t(1, 112, day=27, month=2)))
        self.assertFalse(is_better_cost_pair(buy_t, create_t(1, 112, day=27, month=10, year_offset=-1)))
        self.assertTrue(is_better_cost_pair(buy_t, create_t(1, 112, day=27, month=8)))


if __name__ == '__main__':
    unittest.main()
