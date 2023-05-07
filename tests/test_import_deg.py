import unittest

from decimal import Decimal

from import_deg import import_transactions, convert_to_transactions
from main import get_isin
from optimizer import optimize_product, calculate_totals


class ImportTestCase(unittest.TestCase):
    TAX_YEAR = 2021

    @staticmethod
    def import_test_transactions_en():
        return import_transactions("test_data/Transactions-deg-en-2021.csv")

    def convert_to_transactions(self, df_transactions, product_prefix: str):
        product_id = get_isin(df_transactions, product_prefix)
        transactions = convert_to_transactions(df_transactions, product_id, self.TAX_YEAR)
        return transactions

    def test_import_en(self):
        df_transactions = self.import_test_transactions_en()
        self.assertEqual(88, df_transactions.shape[0])

    def test_conversion(self):
        df_transactions = self.import_test_transactions_en()

        product_id = get_isin(df_transactions, "CLOUDFLARE")
        transactions = convert_to_transactions(df_transactions, product_id, self.TAX_YEAR)
        self.assertEqual(9, len(transactions))

    def test_calculate_tax(self):
        df_transactions = self.import_test_transactions_en()
        ts_cloudflare = self.convert_to_transactions(df_transactions, "CLOUDFLARE")

        report = optimize_product(ts_cloudflare, self.TAX_YEAR)
        self.assertEqual(2, len(report))

        income, cost, fees = calculate_totals(report, self.TAX_YEAR)
        self.assertEqual(Decimal('76573.86'), income)
        self.assertEqual(Decimal('27278.5890'), cost)
        self.assertEqual(Decimal('121.5375'), fees)


if __name__ == '__main__':
    unittest.main()
