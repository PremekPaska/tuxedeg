import os
import decimal
from decimal import Decimal
import unittest

from currency import unified_fx_rate
from import_deg import import_transactions, convert_to_transactions_deg
from import_utils import get_product_id_by_prefix
from optimizer import optimize_transaction_pairing, is_better_cost_pair, calculate_tax, optimize_product, \
    calculate_totals, calculate_break_even_prices
from tests.test_transaction import create_t


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
    STRATEGIES = {2021: 'max_cost'}

    @property
    def fx_rate(self) -> decimal:
        return unified_fx_rate(self.TAX_YEAR, 'USD')

    def test_empty_report_for_buys_only(self):
        trans = [create_t(count=5, price=420.0, day=2)]
        report = optimize_transaction_pairing(trans, self.STRATEGIES)
        self.assertEqual(0, len(report))  # add assertion here

    def test_sell_in_two_parts(self):
        trans = scenario_sell_in_two_parts()
        report = optimize_transaction_pairing(trans, self.STRATEGIES)

        self.assertEqual(2, len(report))
        self.assertEqual(0, trans[0].remaining_count)

        self.assertEqual(-2, report[0].sale_t.count)
        self.assertEqual(2, report[0].buys[0]._count_consumed)
        self.assertEqual(-8, report[1].sale_t.count)

    def test_greedy_fee_consumption(self):
        trans = scenario_sell_in_two_parts()
        report = optimize_transaction_pairing(trans, self.STRATEGIES)

        self.assertTrue(report[0].buys[0]._fee_consumed)
        self.assertFalse(report[1].buys[0]._fee_consumed)

        calculate_tax(report, self.TAX_YEAR)
        # There's always the sale transaction fee
        self.assertEqual(Decimal('1.00') * unified_fx_rate(self.TAX_YEAR, 'EUR'), report[0].fees_tc)
        self.assertEqual(Decimal('0.50') * unified_fx_rate(self.TAX_YEAR, 'EUR'), report[1].fees_tc)

    def test_sell_multiple_buys(self):
        trans = scenario_sell_multiple_buys()
        report = optimize_transaction_pairing(trans, self.STRATEGIES)

        self.assertEqual(1, len(report))
        self.assertEqual(3, len(report[0].buys))
        self.assertEqual(2, sum([buy.trans.remaining_count for buy in report[0].buys]))

    def test_calculate_profit(self):
        transactions = [
            create_t(10, 100.0, day=1),
            create_t(-3, 120.0, day=5)
        ]

        report = optimize_transaction_pairing(transactions, self.STRATEGIES)
        self.assertEqual(1, len(report))

        sale_record = report[0]
        sale_record.calculate_profit()

        self.assertEqual(Decimal('60.0') * self.fx_rate, sale_record.profit_tc)

    def test_calculate_profit_bep(self):
        transactions = [
            create_t(10, 100.0, day=1),
            create_t(10, 300.0, day=3),
            create_t(-3, 120.0, day=5),
            create_t(17, 400.0, day=10),
            create_t(-10, 500.0, day=15)
        ]

        calculate_break_even_prices(transactions)
        report = optimize_transaction_pairing(transactions, {self.TAX_YEAR: 'fifo'})
        self.assertEqual(2, len(report))

        sale_record = report[0]
        sale_record.calculate_profit(enable_bep=True)

        expected_profit_usd = Decimal('-240.0')
        actual_profit_usd = sale_record.profit_tc / self.fx_rate
        self.assertEqual(expected_profit_usd, actual_profit_usd)

        sale_record = report[1]
        sale_record.calculate_profit(enable_bep=True)

        expected_profit_usd = Decimal('2000.0')
        actual_profit_usd = sale_record.profit_tc / self.fx_rate
        self.assertEqual(expected_profit_usd, actual_profit_usd)

    def test_calculate_profit_multiple_buys(self):
        trans = scenario_sell_multiple_buys()
        report = optimize_transaction_pairing(trans, self.STRATEGIES)

        sale_record = report[0]
        sale_record.calculate_profit()
        self.assertEqual(Decimal('900') * self.fx_rate, sale_record.profit_tc)  # assumes max_cost, FIFO would be $940

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
        
    def test_calculate_break_even_prices_buy_only(self):
        # Test with only buy transactions
        transactions = [
            create_t(5, price=100.0, day=1),  # 5 shares at $100 each
            create_t(3, price=150.0, day=2)   # 3 shares at $150 each
        ]
        
        calculate_break_even_prices(transactions)
        
        # First transaction: 5 shares at $100, BEP = $100
        self.assertEqual(Decimal('100.0'), transactions[0].bep)
        
        # Second transaction: after buying 3 more at $150
        # Total cost = (5*100) + (3*150) = 500 + 450 = 950
        # Total quantity = 5 + 3 = 8
        # BEP = 950/8 = 118.75
        self.assertEqual(Decimal('118.75'), transactions[1].bep)
    
    def test_calculate_break_even_prices_with_sales(self):
        # Test with buys and sells
        transactions = [
            create_t(10, price=100.0, day=1),    # Buy 10 at $100
            create_t(5, price=120.0, day=2),     # Buy 5 at $120
            create_t(-8, price=130.0, day=3),    # Sell 8 at $130
            create_t(1, price=140.0, day=4)      # Buy 1 at $140
        ]
        
        calculate_break_even_prices(transactions)
        
        # First transaction: 10 shares at $100, BEP = $100
        self.assertEqual(Decimal('100.0'), transactions[0].bep)
        
        # Second transaction: after buying 5 more at $120
        # Total cost = (10*100) + (5*120) = 1000 + 600 = 1600
        # Total quantity = 10 + 5 = 15
        # BEP = 1600/15 = 106.666...
        expected_bep = Decimal('1600') / Decimal('15')
        self.assertEqual(expected_bep, transactions[1].bep)
        
        # For the sale transaction, no BEP is set, but the total cost is adjusted
        self.assertEqual(expected_bep, transactions[2].bep)
        quantity = 15 + transactions[2].count
        total_cost = Decimal('1600') + transactions[2].count * expected_bep

        # Fourth transaction: after selling 8 at $130 and buying 1 at $140
        t = transactions[3]
        final_expected_bep = (total_cost + t.count * t.share_price) / (quantity + t.count)
        self.assertEqual(final_expected_bep, t.bep)        


class PairingStrategiesTestCase(unittest.TestCase):
    @staticmethod
    def import_test_transactions_cz():
        if not os.path.exists('test_data'):
            os.chdir(os.path.dirname(__file__))
        return import_transactions('test_data/Transactions-deg-cz-2019.csv')

    def import_product_transactions(self, product_prefix: str, tax_year: int):
        df_trans = self.import_test_transactions_cz()
        product_id = get_product_id_by_prefix(df_trans, product_prefix, id_col="ISIN")
        return convert_to_transactions_deg(df_trans, product_id, tax_year)

    def optimize_product_amd(self, tax_year: int, strategies: dict[int,str], enable_bep: bool = False):
        transactions = self.import_product_transactions('ADVANCED MICRO DEVICES', tax_year)

        report = optimize_product(transactions, tax_year, strategies, enable_bep)
        self.assertEqual(38, len(report))
        return report

    def test_pairing_strategy_max_cost(self):
        tax_year = 2019
        report = self.optimize_product_amd(tax_year, {tax_year: 'max_cost'})

        income, cost, fees = calculate_totals(report, tax_year)
        self.assertEqual(Decimal('93774.7573'), income)
        self.assertEqual(Decimal('76584.4204'), cost)
        self.assertEqual(Decimal('593.3456'), fees)

    def test_pairing_strategy_fifo(self):
        tax_year = 2019
        report = self.optimize_product_amd(tax_year, {tax_year: 'fifo'})

        income, cost, fees = calculate_totals(report, tax_year)
        self.assertEqual(Decimal('93774.7573'), income)
        self.assertEqual(Decimal('58947.2520'), cost)
        self.assertEqual(Decimal('487.6372'), fees)

    def test_pairing_strategy_lifo(self):
        tax_year = 2019
        report = self.optimize_product_amd(tax_year, {tax_year: 'lifo'})

        income, cost, fees = calculate_totals(report, tax_year)
        self.assertEqual(Decimal('93774.7573'), income)
        self.assertEqual(Decimal('75028.2394'), cost)
        self.assertEqual(Decimal('593.3456'), fees)

    def test_pairing_strategy_min_cost(self):
        tax_year = 2019
        report = self.optimize_product_amd(tax_year, {tax_year: 'min_cost'})

        income, cost, fees = calculate_totals(report, tax_year)
        self.assertEqual(Decimal('93774.7573'), income)
        self.assertEqual(Decimal('60565.7172'), cost)
        self.assertEqual(Decimal('500.4564'), fees)

    def test_pairing_strategy_lifo_bep(self):
        tax_year = 2019
        report = self.optimize_product_amd(tax_year, {tax_year: 'lifo'}, enable_bep=True)
        # Not sure if LIFO with BEP makes sense, but FIFO gives same results with or without BEP

        income, cost, fees = calculate_totals(report, tax_year)
        self.assertEqual(Decimal('93774.7573'), income)
        self.assertEqual(Decimal('63322.7934'), cost)
        self.assertEqual(Decimal('593.3456'), fees)

if __name__ == '__main__':
    unittest.main()
