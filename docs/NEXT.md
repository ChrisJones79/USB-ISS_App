# NEXT — Iteration 00 (fix cycle 0)

Recommended model/effort: Sonnet 5.5, medium.
Author: claude1. This one task only; revclaude writes every later NEXT.md.

## Context
The repo has process scaffolding but no code. SPEC v0.1 and D-001, D-003 and D-004 are adopted. This iteration lays the foundation that every later iteration builds on:
- the package layout;
- the logging test runner;
- the transport abstraction with a mock;
- the first two protocol commands.

## Goal
Running one command, mock or hardware, executes the test suite and writes a timestamped raw log to `docs/iterations/00/logs/`. In that suite, ISS_VERSION and GET_SER_NUM pass against the mock and against the real USB-ISS.

## Requirements

### 1. Environment (D-003)
- Add `.python-version` pinned to a 3.12.x release.
- Add `pyproject.toml`:
  - src layout, package `usb_iss_app` under `src/`;
  - runtime dependency `pyserial`;
  - dev dependency `pytest`.
  - Do **not** add PySide6 yet; it arrives in iteration 04.
- Add `.gitignore` covering at least `.venv/`, `.env`, `__pycache__/` and `*.egg-info/`.
- Add `.env.example` containing `USB_ISS_PORT=`.
- Add a "Setup" section to `readme.md` with exact commands: pyenv install/local, create `.venv`, `pip install -e .[dev]`, create `.env`.

### 2. Test runner (CLAUDE.md, Workflow section)
- Add `scripts/run_tests.py --iter NN [--hw] [--tag build|review]`.
- It runs pytest and writes, to `docs/iterations/NN/logs/`:
  - the full pytest stdout/stderr;
  - a JUnit XML file.
- File names follow `<tag>-<mock|hw>-<YYYYMMDD-HHMMSS>.{txt,xml}`. The runner never overwrites an existing file.
- The `.txt` log starts with a header giving:
  - the command line;
  - the git commit, plus a dirty flag;
  - the Python and package versions;
  - for hw runs, the port;
  - the UTC start time.
- It ends with the exit code.
- The runner's exit code equals pytest's.
- Without `--hw`, tests marked `hw` are skipped. With `--hw`, they run.
- With `--hw`, the runner refuses to start if `USB_ISS_PORT` is unset.

### 3. Transport (SPEC §3, layer 1)
- `Transport` interface with three methods:
  - `write(data: bytes)`;
  - `read(n: int, timeout: float) -> bytes`, which may return fewer than `n` bytes on timeout;
  - `close()`.
- `SerialTransport` (pyserial):
  - the port comes from `USB_ISS_PORT`, read from the environment or from `.env`;
  - parse `.env` with a small standard-library parser, with no new dependency;
  - set no baud rate expectations (USB-ISS datasheet p.4: baud has no effect).
- The default read timeout is **500 ms** (datasheet p.11).

### 4. Mock USB-ISS (SPEC §3)
- `MockTransport` emulates the USB-ISS byte-for-byte for `5A 01` and `5A 03` (datasheet p.5).
- Its firmware version, current mode and serial number are configurable.
  - Defaults: version 0x09, mode 0x40, serial `"00000001"`.
- For any request it does not implement, the mock returns **no bytes**, so the caller times out.
  - It must not invent responses the datasheet doesn't define.
  - It logs the unhandled request.

### 5. Protocol (SPEC §3, layer 2; datasheet p.5)
- In `usb_iss_app.iss`, add a pure request builder and response parser for each command:
  - `ISS_VERSION`: returns `(module_id, firmware, mode)`.
  - `GET_SER_NUM`: returns an 8-character `str`.
- Add thin `version(transport)` and `serial_number(transport)` helpers that write, read and parse.
- Validation raises typed exceptions:
  - fewer bytes than expected → `IssTimeout`;
  - module_id ≠ 7, or any serial byte outside 0x30–0x39 → `IssProtocolError`.
- Each command cites its datasheet page in a comment (BUILDER.md).

## Constraints / out of scope
- No ISS_MODE or other commands; no GUI; no cards.
- Do not decode the mode byte into names yet (iteration 01). Expose it as an int.
- Do not edit SPEC, DECISIONS, the role files, the templates, LOG or CHANGES.

## Hardware tests
safe-read: `5A 01` and `5A 03` only. Do not change the mode.

## Acceptance criteria
- [ ] `python scripts/run_tests.py --iter 00 --tag build` exits 0 and writes a new `.txt` and `.xml` pair. The header and exit-code footer are present.
- [ ] Mock tests cover all of the following:
  - version and serial-number parsing on valid responses;
  - `IssTimeout` on a short response;
  - `IssProtocolError` on module_id ≠ 7;
  - `IssProtocolError` on a non-digit serial byte;
  - the mock returning nothing for an unhandled request.
- [ ] Each protocol unit test asserts the **exact request bytes** sent: `5A 01` and `5A 03`.
- [ ] A second runner invocation in the same second does not overwrite the first log. There must be a test for this.
- [ ] `--hw` without `USB_ISS_PORT` exits non-zero with a clear message and runs no tests.
- [ ] `python scripts/run_tests.py --iter 00 --hw --tag build` passes on the real USB-ISS. It asserts:
  - module_id == 7;
  - the serial number is 8 ASCII digits;
  - the firmware value is reported in the log.
- [ ] A fresh clone, following the readme Setup section exactly, reaches a passing mock run.

## Report back
- The firmware version and mode byte read from hardware. The serial number is fine to include.
- Measured round-trip time of `5A 01` on hardware (median of 20).
- Anything in the datasheet you found ambiguous.