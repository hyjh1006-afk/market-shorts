# -*- coding: utf-8 -*-
"""시장 관찰 콘텐츠 팩토리 — YouTube Shorts 제작 화면.

실행: streamlit run app.py
"""
from pathlib import Path

import pandas as pd
import streamlit as st

import db
from collectors.stocks import collect_stocks
from collectors.coins import collect_coins
from collectors.news import collect_news
from generators.text_gen import (
    generate_shorts_script, build_llm_prompt, volume_spikes,
)
from generators import llm_gen

st.set_page_config(page_title="시장 브리핑 Shorts 팩토리", page_icon="🎬", layout="wide")
st.title("🎬 시장 브리핑 Shorts 팩토리")

# ── 사이드바: 수집 실행 & 날짜 선택 ──────────────────────────
with st.sidebar:
    st.header("데이터 수집")
    if st.button("🔄 오늘 데이터 수집", type="primary", use_container_width=True):
        with st.status("수집 중...", expanded=True) as status:
            st.write("주식 시세 수집 (yfinance)...")
            stocks = collect_stocks()
            db.save_stocks(stocks)
            st.write(f"→ {len(stocks)}개 종목 저장")

            st.write("코인 시세 수집 (CoinGecko)...")
            try:
                coins = collect_coins()
                db.save_coins(coins)
                st.write(f"→ {len(coins)}개 코인 저장")
            except Exception as e:
                st.warning(f"코인 수집 실패(잠시 후 재시도): {e}")

            st.write("뉴스 수집·선별 (투자 관련성 필터)...")
            news = collect_news()
            db.save_news(news)
            st.write(f"→ {len(news)}건 선별 저장")
            status.update(label="수집 완료 ✅", state="complete")
        st.rerun()

    dates = db.available_dates()
    if dates:
        sel_date = st.selectbox("조회 날짜", dates)
    else:
        sel_date = None
        st.info("먼저 위 버튼으로 데이터를 수집하세요.")

if not sel_date:
    st.stop()

snapshot = db.load_snapshot(sel_date)
ai = llm_gen.provider()

# ── 탭 구성 ──────────────────────────────────────────────────
tab_data, tab_shorts = st.tabs(["1️⃣ 시장 데이터", "2️⃣ Shorts 제작"])

# 1. 시장 데이터
with tab_data:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📈 주식 — 수익률/거래량")
        if snapshot["stocks"]:
            df = pd.DataFrame(snapshot["stocks"])[
                ["name", "price", "ret_1d", "ret_7d", "ret_30d", "vol_ratio", "currency"]]
            df.columns = ["종목", "가격", "1일%", "7일%", "30일%", "거래량배율", "통화"]
            st.dataframe(df, use_container_width=True, hide_index=True)

            spikes = volume_spikes(snapshot["stocks"])
            if spikes:
                st.markdown("**🔍 거래량 급증 (20일 평균 대비 2배 이상)**")
                for s in spikes:
                    st.markdown(f"- {s['name']}: **{s['vol_ratio']}배**")
        else:
            st.info("주식 데이터 없음")

    with col2:
        st.subheader("🪙 코인 — 상위 20")
        if snapshot["coins"]:
            df = pd.DataFrame(snapshot["coins"])[
                ["name", "symbol", "price_usd", "ret_1d", "ret_7d", "ret_30d"]]
            df.columns = ["이름", "심볼", "가격(USD)", "24h%", "7일%", "30일%"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("코인 데이터 없음")

    st.subheader("📰 투자자 관심 뉴스 (관련성 점수순)")
    for n in snapshot["news"][:15]:
        score = n.get("score") or 0
        st.markdown(f"- **[{n['category']}]** [{n['title']}]({n['link']}) · "
                    f"{n['source']} · 관련성 {score:.0f}점")

# 2. Shorts 제작
with tab_shorts:
    if ai is None:
        st.info("💡 **무료로 AI 내레이션 켜는 법**: aistudio.google.com/apikey 에서 무료 키 발급 → "
                "환경변수 `GEMINI_API_KEY`에 저장 → 앱 재시작. "
                "키가 있으면 영상 내레이션과 대본을 AI가 뉴스 해석까지 넣어서 작성합니다.")
    else:
        st.caption(f"🤖 AI 백엔드: {ai} — 영상 내레이션을 AI가 작성합니다")

    col_v, col_s = st.columns([1, 1])

    # 영상 생성 (메인)
    with col_v:
        st.subheader("🎥 Shorts 영상 만들기")
        st.caption("구성: 후킹 → 급등 요약(1.5배속, 반올림 숫자) → 핵심 뉴스 해석 → 관찰 포인트+리스크. "
                   "생성에 1~2분 걸립니다.")
        if st.button("🎬 영상 생성", type="primary", key="gen_video"):
            from generators.video_gen import generate_video
            with st.spinner("AI 내레이션 작성 → 장면 렌더링 → 음성 합성 → 인코딩 중..."):
                try:
                    video_path = generate_video(snapshot)
                    db.save_generated("shorts_video", video_path, sel_date)
                    st.session_state["video_path"] = video_path
                except Exception as e:
                    st.error(f"영상 생성 실패: {e}")

        video_path = st.session_state.get("video_path")
        if video_path and Path(video_path).exists():
            st.video(video_path)
            with open(video_path, "rb") as f:
                st.download_button("⬇️ MP4 다운로드", f, file_name=Path(video_path).name,
                                   mime="video/mp4")

    # 대본 (자막/설명란용 참고)
    with col_s:
        st.subheader("📝 대본 (자막·설명란용)")
        if st.session_state.get("script_date") != sel_date:
            st.session_state["script_date"] = sel_date
            st.session_state["script_area"] = generate_shorts_script(snapshot)

        if ai and st.button("🤖 AI로 대본 생성", key="ai_script"):
            with st.spinner("AI가 작성 중..."):
                try:
                    st.session_state["script_area"] = llm_gen.generate(snapshot, "shorts_script")
                except Exception as e:
                    st.error(f"AI 호출 실패: {e}")

        script = st.text_area("대본", height=420, key="script_area")
        if st.button("💾 기록 저장", key="save_script"):
            db.save_generated("shorts_script", script, sel_date)
            st.success("저장 완료")
        with st.expander("📋 LLM 프롬프트 (직접 붙여넣기용)"):
            st.code(build_llm_prompt(snapshot, "shorts_script"), language=None)
