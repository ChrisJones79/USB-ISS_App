# NEXT — Iteration 01 (fix cycle 0)

Recommended model/effort: Sonnet 5.5, medium.
Author: revclaude. Read `docs/iterations/00/review.md` first; requirements 6–8 carry over from it.

## Context
Iteration 00 was accepted (`iter-00`). Transport, mock, runner, ISS_VERSION and GET_SER_NUM are in place. This iteration adds **ISS_MODE**: every mode frame, the IO_TYPE builder, the baud and SPI divisor calculators, mode-byte decoding, and NACK parsing (SPEC §6 item 01, SPEC F2, SPEC §8).

## Goal
`usb_iss_app.iss` can build every ISS_MODE frame in the datasheet, compute and validate baud and SPI divisors, and parse the 2-byte mode response including NACK reasons. The mock emulates ISS_MODE with correct frame lengths. On hardware, a safe input-only mode sequence passes and records how IO_CHANGE responds.

## Requirements

### 1. Mode values and decoding (datasheet p.6)
- Constants for every operating mode:
  - IO_MODE 0x00, IO_CHANGE 0x10;
  - I2C_S_20KHZ 0x20, I2C_S_50KHZ 0x30, I2C_S_100KHZ 0x40, I2C_S_400KHZ 0x50;
  - I2C_H_100KHZ 0x60, I2C_H_400KHZ 0x70, I2C_H_1000KHZ 0x80;
  - SPI_MODE 0x90 with phase 0–3 (0x90–0x93, p.10);
  - SERIAL 0x01, combinable with IO_MODE (p.8) and with all 7 I2C modes (p.9). For example, 0x61 is I2C_H_100KHZ + SERIAL.
- `decode_mode(b: int) -> str` names the mode byte reported by ISS_VERSION, for example `"I2C_S_100KHZ"`, `"I2C_H_100KHZ+SERIAL"`, `"IO_MODE+SERIAL"` or `"SPI_MODE phase 2"`.
  - An unknown byte returns `"UNKNOWN(0xNN)"` and does not raise, because ISS_VERSION can report state we have not seen yet.

### 2. IO_TYPE builder (datasheet p.7)
- `IoType` enum: OUTPUT_LOW 0b00, OUTPUT_HIGH 0b01, DIGITAL_INPUT 0b10, ANALOGUE_INPUT 0b11.
- `io_type(io1, io2, io3, io4) -> int`, with pin 1 in bits 1:0 and pin 4 in bits 7:6.
- Test against the datasheet examples: 0x01 (I/O1 high, the rest low) and 0xB4.

### 3. Divisor calculators (SPEC F2, SPEC §8, datasheet pp.8 and 10; D-005)
- `baud_divisor(bps) -> (divisor, actual_bps, error_pct)`:
  - `divisor = floor(48000000 / (16 * bps)) - 1`;
  - `actual = 48000000 / (16 * (divisor + 1))`;
  - `error_pct = (actual - bps) / bps * 100`.
  - Follow SPEC §8: the printed formula on p.8 is wrong. Do not implement `16+baud`.
- The serial frame builders raise `ValueError` if |error| > 3 % or if the divisor is outside 0–65535.
- `spi_divisor(sck_hz) -> (divisor, actual_hz, error_pct)` follows D-005 (pending claude1): `ceil(6000000 / sck) - 1`, valid range 1–255, `ValueError` outside it.
- Tests:
  - every row of the p.8 baud table, with 2400 expected as **0x04 0xE1** (SPEC §8);
  - 115200 → divisor 25, actual 115385 (rounded), error +0.16 %;
  - 460800 refused;
  - SPI: 3 MHz → 1, 500 kHz → 11, 23437.5 Hz → 255; 4 MHz and 20 kHz refused.

### 4. ISS_MODE frames and response (datasheet pp.6–10)
Pure builders. The expected bytes are the datasheet examples:

| Builder | Frame | Datasheet example |
|---|---|---|
| `build_io_mode(io_type)` | `5A 02 00 tt` | `5A 02 00 B4` (p.7) |
| `build_io_change(io_type)` | `5A 02 10 tt` | `5A 02 10 B4` (p.7) |
| `build_io_serial(bps, io_type)` | `5A 02 01 hi lo tt` | 19200, 0xB0 → `5A 02 01 00 9B B0` (p.8) |
| `build_i2c_mode(mode, io_type)` | `5A 02 mm tt` | `5A 02 60 04` (p.9) |
| `build_i2c_serial(mode, bps)` | `5A 02 (mm\|01) hi lo` | I2C_H_100KHZ, 19200 → `5A 02 61 00 9B` (p.9) |
| `build_spi_mode(phase, sck_hz)` | `5A 02 (90\|phase) dd` | 3 MHz → `5A 02 90 01` (p.10) |

- Builders reject arguments that are not I2C modes or phases outside 0–3 with `ValueError`.
- `parse_mode_response(resp)` (p.6):
  - `FF 00` → OK;
  - `FF xx` with xx ≠ 0 → `IssProtocolError`;
  - `00 rr` with rr ∈ {05 Unknown command, 06 Internal Error 1, 07 Internal Error 2} → new `IssNack(IssError)` carrying `.reason` and a readable name;
  - `00` followed by any other byte, or any other first byte → `IssProtocolError`;
  - fewer than 2 bytes → `IssTimeout`.
- `set_mode(transport, frame)` writes the frame, reads 2 bytes and parses them.
- Each unit test asserts the exact frame bytes.

### 5. Mock ISS_MODE (SPEC §3, "the mock"; fixes review 00 issue 1)
- The mock frames `5A 02 <mode> …` by the mode byte's length:
  - IO_MODE, IO_CHANGE, I2C and SPI: 4 bytes;
  - I2C+SERIAL: 5 bytes;
  - IO_MODE+SERIAL: 6 bytes.
- It waits for the whole frame before acting. Bytes inside a frame are never interpreted as commands. Test: `5A 02 01 5A 01 B0` (a valid IO+SERIAL frame with divisor 0x5A01) yields exactly `FF 00` and no version reply.
- A valid frame → `FF 00`, and the mock's `mode` becomes the frame's mode byte, so ISS_VERSION reports it.
  - IO_CHANGE leaves `mode` unchanged. That is an assumption until requirement 9 reports hardware behaviour. Mark it in a comment.
- An unknown mode byte → `00 05` after consuming `5A 02 <mode>`.
  - This framing is an assumption, not verified on hardware. Mark it in a comment.
- Add a test-only hook to force the next mode response to NACK with a given reason (06, 07), so `IssNack` is tested end to end through `set_mode`.
- Unknown `5A xx` sub-commands and non-`5A` bytes behave as in iteration 00: dropped, logged, no reply.

### 6. Default timeout test (review 00 issue 2)
Add a test that fails if the default read timeout is not 0.5 s (datasheet p.11).

### 7. SerialTransport timeout (review 00 issue 3)
The `timeout` passed to `SerialTransport(...)` must take effect when `read()` is called without a timeout. Keep 500 ms as the default.

### 8. Runner dirty flag (review 00 issue 4)
- Exclude files under `docs/iterations/*/logs/` when computing the dirty flag.
- When the tree is still dirty, write the `git status --porcelain` lines into the header.
- Commit your code before the final logged runs, so the header names the commit that was tested.

## Constraints / out of scope
- No SERIAL_IO, I2C, SPI transfer or I/O commands (iterations 02–03). No GUI.
- Do not edit SPEC, DECISIONS, the role files, the templates, LOG or CHANGES.
- No new dependencies.

## Hardware tests
**safe-read + mode set, inputs only.** No outputs are driven and no serial or SPI mode is entered. In I2C mode, I/O1 and I/O2 stay general I/O (pin table p.3). Every IO_TYPE below sets them to inputs. Do **not** use the p.9 example `04`, which drives I/O2 high.

Sequence. Each step is one hw test or one ordered test; a fixture or `finally` must always run the restore step:
1. `5A 02 40 0A` (I2C_S_100KHZ, I/O1 and I/O2 digital input) → `FF 00`; ISS_VERSION mode == 0x40.
2. `5A 02 10 0F` (IO_CHANGE, I/O1 and I/O2 analogue input) → log the raw response bytes, then assert `FF 00` (pp.6–7). Log the ISS_VERSION mode byte afterwards, but do not assert it.
3. `5A 02 00 AA` (IO_MODE, all four pins digital input) → `FF 00`; mode == 0x00.
4. Restore: `5A 02 40 0A` → `FF 00`; mode == 0x40. This is the power-up state (p.6, changelog v7).

## Acceptance criteria
- [ ] `python scripts/run_tests.py --iter 01 --tag build` exits 0. The new tests cover requirements 1–7, including every datasheet example frame listed above, the full p.8 baud table with the corrected 2400 row, all three NACK reasons through `set_mode` on the mock, `FF xx` / unknown-reason / short-response errors, and the `5A 02 01 5A 01 B0` framing test.
- [ ] `python scripts/run_tests.py --iter 01 --hw --tag build` passes on the real USB-ISS. The log shows the raw IO_CHANGE response and the mode byte after each step. The device is left in mode 0x40.
- [ ] The final logged runs' headers show the tested commit as `(clean)`, or list the porcelain lines.
- [ ] The iteration 00 tests still pass unchanged.

## Report back
- The raw IO_CHANGE response, and the mode byte ISS_VERSION reports after IO_CHANGE. If the mode byte differs from the mock's assumption, update the mock to match the hardware and say so.
- Anything in pp.6–10 you found ambiguous. For example: which IO_TYPE bits the firmware honours in I2C and IO+SERIAL modes. Don't test this on hardware; just note it.
