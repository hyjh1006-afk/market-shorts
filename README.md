# 🎬 시장 브리핑 Shorts 팩토리

주식/코인/뉴스 데이터를 수집해 YouTube Shorts 영상(+대본)을 자동 생성하는 로컬 웹앱.
자동 게시는 하지 않으며, 검토 후 다운로드해서 사용한다.

핵심 원칙: 시청자는 항상 "그래서 돈이 어디로 가고 있는데?"를 묻고 있다.
영상 구성: 후킹 → 급등 요약(1.5배속 TTS, 반올림 숫자) → 핵심 뉴스 해석 → 관찰 포인트+리스크.

## 실행 방법 3가지

| 방법 | 실행 | 용도 |
|---|---|---|
| PC 웹앱 | 바탕화면 "시장관찰 앱" 또는 `앱실행.bat` | PC에서 데이터 보고 영상 만들기 |
| 폰 (클라우드) | Streamlit Cloud 배포 후 폰 브라우저에서 접속 | 어디서든 버튼 한 번으로 영상 생성·저장 |
| 자동 (매일 아침) | GitHub Actions (07:30 KST) | 수집→영상→유튜브 업로드 무인 실행 (PC 불필요) |

클라우드 배포: 이 폴더를 GitHub `market-shorts` 저장소에 push → share.streamlit.io에서
`streamlit_app.py`로 배포 → Secrets에 `GEMINI_API_KEY` 등록. (Tistory_cloud와 같은 방식)
GitHub Actions 자동 실행에도 저장소 Secrets에 `GEMINI_API_KEY` 필요 (+ 유튜브는
`YT_CLIENT_SECRET_JSON`, `YT_TOKEN_JSON`).
로컬 작업 스케줄러 "MarketShortsDaily"(07:30)도 있음 — Actions가 가동되면 둘 중 하나는 끌 것.

## 유튜브 자동 업로드 설정 (최초 1회)

1. console.cloud.google.com → 새 프로젝트 → "YouTube Data API v3" 사용 설정
2. OAuth 동의 화면 (외부) 구성 → 테스트 사용자에 본인 구글 계정 추가
3. 사용자 인증 정보 → OAuth 클라이언트 ID (데스크톱 앱) → JSON 다운로드
   → `content_factory/client_secret.json` 으로 저장
4. `python uploader.py` 실행 → 브라우저에서 구글 로그인 1회 → 끝

이후 매일 아침 자동 업로드된다. 주의: 구글 미검증 프로젝트로 올린 영상은
**비공개로 잠길 수 있음** — 유튜브 스튜디오에서 공개 전환하거나, 구글 API 감사(무료)를 신청하면 해제된다.

## 폴더 구조

```
content_factory/
├── app.py               # Streamlit 웹앱 (PC용)
├── api_server.py        # 모바일 리모컨 API (포트 8788)
├── mobile-web/          # 폰에서 여는 리모컨 웹 (포트 8091)
├── daily_pipeline.py    # 매일 아침 자동 실행: 수집→영상→유튜브 업로드
├── uploader.py          # YouTube Data API 업로드 (client_secret.json 필요)
├── collect_all.py       # CLI 수집만
├── config.py            # 워치리스트·RSS·뉴스 키워드·TTS·섹터 매핑
├── db.py                # SQLite 스키마와 저장/조회
├── collectors/          # stocks(yfinance) / coins(CoinGecko) / news(RSS+점수 선별)
├── generators/
│   ├── text_gen.py      # Shorts 대본 템플릿 + LLM 프롬프트 + 섹터/뉴스 선별
│   ├── video_gen.py     # Shorts 영상 (AI 배경이미지 + 동기화 자막 + edge-tts)
│   └── llm_gen.py       # AI 내레이션/대본 (Gemini 무료), 이미지(Pollinations 무료)
├── data/market.db       # SQLite (웹앱·모바일·자동실행이 공유)
└── output/              # 생성된 영상 MP4 (공유)
```

## 커스터마이징

- **종목 추가/삭제**: `config.py`의 `STOCK_WATCHLIST` (한국 주식은 `.KS`/`.KQ` 접미사)
- **거래량 급증 기준**: `VOLUME_SPIKE_RATIO` (기본 2.0배)
- **뉴스 피드 추가**: `NEWS_FEEDS`에 RSS URL 추가
- **TTS 목소리**: `TTS_VOICE` (기본 ko-KR-SunHiNeural 여성, InJoonNeural 남성)
- **AI 모델**: `GEMINI_MODEL` / `CLAUDE_MODEL`

## AI 자동 문장 생성 (무료)

**Gemini 무료 티어** 사용 — 신용카드 등록 불필요:

1. https://aistudio.google.com/apikey 접속 (구글 계정 로그인)
2. "API 키 만들기" 클릭 → 키 복사
3. PowerShell에서:
   ```powershell
   [Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "복사한키", "User")
   ```
4. 터미널과 앱 재시작 → 텍스트 탭에 "🤖 AI로 생성" 버튼 활성화

무료 한도는 분당/일일 요청 수 제한 방식이라 하루 몇 번 생성하는 이 용도로는 충분하다.
키가 없으면 템플릿 기반 생성으로 자동 대체되고, "LLM 프롬프트"를 복사해
무료 웹 챗(ChatGPT, Gemini)에 붙여넣는 방법도 항상 사용 가능하다.

(유료 Claude를 쓰려면 `ANTHROPIC_API_KEY` 설정 — 있으면 Claude가 우선된다.)

## 다음 단계 (Phase 3 후보)

- [ ] Windows 작업 스케줄러에 `collect_all.py` 등록해 매일 자동 수집
- [ ] 수익률 추이 차트 카드 (여러 장 세트)
- [ ] 영상에 배경음악(BGM) 추가
- [ ] Claude 대본을 영상 내레이션에 반영
