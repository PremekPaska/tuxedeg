# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

import csv


def import_transactions(file_name: str):
    with open(file_name, encoding="utf8") as file:
        reader = csv.reader(file, delimiter=',')

        header = reader.__next__()

        date_index = header.index("Datum")
        product_index = header.index("Produkt")

        print(date_index, product_index)



def print_hi(name):
    # Use a breakpoint in the code line below to debug your script.
    print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print_hi('PyCharm')
    import_transactions("Transactions.csv")

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
