# Iteration 04 — Review (fix cycle 0)

Model/effort: Opus 5.5 / high (headless, `scripts/loop.sh`) · Reviewed commit: `a9d5e84` on `iter/04` (clean tree). Code tested by the builder at `74f2988`. The two commits after it are the build report and logs (`57760dd`) and claude1's loop.sh v3.1 fix (`a9d5e84`), which touches no product code.

## Verdict
**Accept**

## Independent test run
Both runs used `.venv/bin/python scripts/run_tests.py --iter 04 [--hw] --tag review`. Both headers show `a9d5e84 (clean)`, and both exited 0.
- Mock: `logs/review-mock-20261018-031331.txt` / `.xml`: 240 passed, 8 skipped (hw). Matches the builder's final `build-mock-20261018-021231` (240 passed, 8 skipped).
- Hardware, unit 00069221 (port from `.env`): `logs/review-hw-20261018-031344.txt` / `.xml`, 248 passed. Before running, I read `docs/HARDWARE.md` and checked it against the NEXT 04 hardware section. They agree: IO_TYPE `0xAA` everywhere, plus `0xAF` for IO_CHANGE (all four pins inputs). No serial or SPI mode is entered. The only bus traffic is START, the `A0` address and STOPs. Nothing else held the port: the loop runs one step at a time, and the build step had finished.
- The I2C_DIRECT lines match the builder's `build-hw-20261018-021231` byte for byte:

| Step | Frame | Builder | Review |
|---|---|---|---|
| 2 | `57 01 30 A0 03` (I2C_S_100KHZ) | `00 01` | `00 01` |
| 3 | `57 05` | `ff 00` | `ff 00` |
| 4 | `57` + 58 × `03` (59 B) | `ff 00` | `ff 00` |
| 4 | `57` + 59 × `03` (60 B) | `ff 00` | `ff 00` |
| 5 | `57 01 30 A0 03` (IO_MODE) | `00` | `00` |

  The mode was 0x40 after steps 2–4, 0x00 after step 5, and 0x40 after the restore. All the other hardware lines (iterations 00–03) match too. The GETAD analogue readings differ by a few counts, as expected: the pins are floating or carry the module's TX.
- **An earlier, interrupted review attempt.** `main` already held `review-mock-20261018-030722` and `review-hw-20261018-030754`, both at `57760dd (clean)`, committed by Chris in `1db656f` ("stopped loop script on accident"). They come from a review run that was stopped before it wrote anything else. I did not use them as evidence, and I left them untouched. Their I2C_DIRECT lines also match the table above.

**Mutation check.** I applied 17 single-line mutants, one at a time. Each was an in-place Edit, followed by `pytest tests/test_i2c_direct.py tests/test_i2c.py` and a `git checkout --` restore. No runner logs were written, and the tree was clean afterwards.
- **15 killed.** In `iss.py`:
  - frame limit `>`→`>=`;
  - read total `>`→`>=`;
  - WRITE underflow off by one;
  - no-sub-command check removed;
  - status `< 2`→`< 1`;
  - count-mismatch check removed;
  - NACK table always ISS_MODE's;
  - helper split into two `write()`s.

  In `mock.py`:
  - `begin_direct_write` made a no-op;
  - overflow threshold 61;
  - read bit inverted;
  - I2C_TEST answered in IO_MODE+SERIAL;
  - I2C+SERIAL not treated as I2C;
  - mock underflow off by one;
  - IO_MODE I2C_DIRECT not answered.
- **2 survived** (issues 1 and 2 below):
  - `MockI2cDevice` pointer built little-endian;
  - STOP not ending the transaction.

## Acceptance criteria check
- [x] **Mock run exits 0, and the new tests cover requirements 1–8.** I read `tests/test_i2c_direct.py`. It covers:
  - the constants;
  - all four p.15–16 example frames, built with the builders, and the read counts of both read examples;
  - every limit at the boundary and one past it: READ 1/16 vs 0/17; WRITE 1/16 vs 0/17; frame 59 vs 60; read total 60 vs 61;
  - every refused frame NEXT lists (`()`, `00`, `05`, `1F`, `40`, 256, `31 40`), plus −1 and a bare `30`;
  - the parser, with all four NACK names in the message;
  - the helper: one `write()`, short data → timeout, a count mismatch reads everything;
  - every mock case in requirement 5 (with the deviations below).

  Requirement 6 is `test_i2c.py::test_mock_io_mode_consumes_frame` (changed as NEXT allowed) and the new `test_mock_io_serial_mode_i2c_test_unanswered`. Requirement 7: no `(printed p.N)`, no `PDF page`, and no `pp.10-13`/`pp.10-15` remain in `src/` or `tests/`. Requirement 8: the diff of `test_hw_mode_sequence` is exactly the four IO_TYPE bytes and their labels.
- [x] **Hardware run exits 0.** The log shows the raw responses of steps 2–5 and the device left in mode 0x40, and the `test_hw_mode_sequence` labels read `5A 02 40 AA` and `5A 02 10 AF`.
- [x] **The final logged runs show `(clean)`:** the builder's at `74f2988`, mine at `a9d5e84`.
- [x] **The iteration 00–03 tests are unchanged** apart from the permitted exceptions. Only `test_hw.py`, `test_i2c.py` and the new `test_i2c_direct.py` changed under `tests/`. In `test_i2c.py` the diff is comment-only page edits, the requirement 6 change and one added test. In `test_hw.py` it is requirement 8 and one added test.

**Datasheet check (pp.15–16, against the PDF myself).**
- `0x57`. Sub-commands `01`–`04`, READ `20`–`2F` (1–16), WRITE `30`–`3F` (1–16).
- Status `FF nn` / `00 rr`, and the four reason names, exactly as printed.
- All three example frames, byte for byte. NEXT's `12 34` stands in for the p.16 `nn nn`.
- "< 60 bytes" is ambiguous, as D-007 says. The builder keeps 59.

The helper uses the transport's 500 ms default. It reads the 2 status bytes first, then `nn`, as p.15 says.

## Issues
1. **minor — test (found by mutation).** Requirement 5 says the I2C_DIRECT pointer bytes are taken "high byte first". The code does that (`int.from_bytes(..., "big")`), but no test can tell: every 2-byte-pointer test uses address `0x0000`, and `test_mock_partial_pointer_does_not_set_pointer` sends only one byte. A little-endian mutant passes all 79 I2C tests. → NEXT 05 carry-over.
2. **minor — test (found by mutation).** Requirement 5 says "STOP ends the transaction, so the next address needs a START". No test has anything after a STOP inside a frame, so a mock in which STOP does nothing passes. NEXT 04 did not list such a test; this gap is mine. → NEXT 05 carry-over.
3. **minor — reading (my NEXT 04 defect).** My split-frame case said all the bytes of the second raw write `40 55 03` would land in `unhandled`. But `55` is I2C_AD1, so the mock correctly holds `55 03` as an incomplete I2C_AD1 frame, and only `40` is unhandled. The builder reported this and asserted the right thing. No change needed.
4. **info — hardware.** Three hardware results contradict p.15, and the mock now follows the device, as SPEC §3 requires:
   - `57 05` answers `FF 00`: an unknown sub-command is ignored, not NACKed `04`;
   - a 60-byte frame (`57` + 59 STOPs) answers `FF 00`;
   - in IO_MODE, I2C_DIRECT answers a single `00`.

   The builder was right to keep the 60-byte reading out of the builder limit (D-007). Step 4 does **not** support D-007's reading that the `0x57` byte counts. The true limit is 60 or more and unknown, and 59 stays as the safe limit. SPEC §8 has no entries for these, nor for iteration 03's I2C_TEST-in-IO_MODE result (see Notes for claude1).
5. **info — mock.** NACK `00 04` can no longer occur in the mock, because the device ignored the only unknown sub-command tried. `parse_i2c_direct_status` still names it, as p.15 does. That is correct, since other firmware may send it.

No blocker or major issue. The code does what NEXT 04 asks. The mock assumptions are labelled, and each hardware-driven change cites its log.

## Scope drift
None. No SPI, no GUI. No data byte was written to any I2C address on hardware. No new dependencies. The process files on `iter/04` (`scripts/loop.sh`, `CHANGES.md`) came from claude1's commit `a9d5e84`, which is identical to `690cdb5` on `main`. They are not builder changes.

## Builder report accuracy
No inaccuracies found.
- The counts are right: 240 + 8 mock, 248 hardware, and 239 + 8 / 247 for the superseded runs at `8c37d41`.
- Both final headers show `74f2988 (clean)`.
- The hardware table matches the log.
- All four deviations from NEXT are disclosed and correctly argued. The split-frame one is my NEXT defect (issue 3).
- One quibble: the report says "Model/effort: Sonnet 5.5 (effort not shown to me)". The loop's `run.log` records `effort requested=high`.

## Notes for claude1
- **SPEC §8 is missing four errata that the mock now follows.** SPEC §3 says "the mock follows the device, and §8 records the erratum with its evidence". The evidence for each (fw 0x09, unit 00069221, 3.3 V):
  - I2C_DIRECT `57 05` → `FF 00`, not `00 04` (p.15): `04/logs/build-hw-20261018-021131.txt`, `-021231.txt`, `review-hw-20261018-031344.txt`.
  - A 60-byte I2C_DIRECT frame → `FF 00` (p.15, "< 60 bytes"): the same logs. The builder keeps 59 (D-007). D-007's rationale sentence "NEXT 04 step 4 settles it" can now say that it settled it the other way.
  - I2C_DIRECT in IO_MODE → `00`, a single byte (pp.15–16 say nothing): the same logs.
  - I2C_TEST in IO_MODE → `00`: `03/logs/build-hw-20261017-233218.txt`, `review-hw-20261018-001847.txt`. CP-01 §1.6 lists it as confirmed, but §8 does not.
- **The `safe-read` class (REVIEWER.md, Loop status) is narrower than the existing hardware suite.** `run_tests.py --hw` always runs every hardware test, and those include:
  - IO_CHANGE `0xAF` and IO_MODE `0xFF` (analogue inputs), whose IO_TYPE is not `0xAA`;
  - SETPINS `63 0F`, which is an output command, though it has no effect with no output pins.

  Read strictly, any NEXT that asks for a `--hw` run is `beyond-safe-read`. I classed NEXT 05 as `none` (mock-only), so the question doesn't arise yet. Two possible fixes: widen the class to "the existing hardware suite as of `iter-NN`", or give the runner a way to select tests.
- **A tool denial in this headless review.** A `Write` of a scratch mutation script to `/tmp` was denied: it is outside the allowed directories. I did the same mutation check with allowed tools instead: Edit, `pytest`, and `git checkout --` to restore. The loop settings have no scratch area, so mutation checks will keep costing many tool calls unless one is added (for example, a gitignored `.review-scratch/` with the matching `.venv/bin/python` allow).
- **Records from the loop's first stop.** The earlier review attempt's logs (`review-*-0307*`) were committed to `main` by Chris (`1db656f`), and its loop run record is not in `docs/process/loop/`. claude1's v3.1 commit is on both branches (`690cdb5`, `a9d5e84`). Git merged it cleanly because the content is identical.
- Checkpoint count since CP-01: 1 accepted (04). No checkpoint due.
