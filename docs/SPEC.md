# SPEC — USB-ISS App (v0.1)

claude1 owns the intent of this document. Changes come through checkpoint memos or Chris.

## 1. Purpose
A desktop GUI that:
- gets and sets USB-ISS options;
- operates downstream devices over serial, I2C or SPI through **device cards**.

Cards are the main feature. Everything else exists to support them.

## 2. Stack
Python 3.12, PySide6, pyserial, pytest. See D-001 and D-003.

## 3. Architecture
Four layers. Each layer depends only on the layers below it.

1. **transport**
   - Opens the virtual COM port and does raw byte I/O with timeouts.
   - Has two implementations behind one interface: real (pyserial) and mock.
2. **protocol** (`iss`)
   - Covers every USB-ISS command in the datasheet: ISS setup, I2C, SPI, serial and I/O.
   - Each command is a pure function that builds request bytes, plus a parser for the response.
   - No GUI imports.
3. **cards**
   - Loads card manifests and card drivers.
   - Card drivers talk to their device only through `iss`, never through the transport directly.
4. **gui**
   - Holds the ISS panel (version, serial number, mode, I/O) and a card host, which loads a card's UI panel.

**The mock.**
- The mock USB-ISS emulates the datasheet behaviour: responses, NACK reasons and buffer limits.
- A card may ship a mock of its device, so it can be tested without hardware.

## 4. Features (v1)

**F1. Connect.**
- Pick a port, or take it from `USB_ISS_PORT`.
- Show the module ID, firmware version, current mode and serial number.

**F2. Mode.**
- Set any ISS_MODE from the datasheet, including the combined modes (I2C+Serial, IO+Serial).
- Baud rate is entered in bps. The app computes the divisor and shows the actual rate and the error.
- The app refuses any rate whose error is greater than 3%.

**F3. I/O.**
- Set IO_TYPE per pin, then SETPINS, GETPINS and GETAD.

**F4. Raw console.**
- Send hex bytes and see the response.
- Every frame, in both directions, is shown and logged.

**F5. Cards.**
- Load a card.
- Choose one of its modes.
- The app applies that mode's ISS configuration, then opens the card's panel.

**F6. Card editor.**
- Create or edit a card manifest from the GUI. This covers the metadata, modes, ISS config and resources.
- Driver code is written outside the app; the editor only links to it.

## 5. Device cards

A card is a self-contained directory in `cards/<card-id>/`:

```
cards/gy-mcu90640/
  card.json        manifest (schema below)
  driver.py        one driver class per mode
  panel.py         PySide6 widget(s) for the card UI
  mock.py          optional device mock for tests
  reference/       datasheets and user manuals
  tests/
```

### Manifest (`card.json`)

**Required fields:**
- `id`, `name`, `version`, `description`
- `power`: supply voltage and current draw. The app warns if these exceed what the USB-ISS can supply: 80 mA at 5 V, 30 mA at 3.3 V.
- `resources`: paths into `reference/`
- `modes`: one or more mode entries (below)
- `default_mode`: the id of one entry in `modes`

**Each mode entry has:**
- `id` and `label`
- `status`: `supported` or `planned`. Planned modes are visible in the GUI but can't be activated.
- `iss`: the ISS configuration to apply, given as a mode name plus parameters (baud, io_type, i2c speed, spi phase/divisor).
- `wiring`: a pin map from USB-ISS pins to device pins, shown to the user.
- `driver`: the class name in `driver.py`.
- `device_settings`: device-side options the panel exposes, such as baud, rate or emissivity.

**Principle.** A card should describe *every* way of operating its device, even modes nobody has implemented yet. Once a card has a manifest, a new mode can be added without changing the app.

### First card: GY-MCU90640 (MLX90640 thermal array)

**Mode `serial` (default, supported).**
- ISS configuration: IO_MODE+SERIAL at 115200 baud (divisor 25, actual 115385, error +0.16%).
- Wiring: ISS I/O1 (RX) ← module TX, ISS I/O2 (TX) → module RX, PS left open.
- Device protocol (from the module's user manual):
  - Frames are 1544 bytes: header `5A 5A`, count `0x0602`, then 768 pixel values in little-endian ×100 °C, then Ta, then checksum.
  - The checksum is the 16-bit sum of the first 771 little-endian words.
  - Commands are `A5 <cmd> <arg> <sum8>`, covering baud, rate, query/auto, emissivity, emissivity query and save.
- The driver uses **query mode** by default.
  - Reason: the USB-ISS receive buffer is 62 bytes, so a frame takes at least 25 SERIAL_IO polls.
  - Continuous output is allowed only at 2 Hz or slower.
- 460800 baud is not offered: the divisor would be 5.5 and the error too large.
- Panel:
  - a 32×24 heatmap with the correct pixel order (Col 1/Row 1 is at the upper right);
  - min, max and Ta readouts;
  - device settings;
  - a save-to-flash button behind a confirmation.

**Mode `i2c_direct` (planned).**
- ISS configuration: I2C mode. The module's PS pin is grounded and the module is power-cycled.
- The driver reads the MLX90640 directly, at I2C address 0x33.
- Blocked on two things:
  - the Melexis MLX90640 datasheet (EEPROM calibration and RAM map), which is not yet in `reference/`;
  - confirming the module's I2C logic levels at a 5 V supply.

**Power.**
- The module draws 42 mA, so it **requires the USB-ISS 5 V link**. The 3.3 V supply is limited to 30 mA.

## 6. Roadmap
Each item is roughly one iteration. revclaude may split an item, but must not merge two.

- **00. Bootstrap**
  - Package layout and venv setup instructions.
  - A pytest runner that writes `docs/iterations/NN/logs/`.
  - The transport interface with the mock.
  - `iss` ISS_VERSION and GET_SER_NUM, tested against the mock and, read-only, against hardware.
- **01. ISS_MODE**
  - All modes, the IO_TYPE builder, the baud and SPI divisor calculators with error reporting, and NACK parsing.
- **02. SERIAL_IO and I/O commands**
  - SERIAL_IO, SETPINS, GETPINS and GETAD, with buffer limits enforced (30-byte TX, 62-byte RX).
- **03. I2C and SPI commands**
  - I2C_SGL, I2C_AD0/1/2, I2C_DIRECT, I2C_TEST and SPI, with frame limits enforced.
- **04. Minimal GUI**
  - Features F1, F2 and F4.
- **05. Card framework**
  - Manifest schema and validation, the loader, the card host, and mode activation (F5).
- **06. GY-MCU90640 card, serial driver**
  - Frame parser, checksum, commands and device mock.
  - Hardware test: read one frame in query mode.
- **07. GY-MCU90640 panel**
  - Heatmap and device settings.
- **08. I/O panel (F3)**
- **09. Card editor (F6)**
- **Later:** GY-MCU90640 `i2c_direct`; more cards.

## 7. Out of scope (v1)
- Firmware or bootloader updates.
- Multiple USB-ISS modules at once.
- Editing driver code inside the app.
- Writing to the module's flash in automated tests. Save-to-flash is a manual, confirmed action only.

## 8. Datasheet notes
- **Baud formula (USB-ISS datasheet p.8).** The text prints `48000000/(16+baud)`. The correct formula is `48000000/(16*baud) - 1`, which matches the worked example and the table. Use floor, which matches every table row (19200 gives 155, 9600 gives 311). The actual rate is `48000000/(16*(divisor+1))`.
- **Baud table error (p.8).** The 2400 row lists bytes `0x09 0xE1`, which is 2529. The divisor 1249 is `0x04 0xE1`. Trust the formula, not that row. Add a unit test for it.
- **ISS_MODE response.** The datasheet does not say whether IO_CHANGE returns the same 2-byte response as the other mode commands. Verify this on hardware in iteration 01.