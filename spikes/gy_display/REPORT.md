# Spike report: GY-MCU90640 live display over USB-ISS serial

Brief: `SPIKE-gy-display.md` (claude1, 2026-10-20). Branch `spike/gy-display`, from `origin/main` at `07792f0`. Not merged to `main`.

## Result
It works. The window shows the GY-MCU90640's 32×24 image live at 4 frames/s, received through the USB-ISS in IO_MODE+SERIAL. Everything on the USB-ISS side uses the existing `usb_iss_app` package. No byte was sent to the GY: every SERIAL_IO was the bare receive poll (datasheet p.19). Step 3 was not needed, so it was not run.

Before starting, Chris confirmed that `scripts/loop.sh` was not running and that the bench matched HARDWARE.md. PySide6 6.12.0 imported from `.venv`.

## Step 1: capture, no GUI
Log: `logs/capture-20261020-203047.log`. The raw received bytes are in `logs/capture-20261020-203047.bin`.

| | |
|---|---|
| Firmware | 0x09, serial 00069221 |
| Mode before | 0x40 (I2C_S_100KHZ, left over from an earlier run) |
| Mode sent | `5A 02 01 00 19 AA` |
| Mode read back | 0x01 (IO_MODE+SERIAL) |
| Polls | 160,353 in 30.00 s = 5,345/s, 0 NACKs |
| Bytes | 182,422 = 6,081 B/s (the 115200 8N1 line carries at most ~11,520 B/s) |
| Polls returning the full 62 bytes | 0. Largest single poll: 42 bytes. Most polls returned 0–4. |
| Frames found | 118: 118 checksum pass, 0 fail (0.0%) |
| Bytes discarded while resyncing | 0 |
| Frame rate | 3.93/s over the run; 3.94/s between the first and last good frame |
| Last good frame | min 16.89 °C, max 25.18 °C, Ta 27.17 °C |

## Step 2: display
`view.py` polls in a `QThread` worker that owns the port from open to close. The GUI gets only checksum-valid frames, and only the newest one per poll, so it never queues a backlog. The heatmap is 32×24 at 20 px per cell. Pixel *i* is row `i // 32`, and the manual's column `i % 32 + 1` is drawn from the right. Readouts: min, max, Ta, colour scale, frames/s, checksum fails, good frames, polls/s. Closing the window stops the worker, which closes the port. The worker logs a stats line every 5 s.

Live runs (all exited 0 and logged `port closed`):

| Log | Length | Good frames | Checksum fail | Full polls | Discarded bytes | Notes |
|---|---|---|---|---|---|---|
| `logs/view-20261020-203614.log` | 43,308 s (~12 h) | 170,485 | 8 | 0 | 12,137 | Unplanned. The window stayed open overnight because Chris did not see my question (see below). |
| `logs/view-20261021-084010.log` | 48 s | 188 | 0 | 0 | 0 | Hand test |
| `logs/view-20261021-084621.log` | 43 s | 167 | 0 | 0 | 498 | Hot-corner check. The port opened partway through a frame, and the parser skipped to the next header. |

Over all three runs, 8 of 170,848 frames failed the checksum (0.005%). Polls ran at 5,184–5,290/s, and no poll filled the 62-byte buffer.

**Hand test**, in Chris's words: "Tracking good. Up is up wrt the module, left to right movement is left to right on display, so anti-mirror." That is with column 1 drawn on the right, as the GY manual says.

**Hot corner.** In the step 1 capture, column 1 rows 1–4 (the top right) read 22.2–22.9 °C on average across all 118 frames. Column 2 next to it read 19.4–20.3 °C, and the median of the whole frame was 18.0 °C. In the 08:46 run Chris saw no hot pixels, including with the sensor pointed at the ceiling. Chris's conclusion: there was a warmer object at the edge of the view during the capture.

**"Is the display the full 32×24?"** Chris asked this. `test_view.py` checks it offscreen in the real widget:
- The widget is 640×480 (32×24 cells).
- A frame with 768 distinct values gives 768 distinct cell colours, in the order above.
- Each corner pixel (0, 31, 736, 767) lights only its own corner cell.

**Noise on a uniform scene.** Against the ceiling, the image looked "much more random". By default the colour scale is stretched to each frame's own min..max, so on a uniform scene ordinary sensor noise fills the whole colour range. At Chris's request I added a fixed-range option (below). The viewer does not log per-frame min/max, so the spread on the ceiling was not measured.

## Beyond the brief
- **Fixed colour range** (Chris asked for it). Tick "fixed range" in the window and set from/to in °C, or start with `--fixed LO HI`. Auto range stays the default. Values outside the range clamp to the end colours. Each change is logged. Tested offline with `test_view.py` and on the replay (`logs/view-replay-20261021-085203.log`). It was not run on live hardware.
- **`--replay FILE.bin`** plays a saved capture at ~6,000 B/s, looping, with no port. Replay logs are named `view-replay-*.log`, so they are never confused with hardware runs.
- **`--seconds N --snapshot PNG`** closes the window after N seconds and saves a screenshot. Used for the offscreen checks.
- `capture.py` also reads the serial number (GET_SER_NUM, a safe read) and saves the raw stream to `.bin` next to its log.
- Offline tests: `test_gyframe.py` (parser, resync, checksum, signed values) and `test_view.py` (cell layout, corners, fixed/auto scale). Run them with `.venv/bin/python -m pytest spikes/gy_display -q` (9 pass).

## What the package lacked
Nothing on the USB-ISS side. `version`, `serial_number`, `build_io_serial`, `set_mode` and `serial_io` were enough, unchanged. I built in the spike:
- `gyframe.py`: the GY frame parser (resync on `5A 5A 02 06`, 1544-byte frames, 771-word checksum, signed int16 ÷100) and `SpikeLog`. `SpikeLog` writes a timestamped log that is never overwritten (open mode `x`) and is thread-safe.
- The poll loop and its stats, in `capture.py` and in `view.py`'s `PollWorker`. A future card driver will need its own receive loop like this; the package has only the single poll.

## Datasheet and manual disagreements
- **USB-ISS p.8:** the baud formula prints `16+baud`. This is already in SPEC §8. The table's 115200 divisor, 25 (`00 19`), is what was sent and it works.
- **USB-ISS p.8:** "Only I/O3 and I/O are available" is missing the 4. Not a protocol issue.
- **GY manual §IV.2:** it calls `0x0602` = 1538 "temperature data". That is a byte count (769 words: 768 pixels plus Ta), not a number of values. The parser checks for the bytes `02 06`, whatever they mean.
- **GY manual §IV.2:** it does not say whether the values are signed. The spike reads them as signed int16, as the brief says, since the range goes down to −40 °C. No negative value was seen, so this is not verified on hardware.
- **GY manual §IV.3:** the pixel-order sentence has a typo ("(Col 1, Row XX) (Col 1, Row XX)"). Read with the Col 1/Row 1 note, it gives the order above, and the hand test agrees with it.
- **The GY manual gives no default update rate.** It was 4.00 frames/s at power-up on this module.
- **For claude1, against SPEC §5.** SPEC §5 says the driver uses query mode and that "continuous output is allowed only at 2 Hz or slower", because a frame takes at least 25 SERIAL_IO polls. In this spike, continuous output at the module's default 4 Hz ran for ~12 h with 8 checksum failures in 170,485 frames and no full poll, at ~5,300 polls/s. I have not changed anything. Whether the 2 Hz limit still stands is claude1's call.

## Process notes
- **The overnight run.** I started the viewer in the background and asked the hand-test question in a dialog. Chris did not see the question, which was then cancelled, and the window stayed open with the port held until Chris closed it at 08:38 the next morning. The loop was not running, and nothing else needed the port. It is recorded here because it was not planned.
- **Chris wants this code kept in the repo** for this and future testing, and possibly folded later into something like a module quick-test feature. The brief says nothing here is merged to `main`, so that is claude1's decision.
- **Chris has a second module with PS soldered low (I2C direct).** Chris deferred testing it and will handle it later. HARDWARE.md lists that module as not attached, so it would need updating before any run.
- **Untracked files I did not commit**, because the brief does not let me touch them:
  - `docs/reference/MLX90640-Datasheet-Melexis-1.pdf`. Chris added it. It clears one of SPEC §5's two blockers for `i2c_direct`.
  - `SPIKE-gy-display.md` (the brief), in the repo root.

## Chris's time
About 30 minutes (Chris's figure).

## Files
- `capture.py`: step 1
- `view.py`: step 2
- `gyframe.py`: parser and log helper
- `test_gyframe.py`, `test_view.py`: offline tests
- `logs/`: every run's log, written by the scripts themselves
