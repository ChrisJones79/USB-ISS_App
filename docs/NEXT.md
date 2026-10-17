# NEXT — Iteration 03 (fix cycle 0)

Recommended model/effort: Sonnet 5.5, medium.
Author: revclaude. Read `docs/iterations/02/review.md` (fix cycle 1) first; requirement 6 carries over from it.

## Context
Iteration 02 was accepted (`iter-02`). SERIAL_IO, SETPINS, GETPINS and GETAD are in place, and the mock follows the device for the two hardware findings (SPEC §8).

This iteration is **the first half of roadmap item 03** (SPEC §6: "I2C and SPI commands"). It covers the register-style I2C commands **I2C_SGL, I2C_AD0, I2C_AD1, I2C_AD2** and **I2C_TEST** (datasheet pp.10–15), with the byte limits enforced. I2C_DIRECT and SPI are iteration 04. From now on, roadmap items 04–09 run one iteration number later than their labels.

The byte limits follow **D-006** (pending claude1). D-006 also corrects two datasheet examples whose count byte contradicts their own text.

## Goal
`usb_iss_app.iss` can build and parse the five I2C commands and refuses frames that break the limits. The mock emulates an I2C bus with test-defined devices. On hardware, I2C_TEST and one read on the empty bus record what the real device answers.

## Requirements

### 1. Constants and limits (datasheet pp.10–13; D-006)
- `I2C_SGL = 0x53`, `I2C_AD0 = 0x54`, `I2C_AD1 = 0x55`, `I2C_AD2 = 0x56`, `I2C_TEST = 0x58`.
- `I2C_AD0_MAX = 60`, `I2C_AD1_MAX = 60` (reads and writes), `I2C_AD2_WRITE_MAX = 59`, `I2C_AD2_READ_MAX = 64`. Cite the page or D-006 in a comment on each.

### 2. Builders (datasheet pp.10–13, 15)
**Addresses** take the datasheet's 8-bit form: the even write address, as in its examples (`0x40`, `0xA0`, `0xE0`).
- Every builder raises `ValueError` unless the address is even and 0x00–0xFE.
- Read builders send `addr | 1` (p.11: "add 1 to the device address").

| Function | Frame | Other checks (`ValueError`) |
|---|---|---|
| `build_i2c_sgl_write(addr, value)` | `53 addr value` | value 0–255 |
| `build_i2c_sgl_read(addr)` | `53 addr+1` | |
| `build_i2c_ad0_write(addr, data)` | `54 addr n data…` | 1 ≤ n ≤ 60 |
| `build_i2c_ad0_read(addr, n)` | `54 addr+1 n` | 1 ≤ n ≤ 60 |
| `build_i2c_ad1_write(addr, reg, data)` | `55 addr reg n data…` | reg 0–255; 1 ≤ n ≤ 60 |
| `build_i2c_ad1_read(addr, reg, n)` | `55 addr+1 reg n` | reg 0–255; 1 ≤ n ≤ 60 |
| `build_i2c_ad2_write(addr, reg, data)` | `56 addr regH regL n data…` | reg 0–0xFFFF, high byte first (p.13); 1 ≤ n ≤ 59 |
| `build_i2c_ad2_read(addr, reg, n)` | `56 addr+1 regH regL n` | reg 0–0xFFFF; 1 ≤ n ≤ 64 |
| `build_i2c_test(addr)` | `58 addr` | |

`n` in a write frame is `len(data)`.

### 3. Parsers and helpers (datasheet pp.10–13, 15)
- `parse_i2c_write(resp, command: str) -> None`. Applies to every write (SGL, AD0, AD1, AD2): "0x00 if the write command failed and non-zero if the write succeeded".
  - empty → `IssTimeout`;
  - `00` → `IssNack(None, command)`, where the message names the command, e.g. `"I2C_AD1 NACK"`;
  - **any** non-zero byte → success. Unlike SETPINS, it need not be `FF`.
  - Update the `IssNack` docstring to cover I2C writes.
- `parse_i2c_read(resp, n) -> bytes`: fewer than `n` bytes → `IssTimeout`; otherwise the first `n` bytes.
  - Add a comment: the datasheet defines no status byte for reads, so a read from an absent device can't be detected from the response.
- `parse_i2c_test(resp) -> bool`: empty → `IssTimeout`; `00` → `False`; any other byte → `True` (p.15).
- Helpers, each writing one frame:
  - writes read 1 byte: `i2c_sgl_write`, `i2c_ad0_write`, `i2c_ad1_write`, `i2c_ad2_write`;
  - reads read `n` bytes: `i2c_sgl_read(t, addr) -> int`, `i2c_ad0_read`, `i2c_ad1_read`, `i2c_ad2_read`;
  - `i2c_test(t, addr) -> bool`.
  - All use the transport's default 500 ms timeout (pp.10–13).

### 4. Builder and parser tests
- Exact bytes for every datasheet example:
  - `53 40 00` (p.10) and `53 41` (p.11);
  - `54 F1 02` (p.11);
  - **`54 30 04 12 34 56 78`** (p.11, count corrected per D-006; say so in a comment);
  - `55 E0 00 01 nn` (p.12) and `55 C1 02 02` (p.12);
  - **`56 A0 00 00 20` + 32 data bytes = 37 bytes** (p.13, count corrected per D-006; say so in a comment);
  - `56 A1 00 00 03` (p.13);
  - `58 A0` (p.15).
- Every limit at the boundary and one past it:
  - AD0 write and read: 60 / 61;
  - AD1 write and read: 60 / 61;
  - AD2 write: 59 / 60. AD2 read: 64 / 65.
- Also refused:
  - a count of 0 (empty data, and `n = 0`);
  - an odd address, 0xFF, 0x100 and −2;
  - AD1 reg 256; AD2 reg 0x10000;
  - SGL value 256.
- Parsers: write `00` → `IssNack` with the command named; `01` and `FF` → success; empty → `IssTimeout`. Short read → `IssTimeout`. Test parser: `00`, `01`, `FF` and empty.

### 5. Mock: I2C bus (SPEC §3, "the mock"; datasheet pp.3, 10–15)
- **Device model.** Add a small `MockI2cDevice(size=256)` with a `mem` bytearray and a `pointer`. Writes store at the pointer, reads return from it, and both post-increment with wrap-around at `size`.
  - I2C_SGL write and read act on one byte at the pointer, like a PCF8574's latch.
  - I2C_AD0 reads and writes at the pointer. p.11 describes I2C_AD1 or I2C_AD2 for the first read and then I2C_AD0 for later reads.
  - I2C_AD1 sets the pointer to `reg` first; I2C_AD2 sets it to the 16-bit `reg`.
- `MockTransport.i2c_devices: dict[int, MockI2cDevice]` is keyed by the even 8-bit address and is **empty by default**, like the bench bus.
- **Modes.** The commands work in the I2C modes and in I2C+SERIAL.
- **Framing.** The mock waits for the whole frame, as it does for ISS_MODE. Its bytes are never treated as commands. Frame lengths:
  - SGL: 3 bytes for an even address, 2 for an odd one;
  - AD0: 3 + n for a write, 3 for a read;
  - AD1: 4 + n for a write, 4 for a read;
  - AD2: 5 + n for a write, 5 for a read;
  - TEST: 2.
- **Replies:**
  - write to a present device → `FF`. ASSUMPTION: the datasheet only says "non-zero".
  - write to an absent address → `00`.
  - read from a present device → `n` bytes from `mem`.
  - read from an absent address → `n` bytes of `FF`. ASSUMPTION: the 4.7k pull-ups (p.3) hold SDA high. Hardware step 3 checks this. **If the device answers differently, make the mock match what it did, cite the log in the comment, and report it.**
  - I2C_TEST → `FF` if present (ASSUMPTION: "non-zero"), `00` if absent.
  - a mock-side count above the limits is not checked; the builders refuse those frames.
- **Other modes** (IO_MODE, IO_MODE+SERIAL, SPI): consume the whole frame by the same length rules, record it in `unhandled`, and send no reply. ASSUMPTION: hardware step 4 records the real behaviour for I2C_TEST. Report it, but don't change the mock for it in this iteration.
- Tests, through the helpers:
  - AD1 write then AD1 read returns the same bytes at the same register;
  - AD2 at register `0x0100` on a device with `size=0x10000`;
  - AD1 read of 2 bytes, then AD0 read of 2 bytes, continues at the next address;
  - SGL write then SGL read;
  - absent address: each write → `IssNack`, each read → `FF` bytes, test → `False`. Present address: test → `True`;
  - an AD1 write frame split across two `write()` calls: no reply until it is complete;
  - write data containing `5A 01` → no ISS_VERSION reply;
  - the commands work in I2C+SERIAL;
  - in IO_MODE, `i2c_test` raises `IssTimeout`, the frame is in `unhandled`, and a following `version()` still answers correctly. That proves the whole frame was consumed.

### 6. Carry-over from review 02 (fix cycle 1, issue 2)
- Add one mock test: GETAD on a pin that is not general I/O returns 0.
  - In I2C_S_100KHZ with IO_TYPE `0xAA` and all `adc` non-zero: channels 3 and 4 → 0, channels 1 and 2 → their `adc` values.
  - In IO_MODE+SERIAL: channels 1 and 2 → 0.
  - This test must fail if the `_general_pins()` check in `MockTransport._getad` is removed. Check this by trying it, then restore the code, and say in build.md that you did.
- This is a new test. Existing tests stay unchanged.

## Constraints / out of scope
- No I2C_DIRECT and no SPI command (iteration 04). No GUI.
- No I2C **write** on hardware.
- Do not edit SPEC, DECISIONS, HARDWARE, the role files, the templates, LOG or CHANGES.
- No new dependencies.
- If D-006 looks wrong to you, follow it anyway and say why in build.md.

## Hardware tests
**safe-read + one empty-bus I2C read.** `docs/HARDWARE.md`:
- SCL and SDA (I/O3 and I/O4) are **not connected**. The GY module's own SCL and SDA must never be connected in serial mode, and aren't. The board's 4.7k pull-ups (p.3) hold the bus high.
- So the only I2C traffic is an address, plus one register byte, on an empty bus. No I2C write command (SGL, AD0, AD1 or AD2 write) is sent.
- I/O1 and I/O2 stay digital inputs (IO_TYPE `0xAA`) in every mode used. I/O1 is driven by the module's TX. No serial mode is entered.

Sequence: one test or several. A fixture or `finally` must always run the restore step, as in `io_hw`.
1. `5A 02 40 AA` (I2C_S_100KHZ; I/O1 and I/O2 digital input) → `FF 00`; ISS_VERSION mode == 0x40.
2. Raw `58 A0`, then raw `58 66`. 0x66 is the MLX90640's address 0x33 in 8-bit form; that device is not on this bus. Read each with `n = 2` and log the raw response. Assert exactly 1 byte each, but **don't assert its value**. The expected answer is `00`; anything else is a finding to report.
3. Raw I2C_AD1 read `55 A1 00 01`, read with `n = 3`, and log the raw response (it may be empty). Assert nothing about it. Then ISS_VERSION: assert mode == 0x40. This shows the device still answers and no stray byte is left over.
4. `5A 02 00 AA` (IO_MODE, all digital input) → mode == 0x00. Raw `58 A0`, read with `n = 2`, and log the raw response (it may be empty). Assert nothing about it. Then ISS_VERSION: assert mode == 0x00.
5. Restore: `5A 02 40 AA` → `FF 00`; mode == 0x40.

## Acceptance criteria
- [ ] `.venv/bin/python scripts/run_tests.py --iter 03 --tag build` exits 0. The new tests cover requirements 1–6 as listed, including every datasheet example frame, every limit boundary and the D-006 corrected counts.
- [ ] `.venv/bin/python scripts/run_tests.py --iter 03 --hw --tag build` exits 0. The log shows the raw responses of steps 2, 3 and 4, and the device is left in mode 0x40.
- [ ] The final logged runs' headers show the tested commit as `(clean)`.
- [ ] The iteration 00–02 tests still pass, unchanged. Requirement 6 is an added test.

## Report back
- The raw responses from hardware steps 2–4. For step 3, say whether the mock's absent-device read matched the device, and what you changed if it didn't.
- Anything on pp.10–15 you found ambiguous. Note it; don't test it on hardware. Examples: I2C_SGL reads have no status byte; I2C_AD0 has no documented limit.
