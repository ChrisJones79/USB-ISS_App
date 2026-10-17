# Iteration 01 — Build report

Model/effort: Sonnet 5.5, medium · Branch: iter/01 · Commit: 27e0ac6 (tested code; this report and the logs are committed after it)

## Summary
ISS_MODE is implemented in `iss.py`: mode constants and `decode_mode`, `IoType`/`io_type`, `baud_divisor`/`spi_divisor`, all six frame builders, `parse_mode_response`, `IssNack`, `set_mode`. The mock frames `5A 02 …` by mode byte, has a one-shot NACK hook (`force_next_mode_nack`) and updates `mode`. Review 00 issues 1–4 are fixed (reqs 5–8).

## Files changed
- `src/usb_iss_app/iss.py`, `mock.py`, `transport.py`
- `scripts/run_tests.py`
- `tests/test_mode.py` (new), `tests/test_hw.py`, `tests/test_run_tests.py`, `tests/test_iss.py` (one line, see Deviations)

## Acceptance criteria
- [x] Mock run exits 0: `logs/build-mock-20261017-003245.txt` (112 passed, 3 skipped). Tests cover every datasheet frame, the p.8 baud table with 2400 = 04 E1, all three NACK reasons through `set_mode`, `FF xx`/unknown-reason/short errors, and `test_mock_io_serial_framing_ignores_payload_bytes`.
- [x] Hardware run exits 0: `logs/build-hw-20261017-003245.txt` (115 passed). Shows the raw IO_CHANGE response and the mode after each step; the device ends in 0x40.
- [x] Headers: both logs name the tested commit; see the `git commit:` line in each (code was committed before the runs; logs are excluded from the dirty flag).
- [x] Iteration 00 tests pass, with one exception: see Deviations.

## Test results
Mock: 112 passed, 3 skipped, `logs/build-mock-20261017-003245.txt`. Hardware: 115 passed, `logs/build-hw-20261017-003245.txt`.

## Hardware findings
- Raw IO_CHANGE (`5A 02 10 0F`) response: `FF 00`.
- ISS_VERSION mode byte after IO_CHANGE: 0x40, unchanged. This matches the mock's assumption, so the mock is unchanged. Its comment still marks this as an assumption in the source; the assumption is now confirmed for this one case (I2C_S_100KHZ → IO_CHANGE).
- Mode after step 3 (IO_MODE `00 AA`): 0x00. After restore: 0x40.

## Deviations from NEXT.md
1. **Edited an iteration 00 test.** `test_mock_unhandled_returns_nothing` sent `5A 02 40 00` as its "unhandled" example, with the comment "ISS_MODE not implemented". Req 5 makes that a valid frame (`FF 00`), so the test could not pass unchanged. I changed only the input to `5A 10 40 00` (still unhandled); the assertions are unchanged. This conflicts with "iteration 00 tests pass unchanged"; reviewer please confirm.
2. `SerialTransport.read` now defaults `timeout=None` (meaning "the constructor timeout"), while `Transport`/`MockTransport` keep `DEFAULT_TIMEOUT`. This is how req 7 is met; the default test accepts both.
3. `spi_divisor` refuses > 3 MHz and < 23 437.5 Hz explicitly (D-005). The formula alone would accept 4 MHz (ceil(1.5)−1 = 1).
4. `decode_mode` also names 0x10 as `IO_CHANGE` (not required).

## Questions and proposed spec/process changes
- Datasheet ambiguities (not tested on hardware): which IO_TYPE bits are honoured in I2C and IO+SERIAL modes (IO+SERIAL claims I/O1/I/O2 are Rx/Tx, and says "I/O3 and I/O" are free, an apparent typo for I/O4); the datasheet gives no NACK-framing for an unknown mode byte, so the mock's `00 05` after `5A 02 <mode>` is still an assumption; I2C+SERIAL frame has no IO_TYPE byte, so what the I/O3/I/O4 pins do is unspecified.
- Datasheet p.8 text uses `16+baud` and the 2400 row says 09 E1; handled per SPEC §8.
- SPEC §8 note 3 is superseded by hardware: IO_CHANGE returns `FF 00` (claude1 may reword).
- D-005 is still pending claude1; built to it as instructed.
