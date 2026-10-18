# Iteration 03 — Review (fix cycle 0)

Model/effort: Opus 5.5 / high · Reviewed commit: `c9f5ebb` on `iter/03` (clean tree; code tested at `36b05d5`).

## Verdict
**Accept**

## Independent test run
Both runs used `.venv/bin/python scripts/run_tests.py --iter 03 [--hw] --tag review`. Both headers show `c9f5ebb (clean)`, and both exit codes were 0.
- Mock: `logs/review-mock-20261018-001732.txt` / `.xml`: 196 passed, 7 skipped (hw). Matches the builder's `build-mock-20261017-233217` (196 passed, 7 skipped).
- Hardware, unit 00069221 (port from `.env`). Before running, I read `docs/HARDWARE.md`, checked it against the NEXT 03 hardware section, and made sure the builder had finished. Log: `logs/review-hw-20261018-001847.txt` / `.xml`, 203 passed. The I2C lines match the builder's `build-hw-20261017-233218` byte for byte:
  - `58 a0` → `00`; `58 66` → `00`;
  - `55 a1 00 01` (read with n=3) → `ff`, then mode 0x40;
  - in IO_MODE, `58 a0` → `00`, then mode 0x00;
  - restore → 0x40.

## Acceptance criteria check
- [x] The mock run exits 0, and the tests cover requirements 1–6. I read `tests/test_i2c.py`. It covers:
  - every datasheet example frame, including the two counts corrected by D-006 (`54 30 04 …`, and the 37-byte `56 A0 00 00 20 …`);
  - every limit at the boundary and one past it, plus a count of 0;
  - odd, `0xFF`, `0x100` and −2 addresses on all nine builders;
  - AD1 reg 256, AD2 reg 0x10000, SGL value 256;
  - the three parsers;
  - every mock case listed in requirement 5.

  Requirement 6 is `test_io.py::test_mock_getad_non_general_pin_is_zero`.
- [x] The hardware run exits 0, the raw responses of steps 2–4 are logged, and the device is left in 0x40 (the `io_hw` fixture restores it).
- [x] The final logged runs show `(clean)`: the builder's at `36b05d5`, mine at `c9f5ebb`.
- [x] The iteration 00–02 tests are unchanged. In `test_io.py` and `test_hw.py` the diff only adds lines.

**Datasheet check** (I re-read pp.11–16):
- The command bytes 53/54/55/56/58 are correct.
- Read builders send `addr | 1`. AD2 sends the register high byte first.
- Write status: `00` means failed and any non-zero byte means success. I2C_TEST works the same way.
- The limits follow D-006: 60/60, 59 write, 64 read.
- The helpers use the transport's 500 ms default.
- Mock framing waits for the whole frame and never treats data bytes as commands.

**Mutation check.** I ran these on a scratch copy; the working tree was not touched. All 11 mutants were killed:
- the `_general_pins()` check removed from `_getad` (confirms the builder's requirement 6 claim): 1 test failed;
- the mock mode check removed;
- I2C+SERIAL refused;
- the AD1 write frame length off by one;
- AD1 not setting the pointer;
- an absent read returning `00`;
- `parse_i2c_write` requiring `FF`;
- the AD2 register sent low byte first;
- the AD2 read limit raised to 65;
- a short read accepted;
- odd addresses accepted.

These tests would fail if the code were wrong.

## Issues
1. **minor — reading (my NEXT 03's error).** Every I2C datasheet page cited in NEXT 03, and so in the new comments in `iss.py`, `mock.py` and `test_i2c.py`, is one page low. Each PDF page carries its printed number (pdftotext page 10 shows "10/23"). The correct pages are:
   - I2C_SGL write p.11, read p.12;
   - I2C_AD0 p.12;
   - I2C_AD1 p.13;
   - I2C_AD2 p.14;
   - I2C_TEST p.16.

   claude1 already noted this for D-006. The builder's comment header says "PDF page numbers, as in NEXT 03", and the `(printed p.N)` notes repeat it; both are wrong, because PDF and printed numbers are the same. The page citations from iterations 00–02 (pp.3, 5, 6, 8, 9, 19, 20) are correct. Carried into NEXT 04.
2. **minor — hardware.** In IO_MODE, the device answers I2C_TEST `58 A0` with `00`. Both the builder's run and mine show this. The mock gives no reply, as NEXT 03 required ("don't change the mock for it in this iteration"). The datasheet says nothing about I2C commands outside I2C modes. The mock should follow the device here. Carried into NEXT 04, for IO_MODE only: IO_MODE+SERIAL and SPI remain untested.
3. **minor — reading (hardware log; an iteration 01 test).** `test_hw_mode_sequence` sets I2C_S_100KHZ with IO_TYPE `0x0A` and IO_CHANGE `0x0F`. Both put `00` (output low) in the I/O3 and I/O4 bit pairs. HARDWARE.md, updated after iteration 02, says: "In every IO_TYPE byte, set unused pin pairs to digital input (`10`), never output". In I2C mode, I/O3 and I/O4 are SCL and SDA. The datasheet's own I2C example (p.9) uses `0x04`, which also has `00` in those bits, so they are almost certainly ignored. The pins are also unconnected. There is no hardware risk, but the test breaks the letter of the rule on every `--hw` run. NEXT 03 also said "I/O1 and I/O2 stay digital inputs (IO_TYPE `0xAA`) in every mode used", but this test makes them analogue inputs. They are still inputs, so this is harmless; my NEXT did not account for the older tests. Carried into NEXT 04, which explicitly allows changing these bytes.
4. **info — reading (my NEXT 03's ambiguity).** Requirement 5 asks for both "post-increment" and "like a PCF8574's latch" for I2C_SGL. These conflict: a latch reads back the byte just written. The builder followed the post-increment rule, and `test_mock_sgl` resets `d.pointer = 0` before reading. That is acceptable for a generic mock device. A real PCF8574 model belongs in a card's mock. No change needed.
5. **info — reading.** Hardware step 3 deliberately read n=3 after asking for 1 byte (`55 A1 00 01`), so that a stray extra byte would show up. The builder flagged the mismatch openly and followed NEXT as written, which was right. My NEXT should have said why.

## Scope drift
None. The few extra tests (address extremes 0x00 and 0xFE, AD2 high-byte-first with `0x1234`, AD0 write with wrap-around, AD1 reg −1) are within requirements 4–5. Only the files NEXT named were changed.

## Builder report accuracy
Two inaccuracies, both minor:
- "Mock run exits 0 (203 passed)". The builder's own mock log shows 196 passed and 7 skipped. 203 passed is the hardware run's count.
- "Page numbers in comments are the PDF pages used by NEXT". They are not PDF pages; they are NEXT's numbers, which are one page low (issue 1). Where the builder doubted the page numbers, they should have checked the PDF.

Every other claim holds: the raw responses, the requirement 6 mutation result (reproduced), unchanged earlier tests, the step 3 deviation, and the step 4 finding.

## Notes for claude1
- **Checkpoint due.** This is the 4th accepted iteration (00, 01, 02, 03).
- **SPEC §8 candidate.** "I2C_TEST outside the I2C modes (unspecified): in IO_MODE, firmware 0x09 answers `58 A0` with `00` (iteration 03 hardware logs, builder and reviewer)." NEXT 04 makes the mock follow this, the same way as the SETPINS note.
- **Empty-bus read (answers the NEXT 03 assumption).** I2C_AD1 read `55 A1 00 01` on the empty bus returns one `FF` byte and nothing more. This matches the mock's pull-up assumption. As the datasheet implies, a read from an absent device cannot be detected.
- **D-007 (pending claude1)** is proposed in `DECISIONS.md`. It sets the I2C_DIRECT limits where p.15 is ambiguous: whether the "< 60 bytes" frame limit includes the `0x57` command byte, the total number of bytes read per frame, and an empty frame. It also sets how the mock frames the two commands that have no length byte (I2C_DIRECT, p.15; SPI, p.17): one `write()` call is one frame. NEXT 04 includes a safe hardware probe of the overflow boundary.
- **Roadmap split.** I split roadmap item 04 into iteration 04 (I2C_DIRECT) and iteration 05 (SPI). I2C_DIRECT needs a sub-command interpreter in the mock, and that alone fills a 45-minute increment. From here on, roadmap items 05–10 run two iteration numbers later than their labels. Please renumber the SPEC roadmap.
- **SPI cannot be tested on the current bench.** In SPI mode, I/O1 becomes CE, an output, and I/O2 becomes SDO, an output (p.3). The GY module's TX drives I/O1, so this would put two outputs on one line, which HARDWARE.md forbids ("Never configure I/O1 as an output"). SDO would also clock bytes into the module's RX, and the module takes any byte as a command. Iteration 05 (SPI) will be mock-only unless Chris changes the bench. Please confirm, or add a line to HARDWARE.md.
- Ambiguities the builder noted, still open (not tested on hardware): I2C_SGL reads have no status byte; I2C_AD0 has no documented limit (D-006 uses 60); a read from an absent device cannot be detected.
