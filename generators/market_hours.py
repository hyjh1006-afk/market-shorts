# -*- coding: utf-8 -*-
"""정규장 개장 여부 판단 + 등락률 '기준' 문구 생성.

- 국내: 한국 정규장 09:00~15:30 KST (평일)
- 미국: 미국 동부 정규장 09:30~16:00 ET (서머타임 자동 반영) → KST로 환산 표기
- 공휴일/휴장은 '데이터의 마지막 거래일이 그 시장의 오늘이 아니면 휴장'으로 크로스체크
- 프리마켓/애프터마켓(시간외)은 정규장으로 치지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def now_kst() -> datetime:
    return datetime.now(KST)


def _in_session(local: datetime, start_min: int, end_min: int) -> bool:
    if local.weekday() >= 5:  # 토(5)·일(6)
        return False
    t = local.hour * 60 + local.minute
    return start_min <= t < end_min


def is_weekend(now: datetime | None = None) -> bool:
    """토·일(KST) 여부 — 주말엔 영상이 '주간 결산' 모드로 전환된다."""
    now = (now or now_kst()).astimezone(KST)
    return now.weekday() >= 5


def is_kr_regular_open(now: datetime | None = None) -> bool:
    now = now or now_kst()
    return _in_session(now.astimezone(KST), 9 * 60, 15 * 60 + 30)


def is_us_regular_open(now: datetime | None = None) -> bool:
    now = now or now_kst()
    # 미국 동부 시각으로 판단하면 서머타임이 자동 반영된다
    return _in_session(now.astimezone(ET), 9 * 60 + 30, 16 * 60)


def market_today(market: str, now: datetime | None = None) -> str:
    """그 시장의 '현지 오늘' 날짜 (YYYY-MM-DD). 공휴일 크로스체크용."""
    now = now or now_kst()
    tz = ET if market == "US" else KST
    return now.astimezone(tz).date().isoformat()


def _md(date_str: str) -> str:
    """'2026-07-07' → '7/7'"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{d.month}/{d.day}"
    except (ValueError, TypeError):
        return date_str


def basis_caption(
    market: str,
    prev_date: str,
    last_date: str,
    now: datetime | None = None,
) -> str:
    """등락률 기준 문구. market: 'KR' | 'US'.
    - 장중(정규장 open & 데이터 마지막=오늘): '기준: 전일 종가 → HH:MM KST 현재'
    - 그 외(마감/개장전/주말/휴장): '기준: {prev} 종가 → {last} 종가'
    """
    now = now or now_kst()
    is_open = is_us_regular_open(now) if market == "US" else is_kr_regular_open(now)
    live = is_open and (last_date == market_today(market, now))

    if live:
        hhmm = now.astimezone(KST).strftime("%H:%M")
        return f"기준: 전일 종가 → {hhmm} KST 현재"
    return f"기준: {_md(prev_date)} 종가 → {_md(last_date)} 종가"


def coin_caption(now: datetime | None = None) -> str:
    """코인 24H 롤링 기준 문구: '24H 기준: 7/7 12:30 → 7/8 12:30 KST'"""
    now = (now or now_kst()).astimezone(KST)
    from datetime import timedelta
    prev = now - timedelta(hours=24)
    return (f"24H 기준: {prev.month}/{prev.day} {prev.strftime('%H:%M')} "
            f"→ {now.month}/{now.day} {now.strftime('%H:%M')} KST")
