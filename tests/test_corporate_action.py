import unittest
from datetime import datetime
from decimal import Decimal
import pandas as pd

from corporate_action import apply_stock_splits_for_product
from transaction import Transaction


class SplitTests(unittest.TestCase):
    def _tx(self, symbol: str, t: datetime, qty: int, price: int) -> Transaction:
        """build a Transaction with zero fee/currency noise"""
        return Transaction(
            time=t,
            product_name=symbol,
            isin=symbol,
            count=qty,
            share_price=price,
            currency="USD",
            fee=0,
            fee_currency="USD",
        )

    def test_apply_split_simple(self):
        tx = self._tx("TSLA", datetime(2022, 1, 10), 10, 900)
        tx.apply_split(3, 1)                      # 3-for-1
        self.assertEqual(tx.count, 30)
        self.assertEqual(tx.remaining_count, 30)
        self.assertEqual(tx.share_price, Decimal("300"))

    def test_apply_split_fractional_raises(self):
        tx = self._tx("TSLA", datetime(2022, 1, 10), 7, 100)
        # 3/2 would leave 10.5 shares → error
        with self.assertRaises(ValueError):
            tx.apply_split(3, 2)

    def test_ignore_splits_before_first_trade(self):
        txs = [
            self._tx("AMZN", datetime(2022, 7, 1), 2, 2000),
        ]
        splits = pd.DataFrame(
            {
                "Symbol": ["AMZN"],
                "Report Date": ["2020-05-01"],  # older than trade
                "Numerator": [20],
                "Denominator": [1],
            }
        )
        apply_stock_splits_for_product(txs, splits, "AMZN", id_col="Symbol")
        self.assertEqual(txs[0].count, 2)  # unchanged

    def test_multiple_splits_cumulative(self):
        txs = [
            self._tx("TSLA", datetime(2020, 1, 1), 2, 1000),
        ]
        splits = pd.DataFrame(
            {
                "Symbol": ["TSLA", "TSLA"],
                "Report Date": ["2020-08-28", "2022-08-24"],
                "Numerator": [5, 3],           # 5-for-1 then 3-for-1
                "Denominator": [1, 1],
            }
        )
        apply_stock_splits_for_product(txs, splits, "TSLA", id_col="Symbol")
        # cumulative ratio = 15-for-1
        self.assertEqual(txs[0].count, 30)          # 2 * 15
        self.assertEqual(txs[0].share_price, Decimal("66.66666667").quantize(txs[0].share_price))  # 1000/15

    def test_split_affects_only_earlier_trades(self):
        old = self._tx("SHOP", datetime(2022, 5, 1), 3, 1200)
        new = self._tx("SHOP", datetime(2022, 8, 1), 3, 900)
        txs = [old, new]
        splits = pd.DataFrame(
            {
                "Symbol": ["SHOP"],
                "Report Date": ["2022-06-28"],  # between the two trades
                "Numerator": [10],
                "Denominator": [1],
            }
        )
        apply_stock_splits_for_product(txs, splits, "SHOP", id_col="Symbol")
        self.assertEqual(old.count, 30)     # adjusted
        self.assertEqual(new.count, 3)      # untouched

    def test_split_by_isin(self):
        old = self._tx("CA82509L1076", datetime(2022, 5, 1), 3, 1200)
        new = self._tx("CA82509L1076", datetime(2022, 8, 1), 3, 900)
        txs = [old, new]
        splits = pd.DataFrame(
            {
                "Symbol": ["SHOP"],
                "ISIN": ["CA82509L1076"],
                "Report Date": ["2022-06-28"],  # between the two trades
                "Numerator": [10],
                "Denominator": [1],
            }
        )
        apply_stock_splits_for_product(txs, splits, "CA82509L1076", id_col="ISIN")
        self.assertEqual(old.count, 30)     # adjusted
        self.assertEqual(new.count, 3)      # untouched


if __name__ == "__main__":
    unittest.main()
