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
    st.caption("저장 후 유튜브 앱 → ⊕ → Shorts 업로드. "
               "매일 아침 7:30 자동 생성/업로드는 GitHub Actions가 담당합니다 (README 참고).")
