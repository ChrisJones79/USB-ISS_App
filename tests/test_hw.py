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
        iss.set_mode(hw, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0x0A))
        assert mode_byte("I2C_S_100KHZ 5A 02 40 0A") == 0x40

        frame = iss.build_io_change(0x0F)
        hw.write(frame)
        raw = hw.read(2)
        print(f"HW IO_CHANGE {frame.hex(' ')} raw response: {raw.hex(' ') or '(none)'}")
        mode_byte("IO_CHANGE 5A 02 10 0F")  # logged, not asserted
        assert raw == bytes([0xFF, 0x00])

        iss.set_mode(hw, iss.build_io_mode(0xAA))
        assert mode_byte("IO_MODE 5A 02 00 AA") == 0x00
    finally:
        iss.set_mode(hw, iss.build_i2c_mode(iss.I2C_S_100KHZ, 0x0A))
        assert mode_byte("restore 5A 02 40 0A") == 0x40


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
    """NEXT 02 step 3: p.20 says 00 00 for a channel not set up as analogue."""
    hw, mode_byte, raw = io_hw
    iss.set_mode(hw, iss.build_io_mode(0xAA))
    assert mode_byte("IO_MODE 5A 02 00 AA") == 0x00
    assert raw("GETAD digital", iss.build_get_ad(1), 3) == b"\x00\x00"


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
