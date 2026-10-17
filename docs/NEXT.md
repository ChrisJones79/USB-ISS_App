# NEXT — Iteration 02 (fix cycle 0)

Recommended model/effort: Sonnet 5.5, medium.
Author: revclaude. Read `docs/iterations/01/review.md` first; requirement 6 carries over from it.

## Context
Iteration 01 was accepted (`iter-01`). ISS_MODE, IO_TYPE, the divisor calculators, NACK parsing and the mock's ISS_MODE framing are in place. This iteration adds the **SERIAL_IO** command and the three **I/O commands** SETPINS, GETPINS and GETAD, with the serial buffer limits enforced (SPEC §6 item 02, SPEC F3; datasheet pp.19–20).

## Goal
`usb_iss_app.iss` can build and parse SERIAL_IO, SETPINS, GETPINS and GETAD, and refuses frames that break the datasheet limits. The mock emulates all four commands, including the pin state each mode implies. On hardware, a safe input-only sequence passes and records the raw GETPINS, SETPINS and GETAD responses.

## Requirements

### 1. Command constants and limits (datasheet pp.19–20)
- `SERIAL_IO = 0x62`, `SETPINS = 0x63`, `GETPINS = 0x64`, `GETAD = 0x65`.
- `SERIAL_TX_MAX = 30` and `SERIAL_RX_MAX = 62`: the transmit and receive buffer sizes (p.19).

### 2. SERIAL_IO (datasheet p.19)
- `build_serial_io(data: bytes = b"") -> bytes` returns `62` followed by `data`.
  - `ValueError` if `len(data) > 30`.
  - An empty `data` is valid: it is the receive poll (p.19, last paragraph).
- `parse_serial_io_header(resp) -> (ack: bool, tx_count: int, rx_count: int)` reads the first 3 response bytes:
  - fewer than 3 bytes → `IssTimeout`;
  - first byte `FF` → `ack=True`; `00` → `ack=False`; any other value → `IssProtocolError`;
  - `tx_count > 30` or `rx_count > 62` → `IssProtocolError`.
- `serial_io(transport, data=b"") -> SerialIoResult(ack, tx_count, rx)`:
  - writes the frame, reads 3 bytes, parses them, then reads `rx_count` bytes;
  - fewer than `rx_count` bytes → `IssTimeout`;
  - **a NACK does not raise.** p.19 says a NACK only means the transmit buffer has no room and the caller should retry. p.19 also says "always read these three bytes first", then RxCount bytes. So on a NACK the function still reads and returns any received bytes. Losing them would corrupt the serial stream. Add a comment that this reading of p.19 is our interpretation.
- Tests:
  - exact frame bytes for an empty poll and for a 30-byte payload;
  - 31 bytes refused;
  - every header error above;
  - an ACK with 0 and with 62 rx bytes;
  - a NACK that still carries rx bytes;
  - an rx body shorter than `rx_count` → `IssTimeout`.

### 3. SETPINS, GETPINS, GETAD (datasheet p.20)
- **SETPINS:**
  - `build_set_pins(states)` returns `63 ss`: I/O1 in bit 0 … I/O4 in bit 3. `ValueError` unless 0 ≤ states ≤ 0x0F, because bits 7:4 are "X".
  - `parse_set_pins(resp)`:
    - `FF` → OK;
    - `00` → `IssNack` with `.reason = None` and a message naming SETPINS;
    - any other byte → `IssProtocolError`;
    - empty → `IssTimeout`.
  - Extend `IssNack` to accept `reason=None`, without changing its ISS_MODE behaviour or iteration 01's tests.
  - `set_pins(transport, states)`.
- **GETPINS:**
  - `build_get_pins()` returns `64`.
  - `parse_get_pins(resp) -> int` returns `resp[0] & 0x0F`. Bits 7:4 are don't-care, so they are masked, not treated as an error. Empty → `IssTimeout`.
  - `get_pins(transport)`.
- **GETAD:**
  - `build_get_ad(channel)` returns `65 cc`. `ValueError` unless 1 ≤ channel ≤ 4.
  - `parse_get_ad(resp) -> int` decodes a big-endian 16-bit value. Fewer than 2 bytes → `IssTimeout`. A value > 1023 → `IssProtocolError`, because the converter is 10-bit (p.20).
  - `get_ad(transport, channel)`.
- Tests:
  - exact frame bytes for each builder;
  - the p.20 GETAD examples `02 A6` → 678 and `00 3D` → 61;
  - `03 FF` → 1023 accepted; `04 00` → `IssProtocolError`;
  - GETPINS `F5` → `0x05`;
  - every error path above.

### 4. Mock: I/O state (SPEC §3, "the mock"; datasheet pp.3, 7, 20)
- The mock tracks the current IO_TYPE byte. IO_MODE, IO_CHANGE, I2C_MODE and IO_MODE+SERIAL set it. I2C+SERIAL and SPI frames carry no IO_TYPE and leave it unchanged.
- At construction it is `0xAA` (all digital input). Changelog v7 (p.2) says I/O1 and I/O2 power up as inputs. Mark this as an assumption for I/O3 and I/O4.
- The mode decides which pins are general I/O (pin table, p.3):

  | Mode | General I/O pins |
  |---|---|
  | IO_MODE | 1–4 |
  | IO_MODE+SERIAL | 3, 4 |
  | I2C | 1, 2 |
  | I2C+SERIAL | none |
  | SPI | none |

  IO_TYPE bits for pins that are not general I/O are ignored.
- Test-settable inputs: `inputs` (4-bit levels seen on digital-input pins) and `adc` (four raw 0–1023 values).
- **Outputs:**
  - A general-I/O pin typed OUTPUT_LOW or OUTPUT_HIGH starts at that level whenever IO_TYPE is applied.
  - SETPINS changes the levels of output pins only (p.20) and answers `FF`.
  - Add a test-only hook to make the next SETPINS answer `00`, so `IssNack` is tested end to end through `set_pins`.
- **GETPINS** answers one byte. Bit n is the level of a general-I/O output pin, or the `inputs` level of a general-I/O digital-input pin. Every other bit is 0, which is an assumption: mark it in a comment.
- **GETAD** answers `adc[ch-1]` as 2 bytes only when the channel is 1–4 and that pin is a general-I/O analogue input. Otherwise it answers `00 00` (p.20).

### 5. Mock: SERIAL_IO (SPEC §3; datasheet p.19)
- **Framing.** SERIAL_IO has no length byte. The real device delimits it by the USB transfer. The mock treats a `62` frame as running from the `62` to the end of the `write()` call in which it arrived. Mark this as an assumption.
- **Serial modes** (0x01 and I2C+SERIAL):
  - The mock keeps a transmit buffer of at most 30 bytes.
  - If the payload fits in the free space, the bytes are accepted and the reply is `FF`. Otherwise nothing is accepted and the reply is `00`.
  - Accepted bytes drain at once into a test-visible `serial_sent`, unless a test-only `hold_serial_tx` flag is set. With the flag set they stay pending, so a test can fill the buffer and see the NACK.
  - TxCount is the number of bytes still pending.
- **Receive buffer:** at most 62 bytes, filled by a test-only `inject_serial_rx(data)`.
  - The mock drops bytes beyond 62 and logs them, because overflow behaviour is unspecified. Mark this as an assumption.
  - Every SERIAL_IO reply, ACK or NACK, carries RxCount and all buffered rx bytes, then clears the buffer.
- **Other modes:** a `62` frame is dropped and logged as unhandled, with no reply. The datasheet does not say what happens. Mark this as an assumption.
- Tests (through `serial_io`):
  - poll with nothing to receive → `(True, 0, b"")`;
  - send 30 bytes → `serial_sent` gets exactly those bytes;
  - with `hold_serial_tx`: 20 bytes, then 11 bytes → NACK, `tx_count == 20`, and the 11 bytes are not accepted;
  - inject 70 rx bytes → one poll returns exactly 62 bytes;
  - a NACK reply still carries injected rx bytes;
  - SERIAL_IO in I2C_S_100KHZ → `IssTimeout`, and the frame appears in `unhandled`;
  - a payload containing `5A 01` is sent as data and does not trigger an ISS_VERSION reply.

### 6. Carry-overs from review 01
- Issue 1: update the mock's IO_CHANGE comment. Drop the reference to "NEXT 01 req. 9" and cite the hardware result in `docs/iterations/01/logs/build-hw-20261017-003245.txt`: from I2C_S_100KHZ, IO_CHANGE returned `FF 00` and the mode stayed 0x40. Keep "assumption" for other starting modes.
- Issue 2: in `test_default_timeout_is_500ms`, require the default to be exactly `0.5` for `Transport.read` and `MockTransport.read`. Only `SerialTransport.read` may default to `None`. This is the only edit allowed to an existing test.

## Constraints / out of scope
- No I2C or SPI transfer commands (iteration 03). No GUI.
- No serial mode on hardware (see below).
- Do not edit SPEC, DECISIONS, the role files, the templates, LOG or CHANGES.
- No new dependencies.

## Hardware tests
**safe-read + mode set + SETPINS with no output pins.** No pin is ever set as an output, so SETPINS cannot drive anything (p.20: SETPINS only affects output pins). No serial mode is entered: in serial mode I/O2 becomes a driven TX pin, and nothing in this iteration needs it. Hardware SERIAL_IO waits for a NEXT that states the wiring.

Sequence: one ordered test or several. A fixture or `finally` must always run the restore step.
1. `5A 02 00 AA` (IO_MODE, all four pins digital input) → `FF 00`; ISS_VERSION mode == 0x00.
   - GETPINS (`64`): log the raw response byte and assert exactly 1 byte. Pins are floating, so don't assert the value.
2. SETPINS `63 0F`, sent as raw bytes:
   - log the raw response;
   - assert it is exactly one byte, `FF` or `00`. Which one is the finding: the datasheet does not say how SETPINS answers when no pin is an output.
   - then GETPINS again; log it, don't assert it.
3. GETAD channel 1 (`65 01`) while I/O1 is a digital input → assert `00 00` (p.20).
4. `5A 02 00 FF` (IO_MODE, all four pins analogue input) → `FF 00`; mode == 0x00.
   - `get_ad` on channels 1–4: log each value and assert 0 ≤ value ≤ 1023.
5. Raw `65 00` and raw `65 05` (out-of-range channels; the builder refuses them, so send them as raw bytes) → assert `00 00` for each (p.20).
6. Restore: `5A 02 40 0A` → `FF 00`; mode == 0x40.

## Acceptance criteria
- [ ] `python scripts/run_tests.py --iter 02 --tag build` exits 0. The new tests cover requirements 1–6 as listed under each requirement, including the p.20 GETAD examples, the 30/31-byte transmit boundary, the 62-byte receive cap, and the NACK-with-rx case.
- [ ] `python scripts/run_tests.py --iter 02 --hw --tag build` passes on the real USB-ISS. The log shows:
  - both raw GETPINS bytes;
  - the raw SETPINS response;
  - the four GETAD values;
  - the out-of-range GETAD responses.
  The device is left in mode 0x40.
- [ ] The final logged runs' headers show the tested commit as `(clean)`, or list the porcelain lines.
- [ ] The iteration 00 and 01 tests still pass, unchanged apart from requirement 6, issue 2.

## Report back
- The raw SETPINS response with no output pins, and both raw GETPINS bytes, including the values of bits 7:4.
- The four GETAD values with the pins floating.
- Anything on pp.19–20 you found ambiguous. For example, whether TxCount means bytes still pending or free space. This brief reads it as pending ("characters remaining in the transmit buffer"). Note ambiguities; don't test them on hardware.
