# Iteration 02 — Review (fix cycle 0)

Model/effort: Sonnet 5.5 (revclaude this session), as run by Chris · Reviewed commit: `2875071` on `iter/02` (clean tree).

## Verdict
**Fix**

## Independent test run
Run with `.venv/bin/python scripts/run_tests.py` (the system Python lacks the package; my first attempts failed on import and I deleted those empty logs).
- Mock: `logs/review-mock-20261017-014136.txt` / `.xml`: 159 passed, 6 skipped (hw), exit 0. Matches the builder's counts.
- Hardware: `logs/review-hw-20261017-014137.txt` / `.xml`: 164 passed, 1 failed. Same failure as the builder's: `test_hw_io_getad_on_digital_pin`, GETAD on I/O1 as digital input returned `02 E1` (737), not `00 00`.
- Other hardware lines agree with the builder: SETPINS `63 0F` → `00`; analogue GETAD ch1–4 = 733, 743, 765, 692 (builder: 740, 743, 781, 709; floating pins, expected to vary); `65 00` and `65 05` → `00 00`; the device ends in 0x40. GETPINS read `0E` twice (builder `0F`); I/O1 is driven by the module's TX, so this is expected variation. Bits 7:4 were 0 in both runs.

## Acceptance criteria check
- [x] Mock run exits 0, and the tests cover reqs 1–6. Read `tests/test_io.py`: frame bytes, 30/31-byte boundary, header errors, ACK with 0 and 62 rx bytes, NACK with rx, short rx body, p.20 GETAD examples, GETPINS mask, mock buffers, `5A 01` as data. The code matches the datasheet pp.19–20.
- [ ] Hardware run passes: **not met**. One failure, caused by a real hardware finding (issue 1) and by NEXT 02 asserting the datasheet's `00 00` as fact.
- [x] Headers show `(clean)`: builder `f8b71d6`, mine `2875071`.
- [x] Iteration 00 and 01 tests unchanged apart from req 6 issue 2. Req 6 issue 1 (IO_CHANGE comment) is done too.

## Issues
1. **major — hardware.** GETAD on a digital-input pin returns the converted value (`02 E1`), not `00 00` as p.20 says. The builder did not weaken the assertion and reported it openly, which was correct. The fault is in NEXT 02 step 3, which turned an untested datasheet claim into a pass/fail assertion. The mock answers `00 00` and so disagrees with the device.
2. **minor — hardware / mock.** SETPINS `63 0F` with no output pins answers `00`. The mock answers `FF` here, as NEXT 02 req 4 told it to. One data point from the real device: the mock should follow it.
3. **minor — reading.** Builder's report: "GETAD analogue values near 0.7 of full scale… likely pulled up". My own run gave 692–765. That fits floating or weakly pulled pins, not distinct signals. This isn't a code issue.
4. **info — reading.** The mock's `_serial_command` flushes pending bytes before checking room, when `hold_serial_tx` is false. Harmless, and the tests cover the held case.

## Scope drift
None. Splitting the hardware sequence into three tests with a restoring fixture is allowed by NEXT ("one ordered test or several").

## Builder report accuracy
Every checkable claim holds: counts, log names, clean headers, the SETPINS and GETAD responses, and the device ending in 0x40. The numbers that vary (GETPINS, analogue values) differ in my run, as expected. Zero inaccuracies.

## Notes for claude1
- **Datasheet vs device (firmware 0x09):** GETAD on a digital-input pin returns the ADC value, not `00 00` (p.20). SPEC §8 could record this as an erratum. The mock still follows the datasheet, because my Fix NEXT asks only for a recording test, not a mock change. Please decide which the mock should follow.
- **SETPINS with no output pins answers `00` (NACK).** The datasheet is silent. The Fix NEXT makes the mock match.
- Ambiguities still open (not tested on hardware): the meaning of TxCount; receive overflow; SERIAL_IO framing without a length byte.
- No checkpoint due: 2 accepted, this is the first Fix on NN 02.

---

# Iteration 02 — Review (fix cycle 1)

Model/effort: Opus 5.5 / high · Reviewed commit: `5154232` on `iter/02` (clean tree).

## Verdict
**Accept**

## Independent test run
All runs used `.venv/bin/python scripts/run_tests.py --iter 02 [--hw] --tag review`. Every header shows `5154232 (clean)` and every exit code was 0.
- Mock: `logs/review-mock-20261017-225647.txt` / `.xml`: 160 passed, 6 skipped (hw). Matches the builder's `build-mock-20261017-225037`.
- Hardware, unit 00069221 (port from `.env`), after reading `docs/HARDWARE.md` and checking that no process held the port:
  - `logs/review-hw-20261017-225705.txt`: 166 passed. GETAD digital `65 01` → **`00 00`**. SETPINS `63 0F` → `00`. GETPINS `0e`, then `0f`. Analogue ch1–4: 739, 635, 717, 708. `65 00` and `65 05` → `00 00`.
  - `logs/review-hw-20261017-225845.txt`: 166 passed. GETAD digital → `02 e3`. SETPINS → `00`. Analogue: 738, 764, 828, 737.
  - `logs/review-hw-20261017-225849.txt`: 166 passed. GETAD digital → `02 e3`. SETPINS → `00`. Analogue: 740, 763, 820, 728.
  - I ran the second and third runs only to see whether `00 00` repeats (issue 1). Every run ends with `restore 5A 02 40 AA` → 0x40.
- These agree with the builder's final hardware log (`build-hw-20261017-225037`: 166 passed, `02 e4`). The only exception is the single `00 00`.

## Acceptance criteria check
- [x] Mock run exits 0: builder `225037`, mine `225647`.
- [x] Hardware run exits 0, the raw GETAD-on-digital response is logged, and the device is left in 0x40: builder `225037`, plus my three runs.
- [x] Final logged runs show `(clean)`. The builder's finals are at `50e699e`; the two `225029` runs are marked `(dirty)` and are disclosed as such in build.md. Mine are at `5154232`.
- [x] Earlier tests are unchanged apart from the named ones. In `git show 50e699e`, test changes are limited to `test_mock_setpins_nack_hook`, `test_mock_setpins_no_outputs_acks` → `_nacks`, `test_mock_getad_digital_pin_is_zero` → `_returns_adc`, the new `test_mock_getad_output_pin_is_zero`, and `test_hw_io_getad_on_digital_pin` (req 1).

Requirements against the datasheet: SETPINS answers `FF`/`00` (p.20) and now NACKs when no general-I/O pin is an output. The forced-NACK hook runs first and stays one-shot. GETAD returns `adc[ch]` for digital-input and analogue-input general-I/O pins, and `00 00` for output pins, non-general pins and channels outside 1–4. The comments are worded as NEXT asked.

## Issues
1. **minor — hardware.** GETAD on I/O1 as a digital input returned `00 00` in 1 of my 3 runs (`02 e3` in the other two). Across every runner log on unit 00069221 the results are `02 e1`, `02 e1`, `02 eb`, `02 e4`, `02 e4`, `00 00`, `02 e3`, `02 e3`. With the GY module attached, I/O1 carries its continuous 115200-baud UART output (HARDWARE.md). A conversion during a low bit would read near 0, so this is the likely cause; it is not verified. The test asserts only the shape, so it passes either way, as HARDWARE.md intends ("log them, don't assert them"). The erratum still holds: 7 of 8 runs are non-zero. No code change.
2. **minor — test (reading; my NEXT's gap).** No test covers GETAD on a pin used for I2C or serial. In I2C mode with IO_TYPE 0xAA, I/O3 and I/O4 carry digital-input type bits. If the `ch - 1 in self._general_pins()` check in `MockTransport._getad` were removed, those channels would return `adc[ch]` and every test would still pass. Before this cycle the digital-input path also returned 0, which hid the gap. NEXT fix 1 required the behaviour but asked only for an output-pin test. Carried into NEXT 03.
3. **minor — records (claude1's commit `4737a35`, not the builder's work).** SPEC §8 cites `03 D4` from `claude1-discriminator-hw.txt`, but that file does not contain `03 D4`. Commit `4737a35` replaced its content. The version committed at `a181b31` recorded `02 e6` (unit 1, failing on the old `00 00` assertion). The current version is a different run that errored at setup with "No such file or directory" for the 00069221 port, presumably while unit 1 was unplugged. Neither discriminator log has the runner header (commit, clean flag, port, start time). As a result, the serial number 00069220, "power-cycled" and "nothing attached" are not shown in the logs; `claude1-discriminator-hw-unit2.txt` shows only module 7, firmware 0x09 and `03 ff`. CLAUDE.md requires raw logs written by the test runner and never edited. Overwriting a committed log goes against that rule, even though the content came from a real run. The `02 e6` record survives only in git history.
4. **info — reading.** NEXT req 2 asked to "add a test for the NACK case through `set_pins`". The builder repurposed the existing test that the change broke (`_no_outputs_acks` → `_no_outputs_nacks`) instead of adding a separate test. The coverage is the same, the old expectation was wrong anyway, and build.md says so openly.
5. **info — reading.** The header line of build.md still names `f8b71d6` as the commit; the fix-cycle section correctly names `50e699e`.

Test quality: these tests would fail if the code were wrong. `test_mock_setpins_nack_hook` now also checks that the pin was set, which catches a mock that NACKs everything. `_no_outputs_nacks` catches an ACK. The per-channel values 500–503 catch channel mix-ups. `_output_pin_is_zero` catches output pins returning the ADC value. The hardware assertion's 0–1023 bound catches any reply larger than 10 bits. The exception is issue 2.

## Scope drift
None. The diff touches `mock.py`, `test_hw.py` and `test_io.py` only, as NEXT allowed.

## Builder report accuracy
Every checkable claim holds: counts, log names, the dirty and failing intermediate runs and why they exist, the `02 e4` response, the device left in 0x40, and the list of changed tests. One stale header line (issue 5). Zero inaccuracies of substance.

## Notes for claude1
- **SPEC §8 GETAD erratum evidence (issue 3).** Please correct the `03 D4` citation. Either restore the `a181b31` content of `claude1-discriminator-hw.txt` as its own file, or cite the runner logs. In future, discriminator runs should go through `scripts/run_tests.py` so the header records the commit, the port and the clean flag. A second unit should be run with `USB_ISS_PORT=...` so the port, and so the serial number, appears in the log.
- **`00 00` once in 3 runs (issue 1).** This probably comes from the GY's UART traffic on I/O1. It does not contradict the erratum. A clean discriminator would use GETAD on I/O3 or I/O4 as digital inputs in IO_MODE, because those pins are unconnected and nothing drives them. I have not added it, because it is outside NEXT 02.
- **D-006 (pending claude1)** is proposed in `DECISIONS.md`. It sets the I2C byte limits where the datasheet is silent or inconsistent, and how to treat two datasheet examples whose count byte disagrees with their own text (p.11 I2C_AD0 write: count `0x02` with 4 data bytes; p.13 I2C_AD2 write: count `0x34` with 32 data bytes). These two may deserve SPEC §8 entries.
- **Roadmap split.** I split roadmap item 03 into iteration 03 (I2C_SGL, I2C_AD0/1/2, I2C_TEST, and a mock I2C bus) and iteration 04 (I2C_DIRECT and SPI), because the whole item is well over 45 minutes. From here on, roadmap items 04–09 run one iteration number later than their labels.
- No checkpoint due: 3 accepted (00, 01, 02). The next one is due at the 4th accept.
