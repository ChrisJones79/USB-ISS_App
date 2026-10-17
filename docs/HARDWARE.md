# Bench hardware

Chris owns this file. It describes what is physically connected to the USB-ISS right now. Read it before any hardware test. A `NEXT.md` hardware section must be consistent with it. If they disagree, stop and report the conflict.

Last updated: 2026-10-17 (claude1, from Chris's description; second unit and .env note added in iteration 02).

## USB-ISS
- Connected to the PC over USB. The port comes from `USB_ISS_PORT` in `.env`.
- **The 5 V power link is fitted.** VCC is 5 V, up to 80 mA available (datasheet p.3).
- Firmware 0x09, serial 00069221 (iteration 00 hardware log). This is the bench unit, and `.env` points to it.
- A second USB-ISS, serial 00069220 (firmware 0x09), is available but not normally connected. It was used once in iteration 02 to cross-check the GETAD erratum.
- **The `.env` setting is copied into each VS Code terminal when the terminal opens** (`python.terminal.useEnvFile`), and the environment variable takes priority over `.env`. After you edit `.env`, open a new terminal. To use a different port for one run, set it on the command line: `USB_ISS_PORT=... <command>`.

## Attached: GY-MCU90640, serial mode (card `gy-mcu90640`, mode `serial`)

| GY pin | USB-ISS pin | Notes |
|---|---|---|
| VIN | VCC (5 V) | 100 nF (104) capacitor across VIN and GND. 42 mA draw. |
| GND | GND | |
| TX | I/O1 | USB-ISS RX in serial modes. **Driven by the module.** |
| RX | I/O2 | USB-ISS TX in serial modes. |
| SCL, SDA | not connected | These pins are the MLX90640's own I2C bus. With PS open, the module's MCU is the master on that bus. Never connect them to the USB-ISS in this mode. |
| PS | open | Serial mode. Grounding PS and power-cycling selects I2C-direct mode (GY manual p.5). |

### Consequences for tests
- I/O1 is driven by the module's TX. At power-up the module transmits continuously at 115200 baud (GY manual p.5). **Never configure I/O1 as an output.** In IO_MODE, GETPINS and GETAD on I/O1 return varying values: log them, don't assert them.
- In serial modes the USB-ISS drives I/O2 (TX) into the module's RX. Any byte sent is a command to the module (GY manual §IV). Send only commands that `NEXT.md` names explicitly. Never send save-to-flash in automated tests (SPEC §7).
- I/O3 and I/O4 (SCL and SDA in I2C modes) are unconnected.
- In every IO_TYPE byte, set unused pin pairs to digital input (`10`), never output (`00`/`01`).

## Not attached
- A second GY-MCU90640 with PS grounded (I2C direct). It was removed on 2026-10-17 because two modules would exceed the 80 mA power budget. Iteration 01's hardware runs were taken with both modules attached and the I2C lines shared.
