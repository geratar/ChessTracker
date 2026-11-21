# Progress

## Done
- Phase 1 code: camera list/preview, reconnect, 4-corner calibration with drag, rotation,
  top-down warp, 64-square overlay, a1 colour check, save/load, snapshots, recording. 14 tests pass.

- Phase 1 validated on the real board (Windows PC, EMEET C960, camera 0, MSMF backend, 1280x720).

## Findings from first recording (rec_20261121_102752, 1376 frames)
- Camera is low (~25 deg) and to White's left: in the top-down view each piece smears over 2-3 squares
  toward the far corner. Raising the camera is the cheapest reliability win.
- Board/camera shifts ~3.5 px when the board is touched, and stays shifted for a while.
  Phase 2 must re-align each frame (phase correlation on the board frame) before comparing squares.
- Global brightness drifts ~5% (auto exposure): normalise before per-square comparison.
- Hands show up as big frame-to-frame motion (>10 mean abs diff vs ~3 when still): usable as a stability gate.

## Open issues
- Tall pieces lean toward the camera's far side in the top-down view; Phase 2 must sample
  the lower part of each square (or a configurable offset).

## Phase 2 (first version, done)
- moves.py matching (occlusion-tolerant), detector.py, tracker.py, track.py UI, replay.py.
- On the first recording it detects e4 d5 exd5 c6 with no false moves; ~1 s after the hand leaves.
- 35 tests pass (incl. real-frame regression, hands, lighting, board shift, undo, duplicates).

## Mac live test 1 (10:18)
- Camera now higher, board far away, strong sunlight patches. First move (c4) was not registered;
  after black's d5 it reported "no legal move matches: c4 c5 d5 c6 d7" and got stuck.
- Fixes: missed-move recovery (offers two-move sequences to confirm), a single strongly changed square
  asks instead of being silently absorbed, motion threshold adapts to camera noise. 41 tests pass.

## Phase 3 (first version, done 2026-11-21)
- Browser app with setup wizard, live board with real pieces, themes, flip, fix-last-move and
  enter-move by clicking squares, confirmation buttons, save to library, replay. 46 tests pass;
  UI exercised end to end in headless Chrome on the recording.

## Mac live test 2 (10:46): moves often missed
- Likely cause: stillness was measured on the whole picture, and the player's body is in frame,
  so the board rarely counted as still. Now only the board area (+margin) is watched.
- Change threshold lowered 25 -> 18 for smaller/farther boards (first clip still exact).
- Added Record video button and data/debug.log (every decision with top square scores).

## Occlusion handling (10:55)
- Calibration.shadow_map(): for each square, which squares a standing piece hides (walk up in the
  camera image from the square centre, map back to the board). Matching uses it: changes in the
  hidden zone of moved pieces cost ~nothing; expected squares hidden behind other pieces cost less
  when unchanged. `piece_height` setting (square widths, default 1.6). 51 tests pass.

## Phase 5-ish + library polish (11:00)
- Save with result (1-0 / 0-1 / draw / unfinished), unsaved-game guard (tab change, new game,
  start tracking, closing the browser tab).
- Stockfish analysis in the Library: auto-download, eval bar, graph, ?!/?/?? marks, best-move arrow.
  Download path untested from a Mac (sandbox blocks GitHub downloads); asset selection unit-tested.
- 57 tests pass.

## Mac recording 2 (11:09): side camera, pieces lean onto the next file
- e2-e4 lit up d2/d4 as much as e2/e4 -> "Please confirm e4, d4, e3". Root cause: the matcher counted
  changed squares but ignored how strongly each changed.
- Now candidates are ranked by how much of the measured change they explain (strength-weighted,
  shadow-zone aware; changes outside a move's hidden zone cost almost full price). Accept when the
  best explains >= 20% more than the runner-up (`rel_margin`).
- Recording 2: all 8 moves (e4 e5 Nf3 d5 exd5 Qxd5 d4 exd4) found with zero questions; recording 1
  unchanged. Added as fixtures/game2 regression test. 62 tests pass.

## Camera can't move closer (11:30): more detail in software
- Camera now asks for 1080p (MJPG on Windows/Linux), was 720p: ~2.25x pixels per square if the
  camera supports it. Old 720p calibrations are rescaled automatically (same aspect ratio).
- Decisions use the mean of the last 5 agreeing still frames (less sensor noise). The window
  resets whenever the changed-square set changes, so a flickering hand is never averaged in.
- Aligner max shift capped at 0.35 square (a chessboard repeats every square: false locks).
- Setup shows "Board detail: N pixels per square" (good >= 50, low < 30).
- Replaying both clips at 0.67x / 0.5x / 0.4x resolution: lower resolution gave extra questions,
  so more pixels does help. 63 tests pass.

## In-app update (11:50)
- macOS asked "Open Anyway" for every downloaded ZIP. Now: banner + Settings > Updates fetch the latest
  code from GitHub with Python (no git/token), write only changed files (git blob hashes), keep
  data/, .venv/, config.json, reinstall requirements if they changed, restart in place, page reloads.
  Python-written files aren't quarantined, so the approval is needed once more, never again.
- Needs the repo to be public. Restart tested live (Linux); 66 tests pass.

## Fast play, hands near the board (12:10)
- Stillness is now per square on the top-down board (SquareMotion, 3x3-dilated). Hands beside the
  board are ignored; a hand over part of the board doesn't block a move elsewhere. With a hand on the
  board a move is accepted only if it avoids the hand's squares, explains every visible change, and no
  other legal move could use the hidden squares; else wait (no questions). Under the hand the old
  reference is kept. Brightness offset now uses the median square (hands don't skew it).
- Default wait 0.6+0.5 s -> 0.4+0.3 s; Settings: Fast (0.25+0.2) / Normal / Careful (0.7+0.5).
- Both recordings correct at all three speeds, ~0.7 s quicker. 70 tests pass.

## Fast-game recording 3 (12:40)
- 6 moves in ~8 s; an arm was over most of the board (side camera) the whole time: between e4 and Qa5
  the board was fully clear for one frame. Not recoverable from images.
- Added: catch-up of 2-3 missed moves when exactly one legal sequence explains the strong changes;
  partial-view decisions without the extra confirm wait; rel_to_max 0.4 -> 0.3 (origin square of a
  capture was hidden under the bar); "Lost track ... use Enter a move" instead of a silent wait.
- UI: Finish game with no moves; "Finish without saving"; app renamed ChessEmeg (display name only;
  repo, folder and launcher file names unchanged so the updater keeps working). 72 tests pass.

## Recording 4 (12:45): camera higher, solo fast play, "tracked nothing"
- Not a regression: the previous version also read nothing on this clip. Moves were played every
  1-2 s by one person; the first clear view came after 4 moves (e4 d5 exd5 Qxd5).
- Found and fixed a real risk: catch-up could accept e4 d5 exd5 while Qxd5 had also been played
  (the queen's departure showed on c8 because pieces lean in the camera view). Catch-up now needs a
  complete explanation (every expected square changed, no strong unexplained change), the fewest
  moves that fit, and at most 2 moves while a hand is on the board.
- Clip added (cropped, 2 MB) as fixtures/fast_play: test asserts nothing wrong is ever applied. 73 tests.

## Tap mode + clock (13:10)
- User chose "both": Settings > Move detection: Automatic / Only when I tap. Space or the big
  "Move done" button (any mode) reads the board as soon as nothing moves on it for 2 frames
  (max 1.5 s; moving squares left out). A tap means a move happened, so if nothing fits clearly
  the best candidates are offered. Clock under the board shows each side's thinking time.
- 77 tests pass.

## Blitz recording 5 (13:25)
- Board clear for only ~0.3 s between moves; we needed 0.4 s still + 0.3 s confirm, so nothing was read.
- Now a square counts as still after 2 frames (0.13 s), no extra confirm (Fast = default).
  Guards: a read whose squares look like before within 1 s is taken back ("was a hand");
  squares whose reference predates a hand only produce a move on clear evidence, else refresh;
  faint unexplained changes are absorbed instead of warned about.
- Blitz clip: 1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. d4 c6 5. Bd2, all read, no questions (fixtures/blitz).
  Older clips unchanged; no wrong moves on any clip. 78 tests.

## Normal-pace recording 6 (14:10)
- Broke on: (1) the frame average included frames from the moment a hand left (now only frames with
  nothing moving); (2) a piece leaning onto the next square / captured pieces set beside the board
  pushed real moves under the count-based bar (Qc7) - a single move that fully explains the change
  (lean zones from the shadow map) is now accepted; (3) Qa5 vs Qc5 looked alike - a piece landing on
  an empty square must also change the empty square right behind it in the camera's view.
- Clip: 1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. d4 c6 5. Bd2 Qc7, all correct, one question (right answer
  listed first). All 6 recordings: no wrong move. fixtures/normal_pace. 79 tests.

## Variations + player profiles (16:10)
- Library replay: click a piece then a square to try your own moves; off the game line the board turns
  lighter and a "Your line" bar with Reset (back to where you left the game) appears. Same move as the
  game just steps forward. Eval/arrows hidden while exploring. `/api/explore` checks legality.
- Players (data/players.json, name + one of 20 avatars drawn in `chesstracker/players.py`). "Who's
  playing?" dialog before Start tracking / New game; Anonymous allowed on either side; last pick
  remembered. Names saved as PGN White/Black (+WhiteAvatar/BlackAvatar); shown on clock and Library. 83 tests.

## Next
- Get a live recording + debug.log from the Mac to confirm.
- User raises the camera, recalibrates, records a longer clip (castling, capture, en passant if possible,
  pieces adjusted without moving). Tune thresholds on it and add it to the fixtures.
- Then Phase 3 (GUI polish, manual correction, save/load/replay games).
