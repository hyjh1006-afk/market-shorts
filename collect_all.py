# -*- coding: utf-8 -*-
"""전체 수집 파이프라인을 CLI에서 실행한다 (스케줄러 등록용).

실행: python collect_all.py
"""
import sys

import db
from collectors.stocks import collect_stocks
from collectors.coins import collect_coins
from collectors.news import collect_news


def main() -> int:
    ok = True

    try:
        stocks = collect_stocks()
        db.save_stocks(stocks)
        print(f"[stocks] {len(stocks)} saved")
    except Exception as e:
        print(f"[stocks] FAILED: {e}")
        ok = False

    try:
        coins = collect_coins()
        db.save_coins(coins)
        print(f"[coins] {len(coins)} saved")
    except Exception as e:
        print(f"[coins] FAILED: {e}")
        ok = False

    try:
        news = collect_news()
        db.save_news(news)
        print(f"[news] {len(news)} saved")
        for n in news[:6]:
            print(f"  ({n['category']}) {n['title'][:60]}")
    except Exception as e:
        print(f"[news] FAILED: {e}")
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
