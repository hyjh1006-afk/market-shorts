# -*- coding: utf-8 -*-
"""YouTube 자동 업로드 (YouTube Data API v3).

준비물 (최초 1회):
1. console.cloud.google.com → 프로젝트 생성 → "YouTube Data API v3" 사용 설정
2. OAuth 동의 화면 구성 (외부, 테스트 사용자에 본인 구글 계정 추가)
3. 사용자 인증 정보 → OAuth 클라이언트 ID (데스크톱 앱) → JSON 다운로드
   → 이 폴더에 client_secret.json 으로 저장
4. python uploader.py 실행 → 브라우저에서 구글 로그인 1회 → token.json 자동 생성
   이후로는 로그인 없이 자동 업로드된다.

주의: 구글 미검증 API 프로젝트로 올린 영상은 '비공개'로 잠길 수 있다.
      그 경우 PRIVACY를 "private"로 두고 유튜브 앱/스튜디오에서 공개 전환하거나,
      구글에 API 감사(무료)를 신청하면 공개 업로드가 가능해진다.
"""
from pathlib import Path

BASE = Path(__file__).parent
CLIENT_SECRET = BASE / "client_secret.json"
TOKEN = BASE / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",   # 연결된 채널 확인용
]

PRIVACY = "public"   # private | unlisted | public
DESCRIPTION = ("매일 주식·코인·뉴스 데이터를 바탕으로 돈의 흐름을 정리합니다.\n"
               "본 영상은 투자 조언이 아닌 정보 제공 목적입니다.\n"
               "#주식 #코인 #시장브리핑")
TAGS = ["주식", "코인", "시장브리핑", "shorts", "투자뉴스"]

# 시간표 슬롯 → 제목에 들어갈 시간대 이름 (schedule.json의 기본 6개 기준)
SLOT_LABELS = {
    "07:00": "아침", "08:30": "오전", "12:30": "점심",
    "18:00": "저녁", "21:00": "오후", "22:30": "밤",
}


def _default_title() -> str:
    """예: '26년 7월 4일 아침 시장 브리핑' (한국시간 기준)"""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc) + timedelta(hours=9)
    slot = f"{now.hour:02d}:{'30' if now.minute >= 30 else '00'}"
    label = SLOT_LABELS.get(slot)
    if label is None:  # 시간표에 없는 시각(수동 실행 등)은 시간대로 추정
        h = now.hour
        label = ("아침" if 5 <= h < 8 else "오전" if 8 <= h < 11 else
                 "점심" if 11 <= h < 14 else "오후" if 14 <= h < 18 else
                 "저녁" if 18 <= h < 21 else "밤")
    if now.weekday() >= 5:  # 토·일: 주간 결산 모드
        return f"{now.year % 100:02d}/{now.month:02d}/{now.day:02d} {label} 주간 결산 - 돈의 흐름 #shorts"
    return f"{now.year % 100:02d}/{now.month:02d}/{now.day:02d} {label} 시장 브리핑 - 돈의 흐름 #shorts"


def is_configured() -> bool:
    return CLIENT_SECRET.exists()


def _get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            creds = None   # 토큰 만료/폐기 → 새 로그인으로 진행
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
        creds = flow.run_local_server(port=0)   # 브라우저 열려서 1회 로그인
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_video(path: str, title: str | None = None,
                 description: str | None = None,
                 privacy: str | None = None) -> str:
    """영상을 업로드하고 videoId를 반환한다."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = _get_credentials()
    yt = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title or _default_title(),
            "description": description or DESCRIPTION,
            "tags": TAGS,
            "categoryId": "25",  # News & Politics
        },
        "status": {
            "privacyStatus": privacy or PRIVACY,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(path, mimetype="video/mp4", resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _status, response = request.next_chunk()
    return response["id"]


def _check_channel(creds) -> str:
    """토큰이 어느 채널에 연결됐는지 확인한다."""
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=creds)
    resp = yt.channels().list(part="snippet", mine=True).execute()
    items = resp.get("items", [])
    if not items:
        return "(채널 확인 실패)"
    sn = items[0]["snippet"]
    handle = sn.get("customUrl", "")
    return f"{sn['title']} ({handle})"


def _write_github_secrets_helper():
    """GitHub Actions 시크릿에 붙여넣을 내용을 파일로 저장한다 (로컬 전용, git 제외)."""
    out = BASE / "github_secrets_붙여넣기.txt"
    text = (
        "GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret\n"
        "아래 두 개를 각각 등록하세요 (이 파일은 절대 공유 금지!)\n\n"
        "=== 이름: YT_CLIENT_SECRET_JSON / 값: ===\n"
        + CLIENT_SECRET.read_text(encoding="utf-8").strip() + "\n\n"
        "=== 이름: YT_TOKEN_JSON / 값: ===\n"
        + TOKEN.read_text(encoding="utf-8").strip() + "\n"
    )
    out.write_text(text, encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys
    if not is_configured():
        print("client_secret.json이 없습니다. 파일 상단의 준비물 안내를 따라주세요.")
        sys.exit(1)
    # 인자 없으면 인증만 수행 (token.json 생성)
    if len(sys.argv) < 2:
        print("브라우저가 열립니다. 구글 로그인 후 '계정 선택' 화면에서")
        print("반드시 업로드할 유튜브 채널(rich_youtube_kr)을 선택하세요!")
        creds = _get_credentials()
        print(f"\n인증 완료! 연결된 채널: {_check_channel(creds)}")
        helper = _write_github_secrets_helper()
        print(f"\nGitHub 자동 업로드용 시크릿 내용을 저장했습니다:\n  {helper}")
        print("이 파일을 열어 안내대로 GitHub에 등록하면 매일 아침 자동 업로드가 켜집니다.")
    else:
        vid = upload_video(sys.argv[1])
        print(f"업로드 완료: https://youtube.com/shorts/{vid}")
