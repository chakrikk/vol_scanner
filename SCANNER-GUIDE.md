# Volume Scanner HH / LL — Quick Guide

## What it does

The scanner ranks stocks with unusually strong bullish (`HH`) or bearish (`LL`) intraday movement and shows the highest-volume qualifying option contract for each stock.

## Main columns

- **Signal** — `HH` means bullish/higher-high momentum; `LL` means bearish/lower-low momentum.
- **Net gain** — stock movement from the session open.
- **Change since scan** — change in Net gain from the previous snapshot.
- **Vol factor** — current stock volume divided by average volume.
- **Vol factor change** — change in Vol factor since the previous snapshot.
- **HH count** — structural higher-high count from the scanner data.
- **MaxVolOp** — selected highest-volume option that matches the signal direction: call for HH, put for LL.
- **OI / Option volume** — open interest and current option volume.
- **Vol/OI** — option volume divided by open interest.
- **Days to expiry** — calendar days remaining until expiration.
- **Score** — composite 0–100 score using movement, trend/volume, and option activity.
- **Grade** — `A+`, `B`, or `C`; low-quality `Discard` rows are removed.
- **TradeReady** — `YES` only when automated minimum checks pass.
- **Added at / Updated at** — first appearance and most recent refresh time.

## How to use it

1. Start with `HH` for bullish setups or `LL` for bearish setups.
2. Prefer higher scores and improving Net gain/Vol factor deltas.
3. Confirm the option direction: HH should use a call; LL should use a put.
4. Review DTE, OI, volume, and the Trade readiness checklist.
5. Before entering, manually verify bid/ask spread, delta, implied volatility, earnings/news, entry, stop, target, and position size.

## Refresh and downloads

The public page checks for a new published snapshot every 30 seconds. The local scanner generates the data; `Auto-Publish-Scanner.cmd` rebuilds the public CSV files, commits them, and pushes them to GitHub. Use **Download Excel CSV** to save the full dataset, including columns hidden from the on-screen grid.

## Important limitation

This is a research and decision-support tool, not a guarantee of profitable trades. Options can lose the entire premium; always use a defined risk limit and verify live quotes before trading.
