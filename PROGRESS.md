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

## Next
- Get a live recording + debug.log from the Mac to confirm.
- User raises the camera, recalibrates, records a longer clip (castling, capture, en passant if possible,
  pieces adjusted without moving). Tune thresholds on it and add it to the fixtures.
- Then Phase 3 (GUI polish, manual correction, save/load/replay games).
