// 시장 브리핑 모바일 리모컨
const $ = (id) => document.getElementById(id);

let API = localStorage.getItem("apiBase") || `http://${location.hostname}:8788`;
$("apiBase").value = API;

let polling = null;

async function api(path, opts = {}) {
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { msg = (await res.json()).detail || (await res.json()).message || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function setStatus(text, cls = "") {
  const el = $("status");
  el.className = "status " + cls;
  el.textContent = text;
  el.classList.remove("hidden");
}

function setButtons(disabled) {
  ["btnDaily", "btnCollect", "btnVideo"].forEach(id => $(id).disabled = disabled);
}

async function checkHealth() {
  try {
    const h = await api("/health");
    const yt = h.youtube ? " · 유튜브 연결됨" : "";
    $("conn").textContent = `연결됨 (AI: ${h.ai || "없음"}${yt})`;
    $("conn").className = "badge on";
    return true;
  } catch {
    $("conn").textContent = "연결 안 됨 — 설정에서 API 주소 확인";
    $("conn").className = "badge off";
    return false;
  }
}

async function startJob(path, label) {
  try {
    setButtons(true);
    setStatus(`${label} 시작…`, "spin");
    const { job_id } = await api(path, { method: "POST" });
    polling = setInterval(async () => {
      try {
        const j = await api(`/jobs/${job_id}`);
        if (j.status === "running" || j.status === "queued") {
          setStatus(j.message || "진행 중…", "spin");
        } else if (j.status === "completed") {
          clearInterval(polling); setButtons(false);
          let extra = "";
          if (j.result.video) extra = ` → ${j.result.video}`;
          if (j.result.url) extra = ` → ${j.result.url}`;
          setStatus(`✅ ${label} 완료${extra}`, "ok");
          loadVideos();
        } else {
          clearInterval(polling); setButtons(false);
          setStatus(`❌ 실패: ${j.message}`, "err");
        }
      } catch (e) {
        clearInterval(polling); setButtons(false);
        setStatus(`❌ 상태 확인 실패: ${e.message}`, "err");
      }
    }, 2000);
  } catch (e) {
    setButtons(false);
    setStatus(`❌ ${e.message}`, "err");
  }
}

async function loadVideos() {
  try {
    const vids = await api("/videos");
    if (!vids.length) { $("videos").textContent = "아직 만든 영상이 없어요."; return; }
    $("videos").innerHTML = "";
    vids.forEach(v => {
      const div = document.createElement("div");
      div.className = "video-item";
      const name = document.createElement("div");
      name.className = "video-name";
      name.textContent = `${v.name} (${v.size_mb}MB)`;
      const acts = document.createElement("div");
      acts.className = "acts";

      const play = document.createElement("button");
      play.textContent = "▶";
      play.onclick = () => {
        const p = $("player");
        p.src = `${API}/videos/${encodeURIComponent(v.name)}`;
        p.classList.remove("hidden");
        p.play();
      };
      const dl = document.createElement("button");
      dl.textContent = "⬇";
      dl.onclick = () => window.open(`${API}/videos/${encodeURIComponent(v.name)}`, "_blank");
      const up = document.createElement("button");
      up.textContent = "📺 업로드";
      up.onclick = () => startJob(`/jobs/upload/${encodeURIComponent(v.name)}`, "유튜브 업로드");

      acts.append(play, dl, up);
      div.append(name, acts);
      $("videos").append(div);
    });
  } catch {
    $("videos").textContent = "영상 목록을 불러올 수 없어요 (API 연결 확인).";
  }
}

// 플레이어 닫기 (탭하면 닫힘 버튼 없이 배경 탭)
$("player").addEventListener("pause", () => {
  // 재생 끝/일시정지 시 전체화면 닫기
});
$("player").addEventListener("click", (e) => {
  if (e.target.paused) return;
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { $("player").classList.add("hidden"); $("player").pause(); }
});
$("player").addEventListener("ended", () => {
  $("player").classList.add("hidden");
});
// 더블탭으로 닫기
let lastTap = 0;
$("player").addEventListener("touchend", () => {
  const now = Date.now();
  if (now - lastTap < 400) { $("player").classList.add("hidden"); $("player").pause(); }
  lastTap = now;
});

$("btnDaily").onclick = () => startJob("/jobs/daily", "오늘 영상 만들기");
$("btnCollect").onclick = () => startJob("/jobs/collect", "데이터 수집");
$("btnVideo").onclick = () => startJob("/jobs/video", "영상 생성");
$("btnSave").onclick = () => {
  API = $("apiBase").value.trim().replace(/\/$/, "");
  localStorage.setItem("apiBase", API);
  checkHealth().then(ok => ok && loadVideos());
};

checkHealth().then(ok => ok && loadVideos());
setInterval(checkHealth, 15000);
