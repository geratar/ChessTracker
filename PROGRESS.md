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

## Next
- User raises the camera, recalibrates, records a longer clip (castling, capture, en passant if possible,
  pieces adjusted without moving). Tune thresholds on it and add it to the fixtures.
- Then Phase 3 (GUI polish, manual correction, save/load/replay games).
