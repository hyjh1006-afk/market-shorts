# -*- coding: utf-8 -*-
"""CoinGecko 무료 API로 시총 상위 코인의 시세·등락률을 수집한다."""
import requests

from config import COIN_TOP_N

API = "https://api.coingecko.com/api/v3/coins/markets"


def collect_coins(top_n: int | None = None) -> list[dict]:
    """시총 상위 top_n개 코인의 1/7/30일 등락률을 반환한다."""
    top_n = top_n or COIN_TOP_N
    resp = requests.get(API, params={
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": top_n,
        "page": 1,
        "price_change_percentage": "24h,7d,30d",
    }, timeout=20)
    resp.raise_for_status()

    rows = []
    for c in resp.json():
        rows.append({
            "coin_id": c["id"],
            "symbol": c["symbol"].upper(),
            "name": c["name"],
            "price_usd": c["current_price"],
            "ret_1d": _r(c.get("price_change_percentage_24h_in_currency")),
            "ret_7d": _r(c.get("price_change_percentage_7d_in_currency")),
            "ret_30d": _r(c.get("price_change_percentage_30d_in_currency")),
            "volume_usd": c.get("total_volume"),
            "market_cap": c.get("market_cap"),
        })
    return rows


def _r(v):
    return round(v, 2) if v is not None else None


if __name__ == "__main__":
    for r in collect_coins():
        print(r)
