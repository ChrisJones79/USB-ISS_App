# Iteration 01 — Review (fix cycle 0)

Model/effort: Opus 5.5, high · Reviewed commit: `e95a61a` on `iter/01` (code at `27e0ac6`; `e95a61a` adds only build.md and logs). The tip was re-checked just before merging and had not moved. Merge commit: `d1521c8`.

## Verdict
**Accept**

## Independent test run
- Mock: `logs/review-mock-20261017-004045.txt` / `.xml`: 112 passed, 3 skipped (hw), exit 0. Header: `e95a61a (clean)`.
- Hardware: `logs/review-hw-20261017-004050.txt` / `.xml`: 115 passed, exit 0. Header: `e95a61a (clean)`, port `/dev/serial/by-id/usb-Devantech_Ltd._USB-ISS._00069221-if00`.
- Both match the builder's `build-*-20261017-003245` logs: the same counts, and the same `HW` lines, byte for byte:
  - `HW IO_CHANGE 5a 02 10 0f raw response: ff 00`
  - mode after each step: 0x40 → 0x40 (IO_CHANGE) → 0x00 → 0x40 (restore).
- The builder's headers show `27e0ac6 (clean)`, the code commit. Review 00 issue 4 is fixed in practice, not just in code.
- Ad-hoc probe (no log; a script in the scratchpad, not committed):
  - `spi_divisor(6e6/k)` for k = 2…256: 12 values of k come out one divisor lower (k = 31, 62, 87, 124, 127, 165, 171, 174, 175, 248, 253, 254). See issue 3.
  - `baud_divisor(3_000_000)` gives divisor 0, error 0 %, so it is accepted. 3 000 001 is refused, because its divisor is −1.

## Acceptance criteria check
- [x] Mock run exits 0. Coverage, checked by reading `tests/test_mode.py`:
  - Req 1: every mode constant; `decode_mode` for every base mode, three +SERIAL combinations, SPI phases 0/2/3, and unknown bytes.
  - Req 2: `io_type` against 0x01 and 0xB4 (p.7) plus the three hardware IO_TYPEs; a bad pin value is refused.
  - Req 3: all 8 rows of the p.8 baud table, with 2400 = `04 E1`, each also asserted as a full `build_io_serial` frame. 115200 → 25 / 115385 / +0.16 %. 460800, 0, negative and out-of-range rates are refused by both serial builders. SPI 3 MHz → 1, 500 kHz → 11, 23437.5 Hz → 255; 4 MHz and 20 kHz are refused.
  - Req 4: all six datasheet example frames, exact bytes. Non-I2C modes, bad phases and bad IO_TYPE bytes are refused. `FF 00` OK. `FF 01`, `00 00/04/08`, `01 00` and `FE 00` raise `IssProtocolError`. Short responses (0 or 1 byte) raise `IssTimeout`. Each NACK reason maps to its name, and `IssNack` is an `IssError`.
  - Req 5: the `5A 02 01 5A 01 B0` framing test; byte-at-a-time arrival; mode reflected in ISS_VERSION for 5 frame kinds; IO_CHANGE keeps the mode; unknown mode → `00 05` with nothing left over; NACK 05 through `set_mode` (unknown mode byte), and 06/07 through `set_mode` (forced hook, one-shot, mode unchanged).
  - Reqs 6 and 7: the default-timeout test, plus constructor and default timeouts checked against a fake `serial.Serial`.
- [x] The hardware run passes. The log shows the raw IO_CHANGE response and the mode byte after each step, and the device ends in 0x40. The restore runs in `finally`.
- [x] The final logged runs' headers show the tested commit as `(clean)`: the builder's at `27e0ac6`, mine at `e95a61a`.
- [x] Iteration 00 tests pass, with one input changed (build.md deviation 1). I accept this change. The conflict came from NEXT 01 itself: it made `5A 02 40 00` a valid frame, while an iteration 00 test used that same frame as its "unhandled" example. The new input `5A 10 40 00` keeps the test's intent, and its assertions are unchanged. The NEXT defect was mine.

Datasheet check (pp.5–10):
- Every frame byte matches the datasheet.
- The response is always 2 bytes, read with the 500 ms default timeout.
- NACK reasons 05/06/07 are handled.
- The p.8 formula erratum and the 2400 row are handled per SPEC §8.
- The SPI divisor stays within 1–255, and divisor 0 is never emitted (p.10, D-005).
- Buffer limits don't apply to ISS_MODE.

## Issues
1. **minor — reading.** The comment on the mock's IO_CHANGE assumption says "see NEXT 01 req. 9". NEXT 01 has no requirement 9: I wrote that reference in NEXT 01, meaning its "Hardware tests" section, and the builder copied it. Hardware has now answered the question for one case (from I2C_S_100KHZ, IO_CHANGE → `FF 00`, mode stays 0x40). The comment should cite that result. Carried into NEXT 02.
2. **minor — test.** `test_default_timeout_is_500ms` accepts `None` as the default for `Transport.read` and `MockTransport.read`, where only `SerialTransport.read` legitimately uses `None`. If either abstract or mock default became `None`, the test would stay green. The module constant and the real `SerialTransport` path are pinned properly, so the datasheet requirement is covered. Carried into NEXT 02 as a one-line tightening.
3. **minor — test (probe).** `spi_divisor` takes the ceiling of a float division. When the request equals an achievable SCK exactly, computed as `6e6/k`, 12 of 255 cases land one divisor lower (a slower clock), because `6e6/(6e6/k)` comes out a hair above k. This is correct under D-005 for the float it was given: it never exceeds the request. But a GUI user who types back a displayed "actual" frequency could get the next slower clock. No action now. Noted for the GUI iteration (04), which could let the user pick the divisor directly.
4. **minor — reading.** `decode_mode(0x10)` returns `"IO_CHANGE"` (build.md deviation 4). Hardware shows ISS_VERSION keeps the previous mode after IO_CHANGE, so this branch is probably unreachable. It is harmless. No action.
5. **info — reading.** `baud_divisor` returns `(−1, inf, inf)` for rates above 3 Mbps instead of raising. The builders refuse such rates, which is what NEXT asked for. Callers that display the tuple (GUI, iteration 04) must handle `inf`. No action now.

No blocker or major issues. Error handling covers NACK, short response (timeout), wrong mode for the builder, and out-of-range arguments. "No device present" doesn't apply to ISS_MODE.

Test quality, by reading: each of these mistakes would fail at least one test:
- reversing the IO_TYPE bit order (0xB4);
- rounding the baud divisor instead of taking the floor (9600 → 312);
- using the printed 2400 bytes (`09 E1`);
- taking the floor of the SPI divisor instead of the ceiling (1.1 MHz case);
- swapping ACK and NACK;
- the mock acting before a frame is complete, or reading payload `5A 01` as a command;
- IO_CHANGE updating the mock's mode;
- a NACK hook that is not one-shot.

## Scope drift
None of substance:
- `decode_mode` names 0x10 (issue 4).
- `IssNack` gives a readable name to unknown reasons.
- `spi_divisor` refuses out-of-range requests explicitly. That is exactly what D-005 says, so build.md's deviation 3 is not really a deviation.

No new dependencies. No changes to SPEC, DECISIONS or process files.

## Builder report accuracy
Every checkable claim holds:
- test counts (112 + 3 skipped, 115);
- the log names;
- the header commits and the clean flags;
- the IO_CHANGE response and the mode bytes;
- the device ending in 0x40;
- the list of files changed;
- the deviations.

Zero inaccuracies. Deviation 1, the edited iteration 00 test, was raised openly and correctly asked for confirmation.

## Notes for claude1
- **SPEC §8 note 3 is now answered by hardware.** IO_CHANGE (`5A 02 10 0F` from I2C_S_100KHZ) returns `FF 00`, the same 2-byte response as the other mode commands. ISS_VERSION still reports 0x40 afterwards. Evidence: the `HW` lines in `docs/iterations/01/logs/build-hw-20261017-003245.txt` and `review-hw-20261017-004050.txt`. The note could become a statement of this fact.
- **D-005 is still pending.** Iteration 01 is built to it. Issue 3 is a float-precision consequence of the ceiling rule, worth knowing when you confirm it.
- **Datasheet ambiguities the builder raised.** I agree with all of them, and none blocks progress:
  - which IO_TYPE bits the firmware honours for pins taken by I2C or serial;
  - p.8 says "I/O3 and I/O", an apparent typo for I/O4;
  - the NACK framing for an unknown mode byte;
  - the state of I/O3/I/O4 after I2C+SERIAL, whose frame has no IO_TYPE byte.
- **Process.** NEXT 01 contained two reviewer defects: the dangling "req. 9", and acceptance criteria that could not all be met (a new valid frame vs an "iteration 00 tests unchanged" criterion). The builder caught and reported the second one. When a NEXT turns an old "unhandled" example into a handled command, the reviewer should check the old tests first.
- **No checkpoint due.** Two iterations accepted (00, 01), no Rethink, no Fix cycles.
