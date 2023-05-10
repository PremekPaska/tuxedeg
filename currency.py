import decimal
from decimal import Decimal

FIRST_YEAR = 2017
LAST_YEAR = 2022


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
            Decimal('23.41')   # LAST_YEAR,
        ]
    elif from_curr == 'EUR':
        rates = [
            Decimal('26.29'),  # 2017
            Decimal('25.68'),
            Decimal('25.66'),
            Decimal('26.50'),  # 2020
            Decimal('25.65'),
            Decimal('24.54'),
        ]
    elif from_curr == 'CAD':
        rates = [
            Decimal('17.87'),  # 2017
            Decimal('16.74'),
            Decimal('17.32'),
            Decimal('17.23'),  # 2020
            Decimal('17.33'),
            Decimal('17.93')
        ]
    else:
        raise ValueError(f"Unsupported source currency: {from_curr}")

    if year < FIRST_YEAR or year > LAST_YEAR:
        raise ValueError(f"Year {year} is out of supported range ({FIRST_YEAR} to {LAST_YEAR}).")

    return rates[year - 2017]


def check_currency(currency: str):
    unified_fx_rate(LAST_YEAR, currency)
    return currency
