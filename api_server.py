# -*- coding: utf-8 -*-
"""모바일 리모컨 API 서버 (포트 8788).

폰의 모바일 웹(mobile-web/)이 이 API를 호출한다.
Streamlit 웹앱과 같은 DB(data/market.db)·output 폴더를 공유한다.

실행: python api_server.py  (또는 모바일리모컨.bat)
"""
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from config import OUTPUT_DIR


# ── 잡 저장소 (티스토리 리모컨과 같은 패턴, 단순화) ──────────

@dataclass
class Job:
    job_id: str
    kind: str
    status: str = "queued"      # queued | running | completed | failed
    message: str = ""
    result: dict = field(default_factory=dict)


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._busy = False

    def create(self, kind: str) -> Job:
        with self._lock:
            if self._busy:
                raise HTTPException(409, "이미 실행 중인 작업이 있습니다. 끝난 뒤 다시 시도하세요.")
            self._busy = True
            job = Job(job_id=str(uuid.uuid4())[:8], kind=kind)
            self._jobs[job.job_id] = job
            return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kw):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for k, v in kw.items():
                    setattr(job, k, v)
                if kw.get("status") in ("completed", "failed"):
                    self._busy = False

    def run(self, job: Job, worker):
        def _run():
            try:
                self.update(job.job_id, status="running", message="작업 시작")
                result = worker(lambda msg: self.update(job.job_id, message=msg))
                self.update(job.job_id, status="completed", message="완료", result=result or {})
            except Exception as e:
                self.update(job.job_id, status="failed", message=str(e) or "오류")
        threading.Thread(target=_run, daemon=True).start()


store = JobStore()


# ── 작업 정의 ────────────────────────────────────────────────

def work_collect(progress) -> dict:
    import db
    from collectors.stocks import collect_stocks
    from collectors.coins import collect_coins
    from collectors.news import collect_news

    progress("주식 시세 수집 중...")
    stocks = collect_stocks()
    db.save_stocks(stocks)
    progress(f"주식 {len(stocks)}개 저장. 코인 수집 중...")
    coins = collect_coins()
    db.save_coins(coins)
    progress(f"코인 {len(coins)}개 저장. 뉴스 수집·선별 중...")
    news = collect_news()
    db.save_news(news)
    return {"stocks": len(stocks), "coins": len(coins), "news": len(news)}


def work_video(progress) -> dict:
    import db
    from generators.video_gen import generate_video

    progress("AI 내레이션·이미지 생성 → 영상 합성 중... (2~3분)")
    snapshot = db.load_snapshot()
    if not snapshot["stocks"]:
        raise RuntimeError("오늘 데이터가 없습니다. 먼저 데이터 수집을 실행하세요.")
    path = generate_video(snapshot)
    db.save_generated("shorts_video", path)
    return {"video": Path(path).name}


def work_daily(progress) -> dict:
    r1 = work_collect(progress)
    r2 = work_video(progress)
    return {**r1, **r2}


def work_upload(progress, video_name: str) -> dict:
    from uploader import upload_video, is_configured
    if not is_configured():
        raise RuntimeError("유튜브 업로드가 아직 설정되지 않았습니다 (client_secret.json 필요 — README 참고).")
    path = OUTPUT_DIR / video_name
    if not path.exists():
        raise RuntimeError(f"영상 파일이 없습니다: {video_name}")
    progress("유튜브 업로드 중...")
    video_id = upload_video(str(path))
    return {"youtube_id": video_id, "url": f"https://youtube.com/shorts/{video_id}"}


# ── FastAPI 앱 ───────────────────────────────────────────────

app = FastAPI(title="시장 브리핑 Shorts 리모컨 API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(Exception)
async def unhandled(_req: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"message": str(exc)})


@app.get("/health")
def health():
    from generators import llm_gen
    try:
        from uploader import is_configured
        yt = is_configured()
    except Exception:
        yt = False
    return {"ok": True, "ai": llm_gen.provider(), "youtube": yt}


@app.post("/jobs/daily")
def start_daily():
    job = store.create("daily")
    store.run(job, work_daily)
    return {"job_id": job.job_id}


@app.post("/jobs/collect")
def start_collect():
    job = store.create("collect")
    store.run(job, work_collect)
    return {"job_id": job.job_id}


@app.post("/jobs/video")
def start_video():
    job = store.create("video")
    store.run(job, work_video)
    return {"job_id": job.job_id}


@app.post("/jobs/upload/{video_name}")
def start_upload(video_name: str):
    job = store.create("upload")
    store.run(job, lambda progress: work_upload(progress, video_name))
    return {"job_id": job.job_id}


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "없는 작업입니다.")
    return {"job_id": job.job_id, "kind": job.kind, "status": job.status,
            "message": job.message, "result": job.result}


@app.get("/videos")
def list_videos():
    files = sorted(OUTPUT_DIR.glob("shorts_*.mp4"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"name": f.name, "size_mb": round(f.stat().st_size / 1e6, 1)}
            for f in files[:20]]


@app.get("/videos/{name}")
def get_video(name: str):
    # 경로 탈출 방지
    safe = Path(name).name
    path = OUTPUT_DIR / safe
    if not path.exists() or path.suffix != ".mp4":
        raise HTTPException(404, "없는 영상입니다.")
    return FileResponse(path, media_type="video/mp4", filename=safe)


if __name__ == "__main__":
    host = os.environ.get("API_HOST", "0.0.0.0")
    port = int(os.environ.get("API_PORT", "8788"))
    uvicorn.run(app, host=host, port=port, log_level="info")
