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
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent
CLIENT_SECRET = BASE / "client_secret.json"
TOKEN = BASE / "token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

PRIVACY = "private"   # private | unlisted | public
TITLE_TEMPLATE = "{date} 시장 브리핑 — 오늘 돈은 어디로? #shorts"
DESCRIPTION = ("매일 아침 주식·코인·뉴스 데이터를 바탕으로 돈의 흐름을 정리합니다.\n"
               "본 영상은 투자 조언이 아닌 정보 제공 목적입니다.\n"
               "#주식 #코인 #시장브리핑")
TAGS = ["주식", "코인", "시장브리핑", "shorts", "투자뉴스"]


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
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
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
            "title": title or TITLE_TEMPLATE.format(date=date.today().strftime("%m/%d")),
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


if __name__ == "__main__":
    import sys
    if not is_configured():
        print("client_secret.json이 없습니다. 파일 상단의 준비물 안내를 따라주세요.")
        sys.exit(1)
    # 인자 없으면 인증만 수행 (token.json 생성)
    if len(sys.argv) < 2:
        _get_credentials()
        print("인증 완료! token.json 생성됨. 이제 자동 업로드가 가능합니다.")
    else:
        vid = upload_video(sys.argv[1])
        print(f"업로드 완료: https://youtube.com/shorts/{vid}")
