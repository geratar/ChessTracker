// ChessEmeg UI. Talks to app.py over a small JSON API.
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
function showTab(name, force) {
  const current = document.querySelector(".view.active").id;
  if (!force && current === "play" && name !== "play" && S && S.unsaved)
    return guardUnsaved("You're leaving the game. Save it first? (It stays open on the Play tab either way.)", () => showTab(name, true));
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
$("startBtn").onclick = () => guardUnsaved("Starting tracking begins a new game. Save the current one first?",
  () => choosePlayers(async (white, black) => { await post("/api/tracking/start", { white, black }); showTab("play", true); }));

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
const MARK_CLASS = { "??": "mark-qq", "?": "mark-q", "?!": "mark-qe" };
function renderMoves(el, sans, current, onClick, marks) {
  el.innerHTML = "";
  sans.forEach((san, i) => {
    if (i % 2 === 0) { const n = document.createElement("span"); n.className = "n"; n.textContent = (i / 2 + 1) + "."; el.appendChild(n); }
    const s = document.createElement("span"); s.className = "mv" + (i === current ? " cur" : ""); s.textContent = san;
    const mk = marks && marks[i] && marks[i].mark;
    if (mk) { const m = document.createElement("span"); m.className = MARK_CLASS[mk]; m.textContent = mk; s.appendChild(m); }
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
  const playing = S.mode === "tracking";
  ["finishBtn", "fixBtn", "enterBtn", "undoBtn"].forEach(id => $(id).classList.toggle("hidden", !playing));
  $("saveBtn").classList.add("hidden");               // saving happens through Finish game
  $("newBtn").classList.toggle("hidden", playing);    // only after the game is finished
  $("recBtn").textContent = S.recording ? "⏹ Stop recording" : "⏺ Record video";
  $("recBtn").classList.toggle("danger", S.recording);
  $("clock").classList.toggle("hidden", !playing);
  if (playing && S.clock) {
    const fmt = (x) => `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}`;
    const P = S.players || {};
    ["white", "black"].forEach(side => {
      const p = P[side], el = $(side === "white" ? "clockWhite" : "clockBlack").querySelector(".who");
      const html = p ? `${avatarImg(p.avatar)}<span>${esc(p.name)}</span>` : `<span>${side === "white" ? "White" : "Black"}</span>`;
      if (el.dataset.html !== html) { el.dataset.html = html; el.innerHTML = html; }
    });
    $("clockWhite").querySelector("b").textContent = fmt(S.clock.white);
    $("clockBlack").querySelector("b").textContent = fmt(S.clock.black);
    $("clockWhite").classList.toggle("active", S.clock.turn === "white");
    $("clockBlack").classList.toggle("active", S.clock.turn === "black");
    $("tapBtn").disabled = S.clock.reading;
  }
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
  if (!r.recording) alert("Video saved:\n" + r.file + "\n\nYou'll find it in the app's folder, inside data > recordings.");
};
$("newBtn").onclick = () => guardUnsaved("Start a new game? Save this one first?", () => {
  if (!S.calibration.saved) { showTab("setup", true); return; }
  choosePlayers((white, black) => post("/api/new_game", { white, black }));
});

// ---------------- players ----------------
let playerList = [], avatarCount = 20, pick = { white: null, black: null }, newAvatar = 0, playersThen = null;
const avatarImg = (n) => n === null || n === undefined ? "" : `<img class="av" src="/api/avatar/${n}.svg" alt="">`;
const esc = (t) => String(t).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
async function choosePlayers(then) {
  const r = await api("/api/players"); playerList = r.players; avatarCount = r.avatars;
  let last = {}; try { last = JSON.parse(localStorage.getItem("lastPlayers") || "{}"); } catch (e) { }
  const exists = (id) => id === "anon" || playerList.some(p => p.id === id) ? id : null;
  pick = { white: exists(last.white), black: exists(last.black) };
  playersThen = then; renderPick(); showNewPlayer(!playerList.length);
  $("playersDlg").showModal();
}
function renderPick() {
  ["white", "black"].forEach(side => {
    const other = side === "white" ? "black" : "white", el = $(side === "white" ? "pickWhite" : "pickBlack");
    el.innerHTML = "";
    const anon = document.createElement("button");      // can be picked for both sides
    anon.className = pick[side] === "anon" ? "sel" : "";
    anon.innerHTML = `<span class="av anon">?</span><span>Anonymous</span>`;
    anon.onclick = () => { pick[side] = pick[side] === "anon" ? null : "anon"; renderPick(); };
    el.appendChild(anon);
    playerList.forEach(p => {
      const b = document.createElement("button");
      b.className = pick[side] === p.id ? "sel" : ""; b.disabled = pick[other] === p.id;
      b.innerHTML = `${avatarImg(p.avatar)}<span>${esc(p.name)}</span>`;
      b.onclick = () => { pick[side] = pick[side] === p.id ? null : p.id; renderPick(); };
      el.appendChild(b);
    });
  });
}
function showNewPlayer(on) {
  $("newPlayer").classList.toggle("hidden", !on); $("newPlayerBtn").classList.toggle("hidden", on);
  if (!on) return;
  $("playerName").value = ""; newAvatar = playerList.length % avatarCount;
  const g = $("avatarGrid"); g.innerHTML = "";
  for (let i = 0; i < avatarCount; i++) {
    const b = document.createElement("button"); b.className = i === newAvatar ? "sel" : "";
    b.innerHTML = `<img src="/api/avatar/${i}.svg" alt="avatar ${i + 1}">`;
    b.onclick = () => { newAvatar = i; g.querySelectorAll("button").forEach((x, j) => x.classList.toggle("sel", j === i)); };
    g.appendChild(b);
  }
  $("playerName").focus();
}
$("newPlayerBtn").onclick = () => showNewPlayer(true);
$("newPlayerCancel").onclick = () => showNewPlayer(false);
$("newPlayerSave").onclick = async () => {
  const name = $("playerName").value.trim();
  if (!name) return alert("Type a name for the player.");
  const p = await post("/api/players/create", { name, avatar: newAvatar });
  if (!p || !p.id) return;
  playerList.push(p);
  if (!pick.white || pick.white === "anon") pick.white = p.id; else if (!pick.black || pick.black === "anon") pick.black = p.id;
  showNewPlayer(false); renderPick();
};
$("playerName").addEventListener("keydown", (e) => { if (e.key === "Enter") $("newPlayerSave").click(); });
$("swapPlayers").onclick = () => { pick = { white: pick.black, black: pick.white }; renderPick(); };
$("playersCancel").onclick = () => { playersThen = null; $("playersDlg").close(); };
$("playersGo").onclick = async () => {
  if (!pick.white || !pick.black) return alert("Pick a player for White and for Black (Anonymous is fine too).");
  localStorage.setItem("lastPlayers", JSON.stringify(pick));
  const then = playersThen; playersThen = null; $("playersDlg").close();
  const id = (x) => x === "anon" ? null : x;
  if (then) await then(id(pick.white), id(pick.black));
};
// "Move done": like pressing a chess clock
async function tap() { if (S && S.mode === "tracking" && !S.pending.length) { try { await post("/api/tap"); } catch (e) {} } }
$("tapBtn").onclick = (e) => { e.currentTarget.blur(); tap(); };
document.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || e.repeat || document.querySelector("dialog[open]")) return;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;
  if (!S || S.mode !== "tracking") return;
  e.preventDefault(); tap();
});
$("flipBtn").onclick = () => post("/api/settings", { flipped: !S.settings.flipped });
let afterSave = null, finishing = false;
async function finishWithoutSaving() {
  $("saveDlg").close(); finishing = false; afterSave = null;
  await post("/api/tracking/stop");
  S.unsaved = false;
  $("status").textContent = "Game finished (not saved).";
}
function openSave(then, finish) {
  if (!S.moves.length) {
    if (finish) return finishWithoutSaving();      // nothing played yet: nothing to save
    return alert("No moves to save yet.");
  }
  afterSave = then || null; finishing = !!finish;
  $("saveTitle").textContent = finish ? "Finish game" : "Save game";
  $("doSave").textContent = finish ? "Finish & save" : "Save";
  $("doSaveAnalyze").classList.toggle("hidden", !finish);
  $("finishNoSave").classList.toggle("hidden", !finish);
  $("gameName").value = "";
  const r = document.querySelector(`input[name=result][value="${S.outcome}"]`) || document.querySelector('input[name=result][value="*"]');
  r.checked = true;
  if (finish && S.outcome === "*") document.querySelectorAll("input[name=result]").forEach(x => x.checked = false);
  $("saveDlg").showModal();
}
$("saveBtn").onclick = () => openSave();
$("cancelSave").onclick = () => { afterSave = null; $("saveDlg").close(); };
async function doSave(analyze) {
  const picked = document.querySelector("input[name=result]:checked");
  if (!picked) return alert("Choose who won (or Draw / Not finished).");
  const result = picked.value;
  const saved = await post("/api/library/save", { name: $("gameName").value, result });
  $("saveDlg").close(); $("status").textContent = "Game saved to the Library.";
  S.unsaved = false;
  if (finishing) {
    finishing = false; afterSave = null;
    await post("/api/tracking/stop");
    showTab("library", true);
    await openGame(saved.id);
    if (analyze) $("analyzeBtn").click();
    return;
  }
  const then = afterSave; afterSave = null; if (then) then();
}
$("doSave").onclick = () => doSave(false);
$("finishNoSave").onclick = finishWithoutSaving;
$("doSaveAnalyze").onclick = () => doSave(true);
$("finishBtn").onclick = () => {
  if (S.mode !== "tracking") return alert("No game in progress.");
  openSave(null, true);
};

// ask before an unsaved game could be lost
let unsavedThen = null;
function guardUnsaved(text, proceed) {
  if (!S || !S.unsaved) return proceed();
  unsavedThen = proceed; $("unsavedText").textContent = text; $("unsavedDlg").showModal();
}
$("unsavedCancel").onclick = () => { unsavedThen = null; $("unsavedDlg").close(); };
$("unsavedDiscard").onclick = () => { const p = unsavedThen; unsavedThen = null; $("unsavedDlg").close(); if (p) p(); };
$("unsavedSave").onclick = () => { const p = unsavedThen; unsavedThen = null; $("unsavedDlg").close(); openSave(p); };
window.addEventListener("beforeunload", (e) => { if (S && S.unsaved) { e.preventDefault(); e.returnValue = ""; } });

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
  document.querySelectorAll("#detectModes button").forEach(b => {
    b.classList.toggle("sel", b.dataset.detect === (S.settings.detect || "auto"));
    b.onclick = async () => { await post("/api/settings", { detect: b.dataset.detect });
      document.querySelectorAll("#detectModes button").forEach(x => x.classList.toggle("sel", x === b)); };
  });
  document.querySelectorAll("#speeds button").forEach(b => {
    b.classList.toggle("sel", b.dataset.speed === (S.settings.speed || "normal"));
    b.onclick = async () => { await post("/api/settings", { speed: b.dataset.speed });
      document.querySelectorAll("#speeds button").forEach(x => x.classList.toggle("sel", x === b)); };
  });
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
    const res = { "1-0": "1-0", "0-1": "0-1", "1/2-1/2": "½-½" }[g.result] || "";
    const who = (p, fallback) => p ? `${avatarImg(p.avatar)}<span>${esc(p.name)}</span>` : `<span>${fallback}</span>`;
    const vs = g.white || g.black ? `<div class="vs">${who(g.white, "Anonymous")}<small>vs</small>${who(g.black, "Anonymous")}</div>` : "";
    d.innerHTML = `<span class="res">${res}</span><b></b>${vs}<small>${g.date} ${g.time} · ${g.moves} moves</small>`; d.querySelector("b").textContent = g.name;
    d.onclick = () => openGame(g.id); el.appendChild(d);
  });
}
let ana = null, anaTimer = null;
async function openGame(id) {
  game = await api("/api/game?id=" + encodeURIComponent(id)); ply = game.plies.length - 1; vari = null; replayFrom = null;
  ana = null; clearTimeout(anaTimer); $("anaMsg").textContent = ""; $("analyzeBtn").classList.remove("hidden");
  await pollAnalysis(false);
  renderReplay(); loadLibrary();
}
async function pollAnalysis(keepGoing) {
  if (!game) return;
  const id = game.id;
  const st = await api("/api/analysis?id=" + encodeURIComponent(id));
  if (!game || game.id !== id) return;
  const prog = $("anaProgress");
  if (st.state === "done") {
    ana = st.result; prog.classList.add("hidden"); $("analyzeBtn").classList.add("hidden"); $("anaMsg").textContent = "";
    renderReplay();
  } else if (st.state === "running" || st.state === "downloading") {
    prog.classList.remove("hidden"); $("anaFill").style.width = Math.round((st.progress || 0) * 100) + "%";
    $("anaMsg").textContent = st.message || ""; $("analyzeBtn").classList.add("hidden");
    anaTimer = setTimeout(() => pollAnalysis(true), 500);
  } else if (st.state === "error") {
    prog.classList.add("hidden"); $("analyzeBtn").classList.remove("hidden"); $("anaMsg").textContent = st.message;
  } else { prog.classList.add("hidden"); $("analyzeBtn").classList.remove("hidden"); }
}
$("analyzeBtn").onclick = async () => {
  if (!game) return alert("Open a saved game first.");
  await post("/api/analyze", { id: game.id }); $("anaMsg").textContent = "Starting..."; pollAnalysis(true);
};
function evalText(e) {
  if (e.mate !== null && e.mate !== undefined) return (e.mate > 0 ? "M" : "-M") + Math.abs(e.mate);
  if (Math.abs(e.cp) >= 10000) return e.cp > 0 ? "1-0" : "0-1";
  return (e.cp > 0 ? "+" : "") + (e.cp / 100).toFixed(1);
}
function renderAnalysis() {
  const bar = $("evalBar"), graph = $("evalGraph");
  if (!ana) { bar.classList.add("hidden"); graph.classList.add("hidden"); $("bestLine").textContent = ""; return; }
  const e = ana.evals[ply], flipped = S.settings.flipped;
  bar.classList.remove("hidden"); graph.classList.remove("hidden");
  const clamp = Math.max(-1000, Math.min(1000, e.cp)), whiteShare = 50 + clamp / 20;
  $("evalFill").style.height = (flipped ? 100 - whiteShare : whiteShare) + "%";
  $("evalFill").style.background = flipped ? "#2b2b2b" : "#f0f0f0";
  bar.style.background = flipped ? "#f0f0f0" : "#2b2b2b";
  const t = $("evalText"); t.textContent = evalText(e);
  const whiteTop = flipped; t.style.top = (e.cp >= 0) === whiteTop ? "4px" : ""; t.style.bottom = (e.cp >= 0) === whiteTop ? "" : "4px";
  // graph
  const n = ana.evals.length, W = 400, Hh = 100;
  const y = (cp) => Hh / 2 - Math.max(-1000, Math.min(1000, cp)) / 1000 * (Hh / 2 - 4);
  const pts = ana.evals.map((v, i) => `${(i / Math.max(1, n - 1) * W).toFixed(1)},${y(v.cp).toFixed(1)}`);
  const area = `0,${Hh} ${pts.join(" ")} ${W},${Hh}`;
  const cx = ply / Math.max(1, n - 1) * W;
  let dots = "";
  ana.moves.forEach((m, i) => { if (m.mark === "??" || m.mark === "?") dots += `<circle cx="${((i + 1) / Math.max(1, n - 1) * W).toFixed(1)}" cy="${y(ana.evals[i + 1].cp).toFixed(1)}" r="3" fill="${m.mark === "??" ? "#e05a4f" : "#e6a23c"}"/>`; });
  graph.innerHTML = `<rect x="0" y="0" width="${W}" height="${Hh}" fill="#3c3a37"/><polygon points="${area}" fill="#f0f0f0"/>` +
    `<line x1="0" y1="${Hh / 2}" x2="${W}" y2="${Hh / 2}" stroke="#888" stroke-width="0.5"/>` +
    `<line x1="${cx}" y1="0" x2="${cx}" y2="${Hh}" stroke="#81b64c" stroke-width="2"/>` + dots;
  // best move text
  const mv = ply > 0 ? ana.moves[ply - 1] : null;
  let txt = `Evaluation ${evalText(e)}.`;
  if (mv && mv.mark) txt += ` ${game.plies[ply].san}${mv.mark} lost ${(mv.loss / 100).toFixed(1)} pawns; best was ${mv.best_san}.`;
  if (e.best_san) txt += ` Best now: ${e.best_san}` + (e.pv ? ` (${e.pv})` : "");
  $("bestLine").textContent = txt;
}
$("evalGraph").onclick = (ev) => {
  if (!ana || !game) return;
  const r = ev.currentTarget.getBoundingClientRect();
  go(Math.round((ev.clientX - r.left) / r.width * (game.plies.length - 1)));
};
// your own moves while replaying: vari = { base: ply where you left the game, plies: [...] }, vply = position in it
let vari = null, vply = 0, replayFrom = null;
function curPly() { return vari ? (vply === 0 ? game.plies[vari.base] : vari.plies[vply - 1]) : game.plies[ply]; }
function renderReplay() {
  if (!game) return;
  const p = curPly();
  const q = new URLSearchParams({ fen: p.fen, theme: S.settings.theme, flipped: S.settings.flipped });
  if (p.uci) q.set("lastmove", p.uci);
  if (vari) q.set("explore", "1");
  else if (ana && ana.evals[ply] && ana.evals[ply].best) q.set("arrow", ana.evals[ply].best);
  $("replayImg").src = "/api/board.svg?" + q;
  $("rPos").textContent = vari ? `Your line ${vply} / ${vari.plies.length}` : `${ply} / ${game.plies.length - 1}`;
  const el = $("replayMoves"); el.classList.add("replay");
  renderMoves(el, game.plies.slice(1).map(x => x.san), (vari ? vari.base : ply) - 1, (n) => { vari = null; ply = n; renderReplay(); }, ana && ana.moves);
  $("variation").classList.toggle("hidden", !vari);
  $("replayHint").classList.toggle("hidden", !!vari);
  if (vari) {
    const box = $("varMoves"); box.innerHTML = "";
    vari.plies.forEach((m, i) => {
      const n = vari.base + i;              // plies played before this move
      const s = document.createElement("span");
      s.textContent = (n % 2 === 0 ? `${n / 2 + 1}. ` : (i === 0 ? `${(n + 1) / 2}... ` : "")) + m.san;
      s.className = i === vply - 1 ? "cur" : ""; s.onclick = () => { vply = i + 1; renderReplay(); };
      box.appendChild(s);
    });
    $("bestLine").textContent = "You're exploring your own moves. Reset goes back to the game.";
    $("evalBar").classList.add("hidden"); $("evalGraph").classList.add("hidden");
  } else renderAnalysis();
}
const go = (n) => {
  if (!game) return;
  if (vari) { vply = Math.max(0, Math.min(vari.plies.length, n - vari.base)); return renderReplay(); }
  ply = Math.max(0, Math.min(game.plies.length - 1, n)); renderReplay();
};
function resetVariation() { if (vari) { ply = vari.base; vari = null; replayFrom = null; markReplay(); renderReplay(); } }
$("varReset").onclick = resetVariation;
(function buildReplayGrid() {
  const g = $("replayGrid");
  for (let i = 0; i < 64; i++) { const d = document.createElement("div"); d.onclick = () => replayClick(i); g.appendChild(d); }
})();
function markReplay() { [...$("replayGrid").children].forEach((d, j) => d.classList.toggle("sel", j === replayFrom)); }
async function replayClick(i) {
  if (!game) return;
  if (autoTimer) $("rPlay").click();
  if (replayFrom === null || replayFrom === i) { replayFrom = replayFrom === i ? null : i; return markReplay(); }
  const uci = squareName(replayFrom) + squareName(i);
  replayFrom = null; markReplay();
  let r;
  try { r = await api("/api/explore", { fen: curPly().fen, move: uci }); }
  catch (e) { replayFrom = i; return markReplay(); }   // not a legal move: treat the click as picking a new piece
  if (!vari && ply < game.plies.length - 1 && game.plies[ply + 1].uci === r.uci) return go(ply + 1);   // same as the game
  if (vari && vply < vari.plies.length && vari.plies[vply].uci === r.uci) { vply++; return renderReplay(); }
  if (!vari) { vari = { base: ply, plies: [] }; vply = 0; }
  vari.plies = vari.plies.slice(0, vply); vari.plies.push(r); vply++;
  renderReplay();
}
$("rFirst").onclick = () => go(vari ? vari.base : 0); $("rLast").onclick = () => go(1e9);
$("rPrev").onclick = () => go(ply - 1); $("rNext").onclick = () => go(ply + 1);
$("rPlay").onclick = () => {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null; $("rPlay").textContent = "▷ Auto"; return; }
  if (vari) resetVariation();
  if (game && ply >= game.plies.length - 1) go(0);
  $("rPlay").textContent = "❚❚ Stop";
  autoTimer = setInterval(() => { if (!game || ply >= game.plies.length - 1) { $("rPlay").click(); } else go(ply + 1); }, 1200);
};
window.addEventListener("keydown", (e) => {
  if (!$("library").classList.contains("active")) return;
  if (e.key === "ArrowLeft") go(ply - 1); if (e.key === "ArrowRight") go(ply + 1);
});
$("renameGame").onclick = async () => {
  if (!game) return alert("Open a saved game first.");
  const name = prompt("New name for this game:", game.name);
  if (name === null || !name.trim()) return;
  await post("/api/library/rename", { id: game.id, name: name.trim() });
  game.name = name.trim(); loadLibrary();
};
$("copyPgn").onclick = () => { if (game) navigator.clipboard.writeText(game.pgn); };
$("deleteGame").onclick = async () => {
  if (game && confirm(`Delete "${game.name}"?`)) { await post("/api/library/delete", { id: game.id }); game = null; ana = null; renderAnalysis(); $("replayImg").removeAttribute("src"); $("replayMoves").innerHTML = ""; loadLibrary(); }
};

// ---------------- polling ----------------
let warpOn = false;
// ---------------- updates ----------------
let started = null, updating = false;
function showUpdate(u) {
  const avail = !!(u && u.available);
  $("updateBar").classList.toggle("hidden", !avail || updating);
  $("updateNow2").classList.toggle("hidden", !avail);
  $("updateInfo").textContent = !u ? "Checking..." : u.error ? u.error :
    avail ? `New version: ${u.message} (${(u.date || "").slice(0, 10)})` : "You have the latest version.";
}
async function checkUpdate(force) {
  try { showUpdate(await api("/api/update/check" + (force ? "?force=1" : ""))); } catch (e) {}
}
function doUpdate() {
  guardUnsaved("Updating restarts the app. Save this game first?", async () => {
    updating = true; $("updateBar").classList.add("hidden"); $("settingsDlg").close();
    $("status").textContent = "Updating... the page reloads by itself in a few seconds.";
    try {
      const r = await post("/api/update/apply");
      if (!r.updated) { updating = false; checkUpdate(true); }
    } catch (e) { updating = false; }
  });
}
$("updateNow").onclick = doUpdate;
$("updateNow2").onclick = doUpdate;
$("checkUpdate").onclick = () => { showUpdate(null); checkUpdate(true); };
checkUpdate(false);

async function poll() {
  try {
    S = await api("/api/state");
    if (started === null) started = S.started;
    else if (S.started !== started) { S.unsaved = false; location.reload(); return; }
    renderPlay();
    const hasCal = S.calibration.corners.length === 4;
    if (hasCal && !warpOn) { $("warpImg").src = "/stream.mjpg?view=board"; warpOn = true; }
    if (!hasCal && warpOn) { $("warpImg").removeAttribute("src"); warpOn = false; }
    const oh = $("orientHint");
    oh.textContent = S.calibration.orientation_ok === false ? "a1 looks like a light square: press Rotate." : "";
    const px = S.calibration.square_px, fs = S.camera.frame_size;
    $("detailHint").textContent = px ? `Board detail: ${px} pixels per square` + (fs ? ` (camera ${fs[0]}×${fs[1]})` : "") +
      (px >= 50 ? ". Good." : px >= 30 ? ". OK." : ". Low: moves may be missed. Mark the corners tightly, or bring the camera closer if you can.") : "";
    if (game) renderReplay.lastTheme !== S.settings.theme + S.settings.flipped && (renderReplay.lastTheme = S.settings.theme + S.settings.flipped, renderReplay());
  } catch (e) { $("status").textContent = updating ? "Updating... the page reloads by itself in a few seconds." : "Lost connection to the app. Is its window still open?"; }
  setTimeout(poll, 400);
}

(async function init() {
  buildGrid();
  S = await api("/api/state");
  if (S.mode === "tracking") showTab("play");
  scanCameras();
  poll();
})();
