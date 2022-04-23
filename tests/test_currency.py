import unittest
from decimal import Decimal

from currency import unified_fx_rate


class CurrencyTestCase(unittest.TestCase):
    def test_unified_fx_rate(self):
        self.assertEqual(Decimal('21.72'), unified_fx_rate(2021, 'USD'))
        self.assertEqual(Decimal('23.18'), unified_fx_rate(2017, 'USD'))
        self.assertEqual(Decimal('26.50'), unified_fx_rate(2020, 'EUR'))

    def test_year_range(self):
        self.assertRaises(ValueError, unified_fx_rate, 2016, 'USD')
        self.assertRaises(ValueError, unified_fx_rate, 2035, 'USD')

    def test_currency_exception(self):
        self.assertRaises(ValueError, unified_fx_rate, 2021, 'DOGE')


if __name__ == '__main__':
    unittest.main()
