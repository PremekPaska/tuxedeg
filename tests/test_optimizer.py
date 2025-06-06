import os
import decimal
from decimal import Decimal
from datetime import datetime
import unittest

from currency import unified_fx_rate
from import_deg import import_transactions, convert_to_transactions_deg
from import_utils import get_product_id_by_prefix
from optimizer import optimize_transaction_pairing, is_better_cost_pair, calculate_tax, optimize_product, \
    calculate_totals, calculate_break_even_prices
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


def scenario_time_test():
    # Create a scenario with buys at different times, some over 3 years old
    return [
        # Buy shares 3 years and 1 day before sale (should pass time test)
        create_t(5, price=100.0, day=1, month=1, year_offset=-3),
        # Buy shares 2 years before sale (should not pass time test)
        create_t(3, price=120.0, day=1, month=1, year_offset=-2),
        create_t(-8, price=200.0, day=2, month=1)
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
         
    def test_time_test_flag_disabled(self):
        """Test that the time test flag doesn't skip transactions over 3 years old when not enabled."""
        trans = scenario_time_test()
        report = optimize_transaction_pairing(trans, {self.TAX_YEAR: 'fifo'})
        self.assertEqual(1, len(report))  # One sale record
        
        calculate_tax(report, self.TAX_YEAR, enable_ttest=False)
        
        expected_income_no_ttest = (5 + 3) * 200 * self.fx_rate
        expected_cost_no_ttest = 5 * 100 * unified_fx_rate(self.TAX_YEAR - 3, 'USD') \
                               + 3 * 120 * unified_fx_rate(self.TAX_YEAR - 2, 'USD')
        
        self.assertEqual(expected_income_no_ttest, report[0].income_tc)
        self.assertEqual(expected_cost_no_ttest, report[0].cost_tc)
        self.assertTrue(report[0].buys[0].time_test_passed)  # We still enable the flag.
        self.assertFalse(report[0].buys[1].time_test_passed)
        
    def test_time_test_flag_enabled(self):
        """Test that the time test flag correctly skips transactions over 3 years old."""
        trans = scenario_time_test()
        report = optimize_transaction_pairing(trans, {self.TAX_YEAR: 'fifo'})
        self.assertEqual(1, len(report))  # One sale record
       
        # Test with the ttest flag, buys over 3 years old should be skipped
        calculate_tax(report, self.TAX_YEAR, enable_ttest=True)
        
        # Calculate expected values with ttest
        # Only 3 shares at $120 should be included (other 5 are skipped due to time test)
        expected_income_ttest = 3 * 200 * self.fx_rate
        expected_cost_ttest = 3 * 120 * unified_fx_rate(self.TAX_YEAR - 2, 'USD')
        
        self.assertEqual(expected_income_ttest, report[0].income_tc)
        self.assertEqual(expected_cost_ttest, report[0].cost_tc)
        self.assertTrue(report[0].buys[0].time_test_passed)
        self.assertFalse(report[0].buys[1].time_test_passed)

        self.assertEqual(Decimal('0.50') * unified_fx_rate(self.TAX_YEAR, 'EUR') \
                       + Decimal('0.50') * unified_fx_rate(self.TAX_YEAR - 2, 'EUR'), report[0].fees_tc)

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
        sale_record.calculate_income_and_cost(self.TAX_YEAR)

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
        sale_record.calculate_income_and_cost(self.TAX_YEAR, enable_bep=True)

        expected_profit_usd = Decimal('-240.0')
        actual_profit_usd = sale_record.profit_tc / self.fx_rate
        self.assertEqual(expected_profit_usd, actual_profit_usd)

        sale_record = report[1]
        sale_record.calculate_income_and_cost(self.TAX_YEAR, enable_bep=True)

        expected_profit_usd = Decimal('2000.0')
        actual_profit_usd = sale_record.profit_tc / self.fx_rate
        self.assertEqual(expected_profit_usd, actual_profit_usd)

    def test_calculate_profit_multiple_buys(self):
        trans = scenario_sell_multiple_buys()
        report = optimize_transaction_pairing(trans, self.STRATEGIES)

        sale_record = report[0]
        sale_record.calculate_income_and_cost(self.TAX_YEAR)
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

def make_tx(
    ts: str | datetime,
    qty: int,
    *,
    price: decimal = 10.0,
    product: str = "TEST",
    isin: str = "TEST123",
    currency: str = "USD",
) -> Transaction:
    """
    Build a Transaction in one line.

    Parameters
    ----------
    ts   : ISO-date string or datetime
    qty  : positive (BUY) or negative (SELL) share count
    """
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)

    return Transaction(
        time=ts,
        product_name=product,
        isin=isin,
        count=qty,
        share_price=price,
        currency=currency,
        fee=0,
        fee_currency=currency,
    )


class OptimizerShortSellingTestCase(unittest.TestCase):
    """Extra short-selling coverage for the optimiser."""

    TAX_YEAR = 2024
    STRATEGIES = {TAX_YEAR: "fifo"}   # keep warn_about_default_strategy quiet
 
    @property
    def fx_rate(self) -> decimal:
        return unified_fx_rate(self.TAX_YEAR, 'USD')

    # ------------------------------------------------------------------ #
    def test_single_short_open_and_close(self):
        """SELL 100 → open short, BUY 100 → cover it completely."""
        short_open = make_tx("2024-01-02", -100, price=100.0)
        cover_buy  = make_tx("2024-01-05",  100, price=150.0)

        records = optimize_transaction_pairing([short_open, cover_buy], self.STRATEGIES)
        self.assertEqual(len(records), 1)

        short_record = records[0]
        self.assertIs(short_record.sale_t, short_open)
        self.assertEqual(sum(br._count_consumed for br in short_record.buys), 100)
        self.assertEqual(cover_buy.remaining_count, 0)

        calculate_tax(records, self.TAX_YEAR)
        income, cost, fees = calculate_totals(records, self.TAX_YEAR)
        self.assertEqual(income, Decimal('10000') * self.fx_rate)
        self.assertEqual(cost, Decimal('15000') * self.fx_rate)
        self.assertEqual(fees, Decimal('0') * self.fx_rate)

        self.assertEqual(short_record.close_time, cover_buy.time)
        self.assertNotEqual(short_record.close_time, short_open.time)

    # ------------------------------------------------------------------ #
    def test_deepen_short_then_two_step_cover(self):
        """
        SELL 50  → open
        SELL 70  → deepen to –120
        BUY  60  → partial cover (FIFO: 50+10)
        BUY  60  → final cover
        """
        first_short   = make_tx("2024-01-02",  -50, price=100.0)
        second_short  = make_tx("2024-01-04",  -70, price=120.0)
        first_cover   = make_tx("2024-01-06",   60, price=90.0)
        final_cover   = make_tx("2024-01-10",   60, price=80.0)

        records = optimize_transaction_pairing(
            [first_short, second_short, first_cover, final_cover],
            self.STRATEGIES,
        )
        self.assertEqual(len(records), 2)

        rec_first  = next(r for r in records if r.sale_t is first_short)
        rec_second = next(r for r in records if r.sale_t is second_short)

        self.assertEqual(sum(br._count_consumed for br in rec_first.buys), 50)
        self.assertEqual(sum(br._count_consumed for br in rec_second.buys), 70)
        
        calculate_tax(records, self.TAX_YEAR)
        income, cost, fees = calculate_totals(records, self.TAX_YEAR)
        
        # First short: 50 shares sold at $100, bought at $90 (first_cover)
        # Second short: 10 shares from first_cover at $90 + 60 shares from final_cover at $80
        expected_income_usd = Decimal(50 * 100.0 + 70 * 120.0)  # Income from both shorts
        expected_cost_usd = Decimal(60 * 90.0 + 60 * 80.0)      # Cost from covering both shorts
        expected_fees_usd = Decimal('0')
        
        self.assertEqual(income / self.fx_rate, expected_income_usd)
        self.assertEqual(cost / self.fx_rate, expected_cost_usd)
        self.assertEqual(fees / self.fx_rate, expected_fees_usd)

    # ------------------------------------------------------------------ #
    def test_partial_cover_deepen_and_final_cover(self):
        """
        SELL 80  → open
        BUY  50  → partial cover (remaining –30)
        SELL 100 → deepen to –130
        BUY  130 → final cover
        """
        initial_short  = make_tx("2024-01-02",  -80, price=100.0)
        partial_cover  = make_tx("2024-01-05",   50, price=110.0)
        deepen_short   = make_tx("2024-01-06", -100, price=120.0)
        final_cover    = make_tx("2024-01-10",  130, price=90.0)

        records = optimize_transaction_pairing(
            [initial_short, partial_cover, deepen_short, final_cover],
            self.STRATEGIES,
        )
        self.assertEqual(len(records), 2)

        rec_init   = next(r for r in records if r.sale_t is initial_short)
        rec_deepen = next(r for r in records if r.sale_t is deepen_short)

        self.assertEqual(sum(br._count_consumed for br in rec_init.buys),   80)
        self.assertEqual(sum(br._count_consumed for br in rec_deepen.buys), 100)
        
        calculate_tax(records, self.TAX_YEAR)
        income, cost, fees = calculate_totals(records, self.TAX_YEAR)
        
        # Initial short: 80 shares sold at $100, covered with 50 at $110 and 30 from final_cover at $90
        # Deepen short: 100 shares sold at $120, covered with 100 from final_cover at $90
        expected_income = Decimal(80 * 100.0 + 100 * 120.0) * self.fx_rate  # Income from both shorts
        expected_cost = Decimal(50 * 110.0 + 30 * 90.0 + 100 * 90.0) * self.fx_rate
        expected_fees = Decimal('0') * self.fx_rate
        
        self.assertEqual(income, expected_income)
        self.assertEqual(cost, expected_cost)
        self.assertEqual(fees, expected_fees)

    # ------------------------------------------------------------------ #
    def test_unmatched_open_short_profit_calculation(self):
        """
        BUY 100 @ $10 (USD) → open long
        SELL 100 @ $12 (USD) → close long. Profit in USD: $200.
                                Profit in CZK: $200 * 23.28 (FX for 2024) = 4656.00 CZK.
        SELL  50 @ $15 (USD) → open short, profit $0 (unmatched at this stage).
        Total profit from processed sales should be 4656.00 CZK.
        """

        long_buy        = make_tx("2024-01-02",  100, price=Decimal("10.0")) # USD
        long_close_sell = make_tx("2024-01-04", -100, price=Decimal("12.0")) # USD
        open_short_sell = make_tx("2024-01-05",  -50, price=Decimal("15.0")) # USD

        transactions = [long_buy, long_close_sell, open_short_sell]
        
        sale_records = optimize_transaction_pairing(
            transactions,
            self.STRATEGIES,
        )

        self.assertEqual(len(sale_records), 2, "Expected two sale records.")

        sale_records.sort(key=lambda sr: sr.sale_t.time)

        # First sale record: closing the long position (long_close_sell)
        sr1 = sale_records[0]
        self.assertIs(sr1.sale_t, long_close_sell, "First SaleRecord should correspond to long_close_sell")
        sr1.calculate_income_and_cost(self.TAX_YEAR)
        expected_profit_sr1_usd = (Decimal("12.0") - Decimal("10.0")) * 100
        expected_profit_sr1_tc = expected_profit_sr1_usd * self.fx_rate
        self.assertEqual(sr1.profit_tc, expected_profit_sr1_tc, f"Profit (TC) for first sale (long close) was {sr1.profit_tc}, expected {expected_profit_sr1_tc}")

        # Second sale record: opening the short position (open_short_sell)
        sr2 = sale_records[1]
        self.assertIs(sr2.sale_t, open_short_sell, "Second SaleRecord should correspond to open_short_sell")
        sr2.calculate_income_and_cost(self.TAX_YEAR)
        # This SaleRecord is for an unmatched short sale, so its buys list is empty; zero profits.
        expected_profit_sr2_tc = Decimal("0.00")
        self.assertEqual(sr2.profit_tc, expected_profit_sr2_tc, f"Profit (TC) for second sale (open short) was {sr2.profit_tc}, expected {expected_profit_sr2_tc}")


if __name__ == '__main__':
    unittest.main()
