# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

import pandas as pd


def import_transactions(file_name: str):
    df = pd.read_csv(file_name, encoding="utf8")
    print(df.columns)
    print(df.dtypes)
    print(df.head())

    df_tesla = df[df['Produkt'].str.startswith('TESLA')]
    print("Tesla")
    print(df_tesla.shape[0])
    print(df_tesla.sort_values('Datum').head(30))


def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('PyCharm')
    import_transactions("Transactions.csv")

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
