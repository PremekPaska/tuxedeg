import unittest
import os

from import_ibkr import load_stock_transactions
from transaction_ibkr import convert_to_transactions_ibkr
from pandas import DataFrame
from transaction import Transaction


class ImportTestCase(unittest.TestCase):
    TAX_YEAR = 2022

    @staticmethod
    def import_test_transactions() -> DataFrame:
        if not os.path.exists('test_data'):
            os.chdir(os.path.dirname(__file__))
        return load_stock_transactions(["test_data/U74_2022_test.csv"])

    def convert_to_transactions(self, df_transactions: DataFrame, symbol: str) -> list[Transaction]:
        txs = convert_to_transactions_ibkr(df_transactions, symbol, self.TAX_YEAR)
        return txs

    def test_import(self):
        df_transactions = self.import_test_transactions()
        self.assertEqual(278, df_transactions.shape[0])

    def ignore_test_conversion(self):
        df_txs = self.import_test_transactions()

        transactions = self.convert_to_transactions(df_txs, "MELI")
        self.assertEqual(4, len(transactions))
