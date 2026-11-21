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

## Next
- User runs `calibrate.py` on the Mac, calibrates, saves a few snapshots and a short recording
  (start position, a few moves, a hand over the board). Use them to design Phase 2 detection.
