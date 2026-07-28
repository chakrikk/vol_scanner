from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
import streamlit as st


ROOT = Path(__file__).resolve().parent
STOCK_CSV = ROOT / "stock-template.csv"
OPTION_CSV = ROOT / "options-template.csv"
BACKEND_SCAN_URL = "http://127.0.0.1:18766/api/scan"
PUBLIC_MODE = True

st.set_page_config(page_title="Volume Scanner HH / LL", page_icon=":material/candlestick_chart:", layout="wide")


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path)


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    stocks = read_csv(STOCK_CSV)
    options = read_csv(OPTION_CSV)
    for column in ["close", "prevClose", "open", "high", "low", "volume", "avgVolume", "hhCount"]:
        if column in stocks:
            stocks[column] = pd.to_numeric(stocks[column], errors="coerce").fillna(0)
    for column in ["strike", "last", "volume", "openInterest"]:
        if column in options:
            options[column] = pd.to_numeric(options[column], errors="coerce").fillna(0)
    return stocks, options


def refresh_backend() -> dict:
    payload = {
        "avgVolLength": st.session_state.avg_length,
        "volFactorThreshold": st.session_state.vol_factor,
        "netGainThreshold": st.session_state.net_gain,
        "volumeMin": st.session_state.option_volume,
        "oiMin": st.session_state.oi_min,
        "ratioMin": st.session_state.ratio_min,
    }
    response = requests.post(BACKEND_SCAN_URL, json=payload, timeout=600)
    response.raise_for_status()
    return response.json()


def scanner_results(stocks: pd.DataFrame, options: pd.DataFrame) -> pd.DataFrame:
    if stocks.empty:
        return pd.DataFrame()
    work = stocks.copy()
    work["NetGainPct"] = ((work["close"] - work["open"]) / work["open"].replace(0, pd.NA) * 100).fillna(0)
    work["VolFactor"] = (work["volume"] / work["avgVolume"].replace(0, pd.NA)).fillna(0)
    gain, factor = st.session_state.net_gain, st.session_state.vol_factor
    work["Signal"] = ""
    work.loc[(work["NetGainPct"] > gain) & (work["VolFactor"] > factor), "Signal"] = "HH"
    work.loc[(work["NetGainPct"] < -gain) & (work["VolFactor"] > factor), "Signal"] = "LL"
    work = work[work["Signal"] != ""]
    if work.empty or options.empty:
        return pd.DataFrame()

    opts = options.copy()
    ratio = opts["volume"] / opts["openInterest"].replace(0, pd.NA)
    opts = opts[
        (opts["volume"] >= st.session_state.option_volume)
        & (opts["openInterest"] >= st.session_state.oi_min)
        & ((st.session_state.ratio_min <= 0) | (ratio >= st.session_state.ratio_min))
    ]
    if opts.empty:
        return pd.DataFrame()
    best = opts.loc[opts.groupby("ticker")["volume"].idxmax()].copy()
    best["VolOIRatio"] = (best["volume"] / best["openInterest"].replace(0, pd.NA)).fillna(0)
    best["PremiumEstimate"] = best["volume"] * best["last"] * 100
    best["Rocket"] = best["VolOIRatio"] >= 1
    best = best.rename(
        columns={
            "ticker": "Ticker",
            "contract": "MaxVolOp",
            "openInterest": "OI",
            "volume": "OptionVolume",
            "last": "OptionLast",
        }
    )
    work = work.rename(
        columns={
            "ticker": "Ticker",
            "close": "Last",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "hhCount": "HHCount",
        }
    )
    merged = work.merge(
        best[["Ticker", "MaxVolOp", "OI", "OptionVolume", "VolOIRatio", "OptionLast", "PremiumEstimate", "Rocket"]],
        on="Ticker",
        how="inner",
    )
    return merged[
        ["Signal", "Ticker", "NetGainPct", "VolFactor", "Last", "Open", "High", "Low", "HHCount", "MaxVolOp", "OI", "OptionVolume", "VolOIRatio", "OptionLast", "PremiumEstimate", "Rocket"]
    ].sort_values("VolFactor", ascending=False)


def watchlist_frame(stocks: pd.DataFrame) -> pd.DataFrame:
    if stocks.empty:
        return pd.DataFrame()
    frame = stocks.copy()
    frame["% Change"] = ((frame["close"] - frame["prevClose"]) / frame["prevClose"].replace(0, pd.NA) * 100).fillna(0)
    return frame.rename(columns={"ticker": "Ticker", "close": "Last", "open": "Open", "high": "High", "low": "Low"})[
        ["Ticker", "Last", "% Change", "Open", "High", "Low"]
    ].sort_values("% Change", ascending=False)


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return ("\ufeff" + frame.drop(columns=["Rocket"], errors="ignore").to_csv(index=False)).encode("utf-8")


st.title("Volume Scanner HH / LL")
if PUBLIC_MODE:
    st.caption("Public read-only snapshot of the scanner. Credentials and Schwab connectivity remain on the owner's computer.")
else:
    st.caption("Same-time relative volume, session-open HH/LL signals, and highest-volume qualifying options. Read-only Schwab market data.")

with st.sidebar:
    st.header("Scanner controls")
    st.number_input("Average volume length", min_value=2, max_value=20, value=20, step=1, key="avg_length")
    st.number_input("Minimum volume factor", min_value=0.0, value=1.0, step=0.1, key="vol_factor")
    st.number_input("Minimum NetGain %", min_value=0.0, value=0.5, step=0.1, key="net_gain")
    st.number_input("Minimum option volume", min_value=0, value=500, step=50, key="option_volume")
    st.number_input("Minimum OI", min_value=0, value=50, step=10, key="oi_min")
    st.number_input("Minimum Vol/OI (0 = any)", min_value=0.0, value=0.0, step=0.1, key="ratio_min")
    st.toggle("Auto refresh", value=False, key="auto_refresh")
    st.number_input("Refresh seconds", min_value=30, value=60, step=30, key="refresh_seconds")
    manual_refresh = st.button(":material/refresh: Refresh TOS / Schwab", type="primary", width="stretch", disabled=PUBLIC_MODE)
    if PUBLIC_MODE:
        st.info("Public mode displays the latest published snapshot. Run the local scanner to publish new CSV files.")
    st.divider()

if manual_refresh and not PUBLIC_MODE:
    with st.status("Refreshing Schwab market data…", expanded=True) as status:
        try:
            info = refresh_backend()
            status.write(f"Processed {info['symbols']} symbols and {info['contractsChecked']:,} option contracts.")
            status.update(label=f"Saved {info['snapshot']}", state="complete", expanded=False)
            st.session_state.last_refresh = time.time()
        except Exception as exc:
            status.update(label="Refresh failed", state="error")
            st.error(str(exc))


@st.fragment(run_every=st.session_state.refresh_seconds if st.session_state.auto_refresh else None)
def live_dashboard() -> None:
    if st.session_state.auto_refresh:
        last = st.session_state.get("last_refresh", 0.0)
        if not PUBLIC_MODE and time.time() - last >= st.session_state.refresh_seconds:
            with st.status("Auto-refreshing Schwab market data…", expanded=False):
                try:
                    refresh_backend()
                    st.session_state.last_refresh = time.time()
                except Exception as exc:
                    st.warning(f"Auto refresh failed: {exc}")

    stocks, options = load_frames()
    watch = watchlist_frame(stocks)
    with st.sidebar:
        st.subheader(f"Watchlist · {len(watch)}")
        st.dataframe(
            watch,
            hide_index=True,
            height=520,
            key="streamlit_watchlist",
            column_config={
                "Ticker": st.column_config.TextColumn(pinned=True),
                "Last": st.column_config.NumberColumn(format="$%.2f"),
                "% Change": st.column_config.NumberColumn(format="%.2f%%"),
                "Open": st.column_config.NumberColumn(format="$%.2f"),
                "High": st.column_config.NumberColumn(format="$%.2f"),
                "Low": st.column_config.NumberColumn(format="$%.2f"),
            },
        )

    results = scanner_results(stocks, options)
    side = st.segmented_control("Signal", ["All", "HH", "LL"], default="All", key="signal_filter")
    query = st.text_input("Filter ticker", placeholder="Ticker symbol", key="ticker_filter")
    shown = results.copy()
    if side in {"HH", "LL"} and "Signal" in shown.columns:
        shown = shown[shown["Signal"] == side]
    if query and "Ticker" in shown.columns:
        shown = shown[shown["Ticker"].str.contains(query.strip(), case=False, na=False)]

    with st.container(horizontal=True):
        st.metric("Qualifying", len(results), border=True)
        st.metric("HH bullish", int((results.get("Signal", pd.Series(dtype=str)) == "HH").sum()), border=True)
        st.metric("LL bearish", int((results.get("Signal", pd.Series(dtype=str)) == "LL").sum()), border=True)
        st.metric("Premium notional", f"${results.get('PremiumEstimate', pd.Series(dtype=float)).sum()/1_000_000:,.1f}M", border=True)

    st.subheader("Scanner results")
    st.caption("Select any column heading to sort. Rows without a qualifying option contract are excluded.")
    display = shown.drop(columns=["Rocket"], errors="ignore")
    if display.empty and len(display.columns) == 0:
        st.info("No qualifying HH/LL contracts are present in the published snapshot.")
    else:
        st.dataframe(
            display,
            hide_index=True,
            height=620,
            key="streamlit_scanner_results",
            column_config={
            "Ticker": st.column_config.TextColumn(pinned=True),
            "NetGainPct": st.column_config.NumberColumn("Net gain", format="%.2f%%"),
            "VolFactor": st.column_config.NumberColumn("Vol factor", format="%.2f×"),
            "Last": st.column_config.NumberColumn(format="$%.2f"),
            "Open": st.column_config.NumberColumn(format="$%.2f"),
            "High": st.column_config.NumberColumn(format="$%.2f"),
            "Low": st.column_config.NumberColumn(format="$%.2f"),
            "HHCount": st.column_config.NumberColumn("HH count", format="%d"),
            "OI": st.column_config.NumberColumn(format="%d"),
            "OptionVolume": st.column_config.NumberColumn("Option volume", format="%d"),
            "VolOIRatio": st.column_config.NumberColumn("Vol/OI", format="%.2f×"),
            "OptionLast": st.column_config.NumberColumn("Option last", format="$%.2f"),
            "PremiumEstimate": st.column_config.NumberColumn("Premium estimate", format="$%.2f"),
            },
        )
    st.download_button(
        ":material/download: Download Excel CSV",
        data=csv_bytes(shown),
        file_name=f"volume-scanner-results-{datetime.now():%Y%m%d-%H%M%S}.csv",
        mime="text/csv",
        width="content",
    )
    if STOCK_CSV.exists():
        st.caption(f"Snapshot generated {datetime.fromtimestamp(STOCK_CSV.stat().st_mtime):%Y-%m-%d %I:%M:%S %p}. Educational/research use only.")


live_dashboard()
