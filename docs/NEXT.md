# NEXT — Iteration 05 (fix cycle 0)

Recommended model/effort: Sonnet 5.5, medium. SPI has no sub-commands, so this is smaller than iteration 04.
Author: revclaude. Read `docs/iterations/04/review.md` first. Requirement 4 carries over from it.

## Context
Iteration 04 was accepted (`iter-04`). I2C_DIRECT is in place, and the mock interprets it against `MockI2cDevice`s.

This iteration is **roadmap item 05** (SPEC §6: "SPI, with frame limits enforced. **Mock-only on the current bench**"). It covers the SPI command (datasheet pp.17–18). SPI_MODE and the SCK divisor already exist from iteration 01 (`build_spi_mode`, `spi_divisor`, p.10, D-005), and they don't change.

SPI frames have no length byte. Framing follows **D-007**: the helper sends each frame in one `write()` call, and the mock treats the bytes from the command byte to the end of that `write()` call as one frame.

**Page numbers** below are the datasheet's printed pages (the `N/23` footer).

## Goal
`usb_iss_app.iss` can build an SPI frame, refuse one that breaks the 63-byte limit, send it, and parse the reply. In the SPI modes, the mock passes each frame's data to a test-defined SPI device and returns what the device shifts back. There is no hardware run.

## Requirements

### 1. Constants (p.17)
- `SPI_IO = 0x61` (p.17: "SPI command (0x61)").
  - This is the same value as the I2C_H_100KHZ+SERIAL mode byte (p.9), but that byte only ever appears inside a `5A 02` frame, so the two never meet at the head of the buffer.
  - Say so in a comment.
- `SPI_FRAME_MAX = 63` (p.17: "The maximum frame length including the command is 63 bytes").
- `SPI_DATA_MAX = 62` (`SPI_FRAME_MAX - 1`).
- Cite the page on each.

### 2. Builder, parser and helper (p.17)
- `build_spi_io(data: bytes) -> bytes` returns `61` followed by `data`. It raises `ValueError` unless 1 ≤ len(data) ≤ 62.
  - Lower bound: the p.17 format always has `TxData1`, and an empty frame has no meaning (compare D-006).
- `parse_spi_response(resp: bytes, n: int) -> bytes`. Here `n` is the number of data bytes sent. It handles each reply as follows:
  - empty → `IssTimeout`;
  - first byte `00` → `IssNack(None, "SPI")`, whose message reads `"SPI NACK"`. p.17 does not say how many bytes follow a NACK, so the parser ignores them;
  - first byte `FF` with fewer than `n` bytes after it → `IssTimeout`;
  - first byte `FF` → returns `resp[1:1 + n]`;
  - any other first byte → `IssProtocolError`.
- `spi_io(t, data) -> bytes`:
  - builds the frame and sends it in **one** `write()` call (p.17: "All bytes should be sent to the USB-ISS in one sequence"; D-007);
  - reads `1 + len(data)` bytes with **one** `read()` call. p.17 says the device "always returns the same number of bytes as you send";
  - parses the reply and returns the `len(data)` received bytes (`RxData1`…`RxData n`);
  - uses the transport's default 500 ms timeout, as for the I2C commands (pp.11–14).

### 3. Mock: SPI (SPEC §3, "the mock"; p.17; D-007)
- **Device model.** Add `MockSpiDevice` to `mock.py`. It is a test-defined SPI slave with one method, `transfer(self, data: bytes) -> bytes`, which returns exactly `len(data)` bytes. Byte i of the result is what the device shifts out while it receives byte i.
  - Subclasses override `transfer`.
  - The base class returns `len(data)` × `FF`.
- **Wiring.** Give `MockTransport` a `spi_device: MockSpiDevice | None = None` attribute.
  - With no device, the mock returns `len(data)` × `FF`.
  - ASSUMPTION: SDI floats with nothing attached, and the mock picks `FF`, as for the empty I2C bus. This can't be checked on this bench.
- **Chip select.** One SPI frame is one CE-low period, so it makes exactly one `transfer()` call carrying all of the frame's data bytes.
  - ASSUMPTION: p.17 does not say so, but its 23K256 examples need it. The command, address and data travel in one frame.
- **Framing (D-007).** When `0x61` is at the head of the buffer, the frame is everything from it to the end of the bytes received in that `write()` call. This holds in **every** mode. The mock never waits for a later `write()`.
- **In the SPI modes** (`0x90`–`0x93`):
  - frames of 2 to 63 bytes → `FF` followed by `transfer(data)`;
  - `61` alone → a single `FF`, and `transfer` is not called. ASSUMPTION: one byte sent, one byte back (p.17);
  - frames longer than 63 bytes → a single `00`, and `transfer` is not called. ASSUMPTION: the datasheet doesn't say what the device does; the builder refuses these frames anyway.
- **Other modes** (IO_MODE, IO_MODE+SERIAL, the I2C modes and I2C+SERIAL): consume the frame, record it in `unhandled`, and send no reply.
  - ASSUMPTION: untested. This bench must not send `61` outside a NEXT that asks for it.
  - Comment that iterations 03 and 04 found IO_MODE answering I2C_TEST and I2C_DIRECT with a single `00`, and that SPI has not been tried.
- **Tests** (new `tests/test_spi.py`, through `spi_io` unless raw `write()` is noted). Put a small 23K256 model in the test file, as a `MockSpiDevice` subclass, not in `mock.py`:
  - 32 KiB of memory;
  - a status register that starts at `00`;
  - command `01` writes the status register;
  - `02 aH aL data…` writes at the address, auto-incrementing;
  - `03 aH aL x…` returns one memory byte for each `x`, from the address on;
  - the model returns `FF` in the command and address positions, and ignores byte mode.

### 4. Builder and parser tests
- Exact bytes for the datasheet examples (pp.17–18), built with `build_spi_io`:
  - `61 01 41` (write status register, sequential mode);
  - `61 02 00 00 12 34 56 78` (write 4 bytes at `0x0000`);
  - `61 03 00 00 FF FF FF FF` (read 4 bytes; the four dummy bytes are "any", and the test uses `FF`).
- Limits: 62 data bytes are accepted (a 63-byte frame); 63 data bytes and empty data are refused.
- Parser:
  - `FF 12 34` with n=2 → `12 34`;
  - `00` and `00 xx xx` with n=2 → `IssNack`, with `reason is None` and the message `"SPI NACK"`;
  - empty → `IssTimeout`;
  - `FF 12` with n=2 → `IssTimeout`;
  - `7F 00 00` with n=2 → `IssProtocolError`.
- Helper: one `write()` per frame, and one `read(1 + n)`. Use a recording transport like `_Short` in `test_i2c_direct.py`, and record the `read` sizes too.

### 5. Mock tests (requirement 3)
- **The p.17–18 sequence** against the 23K256 model, in `SPI_MODE` phase 0 at 500 kHz (`build_spi_mode(0, 500_000)`):
  - WRSR returns 2 bytes, and the model's status is `0x41`;
  - WRITE returns 6 bytes;
  - READ returns 7 bytes, and the last 4 are `12 34 56 78`.
- **One frame, one call:** a recording `MockSpiDevice` sees exactly `[02 00 00 12 34 56 78]` after that WRITE.
- **No device:** `spi_io(m, B("01 02 03"))` → `FF FF FF`.
- **Raw frames:**
  - `61` + 62 bytes → `FF` + 62 bytes, one `transfer`;
  - `61` + 63 bytes → a single `00`, and no `transfer`;
  - `61` alone → `FF`, and no `transfer`.
- **Command bytes inside data:** `spi_io(m, B("5A 01"))` passes `5A 01` to the device. There is no ISS_VERSION reply, and `unhandled` stays empty.
- **All four phases** (`0x90`–`0x93`) carry SPI frames.
- **Outside SPI mode** (I2C_S_100KHZ, IO_MODE, IO_MODE+SERIAL, I2C+SERIAL):
  - `spi_io` raises `IssTimeout`;
  - the frame is in `unhandled`;
  - a following `version()` answers the unchanged mode;
  - the device was not called.
- **I2C+SERIAL is still settable:** `set_mode(m, build_i2c_serial(I2C_H_100KHZ, 9600))` still works, so its `5A 02 61 …` frame is not taken for SPI. If an existing test already covers this exact frame, cite it in the report instead of adding a new one.

### 6. Carry-over: two I2C_DIRECT mock tests (review 04, issues 1 and 2)
Add these tests to `tests/test_i2c_direct.py`. Don't change the existing tests.
- **High byte first.** Device at `0xA0`, `size=0x10000`, `addr_bytes=2`. `i2c_direct(m, 1, direct_write(B("A0 01 02 AB")), 3)` gives `mem[0x0102] == 0xAB` and `mem[0x0201] == 0x00`.
- **STOP ends the transaction.** Device at `0x40`, `addr_bytes=0`. `i2c_direct(m, 1, direct_write(B("40")), 3, direct_write(B("40 77")), 3)` returns `b""`, and `mem[0:2] == 00 00`: after the STOP, the second WRITE has no addressed device, so its bytes are discarded.

Each test must fail against the matching mutant from review 04. The first fails if the pointer is built little-endian; the second fails if STOP does nothing. Check this yourself, and revert the code afterwards.

## Constraints / out of scope
- **No hardware run this iteration.** Do not run `--hw`. See below.
- No GUI. No change to `build_spi_mode` or `spi_divisor`.
- Do not edit SPEC, DECISIONS, HARDWARE, NEXT, the role files, the templates, LOG or CHANGES.
- No new dependencies.
- The iteration 00–04 tests stay unchanged, except for the additions in requirement 6.

## Hardware tests
**none.**
- SPEC §6 item 05 and CP-01 make SPI mock-only on this bench.
- In SPI mode, I/O1 becomes the CE output (p.3). HARDWARE.md says the GY module's TX drives I/O1, and "Never configure I/O1 as an output".
- A hardware SPI test needs a bench change that Chris approves. This iteration doesn't ask for one.
- No `61` byte is sent to the device in any mode.

## Acceptance criteria
- [ ] `.venv/bin/python scripts/run_tests.py --iter 05 --tag build` exits 0. The new tests cover requirements 1–6, including the three pp.17–18 example frames and every limit at the boundary and one past it.
- [ ] The final logged run's header shows the tested commit as `(clean)`.
- [ ] `docs/iterations/05/logs/` holds no hardware log.
- [ ] The iteration 00–04 tests pass and are unchanged, apart from the requirement 6 additions.
- [ ] The report says whether each requirement 6 test failed against its mutant.

## Report back
- Anything on pp.17–18 you found ambiguous. Note it; don't test it on hardware. For example:
  - when the device sends a NACK, and how many bytes follow it;
  - whether CE stays low across the whole frame;
  - what a frame of `61` alone, or one over 63 bytes, gets back;
  - what `61` does outside SPI mode.
- Whether any existing test already covers the I2C+SERIAL `5A 02 61 …` frame (requirement 5).
