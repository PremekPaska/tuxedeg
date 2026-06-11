import os
import decimal
from decimal import Decimal
from datetime import datetime
import unittest

from currency import unified_fx_rate
from import_deg import import_transactions, convert_to_transactions_deg
from import_utils import get_product_id_by_prefix
from optimizer import optimize_transaction_pairing, is_better_cost_pair, calculate_tax, optimize_product, \
    calculate_totals, calculate_break_even_prices, calculate_ttc_totals
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

    def test_ttc_totals(self):
        """Sold Time Test Candidate share count for different month thresholds."""
        trans = scenario_time_test()  # 5 shares held ~3y+1d, 3 shares held ~2y+1d
        report = optimize_transaction_pairing(trans, {self.TAX_YEAR: 'fifo'})

        # 12 months: both lots held > 1 year -> 8 shares
        self.assertEqual(8, calculate_ttc_totals(report, self.TAX_YEAR, months=12))
        # 36 months: only the 3-year lot qualifies, matching the time-test count -> 5 shares
        self.assertEqual(5, calculate_ttc_totals(report, self.TAX_YEAR, months=36))

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
    
    # Cross-year short scenarios are covered in OptimizerShortSellingTestCase below.

def make_tx(
    ts: str | datetime,
    qty: int,
    *,
    price: decimal = 10.0,
    fee: decimal = 0,
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
        fee=fee,
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

        records = optimize_transaction_pairing([short_open, cover_buy], self.STRATEGIES, allow_partial=True)
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
            allow_partial=True,
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
            allow_partial=True,
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
            allow_partial=True,
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

    # ------------------------------------------------------------------ #
    def test_sell_closes_long_then_opens_short(self):
        """
        Regression for the old all-or-nothing find_buys HACK.

        BUY  30 @ $50 → hold 30 long
        SELL 100 @ $60 → close the 30 long (taxable!) AND open a 70 short
        BUY  70 @ $40 → cover the 70 short

        The single sell must split into a 30-share long close plus a 70-share
        short. Previously find_buys consumed the 30 buy and then raised, the
        caller discarded the partial match (buy_records=[]) and opened a short
        for the full 100, so the long-close P&L was lost and 30 shares were left
        permanently uncovered.
        """
        long_buy   = make_tx("2024-01-02",   30, price=Decimal("50.0"))
        sell       = make_tx("2024-01-04", -100, price=Decimal("60.0"))
        cover_buy  = make_tx("2024-01-06",   70, price=Decimal("40.0"))

        records = optimize_transaction_pairing([long_buy, sell, cover_buy], self.STRATEGIES, allow_partial=True)

        # One sale record (the sell); the cover buy is appended to it.
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertIs(rec.sale_t, sell)

        long_qty  = sum(br._count_consumed for br in rec.buys if not br._is_short_cover)
        short_qty = sum(br._count_consumed for br in rec.buys if br._is_short_cover)
        self.assertEqual(long_qty, 30, "30 shares should close the existing long")
        self.assertEqual(short_qty, 70, "70 shares should be covered as a short")
        self.assertEqual(long_buy.remaining_count, 0, "the long buy must be fully consumed, not leaked")
        self.assertEqual(cover_buy.remaining_count, 0)

        # Short closes when the covering buy executes.
        self.assertEqual(rec.close_time, cover_buy.time)

        calculate_tax(records, self.TAX_YEAR)
        income, cost, fees = calculate_totals(records, self.TAX_YEAR)
        # Income: all 100 shares sold at $60. Cost: 30 @ $50 (long) + 70 @ $40 (cover).
        self.assertEqual(income, Decimal(100 * 60) * self.fx_rate)
        self.assertEqual(cost, Decimal(30 * 50 + 70 * 40) * self.fx_rate)
        self.assertEqual(fees, Decimal(0))

    # ------------------------------------------------------------------ #
    def test_partial_fill_across_years(self):
        """
        BUY  60 @ $50 (2023) → hold 60 long
        SELL 100 @ $60 (2023, fee $2) → close the 60 long AND open a 40 short
        BUY  40 @ $40 (2024) → cover the short

        The long close must be taxed in 2023 (the year the cash was received),
        the short cover in 2024 -- each pair exactly once, the sale fee exactly
        once (it belongs to the earliest non-empty record, here the long close).
        """
        strategies = {2023: "fifo", 2024: "fifo"}
        long_buy = make_tx("2023-06-01", 60, price=Decimal("50.0"))
        sell     = make_tx("2023-11-01", -100, price=Decimal("60.0"), fee=Decimal("2.0"))
        cover    = make_tx("2024-03-01", 40, price=Decimal("40.0"))

        records = optimize_transaction_pairing([long_buy, sell, cover], strategies, allow_partial=True)
        self.assertEqual(2, len(records))

        rec_2023 = next(r for r in records if r.close_time.year == 2023)
        rec_2024 = next(r for r in records if r.close_time.year == 2024)
        self.assertIs(rec_2023.sale_t, sell)
        self.assertIs(rec_2024.sale_t, sell)
        self.assertTrue(rec_2024.is_spillover)
        self.assertEqual(60, sum(br._count_consumed for br in rec_2023.buys))
        self.assertEqual(40, sum(br._count_consumed for br in rec_2024.buys))

        fx23 = unified_fx_rate(2023, 'USD')
        fx24 = unified_fx_rate(2024, 'USD')

        calculate_tax(records, 2023)
        income, cost, fees = calculate_totals(records, 2023)
        self.assertEqual(Decimal(60 * 60) * fx23, income)
        self.assertEqual(Decimal(60 * 50) * fx23, cost)
        self.assertEqual(Decimal("2.0") * fx23, fees)

        calculate_tax(records, 2024)
        income, cost, fees = calculate_totals(records, 2024)
        self.assertEqual(Decimal(40 * 60) * fx23, income)  # income at sale-year FX
        self.assertEqual(Decimal(40 * 40) * fx24, cost)
        self.assertEqual(Decimal(0), fees)  # sale fee already counted in 2023

    def test_partial_fill_truncated_data_matches_full_data(self):
        """
        Same as test_partial_fill_across_years but without the 2024 cover, the
        way a --year 2023 run sees the data (the importer cuts off later rows).
        The 2023 totals must be identical either way -- previously the long
        close was taxed in 2023 from truncated data and again in 2024 from full
        data (double taxation across filings).
        """
        strategies = {2023: "fifo", 2024: "fifo"}
        long_buy = make_tx("2023-06-01", 60, price=Decimal("50.0"))
        sell     = make_tx("2023-11-01", -100, price=Decimal("60.0"), fee=Decimal("2.0"))

        records = optimize_transaction_pairing([long_buy, sell], strategies, allow_partial=True)
        self.assertEqual(1, len(records))

        fx23 = unified_fx_rate(2023, 'USD')
        calculate_tax(records, 2023)
        income, cost, fees = calculate_totals(records, 2023)
        self.assertEqual(Decimal(60 * 60) * fx23, income)
        self.assertEqual(Decimal(60 * 50) * fx23, cost)
        self.assertEqual(Decimal("2.0") * fx23, fees)

    def test_short_covered_across_years(self):
        """
        SELL 100 @ $100 (2022, fee $3) → open short
        BUY   50 @  $80 (2023) → cover half
        BUY   50 @  $70 (2024) → cover the rest

        Each cover is taxed in its own year (previously the 2023 half was lost:
        excluded from 2023 by close_time and skipped in 2024 as a prior-year
        cover). Income is valued at the sale-year FX rate; the sale fee goes
        once to the earliest non-empty record (2023).
        """
        strategies = {2022: "fifo", 2023: "fifo", 2024: "fifo"}
        short   = make_tx("2022-06-01", -100, price=Decimal("100.0"), fee=Decimal("3.0"))
        cover23 = make_tx("2023-05-01", 50, price=Decimal("80.0"))
        cover24 = make_tx("2024-05-01", 50, price=Decimal("70.0"))

        records = optimize_transaction_pairing([short, cover23, cover24], strategies, allow_partial=True)
        # Sell-time record (empty) + one spillover per cover year.
        self.assertEqual(3, len(records))

        fx22 = unified_fx_rate(2022, 'USD')
        fx23 = unified_fx_rate(2023, 'USD')
        fx24 = unified_fx_rate(2024, 'USD')

        calculate_tax(records, 2022)
        income, cost, fees = calculate_totals(records, 2022)
        self.assertEqual(Decimal(0), income)
        self.assertEqual(Decimal(0), cost)
        self.assertEqual(Decimal(0), fees)

        calculate_tax(records, 2023)
        income, cost, fees = calculate_totals(records, 2023)
        self.assertEqual(Decimal(50 * 100) * fx22, income)
        self.assertEqual(Decimal(50 * 80) * fx23, cost)
        self.assertEqual(Decimal("3.0") * fx22, fees)  # sale fee at sale-year FX

        calculate_tax(records, 2024)
        income, cost, fees = calculate_totals(records, 2024)
        self.assertEqual(Decimal(50 * 100) * fx22, income)
        self.assertEqual(Decimal(50 * 70) * fx24, cost)
        self.assertEqual(Decimal(0), fees)

    def test_degiro_unpairable_sell_raises(self):
        """
        With allow_partial=False (Degiro is long-only), a sell that cannot be
        fully paired against prior buys must raise instead of opening a short --
        so the data problem surfaces rather than becoming a phantom short.
        """
        # Pure short: a sell with no prior buy at all.
        pure_short = make_tx("2024-01-02", -100, price=Decimal("60.0"))
        with self.assertRaises(ValueError):
            optimize_transaction_pairing([pure_short], self.STRATEGIES, allow_partial=False)

        # Long-then-short cross: 30 long held, sell 100 (30 pair, 70 cannot).
        long_buy = make_tx("2024-01-02",   30, price=Decimal("50.0"))
        sell     = make_tx("2024-01-04", -100, price=Decimal("60.0"))
        with self.assertRaises(ValueError):
            optimize_transaction_pairing([long_buy, sell], self.STRATEGIES, allow_partial=False)


if __name__ == '__main__':
    unittest.main()
