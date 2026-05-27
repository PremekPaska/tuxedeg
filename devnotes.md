# Dev notes

Scratchpad for ideas and context that don't belong in code or CLAUDE.md.

## Ideas

- **Months-held column in the pairings CSV** — Add a column into the result pairings
  showing after how many months the lot was sold (per open/buy leg: `(sale - buy)` in
  months). Complements the `SoldTtcShares` results-table column, which only counts shares
  over a threshold; this would show the actual holding period per lot.
  See `build_pairing_rows()` in `main.py`. _(session: time-test-candidates, 2026-05-27)_
