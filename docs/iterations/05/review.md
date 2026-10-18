# Iteration 05 — Review (fix cycle 0)

Model/effort: Opus 5.5 / high · Reviewed commit: `4d1594e` on `iter/05` (clean tree). The builder tested the code at `da2770f`. `4d1594e` adds only the build report and the build log.

## Verdict
**Accept**

## Independent test run
- Mock: `.venv/bin/python scripts/run_tests.py --iter 05 --tag review` → `logs/review-mock-20261018-081546.txt` / `.xml`. Header `4d1594e… (clean)`, 272 passed, 8 skipped (hw), exit 0.
- This matches the builder's `build-mock-20261018-081512` (header `da2770f… (clean)`, 272 passed, 8 skipped). The per-test PASSED/SKIPPED lists in the two logs are identical (I diffed them).
- There was no hardware run, as NEXT 05 says. `docs/iterations/05/logs/` holds no hardware log.

**Mutation check.** I applied 10 single-line mutants, one at a time. Each was an in-place `sed` edit, followed by `pytest tests/test_spi.py` (or `tests/test_i2c_direct.py`) and a `git checkout --` restore. No runner logs were written, and the tree was clean afterwards. **All 10 were killed:**
- Requirement 6, which repeats the builder's check:
  - `MockI2cDevice` pointer `"big"`→`"little"` → `test_mock_pointer_high_byte_first` fails (1 failed, 44 passed);
  - STOP made a no-op → `test_mock_stop_ends_transaction` fails (1 failed, 44 passed).

  Both results agree with build.md.
- SPI, in `iss.py`:
  - `spi_io` reads `len(data)` instead of `1 + len(data)` (10 failed);
  - parser short-reply check off by one (2 failed);
  - builder accepts empty data (1 failed).
- SPI, in `mock.py`:
  - SPI answered in every mode (4 failed);
  - one `transfer()` per byte instead of per frame (8 failed);
  - over-length check `>`→`>=` (1 failed);
  - phase 3 (`0x93`) excluded (1 failed);
  - received bytes returned reversed (1 failed).

## Acceptance criteria check
- [x] **The runner exits 0, and the new tests cover requirements 1–6.** I read `tests/test_spi.py` and the two additions to `tests/test_i2c_direct.py`. They cover:
  - the constants;
  - all three pp.17–18 example frames, byte for byte;
  - the builder limits: 62 accepted (a 63-byte frame); 0 and 63 refused;
  - every parser case NEXT lists, including both NACK forms with `reason is None` and the message `"SPI NACK"`;
  - the helper: one `write()` and `reads == [3]`;
  - the 23K256 sequence, one frame per `transfer()`, no device, the base device, raw frames of 63 / 64 / 1 bytes, command bytes inside data, all four phases, and four non-SPI modes (timeout, `unhandled`, mode unchanged, device not called);
  - the I2C+SERIAL `5A 02 61 …` frame. No earlier test sent it to the mock (`test_mode.py:106` checks only the built bytes), so the builder added `test_mock_i2c_serial_h100_still_settable`, as NEXT allowed.
- [x] **Final logged runs show `(clean)`:** the builder's at `da2770f`, mine at `4d1594e`.
- [x] **No hardware log** in `docs/iterations/05/logs/`.
- [x] **The iteration 00–04 tests are unchanged.** Under `tests/`, `git diff main...iter/05` shows only the new `test_spi.py` and 15 added lines in `test_i2c_direct.py`, with no removed lines.
- [x] **The report says whether each requirement 6 test failed against its mutant.** Both did, and I reproduced both.

**Datasheet check (pp.17–18, against the PDF myself).**
- `0x61` is "SPI command (0x61)". The 63-byte maximum includes the command byte. "All bytes should be sent to the USB-ISS in one sequence." The device "always returns the same number of bytes as you send". The code matches all four.
- The helper reads `len(frame)` = 1 + n bytes in one `read()`, with the transport's 500 ms default. The three example frames match p.17 (WRSR, WRITE) and p.18 (READ).
- `SPI_IO` carries the comment NEXT asked for, about the I2C_H_100KHZ+SERIAL mode byte. Each constant cites p.17.
- Every mock assumption NEXT listed is labelled `ASSUMPTION` in `_spi_command`:
  - frame = rest of the `write()` call;
  - outside SPI mode the frame is dropped with no reply;
  - over-length → `00`;
  - `61` alone → `FF`;
  - one CE-low period = one `transfer()`;
  - SDI floats to `FF`.

## Issues
1. **minor — reading (my NEXT 05 defect).** Requirement 5 said the p.18 WRITE "returns 6 bytes". The WRITE carries 7 data bytes (`02 00 00 12 34 56 78`), and p.17 says the device returns as many bytes as it is sent, so `spi_io` returns 7. The builder asserted 7, which is correct, but did not list the change as a deviation (see Builder report accuracy).
2. **info — reading.** The pp.17–18 ambiguities the builder lists are real, and the mock labels every one: how many bytes follow a NACK, whether CE stays low for the whole frame, replies to a lone `61` and to an over-long frame, and `61` outside SPI mode. None of them can be checked on this bench (HARDWARE.md: SPI mode makes I/O1, which the GY's TX drives, the CE output). They stay assumptions until Chris approves a bench change (SPEC §6 item 05).
3. **info — test.** `_Rec` in `test_spi.py` subclasses `MockTransport` and overrides `write`, so it never runs the mock's SPI path. That is the point: it isolates the helper's write and read calls, as NEXT asked. The mock path is covered separately by the `test_mock_*` tests.

No blocker or major issue.

## Scope drift
None.
- No GUI.
- No change to `build_spi_mode` or `spi_divisor`.
- No new dependency.
- No process or source-of-truth file was touched.
- No hardware run, and no `61` byte sent to the device.

## Builder report accuracy
One omission.
- The "Deviations from NEXT.md" list leaves out the WRITE reply length: NEXT said 6 bytes, and the test asserts 7 (issue 1). The builder's value is right, but the report should have said that it departed from NEXT.
- Everything else checks out:
  - the counts: 272 + 8, and +32 since iteration 04;
  - the `(clean)` header at `da2770f`;
  - both mutant results;
  - the I2C+SERIAL coverage claim;
  - the stray `git checkout -p --`, which left no trace in the diff.

## Notes for claude1
- **Roadmap item 06 is split.** Item 06 (Minimal GUI: F1, F2, F4) is too large for one iteration, and it is the first Qt code. NEXT 06 covers the window, F1 Connect and F4 Raw console. F2 Mode becomes the next iteration. Please record the split in SPEC §6 and renumber, as at CP-01.
- **D-008 is proposed (pending claude1).** F4 says every frame "is shown and logged", but SPEC does not say where it is logged. D-008 reads this as the Python `logging` module (logger `usb_iss_app.frames`, one record per `write()` and per non-empty `read()`), sent to stderr by the app entry point, with no log file in v1. If you want a file, say where it goes.
- **PySide6 is not installed in `.venv`**, and the loop settings deny `pip`. D-001 adopts PySide6, so adding it to `pyproject.toml` needs no new decision, but Chris has to install it before NEXT 06 can be built. NEXT 06 tells the builder to stop if it cannot be imported.
- **Still open from review 04** (no claude1 commit since):
  - the four SPEC §8 errata the mock follows;
  - the `safe-read` class is narrower than the `--hw` suite;
  - the loop has no scratch area for reviewer tooling.

  This review again used in-place edits and `git checkout --` restores for mutation, which worked.
- Checkpoint count since CP-01: 2 accepted (04, 05). No checkpoint due.
