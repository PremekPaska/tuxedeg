# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
from datetime import datetime

import pandas as pd


def eu_str_to_date(date_string: str) -> datetime:
    return datetime.strptime(date_string, '%d-%m-%Y')


def merge_date_time(date_string: str, time_string: str) -> datetime:
    return datetime.strptime(date_string + ' ' + time_string, '%d-%m-%Y %H:%M')


def import_transactions(file_name: str):
    df = pd.read_csv(file_name, encoding="utf8")
    print(df.columns)
    print(df.shape[0])
    # print(df.dtypes)
    # print(df.head())

    pd.set_option('display.max_columns', 12)
    pd.set_option('display.width', 200)

    # To be dropped
    df_nan = df[df['Datum'].isnull()]
    print(f"*** Dropping {df_nan.shape[0]} records with null/NaN 'Datum'. ***")
    print(df_nan)
    df = df[df['Datum'].notnull()]

    df['DateTime'] = df.apply(lambda row: merge_date_time(row['Datum'], row['Čas']), axis=1)

    df_roku = df[df['Produkt'].str.startswith('ROKU')]
    print("Roku")
    print(df_roku.shape[0])
    print(df_roku.sort_values('DateTime').head(5))




def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('PyCharm')
    import_transactions("Transactions.csv")

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
