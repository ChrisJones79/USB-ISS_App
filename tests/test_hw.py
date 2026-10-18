import pytest

from usb_iss_app import iss

pytestmark = pytest.mark.hw


def test_hw_version(hw):
    v = iss.version(hw)
    print(f"HW ISS_VERSION: module_id={v.module_id} firmware=0x{v.firmware:02X} mode=0x{v.mode:02X}")
    assert v.module_id == 7


def test_hw_serial(hw):
    s = iss.serial_number(hw)
    print(f"HW serial number: {s}")
    assert len(s) == 8 and s.isascii() and s.isdigit()


def test_hw_mode_sequence(hw):
    """NEXT 01 hardware sequence: inputs only, always restores I2C_S_100KHZ (0x40)."""
    def mode_byte(label):
        m = iss.version(hw).mode
        print(f"HW after {label}: mode=0x{m:02X} ({iss.decode_mode(m)})")
        return m

    try:
        iss.set_mode(hw, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0xAA))
        assert mode_byte("I2C_S_100KHZ 5A 02 40 AA") == 0x40

        frame = iss.build_io_change(0xAF)
        hw.write(frame)
        raw = hw.read(2)
        print(f"HW IO_CHANGE {frame.hex(' ')} raw response: {raw.hex(' ') or '(none)'}")
        mode_byte("IO_CHANGE 5A 02 10 AF")  # logged, not asserted
        assert raw == bytes([0xFF, 0x00])

        iss.set_mode(hw, iss.build_io_mode(0xAA))
        assert mode_byte("IO_MODE 5A 02 00 AA") == 0x00
    finally:
        iss.set_mode(hw, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0xAA))
        assert mode_byte("restore 5A 02 40 AA") == 0x40


@pytest.fixture
def io_hw(hw):
    """NEXT 02 hardware sequence helpers. No pin is ever an output; always restores I2C_S_100KHZ (0x40)."""
    def mode_byte(label):
        m = iss.version(hw).mode
        print(f"HW after {label}: mode=0x{m:02X} ({iss.decode_mode(m)})")
        return m

    def raw(label, frame, n):
        hw.write(frame)
        r = hw.read(n)
        print(f"HW {label} {frame.hex(' ')} raw response: {r.hex(' ') or '(none)'}")
        return r

    yield hw, mode_byte, raw
    iss.set_mode(hw, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0xAA))
    assert mode_byte("restore 5A 02 40 AA") == 0x40


def test_hw_io_getpins_setpins(io_hw):
    """NEXT 02 steps 1-2."""
    hw, mode_byte, raw = io_hw
    iss.set_mode(hw, iss.build_io_mode(0xAA))
    assert mode_byte("IO_MODE 5A 02 00 AA") == 0x00
    assert len(raw("GETPINS", iss.build_get_pins(), 2)) == 1
    assert raw("SETPINS", bytes([0x63, 0x0F]), 2) in (b"\xff", b"\x00")
    assert len(raw("GETPINS", iss.build_get_pins(), 2)) == 1


def test_hw_io_getad_on_digital_pin(io_hw):
    """NEXT 02 fix 1 req 1. Datasheet p.20 says 00 00 for a channel not set up as analogue;
    the device does not do that (iteration 02 logs: 02 E1). Only the shape is asserted."""
    hw, mode_byte, raw = io_hw
    iss.set_mode(hw, iss.build_io_mode(0xAA))
    assert mode_byte("IO_MODE 5A 02 00 AA") == 0x00
    r = raw("GETAD digital", iss.build_get_ad(1), 3)
    assert len(r) == 2 and 0 <= int.from_bytes(r, "big") <= 1023


def test_hw_io_getad_analogue(io_hw):
    """NEXT 02 steps 4-5."""
    hw, mode_byte, raw = io_hw
    iss.set_mode(hw, iss.build_io_mode(0xFF))
    assert mode_byte("IO_MODE 5A 02 00 FF") == 0x00
    for ch in range(1, 5):
        v = iss.get_ad(hw, ch)
        print(f"HW GETAD channel {ch}: {v}")
        assert 0 <= v <= 1023
    for ch in (0, 5):
        assert raw(f"GETAD out-of-range {ch}", bytes([0x65, ch]), 3) == b"\x00\x00"


def test_hw_i2c_empty_bus(io_hw):
    """NEXT 03 hardware steps 1-5. Empty bus; no I2C write command is sent. Raw responses are logged, not asserted."""
    hw, mode_byte, raw = io_hw
    iss.set_mode(hw, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0xAA))
    assert mode_byte("I2C_S_100KHZ 5A 02 40 AA") == 0x40
    for addr in (0xA0, 0x66):  # 0x66 is the MLX90640's 0x33 in 8-bit form; not on this bus
        assert len(raw(f"I2C_TEST {addr:02X}", iss.build_i2c_test(addr), 2)) == 1
    raw("I2C_AD1 read empty bus", iss.build_i2c_ad1_read(0xA0, 0x00, 1), 3)
    assert mode_byte("after I2C_AD1 read") == 0x40
    iss.set_mode(hw, iss.build_io_mode(0xAA))
    assert mode_byte("IO_MODE 5A 02 00 AA") == 0x00
    raw("I2C_TEST A0 in IO_MODE", iss.build_i2c_test(0xA0), 2)
    assert mode_byte("after I2C_TEST in IO_MODE") == 0x00


def test_hw_i2c_direct_empty_bus(io_hw):
    """NEXT 04 hardware steps 1-5. Address-only frames on the empty bus; no data byte is written to any address.
    Raw responses are logged, not asserted. Each frame is sent in one write()."""
    hw, mode_byte, raw = io_hw
    iss.set_mode(hw, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0xAA))
    assert mode_byte("I2C_S_100KHZ 5A 02 40 AA") == 0x40
    # Step 2: START, WRITE 1 (address A0), STOP. Expected 00 01.
    raw("I2C_DIRECT address-only", bytes.fromhex("57 01 30 A0 03"), 4)
    assert mode_byte("I2C_DIRECT address-only") == 0x40
    # Step 3: unknown sub-command. Expected 00 04.
    raw("I2C_DIRECT unknown sub-command", bytes.fromhex("57 05"), 4)
    assert mode_byte("I2C_DIRECT unknown sub-command") == 0x40
    # Step 4: frame-length boundary, STOP conditions only. 59 bytes expected FF 00; 60 bytes expected 00 02 (D-007).
    raw("I2C_DIRECT 59-byte frame", bytes([iss.I2C_DIRECT]) + bytes([iss.I2C_DIRECT_STOP]) * 58, 4)
    raw("I2C_DIRECT 60-byte frame", bytes([iss.I2C_DIRECT]) + bytes([iss.I2C_DIRECT_STOP]) * 59, 4)
    assert mode_byte("I2C_DIRECT frame-length boundary") == 0x40
    # Step 5: IO_MODE.
    iss.set_mode(hw, iss.build_io_mode(0xAA))
    assert mode_byte("IO_MODE 5A 02 00 AA") == 0x00
    raw("I2C_DIRECT address-only in IO_MODE", bytes.fromhex("57 01 30 A0 03"), 4)
    assert mode_byte("after I2C_DIRECT in IO_MODE") == 0x00
