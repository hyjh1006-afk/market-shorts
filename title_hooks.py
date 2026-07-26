# -*- coding: utf-8 -*-
"""데이터 기반 훅 제목 생성 (ai_monetization_lab 실험 E7 연동).

title_hooks.json의 패턴에 그날 스냅샷 데이터(급등락·거래량 급증)를 채워
클릭을 부르는 업로드 제목을 만든다.

안전 규칙: 어떤 이유로든 실패하면 None을 반환하고, 호출부는 기존
날짜형 기본 제목(_default_title)으로 동작한다. 파일을 지우거나
enabled=false면 완전히 비활성화된다.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "title_hooks.json"
MAX_LEN = 95  # 유튜브 제한(100자) 안전 마진


def _now_kst() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=9)


def _fmt(template: str, name: str, ret: float | None = None, ratio: float | None = None) -> str:
    return template.format(
        name=name,
        ret=f"{ret:+.1f}" if ret is not None else "",
        ratio=f"{ratio:.1f}" if ratio is not None else "",
    )


def build_hook_title(snapshot: dict) -> str | None:
    """스냅샷에서 가장 강한 신호 하나를 골라 훅 제목을 만든다. 실패 시 None."""
    try:
        if _now_kst().weekday() >= 5:
            return None  # 주말은 기존 '주간 결산' 제목 유지

        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not cfg.get("enabled", False):
            return None
        templates = cfg.get("templates", {})
        min_move = float(cfg.get("min_abs_move_pct", 3.0))
        min_vol = float(cfg.get("min_vol_ratio", 2.0))
        suffix = cfg.get("suffix", " #shorts")

        stocks = [s for s in snapshot.get("stocks", [])
                  if s.get("name") and s.get("ret_1d") is not None]
        coins = [c for c in snapshot.get("coins", [])
                 if c.get("name") and c.get("ret_1d") is not None]

        candidates: list[tuple[float, str, dict]] = []  # (신호 강도, 종류, 데이터)

        if stocks:
            top = max(stocks, key=lambda s: s["ret_1d"])
            bottom = min(stocks, key=lambda s: s["ret_1d"])
            if top["ret_1d"] >= min_move:
                candidates.append((abs(top["ret_1d"]), "big_gainer", top))
            if bottom["ret_1d"] <= -min_move:
                candidates.append((abs(bottom["ret_1d"]), "big_loser", bottom))
            spikes = [s for s in stocks if (s.get("vol_ratio") or 0) >= min_vol]
            if spikes:
                sp = max(spikes, key=lambda s: s["vol_ratio"])
                candidates.append((sp["vol_ratio"] * 1.5, "volume_spike", sp))
        if coins:
            ctop = max(coins, key=lambda c: c["ret_1d"])
            if ctop["ret_1d"] >= min_move * 1.5:  # 코인은 변동이 커서 문턱 상향
                candidates.append((ctop["ret_1d"] * 0.8, "coin_mover", ctop))

        if not candidates:
            return None

        _, kind, row = max(candidates, key=lambda x: x[0])
        pool = templates.get(kind) or []
        if not pool:
            return None
        title = _fmt(random.choice(pool), row["name"],
                     ret=row.get("ret_1d"), ratio=row.get("vol_ratio"))
        title = title.strip()
        if not title:
            return None
        if len(title) + len(suffix) > MAX_LEN:
            title = title[: MAX_LEN - len(suffix) - 1] + "…"
        return title + suffix
    except Exception:
        return None  # 어떤 오류든 기본 제목으로 폴백


if __name__ == "__main__":
    # 자가 테스트: python title_hooks.py
    fake = {
        "stocks": [
            {"name": "삼성전자", "ret_1d": 1.2, "vol_ratio": 1.1},
            {"name": "에코프로비엠", "ret_1d": 5.4, "vol_ratio": 3.2},
            {"name": "카카오", "ret_1d": -4.1, "vol_ratio": 1.9},
        ],
        "coins": [{"name": "솔라나", "ret_1d": 8.0}],
    }
    print("예시:", build_hook_title(fake))
