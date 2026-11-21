# Progress

## Done
- Phase 1 code: camera list/preview, reconnect, 4-corner calibration with drag, rotation,
  top-down warp, 64-square overlay, a1 colour check, save/load, snapshots, recording. 14 tests pass.

## Open issues
- Not yet tested with the real camera and board.
- Tall pieces lean toward the camera's far side in the top-down view; Phase 2 must sample
  the lower part of each square (or a configurable offset).

## Next
- User runs `calibrate.py` on the Mac, calibrates, saves a few snapshots and a short recording
  (start position, a few moves, a hand over the board). Use them to design Phase 2 detection.
