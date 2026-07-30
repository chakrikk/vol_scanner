from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SCANNER_CSV = DATA_DIR / "scanner-results.csv"
WATCHLIST_CSV = DATA_DIR / "watchlist.csv"

st.set_page_config(page_title="Volume Scanner HH / LL", page_icon=":material/candlestick_chart:", layout="wide")


@st.cache_data(ttl="30s", max_entries=4)
def read_public_csv(path: str, modified_ns: int) -> pd.DataFrame:
    del modified_ns
    csv_path = Path(path)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(csv_path)


def load_public_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    scanner_mtime = SCANNER_CSV.stat().st_mtime_ns if SCANNER_CSV.exists() else 0
    watchlist_mtime = WATCHLIST_CSV.stat().st_mtime_ns if WATCHLIST_CSV.exists() else 0
    return read_public_csv(str(SCANNER_CSV), scanner_mtime), read_public_csv(str(WATCHLIST_CSV), watchlist_mtime)


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return ("\ufeff" + frame.to_csv(index=False)).encode("utf-8")


def data_timestamp() -> datetime | None:
    times = [path.stat().st_mtime for path in (SCANNER_CSV, WATCHLIST_CSV) if path.exists()]
    return datetime.fromtimestamp(max(times), tz=timezone.utc) if times else None


def color_grid(frame: pd.DataFrame):
    def score_color(value):
        try:
            value = float(value)
            return "background-color: #86efac; color: #111827; font-weight: 700" if value >= 85 else "background-color: #bbf7d0; color: #111827; font-weight: 700" if value >= 70 else "background-color: #fef08a; color: #111827; font-weight: 700"
        except (TypeError, ValueError):
            return ""
    def delta_color(value):
        try:
            value = float(value)
            return "color: #087f5b; font-weight: 700" if value >= 1 else "color: #c92a2a; font-weight: 700" if value <= -1 else ""
        except (TypeError, ValueError):
            return ""
    styler = frame.style
    if "Score" in frame: styler = styler.map(score_color, subset=["Score"])
    if "ScoreDelta" in frame: styler = styler.map(delta_color, subset=["ScoreDelta"])
    if "NetGainDelta" in frame: styler = styler.map(delta_color, subset=["NetGainDelta"])
    if "NetGainPct" in frame: styler = styler.map(delta_color, subset=["NetGainPct"])
    if "VolFactorDelta" in frame: styler = styler.map(delta_color, subset=["VolFactorDelta"])
    bold_columns = [column for column in ["Ticker", "MaxVolOp", "Score"] if column in frame.columns]
    if bold_columns:
        styler = styler.set_properties(subset=bold_columns, **{"font-weight": "700"})
    return styler


st.title("Volume Scanner HH / LL")
st.caption("Public read-only market scanner. Schwab credentials remain on the publisher's computer.")

with st.sidebar:
    st.header("View controls")
    signal = st.segmented_control("Signal", ["All", "HH", "LL"], default="All", key="signal_filter")
    ticker_query = st.text_input("Filter ticker", placeholder="Ticker symbol", key="ticker_filter")
    minimum_factor = st.number_input("Minimum volume factor", min_value=0.0, value=0.0, step=0.1, key="minimum_factor")
    st.caption("The page checks for updated published data every 30 seconds.")
    with st.expander("Trade readiness checklist", expanded=True):
        st.markdown("""
**Required before entry**

- Score ≥ 70
- Correct directional contract: HH = call, LL = put
- Days to expiry ≥ 7
- Option price ≥ $0.10
- Option volume ≥ 500
- Open interest ≥ 500

**Still verify manually**

- Bid/ask spread ≤ 15%
- Delta in the planned range
- IV versus historical volatility
- Earnings or major-event risk
- Entry, stop, target, and position size

`TradeReady = YES` only reflects the automated checks above; it is not a trade recommendation.
""")


@st.fragment(run_every="30s")
def public_dashboard() -> None:
    scanner, watchlist = load_public_data()
    with st.sidebar:
        st.subheader(f"Watchlist · {len(watchlist)}")
        st.dataframe(
            watchlist, hide_index=True, height=520, key="public_watchlist",
            column_config={
                "Ticker": st.column_config.TextColumn(pinned=True),
                "Last": st.column_config.NumberColumn(format="$%.2f"),
                "% Change": st.column_config.NumberColumn(format="%.2f%%"),
                "Open": st.column_config.NumberColumn(format="$%.2f"),
                "High": st.column_config.NumberColumn(format="$%.2f"),
                "Low": st.column_config.NumberColumn(format="$%.2f"),
            },
        )
    if scanner.empty:
        st.warning("No public scanner snapshot has been published yet.")
        return

    shown = scanner.copy()
    if signal in {"HH", "LL"}:
        shown = shown[shown["Signal"] == signal]
    if ticker_query:
        shown = shown[shown["Ticker"].astype(str).str.contains(ticker_query.strip(), case=False, na=False)]
    if "VolFactor" in shown:
        shown = shown[pd.to_numeric(shown["VolFactor"], errors="coerce").fillna(0) >= minimum_factor]
    if "MaxVolOp" in shown and not shown.empty:
        with st.sidebar:
            st.subheader("Copy option contract")
            choices = shown[["Ticker", "MaxVolOp"]].drop_duplicates().sort_values("Ticker")
            choice = st.selectbox("Select ticker", choices["Ticker"].tolist(), key="copy_contract_ticker")
            contract = choices.loc[choices["Ticker"] == choice, "MaxVolOp"].iloc[0]
            st.code(str(contract), language=None)

    with st.container(horizontal=True):
        st.metric("Qualifying", len(shown), border=True)
        st.metric("HH bullish", int((shown["Signal"] == "HH").sum()), border=True)
        st.metric("LL bearish", int((shown["Signal"] == "LL").sum()), border=True)
        premium = pd.to_numeric(shown.get("PremiumEstimate", pd.Series(dtype=float)), errors="coerce").sum()
        st.metric("Premium notional", f"${premium / 1_000_000:,.1f}M", border=True)

    st.subheader("Scanner results")
    st.caption("Select a column heading to sort. Rows without a qualifying option contract are excluded.")
    table_view = shown.drop(columns=["Last", "Open", "High", "Low"], errors="ignore").copy()
    if "Grade" in table_view:
        table_view["Grade"] = table_view["Grade"].map({"A+": "🔥 A+", "B": "✅ B", "C": "⚠️ C"}).fillna(table_view["Grade"])
    if "TradeReady" in table_view:
        table_view["TradeReady"] = table_view["TradeReady"].map({"YES": "✅ YES", "NO": "⛔ NO"}).fillna(table_view["TradeReady"])
    st.dataframe(
        color_grid(table_view), hide_index=True, height=620, key="public_scanner_results",
        column_config={
            "Ticker": st.column_config.TextColumn(pinned=True),
            "NetGainPct": st.column_config.NumberColumn("Net gain", format="%.2f%%"),
            "NetGainDelta": st.column_config.NumberColumn("Change since scan", format="%.2f%%"),
            "VolFactor": st.column_config.NumberColumn("Vol factor", format="%.2f×"),
            "VolFactorDelta": st.column_config.NumberColumn("Vol factor change", format="%.2f×"),
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
            "DaysToExpiry": st.column_config.NumberColumn("Days to expiry", format="%d"),
            "Score": st.column_config.NumberColumn("Score", format="%.1f"),
            "ScoreDelta": st.column_config.NumberColumn("Score change", format="%.1f"),
            "Grade": st.column_config.TextColumn("Grade"),
            "TradeReady": st.column_config.TextColumn("Trade ready"),
            "AddedAt": st.column_config.DatetimeColumn("Added at"),
            "UpdatedAt": st.column_config.DatetimeColumn("Updated at"),
        },
    )
    st.download_button(
        ":material/download: Download Excel CSV", data=csv_bytes(shown),
        file_name=f"volume-scanner-results-{datetime.now():%Y%m%d-%H%M%S}.csv",
        mime="text/csv", width="content",
    )
    updated = data_timestamp()
    if updated:
        st.caption(f"Published {updated.astimezone():%Y-%m-%d %I:%M:%S %p %Z}. Educational/research use only.")


public_dashboard()
