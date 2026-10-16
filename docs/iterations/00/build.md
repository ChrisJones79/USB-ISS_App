# Iteration 00 — Build report

Model/effort: Sonnet 5.5, medium · Branch: iter/00 · Commit: see `git log iter/00` (`iter 00: bootstrap`)

## Summary
Package layout, venv/pyenv setup, logging test runner, Transport + SerialTransport + MockTransport, and `ISS_VERSION` / `GET_SER_NUM` builders, parsers and helpers. All pass on the mock and on the real USB-ISS.

## Files changed
`.python-version`, `pyproject.toml`, `.gitignore`, `.env.example`, `readme.md` (Setup section), `scripts/run_tests.py`, `src/usb_iss_app/{__init__,transport,mock,iss}.py`, `tests/{conftest,test_iss,test_transport,test_run_tests,test_hw}.py`, logs under `docs/iterations/00/logs/`.

## Acceptance criteria
- Runner exits 0, writes `.txt` + `.xml` with header and exit-code footer: **met** — `logs/build-mock-20261016-212915.txt`.
- Mock tests cover parsing, IssTimeout, module_id≠7, non-digit serial, mock silent on unhandled: **met** — `tests/test_iss.py`.
- Exact request bytes `5A 01` / `5A 03` asserted: **met** — `test_version_request_bytes`, `test_serial_request_bytes`, and both short-response tests.
- Same-second second run does not overwrite: **met** — `test_unique_path_never_overwrites` (adds `-2`, `-3` suffix on collision).
- `--hw` without port exits non-zero, runs no tests: **met** — `test_hw_without_port_refuses`; also checked by hand (exit 2, message on stderr).
- Hardware run passes (module_id 7, 8-digit serial, firmware reported): **met** — `logs/build-hw-20261016-212916.txt` (prints `HW ISS_VERSION: ... firmware=0x09`).
- Fresh clone following Setup reaches passing mock run: **met** — see Deviations/notes (checked from a clone of the iter/00 commit).

## Test results
Mock: 19 passed, 2 skipped (hw). Hardware: 21 passed. Logs: `docs/iterations/00/logs/build-mock-20261016-212915.*`, `build-hw-20261016-212916.*`.
The earlier pair (`...212902`, `...212906`) came from before I removed an unused `record_property` call that raised a pytest warning; superseded, left in place because logs are not edited or deleted.

Hardware readings:
- Firmware version **0x09**, mode byte **0x40**, serial **00069221**, module_id 7.
- `5A 01` round trip, median of 20: **0.158 ms** (min 0.140, max 0.203). Measured with an ad-hoc script, not part of the test suite, so there is no log for it.

## Deviations from NEXT.md
- `.python-version` pins **3.12.15** (installed via `pyenv install` since only 3.13/3.14 were present).
- `.env` on this machine has a line break inside the `USB_ISS_PORT` value (`/dev/serial/by-id/` then newline, then `usb-Devantech...-if00`). The parser reads that as an incomplete path. I did not edit `.env` (uncommitted, Chris's file); hardware runs used `export USB_ISS_PORT=<full path>`. **Chris needs to join the two lines.**
- The mock's unhandled-request handling drops 2 bytes at a time for an unknown `5A xx`, and 1 byte for a non-`5A` byte; each drop is logged and recorded in `mock.unhandled`. NEXT.md did not specify the resync behaviour.
- `run_tests.py` has an extra `--env-file` option (used by the refuse test); `pyproject` has `requires-python >=3.12,<3.13`.

## Questions and proposed spec/process changes
- Datasheet ambiguity: the datasheet example shows firmware 0x02, our device reports 0x09; the doc doesn't say how the firmware byte is versioned. The 500 ms timeout (p.11) is taken from NEXT.md; I did not independently re-read that page.
- Measured latency 0.16 ms looks plausible for USB CDC but the first call after open could be slower; not examined.
