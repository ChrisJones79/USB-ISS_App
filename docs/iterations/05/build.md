# Iteration 05 — Build report

Model/effort: Sonnet 5.5 / medium · Branch: iter/05 · Commit: da2770f (code and tests); this report and the log are in the next commit

## Summary
SPI (pp.17–18): `SPI_IO`, `SPI_FRAME_MAX`, `SPI_DATA_MAX`, `build_spi_io`, `parse_spi_response`, `spi_io` in `iss.py`. `MockSpiDevice` and `MockTransport.spi_device` in `mock.py`, with the SPI-mode, no-device, over-length, lone-`61` and outside-SPI-mode behaviour from NEXT. New `tests/test_spi.py` (a 23K256 model lives in it). Two I2C_DIRECT carry-over tests added to `tests/test_i2c_direct.py`. No hardware run.

## Files changed
- `src/usb_iss_app/iss.py`, `src/usb_iss_app/mock.py`
- `tests/test_spi.py` (new), `tests/test_i2c_direct.py` (two tests appended; existing tests unchanged)

## Acceptance criteria
- [x] Runner exits 0, tests cover requirements 1–6: `logs/build-mock-20261018-081512.txt` (272 passed, 8 skipped hw). The three pp.17–18 frames are `test_example_*`; limits are `test_limits` (62 ok; 0 and 63 refused).
- [x] Header shows `da2770f… (clean)`.
- [x] No hardware log in `docs/iterations/05/logs/`.
- [x] Iteration 00–04 tests pass and are unchanged apart from the requirement 6 additions.
- [x] Requirement 6 mutants. I applied each by in-place edit of `mock.py`, ran `tests/test_i2c_direct.py`, then reverted (tree diff confirmed). No runner logs were written for the mutant runs.
  - `test_mock_pointer_high_byte_first` **failed** against the little-endian pointer (`"big"`→`"little"`); the other 44 passed.
  - `test_mock_stop_ends_transaction` **failed** against STOP doing nothing; the other 44 passed.

## Test results
`logs/build-mock-20261018-081512.txt` / `.xml`: 272 passed, 8 skipped (hw), exit 0. Before this, 240 passed, so +32 tests.

## Deviations from NEXT.md
- The "Outside SPI mode" test starts the mock in 0x40 and enters the mode via `set_mode` with the builder frame, for the four listed modes.
- I2C+SERIAL requirement: no existing test sets the mock to `5A 02 61 …` (`test_mode.py:106` only checks the built bytes), so I added `test_mock_i2c_serial_h100_still_settable`.
- A stray `git checkout -p --` with no input ran during the mutation step; it changed nothing (diff confirmed).

## Questions and proposed spec/process changes
Ambiguities on pp.17–18 (noted, not tested):
- When the device sends a NACK, and how many bytes follow it. The parser ignores them.
- Whether CE stays low across the whole frame. The mock assumes it does (one `transfer()`).
- What `61` alone or a frame over 63 bytes gets back. The mock assumes `FF` and `00`.
- What `61` does outside SPI mode. The mock drops it with no reply; IO_MODE answered I2C commands with `00` in iterations 03 and 04.
