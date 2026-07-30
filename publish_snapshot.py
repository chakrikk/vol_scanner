from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


SCANNER_COLUMNS = ["Signal", "Ticker", "NetGainPct", "VolFactor", "Last", "Open", "High", "Low", "HHCount", "MaxVolOp", "OI", "OptionVolume", "VolOIRatio", "OptionLast", "PremiumEstimate", "DaysToExpiry", "Score", "Grade", "TradeReady", "AddedAt", "UpdatedAt"]


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def build_snapshot(source: Path, output: Path) -> tuple[int, int]:
    stocks = read_csv(source / "stock-template.csv")
    options = read_csv(source / "options-template.csv")
    if stocks.empty:
        raise RuntimeError(f"No stock data found in {source}")

    for column in ["close", "prevClose", "open", "high", "low", "volume", "avgVolume", "hhCount"]:
        if column in stocks:
            stocks[column] = pd.to_numeric(stocks[column], errors="coerce").fillna(0)
    stocks["NetGainPct"] = ((stocks["close"] - stocks["open"]) / stocks["open"].replace(0, pd.NA) * 100).fillna(0)
    stocks["VolFactor"] = (stocks["volume"] / stocks["avgVolume"].replace(0, pd.NA)).fillna(0)
    stocks["Signal"] = ""
    stocks.loc[stocks["NetGainPct"] > 0, "Signal"] = "HH"
    stocks.loc[stocks["NetGainPct"] < 0, "Signal"] = "LL"

    watchlist = stocks.rename(columns={"ticker": "Ticker", "close": "Last", "open": "Open", "high": "High", "low": "Low"})
    watchlist["% Change"] = ((stocks["close"] - stocks["prevClose"]) / stocks["prevClose"].replace(0, pd.NA) * 100).fillna(0)
    watchlist = watchlist[["Ticker", "Last", "% Change", "Open", "High", "Low"]].sort_values("% Change", ascending=False)

    scanner = pd.DataFrame(columns=SCANNER_COLUMNS)
    if not options.empty:
        for column in ["last", "volume", "openInterest"]:
            if column in options:
                options[column] = pd.to_numeric(options[column], errors="coerce").fillna(0)
        options = options[(options["volume"] > 0) & (options["openInterest"] > 0) & (options["last"] >= 0.10)].copy()
        if "type" in options.columns:
            direction = stocks[["ticker", "Signal"]].rename(columns={"Signal": "ExpectedSignal"})
            options = options.merge(direction, on="ticker", how="left")
            options["ExpectedType"] = options["ExpectedSignal"].map({"HH": "CALL", "LL": "PUT"})
            options = options[(options["ExpectedType"].isna()) | (options["type"].str.upper() == options["ExpectedType"])]
        if not options.empty:
            best = options.loc[options.groupby("ticker")["volume"].idxmax()].copy()
            best["VolOIRatio"] = (best["volume"] / best["openInterest"].replace(0, pd.NA)).fillna(0)
            best["PremiumEstimate"] = best["volume"] * best["last"] * 100
            best["DaysToExpiry"] = (pd.to_datetime(best["expiration"], errors="coerce").dt.normalize() - pd.Timestamp.now().normalize()).dt.days
            movement = (stocks["NetGainPct"].abs().clip(upper=5) / 5) * 40
            best["Score"] = 0.0
            best = best.rename(columns={"ticker": "Ticker", "contract": "MaxVolOp", "openInterest": "OI", "volume": "OptionVolume", "last": "OptionLast"})
            base = stocks.rename(columns={"ticker": "Ticker", "close": "Last", "open": "Open", "high": "High", "low": "Low", "hhCount": "HHCount"})
            scanner = base.merge(best[["Ticker", "MaxVolOp", "OI", "OptionVolume", "VolOIRatio", "OptionLast", "PremiumEstimate", "DaysToExpiry"]], on="Ticker", how="inner")
            scanner["MovementScore"] = (scanner["NetGainPct"].abs().clip(upper=5) / 5) * 40
            scanner["TrendScore"] = (scanner["VolFactor"].clip(upper=3) / 3) * 20 + (pd.to_numeric(scanner["HHCount"], errors="coerce").fillna(0).clip(upper=20) / 20) * 15
            scanner["OptionsScore"] = (scanner["VolOIRatio"].clip(upper=2) / 2) * 15 + (scanner["OptionVolume"].clip(upper=5000) / 5000) * 10
            scanner["Score"] = (scanner["MovementScore"] + scanner["TrendScore"] + scanner["OptionsScore"]).clip(upper=100).round(1)
            scanner["Grade"] = pd.cut(scanner["Score"], bins=[-float("inf"), 50, 70, 85, float("inf")], labels=["Discard", "C", "B", "A+"]).astype(str)
            scanner["TradeReady"] = ((scanner["Score"] >= 70) & (scanner["DaysToExpiry"] >= 7) & (scanner["OptionVolume"] >= 500) & (scanner["OI"] >= 500)).map({True: "YES", False: "NO"})
            scanner = scanner.drop(columns=["MovementScore", "TrendScore", "OptionsScore"])
            scanner = scanner[scanner["Score"] >= 50]
            scanner = scanner[scanner["Signal"] != ""].sort_values("VolFactor", ascending=False)

    output.mkdir(parents=True, exist_ok=True)
    previous = read_csv(output / "scanner-results.csv")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not scanner.empty:
        prior_added = {}
        if not previous.empty and {"Ticker", "MaxVolOp", "AddedAt"}.issubset(previous.columns):
            for row in previous.itertuples():
                stamp = str(row.AddedAt)
                if stamp.startswith(datetime.now(timezone.utc).date().isoformat()):
                    prior_added.setdefault(str(row.Ticker), stamp)
        scanner["AddedAt"] = [prior_added.get(str(row.Ticker), now) for row in scanner.itertuples()]
        scanner["UpdatedAt"] = now
        scanner = scanner[SCANNER_COLUMNS]
    watchlist.to_csv(output / "watchlist.csv", index=False)
    scanner.to_csv(output / "scanner-results.csv", index=False)
    return len(watchlist), len(scanner)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create credential-free public scanner CSV files.")
    parser.add_argument("--source", type=Path, required=True, help="Private scanner folder")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data")
    args = parser.parse_args()
    watchlist_rows, scanner_rows = build_snapshot(args.source.resolve(), args.output.resolve())
    print(f"Published {watchlist_rows} watchlist rows and {scanner_rows} scanner rows to {args.output.resolve()}")


if __name__ == "__main__":
    main()
