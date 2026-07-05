# -*- coding: utf-8 -*-
"""SQLite 저장소: 일자별 시장 스냅샷과 뉴스를 보관한다."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_snapshot (
    snap_date   TEXT,
    ticker      TEXT,
    name        TEXT,
    price       REAL,
    ret_1d      REAL,
    ret_7d      REAL,
    ret_30d     REAL,
    volume      INTEGER,
    vol_ratio   REAL,       -- 당일 거래량 / 20일 평균
    currency    TEXT,
    PRIMARY KEY (snap_date, ticker)
);
CREATE TABLE IF NOT EXISTS coin_snapshot (
    snap_date   TEXT,
    coin_id     TEXT,
    symbol      TEXT,
    name        TEXT,
    price_usd   REAL,
    ret_1d      REAL,
    ret_7d      REAL,
    ret_30d     REAL,
    volume_usd  REAL,
    market_cap  REAL,
    PRIMARY KEY (snap_date, coin_id)
);
CREATE TABLE IF NOT EXISTS news (
    snap_date   TEXT,
    category    TEXT,
    title       TEXT,
    link        TEXT,
    source      TEXT,
    published   TEXT,
    PRIMARY KEY (snap_date, link)
);
CREATE TABLE IF NOT EXISTS generated_content (
    created_at  TEXT DEFAULT (datetime('now', 'localtime')),
    snap_date   TEXT,
    kind        TEXT,       -- 'x_post' | 'shorts_script' | 'card_image'
    content     TEXT        -- 텍스트 본문 또는 이미지 파일 경로
);
"""


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # 마이그레이션: 기존 DB에 score 컬럼이 없으면 추가
    try:
        conn.execute("ALTER TABLE news ADD COLUMN score REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    return conn


def today() -> str:
    """한국시간 기준 오늘. GitHub Actions(UTC 서버)에서 돌아도 날짜가 밀리지 않는다.
    (영상 첫 화면 날짜가 하루 전으로 찍히던 버그의 원인 — 2026-07-05 수정)"""
    return (datetime.now(timezone.utc) + timedelta(hours=9)).date().isoformat()


def save_stocks(rows: list[dict], snap_date: str | None = None):
    snap_date = snap_date or today()
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO stock_snapshot
               (snap_date, ticker, name, price, ret_1d, ret_7d, ret_30d, volume, vol_ratio, currency)
               VALUES (:snap_date, :ticker, :name, :price, :ret_1d, :ret_7d, :ret_30d, :volume, :vol_ratio, :currency)""",
            [{**r, "snap_date": snap_date} for r in rows],
        )


def save_coins(rows: list[dict], snap_date: str | None = None):
    snap_date = snap_date or today()
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO coin_snapshot
               (snap_date, coin_id, symbol, name, price_usd, ret_1d, ret_7d, ret_30d, volume_usd, market_cap)
               VALUES (:snap_date, :coin_id, :symbol, :name, :price_usd, :ret_1d, :ret_7d, :ret_30d, :volume_usd, :market_cap)""",
            [{**r, "snap_date": snap_date} for r in rows],
        )


def save_news(rows: list[dict], snap_date: str | None = None):
    snap_date = snap_date or today()
    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO news
               (snap_date, category, title, link, source, published, score)
               VALUES (:snap_date, :category, :title, :link, :source, :published, :score)""",
            [{"score": 0, **r, "snap_date": snap_date} for r in rows],
        )


def load_snapshot(snap_date: str | None = None) -> dict:
    """지정일(기본 오늘)의 주식/코인/뉴스를 한 번에 읽는다."""
    snap_date = snap_date or today()
    with get_conn() as conn:
        stocks = [dict(r) for r in conn.execute(
            "SELECT * FROM stock_snapshot WHERE snap_date=? ORDER BY ret_1d DESC", (snap_date,))]
        coins = [dict(r) for r in conn.execute(
            "SELECT * FROM coin_snapshot WHERE snap_date=? ORDER BY ret_1d DESC", (snap_date,))]
        news = [dict(r) for r in conn.execute(
            "SELECT * FROM news WHERE snap_date=? ORDER BY score DESC, published DESC", (snap_date,))]
    return {"date": snap_date, "stocks": stocks, "coins": coins, "news": news}


def save_generated(kind: str, content: str, snap_date: str | None = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO generated_content (snap_date, kind, content) VALUES (?, ?, ?)",
            (snap_date or today(), kind, content),
        )


def available_dates() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT snap_date FROM stock_snapshot ORDER BY snap_date DESC").fetchall()
    return [r["snap_date"] for r in rows]
