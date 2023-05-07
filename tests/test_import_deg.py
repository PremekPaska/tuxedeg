import unittest

from import_deg import import_transactions, convert_to_transactions
from main import get_isin


class ImportTestCase(unittest.TestCase):
    TAX_YEAR = 2021

    def test_import_en(self):
        df_transactions = import_transactions("test_data/Transactions-deg-en-2021.csv")
        self.assertEqual(88, df_transactions.shape[0])

    def test_conversions(self):
        df_transactions = import_transactions("test_data/Transactions-deg-en-2021.csv")

        product_id = get_isin(df_transactions, "CLOUDFLARE")
        transactions = convert_to_transactions(df_transactions, product_id, self.TAX_YEAR)
        self.assertEqual(9, len(transactions))


if __name__ == '__main__':
    unittest.main()
