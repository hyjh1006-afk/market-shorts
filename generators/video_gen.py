# -*- coding: utf-8 -*-
"""Shorts 영상 자동 생성.

구성: 후킹 → 급등 요약 → 핵심 뉴스 → 관찰 포인트+리스크
- 내레이션: AI(Gemini) 작성, 실패 시 템플릿
- 배경: 장면마다 Gemini AI 생성 이미지 (실패 시 단색 배경)
- 자막: 문장 단위로 음성과 동기화되어 하단에 표시
- 음성: edge-tts (config의 TTS_VOICE/TTS_RATE)
출력: output/shorts_YYYY-MM-DD_HHMMSS.mp4 (1080x1920)
"""
import asyncio
import io
import re
import tempfile
from datetime import datetime
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

from config import FONT_BOLD, FONT_REGULAR, OUTPUT_DIR, TTS_VOICE, TTS_RATE
from generators.text_gen import (top_movers, dominant_sector, key_news,
                                 spoken_pct, spoken_name, _fmt_pct)
from generators.market_hours import basis_caption, coin_caption, is_weekend


def _basis(market: str, rows: list[dict], weekly: bool = False) -> str:
    """장면 하단 등락률 기준 문구. rows에서 거래일 날짜를 읽어 생성."""
    if not rows:
        return ""
    last = rows[0].get("last_date", "")
    if weekly:
        week = rows[0].get("week_date", "")
        if week and last:
            from generators.market_hours import _md
            return f"기준: {_md(week)} 종가 → {_md(last)} 종가 (주간)"
        return "기준: 주간 등락률 (5거래일)"
    prev = rows[0].get("prev_date", "")
    return basis_caption(market, prev, last)

W, H = 1080, 1920

# 색상 팔레트
BG = (16, 21, 34)
FG = (235, 238, 245)
ACCENT = (94, 200, 145)
DOWN = (232, 106, 106)
MUTED = (170, 180, 195)
CARD_BG = (28, 35, 52)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def _ret_color(v) -> tuple:
    if v is None:
        return MUTED
    return ACCENT if v >= 0 else DOWN


# ── 장면 정의 ────────────────────────────────────────────────

def build_scenes(snapshot: dict, narrations: dict | None = None) -> list[dict]:
    """장면 구성: hook → 국내(movers) → 미국(us_movers) → 코인(coins) → news → watch.
    주말(토·일)엔 '주간 결산' 모드: 주간 수익률(ret_7d) 기준 + 마무리 톤."""
    stocks, coins, news = snapshot["stocks"], snapshot["coins"], snapshot["news"]
    date = snapshot["date"]
    weekend = is_weekend()
    metric = "ret_7d" if weekend else "ret_1d"
    sector, sec_names = dominant_sector(stocks)
    coin_movers = top_movers(coins, "ret_1d", 2)
    top_news = key_news(news, 2, sector)
    narr = narrations or {}

    if weekend:
        hook = (f"이번 주 시장, 돈은 {sector} 쪽으로 움직였습니다. 한 주 정리하고 다음 주를 준비해봅니다."
                if sector else "이번 주 시장에서 돈이 어디로 움직였는지, 한 주를 정리해봅니다.")
        scenes = [{
            "key": "hook",
            "title": "주간 시장 결산",
            "subtitle": f"{date} · 이번 주 돈의 흐름",
            "items": [],
            "narration": narr.get("hook") or hook,
        }]
    else:
        hook = (f"오늘 시장, 그냥 오른 게 아닙니다. 돈이 {sector} 쪽으로 다시 몰렸습니다."
                if sector else "오늘 시장에서 돈이 어디로 움직였는지 1분으로 정리합니다.")
        scenes = [{
            "key": "hook",
            "title": "오늘의 시장 브리핑",
            "subtitle": f"{date} · 돈은 어디로?",
            "items": [],
            "narration": narr.get("hook") or hook,
        }]

    # 주식을 국내(KRW)·미국(USD)으로 나눠 각각 TOP 10 화면을 만든다
    kr_stocks = [s for s in stocks if s.get("currency") == "KRW"]
    us_stocks = [s for s in stocks if s.get("currency") == "USD"]
    sub_label = "이번 주 등락률 TOP 10" if weekend else "1일 등락률 TOP 10"

    kr_top = top_movers(kr_stocks, metric, 10)
    if kr_top:
        quick = ", ".join(f"{spoken_name(s['name'])} {spoken_pct(s[metric])}"
                          for s in top_movers(kr_stocks, metric, 3))
        kr_narr = (f"이번 주 국내 증시 마무리는 이랬습니다. {quick}." if weekend
                   else f"국내 증시부터 빠르게. {quick}.")
        scenes.append({
            "key": "movers",  # 국내 (키 유지 — AI 내레이션 movers 필드 = 국내)
            "title": "국내 증시 주간 결산" if weekend else "국내 증시",
            "subtitle": f"국내 주식 {sub_label}",
            "items": [(f"{i}. {s['name']}", _fmt_pct(s[metric]), s[metric])
                      for i, s in enumerate(kr_top, 1)],
            "caption": _basis("KR", kr_top, weekly=weekend),
            "narration": narr.get("movers") or kr_narr,
        })

    us_top = top_movers(us_stocks, metric, 10)
    if us_top:
        us_quick = ", ".join(f"{spoken_name(s['name'])} {spoken_pct(s[metric])}"
                             for s in top_movers(us_stocks, metric, 3))
        us_narr = (f"미국 증시는 한 주간 {us_quick}." if weekend
                   else f"미국 증시에서는 {us_quick}.")
        scenes.append({
            "key": "us_movers",
            "title": "미국 증시 주간 결산" if weekend else "미국 증시",
            "subtitle": f"미국 주식 {sub_label}",
            "items": [(f"{i}. {s['name']}", _fmt_pct(s[metric]), s[metric])
                      for i, s in enumerate(us_top, 1)],
            "caption": _basis("US", us_top, weekly=weekend),
            "narration": narr.get("us_movers") or us_narr,
        })

    # 코인 장면: 화면에 코인 TOP 10, 내레이션은 상위 1~2개만
    if coin_movers:
        screen_coins = top_movers(coins, "ret_1d", 10)
        coin_line = ", ".join(
            f"{KO_COIN.get(c['name'], c['symbol'])} {spoken_pct(c['ret_1d'])}"
            for c in coin_movers)
        scenes.append({
            "key": "coins",
            "title": "코인 시장",
            "subtitle": "24시간 상승률 TOP 10",
            "items": [(f"{i}. {c['name']} ({c['symbol']})", _fmt_pct(c["ret_1d"]), c["ret_1d"])
                      for i, c in enumerate(screen_coins, 1)],
            "caption": coin_caption(),
            "narration": narr.get("coins") or f"코인 시장에서는 {coin_line}이 돋보였습니다.",
        })

    if top_news:
        # 템플릿 내레이션은 한국어 제목 뉴스만 읽는다 (영어 제목을 그대로 읽으면 어색)
        ko_news = [x for x in top_news if _has_hangul(x["title"])]
        if not ko_news:
            ko_news = [x for x in key_news(news, 6, sector) if _has_hangul(x["title"])][:2]
        news_lines = [f"{'첫' if i == 1 else '두'} 번째. {x['title']}."
                      for i, x in enumerate(ko_news, 1)]
        if weekend:
            why = (f" 다음 주에도 {sector} 흐름이 이어지는지가 관전 포인트입니다."
                   if sector else " 이 이슈들이 다음 주 어느 섹터로 돈을 움직일지가 관전 포인트입니다.")
            intro = "이번 주 핵심 이슈를 정리하면. "
        else:
            why = (f" 이 흐름은 {sector} 밸류체인과 직접 연결될 수 있습니다."
                   if sector else " 이 뉴스들이 어느 섹터로 돈을 움직이는지가 핵심입니다.")
            intro = "이제 중요한 뉴스입니다. "
        template_news = ((intro + " ".join(news_lines) + why)
                         if news_lines else
                         (f"이번 주 뉴스 흐름의 핵심은 {sector or '주도 섹터'}로 돈이 이어지는지 여부입니다."
                          " 관련 소식이 이어지는지 지켜봐야 합니다."))
        scenes.append({
            "key": "news",
            "title": "이번 주 핵심 이슈" if weekend else "주목할 뉴스",
            "subtitle": "다음 주 돈의 흐름과 연결되는 소식" if weekend else "돈의 흐름과 연결되는 소식",
            "items": [],  # 뉴스 원문 제목은 화면에 안 띄운다 (자막+내레이션으로 충분)
            "narration": narr.get("news") or template_news,
        })

    if weekend:
        if sector and sec_names:
            watch = (f"다음 주 관심 구간은 {sector}. {', '.join(sec_names)} 중심으로 "
                     f"월요일 개장 후 거래량과 뉴스 지속성 확인이 필요합니다.")
        else:
            watch = "이번 주 강했던 종목들이 다음 주에도 이어지는지, 월요일 개장 흐름 확인이 필요합니다."
        scenes.append({
            "key": "watch",
            "title": "다음 주 관전 포인트",
            "subtitle": sector or "다음 주 돈의 흐름",
            "items": [],
            "narration": narr.get("watch") or (watch + " 단, 예측은 참고만 하시고 "
                                                       "실제 흐름은 거래량과 뉴스로 확인하세요."),
        })
    else:
        if sector and sec_names:
            watch = (f"오늘 기준 관심 구간은 {sector}. {', '.join(sec_names)} 중심으로 "
                     f"거래량과 뉴스 지속성 확인이 필요합니다.")
        else:
            watch = "오늘 급등 종목들의 거래량이 내일도 이어지는지 확인이 필요합니다."
        scenes.append({
            "key": "watch",
            "title": "관찰 포인트",
            "subtitle": sector or "돈의 흐름 확인",
            "items": [],
            "narration": narr.get("watch") or (watch + " 단, 단기 급등주는 변동성이 큽니다. "
                                                       "추격매수보다 뉴스 지속성과 거래량을 같이 보세요."),
        })
    return scenes


# ── 렌더링 헬퍼 ──────────────────────────────────────────────

def _has_hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" for ch in s)


# 템플릿 내레이션용 코인 한국어 이름 (AI 모드는 알아서 한국어로 말함)
KO_COIN = {
    "Bitcoin": "비트코인", "Ethereum": "이더리움", "XRP": "리플", "BNB": "비엔비",
    "Solana": "솔라나", "Cardano": "카르다노", "Dogecoin": "도지코인", "TRON": "트론",
    "Chainlink": "체인링크", "Avalanche": "아발란체", "Stellar": "스텔라루멘",
    "Hyperliquid": "하이퍼리퀴드", "Monero": "모네로", "Sui": "수이", "Toncoin": "톤코인",
    "Litecoin": "라이트코인", "Polkadot": "폴카닷", "Shiba Inu": "시바이누",
}


# 장면별 기본 배경 이미지 프롬프트 (AI 내레이션 없이도 항상 이미지 생성)
_STYLE = ("cinematic, dark navy and teal color palette, professional financial "
          "photography, moody lighting, vertical 9:16 composition, "
          "no text, no letters, no numbers, no watermarks, no human faces")

_SECTOR_IMG = {
    "AI·반도체": "glowing semiconductor chip on a circuit board, data streams",
    "2차전지": "electric vehicle battery cells glowing with energy",
    "자동차·모빌리티": "futuristic electric car on a night road",
    "플랫폼·AI서비스": "abstract digital network nodes and app interfaces",
    "빅테크·AI": "futuristic artificial intelligence data center, server racks",
}


def default_image_prompts(sector: str | None, news_titles: list[str]) -> dict:
    joined = " ".join(news_titles).lower()
    if any(k in joined for k in ["bitcoin", "비트코인", "etf", "crypto", "이더리움", "코인"]):
        news_base = "golden bitcoin coin above glowing financial charts"
    elif sector:
        news_base = _SECTOR_IMG.get(sector, "financial newspaper and market data on a desk")
    else:
        news_base = "financial news concept, world map with market data overlays"
    return {
        "hook": f"global financial market money flow concept, glowing light streams over a dark city skyline, {_STYLE}",
        "movers": f"rising Korean stock market rally, upward glowing green candlestick chart on a trading screen, {_STYLE}",
        "us_movers": f"Wall Street and New York stock exchange at night, glowing ticker board, upward chart, {_STYLE}",
        "coins": f"golden cryptocurrency coins glowing above a digital trading chart, {_STYLE}",
        "news": f"{news_base}, {_STYLE}",
        "watch": f"trader watching multiple glowing market monitors in a dark room, seen from behind, {_STYLE}",
    }


def _fit_text(d, text, font, max_w):
    if d.textlength(text, font=font) <= max_w:
        return text
    while text and d.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"


def _wrap_text(d, text, font, max_w):
    """단어 단위 줄바꿈. 줄 목록 반환."""
    words = text.split()
    lines, cur = [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if d.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def _cover_fill(img: Image.Image) -> Image.Image:
    """이미지를 1080x1920에 꽉 차게 리사이즈+크롭."""
    ratio = max(W / img.width, H / img.height)
    nw, nh = round(img.width * ratio), round(img.height * ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - W) // 2, (nh - H) // 2
    return img.crop((left, top, left + W, top + H))


def compose_base(scene: dict, bg_bytes: bytes | None) -> Image.Image:
    """장면 기본 화면: AI 배경(있으면) + 어둡게 + 제목/항목."""
    if bg_bytes:
        try:
            bg = Image.open(io.BytesIO(bg_bytes)).convert("RGB")
            img = _cover_fill(bg)
            # 텍스트 가독성을 위한 어두운 오버레이
            overlay = Image.new("RGBA", (W, H), (10, 14, 24, 150))
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        except Exception:
            img = Image.new("RGB", (W, H), BG)
    else:
        img = Image.new("RGB", (W, H), BG)

    d = ImageDraw.Draw(img)
    n = len(scene["items"])
    compact = n > 5   # 항목 많으면(TOP 10) 촘촘한 레이아웃

    f_title = _font(FONT_BOLD, 84 if compact else 92)
    f_sub = _font(FONT_REGULAR, 42 if compact else 46)
    f_item = _font(FONT_REGULAR, 36 if compact else 44)
    f_pct = _font(FONT_BOLD, 42 if compact else 54)
    row_h = 76 if compact else 106
    row_gap = 10 if compact else 30
    pad_y = (row_h - (f_item.size + 8)) // 2

    title_y = (150 if compact else 300) if scene["items"] else 640
    tw = d.textlength(scene["title"], font=f_title)
    d.text(((W - tw) / 2, title_y), scene["title"], font=f_title, fill=FG,
           stroke_width=3, stroke_fill=(0, 0, 0))
    sw = d.textlength(scene["subtitle"], font=f_sub)
    d.text(((W - sw) / 2, title_y + 115), scene["subtitle"], font=f_sub, fill=MUTED,
           stroke_width=2, stroke_fill=(0, 0, 0))

    # 등락률 기준 문구 — 제목 영역(상단)에 배치해 자막 밴드·항목과 겹치지 않게
    caption = scene.get("caption")
    cap_h = 0
    if caption and scene["items"]:
        f_cap = _font(FONT_REGULAR, 32)
        cw = d.textlength(caption, font=f_cap)
        d.text(((W - cw) / 2, title_y + 168), caption, font=f_cap, fill=MUTED,
               stroke_width=2, stroke_fill=(0, 0, 0))
        cap_h = 46
    d.line([(W / 2 - 120, title_y + 190 + cap_h), (W / 2 + 120, title_y + 190 + cap_h)],
           fill=ACCENT, width=6)

    y = title_y + (250 if compact else 290) + cap_h
    if scene["items"]:
        panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(panel)
        yy = y
        for _ in scene["items"]:
            pd.rounded_rectangle([(80, yy), (W - 80, yy + row_h)], radius=16,
                                 fill=(20, 26, 40, 215))
            yy += row_h + row_gap
        img = Image.alpha_composite(img.convert("RGBA"), panel).convert("RGB")
        d = ImageDraw.Draw(img)
        for name, pct, val in scene["items"]:
            if pct:
                d.text((120, y + pad_y), _fit_text(d, name, f_item, W - 420),
                       font=f_item, fill=FG)
                pw = d.textlength(pct, font=f_pct)
                d.text((W - 120 - pw, y + pad_y - 3), pct, font=f_pct, fill=_ret_color(val))
            else:
                d.text((120, y + pad_y), _fit_text(d, name, f_item, W - 240),
                       font=f_item, fill=FG)
            y += row_h + row_gap
    return img


def add_subtitle(base: Image.Image, sentence: str) -> Image.Image:
    """하단에 자막 밴드 + 문장을 얹는다. 긴 문장은 글자를 줄여 4줄까지."""
    img = base.convert("RGBA")
    d = ImageDraw.Draw(img)
    f_sub = _font(FONT_BOLD, 60)   # 40~50대 시청자 가독성 위해 크게
    lines = _wrap_text(d, sentence, f_sub, W - 160)
    if len(lines) > 3:  # 3줄 초과면 폰트를 살짝 줄여 다시 감싼다 (최대 4줄)
        f_sub = _font(FONT_BOLD, 52)
        lines = _wrap_text(d, sentence, f_sub, W - 150)[:4]

    line_h = round(f_sub.size * 1.42)
    band_h = line_h * len(lines) + 60
    band_top = H - 260 - band_h

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([(50, band_top), (W - 50, band_top + band_h)],
                         radius=24, fill=(0, 0, 0, 175))
    img = Image.alpha_composite(img, overlay)
    d = ImageDraw.Draw(img)

    ty = band_top + 30
    for line in lines:
        lw = d.textlength(line, font=f_sub)
        d.text(((W - lw) / 2, ty), line, font=f_sub, fill=(255, 235, 130),
               stroke_width=2, stroke_fill=(0, 0, 0))
        ty += line_h
    return img.convert("RGB")


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


# ── TTS ──────────────────────────────────────────────────────

async def _tts_async(text: str, path: Path):
    await edge_tts.Communicate(text, TTS_VOICE, rate=TTS_RATE).save(str(path))


def synthesize(text: str, path: Path):
    asyncio.run(_tts_async(text, path))


# ── 최종 합성 ────────────────────────────────────────────────

def generate_video(snapshot: dict, out_dir: Path | None = None,
                   use_ai: bool = True) -> str:
    """Shorts mp4 생성. AI 키가 있으면 내레이션과 배경 이미지를 AI가 만든다."""
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

    from generators import llm_gen
    from generators.text_gen import dominant_sector as _ds, key_news as _kn

    narrations = None
    if use_ai:
        try:
            if llm_gen.is_available():
                narrations = llm_gen.generate_video_narrations(snapshot)
        except Exception:
            narrations = None  # AI 실패 시 템플릿 내레이션으로

    # 배경 이미지는 AI 키가 없어도 항상 생성 (Pollinations는 키 불필요).
    # AI가 장면별 이미지 프롬프트를 줬으면 그걸 우선 쓰고, 없으면 기본 프롬프트.
    sector, _ = _ds(snapshot["stocks"])
    titles = [x["title"] for x in _kn(snapshot["news"], 2, sector)]
    prompts = default_image_prompts(sector, titles)
    if narrations and narrations.get("images"):
        prompts.update({k: v for k, v in narrations["images"].items() if v})
    images = {}
    for k, img_prompt in prompts.items():
        img_bytes = llm_gen.generate_image(img_prompt)
        if img_bytes:
            images[k] = img_bytes

    out_dir = Path(out_dir or OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes = build_scenes(snapshot, narrations)

    clips = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        n = 0
        for scene in scenes:
            base = compose_base(scene, images.get(scene["key"]))
            for sent in _split_sentences(scene["narration"]):
                frame_path = tmp / f"f_{n}.png"
                audio_path = tmp / f"a_{n}.mp3"
                add_subtitle(base, sent).save(frame_path)
                synthesize(sent, audio_path)

                a = AudioFileClip(str(audio_path))
                clips.append(ImageClip(str(frame_path))
                             .with_duration(a.duration + 0.15)
                             .with_audio(a))
                n += 1

        final = concatenate_videoclips(clips, method="chain")
        ts = datetime.now().strftime("%H%M%S")
        out_path = out_dir / f"shorts_{snapshot['date']}_{ts}.mp4"
        final.write_videofile(str(out_path), fps=24, codec="libx264",
                              audio_codec="aac", logger=None)
        final.close()
        for c in clips:
            c.close()
    return str(out_path)


if __name__ == "__main__":
    import db
    print(generate_video(db.load_snapshot()))
