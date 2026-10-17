# Bench hardware

Chris owns this file. It describes what is physically connected to the USB-ISS right now. Read it before any hardware test. A `NEXT.md` hardware section must be consistent with it. If they disagree, stop and report the conflict.

Last updated: 2026-10-17 (claude1, from Chris's measurements). **Bench changed after iteration 02:** the USB-ISS now runs at 3.3 V. Hardware logs from iterations 00–02 were taken at 5 V.

## USB-ISS
- Connected to the PC over USB, which also powers it. The port comes from `USB_ISS_PORT` in `.env`.
- **The 5 V power link is removed, so the USB-ISS runs at 3.3 V.** VCC measured 3.3 V. Logic levels are 3.3 V. Inputs are **not** 5 V tolerant (datasheet p.3).
- The bootloader link is not fitted. Never fit it.
- The VCC pin is **not connected** to anything. Never apply an external voltage to it (p.3).
- GETAD full scale (1023) now corresponds to 3.3 V.
- The bench unit is firmware 0x09, serial 00069221, and `.env` points to it.
- A second USB-ISS, serial 00069220 (firmware 0x09), is available but not normally connected. It was used once in iteration 02 to cross-check the GETAD erratum.
- **The `.env` setting is copied into each VS Code terminal when the terminal opens** (`python.terminal.useEnvFile`), and the environment variable takes priority over `.env`. After you edit `.env`, open a new terminal. To use a different port for one run, set it on the command line: `USB_ISS_PORT=... <command>`.

## Attached: GY-MCU90640, serial mode (card `gy-mcu90640`, mode `serial`)

| GY pin | Connects to | Notes |
|---|---|---|
| VIN | separate 5 V supply (measured 5.0 V) | 100 nF (104) capacitor across VIN and GND. 42 mA draw. |
| GND | supply GND **and** USB-ISS GND | Common ground. |
| TX | USB-ISS I/O1 | USB-ISS RX in serial modes. **Driven by the module**, 3.3 V high (measured). |
| RX | USB-ISS I/O2 | USB-ISS TX in serial modes. 3.3 V logic on both sides. |
| SCL, SDA | not connected | These pins are the MLX90640's own I2C bus. With PS open, the module's MCU is the master on that bus. Never connect them to the USB-ISS in this mode. |
| PS | open | Serial mode. Grounding PS and power-cycling selects I2C-direct mode (GY manual p.5). |

### Consequences for tests
- I/O1 is driven by the module's TX. At power-up the module transmits continuously at 115200 baud, as confirmed on a scope (2026-10-17). **Never configure I/O1 as an output.** In IO_MODE, GETPINS and GETAD on I/O1 return varying values, including `00 00` when sampled while TX is low. Log them, don't assert them.
- While I/O2 is an input, the RX line is undriven. It sits near 2.4 V and picks up crosstalk from TX (scope, 2026-10-17). This is harmless, and in serial modes the USB-ISS drives it.
- In serial modes the USB-ISS drives I/O2 (TX) into the module's RX. Any byte sent is a command to the module (GY manual §IV). Send only commands that `NEXT.md` names explicitly. Never send save-to-flash in automated tests (SPEC §7).
- I/O3 and I/O4 (SCL and SDA in I2C modes) are unconnected. The I2C bus is empty, and the USB-ISS's 4.7k pull-ups hold it at 3.3 V.
- In every IO_TYPE byte, set unused pin pairs to digital input (`10`), never output (`00`/`01`).

## Not attached
- A second GY-MCU90640 with PS grounded (I2C direct). It was removed on 2026-10-17 because two modules would exceed the 80 mA power budget. Iteration 01's hardware runs were taken with both modules attached and the I2C lines shared.
