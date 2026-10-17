# Iteration 02 — Build report

Model/effort: Sonnet 5.5, medium · Branch: iter/02 · Commit: f8b71d6 (code; this report and the logs are committed after it)

## Summary
Added SERIAL_IO, SETPINS, GETPINS and GETAD builders, parsers and helpers to `iss.py`, with the 30-byte transmit and 62-byte receive limits enforced. `IssNack` now accepts `reason=None`. The mock tracks IO_TYPE, the general-I/O pins each mode implies, output levels, `inputs`/`adc`, SETPINS/GETPINS/GETAD, and SERIAL_IO with transmit/receive buffers. Both review-01 carry-overs are done.

**The hardware run has one failing test.** On the real device GETAD on a digital-input pin does not answer `00 00` as p.20 and NEXT step 3 say. It answers a raw ADC value. I did not weaken the assertion. See Test results and Questions.

## Files changed
- `src/usb_iss_app/iss.py`: constants, SERIAL_IO/SETPINS/GETPINS/GETAD, `SerialIoResult`, `IssNack(reason=None, command=...)`.
- `src/usb_iss_app/mock.py`: I/O state and SERIAL_IO emulation; IO_CHANGE comment now cites the iter 01 hardware log (carry-over 1).
- `tests/test_io.py` (new): 47 tests for requirements 1–5.
- `tests/test_hw.py`: three new hardware tests with a restoring fixture.
- `tests/test_mode.py`: `test_default_timeout_is_500ms` tightened (carry-over 2).

## Acceptance criteria
- Mock run exits 0, new tests cover reqs 1–6: **met**. `logs/build-mock-20261017-011807.txt` (159 passed, 6 skipped hw). Covers p.20 GETAD examples, 30/31-byte boundary, 62-byte rx cap, NACK-with-rx.
- Hardware run passes: **not met**. `logs/build-hw-20261017-011807.txt`: 164 passed, 1 failed (`test_hw_io_getad_on_digital_pin`). Raw SETPINS, both GETPINS, four GETAD values and both out-of-range responses are logged; device ends in 0x40 (`restore` line in every test).
- Headers show `(clean)`: **met**, `f8b71d6`.
- Iteration 00/01 tests unchanged except req 6 issue 2: **met**. That test also now asserts `SerialTransport.read` defaults to `None`, which pins the one exception rather than leaving it unchecked.

## Test results
- Mock: `docs/iterations/02/logs/build-mock-20261017-011807.txt`: 159 passed, 6 skipped.
- Hardware: `docs/iterations/02/logs/build-hw-20261017-011807.txt`: 164 passed, 1 failed.

Requested findings (all from the hardware log):
- SETPINS `63 0F` with no output pins: raw response `00` (NACK).
- GETPINS raw bytes: `0F` before and `0F` after SETPINS. Bits 7:4 are 0. Low nibble 1111: all four pins read high.
- GETAD on digital input, I/O1: `02 E1` = 737, not `00 00`. (An earlier, superseded run gave `02 E3`; its logs were deleted as I changed the test layout, so only the final run is in the repo.)
- GETAD analogue mode: ch1 740, ch2 743, ch3 781, ch4 709. All four sit near 0.7 of full scale, so I/O1 and I/O2–I/O4 are likely pulled up/floating rather than showing distinct signals. I did not investigate.
- Out-of-range `65 00` and `65 05`: both `00 00`, as p.20 says.

## Deviations from NEXT.md
1. Hardware sequence split into three tests (steps 1–2, 3, 4–5), each with a fixture that restores `5A 02 40 AA`. NEXT allows "several". Reason: a failure in step 3 would otherwise hide steps 4–5. Step 1 and 2's separate mode-set after the restore is the only added mode traffic.
2. Restore frame is `5A 02 40 AA` as NEXT says (iter 01 used `40 0A`).
3. The superseded first run's logs were removed before the final run because the code under test changed (test layout). Nothing hand-edited.

## Questions and proposed spec/process changes
- **Datasheet vs hardware conflict (GETAD).** p.20 says a channel not set up as analogue returns `0000`. This device (fw 0x09) returns the converted value on a digital-input pin. Reviewer decision needed: keep the test as a recorded datasheet deviation, or change NEXT/SPEC to say the device returns a value. The mock follows the datasheet (`00 00`), so the mock and hardware now disagree. Suggest SPEC §8 note this erratum.
- **SETPINS with no output pins NACKs (`00`).** The datasheet is silent; this is now a finding. The mock ACKs (`FF`) here per NEXT req 4 ("answers FF"). Suggest the mock NACK when no general-I/O pin is an output, if you want it faithful.
- **GETPINS reads 0F** with I/O1 supposedly driven by the module's TX and others floating; consistent with internal pull-ups (not tested further).
- Ambiguity, p.19: TxCount is read as "bytes pending" per NEXT. Untested on hardware. The datasheet's behaviour when the receive buffer overflows is unspecified (mock drops extra bytes). SERIAL_IO framing without a length byte is assumed to be one `write()`.
