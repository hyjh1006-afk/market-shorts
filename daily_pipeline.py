# -*- coding: utf-8 -*-
"""매일 아침 자동 실행: 수집 → 영상 생성 → 유튜브 업로드.

Windows 작업 스케줄러가 매일 아침 이 스크립트를 실행한다.
유튜브 설정(client_secret.json + token.json)이 없으면 업로드만 건너뛴다.
로그: logs/daily_YYYY-MM-DD.log
"""
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

LOG_DIR = BASE / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _materialize_youtube_secrets():
    """GitHub Actions에서는 시크릿(환경변수)으로 유튜브 인증 파일을 만든다."""
    for env_name, fname in [("YT_CLIENT_SECRET_JSON", "client_secret.json"),
                            ("YT_TOKEN_JSON", "token.json")]:
        val = os.environ.get(env_name)
        path = BASE / fname
        if val and not path.exists():
            path.write_text(val, encoding="utf-8")


def log(msg: str):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line)
    with open(LOG_DIR / f"daily_{datetime.now():%Y-%m-%d}.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main() -> int:
    import db
    from collectors.stocks import collect_stocks
    from collectors.coins import collect_coins
    from collectors.news import collect_news
    from generators.video_gen import generate_video

    log("=== 데일리 파이프라인 시작 ===")
    _materialize_youtube_secrets()

    log("1/3 데이터 수집")
    stocks = collect_stocks()
    db.save_stocks(stocks)
    log(f"  주식 {len(stocks)}개")
    try:
        coins = collect_coins()
        db.save_coins(coins)
        log(f"  코인 {len(coins)}개")
    except Exception as e:
        log(f"  코인 수집 실패(무시): {e}")
    news = collect_news()
    db.save_news(news)
    log(f"  뉴스 {len(news)}건")

    log("2/3 영상 생성 (AI 내레이션·이미지)")
    video_path = generate_video(db.load_snapshot())
    db.save_generated("shorts_video", video_path)
    log(f"  생성: {Path(video_path).name}")

    log("3/3 유튜브 업로드")
    try:
        from uploader import upload_video, is_configured, TOKEN
        if not is_configured():
            log("  건너뜀: client_secret.json 없음 (uploader.py 상단 안내 참고)")
        elif not TOKEN.exists():
            log("  건너뜀: 최초 인증 필요 — PC에서 'python uploader.py' 1회 실행")
        else:
            vid = upload_video(video_path)
            log(f"  업로드 완료: https://youtube.com/shorts/{vid}")
    except Exception as e:
        log(f"  업로드 실패: {e}")

    log("=== 완료 ===")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log("치명적 오류:\n" + traceback.format_exc())
        sys.exit(1)
