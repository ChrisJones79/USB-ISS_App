# NEXT — Iteration 02 (fix cycle 1)

Recommended model/effort: Sonnet 5.5, medium.
Author: revclaude. Read `docs/iterations/02/review.md` first.

## Context
Iteration 02 code and mock tests are fine. One hardware test fails because NEXT 02 step 3 asserted the datasheet's `00 00` for GETAD on a digital pin, and the device (firmware 0x09) returns the ADC value instead (`02 E1`). That error was in the NEXT, not in your code. The same hardware run showed that SETPINS with no output pins answers `00`.

## Goal
The hardware run passes with these findings recorded, and the mock matches the device for SETPINS.

## Requirements
1. `tests/test_hw.py`, `test_hw_io_getad_on_digital_pin` (datasheet p.20): send `65 01` with all pins digital input. Log the raw response. Assert only that it is exactly 2 bytes decoding to 0–1023. Rewrite the docstring: p.20 says `00 00`, and the device does not do that (iteration 02 logs). No other hardware test changes.
2. Mock SETPINS (datasheet p.20; SPEC §3):
   - answer `00` when no general-I/O pin in the current mode is OUTPUT_LOW or OUTPUT_HIGH; answer `FF` otherwise;
   - the forced-NACK hook keeps working;
   - comment: observed on hardware once (IO_MODE, all pins digital input, `63 0F` → `00`); the other cases are an assumption.
   - Update only the existing mock SETPINS tests that now fail because they set pins with no output configured, and add a test for the NACK case through `set_pins`. Say which tests you changed in build.md.
3. Mock GETAD follows the device (claude1 decision, SPEC §3 and §8 erratum):
   - For a general-I/O pin that is a **digital input or an analogue input**, return `adc[ch]`. Comment: "p.20 says 0000 for a digital input; device fw 0x09 converts anyway (SPEC §8)".
   - Output pins and pins used for I2C or serial keep `00 00`. Comment: "datasheet; untested on hardware".
   - Channels outside 1–4 keep `00 00` (confirmed on hardware).
   - Update `test_mock_getad_digital_pin_is_zero` to the new behaviour, rename it to match, and name it in build.md. Add one test that an output pin still returns 0.

## Constraints / out of scope
Nothing else. No SPEC, DECISIONS, process files, LOG or CHANGES edits. No new dependencies.

## Hardware tests
**safe-read**, same as NEXT 02: the steps in the old brief are unchanged except step 3 as above. Nothing is driven. `docs/HARDWARE.md` is unchanged.

## Acceptance criteria
- [ ] `.venv/bin/python scripts/run_tests.py --iter 02 --tag build` exits 0.
- [ ] `.venv/bin/python scripts/run_tests.py --iter 02 --hw --tag build` exits 0 with the raw GETAD-on-digital response logged, and the device left in 0x40.
- [ ] Final logged runs show `(clean)` headers.
- [ ] Earlier tests unchanged apart from the SETPINS tests and the mock GETAD-digital test named in build.md.

## Report back
Update `docs/iterations/02/build.md` for this cycle. Old logs stay (no deletions).
