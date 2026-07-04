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
                                 spoken_pct, _fmt_pct)

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
    """장면 4개(key: hook/movers/news/watch)를 만든다."""
    stocks, coins, news = snapshot["stocks"], snapshot["coins"], snapshot["news"]
    date = snapshot["date"]
    sector, sec_names = dominant_sector(stocks)
    movers = top_movers(stocks, "ret_1d", 3)
    coin_movers = top_movers(coins, "ret_1d", 2)
    top_news = key_news(news, 2, sector)
    narr = narrations or {}

    hook = (f"오늘 시장, 그냥 오른 게 아닙니다. 돈이 {sector} 쪽으로 다시 몰렸습니다."
            if sector else "오늘 시장에서 돈이 어디로 움직였는지 1분으로 정리합니다.")
    scenes = [{
        "key": "hook",
        "title": "오늘의 시장 브리핑",
        "subtitle": f"{date} · 돈은 어디로?",
        "items": [],
        "narration": narr.get("hook") or hook,
    }]

    if movers:
        quick = ", ".join(f"{s['name']} {spoken_pct(s['ret_1d'])}" for s in movers)
        coin_quick = "와 ".join(c["symbol"] for c in coin_movers) if coin_movers else ""
        narration = f"급등부터 빠르게. {quick}."
        if coin_quick:
            narration += f" 코인에서는 {coin_quick}가 강했습니다."
        scenes.append({
            "key": "movers",
            "title": f"{sector or '오늘'} 강세" if sector else "오늘 급등",
            "subtitle": "1일 수익률 상위",
            "items": [(s["name"], _fmt_pct(s["ret_1d"]), s["ret_1d"]) for s in movers],
            "narration": narr.get("movers") or narration,
        })

    if top_news:
        news_lines = [f"{'첫' if i == 1 else '두'} 번째. {x['title']}."
                      for i, x in enumerate(top_news, 1)]
        why = (f" 이 흐름은 {sector} 밸류체인과 직접 연결될 수 있습니다."
               if sector else " 이 뉴스들이 어느 섹터로 돈을 움직이는지가 핵심입니다.")
        scenes.append({
            "key": "news",
            "title": "주목할 뉴스",
            "subtitle": "돈의 흐름과 연결되는 소식",
            "items": [],  # 뉴스 원문 제목은 화면에 안 띄운다 (자막+내레이션으로 충분)
            "narration": narr.get("news") or ("이제 중요한 뉴스입니다. " + " ".join(news_lines) + why),
        })

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
    f_title = _font(FONT_BOLD, 92)
    f_sub = _font(FONT_REGULAR, 46)
    f_item = _font(FONT_REGULAR, 44)
    f_pct = _font(FONT_BOLD, 54)

    title_y = 300 if scene["items"] else 640
    tw = d.textlength(scene["title"], font=f_title)
    d.text(((W - tw) / 2, title_y), scene["title"], font=f_title, fill=FG,
           stroke_width=3, stroke_fill=(0, 0, 0))
    sw = d.textlength(scene["subtitle"], font=f_sub)
    d.text(((W - sw) / 2, title_y + 125), scene["subtitle"], font=f_sub, fill=MUTED,
           stroke_width=2, stroke_fill=(0, 0, 0))
    d.line([(W / 2 - 120, title_y + 210), (W / 2 + 120, title_y + 210)], fill=ACCENT, width=6)

    y = title_y + 290
    if scene["items"]:
        panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        pd = ImageDraw.Draw(panel)
        yy = y
        for name, pct, val in scene["items"]:
            pd.rounded_rectangle([(80, yy), (W - 80, yy + 106)], radius=20,
                                 fill=(20, 26, 40, 215))
            yy += 136
        img = Image.alpha_composite(img.convert("RGBA"), panel).convert("RGB")
        d = ImageDraw.Draw(img)
        for name, pct, val in scene["items"]:
            if pct:
                d.text((120, y + 28), _fit_text(d, name, f_item, W - 420), font=f_item, fill=FG)
                pw = d.textlength(pct, font=f_pct)
                d.text((W - 120 - pw, y + 22), pct, font=f_pct, fill=_ret_color(val))
            else:
                d.text((120, y + 28), _fit_text(d, name, f_item, W - 240), font=f_item, fill=FG)
            y += 136
    return img


def add_subtitle(base: Image.Image, sentence: str) -> Image.Image:
    """하단에 자막 밴드 + 문장을 얹는다. 긴 문장은 글자를 줄여 4줄까지."""
    img = base.convert("RGBA")
    d = ImageDraw.Draw(img)
    f_sub = _font(FONT_BOLD, 52)
    lines = _wrap_text(d, sentence, f_sub, W - 200)
    if len(lines) > 3:  # 3줄 초과면 폰트를 줄여 다시 감싼다 (최대 4줄)
        f_sub = _font(FONT_BOLD, 44)
        lines = _wrap_text(d, sentence, f_sub, W - 180)[:4]

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

    narrations, images = None, {}
    if use_ai:
        try:
            from generators import llm_gen
            if llm_gen.is_available():
                narrations = llm_gen.generate_video_narrations(snapshot)
                for k, img_prompt in (narrations.get("images") or {}).items():
                    img_bytes = llm_gen.generate_image(img_prompt)
                    if img_bytes:
                        images[k] = img_bytes
        except Exception:
            narrations = narrations or None  # 내레이션이라도 성공했으면 사용

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
