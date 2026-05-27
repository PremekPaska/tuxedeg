tuxedeg

## Result table status values

- **OK** — the product was processed successfully. Zero income/cost means sales occurred in the tax year but netted zero, or the product had sales in a prior year that caused it to appear (e.g. a buy transaction in the current year keeps it in scope).
- **No sales** — the product had transactions in the tax year (e.g. a buy) but no sale events at all across its entire history.
- **ERROR** — an exception occurred while processing the product; income/cost are recorded as zero and processing continued with other products.

## SoldTtcShares column (shares only)

Counts **Sold Time Test Candidate shares**: shares sold in the tax year that were held longer than the `--months` threshold (default 12 months). The threshold mirrors the time test — `--months 36` counts exactly the shares that qualify for the Czech 3-year exemption under the chosen pairing. Because the pairing strategy decides which buy lots match each sale (and thus their holding periods), comparing this count across strategies helps pick one that maximizes long-held / tax-exempt shares. Hidden in options mode.
