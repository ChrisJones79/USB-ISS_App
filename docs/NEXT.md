# NEXT — Iteration 06 (fix cycle 0)

Recommended model/effort: Sonnet 5.5, high. This is the first Qt code and a new layer.
Author: revclaude. Read `docs/iterations/05/review.md` first.

## Context
Iteration 05 was accepted (`iter-05`). The protocol layer (`iss`) now covers every datasheet command, and the mock emulates each one.

This iteration is the first part of **roadmap item 06** (SPEC §6: "Minimal GUI — Features F1, F2 and F4"). revclaude has split the item, as SPEC §6 allows:
- iteration 06 (this one) covers the main window, **F1 Connect** and **F4 Raw console**;
- **F2 Mode** is the next iteration.

The GUI is layer 4 (SPEC §3). It talks to the device only through `iss` and the transport. No Qt import goes below `usb_iss_app.gui`.

**Frame logging follows D-008 (pending claude1).** If claude1 changes D-008 before you start, follow the new text, and say so in the report.

## Prerequisite: PySide6 (Chris, before the build)
- PySide6 is not installed in `.venv`, and the loop settings deny `pip`. D-001 adopts PySide6.
- Chris installs it into `.venv` (for example `.venv/bin/pip install PySide6`).
- **Builder's first step:** run the runner once. If `import PySide6` fails under `.venv/bin/python -m pytest`, **stop**. Write `build.md` saying so, and do not install anything yourself.

## Requirements

### 1. Dependency and runner header (D-001, D-003)
- Add `"PySide6"` to `[project] dependencies` in `pyproject.toml`. No other new dependency. pytest-qt is **not** allowed.
- `scripts/run_tests.py`: add a `PySide6: <version>` line to the log header, after the `pyserial:` line, using the existing `pkg_version`.

### 2. Frame log: `LoggingTransport` (SPEC F4; D-008)
- Put `LoggingTransport(Transport)` in `transport.py`. Its constructor is `LoggingTransport(inner: Transport, on_frame: Callable[[str, bytes], None] | None = None)`.
  - `write(data)`: logs `TX <hex>`, calls `on_frame("TX", data)`, then forwards to `inner.write`.
  - `read(n, timeout=...)`: forwards to `inner.read`. If the result is non-empty, it logs `RX <hex>` and calls `on_frame("RX", result)`. An empty result is neither logged nor passed to `on_frame`.
  - **Timeout.** `read` passes `timeout` to `inner.read` only when the caller gave one. Otherwise each inner transport keeps its own default (`SerialTransport` uses `None`).
  - `close()` forwards to `inner.close`.
- Logger name `usb_iss_app.frames`, level INFO. The hex is `data.hex(" ").upper()`, for example `TX 5A 01`.
- `transport.py` stays free of Qt.

### 3. Console helpers, free of Qt (SPEC F4)
Put these in `src/usb_iss_app/gui/`, in a module that does not import Qt, so the tests can run them without a display.
- `parse_hex(text: str) -> bytes`:
  - whitespace anywhere is ignored, and case does not matter: `"5A 01"`, `"5a01"` and `" 5A  01 "` all give `5A 01`;
  - raises `ValueError` for empty or whitespace-only input, an odd number of hex digits, or a non-hex character;
  - `0x` prefixes are not accepted.
- `exchange(t: Transport, data: bytes) -> bytes`:
  - one `t.write(data)`;
  - then `t.read(64)` repeatedly, with the transport's default timeout, until a read returns `b""` or 256 bytes have arrived in total;
  - returns everything read.
  - ASSUMPTION: the device sends its whole reply within one 500 ms timeout (p.11). 64 is the internal buffer size (p.14). The 256-byte cap only stops a babbling line.
  - The raw console imposes no frame limit. It exists to send exactly what the user types.

### 4. Main window (SPEC F1, F4; §3 layer 4)
Put `MainWindow(QMainWindow)` in `src/usb_iss_app/gui/`. Its constructor takes three injectable callables:
- `transport_factory(port: str) -> Transport` (default `SerialTransport`);
- `list_ports() -> list[str]` (default: the device names from `serial.tools.list_ports.comports()`);
- `env_port() -> str | None` (default `find_port`).

The tests inject mocks, and nothing in the tests opens a real port.

**Connect group (F1).**
- An editable port combo box lists `list_ports()`.
  - The `env_port()` value is preselected.
  - If that value is not in the list, it is inserted at the top.
- **Connect** does the following:
  - wraps `transport_factory(port)` in a `LoggingTransport` whose `on_frame` feeds the console view;
  - calls `iss.version` and `iss.serial_number`;
  - shows four values: the module ID in decimal (`7`); the firmware as `0x09`; the mode as `decode_mode` plus hex, for example `I2C_S_100KHZ (0x40)`; and the serial number (`00000001`).
- **Refresh** re-reads `iss.version` and updates the shown mode. The console can change the mode behind the panel's back.
- **Disconnect** closes the transport and clears the four values to `—`.
- **Failures.** If the factory, `version()` or `serial_number()` raises `IssError`, `OSError` (pyserial's `SerialException` is one) or `ValueError`:
  - the message is shown in the window (status bar or label);
  - a transport that was opened is closed;
  - the window stays disconnected.
- **Enabled state.**
  - Connected: Connect and the port combo are disabled; Disconnect, Refresh and console Send are enabled.
  - Disconnected: the reverse.
- Closing the window closes the transport.

**Console group (F4).**
- A hex input line, a **Send** button and a read-only view.
- **Send** runs `parse_hex`.
  - On `ValueError`, it shows the error in the view and writes nothing.
  - Otherwise it calls `exchange` on the logging transport.
  - If `exchange` returns nothing, the view adds a line `(no reply)`.
- The view shows every frame of the session as `TX 5A 01` / `RX 07 09 40` lines (D-008), in order. That includes F1's Connect and Refresh traffic.
- **Threading.** All I/O runs synchronously on the GUI thread. ASSUMPTION: this is acceptable for a minimal GUI. On hardware, one action blocks for at most about 1 s.

### 5. Entry point
- `python -m usb_iss_app` (`src/usb_iss_app/__main__.py`) calls `usb_iss_app.gui`'s `main()`. `main()`:
  - configures `logging.basicConfig(level=logging.INFO)` (stderr; D-008);
  - creates the `QApplication` and shows `MainWindow()`;
  - runs the event loop.
- Tests must not call `main()`. Importing it is enough.

### 6. Tests (mock only)
- **Qt setup.** Qt tests set `QT_QPA_PLATFORM=offscreen` before the first `QApplication` is created, and they share one `QApplication` for the session (a fixture in `tests/conftest.py` or a GUI-only conftest). Drive the widgets with `.click()`, `setText` and direct calls. No event loop is needed.
- **`LoggingTransport`** (`caplog`, over `MockTransport`):
  - `5A 01` logs exactly `TX 5A 01` then `RX 07 09 40` on `usb_iss_app.frames`;
  - an empty read logs nothing;
  - `on_frame` receives `("TX", …)` and `("RX", …)` in order;
  - `close` forwards;
  - with a recording inner transport, `read(3)` forwards no timeout and `read(3, timeout=0.1)` forwards `0.1`.
- **`parse_hex`:**
  - accepted: the three forms in requirement 3;
  - refused: `""`, `"  "`, `"5"`, `"5G"`, `"5A 0"`, `"0x5A"`.
- **`exchange`:**
  - on the mock, `5A 01` → `07 09 40`, and `5A 03` → the 8 serial digits;
  - a recording transport shows one `write()` and reads until one returns empty;
  - a transport that always returns 64 bytes stops at 256;
  - a frame the mock drops (for example `61 01` in mode `0x40`) → `b""`.
- **`MainWindow`**, with a factory that returns a `MockTransport` (firmware `0x09`, mode `0x40`, serial `00000001`):
  - `env_port()` is preselected, and it is inserted when `list_ports()` lacks it;
  - Connect calls the factory with the selected port, shows `7`, `0x09`, `I2C_S_100KHZ (0x40)` and `00000001`, and the view holds `TX 5A 01`, `RX 07 09 40`, `TX 5A 03`, `RX 30 30 30 30 30 30 30 31`, in that order;
  - a factory that raises `OSError` → the error is shown, the window stays disconnected, and Send is disabled;
  - a transport that never answers (`version()` → `IssTimeout`) → the error is shown, and that transport is closed;
  - console Send of `5A 01` appends its TX/RX lines; bad hex shows an error, and no write happens; a dropped frame adds `(no reply)`;
  - after a console send of `5A 02 00 AA` (IO_MODE, all inputs, which the mock answers `FF 00`), Refresh shows `IO_MODE (0x00)`;
  - Disconnect closes the transport and clears the values; `window.close()` closes the transport too.
- **Import.** `usb_iss_app.gui.main` imports without starting an event loop.

## Constraints / out of scope
- No F2 Mode panel (next iteration), no F3 I/O panel, no cards.
- No change to the behaviour of `iss.py` or `mock.py`.
- No new dependency except PySide6.
- Do not edit SPEC, DECISIONS, HARDWARE, NEXT, the role files, the templates, LOG or CHANGES.
- The iteration 00–05 tests stay unchanged. The one exception: a `test_run_tests.py` test that checks the header may gain the `PySide6:` line.
- Do not launch the GUI against the real device. The loop has no display, and nobody is watching.

## Hardware tests
**none.**
- Every GUI test uses the mock through the injected factory. Do not run `--hw`.
- Chris may try the GUI on the bench by hand later. The raw console can send any byte, so on this bench Chris must avoid SPI and serial modes and any I/O1 output (HARDWARE.md). The app does not enforce this, and SPEC does not ask it to.

## Acceptance criteria
- [ ] `.venv/bin/python scripts/run_tests.py --iter 06 --tag build` exits 0, and the new tests cover requirements 1–6.
- [ ] The final logged run's header shows the tested commit as `(clean)` and a `PySide6:` version line.
- [ ] `docs/iterations/06/logs/` holds no hardware log.
- [ ] The iteration 00–05 tests pass and are unchanged, apart from the permitted header-test change.
- [ ] `grep -rn "PySide6" src/usb_iss_app` finds hits only under `src/usb_iss_app/gui/`.

## Report back
- The PySide6 version, and whether the offscreen platform worked without extra system packages.
- Anything in F1 or F4 that you found ambiguous. In particular, whether D-008's reading of "logged" was enough to build on.
- Any place where a GUI test needed an event loop or a wait, and how you avoided it.
