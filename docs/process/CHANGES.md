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
