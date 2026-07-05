# -*- coding: utf-8 -*-
"""AI로 Shorts 대본 / 영상 내레이션 생성.

지원 백엔드 (우선순위 순):
1. Claude  — 환경변수 ANTHROPIC_API_KEY (유료)
2. Gemini  — 환경변수 GEMINI_API_KEY (무료 티어, aistudio.google.com/apikey)

둘 다 없으면 provider()가 None을 반환하고 앱은 템플릿 기반 생성으로 대체한다.
"""
import base64
import json
import os

import requests

from config import CLAUDE_MODEL, GEMINI_MODEL, GEMINI_IMAGE_MODEL
from generators.text_gen import build_llm_prompt, build_data_block

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _get_key(name: str) -> str | None:
    """프로세스 환경변수 → 없으면 Windows 사용자 환경변수(레지스트리)에서 읽는다."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            val, _ = winreg.QueryValueEx(k, name)
            if val:
                os.environ[name] = val
                return val
    except (OSError, ImportError):   # 리눅스(클라우드)에는 winreg가 없다
        pass
    return None


def provider() -> str | None:
    """사용 가능한 AI 백엔드 이름('claude'/'gemini') 또는 None."""
    if _get_key("ANTHROPIC_API_KEY"):
        return "claude"
    if _get_key("GEMINI_API_KEY"):
        return "gemini"
    return None


def is_available() -> bool:
    return provider() is not None


def _call(prompt: str) -> str:
    p = provider()
    if p == "claude":
        return _claude(prompt)
    if p == "gemini":
        return _gemini(prompt)
    raise RuntimeError("사용 가능한 API 키가 없습니다 (GEMINI_API_KEY 또는 ANTHROPIC_API_KEY).")


def generate(snapshot: dict, kind: str = "shorts_script") -> str:
    """Shorts 대본 텍스트를 AI가 작성한다."""
    return _call(build_llm_prompt(snapshot, kind))


def generate_video_narrations(snapshot: dict) -> dict:
    """영상 장면별 내레이션 + 배경 이미지 프롬프트를 AI가 작성한다.

    반환: {"hook": str, "movers": str, "coins": str, "news": str, "watch": str,
           "images": {"hook": str, "movers": str, "coins": str, "news": str, "watch": str}}
    """
    from generators.market_hours import is_weekend
    weekend = is_weekend()
    weekend_block = """
【주말 모드 — 주간 결산 톤 (중요!)】
오늘은 주말이라 장이 닫혀 있다. 하루 브리핑이 아니라 '한 주 마무리 + 다음 주 준비' 영상이다:
- hook: "이번 주 시장, 돈은 ○○로 움직였습니다" 같은 주간 결산 후킹.
- movers/us_movers: 데이터 블록의 '주간 등락률'을 쓰고 "이번 주 국내 증시는", "미국 증시는 한 주간" 톤으로.
  "오늘"이라는 단어 금지 — 이번 주/한 주간으로 말할 것.
- news: 이번 주 핵심 이슈 1~2개 정리 + 다음 주에 이 흐름이 어디로 이어질지 관전 포인트.
  단정 예측 금지 — "~할지 지켜봐야", "~가 관전 포인트" 같은 관찰 화법으로.
- watch: 다음 주 관찰할 섹터/종목/일정. "월요일 개장 후" 관점.
""" if weekend else ""

    prompt = f"""너는 투자 콘텐츠 작가야. 시청자는 항상 "그래서 돈이 어디로 가고 있는데?"라고 묻고 있다.
아래 {'이번 주' if weekend else '오늘'}({snapshot['date']}) 시장 데이터로 YouTube Shorts 영상의 장면별 내레이션을 작성해줘.
{weekend_block}
{build_data_block(snapshot)}

아래 JSON 형식으로만 답해. 다른 텍스트, 마크다운, 설명을 붙이지 마:
{{"hook": "...", "movers": "...", "us_movers": "...", "coins": "...", "news": "...", "watch": "...",
  "images": {{"hook": "...", "movers": "...", "us_movers": "...", "coins": "...", "news": "...", "watch": "..."}}}}

각 필드 규칙:
- hook (약 3초 분량, 1문장): 시선을 잡는 후킹. "오늘 시장, 그냥 오른 게 아니라 돈이 ○○ 쪽으로 몰렸습니다" 느낌.
- movers (약 5초, 1문장): '국내 주식'만 빠르게 언급 (미국·코인은 여기서 말하지 마). 숫자는 반드시 반올림해서 ("SK하이닉스 약 11% 상승"). 소수점 금지.
- us_movers (약 5초, 1문장): '미국 주식'만 언급 (엔비디아, 애플, 테슬라 등). 상위 1~2개를 반올림 숫자로. 국내 주식과 겹쳐 말하지 마.
- coins (약 5초, 1문장): 코인 시장 요약. 상위 코인 1~2개만 반올림 숫자로.
- news (약 22초, 3~4문장, 가장 길게): 핵심 뉴스 1~2개. 제목만 읽지 말고 왜 중요한지, 어떤 섹터/종목/코인과 연결되는지,
  돈이 어디로 움직이는 신호인지 설명. **국내뿐 아니라 미국 증시·빅테크 흐름도 최소 한 번 언급**. 영어 제목은 자연스러운 한국어로 풀어서.
- watch (약 12초, 2문장): 어떤 섹터/종목/코인을 관찰할지 ("관심 구간", "관찰 필요", "돈의 흐름 확인" 표현)
  + 리스크 한 문장 ("단기 급등주는 변동성이 크니 추격매수보다 뉴스 지속성과 거래량을 같이 봐야 합니다" 느낌).

전체 분량: 내레이션 여섯 필드를 모두 합쳐 공백 포함 430~500자 (낭독 55~65초 분량). 이 범위를 지켜.

images 필드: 각 장면의 배경 이미지를 AI로 생성할 영어 프롬프트. 규칙:
- 그 장면의 주제와 시각적으로 연결되게 (hook=오늘의 돈의 흐름 컨셉, movers=국내 상승장, us_movers=미국 증시/월스트리트,
  news=뉴스 내용의 핵심 소재, watch=시장 관찰/모니터링 컨셉)
- 스타일 통일: "cinematic, dark navy and teal color palette, professional financial photography"
- 반드시 포함: "vertical 9:16 composition, no text, no letters, no numbers, no watermarks"
- 사람 얼굴 클로즈업 금지, 특정 실존 인물·로고 금지

언어 규칙 (가장 중요 — TTS가 한국어 음성으로 읽는다. 영어 단어가 섞이면 발음이 깨진다):
- 모든 내레이션 필드(미국 증시·미국 뉴스 포함)는 100% 한국어로만 쓴다. 영어 단어를 문장에 넣지 마.
- 영어 뉴스 제목·문장을 원문 그대로 넣지 말고 반드시 한국어로 옮겨 말한다.
- 미국 기업·종목명도 한국어 발음으로 표기: Apple→애플, Nvidia→엔비디아, Tesla→테슬라, Microsoft→마이크로소프트,
  Alphabet/Google→알파벳, Amazon→아마존, Meta→메타, Palantir→팔란티어, AMD→에이엠디, Broadcom→브로드컴, Anthropic→앤트로픽.
- 지수·용어도 한국어로: S&P500→에스앤피500, Nasdaq→나스닥, Dow→다우, Fed→연준, ETF→이티에프, AI→에이아이(또는 "인공지능").
- 예외 없음. 알파벳 대문자 약어라도 한국어 발음으로 풀어 쓴다. 영어 철자를 그대로 두지 마.

톤: 빠르고 몰입감 있는 시장 브리핑, 살짝 구어체. 딱딱한 리포트 말투 금지.
매수 추천·수익 보장·단정 전망 금지."""

    raw = _call(prompt).strip()
    # 마크다운 코드펜스 제거
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw.strip())
    for k in ("hook", "movers", "news", "watch"):
        if not data.get(k):
            raise ValueError(f"내레이션 필드 누락: {k}")
    return data


def _default_us_narration(us_stocks: list[dict]) -> str:
    """AI 미사용 시 미국 주식 장면 템플릿 내레이션."""
    from generators.text_gen import spoken_name, spoken_pct, top_movers
    top = top_movers(us_stocks, "ret_1d", 3)
    if not top:
        return ""
    line = ", ".join(f"{spoken_name(s['name'])} {spoken_pct(s['ret_1d'])}" for s in top)
    return f"미국 증시에서는 {line}."


def generate_image(prompt: str) -> bytes | None:
    """장면 배경 이미지 생성. Pollinations(무료·키 불필요) → 실패 시 Gemini 순서.

    Gemini 이미지 모델(gemini-2.5-flash-image)은 무료 등급에서 한도 0이라
    결제 계정에서만 동작한다. 그래서 기본은 Pollinations를 쓴다.
    """
    img = _pollinations_image(prompt)
    if img:
        return img
    return _gemini_image(prompt)


def _pollinations_image(prompt: str) -> bytes | None:
    import urllib.parse
    try:
        resp = requests.get(
            "https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt),
            params={"width": 1080, "height": 1920, "nologo": "true"},
            timeout=120,
        )
        if resp.ok and "image" in resp.headers.get("content-type", ""):
            return resp.content
    except Exception:
        pass
    return None


def _gemini_image(prompt: str) -> bytes | None:
    if not _get_key("GEMINI_API_KEY"):
        return None
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": "9:16"},
        },
    }
    try:
        resp = requests.post(
            GEMINI_URL.format(model=GEMINI_IMAGE_MODEL),
            params={"key": os.environ["GEMINI_API_KEY"]},
            json=body, timeout=120,
        )
        if resp.status_code == 400:
            body["generationConfig"].pop("imageConfig", None)
            resp = requests.post(
                GEMINI_URL.format(model=GEMINI_IMAGE_MODEL),
                params={"key": os.environ["GEMINI_API_KEY"]},
                json=body, timeout=120,
            )
        resp.raise_for_status()
        for part in resp.json()["candidates"][0]["content"]["parts"]:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    except Exception:
        return None
    return None


def _claude(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(parts).strip()


def _gemini(prompt: str) -> str:
    resp = requests.post(
        GEMINI_URL.format(model=GEMINI_MODEL),
        params={"key": os.environ["GEMINI_API_KEY"]},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Gemini 응답 형식이 예상과 다릅니다: {str(data)[:300]}")


if __name__ == "__main__":
    import db
    p = provider()
    if p is None:
        print("API 키가 없습니다. GEMINI_API_KEY(무료) 또는 ANTHROPIC_API_KEY를 설정하세요.")
    else:
        print(f"[백엔드: {p}]")
        print(generate_video_narrations(db.load_snapshot()))
