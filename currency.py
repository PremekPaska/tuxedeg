import decimal
from decimal import Decimal

FIRST_YEAR = 2017
LAST_YEAR = 2025


# sources
# https://www.kodap.cz/cs/pro-vas/prehledy/jednotny-kurz/jednotne-kurzy-men-stanovene-ministerstvem-financi-prehled.html
# https://www.kurzy.cz/kurzy-men/jednotny-kurz/2017/

def unified_fx_rate(year: int, from_curr: str, to_curr: str = 'CZK') -> decimal:
    if to_curr != 'CZK':
        raise ValueError(f"Unsupported target currency: {to_curr}")

    if from_curr == 'USD':
        rates = [
            Decimal('23.18'),  # 2017 == FIRST_YEAR, TODO: add a couple more previous years
            Decimal('21.78'),
            Decimal('22.93'),
            Decimal('23.14'),  # 2020
            Decimal('21.72'),
            Decimal('23.41'),
            Decimal('22.14'),  # 2023
            Decimal('23.28'),
            Decimal('21.84'),
            Decimal('22.00'),  # LAST_YEAR; TODO: Update!
        ]
    elif from_curr == 'EUR':
        rates = [
            Decimal('26.29'),  # 2017
            Decimal('25.68'),
            Decimal('25.66'),
            Decimal('26.50'),  # 2020
            Decimal('25.65'),
            Decimal('24.54'),
            Decimal('23.97'),  # 2023
            Decimal('25.16'),
            Decimal('24.66'),
            Decimal('24.50'),   # LAST_YEAR; TODO: Update!
        ]
    elif from_curr == 'CAD':
        rates = [
            Decimal('17.87'),  # 2017
            Decimal('16.74'),
            Decimal('17.32'),
            Decimal('17.23'),  # 2020
            Decimal('17.33'),
            Decimal('17.93'),
            Decimal('16.40'),  # 2023
            Decimal('16.96'),
            Decimal('15.61'),
            Decimal('15.50'),   # LAST_YEAR; (Placeholder)
        ]
    else:
        raise ValueError(f"Unsupported source currency: {from_curr}")

    if year < FIRST_YEAR or year > LAST_YEAR:
        raise ValueError(f"Year {year} is out of supported range ({FIRST_YEAR} to {LAST_YEAR}).")

    return rates[year - 2017]


def check_currency(currency: str):
    unified_fx_rate(LAST_YEAR, currency)
    return currency
