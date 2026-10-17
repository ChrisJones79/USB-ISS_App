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
