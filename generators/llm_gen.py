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

    반환: {"hook": str, "movers": str, "news": str, "watch": str,
           "images": {"hook": str, "movers": str, "news": str, "watch": str}}
    """
    prompt = f"""너는 투자 콘텐츠 작가야. 시청자는 항상 "그래서 돈이 어디로 가고 있는데?"라고 묻고 있다.
아래 오늘({snapshot['date']}) 시장 데이터로 YouTube Shorts 영상의 장면별 내레이션을 작성해줘.

{build_data_block(snapshot)}

아래 JSON 형식으로만 답해. 다른 텍스트, 마크다운, 설명을 붙이지 마:
{{"hook": "...", "movers": "...", "news": "...", "watch": "...",
  "images": {{"hook": "...", "movers": "...", "news": "...", "watch": "..."}}}}

각 필드 규칙:
- hook (약 3초 분량, 1문장): 시선을 잡는 후킹. "오늘 시장, 그냥 오른 게 아니라 돈이 ○○ 쪽으로 몰렸습니다" 느낌.
- movers (약 7초, 1~2문장): 급등 주식/코인 빠르게 언급만. 숫자는 반드시 반올림해서 ("SK하이닉스 약 11% 상승"). 소수점 금지.
- news (약 25초, 3~4문장, 가장 길게): 핵심 뉴스 1~2개. 제목만 읽지 말고 왜 중요한지, 어떤 섹터/종목/코인과 연결되는지,
  돈이 어디로 움직이는 신호인지 설명. 영어 제목은 자연스러운 한국어로 풀어서.
- watch (약 12초, 2문장): 어떤 섹터/종목/코인을 관찰할지 ("관심 구간", "관찰 필요", "돈의 흐름 확인" 표현)
  + 리스크 한 문장 ("단기 급등주는 변동성이 크니 추격매수보다 뉴스 지속성과 거래량을 같이 봐야 합니다" 느낌).

전체 분량: 내레이션 네 필드를 모두 합쳐 공백 포함 380~450자 (낭독 45~55초 분량). 이 범위를 지켜.

images 필드: 각 장면의 배경 이미지를 AI로 생성할 영어 프롬프트. 규칙:
- 그 장면의 주제와 시각적으로 연결되게 (hook=오늘의 돈의 흐름 컨셉, movers=상승장/해당 섹터,
  news=뉴스 내용의 핵심 소재, watch=시장 관찰/모니터링 컨셉)
- 스타일 통일: "cinematic, dark navy and teal color palette, professional financial photography"
- 반드시 포함: "vertical 9:16 composition, no text, no letters, no numbers, no watermarks"
- 사람 얼굴 클로즈업 금지, 특정 실존 인물·로고 금지

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
