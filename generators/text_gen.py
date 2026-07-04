# -*- coding: utf-8 -*-
"""시장 스냅샷 → Shorts 대본 / LLM 프롬프트 생성.

핵심 원칙: 시청자는 항상 "그래서 돈이 어디로 가고 있는데?"를 묻고 있다.
숫자 나열이 아니라 뉴스 해석과 돈의 흐름이 콘텐츠의 중심이다.
'관심 구간', '관찰 필요', '돈의 흐름 확인' 같은 중립 표현을 쓴다.
"""
from config import SECTOR_MAP, VOLUME_SPIKE_RATIO


# ── 데이터 요약 헬퍼 ─────────────────────────────────────────

def top_movers(rows: list[dict], key: str = "ret_1d", n: int = 3) -> list[dict]:
    valid = [r for r in rows if r.get(key) is not None]
    return sorted(valid, key=lambda r: r[key], reverse=True)[:n]


def volume_spikes(stocks: list[dict], ratio: float = VOLUME_SPIKE_RATIO) -> list[dict]:
    spikes = [s for s in stocks if (s.get("vol_ratio") or 0) >= ratio]
    return sorted(spikes, key=lambda s: s["vol_ratio"], reverse=True)


def _fmt_pct(v) -> str:
    """화면 표시용 — 소수점 유지."""
    if v is None:
        return "-"
    return f"{'+' if v >= 0 else ''}{v}%"


def spoken_pct(v) -> str:
    """음성 대본용 — 반올림해서 '약 11% 상승' 형태로."""
    if v is None:
        return ""
    n = round(abs(v))
    direction = "상승" if v >= 0 else "하락"
    return f"약 {n}% {direction}"


def dominant_sector(stocks: list[dict]) -> tuple[str | None, list[str]]:
    """상승 상위 종목들의 섹터를 집계해 오늘 돈이 몰린 섹터를 추정한다."""
    movers = top_movers(stocks, "ret_1d", 5)
    scores: dict[str, float] = {}
    names: dict[str, list[str]] = {}
    for s in movers:
        ret = s.get("ret_1d") or 0
        if ret <= 0:
            continue
        sec = SECTOR_MAP.get(s["ticker"])
        if not sec:
            continue
        scores[sec] = scores.get(sec, 0) + ret
        names.setdefault(sec, []).append(s["name"])
    if not scores:
        return None, []
    top = max(scores, key=scores.get)
    return top, names[top]


# 섹터와 뉴스 제목을 연결하는 검색어 (섹터 관련 뉴스에 가점)
SECTOR_NEWS_TERMS = {
    "AI·반도체": ["반도체", "hbm", "칩", "chip", "semiconductor", "ai", "엔비디아",
                "nvidia", "하이닉스", "hynix", "삼성", "samsung", "tsmc", "마이크론",
                "micron", "openai", "anthropic", "데이터센터", "gpu"],
    "2차전지": ["배터리", "2차전지", "전기차", "ev", "리튬", "양극재", "battery"],
    "자동차·모빌리티": ["자동차", "전기차", "모빌리티", "현대차", "테슬라", "tesla", "자율주행"],
    "플랫폼·AI서비스": ["네이버", "naver", "카카오", "kakao", "플랫폼", "ai"],
    "빅테크·AI": ["ai", "애플", "apple", "구글", "google", "메타", "meta",
                "마이크로소프트", "microsoft", "아마존", "amazon", "openai", "anthropic"],
}


def key_news(news: list[dict], n: int = 3, sector: str | None = None) -> list[dict]:
    """투자 관련성 점수 상위 뉴스. sector를 주면 그 섹터 관련 뉴스에 가점."""
    terms = SECTOR_NEWS_TERMS.get(sector, []) if sector else []
    scored = []
    for x in news:
        s = x.get("score") or 0
        if s <= 0:
            continue
        title = x["title"].lower()
        if any(t in title for t in terms):
            s += 3
        scored.append((s, x))
    scored.sort(key=lambda p: p[0], reverse=True)
    return [x for _, x in scored[:n]] or news[:n]


def _stock_line(s: dict) -> str:
    return f"{s['name']}: 1일 {_fmt_pct(s['ret_1d'])} / 7일 {_fmt_pct(s['ret_7d'])} / 30일 {_fmt_pct(s['ret_30d'])}"


def _coin_line(c: dict) -> str:
    return f"{c['name']}({c['symbol']}): 24h {_fmt_pct(c['ret_1d'])} / 7일 {_fmt_pct(c['ret_7d'])}"


def build_data_block(snapshot: dict) -> str:
    """LLM 프롬프트에 넣을 시장 데이터 요약 블록."""
    stocks, coins, news = snapshot["stocks"], snapshot["coins"], snapshot["news"]
    sector, sec_names = dominant_sector(stocks)

    lines = ["[주식 - 1일 수익률 상위]"]
    lines += [_stock_line(s) for s in top_movers(stocks, "ret_1d", 5)]
    lines.append("\n[거래량 급증 (20일 평균 대비)]")
    lines += [f"{s['name']}: {s['vol_ratio']}배" for s in volume_spikes(stocks)[:5]] or ["없음"]
    lines.append("\n[코인 - 24h 상승률 상위]")
    lines += [_coin_line(c) for c in top_movers(coins, "ret_1d", 5)]
    lines.append("\n[투자자 관심 뉴스 (관련성 점수 높은 순)]")
    lines += [f"({x['category']}) {x['title']}" for x in key_news(news, 8, sector)]
    if sector:
        lines.append(f"\n[오늘 자금이 몰린 것으로 추정되는 섹터] {sector} ({', '.join(sec_names)})")
    return "\n".join(lines)


# ── YouTube Shorts 대본 (템플릿 — AI 키 없을 때 대체용) ──────

def generate_shorts_script(snapshot: dict) -> str:
    stocks, coins, news = snapshot["stocks"], snapshot["coins"], snapshot["news"]
    date = snapshot["date"]
    sector, sec_names = dominant_sector(stocks)
    movers = top_movers(stocks, "ret_1d", 3)
    coin_movers = top_movers(coins, "ret_1d", 2)
    top_news = key_news(news, 2, sector)

    hook = (f"오늘 시장, 그냥 오른 게 아닙니다. 돈이 {sector} 쪽으로 다시 몰렸습니다."
            if sector else "오늘 시장에서 돈이 어디로 움직였는지 1분으로 정리합니다.")

    parts = [f"[Shorts 대본] {date} 시장 브리핑", "", "(0~3초 · 후킹)", hook, ""]

    parts.append("(3~10초 · 급등 요약 — 빠르게 치고 지나가기)")
    quick = ", ".join(f"{s['name']} {spoken_pct(s['ret_1d'])}" for s in movers)
    coin_quick = "와 ".join(c["symbol"] for c in coin_movers)
    parts.append(f"{quick}. 코인에서는 {coin_quick}가 강했습니다.")
    parts.append("")

    parts.append("(10~40초 · 핵심 뉴스 — 왜 중요한지 설명)")
    for i, item in enumerate(top_news, 1):
        parts.append(f"{'첫' if i == 1 else '두'} 번째 뉴스. {item['title']}.")
    if sector:
        parts.append(f"이 흐름은 {sector} 밸류체인과 직접 연결될 수 있습니다. "
                     f"돈이 실제로 이 방향으로 이어지는지가 핵심입니다.")
    else:
        parts.append("이 뉴스들이 어느 섹터로 돈을 움직이는지가 핵심입니다.")
    parts.append("")

    parts.append("(40~55초 · 그래서 뭘 관찰할까)")
    if sector and sec_names:
        parts.append(f"오늘 기준 관심 구간은 {sector}입니다. "
                     f"{', '.join(sec_names)} 중심으로 거래량과 뉴스 지속성 확인이 필요합니다.")
    else:
        parts.append("오늘 급등한 종목들의 거래량이 내일도 이어지는지, 돈의 흐름 확인이 필요합니다.")
    parts.append("")

    parts.append("(마지막 3초 · 리스크)")
    parts.append("단기 급등주는 변동성이 큽니다. 추격매수보다 뉴스 지속성과 거래량을 같이 보세요.")
    return "\n".join(parts)


# ── LLM 프롬프트 ─────────────────────────────────────────────

def build_llm_prompt(snapshot: dict, kind: str = "shorts_script") -> str:
    task = """위 데이터로 YouTube Shorts용 45~60초 한국어 내레이션 대본을 작성해줘.

대본 구조 (반드시 이 순서와 시간 배분):
- (0~3초) 후킹 문장: "오늘 시장, 그냥 오른 게 아니라 돈이 ○○ 쪽으로 몰렸습니다" 같은 식으로 시선을 잡는다
- (3~10초) 급등 주식/코인 빠르게 언급만: 이 구간은 짧게. 숫자는 반올림해서 읽는다 ("SK하이닉스 약 11% 상승")
- (10~40초) 핵심 뉴스 1~2개: 가장 많은 시간을 쓴다. 제목만 읽지 말고 왜 중요한지, 시장/섹터/종목에 어떤 영향을 줄 수 있는지 설명한다
- (40~55초) 그래서 어떤 섹터/종목/코인을 관찰할지: "관심 구간", "관찰 필요", "돈의 흐름 확인" 같은 표현 사용
- (마지막 3초) 리스크 한 줄: 예) "단기 급등주는 변동성이 크니 추격매수보다 뉴스 지속성과 거래량을 같이 봐야 합니다"

음성 숫자 규칙: 상승률은 반드시 반올림해서 읽는다. +10.88% → "약 11% 상승", +8.22% → "약 8% 상승". 소수점을 읽지 않는다.
영어 뉴스 제목은 자연스러운 한국어로 풀어서 말한다.
각 구간 앞에 (0~3초) 같은 시간 표시를 붙여줘."""

    return f"""너는 투자 콘텐츠 작가야. 시청자는 출근길이나 자기 전에 쇼츠로 시장을 훑는 개인 투자자이고,
머릿속으로 항상 "그래서 돈이 어디로 가고 있는데?"라고 묻고 있다. 모든 데이터와 뉴스를 그 질문에 답하는 방향으로 해석해줘.

오늘({snapshot['date']}) 시장 데이터:

{build_data_block(snapshot)}

작업: {task}

반드시 지킬 것:
1. 단순 상승률 나열 금지. 뉴스가 왜 중요한지, 어떤 섹터/종목/코인과 연결되는지 반드시 설명.
2. 톤은 빠르고 몰입감 있는 시장 브리핑. 딱딱한 리포트 말투 금지.
3. 매수 추천처럼 들리는 표현 금지. "관심 구간", "관찰 필요", "돈의 흐름 확인" 같은 중립 표현 사용.
4. 수익 보장·단정적 전망 금지 ("오를 것", "사야 할" 등).
5. "왜 올랐고, 돈이 어디로 움직이고 있고, 내일/이번 주 무엇을 봐야 하는지"가 느껴지게.
"""
