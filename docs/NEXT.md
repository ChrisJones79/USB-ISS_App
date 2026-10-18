# NEXT — Iteration 04 (fix cycle 0)

Recommended model/effort: Sonnet 5.5, high. The I2C_DIRECT sub-command interpreter in the mock is the most involved mock work so far.
Author: revclaude. Read `docs/iterations/03/review.md` first. Requirements 6–8 carry over from it.

## Context
Iteration 03 was accepted (`iter-03`). I2C_SGL, I2C_AD0/1/2 and I2C_TEST are in place, and the mock emulates an I2C bus of `MockI2cDevice`s.

This iteration is **the first half of roadmap item 04** (SPEC §6: "I2C_DIRECT and SPI"). It covers **I2C_DIRECT** only (datasheet pp.15–16). SPI is iteration 05. From now on, roadmap items 05–10 run two iteration numbers later than their labels.

The limits and the framing rule follow **D-007** (pending claude1).

A claude1 checkpoint is due (4 accepted iterations). Chris decides whether this build waits for it.

**Page numbers.** Every page number below is the datasheet's printed page, which is also the PDF page. NEXT 03's I2C page numbers were one page low; requirement 7 corrects them.

## Goal
`usb_iss_app.iss` can build I2C_DIRECT frames from sub-commands, refuse frames that break the limits, send them, and parse the two status bytes and the data. The mock interprets I2C_DIRECT against its `MockI2cDevice`s. On hardware, address-only frames on the empty bus, an unknown sub-command and the frame-length boundary record what the real device answers.

## Requirements

### 1. Constants (p.15; D-007)
- `I2C_DIRECT = 0x57`.
- Sub-commands:
  - `I2C_DIRECT_START = 0x01`, `I2C_DIRECT_RESTART = 0x02`, `I2C_DIRECT_STOP = 0x03`, `I2C_DIRECT_NACK = 0x04`;
  - READ is `0x20`–`0x2F` and WRITE is `0x30`–`0x3F`.
- `I2C_DIRECT_FRAME_MAX = 59` (D-007: the whole frame, `0x57` included). `I2C_DIRECT_CHUNK_MAX = 16` (p.15). `I2C_DIRECT_READ_TOTAL_MAX = 60` (D-007). Cite the page or D-007 in a comment on each.
- `I2C_DIRECT_NACK_REASONS = {0x01: "Device Error", 0x02: "Buffer Overflow", 0x03: "Buffer Underflow", 0x04: "Unknown command"}` (p.15).
- `IssNack`: when `command == "I2C_DIRECT"`, take the reason's name from `I2C_DIRECT_NACK_REASONS`, not from `NACK_REASONS`.
  - The message reads, for example, `"I2C_DIRECT NACK: 0x01 Device Error"`.
  - ISS_MODE messages don't change.
  - Update the docstring.

### 2. Builders (p.15)
- `direct_read(n) -> bytes` returns `bytes([0x20 + n - 1])`. It raises `ValueError` unless 1 ≤ n ≤ 16.
- `direct_write(data) -> bytes` returns `bytes([0x30 + len(data) - 1]) + data`. It raises `ValueError` unless 1 ≤ len(data) ≤ 16.
- `build_i2c_direct(*parts: int | bytes) -> bytes` returns `57` followed by the parts. An `int` part is one sub-command byte (0–255); a `bytes` part is appended as is.
  - It then walks the sub-commands and raises `ValueError` if:
    - there are none;
    - a sub-command byte is not in `01`–`04`, `20`–`2F` or `30`–`3F`;
    - a WRITE is followed by fewer data bytes than its count;
    - the frame is longer than 59 bytes;
    - the READ counts add up to more than 60.
  - It does not check I2C semantics, such as whether a START comes before an address.
  - The device address is written with a WRITE like any other byte. In the p.15 example, `31 40 55` is WRITE 2: address `40`, then data `55`.
- `i2c_direct_read_count(frame: bytes) -> int` returns the total READ bytes in a built frame, using the same walk.

### 3. Parser and helper (p.15)
- `parse_i2c_direct_status(resp: bytes) -> int`:
  - fewer than 2 bytes → `IssTimeout`;
  - `00 rr` → `IssNack(rr, "I2C_DIRECT")`;
  - `FF nn` → returns `nn`;
  - any other first byte → `IssProtocolError`.
- `i2c_direct(t, *parts) -> bytes`:
  - builds the frame and sends it in **one** `write()` call (D-007);
  - reads 2 bytes and parses them;
  - reads `nn` bytes; fewer → `IssTimeout`;
  - if `nn` differs from `i2c_direct_read_count(frame)` → `IssProtocolError` (after reading the `nn` bytes, so nothing is left behind);
  - returns the data;
  - uses the transport's default 500 ms timeout, as for the other I2C commands (pp.11–14).

### 4. Builder and parser tests
- Exact bytes for every datasheet example, built with the builders:
  - `57 01 31 40 55 03` (p.15, PCF8574 write);
  - `57 01 34 A0 00 00 12 34 03` (p.16, 24LC512 write, with `nn nn` = `12 34`);
  - `57 01 32 A0 00 00 02 30 A1 22 04 20 03` (p.16, 4-byte read with NACK); read count 4;
  - `57 01 32 A0 00 00 02 30 A1 23 03` (p.16, 4-byte read); read count 4.
- Every limit at the boundary and one past it:
  - `direct_read`: 16 and 1 are accepted; 17 and 0 are refused;
  - `direct_write`: 16 and 1 bytes are accepted; 17 bytes and empty are refused;
  - frame length: 58 × `I2C_DIRECT_STOP` (59 bytes) is accepted; 59 × (60 bytes) is refused;
  - total read: `direct_read(16)` × 3 + `direct_read(12)` (60) is accepted; with `direct_read(13)` instead (61) it is refused.
- Also refused: no parts; sub-command bytes `00`, `05`, `1F` and `40`; `build_i2c_direct(0x31, b"\x40")` (WRITE 2 with one data byte); an int part of 256.
- Parser:
  - `FF 00` → 0; `FF 04` → 4;
  - `00 01` to `00 04` → `IssNack` with that `reason`, and with the name from the table in its message;
  - `00` alone and empty → `IssTimeout`;
  - `7F 00` → `IssProtocolError`.

### 5. Mock: I2C_DIRECT (SPEC §3, "the mock"; pp.15–16; D-007)
- **Device model.** `MockI2cDevice` gains `addr_bytes: int = 1` (0, 1 or 2). Only I2C_DIRECT uses it:
  - in a write transaction, the first `addr_bytes` bytes after the address set the pointer, high byte first, once all of them have arrived;
  - later bytes are written at the pointer.

  I2C_SGL, I2C_AD0, I2C_AD1 and I2C_AD2 behave as before.
- **Framing (D-007).** When `0x57` is at the head of the buffer, the frame is everything from it to the end of the bytes received in that `write()` call. The mock does not wait for a later `write()`, just as for SERIAL_IO.
- **In the I2C modes and I2C+SERIAL:**
  - A frame longer than 59 bytes → `00 02`, and nothing is executed.
  - Otherwise, walk the sub-commands in order:
    - START or RESTART: the next byte written is an address.
    - WRITE k: if fewer than k bytes remain → `00 03`, and stop.
      - If an address is expected, the first byte is the address, and the device is `i2c_devices.get(b & 0xFE)`. If it is absent → `00 01`, and stop. ASSUMPTION: the device stops at the first unacknowledged address. The address's low bit selects write or read.
      - The other bytes go to the device addressed for writing (pointer bytes, then data, as above). If no device is addressed for writing, they are discarded.
    - READ k: k bytes from the device addressed for reading, appended to the read buffer. If no device is addressed for reading → k × `FF`. ASSUMPTION: the pull-ups hold SDA high, which matches iteration 03's empty-bus read.
    - NACK has no effect in the mock. STOP ends the transaction, so the next address needs a START.
    - Any other byte → `00 04`, and stop.
  - At the end of the frame → `FF n` followed by the n bytes read.
  - The mock does not check the total read count; the builder refuses those frames.
- **Other modes** (IO_MODE, IO_MODE+SERIAL, SPI): consume the frame, record it in `unhandled`, and send no reply. ASSUMPTION; hardware step 5 records IO_MODE.
- **Tests, through `i2c_direct`** (raw `write()` where noted):
  - p.15 example against a device at `0x40` with `addr_bytes=0`: returns `b""`, and `mem[0] == 0x55`.
  - p.16 examples against a device at `0xA0` with `size=0x10000` and `addr_bytes=2`. Pre-fill `mem[2:4]`, then send the write example (`12 34` at `0x0000`). Both read examples then return the 4 bytes from `0x0000`.
  - An I2C_DIRECT write to a device with `addr_bytes=1` reads back through `i2c_ad1_read` at the same register.
  - Absent address → `IssNack` with reason 1.
  - Raw `57 01 31 40` in one `write()` → `00 03`.
  - Raw `57 05` → `00 04`.
  - Raw `57` + 59 × `03` (60 bytes) → `00 02`. Raw `57` + 58 × `03` (59 bytes) → `FF 00`.
  - Split frame: raw `57 01 31` → `00 03` straight away. A following raw `40 55 03` gets no reply, and its bytes are in `unhandled`.
  - `5A 01` inside WRITE data is stored as data: no ISS_VERSION reply, and `unhandled` stays empty.
  - The commands work in I2C+SERIAL.
  - In IO_MODE, `i2c_direct` raises `IssTimeout`, the frame is in `unhandled`, and a following `version()` answers mode 0x00.

### 6. Carry-over: I2C_TEST in IO_MODE (review 03, issue 2)
- In IO_MODE (mode byte `0x00`), the mock answers I2C_TEST with `00`. The comment cites `docs/iterations/03/logs/build-hw-20261017-233218.txt` and `review-hw-20261018-001847.txt`.
- IO_MODE+SERIAL and SPI don't change (no reply; ASSUMPTION). The other I2C register commands don't change in IO_MODE.
- Change `test_i2c.py::test_mock_io_mode_consumes_frame`:
  - `i2c_test` now returns `False`, and `58 A0` is not in `unhandled`;
  - the AD1-write half of the test stays as it is.

  This is the only iteration 03 test whose assertions you may change.
- Add a test: in IO_MODE+SERIAL, `i2c_test` still raises `IssTimeout`, and the frame is in `unhandled`.

### 7. Carry-over: page citations (review 03, issue 1)
Comment-only change in `iss.py`, `mock.py`, `test_i2c.py` and `test_hw.py`. Move every I2C page citation added in iteration 03 up by one:
- I2C_SGL write p.11, read p.12; I2C_AD0 p.12; I2C_AD1 p.13; I2C_AD2 p.14; I2C_TEST p.16.
- `pp.10-13` → `pp.11-14`, and `pp.10-15` → `pp.11-16`.
- Remove `(PDF page numbers, as in NEXT 03)` and every `(printed p.N)` note.
- p.3 (pull-ups) is already correct.

### 8. Carry-over: IO_TYPE bytes in an iteration 01 hardware test (review 03, issue 3)
Change only `tests/test_hw.py::test_hw_mode_sequence`:
- I2C mode IO_TYPE `0x0A` → `0xAA`, in both the set and the restore, and in their labels.
- IO_CHANGE `0x0F` → `0xAF` (I/O1 and I/O2 analogue input, I/O3 and I/O4 digital input), and its label.

Nothing else in that test changes. Reason: HARDWARE.md says "In every IO_TYPE byte, set unused pin pairs to digital input (`10`), never output".

## Constraints / out of scope
- No SPI command (iteration 05). No GUI.
- No data byte written to any I2C address on hardware (see below).
- Do not edit SPEC, DECISIONS, HARDWARE, the role files, the templates, LOG or CHANGES.
- No new dependencies.
- If D-007 looks wrong to you, follow it anyway and say why in build.md.
- The iteration 00–03 tests stay unchanged, except for `test_mock_io_mode_consumes_frame` (requirement 6), `test_hw_mode_sequence` (requirement 8) and comment-only edits (requirement 7).

## Hardware tests
**safe-read + address-only I2C_DIRECT on the empty bus.** `docs/HARDWARE.md`:
- SCL and SDA (I/O3 and I/O4) are **not connected**. In the I2C modes the board's 4.7k pull-ups hold the bus high; in the other modes they are disconnected (p.3).
- I/O1 and I/O2 stay digital inputs (IO_TYPE `0xAA`) in every mode used. I/O1 is driven by the module's TX.
- No serial mode is entered. **No SPI mode is entered:** in SPI mode I/O1 becomes the CE output (p.3), and HARDWARE.md forbids I/O1 as an output.
- The only bus traffic is START, one address byte (`A0`) and STOP conditions. No data byte is written to any address.

Sequence: one test or several. The `io_hw` fixture, or a `finally`, must always run the restore step. Send each I2C_DIRECT frame in **one** `write()` call.
1. `5A 02 40 AA` (I2C_S_100KHZ) → mode 0x40.
2. Raw `57 01 30 A0 03` (START, WRITE 1: address `A0`, STOP). Read with `n = 4` and log the raw response. Assert nothing about it; the expected answer is `00 01`. Then ISS_VERSION: assert mode == 0x40.
3. Raw `57 05` (unknown sub-command). Read with `n = 4` and log. Assert nothing; expected `00 04`. Then ISS_VERSION: assert mode == 0x40.
4. Frame-length boundary, STOP conditions only. Read each with `n = 4` and log; assert nothing.
   - Raw `57` + 58 × `03` (59 bytes); expected `FF 00`.
   - Raw `57` + 59 × `03` (60 bytes). Under D-007's reading the expected answer is `00 02`. `FF 00` would mean the command byte does not count.
   - Then ISS_VERSION: assert mode == 0x40.
5. `5A 02 00 AA` (IO_MODE) → mode 0x00. Raw `57 01 30 A0 03`, read with `n = 4`, and log. Assert nothing. Then ISS_VERSION: assert mode == 0x00.
6. Restore: `5A 02 40 AA` → mode 0x40.

**When the device disagrees with the mock:**
- Steps 2, 3 and 5: make the mock match what the device did. Cite the log in the comment, adjust the affected mock test, and report it.
- Step 4: if the device disagrees, make the mock's overflow response match the device, but **keep the builder limit at 59** (D-007). Report it.

## Acceptance criteria
- [ ] `.venv/bin/python scripts/run_tests.py --iter 04 --tag build` exits 0. The new tests cover requirements 1–8 as listed, including every p.15–16 example frame and every limit boundary.
- [ ] `.venv/bin/python scripts/run_tests.py --iter 04 --hw --tag build` exits 0. The log shows:
  - the raw responses of steps 2–5;
  - the device left in mode 0x40;
  - `test_hw_mode_sequence` labels showing `5A 02 40 AA` and `5A 02 10 AF`.
- [ ] The final logged runs' headers show the tested commit as `(clean)`.
- [ ] The iteration 00–03 tests pass and are unchanged, apart from the exceptions listed in the constraints.

## Report back
- The raw responses from hardware steps 2–5, whether the mock matched each one, and what you changed if it didn't.
- Whether step 4 supports D-007's reading of "< 60 bytes".
- Anything on pp.15–16 you found ambiguous. Note it; don't test it on hardware. Examples: what the device does after a NACK partway through a frame; whether a frame must end with STOP; what the NACK sub-command changes when it is not followed by a READ.
