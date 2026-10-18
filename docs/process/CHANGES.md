# Process changes

Each entry: version, date, what changed, why, and the expected effect (which LOG metric should move).

## v1 — 2026-10-11
- Initial process. Builder (vsclaude), reviewer (revclaude), claude1 auditing at checkpoints.
- Why: independent review backed by evidence, and less manual relaying by Chris.
- Expected: few builder-report inaccuracies; most defects caught by revclaude rather than by Chris.
- Updted initial version of `CLAUDE.md` with corrected stack info on D-001 and D-003

## v2 — 2026-10-17 (claude1)
- Added `docs/HARDWARE.md`, the bench wiring inventory, and a pointer to it in `CLAUDE.md` under Hardware.
- Why: no file recorded what was attached to the USB-ISS. Iterations 00 and 01 ran hardware tests assuming nothing was connected, while two GY-MCU90640 modules were attached (over the power budget, I2C lines shared). Hardware safety rested on guesswork.
- Expected: NEXT hardware sections cite the wiring. No hardware-safety defects caught after NEXT is written, which is where the IO_TYPE problem in NEXT 01 was found. LOG metric: "found later by Chris" or by claude1 for hardware issues should stay at 0.

## v3 — 2026-10-18 (claude1, CP-01)
- **Experiment: headless loop.** Added `scripts/loop.sh` and `.claude/loop-settings.json`, plus REVIEWER.md "Loop status" and the stop rules. Between checkpoints, builds and reviews run as `claude -p` with no prompts and a minimal allow list. The loop stops and notifies Chris on any gate.
  - Why: Chris's time per iteration (10/15/45 min recorded) is mostly relaying and pushing.
  - Expected: Chris minutes per accepted iteration fall below 10 for iterations 04–07.
  - Confirm at CP-02 if both hold: Chris's minutes are below 10 on average, and no hardware-safety or log-integrity defect is found later by claude1 or Chris.
  - Refute if either fails: the minutes don't fall (loop stops or debugging cost more), or CP-02 finds a defect that a between-steps read by Chris would have caught.
- **Hygiene** (not experiments):
  - BUILDER.md: no out-of-repo installs; `.venv/bin/python` only; never delete logs; blocked status.
  - CLAUDE.md: log integrity, measurements only from runner logs, printed page numbers.
  - REVIEWER.md: Fix and Rethink are committed on `iter/NN`, which codifies what has been done since iteration 02; no pushing.
  - Expected: log deletions 0, citation errors 0, unlogged measurements 0.
