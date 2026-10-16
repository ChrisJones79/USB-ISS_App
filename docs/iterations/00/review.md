# Iteration 00 — Review (fix cycle 0)

Model/effort: Opus 5.5, high · Reviewed commit: `997ac2b` on `iter/00` (code identical to `6afedc1 iter 00: bootstrap`; `997ac2b` is Chris's `.env` fix). Merged tip: `889a365`, see "Late commit" below.

## Verdict
**Accept**

## Independent test run
- Mock: `logs/review-mock-20261016-235224.txt` / `.xml`: 19 passed, 2 skipped (hw), exit 0. Header records commit `997ac2b (clean)`.
- Hardware: `logs/review-hw-20261016-235224.txt` / `.xml`: 21 passed, exit 0. `HW ISS_VERSION: module_id=7 firmware=0x09 mode=0x40`, `HW serial number: 00069221`.
- The results match the builder's `build-*-20261016-212915/212916` logs. Apart from timings and the XML path, the pytest output of the hw logs is identical line for line.
- Both runs used `.env` directly (`USB_ISS_PORT` unset in the shell), so they also confirm that Chris's `.env` fix in `997ac2b` works.
- Fresh clone: I cloned `iter/00` into my scratchpad and followed the readme Setup commands exactly (pyenv, venv, `pip install -e .[dev]`, `cp .env.example .env`). The mock run passed: 19 passed, 2 skipped, exit 0. That clone's log stays in the scratchpad and is not committed.
- Round trip `5A 01`, ad-hoc script (no log, same as the builder): median of 20 = 0.153 ms (min 0.139, max 0.193); first call after open 0.226 ms. This agrees with the builder's 0.158 ms.
- Mutation checks, run in the scratch clone, each applied and reverted with bytecode caching off:

  | Mutation | Caught? |
  |---|---|
  | `build_version` sends `5A 03` | yes (5 tests fail) |
  | module_id check removed | yes |
  | serial upper bound 0x39 → 0x3A | yes |
  | mock answers unknown `5A xx` | yes (3 fail) |
  | `unique_paths` ignores collisions | yes (2 fail) |
  | short-response length check `< 3` → `< 2` | yes |
  | `DEFAULT_TIMEOUT` 0.5 → 5.0 | **no** |
  | runner returns 0 instead of pytest's rc | **no** |
  | runner opens log with `"w"` instead of `"x"` | **no** (harmless while `unique_paths` is correct) |
  | exit-code footer removed | **no** (I checked it by reading the logs) |

## Acceptance criteria check
- [x] `run_tests.py --iter 00 --tag build` exits 0 and writes a `.txt` + `.xml` pair with the header (command, git commit + dirty flag, Python/pytest/pyserial/package versions, port on hw, UTC start) and the `exit code:` footer. Verified in my own logs.
- [x] Mock tests cover valid version/serial parsing, `IssTimeout` on short responses, `IssProtocolError` on module_id ≠ 7 and on non-digit serial bytes (including the boundary bytes `/` and `:`), and a silent mock on unhandled requests. Note: the short/bad-response tests use the `Scripted` stub rather than `MockTransport`. That is acceptable, since the mock cannot produce malformed responses by design.
- [x] Exact request bytes `5A 01` and `5A 03` are asserted (`test_version_request_bytes`, `test_serial_request_bytes`, both short-response tests).
- [x] Same-second non-overwrite has a test, `test_unique_path_never_overwrites`. It tests the path chooser with a fixed stamp rather than two real runner invocations. I accept that as the deterministic form of the criterion. Opening the log with `"x"` adds a second guard.
- [x] `--hw` without a port exits 2 with a message on stderr, and no log directory is created (`test_hw_without_port_refuses`).
- [x] Hardware run passes: module_id == 7, 8 ASCII digits, firmware printed into the log via `-rA`.
- [x] A fresh clone following the readme Setup reaches a passing mock run. I verified this myself.

## Issues
1. **minor — reading.** The mock's resync rule can invent responses. For any non-`5A` byte it drops one byte and rescans, so payload bytes `5A 01` inside a later command (for example SPI data `61 5A 01`, or a baud divisor `0x5A01` in an IO+SERIAL frame) would make it emit an ISS_VERSION reply the real device would not send. This is harmless today, because only two commands exist. It must be fixed when ISS_MODE introduces variable-length frames. Carried into NEXT 01, requirement 5.
2. **minor — test (mutation).** No test pins the 500 ms default read timeout (datasheet p.11), so changing it to 5 s stays green. Carried into NEXT 01.
3. **minor — reading.** `SerialTransport(timeout=…)` is effectively ignored. `read()` always resets `self._ser.timeout` to its own default of 0.5 s, so the constructor value has no effect. Carried into NEXT 01.
4. **minor — reading/test.** The runner's dirty flag is not very useful. Every untracked log makes the next run "dirty" (my hw log shows this: it is dirty only because of the mock log written one second earlier). Builder logs are taken before commit, so their header shows the *parent* commit (`926459c (dirty)`), and the log cannot identify the code that was tested. Carried into NEXT 01 (ignore `docs/iterations/*/logs/`, and record the porcelain status when dirty).
5. **minor — test.** No test checks that the runner's exit code equals pytest's (mutation not caught). I verified it by reading: `return rc`. No action now.
6. **process — reading. Resolved by Chris during the review.** `.env` was tracked in git: Chris committed it in `926459c` and `997ac2b`, so the `.gitignore` entry had no effect, and CLAUDE.md says `.env` "is not committed". Chris fixed this while the review was running (see "Late commit").

## Late commit
- `889a365 iter 00: stop tracking .env` (Chris, 23:52:31 UTC) landed on `iter/00` seven seconds after my test runs started. I did not see it until after the merge.
- It only removes `.env` from the index. `git diff 997ac2b 889a365` touches nothing else, so the test results above apply to the merged code unchanged.
- **Side effect of my merge, now repaired.** `main` still tracked `.env`, so `git checkout main` overwrote Chris's ignored local `.env`, and merging the deletion then removed it from disk. I recreated it from the `997ac2b` blob, which is the content I read at the start of the review. It is now present, ignored and untracked.
- Process note: the reviewer should check that the branch tip still equals the reviewed commit just before merging, and check out `main` with care when a tracked file is becoming ignored.

## Scope drift
None of substance. The extras are all reported in build.md and are reasonable:
- `--env-file` option (needed to test the refusal hermetically);
- `requires-python <3.13`, consistent with D-003;
- `.pytest_cache/` in `.gitignore`;
- `MockTransport.unhandled` list and `closed` flag.

## Builder report accuracy
- All checkable claims hold: test counts, firmware 0x09, mode 0x40, serial 00069221, round-trip time, log names, deviations.
- One inaccuracy: build.md calls `.env` "uncommitted, Chris's file". It was committed on `main` in `926459c` before the iteration began (see issue 6). It is Chris's file, but it is not uncommitted.
- The builder's datasheet question ("doesn't say how the firmware byte is versioned") is answered by the firmware changelog on datasheet p.2. The byte is the changelog version number, and 0x09 is "Version 9, July 2020" (clock stretching in software I2C), the latest listed.
- The builder said they did not re-read p.11 for the 500 ms timeout. I did: p.11 states "timing out after 500mS" for I2C transactions, and pp.12–14 repeat it.

## Notes for claude1
- **SPEC §8 note 3 vs datasheet.** SPEC says the datasheet "does not say whether IO_CHANGE returns the same 2-byte response". The datasheet p.6 says "The response to the mode setting frames is always two bytes". The IO_CHANGE example on p.7 shows `Receive 0xFF 0x00`. This is not a behavioural conflict, since the hardware check SPEC asks for is harmless and is kept in NEXT 01. But the SPEC note looks factually wrong and may need rewording.
- **Datasheet I2C example drives an output.** The I2C_MODE example on p.9 (`5A 02 60 04`) sets I/O2 to output high. In I2C mode, I/O1 and I/O2 remain general I/O (pin table p.3). NEXT 01's hardware tests use input-only IO_TYPE values for this reason.
- **New decision, pending claude1: D-005**, the SPI divisor rounding direction (SPEC gives the formula but no rounding rule). See DECISIONS.md.
- Process: the role files don't say which commit the `iter-NN` tag goes on. I tagged the review commit on `main`, so the tag contains the code, build.md and review.md together.
