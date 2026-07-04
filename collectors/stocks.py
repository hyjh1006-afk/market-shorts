# -*- coding: utf-8 -*-
"""yfinance로 워치리스트 종목의 수익률·거래량 급증을 계산한다."""
import math

import yfinance as yf

from config import STOCK_WATCHLIST


def _pct(cur: float, prev: float) -> float | None:
    if prev and not math.isnan(prev):
        return round((cur / prev - 1) * 100, 2)
    return None


def collect_stocks(watchlist: dict[str, str] | None = None) -> list[dict]:
    """종목별 1/7/30일 수익률과 거래량 배율을 반환한다.

    7일/30일은 달력일 기준이 아닌 거래일 근사(5거래일/21거래일)를 쓴다.
    """
    watchlist = watchlist or STOCK_WATCHLIST
    tickers = list(watchlist.keys())
    # 45 거래일이면 30일 수익률 + 20일 평균거래량 계산에 충분
    data = yf.download(tickers, period="3mo", interval="1d",
                       group_by="ticker", auto_adjust=True, progress=False)

    rows = []
    for ticker in tickers:
        try:
            df = data[ticker].dropna(subset=["Close"])
        except KeyError:
            continue
        if len(df) < 22:
            continue
        close = df["Close"]
        vol = df["Volume"]
        cur = float(close.iloc[-1])
        vol_avg20 = float(vol.iloc[-21:-1].mean())
        rows.append({
            "ticker": ticker,
            "name": watchlist[ticker],
            "price": round(cur, 2),
            "ret_1d": _pct(cur, float(close.iloc[-2])),
            "ret_7d": _pct(cur, float(close.iloc[-6])),
            "ret_30d": _pct(cur, float(close.iloc[-22])),
            "volume": int(vol.iloc[-1]),
            "vol_ratio": round(float(vol.iloc[-1]) / vol_avg20, 2) if vol_avg20 else None,
            "currency": "KRW" if ticker.endswith((".KS", ".KQ")) else "USD",
        })
    return rows


if __name__ == "__main__":
    for r in collect_stocks():
        print(r)
