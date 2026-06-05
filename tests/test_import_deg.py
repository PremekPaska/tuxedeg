import unittest
import os
import tempfile

from decimal import Decimal

from import_deg import import_transactions, convert_to_transactions_deg, detect_decimal_separator, TRANSACTION_FEE_COLUMN
from import_utils import get_product_id_by_prefix
from optimizer import optimize_product, calculate_totals


class ImportTestCase(unittest.TestCase):
    TAX_YEAR = 2021
    STRATEGIES = {2021: "max_cost"}

    @staticmethod
    def import_test_transactions_en():
        if not os.path.exists('test_data'):
            os.chdir(os.path.dirname(__file__))
        return import_transactions("test_data/Transactions-deg-en-2021.csv")

    def convert_to_transactions(self, df_transactions, product_prefix: str):
        product_id = get_product_id_by_prefix(df_transactions, product_prefix, id_col="ISIN")
        transactions = convert_to_transactions_deg(df_transactions, product_id, self.TAX_YEAR)
        return transactions

    def test_import_en(self):
        df_transactions = self.import_test_transactions_en()
        self.assertEqual(88, df_transactions.shape[0])

    def test_conversion(self):
        df_transactions = self.import_test_transactions_en()

        product_id = get_product_id_by_prefix(df_transactions, "CLOUDFLARE", id_col="ISIN")
        transactions = convert_to_transactions_deg(df_transactions, product_id, self.TAX_YEAR)
        self.assertEqual(9, len(transactions))
        self.assertGreaterEqual(transactions[0].fee, 0)

    def test_calculate_tax(self):
        df_transactions = self.import_test_transactions_en()
        ts_cloudflare = self.convert_to_transactions(df_transactions, "CLOUDFLARE")

        report = optimize_product(ts_cloudflare, self.TAX_YEAR, self.STRATEGIES)
        self.assertEqual(2, len(report))

        income, cost, fees = calculate_totals(report, self.TAX_YEAR)
        self.assertEqual(Decimal('76573.86'), income)
        self.assertEqual(Decimal('27278.5890'), cost)
        self.assertEqual(Decimal('121.5375'), fees)

    def test_import_cz(self):
        df_transactions = import_transactions("test_data/Transactions-deg-cz-2019.csv")
        self.assertEqual(156, df_transactions.shape[0])

        product_id = get_product_id_by_prefix(df_transactions, "ADVANCED MICRO DEVICES", id_col="ISIN")
        tax_year = 2019
        transactions = convert_to_transactions_deg(df_transactions, product_id, tax_year)
        self.assertEqual(74, len(transactions))

        report = optimize_product(transactions, tax_year, {tax_year: "max_cost"})
        self.assertEqual(38, len(report))

        income, cost, fees = calculate_totals(report, tax_year)
        self.assertEqual(Decimal('93774.7573'), income)
        self.assertEqual(Decimal('76584.4204'), cost)
        self.assertEqual(Decimal('593.3456'), fees)


class DecimalSeparatorTestCase(unittest.TestCase):
    """The decimal separator is locale-dependent and must be sniffed from the
    data, not the (always-English) column names. Regression for the Irish export
    that uses '.' decimals + ',' thousands under new-format headers."""

    # New-format headers (Irish locale): period decimals, comma thousands. The
    # "1,234.5600" price exercises the thousands separator; the "-2.00" fee used
    # to be left as the string '-2.00', crashing on `-raw_fee`.
    HEADER = (
        "Date,Time,Product,ISIN,Reference exchange,Venue,Quantity,Price,,Local value,,"
        "Value EUR,Exchange rate,AutoFX Fee,Transaction and/or third party fees EUR,Total EUR,Order ID,\n"
    )
    # period decimals + comma thousands (Irish locale)
    IRISH_CSV = HEADER + (
        '10-01-2025,20:31,TEST CORP,US0000000001,NSY,XNAS,5,"1,234.5600",USD,"-6,172.80",USD,'
        '-6028.00,1.0239,-2.91,-2.00,-6030.91,uuid-0001,\n'
    )
    # comma decimals + period thousands, numeric fields quoted (Czech locale)
    CZECH_CSV = HEADER + (
        '10-01-2025,20:31,TEST CORP,US0000000001,NSY,XNAS,5,"1.234,5600",USD,"-6.172,80",USD,'
        '"-6028,00","1,0239","-2,91","-2,00","-6030,91",uuid-0001,\n'
    )

    def setUp(self):
        if not os.path.exists('test_data'):
            os.chdir(os.path.dirname(__file__))

    def _assert_parsed(self, csv_text, expected_sep):
        with tempfile.NamedTemporaryFile('w', suffix='.csv', encoding='utf8', delete=False) as f:
            f.write(csv_text)
            path = f.name
        self.addCleanup(os.unlink, path)

        self.assertEqual(expected_sep, detect_decimal_separator(path))

        df = import_transactions(path)
        # The fee column must be numeric, not left as strings like '-2.00' / '-2,00'.
        self.assertTrue(df[TRANSACTION_FEE_COLUMN].dtype.kind in 'fi')

        product_id = get_product_id_by_prefix(df, "TEST CORP", id_col="ISIN")
        transactions = convert_to_transactions_deg(df, product_id, 2025)
        self.assertEqual(1, len(transactions))
        tx = transactions[0]
        # Fee is flipped to positive and combined with AutoFX: 2.00 + 2.91 = 4.91.
        self.assertEqual(Decimal('2.00') + Decimal('2.91'), tx.fee)
        # Thousands separator parsed: price -> 1234.56, not 1.2345 or a string.
        self.assertEqual(Decimal('1234.5600').quantize(Decimal('0.000001')), tx.share_price)

    def test_detect_on_fixtures(self):
        self.assertEqual('.', detect_decimal_separator("test_data/Transactions-deg-en-2021.csv"))
        self.assertEqual('.', detect_decimal_separator("test_data/Transactions-deg-cz-2019.csv"))

    def test_irish_period_decimal_comma_thousands(self):
        self._assert_parsed(self.IRISH_CSV, '.')

    def test_czech_comma_decimal_period_thousands(self):
        self._assert_parsed(self.CZECH_CSV, ',')


if __name__ == '__main__':
    unittest.main()
