# Decisions

Format: ID · date · status (adopted / pending Chris / pending claude1) · decision · rationale.

## D-001 · 2026-10-11 · adopted
Language and GUI stack: Python 3.12, PySide6, pyserial, pytest.
Rationale:
- Cross-platform.
- pyserial is the natural fit for the USB-ISS virtual COM port.
- pytest output can be captured directly into the iteration logs.

## D-002 · 2026-10-11 · adopted
Workflow: vsclaude builds, revclaude reviews and writes the next task, claude1 audits at checkpoints. See CLAUDE.md.

## D-003 · 2026-10-11 · adopted
Environment:
- pyenv pins Python 3.12 via a committed `.python-version` file.
- A project venv at `.venv/` (gitignored).
- Dependencies are listed in `pyproject.toml`.
- Never install into, or rely on, the system Python.

Rationale: both Claude Code instances and Chris must run identical interpreters and package versions. A shared system install hides drift.

## D-004 · 2026-10-11 · adopted
Card manifests are JSON (`card.json`). This avoids a YAML dependency, and the GUI card editor (F6) can write it using only the standard library.

## D-005 · 2026-10-16 · adopted
SPI SCK divisor rounding (clarifies SPEC §6 item 01, "SPI divisor calculators with error reporting"; datasheet p.10).
- The divisor is `ceil(6000000 / SCK) - 1`, so the actual SCK (`6000000 / (divisor + 1)`) is never above the requested SCK.
- Valid divisors are 1–255. The calculator never emits 0, because the datasheet says 0 behaves like 1. Requests above 3 MHz or below 23 437.5 Hz are refused.
- The error from the requested SCK is reported, but no error limit is applied. F2's 3% limit applies to serial baud only.
Rationale: an SPI device has a maximum clock, not a tolerance band. Rounding down in frequency can never overclock the device. Baud keeps the floor rule from SPEC §8.
Proposed by revclaude while writing NEXT 01. Ratified by claude1 on 2026-10-17. The formula reproduces all three p.10 examples (3 MHz gives 1, 500 kHz gives 11, 23.4375 kHz gives 255).

## D-006 · 2026-10-17 · pending claude1
I2C data-byte limits and example count bytes (clarifies SPEC §6 item 03, "with frame limits enforced"; datasheet pp.10–13).
- Each count of data bytes runs from 1 up to the limit. A count of 0 is refused, because the datasheet gives it no meaning.
  - I2C_AD1: up to 60 bytes written, and up to 60 read (p.12).
  - I2C_AD2: up to 59 bytes written (p.13: "so as not to overflow the USB-ISS's 64 byte internal buffer"), and up to 64 read (p.13).
  - I2C_AD0: the datasheet gives no limit. Use 60 for both writes and reads, as for I2C_AD1. A full write frame is then 63 bytes, inside the 64-byte buffer.
  - I2C_SGL always moves exactly one byte.
- The count byte equals the number of data bytes that follow (on a write) or are requested (on a read). Two examples contradict their own text, and the text wins:
  - p.11, I2C_AD0 write: the example shows count `0x02` but sends four data bytes, and the text says "sending four bytes". The correct count is `0x04`.
  - p.13, I2C_AD2 write: the example shows count `0x34` but describes 32 data bytes in a "37 byte sequence". The correct count is `0x20`.
Rationale: never send more than the documented buffer holds. Where the datasheet is silent, use the closest documented limit. In both faulty examples, the text and the frame length agree with each other; only the count byte disagrees.
Proposed by revclaude while writing NEXT 03.
