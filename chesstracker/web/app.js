// ChessTracker UI. Talks to app.py over a small JSON API.
const $ = (id) => document.getElementById(id);
let S = null;              // latest /api/state
let corners = [];          // calibration corners being edited (camera pixels)
let dragIdx = null;
let clickMode = null;      // null | "fix" | "enter"
let clickFrom = null;

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const d = await r.json();
  if (!r.ok) { alert(d.error || "Something went wrong"); throw new Error(d.error); }
  return d;
}
const post = (path, body = {}) => api(path, body);

// ---------------- tabs ----------------
function showTab(name) {
  document.querySelectorAll(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === name));
  if (name === "library") loadLibrary();
}
document.querySelectorAll(".tab").forEach(b => b.onclick = () => showTab(b.dataset.tab));

// ---------------- wizard ----------------
function showStep(n) {
  [1, 2, 3].forEach(i => $("step" + i).classList.toggle("hidden", i !== n));
  document.querySelectorAll(".steps li").forEach(li => {
    const i = +li.dataset.step;
    li.classList.toggle("current", i === n); li.classList.toggle("done", i < n);
  });
  if (n === 2) corners = (S && S.calibration.corners) ? S.calibration.corners.map(p => p.slice()) : [];
}
async function scanCameras() {
  $("cameraSelect").innerHTML = "<option>Searching...</option>";
  const cams = await post("/api/cameras");
  const sel = $("cameraSelect");
  sel.innerHTML = cams.length ? "" : "<option>No camera found</option>";
  cams.forEach(c => { const o = document.createElement("option"); o.value = c.index; o.textContent = c.label; sel.appendChild(o); });
  if (S) sel.value = S.camera.index;
  $("camStatus").textContent = cams.length ? "" : "Check the cable and camera permission, then Search again.";
}
$("scanBtn").onclick = scanCameras;
$("cameraSelect").onchange = (e) => post("/api/camera", { index: +e.target.value });
$("toStep2").onclick = () => showStep(2);
$("back1").onclick = () => showStep(1);
$("back2").onclick = () => showStep(2);
$("toStep3").onclick = async () => {
  if (corners.length !== 4) return alert("Click all 4 corners of the board first.");
  await post("/api/corners", { corners }); await post("/api/calibration/save"); showStep(3);
};
$("rotateBtn").onclick = () => post("/api/rotate");
$("undoCorner").onclick = () => { corners.pop(); sendCorners(); };
$("clearCorners").onclick = () => { corners = []; sendCorners(); };
function sendCorners() { post("/api/corners", { corners }); }
function imgPoint(e) {
  const img = $("calibImg"), r = img.getBoundingClientRect();
  return [(e.clientX - r.left) * img.naturalWidth / r.width, (e.clientY - r.top) * img.naturalHeight / r.height];
}
$("calibArea").addEventListener("mousedown", (e) => {
  const p = imgPoint(e), img = $("calibImg"), scale = img.naturalWidth / img.getBoundingClientRect().width;
  dragIdx = corners.findIndex(c => Math.hypot(c[0] - p[0], c[1] - p[1]) < 18 * scale);
  if (dragIdx < 0) { dragIdx = null; if (corners.length < 4) { corners.push(p); sendCorners(); } }
  e.preventDefault();
});
window.addEventListener("mousemove", (e) => { if (dragIdx !== null) { corners[dragIdx] = imgPoint(e); sendCorners(); } });
window.addEventListener("mouseup", () => { dragIdx = null; });
$("startBtn").onclick = async () => { await post("/api/tracking/start"); showTab("play"); };

// ---------------- play ----------------
let boardKey = "";
function renderBoard() {
  const key = [S.fen, S.lastmove, S.settings.theme, S.settings.flipped].join("|");
  if (key === boardKey) return;
  boardKey = key;
  const q = new URLSearchParams({ fen: S.fen, theme: S.settings.theme, flipped: S.settings.flipped });
  if (S.lastmove) q.set("lastmove", S.lastmove);
  $("boardImg").src = "/api/board.svg?" + q;
}
function renderMoves(el, sans, current, onClick) {
  el.innerHTML = "";
  sans.forEach((san, i) => {
    if (i % 2 === 0) { const n = document.createElement("span"); n.className = "n"; n.textContent = (i / 2 + 1) + "."; el.appendChild(n); }
    const s = document.createElement("span"); s.className = "mv" + (i === current ? " cur" : ""); s.textContent = san;
    if (onClick) s.onclick = () => onClick(i + 1);
    el.appendChild(s);
  });
  if (sans.length % 2 === 1) el.appendChild(document.createElement("span"));
  el.scrollTop = el.scrollHeight;
}
function renderPlay() {
  renderBoard();
  const st = $("status");
  st.textContent = S.mode === "tracking" ? S.status : "Not tracking. Go to Setup and press Start tracking.";
  st.className = "status " + (S.mode === "tracking" ? S.status_kind : "info");
  const ask = $("ask");
  if (S.pending.length) {
    ask.classList.remove("hidden");
    const key = S.pending.join("|");
    if (ask.dataset.key !== key) {
      ask.dataset.key = key; ask.innerHTML = "";
      S.pending.forEach((txt, i) => { const b = document.createElement("button"); b.className = "primary"; b.textContent = txt; b.onclick = () => post("/api/confirm", { index: i }); ask.appendChild(b); });
      const no = document.createElement("button"); no.textContent = "None of these"; no.onclick = () => post("/api/reject"); ask.appendChild(no);
      const other = document.createElement("button"); other.className = "ghost"; other.textContent = "Other move..."; other.onclick = () => { post("/api/reject"); startClick("enter"); }; ask.appendChild(other);
    }
  } else { ask.classList.add("hidden"); ask.dataset.key = ""; }
  renderMoves($("moveList"), S.moves, S.moves.length - 1);
  $("recBtn").textContent = S.recording ? "⏹ Stop recording" : "⏺ Record video";
  $("recBtn").classList.toggle("danger", S.recording);
  const b = $("stillBadge");
  b.textContent = !S.camera.connected ? "Camera disconnected" : (S.mode !== "tracking" ? "" : (S.still ? "● board still" : "● movement"));
  b.style.color = S.still ? "#81b64c" : "#e6a23c";
}
// click-to-move on the digital board
function buildGrid() {
  const g = $("boardGrid"); g.innerHTML = "";
  for (let i = 0; i < 64; i++) { const d = document.createElement("div"); d.dataset.i = i; d.onclick = () => clickSquare(i); g.appendChild(d); }
}
function squareName(i) {
  const row = Math.floor(i / 8), col = i % 8, flipped = S.settings.flipped;
  const file = flipped ? 7 - col : col, rank = flipped ? row : 7 - row;
  return "abcdefgh"[file] + (rank + 1);
}
function startClick(mode) {
  if (S.mode !== "tracking") return alert("Start tracking first (Setup tab).");
  clickMode = mode; clickFrom = null;
  $("boardGrid").classList.add("active");
  $("clickHint").textContent = (mode === "fix" ? "Fix last move: " : "Enter a move: ") +
    "click the piece's start square, then its target square on the board. (Esc to cancel)";
}
function endClick() {
  clickMode = null; clickFrom = null; $("boardGrid").classList.remove("active");
  document.querySelectorAll(".grid div").forEach(d => d.classList.remove("sel")); $("clickHint").textContent = "";
}
async function clickSquare(i) {
  if (!clickMode) return;
  if (clickFrom === null) { clickFrom = i; $("boardGrid").children[i].classList.add("sel"); return; }
  const uci = squareName(clickFrom) + squareName(i), mode = clickMode;
  endClick();
  try { await post(mode === "fix" ? "/api/correct" : "/api/move", { move: uci }); } catch (e) { }
}
window.addEventListener("keydown", (e) => { if (e.key === "Escape") endClick(); });
$("fixBtn").onclick = () => { if (!S.moves.length) return alert("No move to fix yet."); startClick("fix"); };
$("enterBtn").onclick = () => startClick("enter");
$("undoBtn").onclick = () => post("/api/undo");
$("recBtn").onclick = async () => {
  const r = await post("/api/record");
  if (!r.recording) alert("Video saved:\n" + r.file + "\n\nYou'll find it in the ChessTracker folder, inside data > recordings.");
};
$("newBtn").onclick = () => { if (confirm("Start a new game? Set up the pieces in the starting position.")) post("/api/new_game"); };
$("flipBtn").onclick = () => post("/api/settings", { flipped: !S.settings.flipped });
$("saveBtn").onclick = () => { if (!S.moves.length) return alert("No moves to save yet."); $("gameName").value = ""; $("saveDlg").showModal(); };
$("cancelSave").onclick = () => $("saveDlg").close();
$("doSave").onclick = async () => { await post("/api/library/save", { name: $("gameName").value }); $("saveDlg").close(); $("status").textContent = "Game saved to the Library."; };

// ---------------- settings ----------------
$("settingsBtn").onclick = () => {
  const box = $("themes"); box.innerHTML = "";
  S.themes.forEach(t => {
    const b = document.createElement("button"); b.className = t === S.settings.theme ? "sel" : "";
    b.innerHTML = `<img src="/api/board.svg?theme=${t}&fen=${encodeURIComponent("8/8/8/8/8/8/8/8 w - - 0 1")}"><span>${t[0].toUpperCase() + t.slice(1)}</span>`;
    b.onclick = async () => { await post("/api/settings", { theme: t }); box.querySelectorAll("button").forEach(x => x.classList.remove("sel")); b.classList.add("sel"); };
    box.appendChild(b);
  });
  $("flipSetting").checked = S.settings.flipped;
  $("settingsDlg").showModal();
};
$("flipSetting").onchange = (e) => post("/api/settings", { flipped: e.target.checked });
$("closeSettings").onclick = () => $("settingsDlg").close();

// ---------------- library ----------------
let game = null, ply = 0, autoTimer = null;
async function loadLibrary() {
  const games = await api("/api/library");
  const el = $("gameList"); el.innerHTML = games.length ? "" : '<p class="hint">No saved games yet. Use "Save game" while playing.</p>';
  games.forEach(g => {
    const d = document.createElement("div"); d.className = "g" + (game && game.id === g.id ? " sel" : "");
    d.innerHTML = `<b></b><small>${g.date} ${g.time} · ${g.moves} moves</small>`; d.querySelector("b").textContent = g.name;
    d.onclick = () => openGame(g.id); el.appendChild(d);
  });
}
async function openGame(id) {
  game = await api("/api/game?id=" + encodeURIComponent(id)); ply = game.plies.length - 1; renderReplay(); loadLibrary();
}
function renderReplay() {
  if (!game) return;
  const p = game.plies[ply];
  const q = new URLSearchParams({ fen: p.fen, theme: S.settings.theme, flipped: S.settings.flipped });
  if (p.uci) q.set("lastmove", p.uci);
  $("replayImg").src = "/api/board.svg?" + q;
  $("rPos").textContent = `${ply} / ${game.plies.length - 1}`;
  const el = $("replayMoves"); el.classList.add("replay");
  renderMoves(el, game.plies.slice(1).map(x => x.san), ply - 1, (n) => { ply = n; renderReplay(); });
}
const go = (n) => { if (game) { ply = Math.max(0, Math.min(game.plies.length - 1, n)); renderReplay(); } };
$("rFirst").onclick = () => go(0); $("rLast").onclick = () => go(1e9);
$("rPrev").onclick = () => go(ply - 1); $("rNext").onclick = () => go(ply + 1);
$("rPlay").onclick = () => {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null; $("rPlay").textContent = "▷ Auto"; return; }
  if (game && ply >= game.plies.length - 1) go(0);
  $("rPlay").textContent = "❚❚ Stop";
  autoTimer = setInterval(() => { if (!game || ply >= game.plies.length - 1) { $("rPlay").click(); } else go(ply + 1); }, 1200);
};
window.addEventListener("keydown", (e) => {
  if (!$("library").classList.contains("active")) return;
  if (e.key === "ArrowLeft") go(ply - 1); if (e.key === "ArrowRight") go(ply + 1);
});
$("copyPgn").onclick = () => { if (game) navigator.clipboard.writeText(game.pgn); };
$("deleteGame").onclick = async () => {
  if (game && confirm(`Delete "${game.name}"?`)) { await post("/api/library/delete", { id: game.id }); game = null; $("replayImg").removeAttribute("src"); $("replayMoves").innerHTML = ""; loadLibrary(); }
};

// ---------------- polling ----------------
let warpOn = false;
async function poll() {
  try {
    S = await api("/api/state");
    renderPlay();
    const hasCal = S.calibration.corners.length === 4;
    if (hasCal && !warpOn) { $("warpImg").src = "/stream.mjpg?view=board"; warpOn = true; }
    if (!hasCal && warpOn) { $("warpImg").removeAttribute("src"); warpOn = false; }
    const oh = $("orientHint");
    oh.textContent = S.calibration.orientation_ok === false ? "a1 looks like a light square: press Rotate." : "";
    if (game) renderReplay.lastTheme !== S.settings.theme + S.settings.flipped && (renderReplay.lastTheme = S.settings.theme + S.settings.flipped, renderReplay());
  } catch (e) { $("status").textContent = "Lost connection to the app. Is its window still open?"; }
  setTimeout(poll, 400);
}

(async function init() {
  buildGrid();
  S = await api("/api/state");
  if (S.mode === "tracking") showTab("play");
  scanCameras();
  poll();
})();
