# Iteration 03 — Build report

Model/effort: Sonnet 5.5, medium · Branch: iter/03 · Commit: 36b05d5 (tested commit; this report and the logs are committed after it)

## Summary
Added the five register-style I2C commands (I2C_SGL, I2C_AD0, I2C_AD1, I2C_AD2, I2C_TEST) to `iss.py`: constants and limits (D-006), nine builders, three parsers, and eleven helpers. The mock gained `MockI2cDevice` and `MockTransport.i2c_devices` (empty by default), frame-length-aware I2C handling in the I2C modes and I2C+SERIAL, and consume-and-record in the other modes. Requirement 6 (GETAD on a non-general pin) is a new test, with the mutation check done. The `IssNack` docstring now covers I2C writes.

## Files changed
- `src/usb_iss_app/iss.py`: I2C constants, builders, parsers, helpers; `IssNack` docstring.
- `src/usb_iss_app/mock.py`: `MockI2cDevice`, `i2c_devices`, `_i2c_frame_len`, `_i2c_command`, dispatch in `_process`.
- `tests/test_i2c.py` (new): requirements 1–5.
- `tests/test_io.py`: one added test, `test_mock_getad_non_general_pin_is_zero` (requirement 6). Existing tests unchanged.
- `tests/test_hw.py`: one added test, `test_hw_i2c_empty_bus` (hardware steps 1–5; restore is the existing `io_hw` fixture).

## Acceptance criteria
- Mock run exits 0 (203 passed): `docs/iterations/03/logs/build-mock-20261017-233217.txt`. The tests cover every datasheet example frame, every limit at the boundary and one past, the D-006 corrected counts, and the mock cases listed in requirement 5. Met.
- Hardware run exits 0 (203 passed): `docs/iterations/03/logs/build-hw-20261017-233218.txt`. The log shows the raw responses of steps 2, 3 and 4, and the final restore leaves mode 0x40. Met.
- Both log headers show the tested commit as `(clean)`. Met.
- Iteration 00–02 tests are unchanged and pass. Met.

## Test results
203 passed, 0 failed (mock and hardware runs). Logs: see the two paths above.

**Requirement 6 mutation check:** I removed `and ch - 1 in self._general_pins()` from `MockTransport._getad`. `test_mock_getad_non_general_pin_is_zero` failed (and nothing else did). I then restored the code from a backup and re-ran the suite green. The committed `mock.py` has the check.

## Hardware results (raw responses are in the hardware log)
- Step 1: `5A 02 40 AA` accepted; mode 0x40.
- Step 2: `58 A0` → `00`. `58 66` → `00`. One byte each, as expected.
- Step 3: `55 A1 00 01` (read requested n=3 bytes) → `ff`: one byte, and nothing more. ISS_VERSION afterwards: mode 0x40.
  - The mock's absent-device read matched the device (one byte, `FF`). **No mock change.**
- Step 4: IO_MODE `5A 02 00 AA` → mode 0x00. `58 A0` read with n=2 → `00` (one byte). ISS_VERSION afterwards: mode 0x00.
  - **Finding:** in IO_MODE the device answers I2C_TEST with `00`. The mock sends no reply in other modes, as NEXT specified. Per NEXT I did not change the mock. Proposal: the mock should answer `00` for I2C_TEST in the non-I2C modes (needs claude1/revclaude decision; SPI, IO_MODE+SERIAL not checked).
- Step 5: restored to mode 0x40.

## Deviations from NEXT.md
- Step 3: the helper reads with `n=3`, but the frame asks the device for one byte (`55 A1 00 01`, as written in NEXT). That is why the response is 1 byte. If NEXT meant a 3-byte read (`... 00 03`) it is a one-line change; the result for the absent-device question is the same.
- Hardware test is one test function, with the sequence inside it (NEXT allowed "one test or several").
- Page numbers in comments are the PDF pages used by NEXT; D-006 says its own page refs were one low and gives printed page numbers. I used NEXT's.

## Questions and proposed spec/process changes
- Ambiguities (not tested on hardware): I2C_SGL reads have no status byte; I2C_AD0 has no documented limit (D-006 uses 60); a read from an absent device can't be detected; the datasheet doesn't say whether I2C_AD1/AD2 reads set a register pointer that I2C_AD0 continues from beyond p.11's description; AD2 read max of 64 vs. AD1/AD0 60 comes from the datasheet text only.
- D-006 looks right to me; I followed it and found nothing against it.
- Mock behaviour for I2C_TEST outside the I2C modes should be updated to `00` (see step 4).
