# Iteration 04 — Build report

Model/effort: Sonnet 5.5 (effort not shown to me; NEXT asked for high) · Branch: iter/04 · Commit: 74f2988 (tested commit; this report and the logs are committed after it)

## Summary
Added I2C_DIRECT to `iss.py`: constants, `direct_read`/`direct_write`, `build_i2c_direct`, `i2c_direct_read_count`, `parse_i2c_direct_status` and the `i2c_direct` helper (one `write()` per frame). `IssNack` takes the reason name from `I2C_DIRECT_NACK_REASONS` for `I2C_DIRECT`. The mock gained `MockI2cDevice.addr_bytes` and an I2C_DIRECT sub-command interpreter. The three carry-overs are done: I2C_TEST in IO_MODE (req 6), page citations (req 7), and the IO_TYPE bytes in `test_hw_mode_sequence` (req 8).

## Files changed
- `src/usb_iss_app/iss.py`: I2C_DIRECT code, `IssNack`, page citations.
- `src/usb_iss_app/mock.py`: `addr_bytes`, `_direct_command`, `_is_i2c_mode`, IO_MODE I2C_TEST reply, page citations.
- `tests/test_i2c_direct.py` (new): requirements 4 and 5.
- `tests/test_i2c.py`: `test_mock_io_mode_consumes_frame` changed as req 6 says; one added test (IO_MODE+SERIAL); comment-only page edits.
- `tests/test_hw.py`: `test_hw_mode_sequence` IO_TYPE bytes (req 8); new `test_hw_i2c_direct_empty_bus`.

## Acceptance criteria
- Mock run exits 0, 240 passed + 8 skipped (hw): `docs/iterations/04/logs/build-mock-20261018-021231.txt`. Tests cover the four datasheet example frames, every limit at the boundary and one past, the refused frames, the parser cases and every mock case listed in req 5. Met.
- Hardware run exits 0, 248 passed: `docs/iterations/04/logs/build-hw-20261018-021231.txt`. It shows the raw responses of steps 2–5, the device left in mode 0x40 (`HW after restore 5A 02 40 AA`), and `test_hw_mode_sequence` labels `5A 02 40 AA` and `5A 02 10 AF`. Met.
- Both final log headers show `74f2988… (clean)`. Met.
- Iteration 00–03 tests pass and are unchanged, apart from the permitted exceptions (`test_mock_io_mode_consumes_frame`, `test_hw_mode_sequence`, comment edits). Met.

## Test results
Final runs: mock 240 passed / 8 skipped; hardware 248 passed. Logs: the two paths above.

Superseded runs, kept: `build-mock-20261018-021123` and `build-hw-20261018-021131` (commit 8c37d41). They were taken before the mock followed the device on steps 3–5 (see below) and both passed.

## Hardware results (raw responses in the final hw log)
| Step | Frame | Device | Mock before | Action |
|---|---|---|---|---|
| 2 | `57 01 30 A0 03` | `00 01` | `00 01` | none |
| 3 | `57 05` | `FF 00` | `00 04` | mock changed |
| 4 | `57` + 58×`03` (59 B) | `FF 00` | `FF 00` | none |
| 4 | `57` + 59×`03` (60 B) | `FF 00` | `00 02` | mock changed |
| 5 | `57 01 30 A0 03` in IO_MODE | `00` (one byte) | no reply | mock changed |

ISS_VERSION after each step: mode 0x40 (0x00 after step 5).

Mock changes (cited in comments to the first hw log):
- Step 3: unknown sub-command bytes are ignored. ASSUMPTION: the same for every unknown byte; only `05` was tried.
- Step 4: the mock's overflow threshold is `MOCK_DIRECT_OVERFLOW = 60`, so a 61-byte frame gives `00 02`. 61 bytes was not tried. Builder limit stays 59 (D-007).
- Step 5: in IO_MODE the mock answers `00` with no `unhandled` entry. IO_MODE+SERIAL and SPI still consume and record.

**Step 4 does not support D-007's reading of "< 60 bytes".** The device answered `FF 00` to a 60-byte frame, so either the `0x57` byte does not count, or the limit is higher. D-007's 59 is still the safe builder limit.

## Deviations from NEXT.md
- Req 5 "split frame": NEXT says the bytes of a following raw `40 55 03` are all in `unhandled`. Only `40` is. `55` is I2C_AD1, so the mock holds `55 03` as an incomplete I2C_AD1 frame, as it does for any I2C command. The test asserts no reply and `unhandled == [40]`. If NEXT meant different bytes, a one-line change.
- Req 5 "raw `57` + 59×`03` (60 bytes) → `00 02`" is superseded by hardware step 4 (NEXT told me to follow the device). The test now sends 60 STOPs after `57` (61 bytes) for `00 02`, and asserts `FF 00` for 59 and 58.
- Req 5 "raw `57 05` → `00 04`" is superseded by hardware step 3 (now `FF 00`). Consequence: `00 04` is no longer reachable in the mock.
- Req 5 "In IO_MODE, `i2c_direct` raises `IssTimeout`, the frame is in `unhandled`" is superseded by hardware step 5. In IO_MODE the mock now answers `00`, which `i2c_direct` reads as a single status byte and raises `IssTimeout`; `unhandled` stays empty. The "frame in unhandled" check moved to a new IO_MODE+SERIAL test.
- Hardware steps are one test, `test_hw_i2c_direct_empty_bus`.
- NEXT says D-007 is "pending claude1"; DECISIONS.md already marks it adopted. No effect.

## Questions and proposed spec/process changes
- SPEC §8 candidates from this hardware (firmware 0x09, 3.3 V, unit 00069221):
  - `57 05` → `FF 00` (an unknown sub-command is ignored, not NACKed `04`);
  - a 60-byte I2C_DIRECT frame is accepted;
  - I2C_DIRECT in IO_MODE → `00`.
- D-007's frame limit could be revisited: the true limit is at least 60 and unknown. A probe of 61+ bytes (STOPs only) would settle whether the `0x57` byte counts.
- Ambiguities on pp.15–16, not tested on hardware:
  - what the device does after a NACK partway through a frame (e.g. whether remaining sub-commands run, and whether a STOP is sent);
  - whether a frame must end with STOP (the bus may stay held);
  - what the NACK sub-command does when no READ follows;
  - the mock treats `57` alone as `FF 00`; the device is untested;
  - whether the `00 01` for an absent address comes after the device has sent STOP.
