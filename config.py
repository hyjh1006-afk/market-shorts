# -*- coding: utf-8 -*-
"""전역 설정: 워치리스트, RSS 피드, 경로."""
from pathlib import Path

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "market.db"
OUTPUT_DIR = BASE_DIR / "output"

# ── 주식 워치리스트 (yfinance 티커) ──────────────────────────
# 한국 주식은 .KS(코스피) / .KQ(코스닥) 접미사
STOCK_WATCHLIST = {
    # 한국
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "373220.KS": "LG에너지솔루션",
    "005380.KS": "현대차",
    "035420.KS": "NAVER",
    "035720.KS": "카카오",
    "247540.KQ": "에코프로비엠",
    # 미국
    "NVDA": "엔비디아",
    "AAPL": "애플",
    "MSFT": "마이크로소프트",
    "TSLA": "테슬라",
    "GOOGL": "알파벳",
    "AMZN": "아마존",
    "META": "메타",
    "PLTR": "팔란티어",
}

# 거래량 급증 판정: 당일 거래량이 20일 평균의 몇 배 이상이면 급증으로 볼지
VOLUME_SPIKE_RATIO = 2.0

# ── 코인 (CoinGecko coin id) ─────────────────────────────────
COIN_TOP_N = 20          # 시총 상위 N개 수집
COIN_MOVERS_N = 5        # 상승률 상위 N개 추림

# ── 뉴스 RSS 피드 ────────────────────────────────────────────
NEWS_FEEDS = {
    "경제": [
        "https://www.yna.co.kr/rss/economy.xml",
        "https://www.hankyung.com/feed/economy",
        "https://www.mk.co.kr/rss/30100041/",  # 매일경제 경제
    ],
    "AI": [
        "https://www.yna.co.kr/rss/technology.xml",
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://venturebeat.com/category/ai/feed/",
    ],
    "코인": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ],
}
NEWS_PER_CATEGORY = 8    # 카테고리별 최대 저장 건수

# ── Shorts 영상 (TTS) ────────────────────────────────────────
# 목소리 후보 (output/목소리샘플_*.mp3 들어보고 선택):
#   ko-KR-HyunsuMultilingualNeural (남성, 가장 자연스러움) / ko-KR-InJoonNeural (남성) / ko-KR-SunHiNeural (여성)
TTS_VOICE = "ko-KR-HyunsuMultilingualNeural"
TTS_RATE = "+30%"                 # 말하기 속도 (브리핑 톤이되 알아듣기 좋게)

# ── 종목 → 섹터 매핑 (돈의 흐름 해석용) ──────────────────────
SECTOR_MAP = {
    "005930.KS": "AI·반도체",
    "000660.KS": "AI·반도체",
    "NVDA": "AI·반도체",
    "373220.KS": "2차전지",
    "247540.KQ": "2차전지",
    "005380.KS": "자동차·모빌리티",
    "TSLA": "자동차·모빌리티",
    "035420.KS": "플랫폼·AI서비스",
    "035720.KS": "플랫폼·AI서비스",
    "AAPL": "빅테크·AI",
    "MSFT": "빅테크·AI",
    "GOOGL": "빅테크·AI",
    "AMZN": "빅테크·AI",
    "META": "빅테크·AI",
    "PLTR": "빅테크·AI",
}

# ── 뉴스 선별: 투자자 관심 키워드 점수제 ─────────────────────
# 제목에 포함되면 가점. 점수 0 이하인 뉴스는 버린다.
NEWS_INCLUDE_KEYWORDS = {
    # 거시경제
    "금리": 3, "연준": 3, "fed": 3, "fomc": 3, "인플레이션": 3, "cpi": 3, "ppi": 2,
    "물가": 2, "환율": 2, "유가": 2, "opec": 2, "고용": 2, "실업": 2, "gdp": 2,
    "국채": 2, "채권": 2, "관세": 3, "무역": 1,
    # AI / 반도체 핵심 기업
    "엔비디아": 3, "nvidia": 3, "openai": 3, "anthropic": 3, "구글": 2, "google": 2,
    "메타": 2, "meta": 2, "애플": 2, "apple": 2, "마이크로소프트": 2, "microsoft": 2,
    "테슬라": 2, "tesla": 2, "amd": 3, "broadcom": 3, "브로드컴": 3, "tsmc": 3,
    "삼성전자": 3, "sk하이닉스": 3, "hynix": 3, "반도체": 3, "hbm": 3, "파운드리": 2,
    "데이터센터": 2, "gpu": 2, "칩": 1, "chip": 2, "semiconductor": 3,
    # 기업 이벤트
    "실적": 3, "earnings": 3, "가이던스": 3, "guidance": 3, "수주": 3, "계약": 1,
    "규제": 2, "소송": 2, "lawsuit": 2, "인수": 2, "합병": 2, "m&a": 3, "merger": 2,
    "acquisition": 2, "신제품": 2, "출시": 1, "공급망": 3, "supply chain": 3,
    "ipo": 2, "상장": 2, "자사주": 2, "배당": 2, "투자": 1,
    # 코인
    "비트코인": 3, "bitcoin": 3, "btc": 2, "이더리움": 3, "ethereum": 3, "etf": 3,
    "스테이블코인": 3, "stablecoin": 3, "알트코인": 2, "암호화폐": 2, "가상자산": 2,
    "crypto": 2, "거래소": 2, "binance": 2, "coinbase": 2, "온체인": 2, "반감기": 3,
}
# 제목에 포함되면 큰 감점 (일반 테크·흥미성 기사 제외)
NEWS_EXCLUDE_KEYWORDS = [
    "추천", "꿀팁", "사용법", "리뷰", "총정리", "해봤", "glossary", "용어",
    "브라우저", "browser", "best apps", "how to", "tips", "productivity", "생산성",
]

# ── AI 문장 생성 ─────────────────────────────────────────────
# 무료: Google AI Studio(aistudio.google.com/apikey)에서 키 발급 → 환경변수 GEMINI_API_KEY
# 유료: 환경변수 ANTHROPIC_API_KEY (설정 시 Claude 우선 사용)
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"   # 장면 배경 이미지 생성 (무료 티어 가능)
CLAUDE_MODEL = "claude-opus-4-8"

# 한글 폰트: Windows면 맑은고딕, 클라우드(리눅스)면 내장 나눔고딕
_WIN_BOLD = r"C:\Windows\Fonts\malgunbd.ttf"
_WIN_REG = r"C:\Windows\Fonts\malgun.ttf"
if Path(_WIN_BOLD).exists():
    FONT_BOLD, FONT_REGULAR = _WIN_BOLD, _WIN_REG
else:
    FONT_BOLD = str(BASE_DIR / "fonts" / "NanumGothic-Bold.ttf")
    FONT_REGULAR = str(BASE_DIR / "fonts" / "NanumGothic-Regular.ttf")
