# -*- coding: utf-8 -*-
"""시장 브리핑 Shorts — 폰에서 어디서나 쓰는 클라우드 버전.

수집 → AI 내레이션·이미지 → Shorts 영상까지 버튼 한 번.
Streamlit Cloud 배포용 진입점 (로컬 PC에서는 app.py를 쓴다).
"""
import os
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="시장 브리핑 Shorts", page_icon="🎬", layout="centered")

# Streamlit secrets → 환경변수 (llm_gen이 환경변수에서 키를 읽음)
try:
    _key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
except Exception:
    _key = ""
if _key:
    os.environ["GEMINI_API_KEY"] = _key

import db
from generators import llm_gen

st.title("🎬 시장 브리핑 Shorts")

ai = llm_gen.provider()
if ai:
    st.caption(f"🤖 AI: {ai} — 내레이션·배경 이미지를 AI가 만듭니다")
else:
    st.warning("GEMINI_API_KEY가 설정되지 않았습니다 (Streamlit secrets에 추가하세요). "
               "지금은 템플릿 내레이션으로 생성됩니다.")

if st.button("⚡ 오늘 영상 만들기", type="primary", use_container_width=True):
    st.session_state.pop("video_bytes", None)
    with st.status("실행 중… (3~5분, 폰을 닫아도 서버에서 계속 돕니다)", expanded=True) as status:
        try:
            st.write("1/3 데이터 수집 (주식·코인·뉴스)")
            from collectors.stocks import collect_stocks
            from collectors.coins import collect_coins
            from collectors.news import collect_news

            stocks = collect_stocks()
            db.save_stocks(stocks)
            st.write(f"→ 주식 {len(stocks)}개")
            try:
                coins = collect_coins()
                db.save_coins(coins)
                st.write(f"→ 코인 {len(coins)}개")
            except Exception as e:
                st.write(f"→ 코인 수집 실패(건너뜀): {e}")
            news = collect_news()
            db.save_news(news)
            st.write(f"→ 뉴스 {len(news)}건 선별")

            st.write("2/3 AI 내레이션·배경 이미지 생성")
            st.write("3/3 음성 합성 → 영상 인코딩")
            from generators.video_gen import generate_video
            path = generate_video(db.load_snapshot())

            st.session_state["video_bytes"] = Path(path).read_bytes()
            st.session_state["video_name"] = Path(path).name
            status.update(label="완성! ✅", state="complete")
        except Exception as e:
            status.update(label="실패", state="error")
            st.error(f"오류: {e}")

if st.session_state.get("video_bytes"):
    st.subheader("📼 완성된 영상")
    st.video(st.session_state["video_bytes"])
    st.download_button(
        "⬇️ MP4 저장 (유튜브 앱으로 올리기)",
        st.session_state["video_bytes"],
        file_name=st.session_state["video_name"],
        mime="video/mp4",
        use_container_width=True,
    )
    st.caption("저장 후 유튜브 앱 → ⊕ → Shorts 업로드. 자동 업로드는 아래 시간표대로 돌아갑니다.")


# ── 자동 업로드 시간표 설정 ──────────────────────────────────
import base64
import json

import requests as _rq

REPO = "hyjh1006-afk/market-shorts"
SCHEDULE_EDIT_URL = f"https://github.com/{REPO}/edit/main/schedule.json"

st.divider()
st.subheader("⚙️ 자동 업로드 시간표")


def _load_schedule() -> dict:
    """{"weekday_times": [...], "weekend_times": [...]} (옛 형식 "times"도 변환)."""
    try:
        r = _rq.get(f"https://api.github.com/repos/{REPO}/contents/schedule.json",
                    headers={"Accept": "application/vnd.github.raw+json"}, timeout=10)
        cfg = json.loads(r.text)
        legacy = cfg.get("times")
        return {
            "weekday_times": cfg.get("weekday_times") or legacy or ["22:30"],
            "weekend_times": cfg.get("weekend_times") or legacy or ["08:00"],
        }
    except Exception:
        return {"weekday_times": ["22:30"], "weekend_times": ["08:00"]}


def _save_schedule(weekday: list[str], weekend: list[str], token: str) -> str | None:
    """GitHub의 schedule.json을 갱신한다. 실패 시 에러 문자열 반환."""
    api = f"https://api.github.com/repos/{REPO}/contents/schedule.json"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json"}
    meta = _rq.get(api, headers=headers, timeout=10)
    if not meta.ok:
        return f"파일 정보를 못 읽었어요 (HTTP {meta.status_code}) — 토큰 권한 확인"
    body = json.dumps({"weekday_times": weekday, "weekend_times": weekend},
                      ensure_ascii=False, indent=2) + "\n"
    resp = _rq.put(api, headers=headers, timeout=15, json={
        "message": f"업로드 시간표 변경: 평일 {', '.join(weekday)} / 주말 {', '.join(weekend)}",
        "content": base64.b64encode(body.encode()).decode(),
        "sha": meta.json()["sha"],
    })
    return None if resp.ok else f"저장 실패 (HTTP {resp.status_code})"


current = _load_schedule()
st.caption(f"현재: 평일 **{', '.join(current['weekday_times'])}** · "
           f"주말 **{', '.join(current['weekend_times'])}** (한국시간 · 매주 반복)")

_options = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]
_wd = st.multiselect("평일(월~금) 업로드 시각 — 30분 단위",
                     _options, default=[t for t in current["weekday_times"] if t in _options])
_we = st.multiselect("주말(토·일) 업로드 시각 — 30분 단위",
                     _options, default=[t for t in current["weekend_times"] if t in _options])

try:
    _gh_token = str(st.secrets.get("GITHUB_TOKEN", "")).strip()
except Exception:
    _gh_token = ""

if st.button("💾 시간표 저장", use_container_width=True):
    if not (1 <= len(_wd) <= 6) or not (1 <= len(_we) <= 6):
        st.error("평일·주말 각각 1개 이상 6개 이하로 선택하세요. (유튜브 무료 업로드 한도가 하루 6개예요)")
    elif not _gh_token:
        st.warning("앱에서 바로 저장하려면 Streamlit secrets에 GITHUB_TOKEN이 필요해요. "
                   f"지금은 [GitHub에서 직접 수정]({SCHEDULE_EDIT_URL})해 주세요 — 예: "
                   '{"weekday_times": ["22:30"], "weekend_times": ["08:00"]}')
    else:
        err = _save_schedule(sorted(_wd), sorted(_we), _gh_token)
        if err:
            st.error(err)
        else:
            st.success(f"저장 완료! 평일 {', '.join(sorted(_wd))} · 주말 {', '.join(sorted(_we))}")

st.caption(f"수동 수정: [GitHub에서 schedule.json 열기]({SCHEDULE_EDIT_URL})")
